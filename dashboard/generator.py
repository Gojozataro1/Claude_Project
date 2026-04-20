from __future__ import annotations

from pathlib import Path
from typing import Optional

from jinja2 import Environment, FileSystemLoader

TEMPLATES_DIR = Path(__file__).parent / "templates"


class DashboardGenerator:
    def __init__(self, output_dir: str = "docs"):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(exist_ok=True)
        self.env = Environment(loader=FileSystemLoader(str(TEMPLATES_DIR)))

    def render(self, scan_data: dict, ai_analysis: dict, post_check: Optional[dict] = None,
               mode: str = "all", layout: Optional[dict] = None) -> str:
        layout = layout or {}
        cm = scan_data.get("cpu_memory", {})
        ds = scan_data.get("disk_storage", {})
        st = scan_data.get("startup_apps", {})
        sec = scan_data.get("security", {})

        root_partition = next(
            (p for p in ds.get("partitions", []) if p["mountpoint"] == "/"),
            ds.get("partitions", [{}])[0] if ds.get("partitions") else {}
        )

        ctx = {
            # Meta
            "mode": mode,
            "hostname": scan_data.get("hostname", "unknown"),
            "macos_version": scan_data.get("macos_version", "unknown"),
            "scan_timestamp": scan_data.get("scan_timestamp", ""),

            # Health
            "health_score": ai_analysis.get("health_score", 50),
            "ai_summary": ai_analysis.get("summary", ""),
            "suggestions": ai_analysis.get("suggestions", []),
            "hide_suggestions": layout.get("hide_suggestions", False),

            # CPU
            "cpu_percent": cm.get("cpu_percent", 0),
            "cpu_count_physical": cm.get("cpu_count_physical", 0),
            "load_avg_1": (cm.get("load_avg_1_5_15") or [0])[0],
            "cpu_color": cm.get("thresholds", {}).get("cpu", "green"),
            "top_processes": cm.get("top_processes", [])[:8],

            # Memory
            "memory_percent": cm.get("memory_percent", 0),
            "memory_used_gb": cm.get("memory_used_gb", 0),
            "memory_total_gb": cm.get("memory_total_gb", 0),
            "memory_color": cm.get("thresholds", {}).get("memory", "green"),

            # Swap
            "swap_percent": cm.get("swap_percent", 0),
            "swap_used_gb": cm.get("swap_used_gb", 0),
            "swap_total_gb": cm.get("swap_total_gb", 0),
            "swap_color": cm.get("thresholds", {}).get("swap", "green"),

            # Disk
            "root_disk_percent": root_partition.get("percent", 0),
            "root_disk_used_gb": root_partition.get("used_gb", 0),
            "root_disk_total_gb": root_partition.get("total_gb", 0),
            "disk_color": ds.get("thresholds", {}).get("root_disk", "green"),
            "cache_size_gb": ds.get("cache_size_gb", 0),
            "cache_color": ds.get("thresholds", {}).get("cache", "green"),
            "trash_size_mb": ds.get("trash_size_mb", 0),
            "trash_color": ds.get("thresholds", {}).get("trash", "green"),
            "downloads_size_gb": ds.get("downloads_size_gb", 0),
            "old_downloads_count": len(ds.get("old_downloads", [])),
            "large_files_count": len(ds.get("large_files", [])),

            # Security
            "show_security": layout.get("show_security", True),
            "sip_enabled": sec.get("sip_enabled"),
            "filevault_enabled": sec.get("filevault_enabled"),
            "sip_color": sec.get("thresholds", {}).get("sip", "green"),
            "fv_color": sec.get("thresholds", {}).get("filevault", "green"),
            "world_readable_count": len(sec.get("world_readable_sensitive", [])),
            "world_readable_color": sec.get("thresholds", {}).get("world_readable", "green"),
            "open_ports": sec.get("open_ports", []),
            "open_ports_count": len(sec.get("open_ports", [])),
            "ports_color": sec.get("thresholds", {}).get("open_ports", "green"),

            # Startup
            "show_startup": layout.get("show_startup", True),
            "launch_agent_count": st.get("launch_agent_count", 0),
            "launch_agents_color": st.get("thresholds", {}).get("launch_agents", "green"),
            "background_count": st.get("total_background_count", 0),
            "background_color": st.get("thresholds", {}).get("background_count", "green"),
            "high_cpu_count": len(st.get("high_cpu_background", [])),
            "high_cpu_color": st.get("thresholds", {}).get("high_cpu_count", "green"),

            # Post check
            "post_check": post_check,

            # AI metadata
            "ai_model": ai_analysis.get("model_used", ""),
            "tokens_input": ai_analysis.get("tokens_used", {}).get("input", 0),
            "tokens_output": ai_analysis.get("tokens_used", {}).get("output", 0),
            "tokens_cache_read": ai_analysis.get("tokens_used", {}).get("cache_read", 0),

            # Chart data
            "chart_cpu": self._chart_cpu(cm),
            "chart_mem": self._chart_mem(cm),
            "chart_disk": self._chart_disk(ds),
        }

        template = self.env.get_template("index.html.j2")
        return template.render(**ctx)

    def write(self, html: str, filename: str = "index.html"):
        out_path = self.output_dir / filename
        out_path.write_text(html, encoding="utf-8")
        return str(out_path)

    def _chart_cpu(self, cm: dict) -> dict:
        cores = cm.get("cpu_per_core", [])
        return {
            "labels": [f"Core {i+1}" for i in range(len(cores))],
            "values": cores,
        }

    def _chart_mem(self, cm: dict) -> dict:
        used = cm.get("memory_used_gb", 0)
        avail = cm.get("memory_available_gb", 0)
        swap = cm.get("swap_used_gb", 0)
        return {
            "labels": ["Used", "Available", "Swap Used"],
            "values": [used, avail, swap],
        }

    def _chart_disk(self, ds: dict) -> dict:
        partitions = ds.get("partitions", [])[:5]
        return {
            "labels": [p["mountpoint"] for p in partitions],
            "used": [p["used_gb"] for p in partitions],
            "free": [p["free_gb"] for p in partitions],
            "pct": [p["percent"] for p in partitions],
        }
