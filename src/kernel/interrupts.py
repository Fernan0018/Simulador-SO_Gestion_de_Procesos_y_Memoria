import heapq
import itertools
from dataclasses import dataclass, field
from enum import IntEnum


class IntType(IntEnum):          # número menor = mayor prioridad (a acordar)
    DIV_ZERO = 1                 # excepción: división entre cero
    PAGE_FAULT = 2               # excepción: fallo de página
    IO_COMPLETE = 3              # fin de E/S (incluye carga de página desde disco)
    IO_REQUEST = 4               # el proceso solicita E/S
    PROCESS_END = 5              # el proceso terminó su ráfaga
    TIMER = 6                    # fin de quantum (Round Robin)
    PROCESS_ARRIVAL = 7          # llega un proceso nuevo al sistema
    SIGNAL = 8                   # señal externa (KILL, STOP, CONT)


NOMBRES = {
    IntType.DIV_ZERO: "División entre cero",
    IntType.PAGE_FAULT: "Fallo de página",
    IntType.IO_COMPLETE: "Fin de E/S",
    IntType.IO_REQUEST: "Solicitud de E/S",
    IntType.PROCESS_END: "Fin de proceso",
    IntType.TIMER: "Fin de quantum (timer)",
    IntType.PROCESS_ARRIVAL: "Llegada de proceso",
    IntType.SIGNAL: "Señal",
}


@dataclass(order=True)
class Interrupt:
    priority: int
    seq: int
    kind: IntType = field(compare=False)
    payload: dict = field(compare=False, default_factory=dict)


class InterruptController:
    def __init__(self, log):
        self.queue, self.handlers, self.log = [], {}, log
        self._seq = itertools.count()

    def register(self, kind, handler):
        self.handlers[kind] = handler

    def raise_int(self, tick, kind, **payload):
        heapq.heappush(self.queue, Interrupt(int(kind), next(self._seq), kind, payload))
        self.log.log(tick, "INT", f"{NOMBRES[kind]} ({kind.name}) encolada {payload}",
                     evento="INT_ENCOLADA", tipo=kind.name, **payload)

    def dispatch_all(self, tick):
        while self.queue:
            irq = heapq.heappop(self.queue)
            self.log.log(tick, "INT", f"Atendiendo {NOMBRES[irq.kind]} ({irq.kind.name})",
                         evento="INT_ATENDIDA", tipo=irq.kind.name, **irq.payload)
            handler = self.handlers.get(irq.kind)
            if handler is None:
                self.log.log(tick, "INT", f"Sin manejador registrado para {irq.kind.name}",
                             evento="INT_SIN_MANEJADOR", tipo=irq.kind.name)
                continue
            handler(tick, **irq.payload)

    def descartar(self, tick, pid, tipos):
        """Quita de la cola las interrupciones pendientes de `pid` de esos tipos
        (p. ej. al hacer KILL). Devuelve cuántas descartó."""
        quedan = [i for i in self.queue
                  if not (i.payload.get("pid") == pid and i.kind in tipos)]
        quitadas = [i for i in self.queue
                    if i.payload.get("pid") == pid and i.kind in tipos]
        if quitadas:
            self.queue[:] = quedan
            heapq.heapify(self.queue)
            for irq in sorted(quitadas):
                self.log.log(tick, "INT",
                             f"{NOMBRES[irq.kind]} ({irq.kind.name}) de P{pid} descartada",
                             evento="INT_DESCARTADA", tipo=irq.kind.name, pid=pid)
        return len(quitadas)
