"""Preset management for the cache module."""

from ui.presetsthing import Ui_Form as PresetsThingUI
from widgets.game_card_widget import GameCardWidget
from widgets.add_game_card_widget import AddGameCardWidget
from ui.dialog6_ui import Ui_Dialog as Dialog6UI
from ui.dialog5_ui import Ui_Dialog as Dialog5UI
from ui.dialog4_ui import Ui_Dialog as Dialog4UI
from ui.dialog3_ui import Ui_Dialog as Dialog3UI
from ui.dialog2_ui import Ui_Dialog as Dialog2UI
from ui.dialog1_ui import Ui_Dialog as Dialog1UI
from PySide6.QtCore import QFile, QSortFilterProxyModel, QRect
from PySide6.QtUiTools import QUiLoader
from PySide6.QtWidgets import (
    QTreeView, QTableView, QWidget, QDialog, QPushButton, QHBoxLayout, QGridLayout, QSizePolicy, QLineEdit, QCheckBox,
    QMenu, QAbstractItemView, QHeaderView, QStyledItemDelegate, QApplication, QLabel, QSlider, QFrame, QVBoxLayout,
    QTextEdit, QFileDialog, QSplitter, QWidgetAction, QStyle, QStyleOptionMenuItem
)
from PySide6.QtGui import QStandardItemModel, QStandardItem, QPixmap, QPainter, QGuiApplication, QPalette
from PySide6.QtCore import Qt, QObject, QEvent, QPersistentModelIndex, QTimer, QUrl, Signal
import os
import gzip
import subprocess
import sys
import tempfile
import pygame
import json
import time
import win32crypt
import base64
import re
import threading
import requests
import struct
import shutil
import uuid
import importlib
import numpy as np
from PIL import Image
import xml.etree.ElementTree as ET
from pathlib import Path
from shiboken6 import isValid
from mutagen import File as MutagenFile
from urllib.parse import urlparse, urlunparse
from datetime import datetime
import gc
from requests.adapters import HTTPAdapter
import urllib.request
import urllib.error
try:
    from mitmproxy import http
except Exception:
    http = None


from shared.constants import CLOG_RAW_URL, ASSET_TYPES, adapter
from shared.utils import strip_cache_header, get_roblosecurity, isnumeric, github_blob_to_raw_url, batch_location
from shared.models import SortProxy
from shared.delegates import HoverDelegate
from shared.ui_loader import load_ui
from shared.audio_player import AudioPlayer
from shared.menu_utils import StayOpenMenu
from shared.threading_utils import _MainThreadInvoker


def _setup_preset_tree(self):
    tree = self.preset_tree

    # Create model with 2 columns
    self.preset_model = QStandardItemModel(0, 2, self.tab_widget)
    self.preset_model.setHorizontalHeaderLabels(["Name", "Total Caches"])

    tree.setModel(self.preset_model)
    tree.setEditTriggers(QAbstractItemView.NoEditTriggers)
    tree.setSortingEnabled(True)
    tree.setAnimated(True)
    tree.setSelectionBehavior(QAbstractItemView.SelectRows)
    tree.setSelectionMode(QAbstractItemView.ExtendedSelection)
    tree.setDragEnabled(False)
    tree.setDragDropMode(QAbstractItemView.NoDragDrop)

    # Make columns resizable
    tree.header().setSectionResizeMode(0, QHeaderView.Interactive)
    tree.header().setSectionResizeMode(1, QHeaderView.ResizeToContents)

    header = tree.header()
    header.sectionResized.connect(
        lambda i, old, new, tv=self.preset_tree: self._on_column_resized(
            i, old, new, tv)
    )

    # Set initial column widths (overridden by saved widths if available)
    tree.setColumnWidth(0, 200)
    QTimer.singleShot(0, lambda: self._apply_saved_col_widths(tree))

    # Compact headers like tables
    tree.header().setMinimumHeight(22)
    tree.header().setMaximumHeight(22)
    tree.header().setMinimumWidth(40)

    tree.header().setDefaultAlignment(Qt.AlignLeft | Qt.AlignVCenter)

    tree.setContextMenuPolicy(Qt.CustomContextMenu)
    tree.customContextMenuRequested.connect(self._show_preset_context_menu)

    QTimer.singleShot(0, self._load_presets)


def _save_presets(self):
    if getattr(self, "_loading_presets", False):
        return
    try:
        presets = []
        for row in range(self.preset_model.rowCount()):
            item = self.preset_model.item(row, 0)
            if not item:
                continue
            cache_names = [item.child(cr, 0).text() for cr in range(
                item.rowCount()) if item.child(cr, 0)]
            presets.append({"name": item.text(), "caches": cache_names})
        self._write_data_file(presets=presets)
    except Exception as e:
        print(f"Failed to save presets: {e}")


def _load_presets(self):
    path = self._loader_rules_path()
    if not path.exists():
        return
    try:
        payload = json.loads(path.read_text(encoding="utf-8", errors="ignore"))
        if not isinstance(payload, dict):
            return
        presets = payload.get("presets", [])
        if not isinstance(presets, list):
            return
        self._loading_presets = True
        for p in presets:
            name = str(p.get("name", ""))
            caches = p.get("caches", [])
            if name and isinstance(caches, list):
                self.add_preset(name, [str(c) for c in caches])
    except Exception as e:
        print(f"Failed to load presets: {e}")
    finally:
        self._loading_presets = False


def add_preset(self, preset_name: str, cache_names: list):

    name_item = QStandardItem(preset_name)
    count_item = QStandardItem(str(len(cache_names)))
    name_item.setEditable(False)
    count_item.setEditable(False)
    self.preset_model.appendRow([name_item, count_item])

    for cache_name in cache_names:
        child_name = QStandardItem(cache_name)
        child_count = QStandardItem("")

        child_name.setEditable(False)
        child_count.setEditable(False)

        name_item.appendRow([child_name, child_count])

    if not getattr(self, "_loading_presets", False):
        self._save_presets()


def create_preset(self):
    dialog = QDialog(self.tab_widget)
    ui = Dialog4UI()
    ui.setupUi(dialog)

    if not dialog.exec():
        return

    preset_name = ui.lineEdit.text().strip()
    if not preset_name:
        return

    enabled_caches = []
    seen = set()

    # Current source (in-memory)
    for row in range(self.loader_model.rowCount()):
        checkbox_item = self.loader_model.item(row, 0)
        name_item = self.loader_model.item(row, 1)
        if checkbox_item and name_item and checkbox_item.checkState() == Qt.Checked:
            name = name_item.text()
            if name not in seen:
                seen.add(name)
                enabled_caches.append(name)

    # Include enabled caches from other sources if checkbox is checked
    include_cb = self.tab_widget.findChild(QCheckBox, "PresetsCheckBox")
    if include_cb and include_cb.isChecked():
        current = getattr(self, "_current_source_name", "Default")
        try:
            all_sources = self._load_all_sources()
            for source_name, rules in all_sources.items():
                if source_name == current:
                    continue
                for r in rules:
                    if r.get("enabled", True):
                        name = str(r.get("name", ""))
                        if name and name not in seen:
                            seen.add(name)
                            enabled_caches.append(name)
        except Exception as e:
            print(f"[create_preset] Failed to include other sources: {e}")

    if not enabled_caches:
        print("No enabled caches to add to preset")
        return

    self.add_preset(preset_name, enabled_caches)
    print(f"Created preset '{preset_name}' with {len(enabled_caches)} caches")


def _show_preset_context_menu(self, position):
    from PySide6.QtWidgets import QMenu, QMessageBox
    tree = self.preset_tree
    index = tree.indexAt(position)

    # Only top-level items are preset rows (not child cache-name rows)
    is_preset_row = index.isValid() and not index.parent().isValid()

    menu = QMenu(tree)

    if is_preset_row:
        export_act = menu.addAction("Export Preset")
        delete_act = menu.addAction("Delete Preset")
        menu.addSeparator()

        def _do_export():
            self._export_preset(index.row())

        def _do_delete():
            item = self.preset_model.item(index.row(), 0)
            name = item.text() if item else "?"
            if QMessageBox.question(
                self.tab_widget, "Delete Preset",
                f'Delete preset "{name}"?',
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
            ) == QMessageBox.Yes:
                self.preset_model.removeRow(index.row())
                self._save_presets()

        export_act.triggered.connect(_do_export)
        delete_act.triggered.connect(_do_delete)

    import_act = menu.addAction("Import Preset")
    import_act.triggered.connect(self._import_preset)

    menu.exec(tree.viewport().mapToGlobal(position))


def _export_preset(self, row: int = None):
    """Export a preset (with all its associated rules) to a JSON file."""
    from PySide6.QtWidgets import QFileDialog, QMessageBox
    from main_loader_rules import _rules_to_replacement_rules

    if row is None:
        # currentIndex() persists after button click; selectedIndexes() may not
        idx = self.preset_tree.currentIndex()
        if not idx.isValid():
            QMessageBox.information(
                self.tab_widget, "Export Preset", "Select a preset first.")
            return
        # If a child row is selected, use its parent (the preset)
        if idx.parent().isValid():
            idx = idx.parent()
        # Force column 0 — currentIndex() may be on column 1
        if idx.column() != 0:
            idx = idx.sibling(idx.row(), 0)
        item = self.preset_model.itemFromIndex(idx)
    else:
        item = self.preset_model.item(row, 0)

    if not item:
        return
    preset_name = item.text()
    cache_names = {
        item.child(cr, 0).text()
        for cr in range(item.rowCount())
        if item.child(cr, 0)
    }

    # Collect rules matching the preset's cache names (current source first,
    # then other sources so we don't export duplicates).
    matched_rules = []
    seen_names = set()

    current_rules = self._snapshot_rules()
    for r in current_rules:
        n = r.get("name", "")
        if n in cache_names and n not in seen_names:
            matched_rules.append(r)
            seen_names.add(n)

    try:
        all_sources = self._load_all_sources()
        current = getattr(self, "_current_source_name", "Default")
        for source_name, rules in all_sources.items():
            if source_name == current:
                continue
            for r in rules:
                n = r.get("name", "")
                if n in cache_names and n not in seen_names:
                    matched_rules.append(r)
                    seen_names.add(n)
    except Exception as e:
        print(f"[export_preset] error loading other sources: {e}")

    if not matched_rules:
        QMessageBox.information(
            self.tab_widget, "Export Preset",
            "No matching rules found for this preset's caches.\n"
            "Make sure the rules still exist in your sources.",
        )
        return

    payload = {
        "preset_name": preset_name,
        "replacement_rules": _rules_to_replacement_rules(matched_rules),
    }

    safe = re.sub(r'[^\w\-. ]', '_', preset_name)
    path, _ = QFileDialog.getSaveFileName(
        self.tab_widget,
        "Export Preset",
        f"{safe}_preset.json",
        "JSON Files (*.json);;All Files (*)",
    )
    if not path:
        return
    try:
        Path(path).write_text(json.dumps(payload, indent=2), encoding="utf-8")
    except Exception as e:
        QMessageBox.warning(self.tab_widget, "Export Failed",
                            f"Could not write file:\n{e}")


def _import_preset(self):
    """Import a preset (+ its rules) from a JSON file into the current source."""
    from PySide6.QtWidgets import QFileDialog, QMessageBox, QInputDialog
    from main_loader_rules import _parse_import_data

    path, _ = QFileDialog.getOpenFileName(
        self.tab_widget,
        "Import Preset",
        "",
        "JSON Files (*.json);;All Files (*)",
    )
    if not path:
        return

    try:
        data = json.loads(Path(path).read_text(
            encoding="utf-8", errors="ignore"))
    except Exception as e:
        QMessageBox.warning(self.tab_widget, "Import Failed",
                            f"Could not read/parse file:\n{e}")
        return

    result = _parse_import_data(data, self.tab_widget)
    if result is None:
        return
    rules_to_add, suggested_name = result

    if not rules_to_add:
        QMessageBox.information(
            self.tab_widget, "Import Preset", "No rules found in file.")
        return

    # Ask for the preset name (default to preset_name from file if present)
    default_name = suggested_name or Path(path).stem
    preset_name, ok = QInputDialog.getText(
        self.tab_widget, "Import Preset",
        "Name for the new preset:", text=default_name,
    )
    if not ok or not preset_name.strip():
        return
    preset_name = preset_name.strip()

    # Merge rules into the current source
    self._push_source_snapshot()
    existing = self._snapshot_rules()
    existing_names = {r.get("name") for r in existing}

    # Only add rules not already present (by name) to avoid duplicates
    new_rules = [r for r in rules_to_add if r.get(
        "name") not in existing_names]
    if new_rules:
        merged = existing + new_rules
        self._load_source_rules(merged)
        all_sources = self._load_all_sources()
        all_sources[getattr(self, "_current_source_name", "Default")] = merged
        self._write_data_file(sources=all_sources)

    # Create the preset entry
    all_names = [r.get("name", "") for r in rules_to_add if r.get("name")]
    self.add_preset(preset_name, all_names)


def apply_preset(self):
    indexes = self.preset_tree.selectionModel().selectedIndexes()
    if not indexes:
        print("No preset selected")
        return

    selected_index = indexes[0]
    item = self.preset_model.itemFromIndex(selected_index)

    if item.parent():
        item = item.parent()

    preset_name = item.text()

    cache_names = []
    for row in range(item.rowCount()):
        child = item.child(row, 0)
        if child:
            cache_names.append(child.text())

    for row in range(self.loader_model.rowCount()):
        checkbox_item = self.loader_model.item(row, 0)
        if checkbox_item:
            checkbox_item.setCheckState(Qt.Unchecked)

    enabled_count = 0
    for row in range(self.loader_model.rowCount()):
        name_item = self.loader_model.item(row, 1)
        checkbox_item = self.loader_model.item(row, 0)

        if name_item and checkbox_item and name_item.text() in cache_names:
            checkbox_item.setCheckState(Qt.Checked)
            enabled_count += 1

    # Update other sources on disk if checkbox is checked
    include_cb = self.tab_widget.findChild(QCheckBox, "PresetsCheckBox")
    if include_cb and include_cb.isChecked():
        cache_names_set = set(cache_names)
        current = getattr(self, "_current_source_name", "Default")
        try:
            all_sources = self._load_all_sources()
            changed = False
            for source_name, rules in all_sources.items():
                if source_name == current:
                    continue
                for r in rules:
                    want = str(r.get("name", "")) in cache_names_set
                    if r.get("enabled", True) != want:
                        r["enabled"] = want
                        changed = True
            if changed:
                self._write_data_file(sources=all_sources)
                self._rebuild_loader_index()
        except Exception as e:
            print(f"[apply_preset] Failed to update other sources: {e}")

    print(
        f"Applied preset '{preset_name}' - enabled {enabled_count}/{len(cache_names)} caches")


def _fetch_clog_json(self):
    try:
        r = self.net.get(CLOG_RAW_URL, timeout=12)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        print(f"[CLOG] Failed to fetch/parse CLOG.json: {e}")
        return None


def _normalize_games_from_clog(self, data):
    if data is None:
        return []
    if isinstance(data, dict) and "games" in data:
        games_val = data["games"]
        if isinstance(games_val, list):
            entries = games_val
        elif isinstance(games_val, dict):
            entries = []
            for game_name, game_obj in games_val.items():
                if isinstance(game_obj, dict):
                    e = dict(game_obj)
                    e.setdefault("name", game_name)
                    entries.append(e)
                else:
                    entries.append({"name": game_name, "caches": game_obj})
        else:
            entries = []
    else:
        if isinstance(data, list):
            entries = data
        elif isinstance(data, dict):
            entries = []
            for k, v in data.items():
                if isinstance(v, dict):
                    e = dict(v)
                    e.setdefault("name", k)
                    entries.append(e)
                else:
                    entries.append({"name": k, "caches": v})
        else:
            entries = []

    normalized = []
    for e in entries:
        if not isinstance(e, dict):
            continue

        name = e.get("name") or e.get("game") or e.get("title")
        if not name:
            continue
        place_id = e.get("placeId") or e.get("place_id") or e.get("id")
        try:
            place_id = int(place_id) if place_id is not None else None
        except Exception:
            place_id = None

        owner = e.get("Owner") or e.get("owner") or ""
        created = e.get("created") or e.get(
            "created_at") or e.get("dateCreated") or ""
        updated = e.get("updated") or e.get(
            "updated_at") or e.get("dateUpdated") or ""
        github_url = e.get("github") or e.get(
            "url") or e.get("link") or None
        replacement_url = (
            e.get("replacement") or e.get("Replacement")
            or e.get("replacements") or e.get("Replacements")
            or None
        )

        normalized.append({
            "name": str(name),
            "created": str(created),
            "updated": str(updated),
            "placeId": place_id,
            "Owner": owner,
            "github": github_url,
            "replacement": replacement_url,
        })

    return normalized


def _flatten_json(self, data, prefix=""):
    out = []

    if isinstance(data, dict):
        for k, v in data.items():
            key = f"{prefix}{k}" if not prefix else f"{prefix}/{k}"
            if isinstance(v, (dict, list)):
                out.extend(self._flatten_json(v, key))
            else:
                out.append((key, "" if v is None else str(v)))
        return out

    if isinstance(data, list):
        for i, v in enumerate(data):
            key = f"{prefix}[{i}]"
            if isinstance(v, (dict, list)):
                out.extend(self._flatten_json(v, key))
            else:
                out.append((key, "" if v is None else str(v)))
        return out

    out.append((prefix or "value", "" if data is None else str(data)))
    return out


def _fetch_and_flatten_urls(self, urls: list[str]) -> list[tuple[str, str]]:
    rows = []
    for url in urls:
        if not url or not isinstance(url, str):
            continue
        if not url.startswith(("http://", "https://")):
            continue

        j = self._fetch_json_url(url)
        if j is None:
            continue

        if isinstance(j, dict) and "caches" in j:
            j = j["caches"]

        rows.extend(self._flatten_json(j, prefix=""))

    seen = set()
    deduped = []
    for k, v in rows:
        sig = (k, v)
        if sig in seen:
            continue
        seen.add(sig)
        deduped.append((k, v))
    return deduped


def _short_url_label(self, url: str) -> str:
    try:
        s = url.strip()
        if "github.com/" in s and "/blob/" in s:
            repo = s.split("github.com/")[1].split("/blob/")[0]
            fn = s.split("/blob/")[-1].split("/")[-1]
            return f"{repo}/{fn}"
        return s.rsplit("/", 1)[-1] or s
    except Exception:
        return url


def _add_json_to_qtree(self, parent_item: "QStandardItem", parent_val_item: "QStandardItem", data, path_prefix: str):
    if isinstance(data, dict):
        for k, v in data.items():
            name_it = QStandardItem(str(k))
            val_it = QStandardItem("")
            name_it.setEditable(False)
            val_it.setEditable(False)
            full_path = f"{path_prefix}/{k}" if path_prefix else str(k)
            name_it.setData(full_path, Qt.UserRole)

            parent_item.appendRow([name_it, val_it])

            if isinstance(v, (dict, list)):
                self._add_json_to_qtree(name_it, val_it, v, full_path)
            else:
                val_it.setText("" if v is None else str(v))
        return

    if isinstance(data, list):
        for i, v in enumerate(data):
            key = f"[{i}]"
            name_it = QStandardItem(key)
            val_it = QStandardItem("")
            name_it.setEditable(False)
            val_it.setEditable(False)

            full_path = f"{path_prefix}{key}" if path_prefix else key
            name_it.setData(full_path, Qt.UserRole)

            parent_item.appendRow([name_it, val_it])

            if isinstance(v, (dict, list)):
                self._add_json_to_qtree(name_it, val_it, v, full_path)
            else:
                val_it.setText("" if v is None else str(v))
        return
    parent_val_item.setText("" if data is None else str(data))


def _collect_leaf_paths(self, root_item: "QStandardItem") -> list[str]:
    out: list[str] = []

    def walk(item: "QStandardItem"):
        if item.rowCount() == 0:
            p = item.data(Qt.UserRole)
            if isinstance(p, str) and p:
                out.append(p)
            return
        for r in range(item.rowCount()):
            ch = item.child(r, 0)
            if ch:
                walk(ch)

    walk(root_item)
    seen = set()
    deduped = []
    for x in out:
        if x in seen:
            continue
        seen.add(x)
        deduped.append(x)
    return deduped


def _load_remote_presets(self):
    data = self._fetch_clog_json()
    games = self._normalize_games_from_clog(data)

    self._remote_presets_by_name = {}
    self._remote_presets_by_place = {}

    for g in games:
        if g.get("name"):
            self._remote_presets_by_name[g["name"]] = g

        pid = g.get("placeId") or g.get("place_id")
        try:
            pid = int(pid) if pid is not None else None
        except:
            pid = None
        if pid:
            self._remote_presets_by_place[pid] = g

    return games


def _populate_test_preset_cards(self):
    try:
        for c in getattr(self, "_preset_cards", []):
            try:
                self.presets_grid.removeWidget(c)
                c.setParent(None)
                c.deleteLater()
            except Exception:
                pass
        self._preset_cards = []
    except Exception:
        self._preset_cards = []
    games = self._load_remote_presets() or []

    for i, g in enumerate(games):
        created = g.get("created", "")
        updated = g.get("updated", "")
        place_id = g.get("placeId") or g.get("place_id")
        try:
            place_id = int(place_id) if place_id is not None else None
        except Exception:
            place_id = None

        initial_name = g.get("name") or (
            f"Place {place_id}" if place_id else "Unknown")

        card = GameCardWidget(self.presets_container)
        card.set_data(name=initial_name, created=created, updated=updated)
        card._game_name = initial_name
        card._place_id = place_id
        gh_url = g.get("github")
        rep_url = g.get("replacement")
        if isinstance(gh_url, str) and gh_url.strip():
            card.ui.joinButton.setText("Assets")
            card.ui.joinButton.setVisible(True)
            card.on_join(lambda _=False, u=gh_url.strip(),
                         pid=place_id: self._open_url_picker(u, "use", pid))
        else:
            card.ui.joinButton.setVisible(False)

        if isinstance(rep_url, str) and rep_url.strip():
            card.ui.openButton.setText("Replacements")
            card.ui.openButton.setVisible(True)
            card.on_open(lambda _=False, u=rep_url.strip(),
                         pid=place_id: self._open_url_picker(u, "replace", pid))
        else:
            card.ui.openButton.setVisible(False)

        card.setMinimumWidth(0)
        card.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

        row = i // 3
        col = i % 3
        self.presets_grid.addWidget(card, row, col)

        self._preset_cards.append(card)
        if place_id:
            def worker(pid=place_id, c=card, cr=created, up=updated):
                real_name = None
                real_cr = cr
                real_up = up
                pix = None

                try:
                    real_name, api_cr, api_up = self._get_game_name_from_placeid(
                        pid)
                    if api_cr:
                        real_cr = api_cr
                    if api_up:
                        real_up = api_up
                except Exception as e:
                    print(f"[GAME META] name fetch failed for {pid}: {e}")

                try:
                    pix = self._fetch_place_icon_pixmap(pid)
                except Exception as e:
                    print(f"[THUMB] fetch failed for {pid}: {e}")

                def apply():
                    if real_name:
                        c.set_data(name=real_name, created=real_cr,
                                   updated=real_up)
                        c._game_name = real_name

                    if pix:
                        if hasattr(c, "set_thumbnail"):
                            try:
                                c.set_thumbnail(pix)
                            except Exception:
                                pass
                        elif hasattr(c, "set_icon"):
                            try:
                                c.set_icon(pix)
                            except Exception:
                                pass

                self._on_main(apply)

            threading.Thread(target=worker, daemon=True).start()

    # Load any custom game dumps the user has previously imported
    for g, fp in _load_custom_game_entries(self):
        _add_game_card_from_entry(self, g, dump_file=fp)

    # "+" add-card — not in _preset_cards so search filtering never hides it
    if not getattr(self, "_add_dump_card", None):
        add_card = AddGameCardWidget(self.presets_container)
        add_card.clicked.connect(lambda: _open_add_game_dump_dialog(self))
        self._add_dump_card = add_card


def _fetch_json_url(self, url: str):
    try:
        if os.path.isfile(url):
            return json.loads(Path(url).read_text(encoding="utf-8", errors="ignore"))
        r = self.net.get(url, timeout=12)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        print(f"[JSON] fetch failed {url}: {e}")
        return None


def _resolve_caches_for_game(self, game_entry: dict) -> list[str]:
    return []

# Presets


def _open_preset_window(self, place_id: int | None):
    entry = getattr(self, "_remote_presets_by_place",
                    {}).get(place_id, None)

    preset_name = None
    if isinstance(entry, dict):
        preset_name = entry.get("name")
    if not preset_name and place_id:
        preset_name = f"Place {place_id}"
    if not preset_name:
        preset_name = "Unknown"

    dialog = QDialog(self.tab_widget)
    dialog.setWindowTitle(f"Preset: {preset_name}")
    dialog.resize(500, 450)

    ui = PresetWindowUI()
    ui.setupUi(dialog)

    dialog.resize(950, 650)
    dialog.setMinimumSize(900, 600)

    try:
        ui.splitter.setSizes([500, 450])
    except Exception:
        pass

    preset_model = QStandardItemModel(0, 2, dialog)
    preset_model.setHorizontalHeaderLabels(["Name", "Value"])

    ui.treeView.setModel(preset_model)
    ui.treeView.setEditTriggers(QAbstractItemView.NoEditTriggers)
    ui.treeView.setSortingEnabled(True)
    ui.treeView.setAnimated(True)
    ui.treeView.header().setSectionResizeMode(0, QHeaderView.Interactive)
    ui.treeView.header().setSectionResizeMode(1, QHeaderView.Stretch)
    ui.treeView.setColumnWidth(0, 300)
    ui.treeView.header().setMinimumHeight(22)
    ui.treeView.header().setMaximumHeight(22)
    ui.treeView.header().setDefaultAlignment(Qt.AlignLeft | Qt.AlignVCenter)

    urls: list[str] = []
    if isinstance(entry, dict):
        gh = entry.get("github")
        rep = entry.get("replacement") or entry.get("Replacement")
        if isinstance(gh, str) and gh.strip():
            urls.append(gh.strip())
        if isinstance(rep, str) and rep.strip():
            urls.append(rep.strip())

    rows = self._fetch_and_flatten_urls(urls) if urls else []

    name_item = QStandardItem(preset_name)
    count_item = QStandardItem("")
    name_item.setEditable(False)
    count_item.setEditable(False)
    preset_model.appendRow([name_item, count_item])

    total_leaves = 0

    for url in (urls or []):
        j = self._fetch_json_url(url)
        if j is None:
            continue

        if isinstance(j, dict) and "caches" in j:
            j = j["caches"]

        url_label = self._short_url_label(url)
        url_item = QStandardItem(url_label)
        url_val = QStandardItem("")
        url_item.setEditable(False)
        url_val.setEditable(False)
        name_item.appendRow([url_item, url_val])
        self._add_json_to_qtree(url_item, url_val, j, path_prefix="")
        total_leaves += len(self._collect_leaf_paths(url_item))

    count_item.setText(str(total_leaves))

    ui.treeView.expandAll()

    ui.ApplyButton.clicked.connect(
        lambda: self._apply_preset_from_window(ui.treeView, dialog)
    )

    dialog.exec()


def _relayout_preset_cards(self):
    if not getattr(self, "presets_scroll", None) or not getattr(self, "presets_container", None):
        return

    cards = getattr(self, "_preset_filtered_cards", None)
    if cards is None:
        cards = getattr(self, "_preset_cards", [])
    if not cards:
        return

    vw = self.presets_scroll.viewport().width()
    if vw <= 0:
        return

    self.presets_container.setUpdatesEnabled(False)

    # Clear layout
    while self.presets_grid.count():
        self.presets_grid.takeAt(0)

    # compute columns
    card_w = 240
    spacing = self.presets_grid.spacing() or 8
    margins = self.presets_grid.contentsMargins()
    avail = vw - (margins.left() + margins.right())
    per_row = max(1, int((avail + spacing) // (card_w + spacing)))

    # 🧢
    per_row = min(per_row, 8)

    allowed = set(cards)
    for c in getattr(self, "_preset_cards", []):
        c.setVisible(c in allowed)

    # Add only the cards we want
    for i, card in enumerate(cards):
        r = i // per_row
        c = i % per_row
        self.presets_grid.addWidget(card, r, c)

    # Always place the "+" add card at the very end
    add_card = getattr(self, "_add_dump_card", None)
    if add_card is not None:
        n = len(cards)
        add_card.setVisible(True)
        self.presets_grid.addWidget(add_card, n // per_row, n % per_row)

    self.presets_container.setUpdatesEnabled(True)
    self.presets_container.update()


def _apply_preset_from_window(self, tree_view, dialog):
    indexes = tree_view.selectionModel().selectedIndexes()
    if not indexes:
        print("No preset selected")
        return

    model = tree_view.model()
    selected_index = indexes[0]
    item = model.itemFromIndex(selected_index)

    # If it's a child item, get its parent
    cache_names = []
    if item.rowCount() == 0:
        p = item.data(Qt.UserRole)
        if isinstance(p, str) and p:
            cache_names = [p]
    else:
        cache_names = self._collect_leaf_paths(item)

    # First uncheck all caches
    for row in range(self.loader_model.rowCount()):
        checkbox_item = self.loader_model.item(row, 0)
        if checkbox_item:
            checkbox_item.setCheckState(Qt.Unchecked)

    # Then check only the caches in the preset
    enabled_count = 0
    for row in range(self.loader_model.rowCount()):
        name_item = self.loader_model.item(row, 1)
        checkbox_item = self.loader_model.item(row, 0)

        if name_item and checkbox_item and name_item.text() in cache_names:
            checkbox_item.setCheckState(Qt.Checked)
            enabled_count += 1

    # Update other sources on disk if checkbox is checked
    include_cb = self.tab_widget.findChild(QCheckBox, "PresetsCheckBox")
    if include_cb and include_cb.isChecked():
        cache_names_set = set(cache_names)
        current = getattr(self, "_current_source_name", "Default")
        try:
            all_sources = self._load_all_sources()
            changed = False
            for source_name, rules in all_sources.items():
                if source_name == current:
                    continue
                for r in rules:
                    want = str(r.get("name", "")) in cache_names_set
                    if r.get("enabled", True) != want:
                        r["enabled"] = want
                        changed = True
            if changed:
                self._write_data_file(sources=all_sources)
                self._rebuild_loader_index()
        except Exception as e:
            print(f"[apply_preset] Failed to update other sources: {e}")

    print(
        f"Applied preset '{preset_name}' - enabled {enabled_count}/{len(cache_names)} caches")

    # Close dialog and switch to loader tab
    dialog.accept()


def _apply_presets_search_filter(self):
    text = self.presets_search.text().strip().lower()

    if not text:
        self._preset_filtered_cards = None
        self._relayout_preset_cards()
        return

    matches = []
    for card in self._preset_cards:
        name = getattr(card, "_game_name", "")
        if text in name.lower():
            matches.append(card)

    # sorting
    matches.sort(key=lambda c: getattr(c, "_game_name", "").lower())

    self._preset_filtered_cards = matches
    self._relayout_preset_cards()


def _set_splitter2_mode(self, mode: str):
    sp2 = getattr(self, "splitter_2", None)
    if not sp2:
        return

    try:
        sp2.setSizes([800, 400])
    except Exception:
        pass


def open_presets_window(self):
    if getattr(self, "_presets_dialog", None) is None:
        dlg = QDialog(self.tab_widget)
        dlg.setWindowTitle("Presets")
        dlg.resize(900, 600)

        ui = PresetsThingUI()
        ui.setupUi(dlg)

        self._presets_dialog = dlg
        self._presets_ui = ui

        self.presets_search = ui.PresetsSearchLine
        self.presets_scroll = ui.Results
        self.presets_container = ui.resultsContainer

        if self.presets_container.layout() is None:
            self.presets_grid = QGridLayout(self.presets_container)
            self.presets_container.setLayout(self.presets_grid)
        else:
            self.presets_grid = self.presets_container.layout()

        self.presets_grid.setContentsMargins(8, 8, 8, 8)
        self.presets_grid.setSpacing(8)
        self.presets_grid.setAlignment(Qt.AlignTop | Qt.AlignLeft)

        self._preset_search_timer = QTimer(dlg)
        self._preset_search_timer.setSingleShot(True)
        self._preset_search_timer.timeout.connect(
            self._apply_presets_search_filter)
        self.presets_search.textChanged.connect(
            lambda: self._preset_search_timer.start(80))

        self._preset_cards = []
        self._preset_filtered_cards = None
        self._populate_test_preset_cards()
        QTimer.singleShot(0, self._relayout_preset_cards)

    self._presets_dialog.show()
    self._presets_dialog.raise_()
    self._presets_dialog.activateWindow()

    _main_mod = sys.modules.get('__main__')
    _apply_light = getattr(_main_mod, 'apply_light_to_mainwindow', None)
    if _apply_light:
        _apply_light(self._presets_dialog)


def _load_2nd_presets_ui_class(self):
    here = os.path.dirname(os.path.dirname(__file__))
    path = os.path.join(here, "ui", "2ndPresetsThing.py")
    spec = importlib.util.spec_from_file_location(
        "_second_presets_ui", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.Ui_Form


def _open_url_picker(self, url: str, target: str, place_id: int | None = None):
    """Fetch url's JSON, show a selectable tree, import chosen IDs to the target lineedit.
    target='use' -> replace_with_lineedit, target='replace' -> replace_ids_lineedit."""
    j = self._fetch_json_url(url)
    if j is None:
        return
    if isinstance(j, dict) and "caches" in j:
        j = j["caches"]

    dlg = QDialog(self.tab_widget)

    Ui2 = self._load_2nd_presets_ui_class()
    ui2 = Ui2()
    ui2.setupUi(dlg)

    dlg.setWindowTitle(self._short_url_label(url))
    dlg.resize(1200, 800)

    tv = ui2.treeView
    _main_mod = sys.modules.get('__main__')
    _sys_is_dark = getattr(_main_mod, 'system_is_dark', None)
    _light_tree_qss = getattr(_main_mod, 'LIGHT_TREE_QSS', None)
    if _sys_is_dark and not _sys_is_dark() and _light_tree_qss:
        tv.setStyleSheet(_light_tree_qss)
    model = QStandardItemModel(0, 2, tv)
    model.setHorizontalHeaderLabels(["Key", "Value"])
    tv.setModel(model)
    tv.setEditTriggers(QAbstractItemView.NoEditTriggers)
    tv.setSelectionBehavior(QAbstractItemView.SelectRows)
    tv.setSelectionMode(QAbstractItemView.ExtendedSelection)
    tv.setObjectName("url_picker_treeView")
    tv.header().setSectionResizeMode(0, QHeaderView.Interactive)
    tv.header().setSectionResizeMode(1, QHeaderView.Stretch)
    QTimer.singleShot(0, lambda: self._apply_saved_col_widths(tv))
    _tv_save_timer = QTimer(dlg)
    _tv_save_timer.setSingleShot(True)
    _tv_save_timer.timeout.connect(
        lambda: self._do_save_col_widths("url_picker_treeView", tv))
    tv.header().sectionResized.connect(
        lambda i, old, new: _tv_save_timer.start(500) if i >= 0 else None
    )

    root_item = QStandardItem(self._short_url_label(url))
    root_val = QStandardItem("")
    root_item.setEditable(False)
    root_val.setEditable(False)
    model.appendRow([root_item, root_val])
    self._add_json_to_qtree(root_item, root_val, j, path_prefix="")
    tv.expandAll()

    # Preview in PreviewFrame2
    preview_frame = ui2.PreviewFrame2
    if not preview_frame.layout():
        preview_frame.setLayout(QVBoxLayout())

    # Cancellation flag: set to True when the dialog closes so in-flight
    # fetch threads don't try to touch the destroyed preview_frame.
    _cancelled = [False]

    def _on_tree_sel_changed(*_):
        if _cancelled[0]:
            return
        sel = tv.selectionModel()
        idxs = sel.selectedRows(0) if sel else []
        if not idxs:
            return
        it = model.itemFromIndex(idxs[0])
        if not it:
            return
        row = it.row()
        parent_item = it.parent()
        val_item = parent_item.child(
            row, 1) if parent_item else model.item(row, 1)
        val_text = str(val_item.text() or "").strip() if val_item else ""

        # Try integer asset ID first
        try:
            asset_id = int(val_text)

            def _fetch(aid=asset_id, pid=place_id):
                try:
                    cookie = get_roblosecurity()
                    sess = self._new_session(cookie)

                    extra_headers = {
                        "X-Preview-Bypass": "1",
                        "User-Agent": "Roblox/WinInetRobloxApp",
                        "Roblox-Play-Session-Id": str(uuid.uuid4()),
                        "Roblox-Game-Id": str(uuid.uuid4()),
                    }
                    if pid:
                        extra_headers["Roblox-Place-Id"] = str(pid)
                        try:
                            uid_resp = sess.get(
                                f"https://apis.roblox.com/universes/v1/places/{pid}/universe",
                                timeout=8,
                                verify=False,
                            )
                            if uid_resp.ok:
                                uid = uid_resp.json().get("universeId")
                                if uid:
                                    extra_headers["Roblox-Universe-Id"] = str(
                                        uid)
                        except Exception as e:
                            print(
                                f"[PRESET PREVIEW] Universe ID lookup failed for place {pid}: {e}")

                    batch_resp = sess.post(
                        "https://assetdelivery.roblox.com/v2/assets/batch",
                        json=[{"assetId": aid, "requestId": "0", "assetTypeId": 0}],
                        timeout=15,
                        verify=False,
                        headers=extra_headers,
                    )
                    if not batch_resp.ok:
                        print(
                            f"[PRESET PREVIEW] Batch request for asset {aid} returned HTTP {batch_resp.status_code}")
                        return
                    batch_data = batch_resp.json()
                    _loc = batch_location(batch_data[0]) if isinstance(batch_data, list) and batch_data else ""
                    if not _loc:
                        print(
                            f"[PRESET PREVIEW] No location in batch response for asset {aid}")
                        return
                    resp = sess.get(
                        _loc,
                        timeout=15,
                        verify=False,
                        headers=extra_headers,
                    )
                    if not resp.ok:
                        print(
                            f"[PRESET PREVIEW] Asset CDN fetch for {aid} returned HTTP {resp.status_code}")
                        return
                    data = resp.content

                    def _show(d=data, aid=aid):
                        if _cancelled[0] or not isValid(preview_frame):
                            return
                        self.display_preview_enhanced(
                            d, 0, aid, str(aid), preview_frame)
                    self._on_main(_show)
                except Exception as e:
                    print(f"[PRESET PREVIEW] Failed to fetch asset {aid}: {e}")

            threading.Thread(target=_fetch, daemon=True).start()
            return
        except (ValueError, TypeError):
            pass

        # Fall back to URL preview (GitHub links or any https URL)
        if val_text.startswith(("http://", "https://")):
            raw_url = github_blob_to_raw_url(val_text)

            def _fetch_url(u=raw_url, label=val_text):
                try:
                    resp = self.net.get(u, timeout=15, verify=False)
                    if not resp.ok:
                        return
                    data = resp.content

                    def _show(d=data, label=label):
                        if _cancelled[0] or not isValid(preview_frame):
                            return
                        self.display_preview_enhanced(
                            d, 0, 0, label, preview_frame)
                    self._on_main(_show)
                except Exception as e:
                    print(f"[PRESET PREVIEW] Failed to fetch URL {u}: {e}")

            threading.Thread(target=_fetch_url, daemon=True).start()

    tv.selectionModel().selectionChanged.connect(_on_tree_sel_changed)

    def collect_ids(item):
        ids = []
        row = item.row()
        parent = item.parent()
        val_item = parent.child(row, 1) if parent else model.item(row, 1)
        if val_item:
            val_text = str(val_item.text() or "")
            if target == "replace" and val_text.startswith(("http://", "https://")):
                ids.append(github_blob_to_raw_url(val_text))
            else:
                ids += re.findall(r"\d+", val_text)
        for r in range(item.rowCount()):
            ch = item.child(r, 0)
            if ch:
                ids += collect_ids(ch)
        return ids

    def on_import():
        sel = tv.selectionModel()
        if not sel:
            return
        ids = []
        for idx in sel.selectedRows(0):
            it = model.itemFromIndex(idx)
            if it:
                ids += collect_ids(it)
        seen = set()
        out = [x for x in ids if not (x in seen or seen.add(x))]
        if target == "use":
            le = getattr(self, "replace_ids_lineedit", None)
        else:
            le = getattr(self, "replace_with_lineedit", None)
        if le:
            le.setText(",".join(out))
        dlg.accept()

    ui2.pushButton.clicked.connect(on_import)

    # Close any active preview before the dialog (and its widgets) are destroyed,
    # so AnimGLWidget GL cleanup happens while the context is still valid.
    # Also set the cancellation flag so any in-flight fetch threads know to drop
    # their result rather than posting to the now-dead preview_frame.
    def _on_dlg_close(_):
        _cancelled[0] = True

        # Bump gen so every in-flight background thread (mesh convert,
        # animation preload, etc.) sees a stale gen and drops its _on_main
        # callback instead of touching the widgets that are about to be
        # destroyed with the dialog.
        if hasattr(self, "_frame_preview_gen"):
            self._frame_preview_gen[preview_frame] = (
                self._frame_preview_gen.get(preview_frame, 0) + 1
            )

        try:
            tv.selectionModel().selectionChanged.disconnect(_on_tree_sel_changed)
        except Exception:
            pass

        # Stop the animation timer BEFORE Qt destroys the child widgets.
        # Do NOT call the full close_preview() here — it calls setParent(None)
        # + deleteLater on GL widgets that Qt is already about to destroy as
        # part of the dialog teardown, which causes a double-destroy crash.
        _state = getattr(self, "_preview_state", {}).get(preview_frame, {})
        anim_viewer = _state.get("anim_viewer")
        if anim_viewer is not None:
            try:
                anim_viewer.timer.stop()
            except Exception:
                pass

        # Stop any audio playing in this frame.
        if preview_frame in getattr(self, "audio_players", {}):
            try:
                self.audio_players[preview_frame].stop()
            except Exception:
                pass
            self.audio_players.pop(preview_frame, None)

        # Drop state refs so stale _on_main callbacks can't pick up widgets.
        if hasattr(self, "_preview_state"):
            self._preview_state.pop(preview_frame, None)
        if hasattr(self, "_preview_token"):
            self._preview_token.pop(preview_frame, None)

    dlg.finished.connect(_on_dlg_close)

    # Apply light mode if active
    _main_mod = sys.modules.get('__main__')
    _apply_light = getattr(_main_mod, 'apply_light_to_mainwindow', None)
    if _apply_light:
        _apply_light(dlg)

    dlg.show()


def _coerce_game_dump(data):
    """Wrap a single-game dict in a list so _normalize_games_from_clog treats it
    as one entry instead of creating one entry per top-level key.

    A dict is considered a single-game entry when it has "name" as a plain string
    or "placeId" as a scalar value, and has no "games" wrapper key.
    """
    if (
        isinstance(data, dict)
        and "games" not in data
        and (
            isinstance(data.get("name"), str)
            or (
                data.get("placeId") is not None
                and not isinstance(data.get("placeId"), dict)
            )
        )
    ):
        return [data]
    return data


def _custom_dumps_dir(self) -> Path:
    base = os.environ.get("LOCALAPPDATA") or str(
        Path.home() / "AppData" / "Local")
    d = Path(base) / "SubplaceJoiner" / "custom_dumps"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _load_custom_game_entries(self) -> list:
    """Return (game_entry, file_path) tuples from all saved custom dump files."""
    import re as _re
    _uuid_only = _re.compile(r'^[0-9a-f]{32}\.json$')
    entries = []
    try:
        for fp in sorted(_custom_dumps_dir(self).glob("*.json")):
            if not _uuid_only.match(fp.name):
                continue  # skip copied asset/replacement files
            try:
                data = json.loads(fp.read_text(
                    encoding="utf-8", errors="ignore"))
                games = self._normalize_games_from_clog(
                    _coerce_game_dump(data))
                for g in games:
                    entries.append((g, fp))
            except Exception as e:
                print(f"[CustomDump] Failed to load {fp.name}: {e}")
    except Exception as e:
        print(f"[CustomDump] Failed to scan custom_dumps dir: {e}")
    return entries


def _add_game_card_from_entry(self, g: dict, dump_file=None):
    """Create a GameCardWidget from a normalized game entry and append it to _preset_cards.

    Pass dump_file (Path) for custom-imported cards — enables right-click delete.
    """
    created = g.get("created", "")
    updated = g.get("updated", "")
    place_id = g.get("placeId") or g.get("place_id")
    try:
        place_id = int(place_id) if place_id is not None else None
    except Exception:
        place_id = None

    initial_name = g.get("name") or (
        f"Place {place_id}" if place_id else "Unknown")

    card = GameCardWidget(self.presets_container)
    card.set_data(name=initial_name, created=created, updated=updated)
    card._game_name = initial_name
    card._place_id = place_id

    gh_url = g.get("github")
    rep_url = g.get("replacement")

    if isinstance(gh_url, str) and gh_url.strip():
        card.ui.joinButton.setText("Assets")
        card.ui.joinButton.setVisible(True)
        card.on_join(lambda _=False, u=gh_url.strip(), pid=place_id:
                     self._open_url_picker(u, "use", pid))
    else:
        card.ui.joinButton.setVisible(False)

    if isinstance(rep_url, str) and rep_url.strip():
        card.ui.openButton.setText("Replacements")
        card.ui.openButton.setVisible(True)
        card.on_open(lambda _=False, u=rep_url.strip(), pid=place_id:
                     self._open_url_picker(u, "replace", pid))
    else:
        card.ui.openButton.setVisible(False)

    card.setMinimumWidth(0)
    card.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

    # Custom-imported cards get a file reference and a right-click delete menu
    if dump_file is not None:
        card._custom_dump_file = str(dump_file)
        card.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        card.customContextMenuRequested.connect(
            lambda pos, c=card: _custom_card_context_menu(self, c, pos)
        )

    self._preset_cards.append(card)

    if place_id:
        def worker(pid=place_id, c=card, cr=created, up=updated):
            real_name = None
            real_cr = cr
            real_up = up
            pix = None
            try:
                real_name, api_cr, api_up = self._get_game_name_from_placeid(
                    pid)
                if api_cr:
                    real_cr = api_cr
                if api_up:
                    real_up = api_up
            except Exception as e:
                print(f"[GAME META] name fetch failed for {pid}: {e}")
            try:
                pix = self._fetch_place_icon_pixmap(pid)
            except Exception as e:
                print(f"[THUMB] fetch failed for {pid}: {e}")

            def apply():
                if real_name:
                    c.set_data(name=real_name, created=real_cr,
                               updated=real_up)
                    c._game_name = real_name
                if pix:
                    try:
                        c.set_thumbnail(pix)
                    except Exception:
                        pass

            self._on_main(apply)

        threading.Thread(target=worker, daemon=True).start()


def _custom_card_context_menu(self, card, pos):
    """Show a right-click context menu for a custom-imported card."""
    menu = QMenu(card)
    delete_action = menu.addAction("Delete")
    action = menu.exec(card.mapToGlobal(pos))
    if action == delete_action:
        _delete_custom_dump_card(self, card)


def _delete_custom_dump_card(self, card):
    """Remove a custom dump card from the grid and delete its backing file."""
    dump_file = getattr(card, "_custom_dump_file", None)
    if dump_file:
        try:
            Path(dump_file).unlink(missing_ok=True)
        except Exception as e:
            print(f"[CustomDump] Failed to delete file {dump_file}: {e}")

    if card in self._preset_cards:
        self._preset_cards.remove(card)
    fc = getattr(self, "_preset_filtered_cards", None)
    if fc and card in fc:
        fc.remove(card)

    try:
        self.presets_grid.removeWidget(card)
        card.setParent(None)
        card.deleteLater()
    except Exception:
        pass

    self._relayout_preset_cards()


def _open_add_game_dump_dialog(self):
    """Open a dialog to import a custom game dump (form or JSON URL/file)."""
    from PySide6.QtWidgets import QMessageBox

    parent = getattr(self, "_presets_dialog", None) or self.tab_widget
    dlg = QDialog(parent)
    dlg.setWindowTitle(
        "Import custom game dump (MAKE SURE ITS FORMATTED CORRECTLY!!!)"
    )
    dlg.setMinimumWidth(520)

    layout = QVBoxLayout(dlg)
    layout.setSpacing(6)
    layout.setContentsMargins(12, 12, 12, 12)

    # Example format
    layout.addWidget(QLabel("Expected JSON format:"))
    example_box = QTextEdit()
    example_box.setReadOnly(True)
    example_box.setMaximumHeight(130)
    example_box.setStyleSheet(
        "font-family: 'Courier New', monospace; font-size: 9pt;")
    example_box.setPlainText(
        '{\n'
        '  "name": "My Game",\n'
        '  "placeId": 12345,\n'
        '  "github": "https://raw.githubusercontent.com/qrhrqiohj/PFTEST/refs/heads/main/Replacements.json",\n'
        '  "replacement": "https://raw.githubusercontent.com/qrhrqiohj/PFTEST/refs/heads/main/Replacements.json"\n'
        '}'
    )
    layout.addWidget(example_box)

    # Manual form
    sep1 = QFrame()
    sep1.setFrameShape(QFrame.Shape.HLine)
    sep1.setFrameShadow(QFrame.Shadow.Sunken)
    layout.addWidget(sep1)
    layout.addWidget(QLabel("Fill in manually:"))

    layout.addWidget(QLabel("Name:"))
    name_edit = QLineEdit()
    name_edit.setPlaceholderText("My Game")
    layout.addWidget(name_edit)

    layout.addWidget(
        QLabel("Place ID (optional — fetches real name automatically):"))
    placeid_edit = QLineEdit()
    placeid_edit.setPlaceholderText("12345")
    layout.addWidget(placeid_edit)

    layout.addWidget(QLabel("Assets URL (github):"))
    assets_row = QHBoxLayout()
    assets_edit = QLineEdit()
    assets_edit.setPlaceholderText(
        "https://raw.githubusercontent.com/qrhrqiohj/PFTEST/refs/heads/main/Replacements.json"
    )
    assets_row.addWidget(assets_edit)
    assets_file_btn = QPushButton("Browse...")
    assets_file_btn.setFixedWidth(80)
    assets_row.addWidget(assets_file_btn)
    layout.addLayout(assets_row)

    def pick_assets_file():
        path, _ = QFileDialog.getOpenFileName(
            dlg, "Select Assets JSON file", "",
            "JSON Files (*.json);;All Files (*)"
        )
        if path:
            assets_edit.setText(path)

    assets_file_btn.clicked.connect(pick_assets_file)

    layout.addWidget(QLabel("Replacements URL (replacement):"))
    replacements_row = QHBoxLayout()
    replacements_edit = QLineEdit()
    replacements_edit.setPlaceholderText(
        "https://raw.githubusercontent.com/qrhrqiohj/PFTEST/refs/heads/main/Replacements.json"
    )
    replacements_row.addWidget(replacements_edit)
    replacements_file_btn = QPushButton("Browse...")
    replacements_file_btn.setFixedWidth(80)
    replacements_row.addWidget(replacements_file_btn)
    layout.addLayout(replacements_row)

    def pick_replacements_file():
        path, _ = QFileDialog.getOpenFileName(
            dlg, "Select Replacements JSON file", "",
            "JSON Files (*.json);;All Files (*)"
        )
        if path:
            replacements_edit.setText(path)

    replacements_file_btn.clicked.connect(pick_replacements_file)

    # OR import from URL/file
    sep2 = QFrame()
    sep2.setFrameShape(QFrame.Shape.HLine)
    sep2.setFrameShadow(QFrame.Shadow.Sunken)
    layout.addWidget(sep2)
    layout.addWidget(QLabel("OR import from URL / file:"))

    url_edit = QLineEdit()
    url_edit.setPlaceholderText(
        "https://raw.githubusercontent.com/.../dump.json")
    layout.addWidget(url_edit)

    file_btn = QPushButton("Import from file...")
    layout.addWidget(file_btn)

    # Buttons
    btn_row = QHBoxLayout()
    ok_btn = QPushButton("Import")
    cancel_btn = QPushButton("Cancel")
    btn_row.addStretch()
    btn_row.addWidget(ok_btn)
    btn_row.addWidget(cancel_btn)
    layout.addLayout(btn_row)

    def pick_file():
        path, _ = QFileDialog.getOpenFileName(
            dlg, "Select JSON game dump", "",
            "JSON Files (*.json);;All Files (*)"
        )
        if path:
            url_edit.setText(path)

    file_btn.clicked.connect(pick_file)
    cancel_btn.clicked.connect(dlg.reject)

    def do_import():
        name_text = name_edit.text().strip()
        placeid_text = placeid_edit.text().strip()
        source_file = None

        if name_text or placeid_text:
            # Build data from form fields
            # Name falls back to "Place {id}" if only placeId was given;
            # _add_game_card_from_entry will overwrite with the real Roblox name.
            data = {"name": name_text or (
                f"Place {placeid_text}" if placeid_text else "Unknown")}
            if placeid_text:
                try:
                    data["placeId"] = int(placeid_text)
                except ValueError:
                    pass
            if assets_edit.text().strip():
                _av = assets_edit.text().strip()
                if os.path.isfile(_av):
                    _ac = _custom_dumps_dir(
                        self) / f"{uuid.uuid4().hex}_{Path(_av).name}"
                    shutil.copy2(_av, _ac)
                    _av = str(_ac)
                data["github"] = _av
            if replacements_edit.text().strip():
                _rv = replacements_edit.text().strip()
                if os.path.isfile(_rv):
                    _rc = _custom_dumps_dir(
                        self) / f"{uuid.uuid4().hex}_{Path(_rv).name}"
                    shutil.copy2(_rv, _rc)
                    _rv = str(_rc)
                data["replacement"] = _rv
        else:
            # Fall back to URL/file
            url_text = url_edit.text().strip()
            if not url_text:
                QMessageBox.warning(
                    dlg, "Import failed",
                    "Fill in the Name field, or provide a URL / file path."
                )
                return

            data = None
            source_file = None
            if os.path.isfile(url_text):
                try:
                    data = json.loads(
                        Path(url_text).read_text(
                            encoding="utf-8", errors="ignore")
                    )
                    source_file = url_text
                except Exception as e:
                    QMessageBox.warning(dlg, "Import failed",
                                        f"Could not read file:\n{e}")
                    return
            elif url_text.startswith(("http://", "https://")):
                data = self._fetch_json_url(url_text)
                if data is None:
                    QMessageBox.warning(dlg, "Import failed",
                                        "Could not fetch or parse JSON from URL.")
                    return
            else:
                QMessageBox.warning(
                    dlg, "Import failed",
                    "Enter a URL (http/https) or a path to a local JSON file."
                )
                return

        # Persist to %LOCALAPPDATA%\SubplaceJoiner\custom_dumps\<uuid>.json
        dump_path = _custom_dumps_dir(self) / f"{uuid.uuid4().hex}.json"
        try:
            if source_file is not None:
                shutil.copy2(source_file, dump_path)
            else:
                dump_path.write_text(json.dumps(
                    data, indent=2), encoding="utf-8")
        except Exception as e:
            QMessageBox.warning(dlg, "Import failed",
                                f"Could not save dump to disk:\n{e}")
            return

        games = self._normalize_games_from_clog(_coerce_game_dump(data))

        if not games:
            QMessageBox.warning(
                dlg, "Import failed",
                "No valid game entries found.\n"
                "Make sure the file is formatted correctly."
            )
            try:
                dump_path.unlink()
            except Exception:
                pass
            return

        for g in games:
            _add_game_card_from_entry(self, g, dump_file=dump_path)

        self._relayout_preset_cards()
        dlg.accept()

    ok_btn.clicked.connect(do_import)
    url_edit.returnPressed.connect(do_import)

    _main_mod = sys.modules.get("__main__")
    _apply_light = getattr(_main_mod, "apply_light_to_mainwindow", None)
    if _apply_light:
        _apply_light(dlg)

    dlg.exec()


# Filter menu
