"""Contratos entre el núcleo (reloj y manejadores) y los módulos de los demás.

Quien programe el scheduler, el dispatcher o la memoria solo tiene que cumplir
estas firmas: el núcleo no depende de nada más. Mientras no existan las
versiones reales, `kernel/stubs.py` trae versiones básicas para poder correr
la simulación de punta a punta.

Todos los módulos escriben en el log con `TransactionLog.log` (nunca `print`).
"""
from typing import List, Optional, Protocol

from processes.pcb import PCB


class Scheduler(Protocol):
    """Decide qué proceso sigue. Solo administra la cola de LISTOS."""

    quantum: Optional[int]
    # None = sin quantum (FCFS, SJF). Un entero = Round Robin: el reloj levanta
    # TIMER cuando el proceso consume ese número de ticks seguidos en la CPU.

    def agregar(self, pcb: PCB) -> None:
        """Mete un proceso (ya en estado LISTO) en la cola de listos."""

    def siguiente(self) -> Optional[PCB]:
        """Saca y devuelve el próximo proceso a ejecutar, o None si no hay."""

    def quitar(self, pid: int) -> None:
        """Retira un proceso de la cola (lo usan KILL y STOP). Si no está, no hace nada."""


class Dispatcher(Protocol):
    """Ejecuta el cambio de contexto que decidió el scheduler."""

    cambios_contexto: int

    def despachar(self, tick: int, saliente: Optional[PCB], entrante: PCB) -> None:
        """Pone a `entrante` en la CPU: lo pasa de LISTO a EJECUCION con
        `entrante.cambiar_estado(...)`, cuenta el cambio de contexto y registra
        el evento CAMBIO_CONTEXTO. `saliente` es el último proceso que tuvo la
        CPU (puede ser None, o ya estar TERMINADO)."""


class Memoria(Protocol):
    """Paginación.

    Se crea con `Memoria(log, ic, procesos)`: el log, el controlador de
    interrupciones y el diccionario `pid -> PCB` (los mismos objetos que usa el
    núcleo). Con `procesos` puede leer `paginas` y `estado` para armar el mapa
    de frames, y mantener `tabla_paginas` de cada PCB.
    """

    def acceder(self, tick: int, pid: int, pagina: int) -> bool:
        """Un proceso usa una página.

        - Si está cargada: actualiza lo que necesite (p. ej. LRU) y devuelve True.
        - Si no: asigna frame (reemplazando si hace falta), levanta
          `PAGE_FAULT` con `pid=` y `pagina=` mediante `ic.raise_int` y devuelve False.
          El reloj se encarga del bloqueo del proceso y de los ticks de carga.
        """

    def liberar(self, tick: int, pid: int) -> None:
        """Libera todos los frames del proceso (al terminar, o por KILL / DIV_ZERO)."""

    def mapa_frames(self) -> List[dict]:
        """Filas del mapa de frames (sección 6 de arquitectura.md)."""
