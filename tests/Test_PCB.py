import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from kernel.transaction_log import TransactionLog
from processes.PCB import PCB, Estado, TransicionInvalida, TRANSICIONES


def nuevo_pcb(**kw):
    datos = dict(pid=1, llegada=0, rafaga_cpu=5)
    datos.update(kw)
    return PCB(**datos)


def pcb_en(estado, log):
    """Lleva un PCB nuevo hasta el estado pedido por un camino válido."""
    p = nuevo_pcb()
    caminos = {
        Estado.NUEVO: [],
        Estado.LISTO: [Estado.LISTO],
        Estado.EJECUCION: [Estado.LISTO, Estado.EJECUCION],
        Estado.BLOQUEADO: [Estado.LISTO, Estado.EJECUCION, Estado.BLOQUEADO],
        Estado.SUSPENDIDO: [Estado.LISTO, Estado.SUSPENDIDO],
        Estado.TERMINADO: [Estado.LISTO, Estado.EJECUCION, Estado.TERMINADO],
    }
    for t, e in enumerate(caminos[estado]):
        p.cambiar_estado(t, e, log)
    return p


class TestPCB(unittest.TestCase):
    def setUp(self):
        self.log = TransactionLog(echo=False)

    def test_valores_iniciales(self):
        p = nuevo_pcb(rafaga_cpu=7)
        self.assertEqual(p.estado, Estado.NUEVO)
        self.assertEqual(p.rafaga_restante, 7)
        self.assertEqual(p.espera, 0)
        self.assertFalse(p.espera_es)
        self.assertIsNone(p.primera_ejecucion)
        self.assertIsNone(p.fin)

    def test_transicion_valida_actualiza_estado(self):
        p = nuevo_pcb()
        p.cambiar_estado(1, Estado.LISTO, self.log)
        self.assertEqual(p.estado, Estado.LISTO)

    def test_transicion_invalida_lanza_error_y_no_cambia(self):
        p = nuevo_pcb()
        with self.assertRaises(TransicionInvalida):
            p.cambiar_estado(1, Estado.EJECUCION, self.log)   # NUEVO -> EJECUCION
        self.assertEqual(p.estado, Estado.NUEVO)
        self.assertEqual(len(self.log.entries), 0)             # no se registra nada

    def test_registra_cambio_estado_en_el_log(self):
        p = nuevo_pcb(pid=3)
        p.cambiar_estado(2, Estado.LISTO, self.log, causa="PROCESS_ARRIVAL")
        self.assertEqual(len(self.log.entries), 1)
        e = self.log.entries[0]
        self.assertEqual(e.evento, "CAMBIO_ESTADO")
        self.assertEqual(e.pid, 3)
        self.assertEqual(e.tick, 2)
        self.assertEqual(e.antes, "NUEVO")
        self.assertEqual(e.despues, "LISTO")

    def test_primera_ejecucion_solo_se_fija_una_vez(self):
        p = nuevo_pcb()
        p.cambiar_estado(1, Estado.LISTO, self.log)
        p.cambiar_estado(2, Estado.EJECUCION, self.log)
        p.cambiar_estado(4, Estado.LISTO, self.log)
        p.cambiar_estado(6, Estado.EJECUCION, self.log)
        self.assertEqual(p.primera_ejecucion, 2)

    def test_fin_se_fija_al_terminar(self):
        p = nuevo_pcb()
        p.cambiar_estado(0, Estado.LISTO, self.log)
        p.cambiar_estado(1, Estado.EJECUCION, self.log)
        p.cambiar_estado(6, Estado.TERMINADO, self.log)
        self.assertEqual(p.fin, 6)

    def test_terminado_es_estado_final(self):
        p = pcb_en(Estado.TERMINADO, self.log)
        for destino in Estado:
            with self.assertRaises(TransicionInvalida):
                p.cambiar_estado(9, destino, self.log)

    def test_bloqueo_y_desbloqueo(self):
        p = nuevo_pcb()
        p.cambiar_estado(0, Estado.LISTO, self.log)
        p.cambiar_estado(1, Estado.EJECUCION, self.log)
        p.cambiar_estado(2, Estado.BLOQUEADO, self.log, causa="IO_REQUEST")
        self.assertTrue(p.espera_es)
        p.cambiar_estado(4, Estado.LISTO, self.log, causa="IO_COMPLETE")
        self.assertFalse(p.espera_es)
        self.assertEqual(p.estado, Estado.LISTO)

    def test_bloqueado_no_pasa_directo_a_ejecucion(self):
        p = pcb_en(Estado.BLOQUEADO, self.log)
        with self.assertRaises(TransicionInvalida):
            p.cambiar_estado(9, Estado.EJECUCION, self.log)

    def test_la_tabla_cubre_todos_los_estados(self):
        self.assertEqual(set(TRANSICIONES), set(Estado))


class TestKill(unittest.TestCase):
    """KILL puede llegar en cualquier estado que no sea NUEVO ni TERMINADO."""

    def setUp(self):
        self.log = TransactionLog(echo=False)

    def test_kill_desde_cada_estado_vivo(self):
        for origen in (Estado.LISTO, Estado.EJECUCION, Estado.BLOQUEADO, Estado.SUSPENDIDO):
            with self.subTest(origen=origen):
                p = pcb_en(origen, self.log)
                p.cambiar_estado(20, Estado.TERMINADO, self.log, causa="KILL")
                self.assertEqual(p.estado, Estado.TERMINADO)
                self.assertEqual(p.fin, 20)
                self.assertFalse(p.espera_es)

    def test_kill_sobre_un_proceso_ya_terminado_es_invalido(self):
        p = pcb_en(Estado.TERMINADO, self.log)
        with self.assertRaises(TransicionInvalida):
            p.cambiar_estado(20, Estado.TERMINADO, self.log, causa="KILL")


class TestStopCont(unittest.TestCase):
    def setUp(self):
        self.log = TransactionLog(echo=False)

    def test_stop_y_cont_sobre_un_proceso_listo(self):
        p = pcb_en(Estado.LISTO, self.log)
        p.cambiar_estado(5, Estado.SUSPENDIDO, self.log, causa="STOP")
        p.reanudar(8, self.log)
        self.assertEqual(p.estado, Estado.LISTO)

    def test_stop_sobre_bloqueado_conserva_la_espera_de_es(self):
        p = pcb_en(Estado.BLOQUEADO, self.log)
        p.cambiar_estado(5, Estado.SUSPENDIDO, self.log, causa="STOP")
        self.assertEqual(p.estado, Estado.SUSPENDIDO)
        self.assertTrue(p.espera_es)

    def test_cont_con_es_pendiente_vuelve_a_bloqueado(self):
        p = pcb_en(Estado.BLOQUEADO, self.log)
        p.cambiar_estado(5, Estado.SUSPENDIDO, self.log, causa="STOP")
        p.reanudar(6, self.log)
        self.assertEqual(p.estado, Estado.BLOQUEADO)
        self.assertTrue(p.espera_es)

    def test_es_completa_estando_suspendido_no_levanta_el_stop(self):
        p = pcb_en(Estado.BLOQUEADO, self.log)
        p.cambiar_estado(5, Estado.SUSPENDIDO, self.log, causa="STOP")
        e = p.es_completada(7, self.log)
        self.assertEqual(p.estado, Estado.SUSPENDIDO)
        self.assertFalse(p.espera_es)
        self.assertEqual(e.evento, "ES_COMPLETADA_SUSPENDIDO")

    def test_cont_tras_es_completada_pasa_a_listo(self):
        p = pcb_en(Estado.BLOQUEADO, self.log)
        p.cambiar_estado(5, Estado.SUSPENDIDO, self.log, causa="STOP")
        p.es_completada(7, self.log)
        p.reanudar(9, self.log)
        self.assertEqual(p.estado, Estado.LISTO)

    def test_es_completada_sobre_bloqueado_pasa_a_listo(self):
        p = pcb_en(Estado.BLOQUEADO, self.log)
        e = p.es_completada(7, self.log)
        self.assertEqual(p.estado, Estado.LISTO)
        self.assertEqual(e.evento, "CAMBIO_ESTADO")
        self.assertEqual(e.antes, "BLOQUEADO")
        self.assertEqual(e.despues, "LISTO")

    def test_es_completada_en_otro_estado_no_hace_nada(self):
        p = pcb_en(Estado.LISTO, self.log)
        self.assertIsNone(p.es_completada(7, self.log))
        self.assertEqual(p.estado, Estado.LISTO)

    def test_cont_sobre_proceso_no_suspendido_es_invalido(self):
        p = pcb_en(Estado.LISTO, self.log)
        with self.assertRaises(TransicionInvalida):
            p.reanudar(7, self.log)


if __name__ == "__main__":
    unittest.main()