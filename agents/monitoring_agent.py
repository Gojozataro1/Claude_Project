#!/usr/bin/env python3
"""Monitoring Agent — polls system metrics and alerts when thresholds are breached."""
from __future__ import annotations

import argparse
import json
import logging
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

import psutil

sys.path.insert(0, str(Path(__file__).parent.parent))

logger = logging.getLogger(__name__)

ALERTS_FILE = Path(__file__).parent.parent / "data" / "alerts.jsonl"

DEFAULT_THRESHOLDS = {
    "cpu_percent": 90.0,       # % — sustained CPU usage
    "memory_percent": 85.0,    # %
    "swap_percent": 50.0,      # %
    "disk_percent": 90.0,      # % for any mounted partition
    "load_avg_ratio": 1.0,     # load_avg_1 / cpu_count
}

DEFAULT_POLL_SECONDS = 60


class MonitoringAgent:
    """
    Continuously polls macOS system metrics and emits structured alerts
    to data/alerts.jsonl whenever a configured threshold is crossed.

    Optionally triggers a full AI Ops scan when a breach is detected.
    """

    def __init__(
        self,
        poll_interval_seconds: int = DEFAULT_POLL_SECONDS,
        thresholds: dict | None = None,
        trigger_scan_on_breach: bool = False,
        scan_mode: str = "all",
        no_ai: bool = False,
    ):
        self.poll_interval = poll_interval_seconds
        self.thresholds = {**DEFAULT_THRESHOLDS, **(thresholds or {})}
        self.trigger_scan_on_breach = trigger_scan_on_breach
        self.scan_mode = scan_mode
        self.no_ai = no_ai
        self._stop_event = threading.Event()
        ALERTS_FILE.parent.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def check_once(self) -> list[dict]:
        """Collect current metrics, check thresholds, return any alert dicts."""
        metrics = self._collect_metrics()
        alerts = self._evaluate(metrics)
        if alerts:
            self._write_alerts(alerts)
            for a in alerts:
                logger.warning("ALERT [%s] %s — value: %s (threshold: %s)",
                               a["severity"], a["metric"], a["value"], a["threshold"])
        return alerts

    def run_forever(self) -> None:
        """Block, poll at the configured interval, until stop() is called."""
        logger.info(
            "MonitoringAgent starting — interval: %ds, thresholds: %s",
            self.poll_interval, self.thresholds,
        )
        breach_already_active: set[str] = set()

        while not self._stop_event.is_set():
            try:
                metrics = self._collect_metrics()
                alerts = self._evaluate(metrics)

                new_breaches = {a["metric"] for a in alerts}

                # Log new breaches (avoid spamming on sustained breach)
                for a in alerts:
                    if a["metric"] not in breach_already_active:
                        logger.warning(
                            "NEW BREACH [%s] %s = %s (threshold %s)",
                            a["severity"], a["metric"], a["value"], a["threshold"],
                        )

                if alerts:
                    self._write_alerts(alerts)

                # Trigger a scan only when a new breach first appears
                new_first_breach = new_breaches - breach_already_active
                if new_first_breach and self.trigger_scan_on_breach:
                    logger.info("Triggering scan due to new breach(es): %s", new_first_breach)
                    self._trigger_scan()

                # Track which metrics are currently in breach
                cleared = breach_already_active - new_breaches
                for m in cleared:
                    logger.info("CLEARED: %s is back within threshold", m)
                breach_already_active = new_breaches

                logger.debug("Poll complete — metrics: cpu=%.1f%% mem=%.1f%% disk_max=%.1f%%",
                             metrics["cpu_percent"], metrics["memory_percent"],
                             metrics["max_disk_percent"])

            except Exception as exc:
                logger.error("MonitoringAgent poll error: %s", exc)

            self._stop_event.wait(timeout=self.poll_interval)

        logger.info("MonitoringAgent stopped.")

    def start_background(self) -> threading.Thread:
        t = threading.Thread(target=self.run_forever, name="MonitoringAgent", daemon=True)
        t.start()
        return t

    def stop(self) -> None:
        self._stop_event.set()

    def tail_alerts(self, n: int = 20) -> list[dict]:
        """Return the last N alert records from data/alerts.jsonl."""
        if not ALERTS_FILE.exists():
            return []
        lines = ALERTS_FILE.read_text().strip().splitlines()
        recent = lines[-n:] if len(lines) >= n else lines
        result = []
        for line in reversed(recent):
            try:
                result.append(json.loads(line))
            except json.JSONDecodeError:
                continue
        return result

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _collect_metrics(self) -> dict:
        cpu = psutil.cpu_percent(interval=1)
        mem = psutil.virtual_memory()
        swap = psutil.swap_memory()
        load = psutil.getloadavg()
        cpu_count = psutil.cpu_count() or 1

        max_disk_pct = 0.0
        disk_breaches: list[dict] = []
        for part in psutil.disk_partitions(all=False):
            try:
                usage = psutil.disk_usage(part.mountpoint)
                if usage.percent > max_disk_pct:
                    max_disk_pct = usage.percent
                if usage.percent >= self.thresholds["disk_percent"]:
                    disk_breaches.append({"mountpoint": part.mountpoint, "percent": usage.percent})
            except (PermissionError, OSError):
                continue

        return {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "cpu_percent": cpu,
            "memory_percent": mem.percent,
            "swap_percent": swap.percent,
            "load_avg_1": load[0],
            "load_avg_ratio": load[0] / cpu_count,
            "cpu_count": cpu_count,
            "max_disk_percent": max_disk_pct,
            "disk_breaches": disk_breaches,
        }

    def _evaluate(self, metrics: dict) -> list[dict]:
        alerts: list[dict] = []
        ts = metrics["timestamp"]

        checks = [
            ("cpu_percent",    metrics["cpu_percent"],    "CPU usage critical"),
            ("memory_percent", metrics["memory_percent"], "Memory usage critical"),
            ("swap_percent",   metrics["swap_percent"],   "Swap usage high"),
            ("load_avg_ratio", metrics["load_avg_ratio"], "Load average high"),
        ]
        for key, value, label in checks:
            threshold = self.thresholds[key]
            if value >= threshold:
                alerts.append({
                    "timestamp": ts,
                    "metric": key,
                    "label": label,
                    "value": round(value, 2),
                    "threshold": threshold,
                    "severity": "critical" if value >= threshold * 1.1 else "warning",
                })

        for breach in metrics["disk_breaches"]:
            alerts.append({
                "timestamp": ts,
                "metric": "disk_percent",
                "label": f"Disk usage critical on {breach['mountpoint']}",
                "value": round(breach["percent"], 2),
                "threshold": self.thresholds["disk_percent"],
                "mountpoint": breach["mountpoint"],
                "severity": "critical" if breach["percent"] >= 95 else "warning",
            })

        return alerts

    def _write_alerts(self, alerts: list[dict]) -> None:
        with open(ALERTS_FILE, "a") as f:
            for a in alerts:
                f.write(json.dumps(a) + "\n")

    def _trigger_scan(self) -> None:
        try:
            from agents.scheduled_scan_agent import ScheduledScanAgent
            agent = ScheduledScanAgent(mode=self.scan_mode, no_ai=self.no_ai)
            t = threading.Thread(target=agent.run_once, name="MonitoringTriggeredScan", daemon=True)
            t.start()
        except Exception as exc:
            logger.error("Failed to trigger scan: %s", exc)


# ------------------------------------------------------------------
# CLI entry point
# ------------------------------------------------------------------

def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Monitoring Agent — watch system metrics and alert on threshold breaches")
    parser.add_argument("--interval", type=int, default=DEFAULT_POLL_SECONDS,
                        help=f"Poll interval in seconds (default: {DEFAULT_POLL_SECONDS})")
    parser.add_argument("--cpu-threshold", type=float, default=DEFAULT_THRESHOLDS["cpu_percent"],
                        help="CPU %% alert threshold")
    parser.add_argument("--mem-threshold", type=float, default=DEFAULT_THRESHOLDS["memory_percent"],
                        help="Memory %% alert threshold")
    parser.add_argument("--disk-threshold", type=float, default=DEFAULT_THRESHOLDS["disk_percent"],
                        help="Disk %% alert threshold")
    parser.add_argument("--trigger-scan", action="store_true",
                        help="Trigger a full scan when a new breach is detected")
    parser.add_argument("--scan-mode", choices=["all", "dev", "ui", "vulnerability"], default="all")
    parser.add_argument("--no-ai", action="store_true")
    parser.add_argument("--once", action="store_true", help="Run a single poll then print alerts and exit")
    parser.add_argument("--tail", type=int, metavar="N", help="Print last N alerts from log and exit")
    parser.add_argument("--verbose", action="store_true")
    return parser.parse_args()


if __name__ == "__main__":
    args = _parse_args()
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )

    thresholds = {
        "cpu_percent": args.cpu_threshold,
        "memory_percent": args.mem_threshold,
        "disk_percent": args.disk_threshold,
    }

    agent = MonitoringAgent(
        poll_interval_seconds=args.interval,
        thresholds=thresholds,
        trigger_scan_on_breach=args.trigger_scan,
        scan_mode=args.scan_mode,
        no_ai=args.no_ai,
    )

    if args.tail:
        records = agent.tail_alerts(args.tail)
        if not records:
            print("No alerts recorded yet.")
        for r in records:
            print(f"[{r['timestamp']}] {r['severity'].upper():8s} {r['label']} — {r['value']} (threshold {r['threshold']})")
        sys.exit(0)

    if args.once:
        alerts = agent.check_once()
        if not alerts:
            print("All metrics within thresholds.")
        for a in alerts:
            print(f"  [{a['severity'].upper()}] {a['label']}: {a['value']} (threshold {a['threshold']})")
        sys.exit(0)

    try:
        agent.run_forever()
    except KeyboardInterrupt:
        print("\nStopped by user.")
