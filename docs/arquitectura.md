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
  kernel/       interrupts.py, transaction_log.py, reloj, configuración
  processes/    pcb.py, dispatcher.py, schedulers/ (fcfs, sjf, rr)
  memory/       paginación, mapa de frames, reemplazo (fifo, lru)
  metrics/      cálculo de métricas y línea de tiempo desde los eventos
  ui/           interfaz en vivo
  main.py       punto de entrada
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

## 4. Interrupciones

Número menor = mayor prioridad (prioridades acordadas por el grupo). Si llega una interrupción sin manejador registrado, queda en el log como `INT_SIN_MANEJADOR`.

| Tipo | Nombre mostrado | Origen | Efecto principal |
|------|-----------------|--------|------------------|
| `DIV_ZERO` (1) | División entre cero | Proceso en ejecución | El proceso pasa a TERMINADO |
| `PAGE_FAULT` (2) | Fallo de página | Memoria | El proceso pasa a BLOQUEADO mientras se carga la página |
| `IO_COMPLETE` (3) | Fin de E/S | Dispositivo (también carga de página) | El proceso pasa de BLOQUEADO a LISTO |
| `IO_REQUEST` (4) | Solicitud de E/S | Proceso en ejecución | El proceso pasa a BLOQUEADO |
| `PROCESS_END` (5) | Fin de proceso | CPU (ráfaga terminada) | El proceso pasa a TERMINADO y se libera su memoria |
| `TIMER` (6) | Fin de quantum | Reloj | Round Robin expulsa al proceso (EJECUCION a LISTO) |
| `PROCESS_ARRIVAL` (7) | Llegada de proceso | Escenario | NUEVO a LISTO y se reevalúa el scheduler |
| `SIGNAL` (8) | Señal | Usuario / escenario | `KILL`, `STOP`, `CONT` |

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

### 5.2 Estados y transiciones

| Transición | Causa |
|------------|-------|
| NUEVO a LISTO | `PROCESS_ARRIVAL` |
| LISTO a EJECUCION | Dispatcher (elegido por el scheduler) |
| EJECUCION a LISTO | `TIMER` (RR) o expropiación |
| EJECUCION a BLOQUEADO | `IO_REQUEST` o `PAGE_FAULT` |
| BLOQUEADO a LISTO | `IO_COMPLETE` |
| EJECUCION a TERMINADO | `PROCESS_END`, `DIV_ZERO` o `SIGNAL KILL` |
| LISTO o EJECUCION a SUSPENDIDO | `SIGNAL STOP` |
| SUSPENDIDO a LISTO | `SIGNAL CONT` |

El estado SUSPENDIDO queda incluido (acordado) para las señales `STOP` / `CONT`.

### 5.3 Scheduler y dispatcher (roles separados)

- **Scheduler**: *decide* qué proceso sigue. Interfaz común: `agregar(pcb)` y `siguiente()`.
- **Dispatcher**: *ejecuta* el cambio. Guarda el contexto del proceso saliente, carga el del entrante, **incrementa el contador de cambios de contexto** y registra el evento `CAMBIO_CONTEXTO`.

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
acceder(tick, pid, pagina)   # si la página no está cargada, levanta PAGE_FAULT
liberar(tick, pid)           # libera los frames del proceso (se llama al terminar)
mapa_frames()                # lista de filas como la tabla anterior
```

## 7. Log estructurado

Cada paso es un `Evento` con: `n`, `tick`, `componente`, `mensaje`, `evento` (tipo), `pid`, `antes`, `despues` y `datos`. La línea de texto se genera a partir del evento: `[#007 t=012] SCHED  P3 pasa de EJECUCION a LISTO`.

Tipos de evento (lista inicial; se puede ampliar por Pull Request si hace falta): `INT_ENCOLADA`, `INT_ATENDIDA`, `INT_SIN_MANEJADOR`, `CAMBIO_ESTADO`, `CAMBIO_CONTEXTO`, `FRAME_ASIGNADO`, `FRAME_LIBERADO`, `REEMPLAZO_PAGINA`.

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