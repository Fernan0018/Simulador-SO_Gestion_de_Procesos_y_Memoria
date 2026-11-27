# Contratos entre módulos

Este documento define cómo se conectan el **núcleo** (reloj y manejadores, de Fernando) con el **scheduler y el dispatcher** (Percy) y con la **memoria** (Angel). Si cumples estas firmas, tu módulo funciona con el resto sin tocar el núcleo. Las firmas en código están en `src/kernel/contratos.py`, y `src/kernel/stubs.py` trae versiones básicas de cada módulo como ejemplo y para probar mientras tanto.

## 1. Reglas generales

- Todo se registra con `TransactionLog.log(...)`. Nadie usa `print`.
- El estado de un proceso cambia **solo** con `pcb.cambiar_estado(tick, nuevo, log, causa)`, que valida la transición (ver 5.2 de `arquitectura.md`).
- Cada módulo toca solo lo suyo: el scheduler, la cola de listos; el dispatcher, el paso de LISTO a EJECUCION y el contador de cambios de contexto; la memoria, los frames. Los demás cambios de estado los hace el núcleo.
- Los módulos pueden **leer** estos campos del PCB: `pid`, `estado`, `prioridad`, `llegada`, `rafaga_cpu`, `rafaga_restante`, `paginas` y `tabla_paginas`.
- Cada módulo se prueba en solitario con sus propios tests, y de punta a punta con `construir(...)` (ver sección 5).

## 2. Scheduler (Percy)

Decide qué proceso sigue. Solo administra la cola de LISTOS.

| Miembro | Descripción |
|---------|-------------|
| `quantum` | `None` si el algoritmo no usa quantum (FCFS, SJF). Un entero si es Round Robin: el reloj levanta `TIMER` cuando el proceso consume ese número de ticks seguidos |
| `agregar(pcb)` | Mete un proceso que **ya está en LISTO** en la cola |
| `siguiente()` | **Saca** y devuelve el próximo proceso a ejecutar, o `None` si no hay |
| `quitar(pid)` | Retira un proceso de la cola. Si no está, no hace nada |

Cuándo llama el núcleo a `agregar`: al llegar un proceso (NUEVO a LISTO), al terminar una E/S o una carga de página (BLOQUEADO a LISTO), al expirar el quantum (EJECUCION a LISTO) y con `CONT` cuando el proceso vuelve a LISTO. Llama a `quitar` con `KILL` y `STOP` sobre un proceso LISTO.

Criterios por algoritmo:

- **FCFS**: orden de llegada a la cola.
- **SJF** (no expropiativo): el de menor `rafaga_restante`; ante empate, el que entró antes a la cola.
- **Round Robin**: cola FIFO con `quantum` entero. El reloj reinicia el quantum cada vez que un proceso toma la CPU.

El scheduler **no cambia estados** ni toca la CPU.

## 3. Dispatcher (Percy)

Ejecuta el cambio de contexto que decidió el scheduler.

| Miembro | Descripción |
|---------|-------------|
| `cambios_contexto` | Contador total |
| `despachar(tick, saliente, entrante)` | Pone a `entrante` en la CPU |

`despachar` debe:

1. Contar el cambio de contexto y registrar `CAMBIO_CONTEXTO` (con `pid=entrante.pid` y, en `datos`, `saliente` y `total`).
2. Pasar a `entrante` de LISTO a EJECUCION: `entrante.cambiar_estado(tick, Estado.EJECUCION, log, causa="dispatcher")`.

`saliente` es el último proceso que tuvo la CPU. Puede ser `None` (primer despacho), estar ya TERMINADO, o ser el mismo `entrante` (Round Robin con un solo proceso listo). El stub cuenta el cambio solo si `saliente` existe y es distinto de `entrante`; si el grupo decide otro criterio, se cambia aquí.

El núcleo lo llama cuando la CPU queda libre, después de atender las interrupciones del tick.

## 4. Memoria (Angel)

Paginación con mapa de frames y reemplazo FIFO / LRU. Se crea con `Memoria(log, ic, procesos)`: el log, el controlador de interrupciones (para levantar `PAGE_FAULT`) y el diccionario `pid -> PCB` (los mismos objetos que usa el núcleo, para leer `paginas` y `estado` y mantener `tabla_paginas`).

| Miembro | Descripción |
|---------|-------------|
| `acceder(tick, pid, pagina) -> bool` | Un proceso usa una página |
| `liberar(tick, pid)` | Libera todos los frames del proceso |
| `mapa_frames() -> list[dict]` | Filas del mapa de frames |

**`acceder`**: el reloj lo llama una vez por cada tick de CPU del proceso en ejecución.

- Si la página **está cargada**: actualiza lo que necesite (por ejemplo, el orden de LRU) y devuelve `True`.
- Si **no está**: asigna un frame (uno libre o una víctima según FIFO / LRU), registra `FRAME_ASIGNADO` (y `REEMPLAZO_PAGINA` si desalojó otra), actualiza `tabla_paginas`, levanta la interrupción con exactamente este formato y devuelve `False`:

  ```python
  self.ic.raise_int(tick, IntType.PAGE_FAULT, pid=pid, pagina=pagina)
  ```

- Cuando el proceso vuelve a la CPU después de la carga, su acceso a esa página debe dar `True`.

**Lo que NO hace la memoria**: no cambia el estado del proceso y no cuenta el tiempo de carga. Ante `PAGE_FAULT`, el núcleo pasa el proceso a BLOQUEADO y el reloj levanta `IO_COMPLETE` a los 2 ticks (costo de carga configurable).

**`liberar`**: el núcleo lo llama cuando el proceso termina (`PROCESS_END`), por `DIV_ZERO` o por `KILL`. Registra `FRAME_LIBERADO`. Debe poder llamarse dos veces seguidas sin problema.

**`mapa_frames`**: una fila por frame, con estas claves (siguen la tabla de la sección 6 de `arquitectura.md`):

| Clave | Valor |
|-------|-------|
| `frame` | Número de frame |
| `inicio`, `fin` | `i*T` y `(i+1)*T - 1` |
| `proceso` | `"SO"` (reservado), `"SO (libre)"` o `"P<pid>"` |
| `pagina` | Número de página, o `None` |
| `estado` | `Estado.value` del proceso dueño, o `None` |

**Qué página usa cada tick**: por ahora el núcleo usa la página `consumido % paginas` (recorre las páginas del proceso en ciclo). Cuando los escenarios definan una secuencia de referencias, se cambia solo `Sistema.pagina_de()`. Para probar con la secuencia de 13 referencias de las diapositivas, llama a `acceder` directamente en un test, sin el reloj.

## 5. Cómo conectar y probar tu módulo

```python
from kernel.simulacion import construir
from kernel.transaction_log import TransactionLog
from processes.pcb import PCB

procesos = [PCB(pid=1, llegada=0, rafaga_cpu=5, paginas=2),
            PCB(pid=2, llegada=1, rafaga_cpu=3, paginas=2)]

log = TransactionLog()
reloj = construir(procesos,
                  scheduler=MiScheduler(quantum=3),     # Percy
                  dispatcher=MiDispatcher(log),         # Percy
                  crear_memoria=MiMemoria,              # Angel: MiMemoria(log, ic, procesos)
                  costo_carga=2,
                  log=log)
print(reloj.ejecutar())   # TERMINADO, ESTANCADO o LIMITE
```

- Lo que no pases usa las versiones básicas de `kernel/stubs.py`: puedes probar solo tu parte.
- `python src/demo_reloj.py` corre un escenario completo por consola.
- Para tests de punta a punta, mira `tests/test_clock.py` (usa `construir(..., echo=False)`).

## 6. Eventos de log por módulo

| Módulo | Eventos |
|--------|---------|
| Núcleo | `INT_ENCOLADA`, `INT_ATENDIDA`, `INT_SIN_MANEJADOR`, `INT_IGNORADA`, `INT_DESCARTADA`, `CAMBIO_ESTADO`, `ES_COMPLETADA_SUSPENDIDO`, `TICK` |
| Dispatcher | `CAMBIO_CONTEXTO` |
| Memoria | `FRAME_ASIGNADO`, `FRAME_LIBERADO`, `REEMPLAZO_PAGINA` |

Si necesitas cambiar una firma de este documento, se hace por Pull Request y se avisa al grupo, porque el núcleo y los demás módulos dependen de ella.