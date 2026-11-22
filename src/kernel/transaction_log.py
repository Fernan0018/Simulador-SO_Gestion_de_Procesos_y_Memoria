class TransactionLog:
    """Registra cada paso del sistema, de forma transaccional."""
    def __init__(self):
        self.entries = []

    def log(self, tick, component, message):
        line = f"[#{len(self.entries) + 1:03d} t={tick:03d}] {component:<10} {message}"
        self.entries.append(line)
        print(line)