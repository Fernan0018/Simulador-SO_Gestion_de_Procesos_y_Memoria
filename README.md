# Simulador de SO: Gestión de Procesos y Memoria

Simulador de un sistema operativo que emula la **gestión de procesos** y la **gestión de memoria** de forma **transaccional**: cada paso y cada cambio de estado del sistema queda registrado y se muestra en tiempo real. Los algoritmos de gestión se ejecutan como respuesta a **interrupciones**, igual que en un sistema operativo real.

> **Estado del proyecto:** en desarrollo. Este README se irá actualizando con cada avance.

## Qué incluye (objetivo del proyecto)

**Gestión de procesos**
- Planificación con **FCFS**, **SJF** y **Round Robin**.
- Scheduler y dispatcher separados, con conteo de **cambios de contexto**.
- **PCB** de cada proceso y sus estados: NUEVO, LISTO, EJECUCION, BLOQUEADO y TERMINADO.

**Gestión de memoria**
- **Paginación** con mapa de frames (registro inicial, registro final, proceso o SO, y estado del proceso).
- Reemplazo de páginas (FIFO y LRU).

**Interrupciones**
- Cada interrupción se muestra con su tipo: división entre cero, fallo de página, fin de E/S, solicitud de E/S, fin de proceso, timer, llegada de proceso y señal.

**Visualización en vivo**
- Mapa de frames, línea de tiempo, tabla de PCB, métricas y log paso a paso.

## Requisitos

- Python 3.10 o superior
- Git (solo para clonar el repositorio)

## Instalación

1. Clonar el repositorio:
   ```
   git clone https://github.com/Fernan0018/Simulador-SO_Gestion_de_Procesos_y_Memoria.git
   cd Simulador-SO_Gestion_de_Procesos_y_Memoria
   ```
2. Crear y activar el entorno virtual:
   - Windows (PowerShell):
     ```
     python -m venv .venv
     .venv\Scripts\Activate.ps1
     ```
   - Linux / macOS:
     ```
     python3 -m venv .venv
     source .venv/bin/activate
     ```
3. Instalar las dependencias:
   ```
   pip install -r requirements.txt
   ```

## Cómo ejecutar

Versión actual (demostración del núcleo de interrupciones y del log):

```
python src/main.py
```

Muestra cómo se encolan y se atienden las interrupciones según su prioridad, registrando cada paso. *(Esta sección se actualizará con los pasos de la interfaz en vivo cuando esté lista.)*

## Estructura del proyecto

```
src/
  kernel/       interrupciones y log transaccional
  processes/    PCB, dispatcher y planificadores
  memory/       paginación, mapa de frames y reemplazo de páginas
  metrics/      métricas y línea de tiempo
  ui/           interfaz en vivo
  main.py       punto de entrada
docs/           arquitectura y manuales
tests/          pruebas
```

## Documentación

- [Arquitectura](docs/arquitectura.md): diseño del simulador, interrupciones, PCB, memoria y log.
- Manual de uso y matriz de combinaciones: *(pendientes)*

## Integrantes

| Integrante | Rol / módulo |
|------------|--------------|
| *Fernando* | *(por definir)* |
| *Percy* | *(por definir)* |
| *Rodrigo* | *(por definir)* |
| *Angel* | *(por definir)* |
| *Paolo* | *(por definir)* |

## Cómo trabajamos

- Las tareas están en los **Issues** del repositorio.
- Cada tarea se hace en su propia rama (`feature/N-descripcion`) creada desde `main`.
- Todo cambio entra a `main` mediante **Pull Request** con revisión de otro integrante.
- Commits con prefijo: `feat:`, `fix:`, `docs:`, `chore:`.

## Curso

*SI421U Arquitectura de Computador y Sistemas Operativos, Profesor Carlos Nelson Ramos Montes, Ciclo 2026-II*