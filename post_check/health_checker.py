import logging
import socket
import subprocess
from datetime import datetime, timezone
from pathlib import Path

import psutil

logger = logging.getLogger(__name__)

CORE_PROCESSES = ["Finder", "Dock", "SystemUIServer", "WindowServer"]
ESSENTIAL_APPS = [
    "/System/Library/CoreServices/Finder.app",
    "/Applications/Safari.app",
    "/System/Applications/Terminal.app",
    "/Applications/Utilities/Terminal.app",
]
DNS_TEST_HOST = "apple.com"


class PostCleanupHealthChecker:
    def run(self) -> dict:
        checks = {
            "core_processes": self.check_core_processes(),
            "network": self.check_network(),
            "disk_health": self.check_disk_health(),
            "system_services": self.check_system_services(),
            "app_integrity": self.check_app_integrity(),
            "memory_cpu": self.check_memory_cpu(),
        }

        issues = [
            {"check": name, "detail": result["detail"]}
            for name, result in checks.items()
            if result["status"] == "fail"
        ]

        verdict = "ALL_CLEAR" if not issues else "ISSUES_FOUND"
        return {
            "verdict": verdict,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "checks": checks,
            "issues": issues,
            "pass_count": sum(1 for r in checks.values() if r["status"] == "pass"),
            "fail_count": len(issues),
        }

    def check_core_processes(self) -> dict:
        running = {p.name() for p in psutil.process_iter(["name"])}
        missing = [name for name in CORE_PROCESSES if name not in running]
        if missing:
            return {"status": "fail", "detail": f"Core processes not running: {', '.join(missing)}"}
        return {"status": "pass", "detail": f"All core processes running: {', '.join(CORE_PROCESSES)}"}

    def check_network(self) -> dict:
        try:
            old_timeout = socket.getdefaulttimeout()
            socket.setdefaulttimeout(5)
            try:
                socket.getaddrinfo(DNS_TEST_HOST, 80)
            finally:
                socket.setdefaulttimeout(old_timeout)
            return {"status": "pass", "detail": f"DNS resolution working ({DNS_TEST_HOST})"}
        except Exception as e:
            return {"status": "fail", "detail": f"Network/DNS check failed: {e}"}

    def check_disk_health(self) -> dict:
        critical_partitions = []
        for part in psutil.disk_partitions(all=False):
            try:
                usage = psutil.disk_usage(part.mountpoint)
                if usage.percent >= 95:
                    critical_partitions.append(f"{part.mountpoint} ({usage.percent:.1f}% full)")
            except (PermissionError, OSError):
                continue
        if critical_partitions:
            return {"status": "fail", "detail": f"Critical disk usage: {'; '.join(critical_partitions)}"}
        return {"status": "pass", "detail": "All disk partitions within safe limits"}

    def check_system_services(self) -> dict:
        try:
            result = subprocess.run(
                ["launchctl", "list"],
                capture_output=True, text=True, timeout=10
            )
            lines = result.stdout.strip().splitlines()
            essential = ["Finder", "Dock"]
            running_names = {p.name() for p in psutil.process_iter(["name"])}
            missing = [s for s in essential if s not in running_names]
            if missing:
                return {"status": "fail", "detail": f"Essential services not listed: {', '.join(missing)}"}
            return {"status": "pass", "detail": f"System services active ({len(lines)} total listed)"}
        except Exception as e:
            return {"status": "fail", "detail": f"Could not check system services: {e}"}

    def check_app_integrity(self) -> dict:
        finder = Path("/System/Library/CoreServices/Finder.app")
        safari = Path("/Applications/Safari.app")
        terminal = Path("/System/Applications/Utilities/Terminal.app")

        missing = []
        for app_path in [finder, safari, terminal]:
            if not app_path.exists():
                missing.append(app_path.name)

        if missing:
            return {"status": "fail", "detail": f"Apps missing: {', '.join(missing)}"}
        return {"status": "pass", "detail": "Key applications present (Finder, Safari, Terminal)"}

    def check_memory_cpu(self) -> dict:
        cpu = psutil.cpu_percent(interval=1)
        mem = psutil.virtual_memory()
        issues = []
        if cpu > 95:
            issues.append(f"CPU critically high: {cpu}%")
        if mem.percent > 95:
            issues.append(f"Memory critically high: {mem.percent}%")
        if issues:
            return {"status": "fail", "detail": "; ".join(issues)}
        return {"status": "pass", "detail": f"CPU {cpu}%, Memory {mem.percent}% — within normal range"}
