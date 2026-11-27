"""Estado compartido que usan el reloj y los manejadores."""
from typing import Dict, List, Optional

from processes.pcb import PCB, Estado


class Sistema:
    def __init__(self, log, ic, scheduler, dispatcher, memoria, procesos,
                 costo_carga: int = 2):
        self.log = log
        self.ic = ic
        self.scheduler = scheduler
        self.dispatcher = dispatcher
        self.memoria = memoria
        self.costo_carga = costo_carga          # ticks que tarda cargar una página
        self.procesos: Dict[int, PCB] = {p.pid: p for p in procesos}

        self.cpu: Optional[PCB] = None          # proceso en EJECUCION
        self.ultimo: Optional[PCB] = None       # último que tuvo la CPU
        self.quantum_restante: Optional[int] = None
        self.esperas: Dict[int, int] = {}       # pid -> ticks que faltan para IO_COMPLETE

    # --- consultas ---------------------------------------------------------

    def procesos_en(self, estado: Estado) -> List[PCB]:
        return [p for p in self.procesos.values() if p.estado is estado]

    @staticmethod
    def consumido(pcb: PCB) -> int:
        """Ticks de CPU que el proceso ya usó."""
        return pcb.rafaga_cpu - pcb.rafaga_restante

    def pagina_de(self, pcb: PCB) -> int:
        """Página que el proceso usa en su próximo tick de CPU.

        Regla provisional: recorre sus páginas en ciclo (0, 1, ..., 0, 1, ...).
        Cuando los escenarios traigan una secuencia de referencias, solo hay
        que cambiar este método.
        """
        return self.consumido(pcb) % max(1, pcb.paginas)

    # --- CPU ---------------------------------------------------------------

    def liberar_cpu(self, pcb: PCB) -> None:
        if self.cpu is pcb:
            self.cpu = None
            self.quantum_restante = None

    def asignar_cpu(self, tick: int) -> None:
        """Si la CPU está libre, el scheduler elige y el dispatcher cambia el contexto."""
        if self.cpu is not None:
            return
        pcb = self.scheduler.siguiente()
        if pcb is None:
            return
        self.dispatcher.despachar(tick, self.ultimo, pcb)
        self.cpu = pcb
        self.ultimo = pcb
        self.quantum_restante = getattr(self.scheduler, "quantum", None)
