import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from kernel.handlers import Manejadores
from kernel.interrupts import IntType
from kernel.simulacion import construir
from kernel.stubs import MemoriaSinFallos
from processes.pcb import PCB, Estado


class MemoriaEspia(MemoriaSinFallos):
    def __init__(self, log, ic, procesos=None):
        super().__init__(log, ic, procesos)
        self.liberadas = []

    def liberar(self, tick, pid):
        self.liberadas.append(pid)


def sim(*procesos):
    """Simulación con memoria espía. Devuelve (sistema, manejadores)."""
    reloj = construir(list(procesos), crear_memoria=MemoriaEspia, echo=False)
    return reloj.s, Manejadores(reloj.s)


def llegan_todos(s):
    for p in s.procesos.values():
        s.ic.raise_int(0, IntType.PROCESS_ARRIVAL, pid=p.pid)
    s.ic.dispatch_all(0)


def en_cpu(s):
    """Todos llegan y el primero de la cola toma la CPU."""
    llegan_todos(s)
    s.asignar_cpu(0)


def eventos(s, nombre):
    return [e for e in s.log.entries if e.evento == nombre]


class TestFlujoBasico(unittest.TestCase):
    def test_llegada_pasa_a_listo_y_entra_al_scheduler(self):
        s, _ = sim(PCB(1, 0, 3))
        llegan_todos(s)
        self.assertIs(s.procesos[1].estado, Estado.LISTO)
        self.assertEqual([p.pid for p in s.scheduler.cola], [1])

    def test_solicitud_es_bloquea_y_libera_la_cpu(self):
        s, _ = sim(PCB(1, 0, 5))
        en_cpu(s)
        s.ic.raise_int(1, IntType.IO_REQUEST, pid=1, duracion=3)
        s.ic.dispatch_all(1)
        self.assertIs(s.procesos[1].estado, Estado.BLOQUEADO)
        self.assertIsNone(s.cpu)
        self.assertEqual(s.esperas, {1: 3})

    def test_fin_es_devuelve_a_listos(self):
        s, _ = sim(PCB(1, 0, 5))
        en_cpu(s)
        s.ic.raise_int(1, IntType.IO_REQUEST, pid=1, duracion=2)
        s.ic.dispatch_all(1)
        s.ic.raise_int(3, IntType.IO_COMPLETE, pid=1)
        s.ic.dispatch_all(3)
        self.assertIs(s.procesos[1].estado, Estado.LISTO)
        self.assertEqual([p.pid for p in s.scheduler.cola], [1])

    def test_fallo_de_pagina_bloquea_con_el_costo_de_carga(self):
        s, _ = sim(PCB(1, 0, 5))
        en_cpu(s)
        s.ic.raise_int(1, IntType.PAGE_FAULT, pid=1, pagina=0)
        s.ic.dispatch_all(1)
        self.assertIs(s.procesos[1].estado, Estado.BLOQUEADO)
        self.assertEqual(s.esperas, {1: s.costo_carga})

    def test_fin_de_proceso_termina_y_libera_memoria(self):
        s, _ = sim(PCB(1, 0, 5))
        en_cpu(s)
        s.ic.raise_int(5, IntType.PROCESS_END, pid=1)
        s.ic.dispatch_all(5)
        p = s.procesos[1]
        self.assertIs(p.estado, Estado.TERMINADO)
        self.assertEqual(p.fin, 5)
        self.assertEqual(s.memoria.liberadas, [1])
        self.assertIsNone(s.cpu)

    def test_timer_devuelve_el_proceso_a_la_cola(self):
        s, _ = sim(PCB(1, 0, 5), PCB(2, 0, 5))
        en_cpu(s)
        s.ic.raise_int(2, IntType.TIMER, pid=1)
        s.ic.dispatch_all(2)
        self.assertIs(s.procesos[1].estado, Estado.LISTO)
        self.assertEqual([p.pid for p in s.scheduler.cola], [2, 1])

    def test_division_entre_cero_termina_el_proceso(self):
        s, _ = sim(PCB(1, 0, 5))
        en_cpu(s)
        s.ic.raise_int(2, IntType.DIV_ZERO, pid=1)
        s.ic.dispatch_all(2)
        self.assertIs(s.procesos[1].estado, Estado.TERMINADO)
        self.assertEqual(s.memoria.liberadas, [1])


class TestInterrupcionesViejas(unittest.TestCase):
    def test_timer_de_un_proceso_que_no_esta_en_cpu_se_ignora(self):
        s, m = sim(PCB(1, 0, 5), PCB(2, 0, 5))
        en_cpu(s)                               # P1 en CPU, P2 LISTO
        m.timer(1, pid=2)
        self.assertIs(s.procesos[2].estado, Estado.LISTO)
        self.assertEqual(len(eventos(s, "INT_IGNORADA")), 1)

    def test_fin_de_proceso_de_un_proceso_terminado_se_ignora(self):
        s, m = sim(PCB(1, 0, 5))
        en_cpu(s)
        m.fin_proceso(5, pid=1)
        m.fin_proceso(5, pid=1)                 # repetida: no debe lanzar TransicionInvalida
        self.assertEqual(len(eventos(s, "INT_IGNORADA")), 1)

    def test_pid_inexistente_se_ignora(self):
        s, m = sim(PCB(1, 0, 5))
        m.fin_es(1, pid=99)
        self.assertEqual(len(eventos(s, "INT_IGNORADA")), 1)


class TestKill(unittest.TestCase):
    def comprobar_muerto(self, s, pid):
        self.assertIs(s.procesos[pid].estado, Estado.TERMINADO)
        self.assertIn(pid, s.memoria.liberadas)
        self.assertNotIn(pid, s.esperas)
        self.assertNotIn(pid, [p.pid for p in s.scheduler.cola])
        self.assertIsNot(s.cpu, s.procesos[pid])

    def test_kill_en_listo(self):
        s, m = sim(PCB(1, 0, 5), PCB(2, 0, 5))
        en_cpu(s)                               # P2 queda LISTO
        m.senal(1, pid=2, senal="KILL")
        self.comprobar_muerto(s, 2)

    def test_kill_en_ejecucion(self):
        s, m = sim(PCB(1, 0, 5))
        en_cpu(s)
        m.senal(1, pid=1, senal="KILL")
        self.comprobar_muerto(s, 1)

    def test_kill_en_bloqueado(self):
        s, m = sim(PCB(1, 0, 5))
        en_cpu(s)
        s.ic.raise_int(1, IntType.IO_REQUEST, pid=1, duracion=4)
        s.ic.dispatch_all(1)
        m.senal(2, pid=1, senal="KILL")
        self.comprobar_muerto(s, 1)

    def test_kill_en_suspendido(self):
        s, m = sim(PCB(1, 0, 5))
        en_cpu(s)
        m.senal(1, pid=1, senal="STOP")
        m.senal(2, pid=1, senal="KILL")
        self.comprobar_muerto(s, 1)

    def test_kill_sobre_nuevo_se_ignora(self):
        s, m = sim(PCB(1, 5, 5))
        m.senal(1, pid=1, senal="KILL")
        self.assertIs(s.procesos[1].estado, Estado.NUEVO)
        self.assertEqual(len(eventos(s, "INT_IGNORADA")), 1)

    def test_kill_descarta_interrupciones_pendientes_del_proceso(self):
        s, m = sim(PCB(1, 0, 5), PCB(2, 0, 5))
        en_cpu(s)
        s.ic.raise_int(1, IntType.IO_COMPLETE, pid=1)
        s.ic.raise_int(1, IntType.PROCESS_END, pid=1)
        s.ic.raise_int(1, IntType.IO_COMPLETE, pid=2)     # de otro proceso: se queda
        m.senal(1, pid=1, senal="KILL")
        quedan = [(i.kind, i.payload["pid"]) for i in s.ic.queue]
        self.assertEqual(quedan, [(IntType.IO_COMPLETE, 2)])
        self.assertEqual(len(eventos(s, "INT_DESCARTADA")), 2)


class TestStopYCont(unittest.TestCase):
    def test_stop_en_listo_lo_saca_de_la_cola_y_cont_lo_devuelve(self):
        s, m = sim(PCB(1, 0, 5), PCB(2, 0, 5))
        en_cpu(s)
        m.senal(1, pid=2, senal="STOP")
        self.assertIs(s.procesos[2].estado, Estado.SUSPENDIDO)
        self.assertEqual([p.pid for p in s.scheduler.cola], [])
        m.senal(2, pid=2, senal="CONT")
        self.assertIs(s.procesos[2].estado, Estado.LISTO)
        self.assertEqual([p.pid for p in s.scheduler.cola], [2])

    def test_stop_en_ejecucion_libera_la_cpu(self):
        s, m = sim(PCB(1, 0, 5))
        en_cpu(s)
        m.senal(1, pid=1, senal="STOP")
        self.assertIsNone(s.cpu)
        self.assertIs(s.procesos[1].estado, Estado.SUSPENDIDO)

    def test_stop_en_bloqueado_deja_la_es_pendiente(self):
        s, m = sim(PCB(1, 0, 5))
        en_cpu(s)
        s.ic.raise_int(1, IntType.IO_REQUEST, pid=1, duracion=4)
        s.ic.dispatch_all(1)
        m.senal(2, pid=1, senal="STOP")
        self.assertIs(s.procesos[1].estado, Estado.SUSPENDIDO)
        self.assertTrue(s.procesos[1].espera_es)
        self.assertEqual(s.esperas, {1: 4})          # la cuenta regresiva sigue

    def test_es_completada_estando_suspendido_no_lo_reanuda(self):
        s, m = sim(PCB(1, 0, 5))
        en_cpu(s)
        s.ic.raise_int(1, IntType.IO_REQUEST, pid=1, duracion=1)
        s.ic.dispatch_all(1)
        m.senal(2, pid=1, senal="STOP")
        s.ic.raise_int(3, IntType.IO_COMPLETE, pid=1)
        s.ic.dispatch_all(3)
        self.assertIs(s.procesos[1].estado, Estado.SUSPENDIDO)
        self.assertEqual(len(eventos(s, "ES_COMPLETADA_SUSPENDIDO")), 1)
        self.assertEqual([p.pid for p in s.scheduler.cola], [])
        m.senal(4, pid=1, senal="CONT")              # ahora sí vuelve, a LISTO
        self.assertIs(s.procesos[1].estado, Estado.LISTO)
        self.assertEqual([p.pid for p in s.scheduler.cola], [1])

    def test_cont_con_es_pendiente_vuelve_a_bloqueado(self):
        s, m = sim(PCB(1, 0, 5))
        en_cpu(s)
        s.ic.raise_int(1, IntType.IO_REQUEST, pid=1, duracion=4)
        s.ic.dispatch_all(1)
        m.senal(2, pid=1, senal="STOP")
        m.senal(3, pid=1, senal="CONT")
        self.assertIs(s.procesos[1].estado, Estado.BLOQUEADO)
        self.assertEqual([p.pid for p in s.scheduler.cola], [])

    def test_senales_que_no_aplican_se_ignoran(self):
        s, m = sim(PCB(1, 0, 5))
        en_cpu(s)
        m.senal(1, pid=1, senal="CONT")              # no estaba suspendido
        m.senal(1, pid=1, senal="PAUSA")             # señal desconocida
        self.assertIs(s.procesos[1].estado, Estado.EJECUCION)
        self.assertEqual(len(eventos(s, "INT_IGNORADA")), 2)


if __name__ == "__main__":
    unittest.main()
