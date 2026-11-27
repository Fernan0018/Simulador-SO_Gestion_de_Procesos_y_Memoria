"""Arma una simulación completa lista para correr."""
from typing import Callable, List, Optional

from kernel.clock import Reloj
from kernel.handlers import Manejadores
from kernel.interrupts import InterruptController
from kernel.sistema import Sistema
from kernel.stubs import DispatcherBasico, MemoriaSinFallos, SchedulerBasico
from kernel.transaction_log import TransactionLog
from processes.pcb import PCB


def construir(procesos: List[PCB], scheduler=None, dispatcher=None,
              crear_memoria: Optional[Callable] = None, costo_carga: int = 2,
              log: Optional[TransactionLog] = None, echo: bool = True) -> Reloj:
    """Devuelve el `Reloj` de una simulación nueva (`reloj.s` es el `Sistema`).

    - `scheduler` y `dispatcher`: instancias que cumplan `kernel/contratos.py`.
    - `crear_memoria(log, ic, procesos)`: clase o función que devuelve el gestor de
      memoria. Recibe el log, el controlador de interrupciones (para levantar
      PAGE_FAULT) y el diccionario pid -> PCB.
    - Lo que no se pase usa las versiones básicas de `kernel/stubs.py`.
    """
    log = log or TransactionLog(echo=echo)
    ic = InterruptController(log)
    scheduler = scheduler or SchedulerBasico()
    dispatcher = dispatcher or DispatcherBasico(log)
    sistema = Sistema(log, ic, scheduler, dispatcher, None, procesos, costo_carga)
    # La memoria recibe los mismos PCB que usa el núcleo (para leer estado y páginas).
    crear_memoria = crear_memoria or MemoriaSinFallos
    sistema.memoria = crear_memoria(log, ic, sistema.procesos)
    Manejadores(sistema).registrar()
    return Reloj(sistema)
