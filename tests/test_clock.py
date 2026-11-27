import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from kernel.interrupts import IntType
from kernel.simulacion import construir
from kernel.stubs import MemoriaPorDemanda, SchedulerBasico
from processes.pcb import PCB, Estado


def corre(procesos, **kw):
    reloj = construir(procesos, echo=False, **kw)
    razon = reloj.ejecutar()
    return reloj, razon


def eventos(reloj, nombre):
    return [e for e in reloj.s.log.entries if e.evento == nombre]


class TestPlanificacion(unittest.TestCase):
    def test_fcfs_dos_procesos(self):
        p1, p2 = PCB(1, 0, 3), PCB(2, 1, 2)
        reloj, razon = corre([p1, p2])
        self.assertEqual(razon, "TERMINADO")
        self.assertEqual((p1.primera_ejecucion, p1.fin, p1.espera), (0, 3, 0))
        self.assertEqual((p2.primera_ejecucion, p2.fin, p2.espera), (3, 5, 2))
        self.assertEqual(reloj.s.dispatcher.cambios_contexto, 1)

    def test_round_robin_quantum_2(self):
        p1, p2 = PCB(1, 0, 4), PCB(2, 0, 3)
        reloj, razon = corre([p1, p2], scheduler=SchedulerBasico(quantum=2))
        self.assertEqual(razon, "TERMINADO")
        self.assertEqual((p1.fin, p2.fin), (6, 7))
        self.assertEqual((p1.espera, p2.espera), (2, 4))
        self.assertEqual(reloj.s.dispatcher.cambios_contexto, 3)
        self.assertEqual(len(eventos(reloj, "CAMBIO_CONTEXTO")), 3)

    def test_la_cpu_espera_si_el_proceso_llega_tarde(self):
        p = PCB(1, 3, 2)
        reloj, _ = corre([p])
        self.assertEqual((p.primera_ejecucion, p.fin), (3, 5))

    def test_si_fin_de_rafaga_y_quantum_coinciden_gana_el_fin(self):
        p = PCB(1, 0, 2)
        reloj, _ = corre([p], scheduler=SchedulerBasico(quantum=2))
        self.assertEqual(p.fin, 2)
        self.assertEqual(eventos(reloj, "CAMBIO_ESTADO")[-1].despues, "TERMINADO")


class TestEntradaSalida(unittest.TestCase):
    def test_es_dura_lo_pedido(self):
        # pide E/S de 3 ticks al consumir 2; vuelve en 2 + 3 = 5 y termina en 7
        p = PCB(1, 0, 4, eventos_es=[(2, 3)])
        reloj, _ = corre([p])
        self.assertEqual(p.fin, 7)

    def test_otro_proceso_usa_la_cpu_durante_la_es(self):
        p1 = PCB(1, 0, 3, eventos_es=[(1, 4)])
        p2 = PCB(2, 0, 3)
        reloj, _ = corre([p1, p2])
        # P1 corre 1 tick y se bloquea hasta t=5; P2 usa la CPU de 1 a 4
        self.assertEqual(p2.fin, 4)
        self.assertEqual(p1.fin, 7)

    def test_es_pedida_al_final_de_la_rafaga_se_ignora(self):
        p = PCB(1, 0, 2, eventos_es=[(2, 5)])
        reloj, _ = corre([p])
        self.assertEqual(p.fin, 2)


class TestMemoria(unittest.TestCase):
    def test_fallos_de_pagina_con_costo_2(self):
        p = PCB(1, 0, 2, paginas=2)
        reloj, razon = corre([p], crear_memoria=MemoriaPorDemanda)
        self.assertEqual(razon, "TERMINADO")
        self.assertEqual(p.fin, 8)
        atendidos = [e for e in eventos(reloj, "INT_ATENDIDA")
                     if e.datos["tipo"] == "PAGE_FAULT"]
        self.assertEqual(len(atendidos), 2)

    def test_el_costo_de_carga_es_configurable(self):
        p = PCB(1, 0, 1, paginas=1)
        reloj, _ = corre([p], crear_memoria=MemoriaPorDemanda, costo_carga=3)
        self.assertEqual(p.fin, 5)

    def test_la_memoria_recibe_los_mismos_pcb_del_nucleo(self):
        p = PCB(1, 0, 1)
        reloj = construir([p], crear_memoria=MemoriaPorDemanda, echo=False)
        self.assertIs(reloj.s.memoria.procesos[1], p)

    def test_la_memoria_se_libera_al_terminar(self):
        p = PCB(1, 0, 1)
        reloj, _ = corre([p], crear_memoria=MemoriaPorDemanda)
        self.assertEqual(reloj.s.memoria.cargadas, set())


class TestSenalesProgramadas(unittest.TestCase):
    def test_kill_programado(self):
        p = PCB(1, 0, 10)
        reloj = construir([p], echo=False)
        reloj.programar(3, IntType.SIGNAL, pid=1, senal="KILL")
        self.assertEqual(reloj.ejecutar(), "TERMINADO")
        self.assertEqual(p.fin, 3)

    def test_stop_en_bloqueado_y_cont_despues_de_que_la_es_termino(self):
        p = PCB(1, 0, 4, eventos_es=[(1, 3)])       # se bloquea en t=1, E/S lista en t=4
        reloj = construir([p], echo=False)
        reloj.programar(2, IntType.SIGNAL, pid=1, senal="STOP")
        reloj.programar(6, IntType.SIGNAL, pid=1, senal="CONT")
        self.assertEqual(reloj.ejecutar(), "TERMINADO")
        fin_es = eventos(reloj, "ES_COMPLETADA_SUSPENDIDO")
        self.assertEqual([e.tick for e in fin_es], [4])
        self.assertEqual(p.fin, 9)                  # 3 ticks más desde t=6

    def test_cont_antes_de_que_termine_la_es_vuelve_a_bloqueado(self):
        p = PCB(1, 0, 4, eventos_es=[(1, 3)])
        reloj = construir([p], echo=False)
        reloj.programar(2, IntType.SIGNAL, pid=1, senal="STOP")
        reloj.programar(3, IntType.SIGNAL, pid=1, senal="CONT")
        self.assertEqual(reloj.ejecutar(), "TERMINADO")
        self.assertEqual(p.fin, 7)                  # E/S lista en t=4, luego 3 ticks

    def test_division_entre_cero_programada(self):
        p = PCB(1, 0, 10)
        reloj = construir([p], echo=False)
        reloj.programar(2, IntType.DIV_ZERO, pid=1)
        reloj.ejecutar()
        self.assertEqual(p.fin, 2)

    def test_proceso_suspendido_para_siempre_deja_la_simulacion_estancada(self):
        p = PCB(1, 0, 5)
        reloj = construir([p], echo=False)
        reloj.programar(2, IntType.SIGNAL, pid=1, senal="STOP")
        self.assertEqual(reloj.ejecutar(), "ESTANCADO")
        self.assertIs(p.estado, Estado.SUSPENDIDO)


class TestRegistro(unittest.TestCase):
    def test_cada_tick_deja_una_foto_en_el_log(self):
        reloj, _ = corre([PCB(1, 0, 3), PCB(2, 1, 2)])
        fotos = eventos(reloj, "TICK")
        self.assertEqual(len(fotos), reloj.tick)
        self.assertEqual([f.pid for f in fotos][:5], [1, 1, 1, 2, 2])

    def test_el_limite_de_ticks_corta_la_simulacion(self):
        reloj = construir([PCB(1, 0, 100)], echo=False)
        self.assertEqual(reloj.ejecutar(max_ticks=10), "LIMITE")


if __name__ == "__main__":
    unittest.main()
