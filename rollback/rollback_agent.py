from __future__ import annotations

import json
import logging
import shutil
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger(__name__)

SNAPSHOTS_DIR = Path(__file__).parent.parent / "snapshots"


class RollbackAgent:
    def __init__(self, snapshots_dir: Path = SNAPSHOTS_DIR):
        self.snapshots_dir = snapshots_dir
        self.snapshots_dir.mkdir(exist_ok=True)

    def create_snapshot(self, actions: list[dict]) -> str:
        snapshot_id = datetime.now(timezone.utc).strftime("%Y-%m-%d_%H%M%S")
        snapshot_path = self.snapshots_dir / snapshot_id
        files_path = snapshot_path / "files"
        files_path.mkdir(parents=True)

        backed_up_actions = []
        for action in actions:
            original = Path(action["original_path"])
            backed_up = self._backup_file(original, files_path)
            backed_up_actions.append({
                **action,
                "backup_path": str(backed_up) if backed_up else None,
                "backup_successful": backed_up is not None,
            })

        manifest = {
            "snapshot_id": snapshot_id,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "actions": backed_up_actions,
        }
        with open(snapshot_path / "manifest.json", "w") as f:
            json.dump(manifest, f, indent=2)

        logger.info("Snapshot created: %s (%d actions)", snapshot_id, len(actions))
        return snapshot_id

    def rollback(self, snapshot_id: str) -> bool:
        manifest = self._load_manifest(snapshot_id)
        if not manifest:
            logger.error("Snapshot not found: %s", snapshot_id)
            return False

        success = True
        for action in manifest["actions"]:
            if not action.get("backup_successful"):
                logger.warning("No backup for action: %s — skipping", action.get("original_path"))
                continue
            try:
                backup = Path(action["backup_path"])
                original = Path(action["original_path"])
                original.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(backup, original)
                logger.info("Restored: %s", original)
            except Exception as e:
                logger.error("Failed to restore %s: %s", action.get("original_path"), e)
                success = False

        if success:
            logger.info("Rollback complete for snapshot: %s", snapshot_id)
        return success

    def purge_snapshot(self, snapshot_id: str) -> bool:
        snapshot_path = self.snapshots_dir / snapshot_id
        if not snapshot_path.exists():
            logger.warning("Snapshot not found for purge: %s", snapshot_id)
            return False
        shutil.rmtree(snapshot_path)
        logger.info("Snapshot purged: %s", snapshot_id)
        return True

    def list_snapshots(self) -> list[dict]:
        result = []
        for entry in sorted(self.snapshots_dir.iterdir(), reverse=True):
            if entry.is_dir():
                manifest = self._load_manifest(entry.name)
                if manifest:
                    size = sum(f.stat().st_size for f in entry.rglob("*") if f.is_file())
                    result.append({
                        "snapshot_id": entry.name,
                        "created_at": manifest.get("created_at"),
                        "action_count": len(manifest.get("actions", [])),
                        "size_mb": round(size / 1e6, 1),
                    })
        return result

    def _backup_file(self, original: Path, files_dir: Path) -> Path | None:
        if not original.exists():
            return None
        try:
            safe_name = str(original).replace("/", "_").lstrip("_")
            dest = files_dir / safe_name
            shutil.copy2(original, dest)
            return dest
        except Exception as e:
            logger.error("Backup failed for %s: %s", original, e)
            return None

    def _load_manifest(self, snapshot_id: str) -> dict | None:
        manifest_path = self.snapshots_dir / snapshot_id / "manifest.json"
        if not manifest_path.exists():
            return None
        try:
            with open(manifest_path) as f:
                return json.load(f)
        except Exception:
            return None
