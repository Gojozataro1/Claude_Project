from __future__ import annotations

import json
import os
from pathlib import Path

PROFILES_DIR = Path(__file__).parent / "profiles"
VALID_MODES = {"all", "dev", "ui", "vulnerability"}


class SkillRouter:
    def __init__(self, mode: str = "all"):
        if mode not in VALID_MODES:
            raise ValueError(f"Invalid mode '{mode}'. Choose from: {', '.join(sorted(VALID_MODES))}")
        self.mode = mode
        self._profile = self._load_profile(mode)

    def _load_profile(self, mode: str) -> dict:
        profile_path = PROFILES_DIR / f"{mode}.json"
        with open(profile_path) as f:
            return json.load(f)

    def get_active_collectors(self) -> list[str]:
        return self._profile["collectors"]

    def get_analyzer_focus(self) -> str:
        return self._profile["analyzer_focus"]

    def get_dashboard_layout(self) -> dict:
        return self._profile["dashboard_layout"]

    def get_disk_patterns(self) -> list[str]:
        return self._profile.get("disk_large_file_patterns", [])

    def describe(self) -> str:
        return f"[{self.mode.upper()}] {self._profile['description']}"

    @staticmethod
    def available_modes() -> list[str]:
        return sorted(VALID_MODES)
