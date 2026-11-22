from kernel.transaction_log import TransactionLog
from kernel.interrupts import InterruptController, IntType

log = TransactionLog()
ic = InterruptController(log)
ic.register(IntType.TIMER, lambda t, **p: log.log(t, "SCHED", "Fin de quantum (pendiente: planificador)"))
ic.register(IntType.PAGE_FAULT, lambda t, **p: log.log(t, "MEM", f"Fallo de página {p} (pendiente: reemplazo)"))

ic.raise_int(1, IntType.TIMER)
ic.raise_int(1, IntType.PAGE_FAULT, pid=2, page=5)
ic.dispatch_all(1)   # PAGE_FAULT se atiende antes que TIMER por prioridad