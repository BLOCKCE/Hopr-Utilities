"""Table setup, context menus, and filter UI for the cache module."""

from shared.utils import strip_cache_header, get_roblosecurity, isnumeric, has_cache_data, get_cache_data, batch_location
from shared.threading_utils import _MainThreadInvoker
from shared.menu_utils import StayOpenMenu
from shared.audio_player import AudioPlayer
from shared.ui_loader import load_ui
from shared.models import SortProxy
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


def _read_app_settings() -> dict:
    try:
        base = os.environ.get("LOCALAPPDATA") or str(
            Path.home() / "AppData" / "Local")
        path = os.path.join(base, "SubplaceJoiner", "app_settings.json")
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _write_app_settings(settings: dict):
    try:
        base = os.environ.get("LOCALAPPDATA") or str(
            Path.home() / "AppData" / "Local")
        path = os.path.join(base, "SubplaceJoiner", "app_settings.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(settings, f, indent=2)
    except Exception as e:
        print(f"[settings] save failed: {e}")


class _NoFocusDelegate(QStyledItemDelegate):
    def paint(self, painter, option, index):
        option.state &= ~QStyle.State_HasFocus
        super().paint(painter, option, index)


def _setup_table(self):
    self.model = QStandardItemModel(0, 6, self.tab_widget)
    self.model.setHorizontalHeaderLabels(
        ["Name", "ID", "Creator", "Type", "Size", "Date"]
    )

    self.proxy = SortProxy(self.tab_widget)
    self.proxy.setSourceModel(self.model)

    tv = self.table_view
    tv.setModel(self.proxy)
    tv.setSelectionBehavior(QAbstractItemView.SelectRows)
    tv.setSelectionMode(QAbstractItemView.ExtendedSelection)
    tv.setSortingEnabled(True)
    tv.verticalHeader().setVisible(False)
    tv.sortByColumn(0, Qt.AscendingOrder)
    tv.setMouseTracking(True)
    tv.setFocusPolicy(Qt.StrongFocus)
    tv.verticalHeader().setDefaultSectionSize(20)
    tv.horizontalHeader().setStretchLastSection(True)
    tv.horizontalHeader().setDefaultAlignment(Qt.AlignLeft | Qt.AlignVCenter)
    header = tv.horizontalHeader()
    header.setSectionResizeMode(QHeaderView.Interactive)

    # Set initial widths (overridden by saved widths if available)
    QTimer.singleShot(0, lambda: (
        self.table_view.setColumnWidth(0, 250),
        self.table_view.setColumnWidth(1, 100),
        self.table_view.setColumnWidth(2, 100),
        self.table_view.setColumnWidth(3, 100),
        self.table_view.setColumnWidth(4, 80),
        self.table_view.setColumnWidth(5, 180),
    ))
    QTimer.singleShot(0, lambda: self._apply_saved_col_widths(self.table_view))

    header.sectionResized.connect(
        lambda i, old, new, tv=self.table_view: self._on_column_resized(
            i, old, new, tv)
    )

    tv.horizontalHeader().setMinimumHeight(22)
    tv.horizontalHeader().setMaximumHeight(22)
    tv.horizontalHeader().setMinimumWidth(32)
    # tv.setStyleSheet("QTableView::item:hover { background-color: #3d3d3d; }")  # temporarily disabled
    tv.setItemDelegate(_NoFocusDelegate(tv))
    tv.viewport().installEventFilter(self)
    tv.setContextMenuPolicy(Qt.CustomContextMenu)
    tv.customContextMenuRequested.connect(self._show_context_menu)
    tv.installEventFilter(self)


def _on_column_resized(self, logical_index, old_size, new_size, view=None):
    if view is None:
        view = self.table_view  # fallback

    # Get header safely
    if isinstance(view, QTreeView):
        header = view.header()
    elif isinstance(view, QTableView):
        header = view.horizontalHeader()
    else:
        return

    count = header.count()
    viewport_right = header.viewport().width()

    if getattr(self, "_adjusting_columns", False):
        return
    if logical_index >= 0:
        if not hasattr(self, "_desired_column_sizes"):
            self._desired_column_sizes = {}
        if view not in self._desired_column_sizes:
            self._desired_column_sizes[view] = {}
        self._desired_column_sizes[view][logical_index] = new_size

    self._adjusting_columns = True
    try:
        for visual in range(count):
            logical = header.logicalIndex(visual)
            left = header.sectionPosition(logical)

            desired = self._desired_column_sizes.get(view, {}).get(
                logical, header.sectionSize(logical)
            )

            offset = 32 * (count - visual) - 32
            max_right = viewport_right - offset
            max_width = max_right - left
            if max_width < 0:
                max_width = 0

            new_width = min(desired, max_width)

            if header.sectionSize(logical) != new_width:
                header.resizeSection(logical, new_width)
    finally:
        self._adjusting_columns = False

    # Debounce-save column widths after a user resize
    if logical_index >= 0:
        view_key = view.objectName() or str(id(view))
        if not hasattr(self, "_col_save_timers"):
            self._col_save_timers = {}
        if view_key not in self._col_save_timers:
            t = QTimer()
            t.setSingleShot(True)
            t.timeout.connect(lambda vk=view_key,
                              v=view: self._do_save_col_widths(vk, v))
            self._col_save_timers[view_key] = t
        self._col_save_timers[view_key].start(500)


def _preview_finder_current_row(self):
    if not getattr(self, "previewFrame", None):
        return

    sel = getattr(self, "table_view", None)
    if sel is None:
        return
    sel_model = sel.selectionModel()
    if not sel_model:
        return

    rows = sel_model.selectedRows()
    if not rows:
        return

    proxy_index = rows[0]
    source_index = self.proxy.mapToSource(proxy_index)
    row = source_index.row()

    id_item = self.model.item(row, 1)
    if not id_item:
        return

    asset_id = id_item.data(Qt.UserRole)

    cache_info = self.cache_logs.get(asset_id)
    is_texturepack = isinstance(
        cache_info, dict) and cache_info.get("assetTypeId") == 63

    # TexturePacks: cache_data holds KTX2 (not previewable). Use texturepack_xml instead.
    if is_texturepack:
        xml_data = cache_info.get("texturepack_xml") if cache_info else None
        if xml_data:
            asset_name = cache_info.get("resolved_name")
            self.display_preview_enhanced(
                xml_data, 63, asset_id, asset_name, self.previewFrame)
        else:
            self._fetch_texturepack_preview(asset_id, self.previewFrame)
        return

    if not cache_info or not has_cache_data(cache_info):
        self.previewFrame.hide()
        return

    cache_data = get_cache_data(cache_info)
    asset_type_id = cache_info.get("assetTypeId")

    asset_name = (cache_info.get("resolved_name")
                  if isinstance(cache_info, dict) else None)
    self.display_preview_enhanced(
        cache_data, asset_type_id, asset_id, asset_name, self.previewFrame)


def _prefetch_texturepack_xml(self, asset_id):
    cookie = get_roblosecurity()

    def _bg():
        try:
            sess = requests.Session()
            sess.trust_env = False
            sess.proxies = {}
            sess.verify = False
            sess.headers.update({
                "User-Agent": "Roblox/WinInet",
                "Content-Type": "application/json",
                "Accept": "application/json",
                "Referer": "https://www.roblox.com/",
                "Origin": "https://www.roblox.com",
            })
            if cookie:
                sess.headers["Cookie"] = f".ROBLOSECURITY={cookie};"

            r = sess.post(
                "https://assetdelivery.roblox.com/v2/assets/batch",
                json=[{"assetId": asset_id, "requestId": "1"}],
                timeout=10,
            )
            if r.status_code != 200:
                return
            d = r.json()
            loc = batch_location(d[0]) if isinstance(d, list) and d else ""
            if not loc:
                return
            resp = sess.get(loc, timeout=10)
            if resp.status_code != 200 or not resp.content:
                return
            content = resp.content
            if not content[:16].decode('utf-8', errors='ignore').startswith("<roblox>"):
                return
            cache_info = self.cache_logs.get(asset_id)
            if cache_info is not None:
                cache_info["texturepack_xml"] = content
        except Exception as e:
            print(f"[TexturePack prefetch] Failed for {asset_id}: {e}")

    threading.Thread(target=_bg, daemon=True).start()


def _fetch_texturepack_preview(self, asset_id, preview_frame):
    if preview_frame is None:
        return

    if not preview_frame.layout():
        preview_frame.setLayout(QVBoxLayout())
    layout = preview_frame.layout()
    while layout.count():
        w = layout.takeAt(0).widget()
        if w:
            w.deleteLater()
    _lbl = QLabel("Loading…")
    _lbl.setAlignment(Qt.AlignCenter)
    layout.addWidget(_lbl)
    preview_frame.show()

    cache_info = self.cache_logs.get(asset_id)
    if cache_info and cache_info.get("texturepack_xml"):
        content = cache_info["texturepack_xml"]
        asset_name = cache_info.get("resolved_name")
        self.display_preview_enhanced(
            content, 63, asset_id, asset_name, preview_frame)
        return

    cookie = get_roblosecurity()

    def _clear_loading():
        lo = preview_frame.layout()
        if lo:
            while lo.count():
                w = lo.takeAt(0).widget()
                if w:
                    w.deleteLater()

    def _bg():
        try:
            sess = requests.Session()
            sess.trust_env = False
            sess.proxies = {}
            sess.verify = False
            sess.headers.update({
                "User-Agent": "Roblox/WinInet",
                "Content-Type": "application/json",
                "Accept": "application/json",
                "Referer": "https://www.roblox.com/",
                "Origin": "https://www.roblox.com",
            })
            if cookie:
                sess.headers["Cookie"] = f".ROBLOSECURITY={cookie};"

            r = sess.post(
                "https://assetdelivery.roblox.com/v2/assets/batch",
                json=[{"assetId": asset_id, "requestId": "1"}],
                timeout=10,
            )
            if r.status_code != 200:
                print(
                    f"[TexturePack preview] batch returned {r.status_code} for {asset_id}")
                self._on_main(_clear_loading)
                return
            d = r.json()
            loc = batch_location(d[0]) if isinstance(d, list) and d else ""
            if not loc:
                print(
                    f"[TexturePack preview] no location in batch response for {asset_id}")
                self._on_main(_clear_loading)
                return
            resp = sess.get(loc, timeout=10)
            if resp.status_code != 200:
                print(
                    f"[TexturePack preview] CDN fetch returned {resp.status_code} for {asset_id}")
                self._on_main(_clear_loading)
                return
            content = resp.content
            if not content:
                self._on_main(_clear_loading)
                return
            if not content[:16].decode('utf-8', errors='ignore').startswith("<roblox>"):
                print(
                    f"[TexturePack preview] unexpected content for {asset_id}: {content[:16]!r}")
                self._on_main(_clear_loading)
                return

            ci = self.cache_logs.get(asset_id)
            if not ci:
                self._on_main(_clear_loading)
                return
            ci["texturepack_xml"] = content

            def _show():
                asset_name = ci.get("resolved_name")
                self.display_preview_enhanced(
                    content, 63, asset_id, asset_name, preview_frame)

            self._on_main(_show)
        except Exception as e:
            print(f"[TexturePack preview] Failed for {asset_id}: {e}")
            self._on_main(_clear_loading)

    import threading
    threading.Thread(target=_bg, daemon=True).start()


def _on_loader_selection_changed(self, *_):
    if getattr(self, "_in_preview2_mode", False):
        return

    self._set_splitter2_mode("preview1")

    tv = getattr(self, "loader_table", None)
    if tv is None:
        return

    selected = tv.selectionModel().selectedRows() if tv.selectionModel() else []

    uses_frame = getattr(self, "_uses_content_frame", None)
    replaces_frame = getattr(self, "_replaces_content_frame", None)
    pw1 = getattr(self, "previewWindow1", None)
    pw2 = getattr(self, "previewWindow1_2", None)

    if not selected:
        if pw1:
            pw1.hide()
        if pw2:
            pw2.hide()
        return

    proxy_idx = selected[0]
    src_idx = self.loader_proxy.mapToSource(proxy_idx)
    row = src_idx.row()

    # Uses preview
    use_item = self.loader_model.item(row, 2)
    use_meta = use_item.data(Qt.UserRole + 1) if use_item else None
    if not isinstance(use_meta, dict):
        use_meta = {"mode": "inline_text", "value": (
            use_item.text() if use_item else "")}

    if uses_frame and pw1:
        mode = use_meta.get("mode", "inline_text")
        if mode == "assetId":
            asset_id_str = str(use_meta.get("value", "")).strip()
            if asset_id_str:
                pw1.show()
                self._load_asset_for_preview(asset_id_str, uses_frame)
            else:
                pw1.hide()
        elif mode == "inline_b64":
            source = use_meta.get("source", "")
            if source.lower().endswith(".obj") and os.path.isfile(source):
                pw1.show()
                self._display_obj_file_preview(source, uses_frame)
            else:
                b64_value = str(use_meta.get("value", ""))
                pw1.show()

                def _decode_and_preview(b64=b64_value, frame=uses_frame, _pw1=pw1):
                    try:
                        data = base64.b64decode(
                            b64.encode("ascii"), validate=False)
                    except Exception:
                        data = b""
                    if not data:
                        self._on_main(_pw1.hide)
                        return
                    try:
                        import shared.mesh_processing as mesh_processing
                        obj_content = mesh_processing.decode_loader_obj_mesh(
                            data)
                    except Exception:
                        obj_content = None
                    if obj_content:
                        tmp_obj = self._make_sj_temp_file(
                            "mesh", 0, ".obj", "loader_mesh")
                        tmp_obj.write_text(obj_content, encoding="utf-8")
                        self._track_temp(frame, str(tmp_obj))
                        obj_path = str(tmp_obj)
                        self._on_main(
                            lambda p=obj_path, f=frame: self._display_obj_file_preview(p, f))
                    else:
                        self._on_main(
                            lambda d=data, f=frame: self.display_preview_enhanced(d, 0, 0, None, f))
                threading.Thread(target=_decode_and_preview,
                                 daemon=True).start()
        else:
            val = use_meta.get("value", "")
            # Numeric inline_text values are asset IDs — fetch and preview them
            if str(val).strip().isdigit():
                pw1.show()
                self._load_asset_for_preview(str(val).strip(), uses_frame)
            else:
                data = val.encode("utf-8") if isinstance(val, str) else bytes(val)
                if data:
                    # If this is an OBJ stored as inline_text, preview it as a 3D mesh
                    is_obj = use_meta.get("is_obj", False)
                    if not is_obj:
                        import re as _re
                        is_obj = bool(_re.search(rb'(?m)^v\s+', data[:1024]))
                    if is_obj:
                        source = use_meta.get("source", "")
                        if source and os.path.isfile(source):
                            pw1.show()
                            self._display_obj_file_preview(source, uses_frame)
                        else:
                            tmp_obj = self._make_sj_temp_file(
                                "mesh", 0, ".obj", "loader_mesh")
                            tmp_obj.write_bytes(data)
                            self._track_temp(uses_frame, str(tmp_obj))
                            pw1.show()
                            self._display_obj_file_preview(
                                str(tmp_obj), uses_frame)
                    else:
                        pw1.show()
                        self.display_preview_enhanced(data, 0, 0, None, uses_frame)
                else:
                    pw1.hide()

    # Replaces preview
    rep_item = self.loader_model.item(row, 3)
    replace_text = (rep_item.data(Qt.UserRole + 1) if rep_item else "") or (rep_item.text() if rep_item else "")
    replace_ids = [x.strip() for x in replace_text.split(",") if x.strip()]

    self._replace_preview_ids = replace_ids
    self._replace_preview_idx = 0

    if replaces_frame and pw2:
        # Always clear the replaces frame when switching entries so stale
        # content from the previous selection never bleeds through.
        self.close_preview(replaces_frame, hide=False)

        if replace_ids:
            try:
                first_int = int(replace_ids[0].strip())
            except (ValueError, TypeError):
                first_int = None
            if first_int is not None:
                pw2.show()
                self._load_asset_for_preview(replace_ids[0], replaces_frame)
            else:
                pw2.hide()
        else:
            pw2.hide()
    elif pw2:
        pw2.hide()


def _setup_filter_menu(self):
    menu = StayOpenMenu(self.filter_button)

    asset_menu = StayOpenMenu(menu)
    asset_menu.setTitle("Asset type")
    menu.addMenu(asset_menu)

    asset_menu.setStyleSheet("QMenu { menu-scrollable: 1; }")

    self.all_action = asset_menu.addAction("All")
    self.all_action.setCheckable(True)
    self.all_action.setChecked(True)

    self.type_actions = {}
    asset_menu.addSeparator()

    for asset_id, name in ASSET_TYPES:
        act = asset_menu.addAction(name)
        act.setCheckable(True)
        self.type_actions[asset_id] = act

    self.all_action.toggled.connect(self._on_all_toggled)
    for act in self.type_actions.values():
        act.toggled.connect(self._on_item_toggled)

    menu.addSeparator()
    search_menu = StayOpenMenu(menu)
    search_menu.setTitle("Search by")
    menu.addMenu(search_menu)

    self.search_col_actions = {}
    cols = [
        ("Name", 0),
        ("ID", 1),
        ("Creator", 2),
        ("Type", 3),
        ("Size", 4),
        ("Date", 5),
    ]

    for label, col in cols:
        a = search_menu.addAction(label)
        a.setCheckable(True)
        a.setChecked(True)
        a.toggled.connect(lambda _=False: self._apply_finder_filters())
        self.search_col_actions[col] = a

    self.filter_button.setMenu(menu)

    self.all_action.toggled.connect(lambda _: self._apply_finder_filters())
    for act in self.type_actions.values():
        act.toggled.connect(lambda _: self._apply_finder_filters())

    def _save_type_filter():
        _write_app_settings({**_read_app_settings(),
                             "asset_type_all": self.all_action.isChecked(),
                             "asset_type_ids": [tid for tid, a in self.type_actions.items() if a.isChecked()],
                             })

    def _save_search_cols():
        _write_app_settings({**_read_app_settings(),
                             "search_cols": [c for c, a in self.search_col_actions.items() if a.isChecked()],
                             })

    self.all_action.toggled.connect(lambda _: _save_type_filter())
    for act in self.type_actions.values():
        act.toggled.connect(lambda _: _save_type_filter())
    for act in self.search_col_actions.values():
        act.toggled.connect(lambda _: _save_search_cols())

    # Restore saved state
    _saved = _read_app_settings()
    if "asset_type_all" in _saved or "asset_type_ids" in _saved:
        _all = _saved.get("asset_type_all", True)
        _ids = set(_saved.get("asset_type_ids", []))
        for act in list(self.type_actions.values()) + [self.all_action]:
            act.blockSignals(True)
        self.all_action.setChecked(_all)
        for tid, act in self.type_actions.items():
            act.setChecked(tid in _ids)
        for act in list(self.type_actions.values()) + [self.all_action]:
            act.blockSignals(False)
        self._on_all_toggled(self.all_action.isChecked())
    if "search_cols" in _saved:
        _cols = set(_saved["search_cols"])
        for col, act in self.search_col_actions.items():
            act.blockSignals(True)
            act.setChecked(col in _cols)
            act.blockSignals(False)
    self._apply_finder_filters()


def _on_all_toggled(self, checked):
    for act in self.type_actions.values():
        act.setEnabled(not checked)


def _on_item_toggled(self):
    any_checked = any(a.isChecked() for a in self.type_actions.values())
    self.all_action.blockSignals(True)
    self.all_action.setChecked(not any_checked)
    self.all_action.blockSignals(False)

# Settings menu


def _setup_settings_menu(self):
    menu = StayOpenMenu(self.settings_button)
    _saved = _read_app_settings()

    self.show_names_action = menu.addAction("Show Names")
    self.show_names_action.setCheckable(True)
    self.show_names_action.setChecked(_saved.get("show_names", True))
    self.show_names_action.toggled.connect(self._on_show_names_toggled)
    self.show_names_action.toggled.connect(
        lambda v: _write_app_settings({**_read_app_settings(), "show_names": v}))

    self.export_raw = menu.addAction("Export Raw")
    self.export_raw.setCheckable(True)
    self.export_raw.setChecked(_saved.get("export_raw", False))
    self.export_raw.toggled.connect(self._on_export_raw_toggled)
    self.export_raw.toggled.connect(
        lambda v: _write_app_settings({**_read_app_settings(), "export_raw": v}))

    namemenu = StayOpenMenu(menu)
    namemenu.setTitle("Export File Name")
    menu.addMenu(namemenu)

    self.name_action = namemenu.addAction("Name")
    self.name_action.setCheckable(True)
    self.name_action.setChecked(_saved.get("export_fname_name", True))
    self.name_action.toggled.connect(
        lambda v: _write_app_settings({**_read_app_settings(), "export_fname_name": v}))

    self.id_action = namemenu.addAction("Id")
    self.id_action.setCheckable(True)
    self.id_action.setChecked(_saved.get("export_fname_id", True))
    self.id_action.toggled.connect(
        lambda v: _write_app_settings({**_read_app_settings(), "export_fname_id": v}))

    self.Hash_action = namemenu.addAction("Hash")
    self.Hash_action.setCheckable(True)
    self.Hash_action.setChecked(_saved.get("export_fname_hash", False))
    self.Hash_action.toggled.connect(
        lambda v: _write_app_settings({**_read_app_settings(), "export_fname_hash": v}))

    columnmenu = StayOpenMenu(menu)
    columnmenu.setTitle("Toggle columns")
    menu.addMenu(columnmenu)

    self.name_column = columnmenu.addAction("Name")
    self.name_column.setCheckable(True)
    self.name_column.setChecked(_saved.get("col_name", True))

    self.id_column = columnmenu.addAction("Id")
    self.id_column.setCheckable(True)
    self.id_column.setChecked(_saved.get("col_id", True))

    self.creator_column = columnmenu.addAction("Creator")
    self.creator_column.setCheckable(True)
    self.creator_column.setChecked(_saved.get("col_creator", True))

    self.type_column = columnmenu.addAction("Type")
    self.type_column.setCheckable(True)
    self.type_column.setChecked(_saved.get("col_type", True))

    self.size_column = columnmenu.addAction("Size")
    self.size_column.setCheckable(True)
    self.size_column.setChecked(_saved.get("col_size", True))

    self.date_column = columnmenu.addAction("Date")
    self.date_column.setCheckable(True)
    self.date_column.setChecked(_saved.get("col_date", True))

    col_actions = {
        0: self.name_column,
        1: self.id_column,
        2: self.creator_column,
        3: self.type_column,
        4: self.size_column,
        5: self.date_column,
    }
    _col_keys = {0: "col_name", 1: "col_id", 2: "col_creator",
                 3: "col_type", 4: "col_size", 5: "col_date"}

    for col, act in col_actions.items():
        act.toggled.connect(
            lambda checked, c=col: self.table_view.setColumnHidden(c, not checked))
        act.toggled.connect(
            lambda v, k=_col_keys[col]: _write_app_settings({**_read_app_settings(), k: v}))

    for col, act in col_actions.items():
        self.table_view.setColumnHidden(col, not act.isChecked())

    mesh_fmt_menu = StayOpenMenu(menu)
    mesh_fmt_menu.setTitle("Mesh && csg format")
    menu.addMenu(mesh_fmt_menu)

    self.mesh_fmt_obj_action = mesh_fmt_menu.addAction(".obj")
    self.mesh_fmt_obj_action.setCheckable(True)
    self.mesh_fmt_obj_action.setChecked(_saved.get("mesh_fmt_obj", True))
    self.mesh_fmt_obj_action.toggled.connect(
        lambda v: _write_app_settings({**_read_app_settings(), "mesh_fmt_obj": v}))

    self.mesh_fmt_rbxmx_action = mesh_fmt_menu.addAction(".rbxmx")
    self.mesh_fmt_rbxmx_action.setCheckable(True)
    self.mesh_fmt_rbxmx_action.setChecked(_saved.get("mesh_fmt_rbxmx", False))
    self.mesh_fmt_rbxmx_action.toggled.connect(
        lambda v: _write_app_settings({**_read_app_settings(), "mesh_fmt_rbxmx": v}))

    self.settings_button.setMenu(menu)

# Context menu


def _show_loader_context_menu(self, position):
    tv = self.loader_table
    if tv is None:
        return

    index = tv.indexAt(position)
    has_index = index.isValid()

    selected_rows = tv.selectionModel().selectedRows()

    menu = QMenu(tv)

    copy_action = menu.addAction("Copy")
    copy_action.setEnabled(has_index)
    rename_action = menu.addAction("Rename")
    rename_action.setEnabled(has_index)
    rename_action.triggered.connect(
        lambda: self._open_loader_rename_dialog(index))

    def do_copy():
        text = self.loader_proxy.data(index, Qt.DisplayRole)
        if text is None:
            text = ""
        QApplication.clipboard().setText(str(text))

    copy_action.triggered.connect(do_copy)

    menu.addSeparator()

    delete_action = menu.addAction("Delete")
    delete_action.setEnabled(bool(selected_rows))
    delete_action.triggered.connect(
        lambda: self._delete_selected_loader_rows(selected_rows))

    menu.addSeparator()

    export_source_action = menu.addAction("Export Source...")
    export_source_action.triggered.connect(
        lambda: self._export_loader_source())

    import_source_action = menu.addAction("Import into Source...")
    import_source_action.triggered.connect(
        lambda: self._import_loader_source())

    menu.exec(tv.viewport().mapToGlobal(position))


def _open_loader_rename_dialog(self, proxy_index):
    if not proxy_index or not proxy_index.isValid():
        return

    src_index = self.loader_proxy.mapToSource(proxy_index)
    src_row = src_index.row()

    name_item = self.loader_model.item(src_row, 1)
    if not name_item:
        return

    old_name = name_item.text()

    dialog1 = QDialog(self.tab_widget)
    ui1 = Dialog1UI()
    ui1.setupUi(dialog1)

    ui1.lineEdit.setText(old_name)
    ui1.lineEdit.selectAll()
    ui1.lineEdit.setFocus()

    if not dialog1.exec():
        return

    new_name = ui1.lineEdit.text().strip()
    if not new_name:
        return

    name_item.setText(new_name)


def _delete_selected_loader_rows(self, selected_proxy_rows):
    if not selected_proxy_rows:
        return
    source_rows = {self.loader_proxy.mapToSource(
        idx).row() for idx in selected_proxy_rows}
    for row in sorted(source_rows, reverse=True):
        self.loader_model.removeRow(row)


def _show_context_menu(self, position):
    tv = self.table_view

    # index under cursor (proxy index)
    index = tv.indexAt(position)
    has_index = index.isValid()

    # selected rows (for Delete)
    selected_rows = tv.selectionModel().selectedRows()

    menu = QMenu(tv)

    # Copy cell
    copy_action = menu.addAction("Copy")
    copy_action.setEnabled(has_index)

    def do_copy():
        # Copy display text of the right-clicked cell
        text = self.proxy.data(index, Qt.DisplayRole)
        if text is None:
            text = ""
        QApplication.clipboard().setText(str(text))

    copy_action.triggered.connect(do_copy)

    # Copy as game dump
    copy_dump_action = menu.addAction("Copy as game dump")
    copy_dump_action.setEnabled(bool(selected_rows))

    def do_copy_as_game_dump():
        rows = {self.proxy.mapToSource(idx).row() for idx in selected_rows}
        # Build {TypeName: {AssetName: assetId, ...}, ...}
        # This is the format _add_json_to_qtree renders as a collapsible tree
        # in the Assets / Replacements picker when you open a custom game dump.
        by_type = {}
        name_counts = {}  # track duplicate names per type for deduplication
        for row in sorted(rows):
            name = self.model.data(self.model.index(row, 0)) or "Unknown"
            asset_id_raw = self.model.data(self.model.index(row, 1))
            type_name = self.model.data(self.model.index(row, 3)) or "Unknown"
            try:
                asset_id = int(asset_id_raw)
            except (ValueError, TypeError):
                continue
            bucket = by_type.setdefault(type_name, {})
            # Deduplicate names within the same type bucket
            key = name
            count_key = (type_name, name)
            if key in bucket:
                name_counts[count_key] = name_counts.get(count_key, 1) + 1
                key = f"{name} ({name_counts[count_key]})"
            bucket[key] = asset_id
        if not by_type:
            return
        # Sort type groups alphabetically
        result = {t: by_type[t] for t in sorted(by_type)}
        QApplication.clipboard().setText(json.dumps(result, indent=2))

    copy_dump_action.triggered.connect(do_copy_as_game_dump)

    menu.addSeparator()

    # Delete slected rows
    delete_action = menu.addAction("Delete")
    delete_action.setEnabled(bool(selected_rows))
    delete_action.triggered.connect(
        lambda: self._delete_selected_rows(selected_rows))

    export_action = menu.addAction("Export")
    export_action.setEnabled(bool(selected_rows))
    export_action.triggered.connect(
        lambda: self._export_selected_rows(selected_rows))

    menu.addSeparator()

    send_menu = QMenu("Send to loader", menu)

    def do_send_use():
        rows = sorted(self.proxy.mapToSource(idx).row()
                      for idx in selected_rows)
        if not rows:
            return
        asset_id = self.model.data(self.model.index(rows[0], 1))
        if asset_id is not None and getattr(self, "replace_with_lineedit", None):
            self.replace_with_lineedit.setText(str(asset_id))

    def do_send_replace():
        rows = sorted(self.proxy.mapToSource(idx).row()
                      for idx in selected_rows)
        ids = [str(self.model.data(self.model.index(r, 1)))
               for r in rows if self.model.data(self.model.index(r, 1)) is not None]
        if ids and getattr(self, "replace_ids_lineedit", None):
            self.replace_ids_lineedit.setText(", ".join(ids))

    use_action = send_menu.addAction("Use asset")
    use_action.setEnabled(bool(selected_rows))
    use_action.triggered.connect(do_send_use)

    replace_action = send_menu.addAction("Replace asset(s)")
    replace_action.setEnabled(bool(selected_rows))
    replace_action.triggered.connect(do_send_replace)

    menu.addMenu(send_menu)

    menu.exec(tv.viewport().mapToGlobal(position))


def _export_selected_rows(self, selected_indexes):
    from PySide6.QtWidgets import QMessageBox
    if not selected_indexes:
        return

    date_folder = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    base_export_dir = os.path.join(
        os.environ.get("LOCALAPPDATA", os.path.expanduser("~")),
        "SubplaceJoiner", "Export", date_folder
    )

    do_raw = getattr(self, "export_raw", None) and self.export_raw.isChecked()

    # Collect row data on the main thread - Qt model access must stay here
    rows_data = []
    rows = {self.proxy.mapToSource(idx).row() for idx in selected_indexes}
    for row in rows:
        asset_id = self.model.data(self.model.index(row, 1))
        if asset_id is None:
            continue
        try:
            log = self.cache_logs[int(asset_id)]
        except (KeyError, ValueError):
            print(f"Skipping invalid asset ID: {asset_id}")
            continue

        asset_type_id = log.get("assetTypeId")
        raw_cache_data = get_cache_data(log)
        texturepack_xml = log.get("texturepack_xml")
        resolved_name = log.get("resolved_name")
        location = log.get("location")
        cache_hash = ""
        if location:
            parsed_location = urlparse(location)
            cache_hash = parsed_location.path.rsplit("/", 1)[-1]

        parts = []
        if getattr(self, "name_action", None) and self.name_action.isChecked():
            if resolved_name:
                parts.append(resolved_name)
        if getattr(self, "id_action", None) and self.id_action.isChecked():
            parts.append(str(asset_id))
        if getattr(self, "Hash_action", None) and self.Hash_action.isChecked():
            if cache_hash:
                parts.append(cache_hash)
        name = " - ".join(parts) if parts else str(asset_id)
        safe_name = re.sub(r'[<>:"/\\|?*\x00-\x1f\x7f]', '_', name).strip()

        rows_data.append({
            "asset_id": int(asset_id),
            "asset_type_id": asset_type_id,
            "raw_cache_data": raw_cache_data,
            "texturepack_xml": texturepack_xml,
            "resolved_name": resolved_name,
            "safe_name": safe_name,
        })

    if not rows_data:
        return

    os.makedirs(base_export_dir, exist_ok=True)

    def _do_export():
        exported_count = 0
        texture_exports = []  # (asset_id, safe_name, xml_bytes)
        _fmt_obj = self.mesh_fmt_obj_action.isChecked()
        _fmt_rbxmx = self.mesh_fmt_rbxmx_action.isChecked()
        # Fallback: if nothing is checked export as obj so the user always gets something
        if not _fmt_obj and not _fmt_rbxmx:
            _fmt_obj = True

        for item in rows_data:
            asset_id = item["asset_id"]
            asset_type_id = item["asset_type_id"]
            raw_cache_data = item["raw_cache_data"]
            texturepack_xml = item["texturepack_xml"]
            resolved_name = item["resolved_name"]
            safe_name = item["safe_name"]

            # TexturePacks: use the XML we fetched, not the KTX2 cache_data
            is_texturepack = asset_type_id == 63 and texturepack_xml
            if is_texturepack:
                file_type = "TEXTURE"
            else:
                file_type = self._identify_file_type(raw_cache_data)
                if asset_type_id == 24:
                    file_type = "RBXM Animation"

            # Raw export
            if do_raw:
                if file_type in ["PNG", "GIF", "JPEG", "JFIF"]:
                    folder = "image"
                elif file_type in ["OGG", "MP3"]:
                    folder = "audio"
                elif file_type.startswith("Mesh"):
                    folder = "mesh"
                elif file_type in ["JSON", "Translation (JSON)", "TTF (JSON)"]:
                    folder = "json"
                elif file_type in ["XML", "EXTM3U"]:
                    folder = "xml"
                elif file_type == "RBXM Animation":
                    folder = "animation"
                elif file_type == "TEXTURE":
                    folder = "texture"
                else:
                    folder = "unknown"

                export_dir = os.path.join(base_export_dir, folder)
                os.makedirs(export_dir, exist_ok=True)

                if is_texturepack:
                    # Raw TexturePack = the XML descriptor
                    file_path = os.path.join(export_dir, f"{safe_name}.xml")
                    with open(file_path, "wb") as f:
                        f.write(texturepack_xml)
                    exported_count += 1
                elif raw_cache_data:
                    file_path = os.path.join(export_dir, safe_name)
                    with open(file_path, "wb") as f:
                        f.write(raw_cache_data)
                    exported_count += 1
                continue

            # Normal (converted) export
            cache_data = strip_cache_header(
                raw_cache_data) if raw_cache_data else raw_cache_data

            # SolidModel: convert to .rbxmx and/or .obj
            if asset_type_id == 39:
                if not cache_data:
                    print(
                        f"[SolidModel export] No cache data for asset {asset_id}, skipping")
                    continue
                export_dir = os.path.join(base_export_dir, "solidmodel")
                os.makedirs(export_dir, exist_ok=True)
                if _fmt_rbxmx:
                    rbxmx_bytes = self._convert_solidmodel_for_export(
                        cache_data, asset_id, resolved_name)
                    if rbxmx_bytes:
                        file_path = os.path.join(
                            export_dir, f"{safe_name}.rbxmx")
                        with open(file_path, "wb") as f:
                            f.write(rbxmx_bytes)
                        exported_count += 1
                        print(f"[SolidModel export] Wrote {file_path}")
                    else:
                        file_path = os.path.join(
                            export_dir, f"{safe_name}.rbxm")
                        with open(file_path, "wb") as f:
                            f.write(cache_data)
                        exported_count += 1
                        print(
                            f"[SolidModel export] Conversion failed, wrote raw fallback {file_path}")
                if _fmt_obj:
                    try:
                        import sys as _sys
                        import gzip as _gzip
                        _cache_dir = os.path.dirname(
                            os.path.dirname(os.path.abspath(__file__)))
                        if _cache_dir not in _sys.path:
                            _sys.path.insert(0, _cache_dir)
                        from tools.solidmodel_converter.converter import (
                            deserialize_rbxm, _get_top_level_mesh_data, _try_extract_child_data,
                        )
                        from tools.solidmodel_converter.csg_mesh import parse_csg_mesh_full, export_obj as _export_obj
                        _ZSTD = b'\x28\xb5\x2f\xfd'
                        _GZIP = b'\x1f\x8b'
                        data = cache_data
                        if data[:4] == _ZSTD:
                            import zstandard
                            data = zstandard.ZstdDecompressor().decompress(
                                data, max_output_size=64 * 1024 * 1024)
                        elif data[:2] == _GZIP:
                            data = _gzip.decompress(data)
                        doc = deserialize_rbxm(data)
                        mesh_data = _get_top_level_mesh_data(doc)
                        if mesh_data is None:
                            child_doc = _try_extract_child_data(doc)
                            if child_doc is not None:
                                mesh_data = _get_top_level_mesh_data(child_doc)
                        if mesh_data is None:
                            for inst in list(doc.roots) + list(doc.instances.values()):
                                prop = inst.properties.get('MeshData')
                                if prop is not None and isinstance(prop.value, bytes) and len(prop.value) > 0:
                                    mesh_data = prop.value
                                    break
                        if mesh_data is not None:
                            result = parse_csg_mesh_full(mesh_data)
                            vertices = result.vertices
                            indices = result.indices
                            if result.submesh_boundaries and len(result.submesh_boundaries) > 1:
                                indices = indices[:result.submesh_boundaries[1]]
                            obj_dest = Path(export_dir) / f"{safe_name}.obj"
                            _export_obj(vertices, indices, obj_dest,
                                        object_name=resolved_name or 'SolidModel')
                            exported_count += 1
                            print(f"[SolidModel export] Wrote OBJ {obj_dest}")
                        else:
                            print(
                                f"[SolidModel export] No mesh data for OBJ export, asset {asset_id}")
                    except Exception as e:
                        print(
                            f"[SolidModel export] OBJ failed for asset {asset_id}: {e}")
                        import traceback
                        traceback.print_exc()
                continue

            if file_type in ["PNG", "GIF", "JPEG", "JFIF"]:
                export_dir = os.path.join(base_export_dir, "image")
                os.makedirs(export_dir, exist_ok=True)
                ext = "jpg" if file_type.lower() in ("jpeg", "jfif") else file_type.lower()
                file_path = os.path.join(export_dir, f"{safe_name}.{ext}")
                if cache_data:
                    with open(file_path, "wb") as f:
                        f.write(cache_data)
                    exported_count += 1

            elif file_type in ["OGG", "MP3"]:
                export_dir = os.path.join(base_export_dir, "audio")
                os.makedirs(export_dir, exist_ok=True)
                file_path = os.path.join(
                    export_dir, f"{safe_name}.{file_type.lower()}")
                if cache_data:
                    with open(file_path, "wb") as f:
                        f.write(cache_data)
                    exported_count += 1

            elif file_type.startswith("Mesh"):
                export_dir = os.path.join(base_export_dir, "mesh")
                os.makedirs(export_dir, exist_ok=True)
                if _fmt_obj:
                    obj_path = self._convert_mesh_to_obj(
                        cache_data, asset_id, resolved_name)
                    if obj_path and os.path.exists(obj_path):
                        dest = os.path.join(export_dir, f"{safe_name}.obj")
                        try:
                            shutil.copy2(obj_path, dest)
                            exported_count += 1
                        except Exception as e:
                            print(f"Failed to copy mesh {asset_id}: {e}")
                    else:
                        print(
                            f"Mesh OBJ conversion failed for asset {asset_id}")

            elif file_type in ["JSON", "Translation (JSON)", "TTF (JSON)"]:
                export_dir = os.path.join(base_export_dir, "json")
                os.makedirs(export_dir, exist_ok=True)
                file_path = os.path.join(export_dir, f"{safe_name}.json")
                if cache_data:
                    with open(file_path, "wb") as f:
                        f.write(cache_data)
                    exported_count += 1

            elif file_type in ["XML", "EXTM3U"]:
                export_dir = os.path.join(base_export_dir, "xml")
                os.makedirs(export_dir, exist_ok=True)
                ext = "m3u" if file_type == "EXTM3U" else "xml"
                file_path = os.path.join(export_dir, f"{safe_name}.{ext}")
                if cache_data:
                    with open(file_path, "wb") as f:
                        f.write(cache_data)
                    exported_count += 1

            elif file_type == "RBXM Animation":
                export_dir = os.path.join(base_export_dir, "animation")
                os.makedirs(export_dir, exist_ok=True)
                file_path = os.path.join(export_dir, f"{safe_name}.rbxm")
                if cache_data:
                    with open(file_path, "wb") as f:
                        f.write(cache_data)
                    exported_count += 1

            elif file_type == "TEXTURE":
                texture_exports.append((asset_id, safe_name, texturepack_xml))

            else:
                export_dir = os.path.join(base_export_dir, "unknown")
                os.makedirs(export_dir, exist_ok=True)
                file_path = os.path.join(export_dir, safe_name)
                if cache_data:
                    with open(file_path, "wb") as f:
                        f.write(cache_data)
                    exported_count += 1

        # TexturePack: batch-resolve all map asset IDs then download in parallel
        if texture_exports:
            cookie = get_roblosecurity()
            sess = self._new_session(cookie)
            sess.mount("https://", adapter)

            texture_requests = []
            for asset_id, safe_name, xml_data in texture_exports:
                xml_text = xml_data.decode("utf-8", errors="ignore")
                packs = self.read_texturepack_xml(xml_text)
                if not packs:
                    continue
                pack = packs[0]
                for key in ("color", "normal", "metalness", "roughness"):
                    if key in pack:
                        texture_requests.append(
                            (asset_id, safe_name, key, pack[key]))

            if texture_requests:
                resolved = []
                req_id = 0

                def chunks(lst, n):
                    for i in range(0, len(lst), n):
                        yield lst[i:i + n]

                for batch in chunks(texture_requests, 256):
                    payload = []
                    id_map = {}
                    for entry in batch:
                        payload.append(
                            {"assetId": entry[3], "requestId": str(req_id)})
                        id_map[str(req_id)] = entry
                        req_id += 1
                    try:
                        r = sess.post(
                            "https://assetdelivery.roblox.com/v2/assets/batch",
                            json=payload,
                            timeout=20,
                        )
                        if not r.ok:
                            continue
                        for row in r.json():
                            entry = id_map.get(row.get("requestId"))
                            loc = batch_location(row)
                            if entry and loc:
                                resolved.append(entry + (loc,))
                    except Exception as e:
                        print(f"Texture batch request failed: {e}")

                export_root = os.path.join(base_export_dir, "texture")
                os.makedirs(export_root, exist_ok=True)
                lock = threading.Lock()

                def worker(a_id, s_name, map_type, tex_id, url):
                    nonlocal exported_count
                    try:
                        resp = sess.get(url, timeout=20)
                        if not resp.ok:
                            return
                        with lock:
                            asset_dir = os.path.join(export_root, s_name)
                            os.makedirs(asset_dir, exist_ok=True)
                        path = os.path.join(asset_dir, f"{map_type}.png")
                        with open(path, "wb") as f:
                            f.write(resp.content)
                        with lock:
                            exported_count += 1
                    except Exception as e:
                        print(f"Texture download failed: {e}")

                dl_threads = []
                for entry in resolved:
                    t = threading.Thread(target=worker, args=entry)
                    t.start()
                    dl_threads.append(t)
                for t in dl_threads:
                    t.join()

        def _done():
            try:
                os.startfile(base_export_dir)
            except Exception:
                pass
            msg = QMessageBox(self.tab_widget)
            msg.setWindowTitle("Export Complete")
            if exported_count > 0:
                msg.setText(
                    f"Exported {exported_count} file(s) to:\n{base_export_dir}")
            else:
                msg.setText(
                    "Nothing was exported. The selected items may have no cache data.")
            msg.exec()

        self._on_main(_done)

    threading.Thread(target=_do_export, daemon=True).start()


def _convert_solidmodel_for_export(self, cache_data, asset_id, resolved_name=None):
    """Convert a SolidModel binary blob to importable RBXMX bytes.

    Extracts the embedded ChildData RBXM, injects the top-level MeshData
    into each PartOperation so the result loads correctly in Roblox Studio.
    Returns XML bytes on success, or None on failure.
    """
    try:
        import gzip as _gzip
        import os as _os
        import sys as _sys
        _cache_dir = _os.path.dirname(
            _os.path.dirname(_os.path.abspath(__file__)))
        if _cache_dir not in _sys.path:
            _sys.path.insert(0, _cache_dir)

        from tools.solidmodel_converter.converter import (
            deserialize_rbxm,
            _get_top_level_mesh_data,
            _try_extract_child_data,
            _inject_mesh_data,
        )
        from tools.solidmodel_converter.rbxm.xml_writer import write_rbxmx

        _ZSTD = b'\x28\xb5\x2f\xfd'
        data = cache_data
        if data[:4] == _ZSTD:
            import zstandard
            data = zstandard.ZstdDecompressor().decompress(
                data, max_output_size=64 * 1024 * 1024)
        elif data[:2] == b'\x1f\x8b':
            data = _gzip.decompress(data)

        doc = deserialize_rbxm(data)
        top_mesh_data = _get_top_level_mesh_data(doc)
        child_doc = _try_extract_child_data(doc)

        if child_doc is not None:
            if top_mesh_data is not None:
                _inject_mesh_data(child_doc, top_mesh_data)
            doc = child_doc

        return write_rbxmx(doc)
    except Exception as e:
        print(
            f"[SolidModel export] Conversion failed for asset {asset_id}: {e}")
        import traceback
        traceback.print_exc()
        return None


def clear_all_rows(self):
    # Cancel any pending index flush timer.
    lock = getattr(self, "_cache_index_lock", None)
    if lock is not None:
        with lock:
            old_t = getattr(self, "_cache_index_timer", None)
            if old_t is not None:
                old_t.cancel()
                self._cache_index_timer = None
            self._cache_index_pending = {}

    # Delete all persistent .bin files and reset index.json.
    for asset_id, _info in self.cache_logs.items():
        if isinstance(_info, dict):
            _p = _info.get("cache_data_path")
            if _p:
                try:
                    os.unlink(_p)
                except Exception:
                    pass
    try:
        idx_path = self._cache_index_path()
        idx_path.write_text('{"version": 2, "assets": {}}', encoding="utf-8")
    except Exception:
        pass

    self.model.removeRows(0, self.model.rowCount())
    self.cache_logs.clear()
    if getattr(self, "previewFrame", None):
        self.close_preview(self.previewFrame, deselect=False)
        # Bump the generation counter so any in-flight preview callbacks
        # (queued via _on_main) see a stale gen and discard their result.
        if hasattr(self, "_frame_preview_gen"):
            _fpg = self._frame_preview_gen.get(self.previewFrame, 0)
            self._frame_preview_gen[self.previewFrame] = _fpg + 1
    lbl = getattr(self, "info_label", None)
    if lbl is not None:
        lbl.setText("Caches in cache finder: 0")


def delete_roblox_db(self):
    base = Path(os.getenv("LOCALAPPDATA") or "") / "Roblox"
    candidates = []

    if base.exists():
        for root, _, files in os.walk(base):
            for f in files:
                if f.lower().endswith((".db", ".sqlite")):
                    candidates.append(str(Path(root) / f))

    def show_result_dialog6(message: str):
        dialog6 = QDialog(self.tab_widget)
        ui6 = Dialog6UI()
        ui6.setupUi(dialog6)

        label = dialog6.findChild(QLabel)
        if label:
            label.setText(message)
        else:
            print("Dialog6: QLabel not found")

        dialog6.exec()

    if not candidates:
        show_result_dialog6(
            "No .db files found in LocalAppData\\Roblox"
        )
        return

    dialog5 = QDialog(self.tab_widget)
    ui5 = Dialog5UI()
    ui5.setupUi(dialog5)

    if not dialog5.exec():
        return

    for proc in ("RobloxPlayerBeta.exe", "RobloxPlayer.exe", "RobloxStudio.exe"):
        try:
            subprocess.run(
                ["taskkill", "/F", "/IM", proc],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                creationflags=subprocess.CREATE_NO_WINDOW,
            )
        except Exception:
            pass

    deleted = 0
    for p in candidates:
        try:
            os.remove(p)
            deleted += 1
        except Exception as e:
            print("Failed:", p, e)

    show_result_dialog6(f"Deleted {deleted} DB(s)")


def _delete_roblox_db_silent(self):
    base = Path(os.getenv("LOCALAPPDATA") or "") / "Roblox"
    candidates = []
    if base.exists():
        for root, _, files in os.walk(base):
            for f in files:
                if f.lower().endswith((".db", ".sqlite")):
                    candidates.append(str(Path(root) / f))
    if not candidates:
        print("[Del DB on start] No .db files found in LocalAppData\\Roblox")
        return
    for proc in ("RobloxPlayerBeta.exe", "RobloxPlayer.exe", "RobloxStudio.exe"):
        try:
            subprocess.run(
                ["taskkill", "/F", "/IM", proc],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                creationflags=subprocess.CREATE_NO_WINDOW,
            )
        except Exception:
            pass
    deleted = 0
    for p in candidates:
        try:
            os.remove(p)
            deleted += 1
        except Exception as e:
            print(f"[Del DB on start] Failed to delete {p}: {e}")
    print(f"[Del DB on start] Deleted {deleted} DB(s)")


def _delete_selected_rows(self, selected_indexes):
    source_rows = []
    for proxy_index in selected_indexes:
        source_index = self.proxy.mapToSource(proxy_index)
        source_rows.append(source_index.row())

    source_rows = sorted(set(source_rows), reverse=True)

    # Build a reverse map from source row -> asset_id for cleanup.
    row_to_asset = {}
    for asset_id, info in self.cache_logs.items():
        if not isinstance(info, dict):
            continue
        idx = info.get("name_index")
        if idx and idx.isValid():
            row_to_asset[idx.row()] = asset_id

    asset_ids_to_delete = []
    for row in source_rows:
        asset_id = row_to_asset.get(row)
        if asset_id is not None:
            asset_ids_to_delete.append(asset_id)
            self.cache_logs.pop(asset_id, None)
        self.model.removeRow(row)

    # Update the label immediately after rows are removed
    lbl = getattr(self, "info_label", None)
    if lbl is not None:
        lbl.setText(f"Caches in cache finder: {self.model.rowCount()}")

    # Do the actual file/index deletion on a background thread
    def _do_delete(ids=asset_ids_to_delete):
        for asset_id in ids:
            self._delete_cache_entry(asset_id)

    threading.Thread(target=_do_delete, daemon=True).start()

# Event filter


def eventFilter(self, obj, event):
    from PySide6.QtGui import QKeySequence

    tables = [self.table_view, getattr(self, "loader_table", None)]
    tables = [t for t in tables if t is not None]
    viewports = [t.viewport() for t in tables]

    if event.type() == QEvent.Resize:
        if obj == self.table_view.viewport():
            QTimer.singleShot(
                0, lambda: self._on_column_resized(-1, 0, 0, self.table_view))

        lt = getattr(self, "loader_table", None)
        if lt is not None and obj == lt.viewport():
            QTimer.singleShot(
                0, lambda: self._on_column_resized(-1, 0, 0, lt))

        pt = getattr(self, "preset_tree", None)
        if pt is not None and obj == pt.viewport():
            QTimer.singleShot(
                0, lambda: self._on_column_resized(-1, 0, 0, pt))

    # Ctrl + a supportalorta
    if obj in (tables + viewports) and event.type() == QEvent.KeyPress:
        if event.matches(QKeySequence.SelectAll):
            if obj in viewports:
                obj.parent().selectAll()
            else:
                obj.selectAll()
            return True

    tv = self.table_view
    if getattr(self, "previewFrame", None) and tv is not None:
        if obj is tv.viewport() and event.type() == QEvent.MouseButtonPress:
            QTimer.singleShot(0, self._preview_finder_current_row)
        elif obj is tv and event.type() == QEvent.KeyPress:
            nav = {Qt.Key_Up, Qt.Key_Down, Qt.Key_PageUp, Qt.Key_PageDown,
                   Qt.Key_Home, Qt.Key_End}
            if event.key() in nav:
                QTimer.singleShot(0, self._preview_finder_current_row)

    return QObject.eventFilter(self, obj, event)
