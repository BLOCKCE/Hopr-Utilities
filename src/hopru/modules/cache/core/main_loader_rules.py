"""Cache loader rules — persistence, table setup, and rule management."""

from ui.presetsthing import Ui_Form as PresetsThingUI
from widgets.game_card_widget import GameCardWidget
from ui.dialog6_ui import Ui_Dialog as Dialog6UI
from ui.dialog5_ui import Ui_Dialog as Dialog5UI
from ui.dialog4_ui import Ui_Dialog as Dialog4UI
from ui.dialog3_ui import Ui_Dialog as Dialog3UI
from ui.dialog2_ui import Ui_Dialog as Dialog2UI
from ui.dialog1_ui import Ui_Dialog as Dialog1UI
from PySide6.QtCore import QFile, QSortFilterProxyModel, QRect
from PySide6.QtUiTools import QUiLoader
from PySide6.QtWidgets import (
    QTreeView, QTableView, QWidget, QDialog, QPushButton, QHBoxLayout, QGridLayout, QSizePolicy, QLineEdit,
    QMenu, QAbstractItemView, QHeaderView, QStyledItemDelegate, QApplication, QLabel, QSlider, QFrame, QVBoxLayout,
    QTextEdit, QFileDialog, QSplitter, QWidgetAction, QStyle, QStyleOptionMenuItem
)
from PySide6.QtGui import QStandardItemModel, QStandardItem, QPixmap, QPainter, QGuiApplication, QPalette
from PySide6.QtCore import Qt, QObject, QEvent, QPersistentModelIndex, QTimer, QUrl, Signal
import os
import gzip
import sys
import tempfile
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
try:
    from mitmproxy import http
except Exception:
    http = None


from shared.constants import CLOG_RAW_URL, ASSET_TYPES, adapter
from shared.utils import strip_cache_header, get_roblosecurity, isnumeric, github_blob_to_raw_url
from shared.models import SortProxy
from shared.delegates import NoFocusDelegate
from shared.ui_loader import load_ui
from shared.audio_player import AudioPlayer
from shared.menu_utils import StayOpenMenu
from shared.threading_utils import _MainThreadInvoker


def _loader_rules_path(self) -> Path:
    base = os.environ.get("LOCALAPPDATA")
    if not base:
        base = str(Path.home() / "AppData" / "Local")
    root = Path(base) / "SubplaceJoiner"
    root.mkdir(parents=True, exist_ok=True)
    return root / "cache_loader_rules.json"


def _write_data_file(self, *, sources=None, presets=None, enabled_sources="__unset__"):
    """Read the data file, update only the provided keys, and write it back.
    This preserves keys not being updated (e.g. sources won't erase presets)."""
    path = self._loader_rules_path()
    try:
        full = json.loads(path.read_text(encoding="utf-8",
                          errors="ignore")) if path.exists() else {}
        if not isinstance(full, dict) or full.get("version", 1) == 1:
            full = {}
    except Exception:
        full = {}
    full["version"] = 2
    if sources is not None:
        full["sources"] = sources
    if presets is not None:
        full["presets"] = presets
    if enabled_sources != "__unset__":
        if enabled_sources is None:
            full.pop("enabled_sources", None)  # None = all enabled, remove key
        else:
            full["enabled_sources"] = list(enabled_sources)
    path.write_text(json.dumps(full, indent=2), encoding="utf-8")


def _save_column_widths(self, view_key: str, widths: dict):
    path = self._loader_rules_path()
    try:
        full = json.loads(path.read_text(encoding="utf-8",
                          errors="ignore")) if path.exists() else {}
        if not isinstance(full, dict):
            full = {}
    except Exception:
        full = {}
    col_widths = full.get("column_widths", {})
    col_widths[view_key] = {str(k): v for k, v in widths.items()}
    full["column_widths"] = col_widths
    path.write_text(json.dumps(full, indent=2), encoding="utf-8")


def _load_column_widths(self, view_key: str) -> dict:
    path = self._loader_rules_path()
    if not path.exists():
        return {}
    try:
        full = json.loads(path.read_text(encoding="utf-8", errors="ignore"))
        if not isinstance(full, dict):
            return {}
        saved = full.get("column_widths", {}).get(view_key, {})
        return {int(k): v for k, v in saved.items()}
    except Exception:
        return {}


def _apply_saved_col_widths(self, view):
    view_key = view.objectName() or str(id(view))
    saved = self._load_column_widths(view_key)
    for col, width in saved.items():
        view.setColumnWidth(col, width)


def _do_save_col_widths(self, view_key: str, view):
    try:
        if isinstance(view, QTreeView):
            h = view.header()
        else:
            h = view.horizontalHeader()
        widths = {i: h.sectionSize(i) for i in range(h.count())}
        self._save_column_widths(view_key, widths)
    except Exception as e:
        print(f"[col widths] save failed: {e}")


def _load_all_sources(self) -> dict:
    """Load the full {source_name: [rules]} dict from disk, migrating v1 if needed."""
    path = self._loader_rules_path()
    if not path.exists():
        return {"Default": []}
    try:
        payload = json.loads(path.read_text(encoding="utf-8", errors="ignore"))
        if isinstance(payload, dict):
            if payload.get("version", 1) == 1:
                return {"Default": payload.get("rules", [])}
            sources = payload.get("sources", {})
            if isinstance(sources, dict) and sources:
                return sources
    except Exception:
        pass
    return {"Default": []}


def _snapshot_rules(self) -> list:
    """Return current model state as a list of rule dicts (same format as disk)."""
    rules = []
    for row in range(self.loader_model.rowCount()):
        on_item = self.loader_model.item(row, 0)
        name_item = self.loader_model.item(row, 1)
        use_item = self.loader_model.item(row, 2)
        rep_item = self.loader_model.item(row, 3)
        enabled = bool(on_item and on_item.checkState() == Qt.Checked)
        name = name_item.text() if name_item else ""
        replace_text = (rep_item.data(Qt.UserRole + 1) if rep_item else "") or (rep_item.text() if rep_item else "")
        meta = use_item.data(Qt.UserRole + 1) if use_item else None
        if not isinstance(meta, dict):
            meta = {"mode": "inline_text", "value": (
                use_item.text() if use_item else "")}
        rules.append({"enabled": enabled, "name": name,
                     "use": meta, "replace": replace_text})
    return rules


def _push_source_snapshot(self):
    """Push the current full sources state onto the undo stack (for create/delete source undo)."""
    all_sources = self._load_all_sources()
    current = getattr(self, "_current_source_name", "Default")
    undo_stack = getattr(self, "_undo_stack", [])
    undo_stack.append(
        {"type": "sources", "all_sources": all_sources, "current": current})
    if len(undo_stack) > 50:
        undo_stack.pop(0)
    self._undo_stack = undo_stack


def _undo_loader(self):
    """Restore the previous loader rules / sources state (Ctrl+Z)."""
    from PySide6.QtWidgets import QApplication, QLineEdit
    focused = QApplication.focusWidget()
    if isinstance(focused, QLineEdit):
        return
    undo_stack = getattr(self, "_undo_stack", [])
    if not undo_stack:
        return
    entry = undo_stack.pop()
    self._undo_stack = undo_stack

    if isinstance(entry, dict) and entry.get("type") == "sources":
        all_sources = entry["all_sources"]
        current = entry["current"]
        self._write_data_file(sources=all_sources)
        cb = getattr(self, "sources_combo", None)
        if cb is not None:
            cb.blockSignals(True)
            cb.clear()
            for sname in all_sources:
                cb.addItem(sname)
            if current in all_sources:
                cb.setCurrentText(current)
            cb.blockSignals(False)
        self._current_source_name = current if current in all_sources else (
            cb.currentText() if cb else "Default")
        self._load_source_rules(all_sources.get(self._current_source_name, []))
        return

    # rules entry — may be {"type": "rules", "rules": [...]} or a bare list (legacy)
    rules = entry.get("rules", entry) if isinstance(entry, dict) else entry
    self._undoing = True
    try:
        self._load_source_rules(rules)
        current = getattr(self, "_current_source_name", "Default")
        all_sources = self._load_all_sources()
        all_sources[current] = rules
        self._write_data_file(sources=all_sources)
    finally:
        self._undoing = False


def _save_loader_rules(self):
    if getattr(self, "_loading_loader_rules", False):
        return
    try:
        rules = []
        for row in range(self.loader_model.rowCount()):
            on_item = self.loader_model.item(row, 0)
            name_item = self.loader_model.item(row, 1)
            use_item = self.loader_model.item(row, 2)
            rep_item = self.loader_model.item(row, 3)

            enabled = bool(on_item and on_item.checkState() == Qt.Checked)
            name = name_item.text() if name_item else ""
            replace_text = (rep_item.data(Qt.UserRole + 1) if rep_item else "") or (rep_item.text() if rep_item else "")

            meta = use_item.data(Qt.UserRole + 1) if use_item else None
            if not isinstance(meta, dict):
                meta = {"mode": "inline_text", "value": (
                    use_item.text() if use_item else "")}

            rules.append({
                "enabled": enabled,
                "name": name,
                "use": meta,
                "replace": replace_text,
            })

        if not getattr(self, "_undoing", False):
            prev = getattr(self, "_last_saved_rules", None)
            if prev is not None:
                undo_stack = getattr(self, "_undo_stack", [])
                undo_stack.append({"type": "rules", "rules": prev})
                if len(undo_stack) > 50:
                    undo_stack.pop(0)
                self._undo_stack = undo_stack
        self._last_saved_rules = rules

        current = getattr(self, "_current_source_name", "Default")
        all_sources = self._load_all_sources()
        all_sources[current] = rules
        self._write_data_file(sources=all_sources)
    except Exception as e:
        print(f"Failed to save loader rules: {e}")


def _clear_loader_rules(self):
    self.loader_model.removeRows(0, self.loader_model.rowCount())


def _load_loader_rules(self):
    """Initial load: populate SourcesComboBox and load the first source's rules."""
    all_sources = self._load_all_sources()

    cb = getattr(self, "sources_combo", None)
    if cb is not None:
        cb.blockSignals(True)
        cb.clear()
        for name in all_sources:
            cb.addItem(name)
        if cb.count() == 0:
            cb.addItem("Default")
        cb.setCurrentIndex(0)
        cb.blockSignals(False)
        source_name = cb.currentText()
    else:
        source_name = "Default"

    self._current_source_name = source_name
    self._load_source_rules(all_sources.get(source_name, []))


def _load_source_rules(self, rules: list):
    """Clear the model and populate it with a given list of rule dicts."""
    try:
        self._loading_loader_rules = True
        self._clear_loader_rules()
        for r in rules:
            enabled = bool(r.get("enabled", True))
            name = str(r.get("name", ""))
            replace_text = self._resolve_replace_field(
                str(r.get("replace", "")))

            use_meta = r.get("use", {})
            if isinstance(use_meta, str):
                use_meta = {"mode": "inline_text", "value": use_meta}

            display_use = ""
            if isinstance(use_meta, dict):
                mode = use_meta.get("mode")
                if mode == "assetId":
                    display_use = str(use_meta.get("value", ""))
                elif "source" in use_meta:
                    display_use = Path(use_meta['source']).name
                elif mode == "inline_b64":
                    val = str(use_meta.get("value", ""))
                    display_use = val[:10] + "…" if len(val) > 10 else val
                else:
                    display_use = str(use_meta.get("value", ""))

            display_replace = replace_text[:10] + "…" if len(replace_text) > 10 else replace_text

            on_item = QStandardItem()
            on_item.setFlags(Qt.ItemIsEnabled |
                             Qt.ItemIsSelectable | Qt.ItemIsUserCheckable)
            on_item.setCheckable(True)
            on_item.setCheckState(Qt.Checked if enabled else Qt.Unchecked)

            name_item = QStandardItem(name)
            from_item = QStandardItem(display_use)
            to_item = QStandardItem(display_replace)
            to_item.setData(replace_text, Qt.UserRole + 1)

            from_item.setData(use_meta, Qt.UserRole + 1)

            for it in (name_item, from_item, to_item):
                it.setEditable(False)

            self.loader_model.appendRow(
                [on_item, name_item, from_item, to_item])
    except Exception as e:
        print(f"Failed to load source rules: {e}")
    finally:
        self._loading_loader_rules = False
    self._last_saved_rules = self._snapshot_rules()
    self._rebuild_loader_index()


_WAVE_BATCH = 2000      # rows per wave — large enough to be visually distinct
_WAVE_INTERVAL_MS = 3000  # ms between waves — long enough to see each chunk land


def add_row(self, name, asset_id, type_name, size_text, size_bytes, date_text, date_sort, creator_name=""):
    # Buffer the row data; a background sort + wave-insert is triggered once.
    if not hasattr(self, "_pending_finder_rows"):
        self._pending_finder_rows = []
    self._pending_finder_rows.append(
        (name, asset_id, type_name, size_text,
         size_bytes, date_text, date_sort, creator_name)
    )
    if not getattr(self, "_finder_flush_scheduled", False):
        self._finder_flush_scheduled = True
        self._on_main(lambda: _kick_finder_sort(self))


def _kick_finder_sort(self):
    """Grab all pending rows, sort them on a bg thread, then wave-insert."""
    rows = getattr(self, "_pending_finder_rows", [])
    self._pending_finder_rows = []
    self._finder_flush_scheduled = False

    if not rows:
        return

    # Read sort params here on the main thread — Qt objects must not be
    # accessed from the background thread.
    sort_col = self.proxy.sortColumn()
    sort_asc = self.proxy.sortOrder() == Qt.AscendingOrder

    def _bg():
        # Tuple layout: (name, asset_id, type_name, size_text,
        # size_bytes, date_text, date_sort, creator_name)
        _COL_KEYS = [
            lambda r: str(r[0]).lower(),                          # 0 Name
            lambda r: int(r[1]),                                  # 1 Asset ID
            lambda r: str(r[7]).lower(),                          # 2 Creator
            lambda r: str(r[2]).lower(),                          # 3 Type
            lambda r: (r[4] if r[4] is not None else 0),         # 4 Size
            lambda r: (r[6] if r[6] is not None else 0),         # 5 Date
        ]
        key_fn = _COL_KEYS[sort_col] if 0 <= sort_col < len(
            _COL_KEYS) else _COL_KEYS[5]
        sorted_rows = sorted(rows, key=key_fn, reverse=not sort_asc)
        self._on_main(lambda: _start_wave_insert(self, sorted_rows))

    threading.Thread(target=_bg, daemon=True).start()


def _start_wave_insert(self, sorted_rows):
    if not sorted_rows:
        return

    # If a wave is already running just extend its queue.
    existing = getattr(self, "_wave_queue", None)
    if existing is not None:
        existing.extend(sorted_rows)
        return

    self._wave_queue = list(sorted_rows)

    timer = QTimer()
    timer.setSingleShot(False)
    self._wave_timer = timer

    def _wave():
        q = self._wave_queue
        if not q:
            timer.stop()
            self._wave_timer = None
            self._wave_queue = None
            self._finder_programmatic_selection = True
            try:
                self.proxy.invalidate()
            finally:
                QTimer.singleShot(0, lambda: setattr(
                    self, '_finder_programmatic_selection', False))
            lbl = getattr(self, "info_label", None)
            if lbl is not None:
                lbl.setText(f"Caches in cache finder: {self.model.rowCount()}")
            return

        batch = q[:_WAVE_BATCH]
        del q[:_WAVE_BATCH]

        # Block model signals so the proxy doesn't process a rowsInserted
        # for every single appendRow — it will get one invalidate() at the end.
        self.model.blockSignals(True)
        try:
            for name, asset_id, type_name, size_text, size_bytes, date_text, date_sort, creator_name in batch:
                row = self.model.rowCount()
                items = [
                    QStandardItem(name),
                    QStandardItem(str(asset_id)),
                    QStandardItem(creator_name),
                    QStandardItem(type_name),
                    QStandardItem(size_text),
                    QStandardItem(date_text),
                ]
                items[4].setData(size_bytes, Qt.UserRole)
                items[5].setData(date_sort, Qt.UserRole)
                items[1].setData(int(asset_id), Qt.UserRole)
                items[3].setData(
                    self.cache_logs.get(asset_id, {}).get("assetTypeId"),
                    Qt.UserRole,
                )
                self.model.appendRow(items)
                if asset_id in self.cache_logs:
                    self.cache_logs[asset_id]["name_index"] = QPersistentModelIndex(
                        self.model.index(row, 0)
                    )
                    self.cache_logs[asset_id]["creator_index"] = QPersistentModelIndex(
                        self.model.index(row, 2)
                    )
        finally:
            self.model.blockSignals(False)

        self._finder_programmatic_selection = True
        try:
            self.proxy.invalidate()
        finally:
            QTimer.singleShot(0, lambda: setattr(
                self, '_finder_programmatic_selection', False))

        lbl = getattr(self, "info_label", None)
        if lbl is not None:
            lbl.setText(f"Caches in cache finder: {self.model.rowCount()}")

    timer.timeout.connect(_wave)
    timer.start(_WAVE_INTERVAL_MS)
    _wave()  # fire first wave immediately


def _flush_finder_rows(self):
    rows = getattr(self, "_pending_finder_rows", [])
    self._pending_finder_rows = []
    self._finder_flush_scheduled = False

    # Stop any in-progress wave so it doesn't race with clear_all_rows.
    wt = getattr(self, "_wave_timer", None)
    if wt is not None:
        wt.stop()
        self._wave_timer = None
        self._wave_queue = None

    if not rows:
        return

    tv = getattr(self, "table_view", None)
    if tv is not None:
        tv.setUpdatesEnabled(False)
    try:
        for name, asset_id, type_name, size_text, size_bytes, date_text, date_sort, creator_name in rows:
            row = self.model.rowCount()
            items = [
                QStandardItem(name),
                QStandardItem(str(asset_id)),
                QStandardItem(creator_name),
                QStandardItem(type_name),
                QStandardItem(size_text),
                QStandardItem(date_text),
            ]
            items[4].setData(size_bytes, Qt.UserRole)
            items[5].setData(date_sort, Qt.UserRole)
            items[1].setData(int(asset_id), Qt.UserRole)
            items[3].setData(
                self.cache_logs.get(asset_id, {}).get("assetTypeId"),
                Qt.UserRole,
            )
            self.model.appendRow(items)
            if asset_id in self.cache_logs:
                self.cache_logs[asset_id]["name_index"] = QPersistentModelIndex(
                    self.model.index(row, 0)
                )
                self.cache_logs[asset_id]["creator_index"] = QPersistentModelIndex(
                    self.model.index(row, 2)
                )
    finally:
        if tv is not None:
            tv.setUpdatesEnabled(True)


def _schedule_proxy_sort(self):
    """Debounced proxy invalidate: fires 300 ms after the last call."""
    if not hasattr(self, "_proxy_sort_timer"):
        def _do_sort():
            self._finder_programmatic_selection = True
            try:
                self.proxy.invalidate()
            finally:
                QTimer.singleShot(0, lambda: setattr(
                    self, '_finder_programmatic_selection', False))
        t = QTimer()
        t.setSingleShot(True)
        t.timeout.connect(_do_sort)
        self._proxy_sort_timer = t
    self._proxy_sort_timer.start(300)


def _update_row_creator(self, asset_id, creator_name):
    info = self.cache_logs.get(asset_id)
    if not info:
        return
    idx = info.get("creator_index")
    if not idx or not idx.isValid():
        return
    self.model.setData(idx, creator_name)


def _update_row_name(self, asset_id, name):
    info = self.cache_logs.get(asset_id)
    if not info:
        return

    idx = info.get("name_index")
    if not idx or not idx.isValid():
        return

    self.model.setData(idx, name)


def _batch_update_row_names(self, updates: dict):
    """Apply a batch of name updates in one pass with view updates suppressed."""
    tv = getattr(self, "table_view", None)
    if tv is not None:
        tv.setUpdatesEnabled(False)
    try:
        for asset_id, name in updates.items():
            self._update_row_name(asset_id, name)
    finally:
        if tv is not None:
            tv.setUpdatesEnabled(True)


def _batch_update_row_creators(self, updates: dict):
    """Apply a batch of creator updates in one pass with view updates suppressed."""
    tv = getattr(self, "table_view", None)
    if tv is not None:
        tv.setUpdatesEnabled(False)
    try:
        for asset_id, creator_name in updates.items():
            self._update_row_creator(asset_id, creator_name)
    finally:
        if tv is not None:
            tv.setUpdatesEnabled(True)


def _setup_loader_table(self):
    tv = getattr(self, "loader_table", None)
    if tv is None:
        return
    self.loader_model = QStandardItemModel(0, 4, self.tab_widget)
    self.loader_model.setHorizontalHeaderLabels(
        ["On", "Name", "Use", "Replace"])
    self.loader_model.itemChanged.connect(
        lambda *_: (self._save_loader_rules(), self._rebuild_loader_index()))

    self.loader_proxy = SortProxy(self.tab_widget)
    self.loader_proxy.setSourceModel(self.loader_model)

    tv.setModel(self.loader_proxy)
    tv.setContextMenuPolicy(Qt.CustomContextMenu)
    tv.customContextMenuRequested.connect(self._show_loader_context_menu)
    tv.setSelectionBehavior(QAbstractItemView.SelectRows)
    tv.setSelectionMode(QAbstractItemView.ExtendedSelection)
    tv.setSortingEnabled(True)
    tv.verticalHeader().setVisible(False)
    tv.sortByColumn(1, Qt.AscendingOrder)

    header = tv.horizontalHeader()

    header.sectionResized.connect(
        lambda i, old, new, tv=self.loader_table: self._on_column_resized(
            i, old, new, tv)
    )

    # Match sizing/feel of finder
    tv.verticalHeader().setDefaultSectionSize(20)
    tv.horizontalHeader().setMinimumHeight(22)
    tv.horizontalHeader().setMaximumHeight(22)
    tv.horizontalHeader().setMinimumWidth(40)
    tv.horizontalHeader().setDefaultAlignment(Qt.AlignLeft | Qt.AlignVCenter)
    tv.horizontalHeader().setStretchLastSection(True)

    tv.setItemDelegate(NoFocusDelegate(tv))
    tv.viewport().installEventFilter(self)

    # Checkbox column width (overridden by saved widths if available)
    QTimer.singleShot(0, lambda: (
        tv.setColumnWidth(0, 50)
    ))
    QTimer.singleShot(
        0, lambda: self._apply_saved_col_widths(self.loader_table))

    # Load persisted cache loader rules (if any)
    self._load_loader_rules()


def _infer_content_type_from_name(self, filename_or_ext: str) -> str:
    ext = (Path(filename_or_ext).suffix or filename_or_ext or "").lower()
    content_types = {
        ".json": "application/json",
        ".xml": "application/xml",
        ".txt": "text/plain; charset=utf-8",
        ".lua": "text/plain; charset=utf-8",
        ".rbxm": "application/octet-stream",
        ".rbxmx": "application/xml",
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".gif": "image/gif",
        ".webp": "image/webp",
        ".ogg": "audio/ogg",
        ".mp3": "audio/mpeg",
        ".wav": "audio/wav",
    }
    return content_types.get(ext, "application/octet-stream")


def _resolve_use_field(self, raw: str):
    """Turns the 'Use' field into (display_text, meta_dict)."""
    raw = (raw or "").strip()
    if not raw:
        return "", {"mode": "inline_text", "value": "", "content_type": "text/plain; charset=utf-8"}

    if isnumeric(raw):
        return raw, {"mode": "assetId", "value": raw}

    if raw.startswith(("http://", "https://")):
        url = github_blob_to_raw_url(raw)
        try:
            import urllib3
            urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
            resp = requests.get(url, timeout=15, verify=False)
            resp.raise_for_status()
            data = resp.content
            path_part = url.split("?")[0]
            _last = path_part.rsplit("/", 1)[-1]
            ext = _last.rsplit(".", 1)[-1].lower() if "." in _last else ""
            ctype = {
                "png": "image/png", "jpg": "image/jpeg", "jpeg": "image/jpeg",
                "gif": "image/gif", "webp": "image/webp", "ogg": "audio/ogg",
                "mp3": "audio/mpeg", "wav": "audio/wav",
                "rbxm": "application/octet-stream", "rbxmx": "application/xml",
                "xml": "application/xml", "json": "application/json",
            }.get(ext, "application/octet-stream")
            b64 = base64.b64encode(data).decode("ascii")
            display = _last or url
            print(f"[URL fetch] Fetched {url} ({len(data)} bytes)")
            return display, {
                "mode": "inline_b64",
                "value": b64,
                "content_type": ctype,
                "source": url,
            }
        except Exception as e:
            print(f"[URL fetch] Failed to fetch {url}: {e}")
            # Fall back to lazy-fetch mode so it still works at runtime
            return url, {"mode": "url", "value": url}

    p = Path(raw)
    if p.exists() and p.is_file():
        # OBJ files are stored as raw OBJ text so the MITM can detect the
        # format at runtime and route to the correct converter based on the
        # target asset type:
        #   - SolidModel (type 39)  -> OBJ injected as CSGMDL into the CDN RBXM blob
        #   - Mesh / MeshPart (4, 40) -> converted to Roblox V2.00 binary mesh
        # Pre-converting here would lose the OBJ format and break both paths.
        if p.suffix.lower() == ".obj":
            try:
                obj_text = p.read_bytes().decode("utf-8", errors="replace")
                return p.name, {
                    "mode": "inline_text",
                    "value": obj_text,
                    "content_type": "application/octet-stream",
                    "source": str(p),
                    "is_obj": True,
                }
            except Exception as e:
                print(f"[OBJ] Failed to read {p.name}: {e}")

        data = p.read_bytes()
        try:
            txt = data.decode("utf-8")
            if "\x00" in txt:
                raise UnicodeError("binary-ish")
            return p.name, {
                "mode": "inline_text",
                "value": txt,
                "content_type": self._infer_content_type_from_name(p.name),
                "source": str(p),
            }
        except Exception:
            b64 = base64.b64encode(data).decode("ascii")
            return p.name, {
                "mode": "inline_b64",
                "value": b64,
                "content_type": self._infer_content_type_from_name(p.name),
                "source": str(p),
            }

    return raw, {"mode": "inline_text", "value": raw, "content_type": "text/plain; charset=utf-8"}


def _resolve_replace_field(self, raw: str) -> str:
    """If 'Replace' is a file path, read IDs from that file; otherwise return as-is."""
    raw = (raw or "").strip()
    if not raw:
        return ""
    p = Path(raw)
    if p.exists() and p.is_file():
        try:
            return p.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            return raw
    return raw


def _get_use_payload(self, row: int):
    """Returns (mode, value, content_type)."""
    use_item = self.loader_model.item(row, 2)
    meta = use_item.data(Qt.UserRole + 1) if use_item else None
    if not isinstance(meta, dict):
        txt = (use_item.text() if use_item else "") or ""
        if isnumeric(txt.strip()):
            return "assetId", txt.strip(), None
        return "inline", txt.encode("utf-8"), "text/plain; charset=utf-8"

    mode = meta.get("mode")
    if mode == "assetId":
        return "assetId", str(meta.get("value", "")).strip(), None

    if mode == "url":
        return "url", str(meta.get("value", "")).strip(), None

    ctype = meta.get("content_type") or "application/octet-stream"
    if mode == "inline_b64":
        # Cache decoded bytes in the meta dict so we only decode once
        data = meta.get("_decoded")
        if not isinstance(data, (bytes, bytearray)):
            try:
                data = base64.b64decode(
                    str(meta.get("value", "")).encode("ascii"), validate=False)
            except Exception:
                data = b""
            meta["_decoded"] = data
        return "inline", bytes(data), ctype

    val = meta.get("value", "")
    val_str = str(val).strip() if not isinstance(val, (bytes, bytearray)) else ""
    if val_str and isnumeric(val_str):
        return "assetId", val_str, None
    if isinstance(val, str):
        return "inline", val.encode("utf-8"), ctype
    if isinstance(val, (bytes, bytearray)):
        return "inline", bytes(val), ctype
    return "inline", str(val).encode("utf-8"), ctype


def add_rule(self, enabled: bool, name: str, from_key: str, to_key: str):
    on_item = QStandardItem()
    on_item.setFlags(Qt.ItemIsEnabled |
                     Qt.ItemIsSelectable | Qt.ItemIsUserCheckable)
    on_item.setCheckable(True)
    on_item.setCheckState(Qt.Checked if enabled else Qt.Unchecked)

    name_item = QStandardItem(name)

    display_use, use_meta = self._resolve_use_field(from_key)
    replace_text = self._resolve_replace_field(to_key)

    from_item = QStandardItem(display_use)
    to_item = QStandardItem(replace_text)

    from_item.setData(use_meta, Qt.UserRole + 1)

    for it in (name_item, from_item, to_item):
        it.setEditable(False)

    self.loader_model.appendRow([on_item, name_item, from_item, to_item])
    self._save_loader_rules()
    self._rebuild_loader_index()


def _meta_to_payload(meta: dict):
    """Convert a use_meta dict to (mode, value, content_type) — mirrors _get_use_payload."""
    if not isinstance(meta, dict):
        return "inline", b"", "text/plain; charset=utf-8"
    mode = meta.get("mode", "inline_text")
    if mode == "assetId":
        return "assetId", str(meta.get("value", "")).strip(), None
    if mode == "url":
        return "url", str(meta.get("value", "")).strip(), None
    ctype = meta.get("content_type") or "application/octet-stream"
    if mode == "inline_b64":
        try:
            data = base64.b64decode(
                str(meta.get("value", "")).encode("ascii"), validate=False)
        except Exception:
            data = b""
        return "inline", data, ctype
    val = meta.get("value", "")
    val_str = str(val).strip() if not isinstance(val, (bytes, bytearray)) else ""
    if val_str and isnumeric(val_str):
        return "assetId", val_str, None
    if isinstance(val, str):
        return "inline", val.encode("utf-8"), ctype
    if isinstance(val, (bytes, bytearray)):
        return "inline", bytes(val), ctype
    return "inline", str(val).encode("utf-8"), ctype


def _rebuild_loader_index(self):
    if getattr(self, "_loading_loader_rules", False):
        return
    index = {}
    type_index = {}

    # Current source: in-memory model is authoritative (may have unsaved checkbox changes)
    enabled_sources = getattr(self, "_enabled_sources", None)
    current = getattr(self, "_current_source_name", "Default")
    for row in range(self.loader_model.rowCount()) if (enabled_sources is None or current in enabled_sources) else []:
        on_item = self.loader_model.item(row, 0)
        if not on_item or on_item.checkState() != Qt.Checked:
            continue
        mode, use_val, use_ctype = self._get_use_payload(row)
        rep_item = self.loader_model.item(row, 3)
        if rep_item is None:
            continue
        for rid in self._split_csv((rep_item.data(Qt.UserRole + 1) if rep_item else "") or (rep_item.text() if rep_item else "")):
            if rid.lower().startswith("type:"):
                type_name = rid[5:].strip().lower()
                type_index.setdefault(type_name, []).append(
                    (mode, use_val, use_ctype))
            else:
                index.setdefault(rid, []).append((mode, use_val, use_ctype))

    # Other sources: include based on _enabled_sources (None = all enabled)
    try:
        all_sources = self._load_all_sources()
        for source_name, rules in all_sources.items():
            if source_name == current:
                continue
            if enabled_sources is not None and source_name not in enabled_sources:
                continue
            for r in rules:
                if not r.get("enabled", True):
                    continue
                use_meta = r.get("use", {})
                if isinstance(use_meta, str):
                    use_meta = {"mode": "inline_text", "value": use_meta}
                replace_text = r.get("replace", "")
                mode, use_val, use_ctype = _meta_to_payload(use_meta)
                for rid in self._split_csv(replace_text):
                    if rid.lower().startswith("type:"):
                        type_name = rid[5:].strip().lower()
                        type_index.setdefault(type_name, []).append(
                            (mode, use_val, use_ctype))
                    else:
                        index.setdefault(rid, []).append(
                            (mode, use_val, use_ctype))
    except Exception as e:
        print(f"[loader_index] Failed to include other sources: {e}")

    self._loader_index = index
    self._type_loader_index = type_index


def _load_selected(self):
    """Populate the Use/Replace lineedits from the selected loader row."""
    tv = getattr(self, "loader_table", None)
    if tv is None:
        return
    idx = tv.selectionModel().currentIndex()
    if not idx.isValid():
        return
    src = self.loader_proxy.mapToSource(idx)
    row = src.row()

    use_item = self.loader_model.item(row, 2)
    rep_item = self.loader_model.item(row, 3)

    use_text = ""
    if use_item:
        meta = use_item.data(Qt.UserRole + 1)
        if isinstance(meta, dict):
            raw = meta.get("source") or meta.get("value") or use_item.text()
            use_text = raw.decode(
                "utf-8", errors="replace") if isinstance(raw, (bytes, bytearray)) else str(raw)
        else:
            use_text = use_item.text()

    rep_text = (rep_item.data(Qt.UserRole + 1) if rep_item else "") or (rep_item.text() if rep_item else "")

    if getattr(self, "replace_with_lineedit", None):
        self.replace_with_lineedit.setText(use_text)
    if getattr(self, "replace_ids_lineedit", None):
        self.replace_ids_lineedit.setText(rep_text)


def _update_selected(self):
    """Update the selected loader row with the current lineedit values."""
    tv = getattr(self, "loader_table", None)
    if tv is None:
        return
    idx = tv.selectionModel().currentIndex()
    if not idx.isValid():
        return
    src = self.loader_proxy.mapToSource(idx)
    row = src.row()

    use_raw = (getattr(self, "replace_with_lineedit", None)
               and self.replace_with_lineedit.text() or "").strip()
    rep_raw = (getattr(self, "replace_ids_lineedit", None)
               and self.replace_ids_lineedit.text() or "").strip()

    def _apply(display_use, use_meta, replace_text):
        use_item = self.loader_model.item(row, 2)
        rep_item = self.loader_model.item(row, 3)
        if use_item:
            use_item.setText(display_use)
            use_item.setData(use_meta, Qt.UserRole + 1)
        if rep_item:
            rep_item.setText(replace_text)
        self._save_loader_rules()
        self._rebuild_loader_index()

    def _bg():
        display_use, use_meta = self._resolve_use_field(use_raw)
        replace_text = self._resolve_replace_field(rep_raw)
        self._on_main(lambda: _apply(display_use, use_meta, replace_text))

    threading.Thread(target=_bg, daemon=True).start()


def _on_source_changed(self, source_name: str):
    """Save current source's rules then load the newly selected source."""
    self._save_loader_rules()  # saves under old _current_source_name
    self._current_source_name = source_name
    all_sources = self._load_all_sources()
    self._load_source_rules(all_sources.get(source_name, []))


def _create_source(self):
    from PySide6.QtWidgets import QInputDialog
    name, ok = QInputDialog.getText(
        self.tab_widget, "Create Source", "Source name:")
    if not ok:
        return
    name = (name or "").strip()
    if not name:
        return
    cb = getattr(self, "sources_combo", None)
    if cb is None:
        return
    # Switch to existing source if name already exists
    for i in range(cb.count()):
        if cb.itemText(i) == name:
            cb.setCurrentIndex(i)
            return
    # Snapshot before creating so Ctrl+Z can undo
    self._push_source_snapshot()
    # Save current source before switching — suppress undo push so only the
    # sources snapshot above ends up on the stack (not a spurious rules entry).
    self._undoing = True
    try:
        self._save_loader_rules()
    finally:
        self._undoing = False
    # Write new empty source to disk
    all_sources = self._load_all_sources()
    all_sources[name] = []
    self._write_data_file(sources=all_sources)
    # Add to combobox and switch (block signals - we handle the switch manually)
    cb.blockSignals(True)
    cb.addItem(name)
    cb.setCurrentText(name)
    cb.blockSignals(False)
    self._current_source_name = name
    self._clear_loader_rules()
    self._rebuild_loader_index()


def _rules_to_replacement_rules(rules: list) -> list:
    """Convert internal rule dicts to the replacement_rules export format.

    File-based and inline content is embedded so the export is self-contained:
      mode "id"   -> with_id (asset ID redirect)
      mode "b64"  -> with_content_b64 + with_content_type (binary file)
      mode "text" -> with_content + with_content_type (text file)
      mode "url"  -> with_url (lazy-fetch URL)
    """
    out = []
    for r in rules:
        name = r.get("name", "")
        enabled = r.get("enabled", True)
        replace_str = r.get("replace", "")
        use = r.get("use", {})
        if isinstance(use, str):
            use = {"mode": "inline_text", "value": use}

        replace_ids = []
        replace_extras = []  # non-numeric entries like "type: Mesh"
        # Split only on commas/newlines (not spaces) so "type: Mesh" stays intact
        for part in re.split(r"[\n,]+", replace_str):
            part = part.strip()
            if not part:
                continue
            if part.isdigit():
                replace_ids.append(int(part))
            else:
                replace_extras.append(part)

        use_mode = use.get("mode", "inline_text") if isinstance(
            use, dict) else "inline_text"

        entry = {"name": name, "replace_ids": replace_ids, "enabled": enabled}
        if replace_extras:
            entry["replace_extras"] = replace_extras

        if use_mode == "assetId":
            entry["mode"] = "id"
            try:
                entry["with_id"] = int(use.get("value", 0))
            except (ValueError, TypeError):
                entry["mode"] = "text"
                entry["with_content"] = ""
        elif use_mode == "inline_b64":
            entry["mode"] = "b64"
            entry["with_content_b64"] = str(use.get("value", ""))
            if use.get("content_type"):
                entry["with_content_type"] = use["content_type"]
            # Preserve the original filename so the Use column shows it after re-import
            if use.get("source"):
                entry["with_name"] = Path(str(use["source"])).name
        elif use_mode == "url":
            entry["mode"] = "url"
            entry["with_url"] = str(use.get("value", ""))
        else:
            # inline_text or unknown
            entry["mode"] = "text"
            val = use.get("value", "") if isinstance(use, dict) else ""
            if isinstance(val, (bytes, bytearray)):
                val = val.decode("utf-8", errors="replace")
            entry["with_content"] = str(val)
            if isinstance(use, dict) and use.get("content_type"):
                entry["with_content_type"] = use["content_type"]
            # Preserve the original filename so the Use column shows it after re-import
            if isinstance(use, dict) and use.get("source"):
                entry["with_name"] = Path(str(use["source"])).name

        out.append(entry)
    return out


def _replacement_rules_to_rules(entries: list) -> list:
    """Convert replacement_rules export entries back to internal rule dicts."""
    out = []
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        name = str(entry.get("name", ""))
        enabled = bool(entry.get("enabled", True))
        replace_ids = entry.get("replace_ids", [])
        replace_extras = entry.get("replace_extras", [])

        def _normalize(s):
            s = str(s).strip()
            if not s:
                return s
            if s.lower().startswith("type:"):
                return s          # already prefixed
            try:
                int(s)
                return s          # numeric -> asset ID, keep as-is
            except ValueError:
                return f"type: {s}"  # non-numeric -> type name

        all_parts = [_normalize(i) for i in replace_ids if str(i).strip()] + \
                    [str(e) for e in replace_extras if str(e).strip()]
        replace_str = ", ".join(p for p in all_parts if p)

        mode = entry.get("mode", "id")
        with_id = entry.get("with_id")

        if mode == "id" and with_id is not None:
            use = {"mode": "assetId", "value": str(with_id)}
        elif mode == "b64" and "with_content_b64" in entry:
            use = {"mode": "inline_b64", "value": entry["with_content_b64"]}
            if entry.get("with_content_type"):
                use["content_type"] = entry["with_content_type"]
            # Restore display name: _load_source_rules uses source to show filename
            if entry.get("with_name"):
                use["source"] = entry["with_name"]
        elif mode == "url" and "with_url" in entry:
            use = {"mode": "url", "value": entry["with_url"]}
        elif "with_content" in entry or mode == "text":
            use = {"mode": "inline_text",
                   "value": entry.get("with_content", "")}
            if entry.get("with_content_type"):
                use["content_type"] = entry["with_content_type"]
            # Restore display name
            if entry.get("with_name"):
                use["source"] = entry["with_name"]
        else:
            use = {"mode": "inline_text", "value": ""}

        out.append({"enabled": enabled, "name": name,
                   "use": use, "replace": replace_str})
    return out


def _parse_import_data(data, parent_widget=None):
    """Parse an import payload and return (rules_list, preset_name_or_None).

    Handles:
      - {"replacement_rules": [...]}           external / preset export format
      - {"preset_name": ..., "replacement_rules": [...]}  preset export format
      - {"sources": {...}}                     internal multi-source format
      - {"rules": [...]}                       internal v1 format
      - [...]                                  bare list of rule dicts
    Returns None on user cancel.
    """
    from PySide6.QtWidgets import QMessageBox
    preset_name = None

    if isinstance(data, dict) and "replacement_rules" in data:
        preset_name = data.get("preset_name") or None
        rules = _replacement_rules_to_rules(data["replacement_rules"])
        return rules, preset_name

    if isinstance(data, dict) and "sources" in data:
        sources = data["sources"]
        if not isinstance(sources, dict) or not sources:
            QMessageBox.warning(parent_widget, "Import Failed",
                                "No sources found in file.")
            return None
        source_names = list(sources.keys())
        if len(source_names) == 1:
            chosen = source_names[0]
        else:
            from PySide6.QtWidgets import QInputDialog
            chosen, ok = QInputDialog.getItem(
                parent_widget, "Select Source",
                "Which source do you want to import?",
                source_names, 0, False,
            )
            if not ok:
                return None
        return sources.get(chosen, []), None

    if isinstance(data, dict) and "rules" in data:
        return data["rules"], None

    if isinstance(data, list):
        return data, None

    QMessageBox.warning(
        parent_widget, "Import Failed",
        'Unrecognized format. Expected {"replacement_rules": [...]} or internal source format.',
    )
    return None


def _export_loader_source(self):
    """Export the current source's rules to the replacement_rules JSON format."""
    from PySide6.QtWidgets import QFileDialog, QMessageBox
    current = getattr(self, "_current_source_name", "Default")
    rules = self._snapshot_rules()

    payload = {"replacement_rules": _rules_to_replacement_rules(rules)}
    safe_name = re.sub(r'[^\w\-. ]', '_', current)

    path, _ = QFileDialog.getSaveFileName(
        getattr(self, "tab_widget", None),
        "Export Source Rules",
        f"{safe_name}_config.json",
        "JSON Files (*.json);;All Files (*)",
    )
    if not path:
        return
    try:
        Path(path).write_text(json.dumps(payload, indent=2), encoding="utf-8")
    except Exception as e:
        QMessageBox.warning(
            getattr(self, "tab_widget", None),
            "Export Failed",
            f"Could not write file:\n{e}",
        )


def _import_loader_source(self):
    """Import rules from a replacement_rules JSON file into the current source."""
    from PySide6.QtWidgets import QFileDialog, QMessageBox
    path, _ = QFileDialog.getOpenFileName(
        getattr(self, "tab_widget", None),
        "Import Source Rules",
        "",
        "JSON Files (*.json);;All Files (*)",
    )
    if not path:
        return

    try:
        data = json.loads(Path(path).read_text(
            encoding="utf-8", errors="ignore"))
    except Exception as e:
        QMessageBox.warning(getattr(self, "tab_widget", None),
                            "Import Failed", f"Could not read/parse file:\n{e}")
        return

    result = _parse_import_data(data, getattr(self, "tab_widget", None))
    if result is None:
        return
    rules_to_add, _ = result

    if not rules_to_add:
        QMessageBox.information(
            getattr(self, "tab_widget", None), "Import", "No rules found to import.")
        return

    reply = QMessageBox.question(
        getattr(self, "tab_widget", None),
        "Import Rules",
        f"Import {len(rules_to_add)} rule(s) into source \"{getattr(self, '_current_source_name', 'Default')}\"?\n\n"
        "Yes = merge with existing rules\nNo = replace existing rules",
        QMessageBox.Yes | QMessageBox.No | QMessageBox.Cancel,
        QMessageBox.Yes,
    )
    if reply == QMessageBox.Cancel:
        return

    self._push_source_snapshot()
    if reply == QMessageBox.No:
        merged = rules_to_add
    else:
        merged = self._snapshot_rules() + rules_to_add

    self._load_source_rules(merged)
    all_sources = self._load_all_sources()
    all_sources[getattr(self, "_current_source_name", "Default")] = merged
    self._write_data_file(sources=all_sources)


def _delete_source(self):
    from PySide6.QtWidgets import QMessageBox
    cb = getattr(self, "sources_combo", None)
    if cb is None or cb.count() <= 1:
        return  # Never delete the last source
    current = getattr(self, "_current_source_name", "Default")
    reply = QMessageBox.question(
        self.tab_widget,
        "Delete Source",
        f'Delete source "{current}"?',
        QMessageBox.Yes | QMessageBox.No,
        QMessageBox.No,
    )
    if reply != QMessageBox.Yes:
        return
    # Snapshot before deleting so Ctrl+Z can undo
    self._push_source_snapshot()
    all_sources = self._load_all_sources()
    all_sources.pop(current, None)
    self._write_data_file(sources=all_sources)
    cb.blockSignals(True)
    idx = cb.findText(current)
    if idx >= 0:
        cb.removeItem(idx)
    cb.blockSignals(False)
    new_source = cb.currentText()
    self._current_source_name = new_source
    self._load_source_rules(all_sources.get(new_source, []))
