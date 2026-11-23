# Arquitectura del simulador de SO

> Borrador para acordar con el grupo. Todo lo marcado como **(a acordar)** debe decidirse en la primera reunión y luego quedar fijo aquí.

## 1. Objetivo

Simular un sistema operativo que realiza **gestión de procesos** y **gestión de memoria** de forma **transaccional** (cada paso y cambio de estado queda registrado en el log). Los algoritmos de gestión **no se llaman directamente**: se ejecutan como respuesta a **interrupciones**.

## 2. Estructura del proyecto

```
src/
  kernel/       interrupts.py, transaction_log.py (+ reloj del sistema)
  processes/    PCB, gestor de procesos, planificadores
  memory/       gestor de memoria, tabla de páginas, reemplazo de páginas
  ui/           visualización del log y del estado del sistema
  main.py       punto de entrada y escenarios de prueba
docs/           documentación (este archivo, manuales)
tests/          pruebas
```

## 3. Flujo general

1. El **reloj** avanza un `tick` a la vez.
2. Los módulos (CPU simulada, E/S, memoria, usuario) **levantan interrupciones** con `raise_int(tick, tipo, **payload)`.
3. El `InterruptController` las guarda en una cola con prioridad y las atiende con `dispatch_all(tick)`, llamando al **manejador** registrado para cada tipo.
4. Cada manejador ejecuta el algoritmo correspondiente (planificar, reemplazar página, etc.) y **registra cada paso en el log**.

## 3.1 Convención de manejadores

```python
def handler(tick, **payload):
    ...
```

Registro: `controller.register(IntType.TIMER, handler)`.

## 4. Interrupciones

Número menor = mayor prioridad.

| Tipo | Prioridad | Quién la levanta | Quién la atiende | Payload |
|------|-----------|------------------|------------------|---------|
| `PAGE_FAULT` | 1 | Memoria (acceso a página ausente) | Gestor de memoria | `pid`, `page` |
| `IO_COMPLETE` | 2 | Dispositivo de E/S simulado | Gestor de procesos | `pid` |
| `TIMER` | 3 | Reloj (fin de quantum) | Planificador | — |
| `SIGNAL` | 4 | Usuario / escenario | Gestor de procesos | `pid`, `signal` (`KILL`, `STOP`, `CONT`) |
| `PROCESS_END` | **(a acordar)** | CPU simulada (ráfaga terminada) | Gestor de procesos | `pid` |

> `PROCESS_END` aún no existe en `IntType`; quien lo necesite lo agrega con un PR pequeño.

## 5. Procesos

### 5.1 PCB

| Campo | Descripción |
|-------|-------------|
| `pid` | Identificador único |
| `estado` | Ver 5.2 |
| `prioridad` | Entero (menor = más importante) |
| `tiempo_llegada` | Tick en que llega al sistema |
| `rafaga_cpu` | Tiempo total de CPU requerido |
| `rafaga_restante` | Tiempo de CPU que falta |
| `paginas_necesarias` | Cantidad de páginas que usa |
| `tabla_paginas` | Mapa página → marco (o ausente) |

### 5.2 Estados

`NUEVO → LISTO → EJECUCION → TERMINADO`, con `EJECUCION → BLOQUEADO → LISTO` (E/S) y `EJECUCION → LISTO` (fin de quantum).

Toda transición se registra en el log, por ejemplo: `P3 pasa de EJECUCION a LISTO`.

### 5.3 Planificador (interfaz común)

```python
class Scheduler:
    def agregar(self, pcb): ...
    def siguiente(self): ...   # devuelve el PCB a ejecutar o None
```

Algoritmos a implementar: Round Robin (obligatorio), más uno o dos a elegir **(a acordar)**: SJF, prioridades.

## 6. Memoria

Parámetros **(a acordar)**:

- Número de marcos: `N`
- Tamaño de página: `T`
- Algoritmo de reemplazo: FIFO primero, luego LRU

API que expone el gestor de memoria:

```python
acceder(tick, pid, pagina)   # si la página no está, levanta PAGE_FAULT
liberar(tick, pid)           # libera los marcos del proceso
```

El manejador de `PAGE_FAULT` carga la página, elige víctima si no hay marcos libres y actualiza las tablas de páginas, **registrando cada paso**.

## 7. Formato del log transaccional

```
[#001 t=001] COMPONENTE mensaje
```

Ejemplo: `[#007 t=012] SCHED      P3 pasa de EJECUCION a LISTO`.

Cada decisión o cambio de estado va en su propia línea. Nadie imprime con `print` directamente: todo pasa por `TransactionLog.log`.

## 8. Escenarios de prueba

Archivo con la lista de procesos de entrada (`pid`, llegada, ráfaga, prioridad, páginas) y, opcionalmente, señales programadas por tick. **(a acordar el formato: JSON o Python)**.

## 9. Convenciones de trabajo

- Una rama por tarea: `feature/...`, `fix/...`, `docs/...`.
- Commits con prefijo: `feat:`, `fix:`, `docs:`, `chore:`.
- Pull Request pequeño, con revisión de otro integrante antes del *Squash and merge*.
- Antes de empezar cada sesión: `git checkout main` y `git pull origin main`.

## 10. Decisiones abiertas

- [ ] Prioridad de `PROCESS_END` en `IntType`
- [ ] Algoritmos de planificación adicionales
- [ ] Valores de `N` (marcos) y `T` (tamaño de página)
- [ ] Formato del archivo de escenarios
- [ ] Tecnología de la UI (consola o gráfica)