"""Manejadores de interrupciones: cada uno recibe `(tick, **payload)`.

Los manejadores solo cambian el estado del sistema (PCB, scheduler, memoria);
quien levanta las interrupciones es el reloj (ver `kernel/clock.py`).
Si llega una interrupción "vieja" (p. ej. de un proceso que ya no está en la
CPU) se ignora y queda registrada como INT_IGNORADA.
"""
from kernel.interrupts import IntType
from kernel.sistema import Sistema
from processes.pcb import PCB, Estado

# Interrupciones de un proceso que se descartan cuando se le hace KILL.
PENDIENTES_AL_MATAR = {IntType.IO_COMPLETE, IntType.PROCESS_END, IntType.IO_REQUEST,
                       IntType.TIMER, IntType.PAGE_FAULT}


class Manejadores:
    def __init__(self, sistema: Sistema):
        self.s = sistema

    def registrar(self) -> None:
        ic = self.s.ic
        ic.register(IntType.PROCESS_ARRIVAL, self.llegada)
        ic.register(IntType.IO_REQUEST, self.solicitud_es)
        ic.register(IntType.IO_COMPLETE, self.fin_es)
        ic.register(IntType.PAGE_FAULT, self.fallo_pagina)
        ic.register(IntType.PROCESS_END, self.fin_proceso)
        ic.register(IntType.TIMER, self.timer)
        ic.register(IntType.DIV_ZERO, self.division_cero)
        ic.register(IntType.SIGNAL, self.senal)

    # --- utilidades --------------------------------------------------------

    def _ignorar(self, tick, pid, que, motivo):
        self.s.log.log(tick, "KERNEL", f"{que} de P{pid} ignorada: {motivo}",
                       evento="INT_IGNORADA", pid=pid, que=que)

    def _pcb(self, tick, pid, que):
        pcb = self.s.procesos.get(pid)
        if pcb is None:
            self._ignorar(tick, pid, que, "el proceso no existe")
        return pcb

    def _en_cpu(self, tick, pid, que):
        """Devuelve el PCB si realmente está ejecutándose; si no, ignora."""
        pcb = self._pcb(tick, pid, que)
        if pcb is None:
            return None
        if self.s.cpu is not pcb or pcb.estado is not Estado.EJECUCION:
            self._ignorar(tick, pid, que, f"no está en la CPU (estado {pcb.estado.value})")
            return None
        return pcb

    def _terminar(self, tick, pcb: PCB, causa: str):
        self.s.liberar_cpu(pcb)
        self.s.esperas.pop(pcb.pid, None)
        pcb.cambiar_estado(tick, Estado.TERMINADO, self.s.log, causa=causa)
        self.s.memoria.liberar(tick, pcb.pid)

    # --- interrupciones ----------------------------------------------------

    def llegada(self, tick, pid):
        pcb = self._pcb(tick, pid, "PROCESS_ARRIVAL")
        if pcb is None:
            return
        if pcb.estado is not Estado.NUEVO:
            return self._ignorar(tick, pid, "PROCESS_ARRIVAL", f"ya está {pcb.estado.value}")
        pcb.cambiar_estado(tick, Estado.LISTO, self.s.log, causa="PROCESS_ARRIVAL")
        self.s.scheduler.agregar(pcb)

    def solicitud_es(self, tick, pid, duracion):
        pcb = self._en_cpu(tick, pid, "IO_REQUEST")
        if pcb is None:
            return
        self.s.liberar_cpu(pcb)
        pcb.cambiar_estado(tick, Estado.BLOQUEADO, self.s.log, causa=f"IO_REQUEST ({duracion} ticks)")
        self.s.esperas[pid] = max(1, duracion)

    def fallo_pagina(self, tick, pid, pagina):
        pcb = self._en_cpu(tick, pid, "PAGE_FAULT")
        if pcb is None:
            return
        self.s.liberar_cpu(pcb)
        pcb.cambiar_estado(tick, Estado.BLOQUEADO, self.s.log,
                           causa=f"PAGE_FAULT página {pagina}")
        self.s.esperas[pid] = max(1, self.s.costo_carga)

    def fin_es(self, tick, pid):
        """Termina una E/S o una carga de página."""
        pcb = self._pcb(tick, pid, "IO_COMPLETE")
        if pcb is None:
            return
        antes = pcb.estado
        if antes not in (Estado.BLOQUEADO, Estado.SUSPENDIDO):
            return self._ignorar(tick, pid, "IO_COMPLETE", f"está {antes.value}")
        pcb.es_completada(tick, self.s.log)
        if antes is Estado.BLOQUEADO and pcb.estado is Estado.LISTO:
            self.s.scheduler.agregar(pcb)

    def fin_proceso(self, tick, pid):
        pcb = self._en_cpu(tick, pid, "PROCESS_END")
        if pcb is not None:
            self._terminar(tick, pcb, "PROCESS_END")

    def division_cero(self, tick, pid):
        pcb = self._en_cpu(tick, pid, "DIV_ZERO")
        if pcb is not None:
            self._terminar(tick, pcb, "DIV_ZERO")

    def timer(self, tick, pid):
        """Fin de quantum: el proceso vuelve a la cola de listos."""
        pcb = self._en_cpu(tick, pid, "TIMER")
        if pcb is None:
            return
        self.s.liberar_cpu(pcb)
        pcb.cambiar_estado(tick, Estado.LISTO, self.s.log, causa="TIMER")
        self.s.scheduler.agregar(pcb)

    # --- señales -----------------------------------------------------------

    def senal(self, tick, pid, senal):
        pcb = self._pcb(tick, pid, f"SIGNAL {senal}")
        if pcb is None:
            return
        accion = {"KILL": self._kill, "STOP": self._stop, "CONT": self._cont}.get(senal)
        if accion is None:
            return self._ignorar(tick, pid, f"SIGNAL {senal}", "señal desconocida")
        accion(tick, pcb)

    def _kill(self, tick, pcb: PCB):
        if pcb.estado in (Estado.NUEVO, Estado.TERMINADO):
            return self._ignorar(tick, pcb.pid, "SIGNAL KILL", f"está {pcb.estado.value}")
        if pcb.estado is Estado.LISTO:
            self.s.scheduler.quitar(pcb.pid)
        self.s.ic.descartar(tick, pcb.pid, PENDIENTES_AL_MATAR)
        self._terminar(tick, pcb, "KILL")

    def _stop(self, tick, pcb: PCB):
        if pcb.estado not in (Estado.LISTO, Estado.EJECUCION, Estado.BLOQUEADO):
            return self._ignorar(tick, pcb.pid, "SIGNAL STOP", f"está {pcb.estado.value}")
        if pcb.estado is Estado.LISTO:
            self.s.scheduler.quitar(pcb.pid)
        self.s.liberar_cpu(pcb)
        # Si estaba BLOQUEADO, su E/S sigue pendiente: self.s.esperas no se toca.
        pcb.cambiar_estado(tick, Estado.SUSPENDIDO, self.s.log, causa="STOP")

    def _cont(self, tick, pcb: PCB):
        if pcb.estado is not Estado.SUSPENDIDO:
            return self._ignorar(tick, pcb.pid, "SIGNAL CONT", f"está {pcb.estado.value}")
        pcb.reanudar(tick, self.s.log)
        if pcb.estado is Estado.LISTO:
            self.s.scheduler.agregar(pcb)
