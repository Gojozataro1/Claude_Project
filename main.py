#!/usr/bin/env python3
import argparse
import json
import logging
import os
import platform
import socket
import sys
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("aiops")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="macOS AI Ops — system health scanner and dashboard generator"
    )
    parser.add_argument("--mode", choices=["all", "dev", "ui", "vulnerability"], default=None,
                        help="Analysis mode (default: $AI_OPS_MODE or 'all')")
    parser.add_argument("--no-ai", action="store_true", help="Skip Claude API analysis")
    parser.add_argument("--verbose", action="store_true", help="Enable debug logging")
    parser.add_argument("--output-dir", default=None, help="Output directory for HTML (default: docs/)")
    parser.add_argument("--data-dir", default=None, help="Directory for scan JSON (default: data/)")

    # Rollback commands
    parser.add_argument("--list-snapshots", action="store_true", help="List all rollback snapshots")
    parser.add_argument("--rollback", metavar="SNAPSHOT_ID", help="Restore from a snapshot")
    parser.add_argument("--purge", metavar="SNAPSHOT_ID", help="Purge a snapshot after green signal")

    # Post-check
    parser.add_argument("--post-check", action="store_true", help="Run post-cleanup health check only")

    return parser.parse_args()


def run_scan(args: argparse.Namespace) -> int:
    from router.skill_router import SkillRouter
    from analyzer.claude_analyzer import ClaudeAnalyzer
    from dashboard.generator import DashboardGenerator

    mode = args.mode or os.getenv("AI_OPS_MODE", "all")
    output_dir = args.output_dir or os.getenv("AI_OPS_OUTPUT_DIR", "docs")
    data_dir = args.data_dir or os.getenv("AI_OPS_DATA_DIR", "data")
    model = os.getenv("AI_OPS_MODEL", "claude-sonnet-4-6")

    router = SkillRouter(mode)
    logger.info("Starting scan: %s", router.describe())

    scan_data = _collect(router)

    # AI Analysis
    ai_analysis = {"summary": "AI analysis skipped (--no-ai).", "health_score": 50, "suggestions": [], "model_used": "none", "tokens_used": {}}
    if not args.no_ai:
        api_key = os.getenv("ANTHROPIC_API_KEY", "")
        if not api_key:
            logger.warning("ANTHROPIC_API_KEY not set — skipping AI analysis. Run with --no-ai to suppress this warning.")
        else:
            logger.info("Running Claude analysis...")
            analyzer = ClaudeAnalyzer(api_key=api_key, model=model)
            ai_analysis = analyzer.analyze(scan_data, mode_focus=router.get_analyzer_focus())
            logger.info("Health score: %d/100, %d suggestions",
                        ai_analysis.get("health_score", 0), len(ai_analysis.get("suggestions", [])))

    # Write scan data
    Path(data_dir).mkdir(exist_ok=True)
    scan_output = {**scan_data, "ai_analysis": ai_analysis}
    scan_file = Path(data_dir) / "latest_scan.json"
    scan_file.write_text(json.dumps(scan_output, indent=2, default=str))
    logger.info("Scan data written: %s", scan_file)

    # Generate dashboard
    generator = DashboardGenerator(output_dir=output_dir)
    html = generator.render(scan_data, ai_analysis, mode=mode, layout=router.get_dashboard_layout())
    out_path = generator.write(html)
    logger.info("Dashboard written: %s", out_path)

    # Summary
    score = ai_analysis.get("health_score", "N/A")
    criticals = sum(1 for s in ai_analysis.get("suggestions", []) if s.get("priority") == "Critical")
    print(f"\n{'='*50}")
    print(f"  Health Score: {score}/100")
    print(f"  Critical Issues: {criticals}")
    print(f"  Suggestions: {len(ai_analysis.get('suggestions', []))}")
    print(f"  Dashboard: {out_path}")
    print(f"{'='*50}\n")
    return 0


def _collect(router) -> dict:
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
            logger.info("Collecting: %s", name)
            try:
                data = cls().collect()
                scan_data[key] = data
                logger.info("  Done: %s", name)
            except Exception as e:
                logger.error("Collector %s failed: %s", name, e)

    return scan_data


def main() -> int:
    args = parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    # Rollback commands
    if args.list_snapshots:
        from rollback.rollback_agent import RollbackAgent
        snapshots = RollbackAgent().list_snapshots()
        if not snapshots:
            print("No snapshots found.")
        for s in snapshots:
            print(f"  {s['snapshot_id']}  |  {s['created_at']}  |  {s['action_count']} actions  |  {s['size_mb']}MB")
        return 0

    if args.rollback:
        from rollback.rollback_agent import RollbackAgent
        success = RollbackAgent().rollback(args.rollback)
        print("Rollback successful." if success else "Rollback FAILED — check logs.")
        return 0 if success else 1

    if args.purge:
        from rollback.rollback_agent import RollbackAgent
        success = RollbackAgent().purge_snapshot(args.purge)
        print(f"Snapshot {args.purge} purged." if success else "Purge failed — snapshot not found.")
        return 0 if success else 1

    # Post-check only
    if args.post_check:
        from post_check.health_checker import PostCleanupHealthChecker
        logger.info("Running post-cleanup health check...")
        result = PostCleanupHealthChecker().run()
        verdict = result["verdict"]
        print(f"\n{'='*50}")
        print(f"  Post-Cleanup Status: {verdict}")
        print(f"  Passed: {result['pass_count']} / {result['pass_count'] + result['fail_count']}")
        for check, r in result["checks"].items():
            icon = "✓" if r["status"] == "pass" else "✗"
            print(f"  {icon} {check}: {r['detail']}")
        if result["issues"]:
            print("\n  Issues found:")
            for issue in result["issues"]:
                print(f"    - {issue['check']}: {issue['detail']}")
        print(f"{'='*50}\n")
        return 0 if verdict == "ALL_CLEAR" else 1

    # Full scan
    return run_scan(args)


if __name__ == "__main__":
    sys.exit(main())
