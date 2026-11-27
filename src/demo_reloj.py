"""Demo del núcleo: reloj, interrupciones, PCB, scheduler y memoria básicos.

Uso:  python src/demo_reloj.py

Muestra paso a paso un escenario con Round Robin (quantum 3), E/S, fallos de
página y señales STOP / CONT / KILL, y al final un resumen por proceso.
"""
from kernel.interrupts import IntType
from kernel.simulacion import construir
from kernel.stubs import MemoriaPorDemanda, SchedulerBasico
from processes.pcb import PCB

procesos = [
    PCB(pid=1, llegada=0, rafaga_cpu=6, paginas=2, eventos_es=[(3, 2)]),
    PCB(pid=2, llegada=1, rafaga_cpu=4, paginas=2),
    PCB(pid=3, llegada=2, rafaga_cpu=8, paginas=1),
]

reloj = construir(procesos, scheduler=SchedulerBasico(quantum=3),
                  crear_memoria=MemoriaPorDemanda, costo_carga=2)

reloj.programar(8, IntType.SIGNAL, pid=2, senal="STOP")
reloj.programar(14, IntType.SIGNAL, pid=2, senal="CONT")
reloj.programar(12, IntType.SIGNAL, pid=3, senal="KILL")

razon = reloj.ejecutar()

print()
print(f"Simulación: {razon} (tick final {reloj.tick})")
print(f"Cambios de contexto: {reloj.s.dispatcher.cambios_contexto}")
print(f"{'PID':>4} {'llegada':>8} {'1ª CPU':>7} {'fin':>5} {'espera':>7} {'estado':>11}")
for p in procesos:
    print(f"{p.pid:>4} {p.llegada:>8} {p.primera_ejecucion!s:>7} {p.fin!s:>5} "
          f"{p.espera:>7} {p.estado.value:>11}")
