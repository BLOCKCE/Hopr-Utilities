"""Miscellaneous temp-file helpers used by the Main widget."""

import os
import re
import uuid
from pathlib import Path

def _sj_temp_root(self) -> Path:
    base = os.environ.get("LOCALAPPDATA")
    if not base:
        base = str(Path.home() / "AppData" / "Local")
    root = Path(base) / "SubplaceJoiner" / "temp"
    root.mkdir(parents=True, exist_ok=True)
    return root

def _safe_name(self, s: str) -> str:
    s = (s or "").strip()
    if not s:
        return "ASSET"
    s = re.sub(r'[<>:"/\\|?*\x00-\x1F]+', "_", s)
    s = re.sub(r"\s+", "_", s)
    s = re.sub(r"_+", "_", s).strip("_")
    return s[:80] if s else "ASSET"

def _make_sj_temp_file(self, kind: str, asset_id: int, ext: str, asset_name: str | None = None) -> Path:
    folder = self._sj_temp_root() / (kind or "misc")
    folder.mkdir(parents=True, exist_ok=True)
    return folder / f"ASSET_{asset_id}{ext}"

def _make_sj_temp_dir(self, kind: str, asset_id: int, prefix: str) -> Path:
    folder = self._sj_temp_root() / (kind or "misc")
    folder.mkdir(parents=True, exist_ok=True)
    return folder / f"{prefix}_{asset_id}_{uuid.uuid4().hex[:8]}"

