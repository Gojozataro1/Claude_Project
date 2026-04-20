from __future__ import annotations

import os
import socket
import stat
import subprocess
from pathlib import Path

import psutil

SENSITIVE_PATTERNS = ["*.pem", "*.key", "*.p12", "*.pfx", "*.crt", ".env", "id_rsa", "id_ed25519", "id_dsa", "*.jks"]
SAFE_SSH_MODES = {0o600, 0o400}


class SecurityCollector:
    def __init__(self):
        self.home = Path.home()

    def collect(self) -> dict:
        world_readable = self._world_readable_sensitive()
        open_ports = self._open_ports()
        sip = self._sip_status()
        filevault = self._filevault_status()
        public_files = self._public_dir()
        ssh_keys = self._ssh_key_permissions()
        env_files = self._exposed_env_files()

        critical_count = sum([
            1 if not sip else 0,
            1 if not filevault else 0,
            len([f for f in world_readable if f["severity"] == "Critical"]),
        ])

        return {
            "world_readable_sensitive": world_readable,
            "open_ports": open_ports,
            "sip_enabled": sip,
            "filevault_enabled": filevault,
            "public_dir_exposure": public_files,
            "ssh_key_permissions": ssh_keys,
            "env_files_exposed": env_files,
            "critical_count": critical_count,
            "thresholds": {
                "sip": "green" if sip else "red",
                "filevault": "green" if filevault else "red",
                "world_readable": self._color(len(world_readable), warn=1, crit=3),
                "open_ports": self._color(len(open_ports), warn=5, crit=10),
            },
        }

    def _world_readable_sensitive(self) -> list[dict]:
        result = []
        for pattern in SENSITIVE_PATTERNS:
            name = Path(pattern).name if not pattern.startswith("*") else None
            for candidate in self._find_sensitive(pattern):
                try:
                    file_stat = candidate.stat()
                    mode = file_stat.st_mode
                    world_readable = bool(mode & stat.S_IROTH)
                    if world_readable:
                        result.append({
                            "path": str(candidate),
                            "permissions_octal": oct(mode & 0o777),
                            "size_bytes": file_stat.st_size,
                            "severity": "Critical",
                            "reason": "World-readable sensitive file",
                        })
                except (PermissionError, OSError):
                    continue
        return result

    def _find_sensitive(self, pattern: str) -> list[Path]:
        results = []
        search_dirs = [self.home, self.home / ".ssh", self.home / "Documents", self.home / "Desktop"]
        for d in search_dirs:
            if d.exists():
                try:
                    if pattern.startswith("*"):
                        results.extend(d.rglob(pattern))
                    else:
                        target = d / pattern
                        if target.exists():
                            results.append(target)
                except (PermissionError, OSError):
                    pass
        return results

    def _open_ports(self) -> list[dict]:
        result = []
        seen = set()
        try:
            connections = psutil.net_connections(kind="inet")
        except (psutil.AccessDenied, PermissionError):
            return []
        for conn in connections:
            if conn.status == "LISTEN" and conn.laddr.port not in seen:
                seen.add(conn.laddr.port)
                proc_name = "unknown"
                try:
                    if conn.pid:
                        proc_name = psutil.Process(conn.pid).name()
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    pass
                result.append({
                    "port": conn.laddr.port,
                    "address": conn.laddr.ip,
                    "pid": conn.pid,
                    "process_name": proc_name,
                })
        result.sort(key=lambda x: x["port"])
        return result

    def _sip_status(self) -> bool | None:
        try:
            out = subprocess.run(["csrutil", "status"], capture_output=True, text=True, timeout=5)
            return "enabled" in out.stdout.lower()
        except Exception:
            return None

    def _filevault_status(self) -> bool | None:
        try:
            out = subprocess.run(["fdesetup", "status"], capture_output=True, text=True, timeout=5)
            return "on" in out.stdout.lower()
        except Exception:
            return None

    def _public_dir(self) -> list[dict]:
        public = self.home / "Public"
        result = []
        if not public.exists():
            return result
        try:
            for entry in public.rglob("*"):
                if entry.is_file():
                    try:
                        s = entry.stat()
                        result.append({
                            "path": str(entry),
                            "size_bytes": s.st_size,
                            "permissions_octal": oct(s.st_mode & 0o777),
                        })
                    except (PermissionError, OSError):
                        continue
        except (PermissionError, OSError):
            pass
        return result[:20]

    def _ssh_key_permissions(self) -> list[dict]:
        ssh_dir = self.home / ".ssh"
        result = []
        if not ssh_dir.exists():
            return result
        try:
            for entry in ssh_dir.iterdir():
                if entry.is_file():
                    try:
                        mode = entry.stat().st_mode & 0o777
                        is_safe = mode in SAFE_SSH_MODES
                        result.append({
                            "path": str(entry),
                            "permissions_octal": oct(mode),
                            "is_safe": is_safe,
                            "severity": "green" if is_safe else "Critical",
                        })
                    except (PermissionError, OSError):
                        continue
        except (PermissionError, OSError):
            pass
        return result

    def _exposed_env_files(self) -> list[dict]:
        result = []
        try:
            for env_file in self.home.rglob(".env"):
                try:
                    s = env_file.stat()
                    world_readable = bool(s.st_mode & stat.S_IROTH)
                    if world_readable:
                        result.append({
                            "path": str(env_file),
                            "permissions_octal": oct(s.st_mode & 0o777),
                            "severity": "Critical",
                        })
                except (PermissionError, OSError):
                    continue
        except (PermissionError, OSError):
            pass
        return result

    def _color(self, value: float, warn: float, crit: float) -> str:
        if value >= crit:
            return "red"
        if value >= warn:
            return "yellow"
        return "green"
