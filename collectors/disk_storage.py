import os
import time
from pathlib import Path

import psutil


class DiskStorageCollector:
    def __init__(self, large_file_threshold_mb: int = 500, old_file_days: int = 90):
        self.large_file_threshold_bytes = large_file_threshold_mb * 1024 * 1024
        self.old_file_cutoff = time.time() - (old_file_days * 86400)
        self.home = Path.home()

    def collect(self) -> dict:
        partitions = self._partitions()
        cache_size, cache_top = self._cache_info()
        trash_size = self._dir_size(self.home / ".Trash")
        downloads_size, old_downloads = self._downloads_info()
        large_files = self._find_large_files()

        primary = next((p for p in partitions if p["mountpoint"] == "/"), partitions[0] if partitions else {})

        return {
            "partitions": partitions,
            "large_files": large_files,
            "cache_size_gb": round(cache_size / 1e9, 2),
            "cache_top_dirs": cache_top,
            "trash_size_mb": round(trash_size / 1e6, 1),
            "downloads_size_gb": round(downloads_size / 1e9, 2),
            "old_downloads": old_downloads,
            "thresholds": {
                "root_disk": self._color(primary.get("percent", 0), warn=75, crit=90),
                "cache": self._color(cache_size / 1e9, warn=5, crit=10),
                "trash": self._color(trash_size / 1e6, warn=1000, crit=5000),
            },
        }

    def _partitions(self) -> list[dict]:
        result = []
        for part in psutil.disk_partitions(all=False):
            try:
                usage = psutil.disk_usage(part.mountpoint)
                result.append({
                    "mountpoint": part.mountpoint,
                    "device": part.device,
                    "fstype": part.fstype,
                    "total_gb": round(usage.total / 1e9, 2),
                    "used_gb": round(usage.used / 1e9, 2),
                    "free_gb": round(usage.free / 1e9, 2),
                    "percent": usage.percent,
                })
            except (PermissionError, OSError):
                continue
        return result

    def _cache_info(self) -> tuple[int, list[dict]]:
        cache_dir = self.home / "Library" / "Caches"
        if not cache_dir.exists():
            return 0, []
        total = 0
        subdirs = []
        try:
            for entry in cache_dir.iterdir():
                if entry.is_dir():
                    size = self._dir_size(entry)
                    total += size
                    subdirs.append({"name": entry.name, "size_mb": round(size / 1e6, 1)})
        except PermissionError:
            pass
        subdirs.sort(key=lambda x: x["size_mb"], reverse=True)
        return total, subdirs[:5]

    def _downloads_info(self) -> tuple[int, list[dict]]:
        dl_dir = self.home / "Downloads"
        if not dl_dir.exists():
            return 0, []
        total = 0
        old = []
        try:
            for entry in dl_dir.iterdir():
                try:
                    stat = entry.stat()
                    total += stat.st_size
                    if stat.st_atime < self.old_file_cutoff:
                        old.append({
                            "path": str(entry),
                            "size_mb": round(stat.st_size / 1e6, 1),
                            "last_accessed_days_ago": int((time.time() - stat.st_atime) / 86400),
                        })
                except (PermissionError, OSError):
                    continue
        except PermissionError:
            pass
        old.sort(key=lambda x: x["size_mb"], reverse=True)
        return total, old[:10]

    def _find_large_files(self) -> list[dict]:
        result = []
        skip_dirs = {".Trash", "Library"}
        try:
            for entry in self.home.iterdir():
                if entry.name in skip_dirs or entry.name.startswith("."):
                    continue
                if entry.is_file():
                    self._check_file(entry, result)
                elif entry.is_dir():
                    self._walk_for_large(entry, result, depth=0, max_depth=4)
        except PermissionError:
            pass
        result.sort(key=lambda x: x["size_mb"], reverse=True)
        return result[:20]

    def _walk_for_large(self, directory: Path, result: list, depth: int, max_depth: int):
        if depth > max_depth:
            return
        try:
            for entry in directory.iterdir():
                if entry.is_file():
                    self._check_file(entry, result)
                elif entry.is_dir() and not entry.is_symlink():
                    self._walk_for_large(entry, result, depth + 1, max_depth)
        except (PermissionError, OSError):
            pass

    def _check_file(self, path: Path, result: list):
        try:
            stat = path.stat()
            if stat.st_size >= self.large_file_threshold_bytes:
                result.append({
                    "path": str(path),
                    "size_mb": round(stat.st_size / 1e6, 1),
                    "last_accessed_days_ago": int((time.time() - stat.st_atime) / 86400),
                })
        except (PermissionError, OSError):
            pass

    def _dir_size(self, path: Path) -> int:
        total = 0
        try:
            for entry in path.rglob("*"):
                try:
                    if entry.is_file():
                        total += entry.stat().st_size
                except (PermissionError, OSError):
                    continue
        except (PermissionError, OSError):
            pass
        return total

    def _color(self, value: float, warn: float, crit: float) -> str:
        if value >= crit:
            return "red"
        if value >= warn:
            return "yellow"
        return "green"
