"""Reloj de la simulación.

El reloj es el dueño del tiempo y el que levanta las interrupciones del sistema:
PROCESS_ARRIVAL, IO_REQUEST, IO_COMPLETE (incluye la carga de páginas),
PROCESS_END y TIMER. Las que vienen de afuera (SIGNAL, DIV_ZERO) las programa
el escenario con `programar()`. PAGE_FAULT la levanta la memoria en `acceder()`.

Modelo de tiempo: `avanzar()` procesa el instante `t` y deja la CPU trabajando
durante [t, t+1). Los eventos que resultan de ese trabajo (fin de ráfaga,
pedido de E/S, fin de quantum, fallo de página) quedan con tiempo t+1 y se
atienden al inicio del siguiente avance. Por eso el `fin` de un proceso que
llegó en 0 y tiene ráfaga 3 es 3.

Orden dentro de un avance:
  1. llegadas del instante       4. dispatch_all (atiende todo por prioridad)
  2. señales programadas         5. si la CPU está libre: scheduler + dispatcher
  3. cuenta regresiva de E/S     6. foto del tick (evento TICK) y tiempo de espera
                                 7. la CPU trabaja un tick
"""
from collections import defaultdict
from typing import Dict, List, Tuple

from kernel.interrupts import IntType
from kernel.sistema import Sistema
from processes.pcb import Estado


class Reloj:
    def __init__(self, sistema: Sistema):
        self.s = sistema
        self.tick = 0
        self.externos: Dict[int, List[Tuple[IntType, dict]]] = defaultdict(list)
        self._anunciados = set()        # pids cuya llegada ya se levantó

    # --- escenario ---------------------------------------------------------

    def programar(self, tick: int, tipo: IntType, **payload) -> None:
        """Agenda una interrupción externa (p. ej. SIGNAL o DIV_ZERO) para un instante."""
        self.externos[tick].append((tipo, payload))

    # --- estado de la simulación -------------------------------------------

    @property
    def terminado(self) -> bool:
        return all(p.estado is Estado.TERMINADO for p in self.s.procesos.values())

    @property
    def estancado(self) -> bool:
        """Nada puede volver a cambiar (p. ej. solo quedan procesos SUSPENDIDOS)."""
        s = self.s
        hay_futuro = any(p.estado is Estado.NUEVO for p in s.procesos.values()) or \
            any(t >= self.tick and evs for t, evs in self.externos.items())
        hay_actividad = bool(s.esperas) or bool(s.ic.queue) or any(
            p.estado in (Estado.LISTO, Estado.EJECUCION) for p in s.procesos.values())
        return not (hay_futuro or hay_actividad)

    def ejecutar(self, max_ticks: int = 10_000) -> str:
        """Avanza hasta que todo termine. Devuelve TERMINADO, ESTANCADO o LIMITE."""
        while self.tick < max_ticks:
            if self.terminado:
                return "TERMINADO"
            if self.estancado:
                return "ESTANCADO"
            self.avanzar()
        return "LIMITE"

    # --- un tick -----------------------------------------------------------

    def avanzar(self) -> None:
        t = self.tick
        s = self.s
        self._levantar_llegadas(t)
        self._levantar_externos(t)
        self._avanzar_esperas(t)
        s.ic.dispatch_all(t)
        s.asignar_cpu(t)
        self._foto_del_tick(t)
        self._acumular_espera()
        self._trabajar_cpu(t)
        self.tick = t + 1

    def _levantar_llegadas(self, t):
        for pcb in self.s.procesos.values():
            if pcb.estado is Estado.NUEVO and pcb.llegada <= t \
                    and pcb.pid not in self._anunciados:
                self._anunciados.add(pcb.pid)
                self.s.ic.raise_int(t, IntType.PROCESS_ARRIVAL, pid=pcb.pid)

    def _levantar_externos(self, t):
        for tipo, payload in self.externos.get(t, []):
            self.s.ic.raise_int(t, tipo, **payload)

    def _avanzar_esperas(self, t):
        """Cuenta regresiva de las E/S y cargas de página en curso."""
        for pid in list(self.s.esperas):
            self.s.esperas[pid] -= 1
            if self.s.esperas[pid] <= 0:
                del self.s.esperas[pid]
                self.s.ic.raise_int(t, IntType.IO_COMPLETE, pid=pid)

    def _foto_del_tick(self, t):
        s = self.s
        listos = [p.pid for p in s.procesos_en(Estado.LISTO)]
        bloqueados = [p.pid for p in s.procesos_en(Estado.BLOQUEADO)]
        suspendidos = [p.pid for p in s.procesos_en(Estado.SUSPENDIDO)]
        cpu = s.cpu.pid if s.cpu else None
        s.log.log(t, "RELOJ",
                  f"CPU: {'P' + str(cpu) if cpu else 'libre'} | listos: {listos} | "
                  f"bloqueados: {bloqueados} | suspendidos: {suspendidos}",
                  evento="TICK", pid=cpu, listos=listos, bloqueados=bloqueados,
                  suspendidos=suspendidos)

    def _acumular_espera(self):
        for pcb in self.s.procesos_en(Estado.LISTO):
            pcb.espera += 1

    def _trabajar_cpu(self, t):
        """La CPU ejecuta un tick del proceso actual y levanta lo que resulte."""
        s = self.s
        pcb = s.cpu
        if pcb is None:
            return
        ahora = t + 1                   # instante en que terminan los efectos
        if not s.memoria.acceder(ahora, pcb.pid, s.pagina_de(pcb)):
            return                      # fallo de página: la memoria levantó PAGE_FAULT
        pcb.rafaga_restante -= 1
        if s.quantum_restante is not None:
            s.quantum_restante -= 1
        if pcb.rafaga_restante == 0:
            s.ic.raise_int(ahora, IntType.PROCESS_END, pid=pcb.pid)
            return
        pedido = next((dur for en, dur in pcb.eventos_es if en == s.consumido(pcb)), None)
        if pedido is not None:
            s.ic.raise_int(ahora, IntType.IO_REQUEST, pid=pcb.pid, duracion=pedido)
        elif s.quantum_restante == 0:
            s.ic.raise_int(ahora, IntType.TIMER, pid=pcb.pid)
