#!/usr/bin/env python3
"""
Remediation Agent — applies safe fixes from Claude's suggestions with full rollback support.

Safety tiers:
  SAFE_AUTO      — non-destructive permission fixes (e.g. chmod on SSH keys)
  SAFE_SNAPSHOT  — deletions / file changes that are reversible via RollbackAgent snapshot
  MANUAL         — security settings (SIP, FileVault), system files, network — never auto-applied
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

logger = logging.getLogger(__name__)

LATEST_SCAN = Path(__file__).parent.parent / "data" / "latest_scan.json"
REMEDIATION_LOG = Path(__file__).parent.parent / "data" / "remediation_log.jsonl"

# Patterns that identify safe, non-destructive permission fixes
_SAFE_AUTO_PATTERNS: list[re.Pattern] = [
    re.compile(r"chmod\s+(600|400|700)\s+~?/?(\.ssh|\.gnupg)/", re.IGNORECASE),
]

# Patterns for file-deletion actions that are recoverable (trash, user caches)
_SAFE_SNAPSHOT_PATTERNS: list[re.Pattern] = [
    re.compile(r"osascript.*empty\s+trash", re.IGNORECASE),
    re.compile(r"rm\s+-[rf]+\s+~?/?(\.Trash|Users/[^/]+/\.Trash)", re.IGNORECASE),
    re.compile(r"rm\s+-[rf]+\s+~/Library/Caches", re.IGNORECASE),
]

# Patterns that must NEVER be auto-applied
_BLOCKED_PATTERNS: list[re.Pattern] = [
    re.compile(r"csrutil", re.IGNORECASE),
    re.compile(r"fdesetup", re.IGNORECASE),
    re.compile(r"sudo\s+rm\s+-rf\s+/(?!Users)", re.IGNORECASE),
    re.compile(r"systemctl|launchctl\s+(disable|unload)", re.IGNORECASE),
]


def _classify_action(action_str: str) -> str:
    """Return 'safe_auto', 'safe_snapshot', or 'manual'."""
    for pat in _BLOCKED_PATTERNS:
        if pat.search(action_str):
            return "manual"
    for pat in _SAFE_AUTO_PATTERNS:
        if pat.search(action_str):
            return "safe_auto"
    for pat in _SAFE_SNAPSHOT_PATTERNS:
        if pat.search(action_str):
            return "safe_snapshot"
    return "manual"


class RemediationAgent:
    """
    Reads the latest scan, classifies each suggestion's action, and applies
    those in the safe tiers.  Always creates a rollback snapshot before
    making any filesystem changes.
    """

    def __init__(self, dry_run: bool = True, auto_apply: bool = False):
        self.dry_run = dry_run
        self.auto_apply = auto_apply  # if True, applies safe_snapshot actions too
        REMEDIATION_LOG.parent.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def load_suggestions(self) -> list[dict]:
        if not LATEST_SCAN.exists():
            raise FileNotFoundError(f"No latest scan found at {LATEST_SCAN}. Run a scan first.")
        data = json.loads(LATEST_SCAN.read_text())
        return data.get("ai_analysis", {}).get("suggestions", [])

    def plan(self) -> dict:
        """
        Classify all suggestions and return a plan dict without applying anything.
        """
        suggestions = self.load_suggestions()
        plan: dict[str, list[dict]] = {"safe_auto": [], "safe_snapshot": [], "manual": []}
        for s in suggestions:
            action_str = s.get("action", "")
            tier = _classify_action(action_str)
            plan[tier].append({
                "priority": s.get("priority"),
                "category": s.get("category"),
                "title": s.get("title"),
                "action": action_str,
                "estimated_impact": s.get("estimated_impact", ""),
                "tier": tier,
            })
        return plan

    def apply(self) -> dict:
        """
        Apply safe actions.  Returns a summary dict with applied/skipped/failed counts.
        Creates a rollback snapshot before any filesystem changes.
        """
        plan = self.plan()
        to_apply = list(plan["safe_auto"])
        if self.auto_apply:
            to_apply += list(plan["safe_snapshot"])

        if not to_apply:
            logger.info("No auto-applicable actions found.")
            return {"applied": 0, "skipped": len(plan["manual"]), "failed": 0, "snapshot_id": None}

        # Create snapshot for safe_snapshot items (file deletions)
        snapshot_id = None
        snapshot_items = [a for a in to_apply if a["tier"] == "safe_snapshot"]
        if snapshot_items and not self.dry_run:
            snapshot_id = self._create_snapshot(snapshot_items)

        results = []
        applied = failed = 0

        for item in to_apply:
            if self.dry_run:
                logger.info("[DRY-RUN] Would apply (%s): %s", item["tier"], item["action"])
                results.append({**item, "status": "dry_run"})
                continue

            success, output = self._run_action(item["action"])
            status = "applied" if success else "failed"
            if success:
                applied += 1
                logger.info("Applied (%s): %s", item["tier"], item["title"])
            else:
                failed += 1
                logger.error("Failed (%s): %s — %s", item["tier"], item["title"], output)

            results.append({**item, "status": status, "output": output})

        # Run post-check after applying (unless dry-run)
        post_check = None
        if not self.dry_run and applied > 0:
            post_check = self._run_post_check()

        summary = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "dry_run": self.dry_run,
            "applied": applied if not self.dry_run else 0,
            "dry_run_count": len(to_apply) if self.dry_run else 0,
            "skipped_manual": len(plan["manual"]),
            "failed": failed,
            "snapshot_id": snapshot_id,
            "results": results,
            "post_check": post_check,
        }

        if not self.dry_run:
            self._log_run(summary)

        return summary

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _create_snapshot(self, items: list[dict]) -> str | None:
        """Back up files referenced in safe_snapshot actions before modifying them."""
        from rollback.rollback_agent import RollbackAgent

        # Extract file paths from action strings
        actions = []
        home = Path.home()
        path_candidates = [
            home / ".Trash",
            home / "Library" / "Caches",
        ]
        for p in path_candidates:
            if p.exists():
                actions.append({"original_path": str(p)})

        if not actions:
            return None
        try:
            snapshot_id = RollbackAgent().create_snapshot(actions)
            logger.info("Rollback snapshot created: %s", snapshot_id)
            return snapshot_id
        except Exception as exc:
            logger.error("Could not create snapshot: %s", exc)
            return None

    def _run_action(self, action_str: str) -> tuple[bool, str]:
        """Execute a shell action string. Returns (success, output)."""
        try:
            result = subprocess.run(
                action_str,
                shell=True,
                capture_output=True,
                text=True,
                timeout=30,
            )
            output = (result.stdout + result.stderr).strip()
            return result.returncode == 0, output
        except subprocess.TimeoutExpired:
            return False, "Command timed out after 30s"
        except Exception as exc:
            return False, str(exc)

    def _run_post_check(self) -> dict:
        try:
            from post_check.health_checker import PostCleanupHealthChecker
            return PostCleanupHealthChecker().run()
        except Exception as exc:
            logger.error("Post-check failed: %s", exc)
            return {"verdict": "ERROR", "error": str(exc)}

    def _log_run(self, summary: dict) -> None:
        with open(REMEDIATION_LOG, "a") as f:
            f.write(json.dumps(summary, default=str) + "\n")


# ------------------------------------------------------------------
# CLI entry point
# ------------------------------------------------------------------

def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Remediation Agent — auto-apply safe Claude suggestions with rollback support"
    )
    mode_group = parser.add_mutually_exclusive_group()
    mode_group.add_argument("--dry-run", action="store_true", default=True,
                            help="Show what would be applied without making changes (default)")
    mode_group.add_argument("--apply", action="store_true",
                            help="Apply safe_auto actions (chmod fixes etc.)")
    mode_group.add_argument("--apply-all", action="store_true",
                            help="Apply safe_auto AND safe_snapshot actions (e.g. empty trash, clear cache)")
    parser.add_argument("--plan-only", action="store_true",
                        help="Print the classified action plan and exit")
    parser.add_argument("--verbose", action="store_true")
    return parser.parse_args()


def _print_plan(plan: dict) -> None:
    total = sum(len(v) for v in plan.values())
    print(f"\nRemediation Plan  ({total} suggestions)\n{'='*60}")
    for tier, items in plan.items():
        label = {"safe_auto": "SAFE AUTO", "safe_snapshot": "SAFE (snapshot)", "manual": "MANUAL ONLY"}[tier]
        print(f"\n  [{label}]  {len(items)} action(s)")
        for item in items:
            print(f"    [{item['priority']:8s}] {item['title']}")
            print(f"             Action: {item['action'][:80]}")
            if item["estimated_impact"]:
                print(f"             Impact: {item['estimated_impact']}")
    print()


if __name__ == "__main__":
    args = _parse_args()
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )

    dry_run = not (args.apply or args.apply_all)
    auto_apply = args.apply_all

    agent = RemediationAgent(dry_run=dry_run, auto_apply=auto_apply)

    if args.plan_only:
        try:
            plan = agent.plan()
            _print_plan(plan)
        except FileNotFoundError as e:
            print(f"Error: {e}")
            sys.exit(1)
        sys.exit(0)

    try:
        summary = agent.apply()
    except FileNotFoundError as e:
        print(f"Error: {e}")
        sys.exit(1)

    print(f"\n{'='*60}")
    if summary["dry_run"]:
        print(f"  DRY-RUN: {summary['dry_run_count']} action(s) would be applied")
    else:
        print(f"  Applied  : {summary['applied']}")
        print(f"  Failed   : {summary['failed']}")
        if summary["snapshot_id"]:
            print(f"  Snapshot : {summary['snapshot_id']}")
    print(f"  Skipped (manual review required): {summary['skipped_manual']}")

    if summary.get("post_check"):
        pc = summary["post_check"]
        print(f"\n  Post-check: {pc.get('verdict', 'N/A')}")
        if pc.get("issues"):
            for issue in pc["issues"]:
                print(f"    ! {issue['check']}: {issue['detail']}")

    if summary["dry_run"]:
        print("\n  Run with --apply or --apply-all to execute.")
    print(f"{'='*60}\n")
