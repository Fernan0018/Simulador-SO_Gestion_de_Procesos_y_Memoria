from kernel.transaction_log import TransactionLog
from kernel.interrupts import InterruptController, IntType

log = TransactionLog()
ic = InterruptController(log)

ic.register(IntType.TIMER, lambda t, **p: log.log(t, "SCHED", "Fin de quantum (pendiente: planificador)"))
ic.register(IntType.PAGE_FAULT, lambda t, **p: log.log(t, "MEM", f"Fallo de página {p} (pendiente: reemplazo)"))

ic.raise_int(1, IntType.TIMER)
ic.raise_int(1, IntType.PAGE_FAULT, pid=2, page=5)
ic.raise_int(1, IntType.DIV_ZERO, pid=3)      # sin manejador a propósito: queda en el log
ic.dispatch_all(1)

# Los eventos quedan como datos, listos para la UI y las métricas
print()
print("Eventos guardados:", len(log.entries))
print("Primer evento:", log.entries[0])