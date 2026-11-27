# Arquitectura del simulador de SO

> Decisiones acordadas por el grupo (noviembre 2026). Los valores de este documento quedan fijos; cualquier cambio posterior se hace por Pull Request.

## 1. Objetivo y requisitos del profesor

Emular un sistema operativo en dos niveles, **gestión de procesos** y **gestión de memoria**, aplicando los algoritmos vistos en clase y mostrando cada paso **en tiempo real** (no solo el resultado final). Conceptos que deben verse: estados, scheduler, dispatcher, interrupciones, PCB, cambios de contexto, frames.

Requisitos que condicionan el diseño:

- Algoritmos de planificación: **FCFS, SJF y Round Robin**.
- Memoria con **paginación**: lista de frames con registro inicial, registro final, proceso (o `SO` si no hay proceso) y estado de ese proceso.
- Línea de tiempo con todos los procesos, sus estados y cómo cada interrupción encaja en el tiempo.
- Mostrar cada PCB y el total de cambios de contexto; mostrar métricas.
- Cada interrupción se muestra con su **tipo** (división entre cero, E/S, etc.).
- Todo configurable y explicable: el grupo debe dominar qué cambia en cada combinación de configuración.
- Entrega con documento de **cómo correr el programa** y **manual de uso**.
- Opcional: varios procesadores.

## 2. Estructura del proyecto

```
src/
  kernel/       interrupts.py, transaction_log.py, clock.py (reloj), handlers.py (manejadores),
                sistema.py (estado compartido), simulacion.py (construir), contratos.py (firmas),
                stubs.py (módulos provisionales hasta que existan los reales)
  processes/    pcb.py, dispatcher.py, schedulers/ (fcfs, sjf, rr)
  memory/       paginación, mapa de frames, reemplazo (fifo, lru)
  metrics/      cálculo de métricas y línea de tiempo desde los eventos
  ui/           interfaz en vivo
  main.py       punto de entrada
  demo_reloj.py demo del núcleo de punta a punta por consola
docs/           arquitectura, manual de uso, cómo ejecutar, matriz de pruebas
tests/          pruebas
```

## 3. Flujo general

1. El **reloj** avanza un `tick` a la vez.
2. Los módulos (CPU simulada, E/S, memoria, escenario) **levantan interrupciones** con `raise_int(tick, tipo, **payload)`.
3. El `InterruptController` las guarda en una cola con prioridad y las atiende con `dispatch_all(tick)`, llamando al **manejador** de cada tipo.
4. Cada manejador ejecuta el algoritmo correspondiente y **registra cada paso en el log estructurado**.
5. La **UI y las métricas se suscriben al log** y se actualizan en vivo con cada evento.

Manejadores: `handler(tick, **payload)`. Registro: `controller.register(IntType.TIMER, handler)`.

### 3.1 El reloj genera los eventos

El **reloj** (`kernel/clock.py`) es el dueño del tiempo y levanta las interrupciones del sistema: `PROCESS_ARRIVAL`, `IO_REQUEST`, `IO_COMPLETE` (incluye la carga de páginas), `PROCESS_END` y `TIMER`. El scheduler solo decide quién usa la CPU. `PAGE_FAULT` la levanta la memoria dentro de `acceder()`; `SIGNAL` y `DIV_ZERO` vienen del escenario (`reloj.programar(tick, tipo, **payload)`).

**Modelo de tiempo.** `avanzar()` procesa el instante `t` y deja la CPU trabajando durante [t, t+1). Los efectos de ese trabajo (fin de ráfaga, pedido de E/S, fin de quantum, fallo de página) quedan con tiempo `t+1` y se atienden al inicio del siguiente avance. Por eso un proceso que llega en 0 con ráfaga 3 tiene `fin = 3`.

**Orden dentro de un avance:**

1. Se levantan las llegadas del instante (`PROCESS_ARRIVAL`).
2. Se levantan las interrupciones programadas por el escenario (señales, `DIV_ZERO`).
3. Cuenta regresiva de las E/S y cargas de página en curso; al llegar a 0 se levanta `IO_COMPLETE`.
4. `dispatch_all(t)` atiende todo lo pendiente por prioridad.
5. Si la CPU está libre: `scheduler.siguiente()` y `dispatcher.despachar(...)`.
6. Se registra el evento `TICK` y se suma 1 a `espera` de cada proceso LISTO.
7. La CPU ejecuta un tick: consulta la memoria (`acceder`); si hay fallo, el tick se pierde; si no, baja `rafaga_restante` y levanta `PROCESS_END`, `IO_REQUEST` o `TIMER` según corresponda (en ese orden de preferencia).

**Duración de una E/S.** Si una E/S de `d` ticks se atiende en el instante `t0`, `IO_COMPLETE` se atiende en `t0 + d`. Lo mismo vale para la carga de una página (`d` = costo de carga).

**Referencias de página.** Regla provisional: en cada tick de CPU el proceso usa la página `consumido % paginas` (recorre sus páginas en ciclo). Está aislada en `Sistema.pagina_de()` para reemplazarla cuando los escenarios definan una secuencia de referencias.

`ejecutar()` devuelve `TERMINADO` cuando todos los procesos terminaron, `ESTANCADO` cuando nada puede volver a cambiar (por ejemplo, solo quedan procesos SUSPENDIDOS) y `LIMITE` al llegar al máximo de ticks.

## 4. Interrupciones

Número menor = mayor prioridad (prioridades acordadas por el grupo). Si llega una interrupción sin manejador registrado, queda en el log como `INT_SIN_MANEJADOR`.

| Tipo | Nombre mostrado | Origen | Efecto principal |
|------|-----------------|--------|------------------|
| `DIV_ZERO` (1) | División entre cero | Escenario (error del proceso en ejecución) | El proceso pasa a TERMINADO |
| `PAGE_FAULT` (2) | Fallo de página | Memoria | El proceso pasa a BLOQUEADO mientras se carga la página |
| `IO_COMPLETE` (3) | Fin de E/S | Reloj (termina la espera de E/S o de la carga de página) | El proceso pasa de BLOQUEADO a LISTO (si está SUSPENDIDO, sigue suspendido; ver 5.2) |
| `IO_REQUEST` (4) | Solicitud de E/S | Reloj (el proceso llegó al tick de CPU de su `eventos_es`) | El proceso pasa a BLOQUEADO |
| `PROCESS_END` (5) | Fin de proceso | Reloj (la ráfaga restante llegó a 0) | El proceso pasa a TERMINADO y se libera su memoria |
| `TIMER` (6) | Fin de quantum | Reloj | Round Robin expulsa al proceso (EJECUCION a LISTO) |
| `PROCESS_ARRIVAL` (7) | Llegada de proceso | Reloj (llega el tick de llegada del escenario) | NUEVO a LISTO y se reevalúa el scheduler |
| `SIGNAL` (8) | Señal | Usuario / escenario (`reloj.programar`) | `KILL`, `STOP`, `CONT` |

## 5. Procesos

### 5.1 PCB

| Campo | Descripción |
|-------|-------------|
| `pid` | Identificador único |
| `estado` | Ver 5.2 |
| `prioridad` | Entero (menor = más importante) |
| `llegada` | Tick de llegada |
| `rafaga_cpu` / `rafaga_restante` | CPU total y pendiente |
| `eventos_es` | Lista de (tick de CPU en que pide E/S, duración) |
| `paginas` | Cantidad de páginas que usa |
| `tabla_paginas` | Página a frame (o ausente) |
| `primera_ejecucion` | Tick en que corrió por primera vez (tiempo de respuesta) |
| `fin` | Tick en que terminó |
| `espera` | Tiempo acumulado en LISTO |
| `espera_es` | `True` mientras el proceso aguarda una E/S o la carga de una página; permite decidir, al recibir `CONT`, si vuelve a BLOQUEADO o a LISTO |

### 5.2 Estados y transiciones

| Transición | Causa |
|------------|-------|
| NUEVO a LISTO | `PROCESS_ARRIVAL` |
| LISTO a EJECUCION | Dispatcher (elegido por el scheduler) |
| EJECUCION a LISTO | `TIMER` (RR) o expropiación |
| EJECUCION a BLOQUEADO | `IO_REQUEST` o `PAGE_FAULT` |
| BLOQUEADO a LISTO | `IO_COMPLETE` |
| EJECUCION a TERMINADO | `PROCESS_END` o `DIV_ZERO` |
| LISTO, EJECUCION o BLOQUEADO a SUSPENDIDO | `SIGNAL STOP` |
| SUSPENDIDO a LISTO | `SIGNAL CONT` (la E/S ya terminó o no había E/S pendiente) |
| SUSPENDIDO a BLOQUEADO | `SIGNAL CONT` (la E/S aún está pendiente) |
| LISTO, EJECUCION, BLOQUEADO o SUSPENDIDO a TERMINADO | `SIGNAL KILL` |

El estado SUSPENDIDO queda incluido (acordado) para las señales `STOP` / `CONT`. Reglas de las señales, como en un sistema operativo real:

- **`KILL`** puede llegar en cualquier estado que no sea NUEVO ni TERMINADO. Al matar un proceso se libera su memoria y se descarta cualquier `IO_COMPLETE` o `PROCESS_END` que tuviera pendiente.
- **`STOP`** sobre un proceso BLOQUEADO lo pasa a SUSPENDIDO, pero su E/S sigue pendiente (`espera_es = True`).
- Si el `IO_COMPLETE` llega estando el proceso SUSPENDIDO, **no lo reanuda**: solo marca la E/S como terminada (evento `ES_COMPLETADA_SUSPENDIDO`) y el proceso sigue suspendido hasta recibir `CONT`.
- Una transición que no esté en esta tabla lanza `TransicionInvalida` y no modifica el PCB ni el log.

### 5.3 Scheduler y dispatcher (roles separados)

- **Scheduler**: *decide* qué proceso sigue y solo administra la cola de LISTOS. Interfaz común: `agregar(pcb)`, `siguiente()` (saca y devuelve el próximo, o `None`), `quitar(pid)` (lo usan `KILL` y `STOP`) y el atributo `quantum` (`None` = sin quantum; un entero = Round Robin, y el reloj levanta `TIMER` al consumirlo).
- **Dispatcher**: *ejecuta* el cambio con `despachar(tick, saliente, entrante)`. Guarda el contexto del proceso saliente, carga el del entrante (LISTO a EJECUCION), **incrementa el contador de cambios de contexto** y registra el evento `CAMBIO_CONTEXTO`.

Las firmas completas y las reglas de cada módulo están en [contratos.md](contratos.md) (y en `src/kernel/contratos.py`).

Algoritmos: **FCFS**, **SJF** (no expropiativo; SRTF opcional si sobra tiempo) y **Round Robin** (quantum configurable).

## 6. Memoria (paginación)

Parámetros configurables (valores por defecto acordados; todos se pueden cambiar desde la configuración):

- `N` = 16 frames y tamaño de página/frame `T` = 4.
- `K` = 2 frames reservados para el SO (siempre ocupados por `SO`).
- Algoritmo de reemplazo: FIFO y LRU.
- Costo de carga de página = 2 ticks: el proceso queda BLOQUEADO y la carga termina con `IO_COMPLETE`.

El frame `i` ocupa las direcciones `[i*T, (i+1)*T - 1]`. El **mapa de frames** se muestra siempre así:

| Frame | Inicio | Fin | Proceso | Página | Estado del proceso |
|-------|--------|-----|---------|--------|--------------------|
| 0 | 0 | T-1 | SO | - | - |
| 4 | 4T | 5T-1 | P2 | 3 | EJECUCION |
| 5 | 5T | 6T-1 | SO (libre) | - | - |

API del gestor de memoria:

```python
acceder(tick, pid, pagina)   # True si la página está cargada; si no, asigna frame (reemplazando si hace falta), levanta PAGE_FAULT y devuelve False
liberar(tick, pid)           # libera los frames del proceso (se llama al terminar)
mapa_frames()                # lista de filas como la tabla anterior
```

La memoria se crea con `Memoria(log, ic, procesos)` (`procesos` es el diccionario `pid -> PCB`). La memoria **no cambia el estado de los procesos ni cuenta el tiempo de carga**: ante un `PAGE_FAULT` el manejador del núcleo pasa el proceso a BLOQUEADO y el reloj levanta `IO_COMPLETE` a los `costo de carga` ticks.

## 7. Log estructurado

Cada paso es un `Evento` con: `n`, `tick`, `componente`, `mensaje`, `evento` (tipo), `pid`, `antes`, `despues` y `datos`. La línea de texto se genera a partir del evento: `[#007 t=012] SCHED  P3 pasa de EJECUCION a LISTO`.

Tipos de evento (lista inicial; se puede ampliar por Pull Request si hace falta): `INT_ENCOLADA`, `INT_ATENDIDA`, `INT_SIN_MANEJADOR`, `INT_IGNORADA`, `INT_DESCARTADA`, `CAMBIO_ESTADO`, `ES_COMPLETADA_SUSPENDIDO`, `CAMBIO_CONTEXTO`, `TICK`, `FRAME_ASIGNADO`, `FRAME_LIBERADO`, `REEMPLAZO_PAGINA`.

`TICK` es una foto que deja el reloj en cada tick (`pid` = proceso en CPU, o `None`; `datos`: `listos`, `bloqueados`, `suspendidos`) y es la base de la línea de tiempo. `INT_IGNORADA` se registra cuando llega una interrupción que ya no aplica (por ejemplo un `TIMER` de un proceso que ya no está en la CPU); `INT_DESCARTADA`, cuando `KILL` retira interrupciones pendientes de un proceso.

Nadie usa `print` directamente: todo pasa por `TransactionLog.log`. La UI y las métricas usan `log.subscribe(callback)` para recibir los eventos en vivo.

## 8. Interfaz en vivo

Vistas obligatorias, actualizadas en tiempo real:

1. **Mapa de frames** (tabla de la sección 6).
2. **Línea de tiempo** con todos los procesos, su estado en cada tick y las interrupciones marcadas con su tipo.
3. **Tabla de PCB** de todos los procesos.
4. **Métricas** y contador de cambios de contexto.
5. **Log** paso a paso.

Controles: elegir algoritmo, quantum, `N`, `T`, reemplazo y escenario; iniciar, pausar, paso a paso y velocidad. Tecnología: **Tkinter** (acordado).

## 9. Métricas

Por proceso: tiempo de espera, de retorno y de respuesta. Globales: promedios, uso de CPU, rendimiento (procesos por unidad de tiempo), cambios de contexto, fallos de página.

## 10. Configuración y escenarios

Parámetros: algoritmo de planificación, quantum, `N`, `T`, `K`, reemplazo, costo de carga de página y número de CPUs (1, acordado por ahora; la CPU debe ser un objeto para poder sumar más sin reescribir). Escenario: lista de procesos (`pid`, llegada, ráfaga, prioridad, páginas, eventos de E/S, instrucción de error opcional) y señales programadas. Formato: **JSON** (acordado).

## 11. Matriz de pruebas

Mantener `docs/combinaciones.md`: para cada combinación (algoritmo x quantum x memoria x reemplazo x escenario) anotar qué cambia en tiempos, estados, fallos de página y cambios de contexto. Cada integrante debe poder explicarla.

## 12. Entregables

- `README.md` con cómo instalar y ejecutar paso a paso.
- Manual de uso (documento adjunto).
- Programa que corra con una sola instrucción documentada.

## 13. Convenciones de trabajo

- Una rama por tarea: `feature/N-descripcion`, `fix/...`, `docs/...`.
- Commits con prefijo `feat:`, `fix:`, `docs:`, `chore:`.
- Pull Request pequeño con revisión de otro integrante y `Closes #N` en la descripción.
- Antes de empezar: `git checkout main` y `git pull origin main`.

## 14. Decisiones tomadas

- [x] Prioridades de las interrupciones: las de la sección 4
- [x] SJF no expropiativo (SRTF opcional si sobra tiempo)
- [x] `N` = 16, `T` = 4, `K` = 2 y costo de carga de página = 2 ticks
- [x] Reemplazo de páginas: FIFO y LRU
- [x] Estado SUSPENDIDO para STOP/CONT
- [x] Formato de escenarios: JSON
- [x] Tecnología de la UI: Tkinter
- [x] Varios procesadores: no por ahora (opcional, la CPU queda como objeto)
- [x] El reloj genera todos los eventos del sistema (llegadas, E/S, fin de proceso, `TIMER`); el scheduler solo decide quién usa la CPU
- [x] Firmas de scheduler, dispatcher y memoria en [contratos.md](contratos.md)