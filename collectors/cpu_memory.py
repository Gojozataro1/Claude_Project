import os
import psutil


class CpuMemoryCollector:
    def collect(self) -> dict:
        cpu_percent = psutil.cpu_percent(interval=1)
        cpu_per_core = psutil.cpu_percent(interval=None, percpu=True)
        freq = psutil.cpu_freq()
        load_avg = list(os.getloadavg())

        mem = psutil.virtual_memory()
        swap = psutil.swap_memory()

        top_processes = self._top_processes()

        return {
            "cpu_percent": cpu_percent,
            "cpu_per_core": cpu_per_core,
            "cpu_freq_mhz": round(freq.current, 1) if freq else None,
            "cpu_count_logical": psutil.cpu_count(logical=True),
            "cpu_count_physical": psutil.cpu_count(logical=False),
            "load_avg_1_5_15": load_avg,
            "memory_total_gb": round(mem.total / 1e9, 2),
            "memory_used_gb": round(mem.used / 1e9, 2),
            "memory_available_gb": round(mem.available / 1e9, 2),
            "memory_percent": mem.percent,
            "swap_total_gb": round(swap.total / 1e9, 2),
            "swap_used_gb": round(swap.used / 1e9, 2),
            "swap_percent": swap.percent,
            "top_processes": top_processes,
            "thresholds": {
                "cpu": self._color(cpu_percent, warn=60, crit=85),
                "memory": self._color(mem.percent, warn=70, crit=85),
                "swap": self._color(swap.percent, warn=40, crit=70),
            },
        }

    def _top_processes(self) -> list[dict]:
        procs = []
        for p in psutil.process_iter(["pid", "name", "cpu_percent", "memory_percent", "status"]):
            try:
                info = p.info
                procs.append({
                    "pid": info["pid"],
                    "name": info["name"],
                    "cpu_percent": round(info["cpu_percent"] or 0, 1),
                    "memory_percent": round(info["memory_percent"] or 0, 1),
                    "status": info["status"],
                })
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
        procs.sort(key=lambda x: x["cpu_percent"], reverse=True)
        return procs[:10]

    def _color(self, value: float, warn: float, crit: float) -> str:
        if value >= crit:
            return "red"
        if value >= warn:
            return "yellow"
        return "green"
