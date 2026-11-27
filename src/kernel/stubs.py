"""Versiones básicas (provisionales) de los módulos de los demás integrantes.

Sirven para que el núcleo corra de punta a punta mientras no existan las
versiones reales. Cumplen las firmas de `kernel/contratos.py`.
"""
from collections import deque
from typing import Optional

from kernel.interrupts import IntType
from processes.pcb import PCB, Estado


class SchedulerBasico:
    """Cola FIFO. Sin quantum es FCFS; con quantum se comporta como Round Robin."""

    def __init__(self, quantum: Optional[int] = None):
        self.quantum = quantum
        self.cola = deque()

    def agregar(self, pcb: PCB) -> None:
        self.cola.append(pcb)

    def siguiente(self) -> Optional[PCB]:
        return self.cola.popleft() if self.cola else None

    def quitar(self, pid: int) -> None:
        self.cola = deque(p for p in self.cola if p.pid != pid)


class DispatcherBasico:
    def __init__(self, log):
        self.log = log
        self.cambios_contexto = 0

    def despachar(self, tick: int, saliente: Optional[PCB], entrante: PCB) -> None:
        if saliente is not None and saliente is not entrante:
            self.cambios_contexto += 1
            self.log.log(tick, "DISPATCH",
                         f"Cambio de contexto P{saliente.pid} -> P{entrante.pid}",
                         evento="CAMBIO_CONTEXTO", pid=entrante.pid,
                         saliente=saliente.pid, total=self.cambios_contexto)
        entrante.cambiar_estado(tick, Estado.EJECUCION, self.log, causa="dispatcher")


class MemoriaSinFallos:
    """Toda página está siempre cargada: nunca hay PAGE_FAULT."""

    def __init__(self, log, ic, procesos=None):
        self.log, self.ic, self.procesos = log, ic, procesos or {}

    def acceder(self, tick, pid, pagina) -> bool:
        return True

    def liberar(self, tick, pid) -> None:
        pass

    def mapa_frames(self):
        return []


class MemoriaPorDemanda:
    """Sin límite de frames y sin reemplazo: la primera vez que un proceso toca
    una página hay fallo de página; después ya está cargada."""

    def __init__(self, log, ic, procesos=None):
        self.log, self.ic, self.procesos = log, ic, procesos or {}
        self.cargadas = set()           # (pid, pagina)

    def acceder(self, tick, pid, pagina) -> bool:
        if (pid, pagina) in self.cargadas:
            return True
        self.cargadas.add((pid, pagina))
        self.ic.raise_int(tick, IntType.PAGE_FAULT, pid=pid, pagina=pagina)
        return False

    def liberar(self, tick, pid) -> None:
        self.cargadas = {c for c in self.cargadas if c[0] != pid}

    def mapa_frames(self):
        return []
