import heapq, itertools
from dataclasses import dataclass, field
from enum import IntEnum

class IntType(IntEnum):      # número menor = mayor prioridad
    PAGE_FAULT = 1
    IO_COMPLETE = 2
    TIMER = 3
    SIGNAL = 4

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
        self.log.log(tick, "INT", f"{kind.name} encolada {payload}")

    def dispatch_all(self, tick):
        while self.queue:
            irq = heapq.heappop(self.queue)
            self.log.log(tick, "INT", f"Atendiendo {irq.kind.name}")
            self.handlers[irq.kind](tick, **irq.payload)