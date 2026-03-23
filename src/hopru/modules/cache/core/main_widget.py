"""Main Cache tab implementation (split out from main.py)."""

from .main_mitm import parse_body, rebuild_body, _new_session, event, _split_csv, request, response
from .main_resolver import fetch_creator_names, fetch_asset_names, name_resolver_loop, creator_resolver_loop, _on_show_names_toggled, process_asset_row, fetch_and_process, _on_export_raw_toggled, _on_export_converted_toggled, _cache_dir, _cache_index_path, _get_cache_bin_path, _queue_cache_index_update, _flush_cache_index, _delete_cache_entry, _load_persistent_cache
from .main_presets import _setup_preset_tree, add_preset, create_preset, apply_preset, _fetch_clog_json, _normalize_games_from_clog, _flatten_json, _fetch_and_flatten_urls, _short_url_label, _add_json_to_qtree, _collect_leaf_paths, _load_remote_presets, _populate_test_preset_cards, _fetch_json_url, _resolve_caches_for_game, _open_preset_window, _relayout_preset_cards, _apply_preset_from_window, _apply_presets_search_filter, _set_splitter2_mode, open_presets_window, _load_2nd_presets_ui_class, _save_presets, _load_presets, _open_url_picker, _custom_dumps_dir, _load_custom_game_entries, _add_game_card_from_entry, _open_add_game_dump_dialog, _custom_card_context_menu, _delete_custom_dump_card, _show_preset_context_menu, _export_preset, _import_preset
from .main_finder import _parse_size_to_bytes, _build_finder_conditions, _apply_finder_filters
from .main_table import _setup_table, _on_column_resized, _preview_finder_current_row, _fetch_texturepack_preview, _prefetch_texturepack_xml, _setup_filter_menu, _on_all_toggled, _on_item_toggled, _setup_settings_menu, _show_loader_context_menu, _open_loader_rename_dialog, _delete_selected_loader_rows, _show_context_menu, _export_selected_rows, _convert_solidmodel_for_export, clear_all_rows, delete_roblox_db, _delete_selected_rows, eventFilter, _on_loader_selection_changed, _delete_roblox_db_silent, _read_app_settings, _write_app_settings
from .main_loader_rules import _loader_rules_path, _save_loader_rules, _clear_loader_rules, _load_loader_rules, _setup_loader_table, add_row, _kick_finder_sort, _start_wave_insert, _flush_finder_rows, _schedule_proxy_sort, _update_row_creator, _update_row_name, _batch_update_row_names, _batch_update_row_creators, _infer_content_type_from_name, _resolve_use_field, _resolve_replace_field, _get_use_payload, add_rule, _rebuild_loader_index, _load_selected, _update_selected, _load_all_sources, _load_source_rules, _on_source_changed, _create_source, _delete_source, _export_loader_source, _import_loader_source, _rules_to_replacement_rules, _replacement_rules_to_rules, _parse_import_data, _write_data_file, _snapshot_rules, _undo_loader, _push_source_snapshot, _save_column_widths, _load_column_widths, _apply_saved_col_widths, _do_save_col_widths
from .main_preview import display_preview_enhanced, _clear_layout, read_texturepack_xml, _identify_file_type, _get_game_name_from_placeid, _fetch_place_icon_pixmap, _get_extension_for_type, _display_image_preview, _display_audio_preview, _convert_srgb_to_linear, _display_mesh_preview, _convert_mesh_to_obj, _display_3d_model, _display_solidmodel_preview, _parse_obj_vertex_colors, _display_json_preview, _display_localization_preview, _display_text_preview, _display_animation_preview, _display_texture_preview, render_flat_material, _start_new_preview_session, _track_temp, _display_file_info, _add_preview_buttons, close_preview, _delete_preview_temp_files, _open_externally, _select_program_to_open, _format_size
from .main_misc import _sj_temp_root, _safe_name, _make_sj_temp_file, _make_sj_temp_dir
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
    QTextEdit, QFileDialog, QSplitter, QWidgetAction, QStyle, QStyleOptionMenuItem, QComboBox
)
from PySide6.QtGui import QStandardItemModel, QStandardItem, QPixmap, QPainter, QGuiApplication, QPalette, QKeySequence, QShortcut
from PySide6.QtCore import Qt, QObject, QEvent, QPersistentModelIndex, QTimer, QUrl, Signal
import os
import gzip
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


# Local split-out helpers
from shared.constants import CLOG_RAW_URL, ASSET_TYPES, adapter
from shared.utils import strip_cache_header, get_roblosecurity, isnumeric, has_cache_data, get_cache_data, batch_location
from shared.models import SortProxy
from shared.delegates import HoverDelegate
from shared.ui_loader import load_ui
from shared.audio_player import AudioPlayer
from shared.menu_utils import StayOpenMenu
from shared.threading_utils import _MainThreadInvoker
from shared.qt_message_filter import install_qt_message_filter


# Suppress noisy Qt warnings that don't affect functionality.
install_qt_message_filter()


class Main(QObject):
    def __init__(self, tab_widget: QWidget):
        self._invoker = _MainThreadInvoker(None)
        self._desired_column_sizes = {}
        self._adjusting_columns = False
        super().__init__(tab_widget)
        self.tab_widget = tab_widget
        self.base_path = os.path.dirname(os.path.dirname(__file__))

        self._presets_dialog = None
        self._presets_ui = None
        self.presets_search = None
        self.presets_scroll = None
        self.presets_container = None
        self.presets_grid = None
        self._preset_search_timer = None
        self._preset_cards = []
        self._preset_filtered_cards = None

        # Stacked widget
        self.stacked = tab_widget.findChild(QWidget, "stackedWidget")
        self.loader_btn = tab_widget.findChild(QWidget, "CacheLoaderButton")
        self.custom_presets_btn = tab_widget.findChild(
            QWidget, "CustomPresetsButton")
        self.finder_btn = tab_widget.findChild(QWidget, "CacheFinderButton")
        self.presets_btn = tab_widget.findChild(QWidget, "Presets")

        self.loader_btn.clicked.connect(
            lambda: self.stacked.setCurrentIndex(0))
        self.custom_presets_btn.clicked.connect(
            lambda: self.stacked.setCurrentIndex(1))
        self.finder_btn.clicked.connect(
            lambda: self.stacked.setCurrentIndex(2))
        self.presets_btn.clicked.connect(self.open_presets_window)

        # Cache finder
        self.table_view = tab_widget.findChild(QWidget, "tableView")
        self.filter_button = tab_widget.findChild(QWidget, "filterButton")
        self.settings_button = tab_widget.findChild(QWidget, "pushButton_14")
        self.previewFrame = tab_widget.findChild(QWidget, "previewFrame")
        if self.previewFrame:
            self.previewFrame.hide()
        self.clear_button = tab_widget.findChild(QWidget, "ClearButton")
        if self.clear_button:
            self.clear_button.clicked.connect(self.clear_all_rows)
        self.DB_button = tab_widget.findChild(QWidget, "DeleteDBButton")
        if self.DB_button:
            self.DB_button.clicked.connect(self.delete_roblox_db)

        self.splitter = tab_widget.findChild(QSplitter, "splitter")
        if self.splitter:
            self.splitter.splitterMoved.connect(
                lambda pos, index: self._on_column_resized(
                    -1, 0, 0, self.table_view)
            )

        self._setup_table()
        QTimer.singleShot(0, self._run_startup_actions)
        self._setup_filter_menu()
        self._setup_settings_menu()

        # Cache searching wtv
        self.loader_search_loaded = tab_widget.findChild(
            QLineEdit, "lineEdit_2")
        self.loader_search_available = tab_widget.findChild(
            QLineEdit, "SearchAvailableInput")

        def apply_loader_filter():
            text = ""
            if self.loader_search_loaded:
                text = self.loader_search_loaded.text()

            self.loader_proxy.set_search(text, cols=[1, 2, 3])

        if self.loader_search_loaded:
            self.loader_search_loaded.textChanged.connect(
                lambda _: apply_loader_filter())

        if self.loader_search_available:
            self.loader_search_available.textChanged.connect(
                lambda _: apply_loader_filter())

        # Finder/dumper/wtv search
        self.finder_search = tab_widget.findChild(QLineEdit, "lineEdit_5")

        # Column filter checkboxes next to Finder search
        self.finder_cb_name = tab_widget.findChild(QCheckBox, "checkBox_4")
        self.finder_cb_type = tab_widget.findChild(QCheckBox, "checkBox_5")
        self.finder_cb_size = tab_widget.findChild(QCheckBox, "checkBox_6")
        self.finder_cb_date = tab_widget.findChild(QCheckBox, "checkBox_7")
        self.finder_log_cb = tab_widget.findChild(QCheckBox, "checkBox_8")

        for cb in (self.finder_cb_name, self.finder_cb_type, self.finder_cb_size, self.finder_cb_date):
            if cb:
                cb.setChecked(True)

        _finder_saved = _read_app_settings()
        self._log_finder = _finder_saved.get("finder_log", True)
        if self.finder_log_cb:
            self.finder_log_cb.setChecked(self._log_finder)
            self.finder_log_cb.toggled.connect(self._on_finder_log_toggled)

        if self.finder_search:
            self._finder_search_timer = QTimer(self.tab_widget)
            self._finder_search_timer.setSingleShot(True)
            self._finder_search_timer.timeout.connect(self._apply_finder_filters)
            self.finder_search.textChanged.connect(
                lambda _: self._finder_search_timer.start(150))

        for cb in (self.finder_cb_name, self.finder_cb_type, self.finder_cb_size, self.finder_cb_date):
            if cb:
                cb.toggled.connect(lambda _: self._apply_finder_filters())

        # Cache loader
        self.create_cache_btn = tab_widget.findChild(
            QWidget, "CreateCacheButton")
        self.create_cache_btn.clicked.connect(self.open_cache_dialogs)

        self.loader_table = tab_widget.findChild(QWidget, "tableView_2")
        self.sources_combo = tab_widget.findChild(QComboBox, "SourcesComboBox")
        self._current_source_name = "Default"
        self._enabled_sources = None  # None = all sources enabled
        try:
            _p = self._loader_rules_path()
            if _p.exists():
                _d = json.loads(_p.read_text(encoding="utf-8", errors="ignore"))
                if isinstance(_d, dict) and "enabled_sources" in _d:
                    _es = _d["enabled_sources"]
                    self._enabled_sources = set(_es) if isinstance(_es, list) else None
        except Exception:
            pass
        self._setup_loader_table()

        self.apply_selected_btn = tab_widget.findChild(
            QPushButton, "applySelected")
        if self.apply_selected_btn:
            self.apply_selected_btn.clicked.connect(
                self._apply_selected_loader_rows)
        self.delete_db_loader_btn = tab_widget.findChild(
            QPushButton, "DeleteDBLoader")
        if self.delete_db_loader_btn:
            self.delete_db_loader_btn.clicked.connect(self.delete_roblox_db)

        self.load_selected_btn = tab_widget.findChild(
            QPushButton, "LoadSelected")
        if self.load_selected_btn:
            self.load_selected_btn.clicked.connect(self._load_selected)
        self.update_selected_btn = tab_widget.findChild(
            QPushButton, "UpdateSelected")
        if self.update_selected_btn:
            self.update_selected_btn.clicked.connect(self._update_selected)

        self.create_source_btn = tab_widget.findChild(
            QPushButton, "CreateSource")
        if self.create_source_btn:
            self.create_source_btn.clicked.connect(self._create_source)
        self.delete_source_btn = tab_widget.findChild(
            QPushButton, "DeleteSource")
        if self.delete_source_btn:
            self.delete_source_btn.clicked.connect(self._delete_source)
        if self.sources_combo:
            self.sources_combo.currentTextChanged.connect(
                self._on_source_changed)

        self.enabled_sources_btn = tab_widget.findChild(
            QPushButton, "EnabledSources")
        if self.enabled_sources_btn:
            self.enabled_sources_btn.clicked.connect(
                self._show_enabled_sources_menu)

        self.replace_all_x_btn = tab_widget.findChild(QPushButton, "ReplaceAllX")
        if self.replace_all_x_btn:
            self.replace_all_x_btn.clicked.connect(self._show_replace_all_x_menu)

        undo_shortcut = QShortcut(QKeySequence.StandardKey.Undo, self.tab_widget)
        undo_shortcut.setContext(Qt.WidgetWithChildrenShortcut)
        undo_shortcut.activated.connect(self._undo_loader)

        self.info_label = None

        def _find_info_label():
            self.info_label = tab_widget.window().findChild(QLabel, "InfoLabel")
            if self.info_label:
                self.info_label.setText(
                    f"Caches in cache finder: {self.model.rowCount()}")
        QTimer.singleShot(0, _find_info_label)

        self.splitter_2 = tab_widget.findChild(QSplitter, "splitter_2")
        self.previewWindow1 = tab_widget.findChild(QWidget, "PreviewWindow1")
        self.previewWindow1_2 = tab_widget.findChild(
            QWidget, "PreviewWindow1_2")
        self.replace_ids_lineedit = tab_widget.findChild(QLineEdit, "lineEdit")
        self.replace_with_lineedit = tab_widget.findChild(
            QLineEdit, "lineEdit_3")

        self.import_from_file_btn = tab_widget.findChild(
            QPushButton, "pushButton_4")
        if self.import_from_file_btn:
            self.import_from_file_btn.clicked.connect(self.import_from_file)
        self.replace_with_lineedit = tab_widget.findChild(
            QLineEdit, "lineEdit_3")

        if self.splitter_2 and self.loader_table:
            self.splitter_2.splitterMoved.connect(
                lambda *_: QTimer.singleShot(
                    0, lambda: self._on_column_resized(-1,
                                                       0, 0, self.loader_table)
                )
            )

        try:
            if self.loader_table and self.loader_table.selectionModel():
                self.loader_table.selectionModel().selectionChanged.connect(
                    self._on_loader_selection_changed
                )
        except Exception as e:
            print("[UI] selection connect failed:", e)

        # Custom presets
        self.preset_tree = tab_widget.findChild(QWidget, "treeView")
        self.create_preset_btn = tab_widget.findChild(
            QWidget, "CreatePresetButton")
        self.apply_preset_btn = tab_widget.findChild(
            QWidget, "ApplyPresetButton")

        self._setup_preset_tree()

        self.create_preset_btn.clicked.connect(self.create_preset)
        self.apply_preset_btn.clicked.connect(self.apply_preset)

        self.export_preset_btn = tab_widget.findChild(QPushButton, "ExportCustomPreset")
        if self.export_preset_btn:
            self.export_preset_btn.clicked.connect(self._export_preset)
        self.import_preset_btn = tab_widget.findChild(QPushButton, "ImportCustomPreset")
        if self.import_preset_btn:
            self.import_preset_btn.clicked.connect(self._import_preset)

        self.delivery_endpoint = "/v2/assets/batch"

        self._cache_index_lock = threading.Lock()
        self._cache_index_pending = {}
        self._cache_index_timer = None

        self.cache_logs = {}
        self.temp_files = {}
        self._preview_token = {}
        self._preview_state = {}
        self._frame_preview_gen = {}

        self.net = requests.Session()
        self.net.trust_env = False
        self.net.proxies = {}
        self.net.headers.update({"User-Agent": "Mozilla/5.0"})

        self._replace_preview_ids = []
        self._replace_preview_idx = 0
        self._uses_content_frame = None
        self._replaces_content_frame = None
        self._setup_loader_preview_windows()

        threading.Thread(target=self.name_resolver_loop, daemon=True).start()
        threading.Thread(target=self.creator_resolver_loop,
                         daemon=True).start()

        pygame.mixer.init()
        self.persistent_volume = 1.0
        self.audio_players = {}
        tools_dir = os.path.join(self.base_path, "tools")
        self.rojo_path = os.path.join(tools_dir, "rojo", "rojo.exe")
        self.animpreview_script = os.path.join(
            tools_dir, "animpreview", "animpreview.py")
        self.animpreview_project_template = os.path.join(
            tools_dir, "animpreview", "default.project.json")

        self.animpreview_r15_rig = os.path.join(
            tools_dir, "animpreview", "R15Rig.rbxmx")
        self.animpreview_r6_rig = os.path.join(
            tools_dir, "animpreview", "R6Rig.rbxmx")

        self.temp_dirs = {}

    def _on_main(self, fn):
        inv = getattr(self, '_invoker', None)
        if inv is not None:
            inv.call.emit(fn)
            return
        try:
            QTimer.singleShot(0, fn)
        except Exception as e:
            import traceback
            traceback.print_exc()

    # Dialog flow

    def _show_replace_all_x_menu(self):
        le = getattr(self, "replace_ids_lineedit", None)

        # Parse which type names are already selected in the lineedit.
        already_checked = set()
        if le:
            for part in self._split_csv(le.text()):
                p = part.strip()
                if p.lower().startswith("type:"):
                    already_checked.add(p[5:].strip().lower())

        menu = StayOpenMenu(self.tab_widget)
        menu.setStyleSheet("QMenu { menu-scrollable: 1; }")

        actions = {}  # type_name -> QAction
        for _type_id, type_name in ASSET_TYPES:
            act = menu.addAction(type_name)
            act.setCheckable(True)
            act.setChecked(type_name.lower() in already_checked)
            actions[type_name] = act

        def _apply():
            if le is None:
                return
            selected = [name for name, act in actions.items() if act.isChecked()]
            # Keep any non-type entries already in the lineedit (numeric IDs etc.)
            existing_non_type = [
                p.strip() for p in self._split_csv(le.text())
                if not p.strip().lower().startswith("type:")
            ]
            type_parts = [f"type: {name}" for name in selected]
            all_parts = existing_non_type + type_parts
            le.setText(", ".join(all_parts))

        menu.aboutToHide.connect(_apply)

        btn = self.replace_all_x_btn
        menu.exec(btn.mapToGlobal(btn.rect().bottomLeft()))

    def _show_enabled_sources_menu(self):
        btn = getattr(self, "enabled_sources_btn", None)
        if btn is None:
            return

        enabled = getattr(self, "_enabled_sources", None)  # None = all enabled
        current = getattr(self, "_current_source_name", "Default")
        try:
            all_sources = self._load_all_sources()
        except Exception:
            all_sources = {}

        menu = StayOpenMenu(btn)
        menu.setStyleSheet("QMenu { menu-scrollable: 1; }")

        source_actions = {}
        for source_name in all_sources.keys():
            label = f"{source_name} (active)" if source_name == current else source_name
            act = menu.addAction(label)
            act.setCheckable(True)
            act.setChecked(enabled is None or source_name in enabled)
            source_actions[source_name] = act

        def _on_toggle():
            new_enabled = {
                name for name, act in source_actions.items() if act.isChecked()
            }
            self._enabled_sources = None if len(new_enabled) == len(source_actions) else new_enabled
            self._write_data_file(enabled_sources=self._enabled_sources)
            self._rebuild_loader_index()

        for act in source_actions.values():
            act.toggled.connect(lambda _: _on_toggle())

        menu.exec(btn.mapToGlobal(btn.rect().bottomLeft()))

    def open_cache_dialogs(self):
        from PySide6.QtWidgets import QInputDialog, QMessageBox

        name, ok = QInputDialog.getText(
            self.tab_widget, "Create Cache", "Cache name:")
        if not ok:
            return

        name = (name or "").strip()
        if not name:
            return

        use = ""
        replace = ""

        try:
            replace = (self.replace_ids_lineedit.text() or "").strip()
        except Exception:
            pass

        try:
            use = (self.replace_with_lineedit.text() or "").strip()
        except Exception:
            pass

        if not use:
            use = "0"

        if not replace:
            QMessageBox.warning(
                self.tab_widget,
                "Missing info",
                "Fill in Replace IDs (comma separated), then click Create Cache again."
            )
            return

        self.add_rule(True, name, use, replace)
        self.replace_ids_lineedit.clear()
        self.replace_with_lineedit.clear()

    def import_from_file(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self.tab_widget,
            "Select file to import",
            "",
            "All Files (*)"
        )
        if not file_path:
            return

        if getattr(self, "replace_with_lineedit", None):
            self.replace_with_lineedit.setText(file_path)
        else:
            print("[IMPORT] replace_with_lineedit not found")
        return

    # Cache finder

    def _run_startup_actions(self):
        settings = _read_app_settings()
        if settings.get("del_db_on_start"):
            self._delete_roblox_db_silent()
        self._load_persistent_cache()
        if settings.get("clear_finder_on_start"):
            # _load_persistent_cache batches rows via _on_main (queued signal).
            # Flush them synchronously first so cache_logs is fully populated
            # and the model has rows, then clear — same as pressing the button.
            self._flush_finder_rows()
            self.clear_all_rows()

    def _setup_loader_preview_windows(self):
        """Set up inner content frames for the two loader preview panes."""
        pw1 = getattr(self, "previewWindow1", None)
        if pw1 is not None:
            outer = QVBoxLayout(pw1)
            outer.setContentsMargins(0, 0, 0, 0)
            outer.setSpacing(0)
            self._uses_content_frame = QFrame(pw1)
            self._uses_content_frame.setFrameShape(QFrame.NoFrame)
            self._uses_content_frame.setLayout(QVBoxLayout())
            self._uses_content_frame.layout().setContentsMargins(0, 0, 0, 0)
            outer.addWidget(self._uses_content_frame, 1)
            pw1.hide()

        pw2 = getattr(self, "previewWindow1_2", None)
        if pw2 is not None:
            outer = QVBoxLayout(pw2)
            outer.setContentsMargins(0, 0, 0, 0)
            outer.setSpacing(0)
            self._replaces_content_frame = QFrame(pw2)
            self._replaces_content_frame.setFrameShape(QFrame.NoFrame)
            self._replaces_content_frame.setLayout(QVBoxLayout())
            self._replaces_content_frame.layout().setContentsMargins(0, 0, 0, 0)
            outer.addWidget(self._replaces_content_frame, 1)
            pw2.hide()

    def _navigate_replace_preview(self, delta):
        ids = getattr(self, "_replace_preview_ids", [])
        if not ids:
            return
        idx = max(0, min(len(ids) - 1, getattr(self,
                  "_replace_preview_idx", 0) + delta))
        self._replace_preview_idx = idx
        frame = getattr(self, "_replaces_content_frame", None)
        if frame:
            self._load_asset_for_preview(ids[idx], frame)

    def _apply_selected_loader_rows(self):
        tv = getattr(self, "loader_table", None)
        if tv is None:
            return
        selected = tv.selectionModel().selectedRows() if tv.selectionModel() else []
        for proxy_idx in selected:
            src_idx = self.loader_proxy.mapToSource(proxy_idx)
            item = self.loader_model.item(src_idx.row(), 0)
            if item is None:
                continue
            item.setCheckState(Qt.Unchecked if item.checkState()
                               == Qt.Checked else Qt.Checked)

    def _display_obj_file_preview(self, obj_path, content_frame):
        self._frame_preview_gen = getattr(self, "_frame_preview_gen", {})
        gen = self._frame_preview_gen.get(content_frame, 0) + 1
        self._frame_preview_gen[content_frame] = gen
        if not content_frame.layout():
            content_frame.setLayout(QVBoxLayout())
        self._on_main(lambda g=gen: self._display_3d_model(
            obj_path, content_frame, g))
        content_frame.show()

    def _reset_content_frame(self, frame):
        """Clear an inner content frame without hiding the outer wrapper."""
        if frame in getattr(self, "audio_players", {}):
            try:
                self.audio_players[frame].stop()
            except Exception:
                pass
            try:
                del self.audio_players[frame]
            except Exception:
                pass
        plotter = getattr(self, "_plotters", {}).pop(frame, None)
        if plotter is not None:
            try:
                plotter.close()
            except Exception:
                pass
            try:
                plotter.deleteLater()
            except Exception:
                pass
        layout = frame.layout()
        if layout:
            while layout.count():
                child = layout.takeAt(0)
                w = child.widget()
                if w:
                    w.deleteLater()
                elif child.layout():
                    while child.layout().count():
                        sub = child.layout().takeAt(0)
                        if sub.widget():
                            sub.widget().deleteLater()
                    child.layout().deleteLater()
        if hasattr(self, "_preview_state"):
            self._preview_state.pop(frame, None)
        if hasattr(self, "_preview_token"):
            self._preview_token.pop(frame, None)

    def _load_asset_for_preview(self, asset_id_str, content_frame):
        """Fetch asset bytes (from cache_logs or Roblox CDN) and show preview."""
        try:
            asset_id_int = int(str(asset_id_str).strip())
        except (ValueError, TypeError):
            return

        cache_info = self.cache_logs.get(asset_id_int)
        is_texturepack = isinstance(
            cache_info, dict) and cache_info.get("assetTypeId") == 63
        if is_texturepack:
            xml_data = cache_info.get("texturepack_xml")
            if xml_data:
                asset_name = cache_info.get("resolved_name")
                self.display_preview_enhanced(
                    xml_data, 63, asset_id_int, asset_name, content_frame)
                return
        elif cache_info and has_cache_data(cache_info):
            cache_data = get_cache_data(cache_info)
            asset_type_id = cache_info.get("assetTypeId", 0)
            asset_name = cache_info.get("resolved_name")
            self.display_preview_enhanced(
                cache_data, asset_type_id, asset_id_int, asset_name, content_frame)
            return

        # Not in cache - fetch from Roblox CDN in background
        from shared.utils import get_roblosecurity
        import threading as _threading

        def _bg():
            try:
                cookie = get_roblosecurity()
                sess = self._new_session(cookie)
                bypass_headers = {"X-Preview-Bypass": "1"}
                r = sess.post(
                    "https://assetdelivery.roblox.com/v2/assets/batch",
                    json=[{"assetId": asset_id_int, "requestId": "1"}],
                    timeout=10,
                    headers=bypass_headers,
                )
                if not r.ok:
                    return
                d = r.json()
                loc = batch_location(d[0]) if isinstance(d, list) and d else ""
                if not loc:
                    return
                resp = sess.get(loc, timeout=10,
                                headers=bypass_headers)
                if not resp.ok:
                    return
                content = resp.content
                # Cache the fetched data so future selections skip the network
                # round-trip and use the fast synchronous path instead.
                ci = self.cache_logs.setdefault(asset_id_int, {})
                if not has_cache_data(ci):
                    try:
                        import tempfile as _tf, os as _os
                        tmp_fd, tmp_path = _tf.mkstemp(suffix=".rbxcache", prefix="sj_cache_")
                        with _os.fdopen(tmp_fd, "wb") as _f:
                            _f.write(content)
                        ci["cache_data_path"] = tmp_path
                    except Exception:
                        ci["cache_data"] = content
                    ci.setdefault("assetTypeId", 0)
                # Use _on_main (queued signal) rather than QTimer.singleShot so
                # the callback is reliably posted to the main thread even when
                # called from a Python background thread (which has no Qt event
                # loop of its own).
                self._on_main(lambda c=content: self.display_preview_enhanced(
                    c, 0, asset_id_int, None, content_frame
                ))
            except Exception as e:
                print(f"[Loader Preview] fetch failed for {asset_id_int}: {e}")

        _threading.Thread(target=_bg, daemon=True).start()


# Attach extracted methods

Main._make_sj_temp_dir = _make_sj_temp_dir
Main._make_sj_temp_file = _make_sj_temp_file
Main._safe_name = _safe_name
Main._sj_temp_root = _sj_temp_root
Main._add_preview_buttons = _add_preview_buttons
Main._convert_mesh_to_obj = _convert_mesh_to_obj
Main._convert_srgb_to_linear = _convert_srgb_to_linear
Main._delete_preview_temp_files = _delete_preview_temp_files
Main._display_3d_model = _display_3d_model
Main._display_solidmodel_preview = _display_solidmodel_preview
Main._display_animation_preview = _display_animation_preview
Main._display_audio_preview = _display_audio_preview
Main._display_file_info = _display_file_info
Main._display_image_preview = _display_image_preview
Main._display_json_preview = _display_json_preview
Main._display_localization_preview = _display_localization_preview
Main._clear_layout = _clear_layout
Main._display_mesh_preview = _display_mesh_preview
Main._display_text_preview = _display_text_preview
Main._display_texture_preview = _display_texture_preview
Main._fetch_place_icon_pixmap = _fetch_place_icon_pixmap
Main._format_size = _format_size
Main._get_extension_for_type = _get_extension_for_type
Main._get_game_name_from_placeid = _get_game_name_from_placeid
Main._identify_file_type = _identify_file_type
Main._open_externally = _open_externally
Main._select_program_to_open = _select_program_to_open
Main._start_new_preview_session = _start_new_preview_session
Main._track_temp = _track_temp
Main.close_preview = close_preview
Main.display_preview_enhanced = display_preview_enhanced
Main.read_texturepack_xml = read_texturepack_xml
Main.render_flat_material = render_flat_material
Main._clear_loader_rules = _clear_loader_rules
Main._get_use_payload = _get_use_payload
Main._infer_content_type_from_name = _infer_content_type_from_name
Main._load_loader_rules = _load_loader_rules
Main._loader_rules_path = _loader_rules_path
Main._resolve_replace_field = _resolve_replace_field
Main._resolve_use_field = _resolve_use_field
Main._save_loader_rules = _save_loader_rules
Main._setup_loader_table = _setup_loader_table
Main._update_row_creator = _update_row_creator
Main._update_row_name = _update_row_name
Main._batch_update_row_names = _batch_update_row_names
Main._batch_update_row_creators = _batch_update_row_creators
Main.add_row = add_row
Main._kick_finder_sort = _kick_finder_sort
Main._start_wave_insert = _start_wave_insert
Main._flush_finder_rows = _flush_finder_rows
Main._schedule_proxy_sort = _schedule_proxy_sort
Main.add_rule = add_rule
Main._rebuild_loader_index = _rebuild_loader_index
Main._load_selected = _load_selected
Main._update_selected = _update_selected
Main._load_all_sources = _load_all_sources
Main._load_source_rules = _load_source_rules
Main._on_source_changed = _on_source_changed
Main._create_source = _create_source
Main._delete_source = _delete_source
Main._export_loader_source = _export_loader_source
Main._import_loader_source = _import_loader_source
Main._write_data_file = _write_data_file
Main._save_column_widths = _save_column_widths
Main._load_column_widths = _load_column_widths
Main._apply_saved_col_widths = _apply_saved_col_widths
Main._do_save_col_widths = _do_save_col_widths
Main._snapshot_rules = _snapshot_rules
Main._undo_loader = _undo_loader
Main._push_source_snapshot = _push_source_snapshot
Main._delete_selected_loader_rows = _delete_selected_loader_rows
Main._delete_selected_rows = _delete_selected_rows
Main._export_selected_rows = _export_selected_rows
Main._convert_solidmodel_for_export = _convert_solidmodel_for_export
Main._on_all_toggled = _on_all_toggled
Main._on_column_resized = _on_column_resized
Main._preview_finder_current_row = _preview_finder_current_row
Main._fetch_texturepack_preview = _fetch_texturepack_preview
Main._prefetch_texturepack_xml = _prefetch_texturepack_xml
Main._on_item_toggled = _on_item_toggled
Main._on_loader_selection_changed = _on_loader_selection_changed
Main._open_loader_rename_dialog = _open_loader_rename_dialog
Main._setup_filter_menu = _setup_filter_menu
Main._setup_settings_menu = _setup_settings_menu
Main._setup_table = _setup_table
Main._show_context_menu = _show_context_menu
Main._show_loader_context_menu = _show_loader_context_menu
Main.clear_all_rows = clear_all_rows
Main.delete_roblox_db = delete_roblox_db
Main._delete_roblox_db_silent = _delete_roblox_db_silent
Main.eventFilter = eventFilter
Main._apply_finder_filters = _apply_finder_filters
Main._build_finder_conditions = _build_finder_conditions
Main._parse_size_to_bytes = _parse_size_to_bytes
Main._add_json_to_qtree = _add_json_to_qtree
Main._apply_preset_from_window = _apply_preset_from_window
Main._apply_presets_search_filter = _apply_presets_search_filter
Main._collect_leaf_paths = _collect_leaf_paths
Main._fetch_and_flatten_urls = _fetch_and_flatten_urls
Main._fetch_clog_json = _fetch_clog_json
Main._fetch_json_url = _fetch_json_url
Main._flatten_json = _flatten_json
Main._load_2nd_presets_ui_class = _load_2nd_presets_ui_class
Main._load_remote_presets = _load_remote_presets
Main._normalize_games_from_clog = _normalize_games_from_clog
Main._open_preset_window = _open_preset_window
Main._populate_test_preset_cards = _populate_test_preset_cards
Main._relayout_preset_cards = _relayout_preset_cards
Main._resolve_caches_for_game = _resolve_caches_for_game
Main._set_splitter2_mode = _set_splitter2_mode
Main._setup_preset_tree = _setup_preset_tree
Main._short_url_label = _short_url_label
Main.add_preset = add_preset
Main._save_presets = _save_presets
Main._load_presets = _load_presets
Main._open_url_picker = _open_url_picker
Main._custom_dumps_dir = _custom_dumps_dir
Main._load_custom_game_entries = _load_custom_game_entries
Main._add_game_card_from_entry = _add_game_card_from_entry
Main._open_add_game_dump_dialog = _open_add_game_dump_dialog
Main._custom_card_context_menu = _custom_card_context_menu
Main._delete_custom_dump_card = _delete_custom_dump_card
Main._show_preset_context_menu = _show_preset_context_menu
Main._export_preset = _export_preset
Main._import_preset = _import_preset
Main.apply_preset = apply_preset
Main.create_preset = create_preset
Main.open_presets_window = open_presets_window
Main._on_export_converted_toggled = _on_export_converted_toggled
Main._on_export_raw_toggled = _on_export_raw_toggled
Main._on_show_names_toggled = _on_show_names_toggled


def _on_finder_log_toggled(self, checked):
    self._log_finder = checked
    _write_app_settings({**_read_app_settings(), "finder_log": checked})


Main._on_finder_log_toggled = _on_finder_log_toggled
Main.creator_resolver_loop = creator_resolver_loop
Main.fetch_and_process = fetch_and_process
Main.fetch_asset_names = fetch_asset_names
Main.fetch_creator_names = fetch_creator_names
Main.name_resolver_loop = name_resolver_loop
Main.process_asset_row = process_asset_row
Main._cache_dir = _cache_dir
Main._cache_index_path = _cache_index_path
Main._get_cache_bin_path = _get_cache_bin_path
Main._queue_cache_index_update = _queue_cache_index_update
Main._flush_cache_index = _flush_cache_index
Main._delete_cache_entry = _delete_cache_entry
Main._load_persistent_cache = _load_persistent_cache
Main._new_session = _new_session
Main._split_csv = _split_csv
Main.event = event
Main.parse_body = parse_body
Main.rebuild_body = rebuild_body
Main.request = request
Main.response = response
