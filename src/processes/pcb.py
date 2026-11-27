"""PCB (Process Control Block) y estados de un proceso.

Sigue la sección 5 de docs/arquitectura.md.
"""
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Tuple


class Estado(Enum):
    NUEVO = "NUEVO"
    LISTO = "LISTO"
    EJECUCION = "EJECUCION"
    BLOQUEADO = "BLOQUEADO"
    SUSPENDIDO = "SUSPENDIDO"   # SIGNAL STOP / CONT
    TERMINADO = "TERMINADO"


# Transiciones permitidas (sección 5.2 de arquitectura.md).
# Cada clave es el estado de origen y su valor, los destinos válidos.
TRANSICIONES = {
    Estado.NUEVO: {Estado.LISTO},                       # PROCESS_ARRIVAL
    Estado.LISTO: {Estado.EJECUCION,                    # dispatcher
                   Estado.SUSPENDIDO,                   # STOP
                   Estado.TERMINADO},                   # KILL
    Estado.EJECUCION: {Estado.LISTO,                    # TIMER o expropiación
                       Estado.BLOQUEADO,                # IO_REQUEST o PAGE_FAULT
                       Estado.SUSPENDIDO,               # STOP
                       Estado.TERMINADO},               # PROCESS_END, DIV_ZERO o KILL
    Estado.BLOQUEADO: {Estado.LISTO,                    # IO_COMPLETE
                       Estado.SUSPENDIDO,               # STOP (la E/S sigue pendiente)
                       Estado.TERMINADO},               # KILL
    Estado.SUSPENDIDO: {Estado.LISTO,                   # CONT (con la E/S ya completada)
                        Estado.BLOQUEADO,               # CONT (con la E/S aún pendiente)
                        Estado.TERMINADO},              # KILL
    Estado.TERMINADO: set(),                            # estado final
}


class TransicionInvalida(Exception):
    """Se intentó una transición de estado que la tabla no permite."""


@dataclass
class PCB:
    pid: int
    llegada: int
    rafaga_cpu: int
    prioridad: int = 0                      # menor = más importante
    paginas: int = 1                        # cantidad de páginas que usa
    eventos_es: List[Tuple[int, int]] = field(default_factory=list)
    # (tick de CPU en que pide E/S, duración)
    estado: Estado = Estado.NUEVO
    rafaga_restante: Optional[int] = None
    tabla_paginas: Dict[int, Optional[int]] = field(default_factory=dict)
    # página -> frame (None o ausente = no cargada)
    primera_ejecucion: Optional[int] = None
    fin: Optional[int] = None
    espera: int = 0                         # tiempo acumulado en LISTO
    espera_es: bool = False
    # True mientras el proceso aguarda una E/S o la carga de una página.
    # Permite saber, al recibir CONT, si debe volver a BLOQUEADO o a LISTO.

    def __post_init__(self):
        if self.rafaga_restante is None:
            self.rafaga_restante = self.rafaga_cpu

    def puede_pasar_a(self, nuevo: Estado) -> bool:
        return nuevo in TRANSICIONES[self.estado]

    def cambiar_estado(self, tick: int, nuevo: Estado, log, causa: str = ""):
        """Valida la transición, actualiza el PCB y registra CAMBIO_ESTADO."""
        if not self.puede_pasar_a(nuevo):
            raise TransicionInvalida(
                f"P{self.pid}: {self.estado.value} -> {nuevo.value} no está permitida")

        antes = self.estado
        self.estado = nuevo

        if nuevo is Estado.EJECUCION and self.primera_ejecucion is None:
            self.primera_ejecucion = tick
        if nuevo is Estado.TERMINADO:
            self.fin = tick
            self.espera_es = False
        if nuevo is Estado.BLOQUEADO and antes is Estado.EJECUCION:
            self.espera_es = True           # empieza una E/S o carga de página
        if nuevo is Estado.LISTO and antes is Estado.BLOQUEADO:
            self.espera_es = False          # la E/S terminó

        mensaje = f"P{self.pid} pasa de {antes.value} a {nuevo.value}"
        if causa:
            mensaje += f" ({causa})"
        return log.log(tick, "SCHED", mensaje, evento="CAMBIO_ESTADO",
                       pid=self.pid, antes=antes.value, despues=nuevo.value,
                       causa=causa)

    # --- Operaciones de alto nivel para los manejadores de SIGNAL / IO_COMPLETE ---

    def es_completada(self, tick: int, log):
        """Maneja IO_COMPLETE (fin de E/S o de carga de página).

        - BLOQUEADO: pasa a LISTO.
        - SUSPENDIDO con E/S pendiente: sigue suspendido, pero la E/S queda
          marcada como terminada (como en un SO real: el STOP no se levanta solo).
        - Cualquier otro estado: no hay nada que completar.
        """
        if self.estado is Estado.BLOQUEADO:
            return self.cambiar_estado(tick, Estado.LISTO, log, causa="IO_COMPLETE")
        if self.estado is Estado.SUSPENDIDO and self.espera_es:
            self.espera_es = False
            return log.log(tick, "SCHED",
                           f"P{self.pid} termina su E/S estando SUSPENDIDO (sigue suspendido)",
                           evento="ES_COMPLETADA_SUSPENDIDO", pid=self.pid,
                           antes=self.estado.value, despues=self.estado.value)
        return None

    def reanudar(self, tick: int, log):
        """Maneja SIGNAL CONT: SUSPENDIDO vuelve a BLOQUEADO si su E/S sigue
        pendiente, o a LISTO si ya terminó."""
        destino = Estado.BLOQUEADO if self.espera_es else Estado.LISTO
        return self.cambiar_estado(tick, destino, log, causa="CONT")