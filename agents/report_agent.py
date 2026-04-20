#!/usr/bin/env python3
"""Report Agent — aggregates scan history and generates an HTML trend report."""
from __future__ import annotations

import argparse
import json
import logging
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

from jinja2 import Environment, FileSystemLoader

sys.path.insert(0, str(Path(__file__).parent.parent))

logger = logging.getLogger(__name__)

SCANS_DIR = Path(__file__).parent.parent / "data" / "scans"
LATEST_SCAN = Path(__file__).parent.parent / "data" / "latest_scan.json"
TEMPLATES_DIR = Path(__file__).parent / "templates"
DEFAULT_OUTPUT_DIR = Path(__file__).parent.parent / "docs"


class ReportAgent:
    """
    Reads archived scan files from data/scans/, computes trends, and renders
    an HTML report to docs/report.html.
    """

    def __init__(self, output_dir: str | Path = DEFAULT_OUTPUT_DIR):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(exist_ok=True)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def load_scan_history(self) -> list[dict]:
        """Return all archived scans sorted oldest→newest, including latest_scan.json."""
        scans: list[dict] = []

        # Archived scans
        if SCANS_DIR.exists():
            for path in sorted(SCANS_DIR.glob("scan_*.json")):
                try:
                    data = json.loads(path.read_text())
                    data["_source_file"] = path.name
                    scans.append(data)
                except Exception as exc:
                    logger.warning("Could not read %s: %s", path.name, exc)

        # Include latest_scan if not already in archived list
        if LATEST_SCAN.exists():
            try:
                latest = json.loads(LATEST_SCAN.read_text())
                ts = latest.get("scan_timestamp", "")
                if not any(s.get("scan_timestamp") == ts for s in scans):
                    latest["_source_file"] = "latest_scan.json"
                    scans.append(latest)
            except Exception as exc:
                logger.warning("Could not read latest_scan.json: %s", exc)

        return scans

    def compute_trends(self, scans: list[dict]) -> dict:
        """Derive trend data from the scan list."""
        if not scans:
            return {}

        # Time series of health scores
        score_series: list[dict] = []
        for s in scans:
            ts = s.get("scan_timestamp", "")
            score = s.get("ai_analysis", {}).get("health_score")
            if ts and score is not None:
                score_series.append({"timestamp": ts, "score": score})

        # Recurring suggestions by title (across all scans)
        title_counter: Counter = Counter()
        category_counter: Counter = Counter()
        priority_counter: Counter = Counter()
        suggestion_details: dict[str, dict] = {}

        for s in scans:
            for sug in s.get("ai_analysis", {}).get("suggestions", []):
                title = sug.get("title", "Unknown")
                category = sug.get("category", "Unknown")
                priority = sug.get("priority", "Info")
                title_counter[title] += 1
                category_counter[category] += 1
                priority_counter[priority] += 1
                if title not in suggestion_details:
                    suggestion_details[title] = sug

        # Suggestions appearing in more than one scan = recurring
        recurring = [
            {**suggestion_details[title], "occurrence_count": count}
            for title, count in title_counter.most_common(10)
            if count > 1
        ]

        # Category distribution (latest scan only for pie chart)
        latest_suggestions = scans[-1].get("ai_analysis", {}).get("suggestions", [])
        latest_category_dist = Counter(s.get("category", "Other") for s in latest_suggestions)

        # Score statistics
        scores = [s["score"] for s in score_series]
        avg_score = round(sum(scores) / len(scores), 1) if scores else None
        min_score = min(scores) if scores else None
        max_score = max(scores) if scores else None
        trend_direction = "stable"
        if len(scores) >= 2:
            delta = scores[-1] - scores[-2]
            if delta >= 5:
                trend_direction = "improving"
            elif delta <= -5:
                trend_direction = "degrading"

        # Alerts summary (if alerts file exists)
        alerts_summary = self._load_alerts_summary()

        return {
            "score_series": score_series,
            "avg_score": avg_score,
            "min_score": min_score,
            "max_score": max_score,
            "latest_score": scores[-1] if scores else None,
            "trend_direction": trend_direction,
            "total_scans": len(scans),
            "recurring_issues": recurring,
            "category_distribution": dict(latest_category_dist),
            "priority_distribution": dict(priority_counter),
            "alerts_summary": alerts_summary,
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }

    def generate_report(self) -> str:
        """Load history, compute trends, render and write HTML. Returns output path."""
        scans = self.load_scan_history()
        if not scans:
            raise RuntimeError("No scan data found. Run at least one scan first.")

        trends = self.compute_trends(scans)
        latest_scan = scans[-1]
        latest_ai = latest_scan.get("ai_analysis", {})

        ctx = {
            "hostname": latest_scan.get("hostname", "unknown"),
            "macos_version": latest_scan.get("macos_version", "unknown"),
            "generated_at": trends["generated_at"],
            "total_scans": trends["total_scans"],
            "latest_score": trends["latest_score"],
            "avg_score": trends["avg_score"],
            "min_score": trends["min_score"],
            "max_score": trends["max_score"],
            "trend_direction": trends["trend_direction"],
            "score_series_json": json.dumps(trends["score_series"]),
            "category_dist_json": json.dumps(trends["category_distribution"]),
            "priority_dist_json": json.dumps(trends["priority_distribution"]),
            "recurring_issues": trends["recurring_issues"],
            "latest_suggestions": latest_ai.get("suggestions", []),
            "latest_summary": latest_ai.get("summary", ""),
            "alerts_summary": trends["alerts_summary"],
        }

        env = Environment(loader=FileSystemLoader(str(TEMPLATES_DIR)))
        template = env.get_template("report.html.j2")
        html = template.render(**ctx)

        out_path = self.output_dir / "report.html"
        out_path.write_text(html, encoding="utf-8")
        logger.info("Report written: %s", out_path)
        return str(out_path)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _load_alerts_summary(self) -> dict:
        alerts_file = Path(__file__).parent.parent / "data" / "alerts.jsonl"
        if not alerts_file.exists():
            return {"total": 0, "by_metric": {}, "by_severity": {}}
        records = []
        for line in alerts_file.read_text().strip().splitlines():
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError:
                continue
        by_metric: Counter = Counter(r.get("metric") for r in records)
        by_severity: Counter = Counter(r.get("severity") for r in records)
        return {
            "total": len(records),
            "by_metric": dict(by_metric.most_common(5)),
            "by_severity": dict(by_severity),
        }


# ------------------------------------------------------------------
# CLI entry point
# ------------------------------------------------------------------

def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Report Agent — generate HTML trend report from scan history")
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR),
                        help="Directory to write report.html")
    parser.add_argument("--stats-only", action="store_true",
                        help="Print trend statistics to stdout and exit (no HTML generated)")
    parser.add_argument("--verbose", action="store_true")
    return parser.parse_args()


if __name__ == "__main__":
    args = _parse_args()
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )

    agent = ReportAgent(output_dir=args.output_dir)

    try:
        scans = agent.load_scan_history()
        trends = agent.compute_trends(scans)
    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)

    if args.stats_only or not scans:
        print(f"\n{'='*50}")
        print(f"  Scans analysed   : {trends.get('total_scans', 0)}")
        print(f"  Latest score     : {trends.get('latest_score', 'N/A')}/100")
        print(f"  Avg score        : {trends.get('avg_score', 'N/A')}/100")
        print(f"  Score range      : {trends.get('min_score', 'N/A')} – {trends.get('max_score', 'N/A')}")
        print(f"  Trend            : {trends.get('trend_direction', 'N/A')}")
        print(f"  Alerts logged    : {trends.get('alerts_summary', {}).get('total', 0)}")
        if trends.get("recurring_issues"):
            print("\n  Top recurring issues:")
            for r in trends["recurring_issues"][:5]:
                print(f"    [{r['priority']:8s}] {r['title']} ({r['occurrence_count']}x)")
        print(f"{'='*50}\n")
        sys.exit(0)

    try:
        out = agent.generate_report()
        print(f"\nReport generated: {out}\n")
    except RuntimeError as e:
        print(f"Error: {e}")
        sys.exit(1)
