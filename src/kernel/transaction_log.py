from dataclasses import dataclass, field
from typing import Callable, Optional


@dataclass
class Evento:
    """Un paso del sistema, guardado como datos (no solo como texto)."""
    n: int
    tick: int
    componente: str
    mensaje: str
    evento: Optional[str] = None    # p. ej. CAMBIO_ESTADO, CAMBIO_CONTEXTO, INT_ATENDIDA
    pid: Optional[int] = None
    antes: Optional[str] = None     # estado anterior (si aplica)
    despues: Optional[str] = None   # estado nuevo (si aplica)
    datos: dict = field(default_factory=dict)

    def __str__(self):
        return f"[#{self.n:03d} t={self.tick:03d}] {self.componente:<10} {self.mensaje}"


class TransactionLog:
    """Registro transaccional: cada paso queda guardado y se avisa en vivo."""

    def __init__(self, echo=True):
        self.entries = []        # lista de Evento
        self.echo = echo         # imprimir cada línea en consola
        self._listeners = []

    def subscribe(self, callback: Callable[[Evento], None]):
        """La UI (o las métricas) se suscriben para recibir cada evento en vivo."""
        self._listeners.append(callback)

    def log(self, tick, component, message, evento=None, pid=None,
            antes=None, despues=None, **datos):
        e = Evento(len(self.entries) + 1, tick, component, message,
                   evento, pid, antes, despues, datos)
        self.entries.append(e)
        if self.echo:
            print(e)
        for callback in self._listeners:
            callback(e)
        return e