"""First-run welcome dialog with optional HoprU import."""

import json
import os
from pathlib import Path

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QLabel, QCheckBox, QPushButton,
)
from PySide6.QtCore import Qt


def _local_app_data() -> Path:
    base = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
    return Path(base)


def _rules_path() -> Path:
    return _local_app_data() / "SubplaceJoiner" / "cache_loader_rules.json"


def _settings_path() -> Path:
    return _local_app_data() / "SubplaceJoiner" / "app_settings.json"


def _import_from_hopru():
    """Parse caches.json and collections.json from HoprU and merge into
    cache_loader_rules.json using the current format."""
    sj_dir = _local_app_data() / "SubplaceJoiner"
    caches_path = sj_dir / "caches.json"
    collections_path = sj_dir / "collections.json"
    rules_path = _rules_path()

    # ── load existing rules ──────────────────────────────────────────────────
    existing: dict = {}
    if rules_path.exists():
        try:
            existing = json.loads(rules_path.read_text(encoding="utf-8", errors="ignore"))
            if not isinstance(existing, dict) or existing.get("version", 1) == 1:
                existing = {}
        except Exception:
            existing = {}
    existing["version"] = 2

    sources: dict = existing.get("sources", {"Default": []})
    presets: list = existing.get("presets", [])

    # ── import caches ────────────────────────────────────────────────────────
    if caches_path.exists():
        try:
            old = json.loads(caches_path.read_text(encoding="utf-8", errors="ignore"))
            for item in old.get("items", []):
                source   = item.get("source", "Default")
                name     = item.get("name", "")
                use_hash = item.get("use_hash", "")
                hash_kind = item.get("hash_kind", "id")
                replace_hash = item.get("replace_hash", "")
                enabled  = item.get("enabled", False)

                if not name:
                    continue

                if hash_kind == "id":
                    use_meta = {"mode": "inline_text", "value": use_hash}
                else:
                    # Binary/hash content stored as base64
                    use_meta = {
                        "mode": "inline_b64",
                        "value": use_hash,
                        "content_type": "application/octet-stream",
                    }

                rule = {
                    "enabled": enabled,
                    "name": name,
                    "use": use_meta,
                    "replace": replace_hash,
                }

                if source not in sources:
                    sources[source] = []

                # Skip duplicates (matched by name within source)
                existing_names = {r.get("name") for r in sources[source]}
                if name not in existing_names:
                    sources[source].append(rule)

        except Exception as e:
            print(f"[welcome] caches import error: {e}")

    # ── import collections as custom presets ─────────────────────────────────
    if collections_path.exists():
        try:
            collections = json.loads(
                collections_path.read_text(encoding="utf-8", errors="ignore")
            )
            existing_preset_names = {p.get("name") for p in presets}

            for col in collections:
                col_name = col.get("name", "")
                cache_names = [
                    item.get("name", "")
                    for item in col.get("items", [])
                    if item.get("name")
                ]
                if col_name and col_name not in existing_preset_names:
                    presets.append({"name": col_name, "caches": cache_names})

        except Exception as e:
            print(f"[welcome] collections import error: {e}")

    # ── write back ───────────────────────────────────────────────────────────
    existing["sources"] = sources
    existing["presets"] = presets
    rules_path.parent.mkdir(parents=True, exist_ok=True)
    rules_path.write_text(json.dumps(existing, indent=2), encoding="utf-8")


def _mark_welcome_shown():
    path = _settings_path()
    try:
        settings: dict = {}
        if path.exists():
            settings = json.loads(path.read_text(encoding="utf-8", errors="ignore"))
            if not isinstance(settings, dict):
                settings = {}
        settings["welcome_shown"] = True
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(settings, indent=2), encoding="utf-8")
    except Exception as e:
        print(f"[welcome] failed to save settings: {e}")


class WelcomeDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Welcome!")
        self.setMinimumWidth(480)
        self.setWindowFlags(
            self.windowFlags() & ~Qt.WindowContextHelpButtonHint
        )

        layout = QVBoxLayout(self)
        layout.setSpacing(12)
        layout.setContentsMargins(20, 20, 20, 20)

        # ── title ────────────────────────────────────────────────────────────
        title = QLabel("Welcome!")
        title.setAlignment(Qt.AlignCenter)
        font = title.font()
        font.setPointSize(18)
        font.setBold(True)
        title.setFont(font)
        layout.addWidget(title)

        # ── body text ────────────────────────────────────────────────────────
        body = QLabel(
            "It appears this is your first time using this program, in this program you can find various "
            "different utilities, the program will close to system tray if you just click the X, you need "
            "to click QUIT after right clicking the program in system tray (system tray is that little arrow "
            "next to the time in your taskbar). This can be disabled though!"
        )
        body.setWordWrap(True)
        body.setAlignment(Qt.AlignLeft | Qt.AlignTop)
        layout.addWidget(body)

        layout.addSpacing(4)

        # ── checkboxes ───────────────────────────────────────────────────────
        self._import_check = QCheckBox("Import old caches from HoprU?")
        self._import_check.setChecked(True)
        self._dont_show_check = QCheckBox("Don't show again")
        layout.addWidget(self._import_check)
        layout.addWidget(self._dont_show_check)

        layout.addSpacing(4)

        # ── ok button ────────────────────────────────────────────────────────
        ok_btn = QPushButton("Ok")
        ok_btn.setDefault(True)
        ok_btn.clicked.connect(self._on_ok)
        layout.addWidget(ok_btn)

    def _on_ok(self):
        if self._import_check.isChecked():
            _import_from_hopru()
        if self._dont_show_check.isChecked():
            _mark_welcome_shown()
        self.accept()
