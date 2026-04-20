import plistlib
from pathlib import Path

import psutil


class StartupAppsCollector:
    def __init__(self):
        self.home = Path.home()

    def collect(self) -> dict:
        launch_agents = self._launch_agents()
        login_items = self._login_items()
        background_procs, high_cpu = self._background_processes()

        return {
            "launch_agents": launch_agents,
            "launch_agent_count": len(launch_agents),
            "login_items": login_items,
            "background_processes": background_procs,
            "total_background_count": len(background_procs),
            "high_cpu_background": high_cpu,
            "thresholds": {
                "launch_agents": self._color(len(launch_agents), warn=15, crit=30),
                "background_count": self._color(len(background_procs), warn=50, crit=100),
                "high_cpu_count": self._color(len(high_cpu), warn=1, crit=3),
            },
        }

    def _launch_agents(self) -> list[dict]:
        agents_dir = self.home / "Library" / "LaunchAgents"
        result = []
        if not agents_dir.exists():
            return result
        for plist_file in agents_dir.glob("*.plist"):
            try:
                with open(plist_file, "rb") as f:
                    data = plistlib.load(f)
                result.append({
                    "label": data.get("Label", plist_file.stem),
                    "program": data.get("Program") or (data.get("ProgramArguments") or [""])[0],
                    "run_at_load": bool(data.get("RunAtLoad", False)),
                    "keep_alive": bool(data.get("KeepAlive", False)),
                    "plist_path": str(plist_file),
                })
            except Exception:
                result.append({
                    "label": plist_file.stem,
                    "program": "unknown",
                    "run_at_load": None,
                    "keep_alive": None,
                    "plist_path": str(plist_file),
                    "parse_error": True,
                })
        return result

    def _login_items(self) -> list[dict]:
        plist_path = self.home / "Library" / "Preferences" / "com.apple.loginitems.plist"
        result = []
        if not plist_path.exists():
            return result
        try:
            with open(plist_path, "rb") as f:
                data = plistlib.load(f)
            session_items = data.get("SessionItems", {}).get("CustomListItems", [])
            for item in session_items:
                result.append({
                    "name": item.get("Name", "Unknown"),
                    "enabled": not item.get("Disabled", False),
                })
        except Exception:
            pass
        return result

    def _background_processes(self) -> tuple[list[dict], list[dict]]:
        background = []
        high_cpu = []
        for p in psutil.process_iter(["pid", "name", "cpu_percent", "memory_percent", "status", "terminal"]):
            try:
                info = p.info
                if info.get("terminal") is None:
                    proc = {
                        "pid": info["pid"],
                        "name": info["name"],
                        "cpu_percent": round(info["cpu_percent"] or 0, 1),
                        "memory_percent": round(info["memory_percent"] or 0, 1),
                        "status": info["status"],
                    }
                    background.append(proc)
                    if proc["cpu_percent"] > 5.0:
                        high_cpu.append(proc)
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
        background.sort(key=lambda x: x["cpu_percent"], reverse=True)
        high_cpu.sort(key=lambda x: x["cpu_percent"], reverse=True)
        return background[:30], high_cpu

    def _color(self, value: float, warn: float, crit: float) -> str:
        if value >= crit:
            return "red"
        if value >= warn:
            return "yellow"
        return "green"
