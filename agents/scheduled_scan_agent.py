#!/usr/bin/env python3
"""Scheduled Scan Agent — runs AI Ops scans at a configurable interval."""
from __future__ import annotations

import argparse
import json
import logging
import os
import platform
import socket
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

DEFAULT_INTERVAL_MINUTES = 1440  # 24 hours
SCANS_DIR = Path(__file__).parent.parent / "data" / "scans"


class ScheduledScanAgent:
    """Runs AI Ops scans on a repeating schedule and archives each result."""

    def __init__(
        self,
        interval_minutes: int = DEFAULT_INTERVAL_MINUTES,
        mode: str = "all",
        no_ai: bool = False,
        output_dir: str = "docs",
        data_dir: str = "data",
    ):
        self.interval_seconds = interval_minutes * 60
        self.mode = mode
        self.no_ai = no_ai
        self.output_dir = output_dir
        self.data_dir = data_dir
        self._stop_event = threading.Event()
        SCANS_DIR.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def run_once(self) -> dict:
        """Execute a single scan and return the combined result dict."""
        from router.skill_router import SkillRouter
        from analyzer.claude_analyzer import ClaudeAnalyzer
        from dashboard.generator import DashboardGenerator

        model = os.getenv("AI_OPS_MODEL", "claude-sonnet-4-6")
        router = SkillRouter(self.mode)
        logger.info("ScheduledScanAgent: starting scan [%s]", router.describe())

        scan_data = self._collect(router)

        if self.no_ai:
            ai_analysis = {
                "summary": "AI analysis skipped (no_ai=True).",
                "health_score": 50,
                "suggestions": [],
                "model_used": "none",
                "tokens_used": {},
            }
        else:
            api_key = os.getenv("ANTHROPIC_API_KEY", "")
            if not api_key:
                logger.warning("ANTHROPIC_API_KEY not set — skipping AI analysis.")
                ai_analysis = {
                    "summary": "AI analysis skipped (no API key).",
                    "health_score": 50,
                    "suggestions": [],
                    "model_used": "none",
                    "tokens_used": {},
                }
            else:
                analyzer = ClaudeAnalyzer(api_key=api_key, model=model)
                ai_analysis = analyzer.analyze(scan_data, mode_focus=router.get_analyzer_focus())
                logger.info(
                    "Health score: %d/100, %d suggestions",
                    ai_analysis.get("health_score", 0),
                    len(ai_analysis.get("suggestions", [])),
                )

        result = {**scan_data, "ai_analysis": ai_analysis}

        # Write latest_scan.json (main data file)
        Path(self.data_dir).mkdir(exist_ok=True)
        latest = Path(self.data_dir) / "latest_scan.json"
        latest.write_text(json.dumps(result, indent=2, default=str))

        # Archive timestamped copy
        ts = datetime.now(timezone.utc).strftime("%Y-%m-%d_%H%M%S")
        archive_path = SCANS_DIR / f"scan_{ts}.json"
        archive_path.write_text(json.dumps(result, indent=2, default=str))
        logger.info("Scan archived: %s", archive_path)

        # Regenerate dashboard
        generator = DashboardGenerator(output_dir=self.output_dir)
        html = generator.render(scan_data, ai_analysis, mode=self.mode, layout=router.get_dashboard_layout())
        out_path = generator.write(html)
        logger.info("Dashboard updated: %s", out_path)

        return result

    def run_forever(self) -> None:
        """Block and run scans at the configured interval until stopped."""
        logger.info(
            "ScheduledScanAgent starting — interval: %d min, mode: %s",
            self.interval_seconds // 60,
            self.mode,
        )
        while not self._stop_event.is_set():
            try:
                result = self.run_once()
                score = result.get("ai_analysis", {}).get("health_score", "N/A")
                logger.info("Scan complete — health score: %s/100", score)
            except Exception as exc:
                logger.error("Scan failed: %s", exc)

            self._stop_event.wait(timeout=self.interval_seconds)

        logger.info("ScheduledScanAgent stopped.")

    def start_background(self) -> threading.Thread:
        """Start the agent loop in a background daemon thread."""
        t = threading.Thread(target=self.run_forever, name="ScheduledScanAgent", daemon=True)
        t.start()
        logger.info("ScheduledScanAgent running in background thread.")
        return t

    def stop(self) -> None:
        self._stop_event.set()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _collect(self, router) -> dict:
        from collectors.cpu_memory import CpuMemoryCollector
        from collectors.disk_storage import DiskStorageCollector
        from collectors.startup_apps import StartupAppsCollector
        from collectors.security import SecurityCollector

        active = router.get_active_collectors()
        scan_data: dict = {
            "scan_timestamp": datetime.now(timezone.utc).isoformat(),
            "hostname": socket.gethostname(),
            "macos_version": platform.mac_ver()[0] or platform.version(),
            "cpu_memory": {},
            "disk_storage": {},
            "startup_apps": {},
            "security": {},
        }
        collector_map = {
            "cpu_memory": (CpuMemoryCollector, "cpu_memory"),
            "disk_storage": (DiskStorageCollector, "disk_storage"),
            "startup_apps": (StartupAppsCollector, "startup_apps"),
            "security": (SecurityCollector, "security"),
        }
        for name, (cls, key) in collector_map.items():
            if name in active:
                try:
                    scan_data[key] = cls().collect()
                except Exception as exc:
                    logger.error("Collector %s failed: %s", name, exc)
        return scan_data


# ------------------------------------------------------------------
# CLI entry point
# ------------------------------------------------------------------

def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Scheduled Scan Agent — run AI Ops scans on a schedule")
    parser.add_argument("--interval", type=int, default=DEFAULT_INTERVAL_MINUTES,
                        help=f"Interval between scans in minutes (default: {DEFAULT_INTERVAL_MINUTES})")
    parser.add_argument("--mode", choices=["all", "dev", "ui", "vulnerability"], default="all")
    parser.add_argument("--no-ai", action="store_true", help="Skip Claude analysis")
    parser.add_argument("--once", action="store_true", help="Run a single scan then exit")
    parser.add_argument("--verbose", action="store_true")
    return parser.parse_args()


if __name__ == "__main__":
    args = _parse_args()
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )

    agent = ScheduledScanAgent(
        interval_minutes=args.interval,
        mode=args.mode,
        no_ai=args.no_ai,
    )

    if args.once:
        result = agent.run_once()
        score = result.get("ai_analysis", {}).get("health_score", "N/A")
        criticals = sum(
            1 for s in result.get("ai_analysis", {}).get("suggestions", [])
            if s.get("priority") == "Critical"
        )
        print(f"\n{'='*50}")
        print(f"  Health Score : {score}/100")
        print(f"  Critical     : {criticals}")
        print(f"  Suggestions  : {len(result.get('ai_analysis', {}).get('suggestions', []))}")
        print(f"{'='*50}\n")
        sys.exit(0)
    else:
        try:
            agent.run_forever()
        except KeyboardInterrupt:
            print("\nStopped by user.")
