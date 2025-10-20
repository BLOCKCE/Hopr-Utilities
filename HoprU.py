# SubplaceJoiner_Qt.py (patched v2)
# PySide6 UI + join flow fixes + persistence fixes

import uuid
import json
from PySide6.QtCore import QObject, Signal, Qt, QTimer
import time
import sys
import os
import json
import uuid
import threading
import platform
import webbrowser
import subprocess
import base64
import re
import stat
import ctypes
import struct
import socket
from urllib.parse import urlparse, urlunparse
from ctypes import wintypes
from datetime import datetime, timezone
from pathlib import Path
from io import BytesIO

# --- ensure Requests ignores system proxies to avoid hangs ---

import requests
import asyncio
from PIL import Image, ImageDraw
try:
    from PIL.ImageQt import ImageQt
except Exception:
    ImageQt = None

# Optional deps used opportunistically
try:
    import psutil
except Exception:
    psutil = None

try:
    from mitmproxy import http  # type: ignore
    from mitmproxy.options import Options  # type: ignore
    from mitmproxy.tools.dump import DumpMaster  # type: ignore
    import mitmproxy.proxy.mode_servers as mode_servers
    MITM_AVAILABLE = True
except Exception:
    MITM_AVAILABLE = False

try:
    import win32crypt  # type: ignore
except Exception:
    win32crypt = None

from PySide6.QtCore import Qt, QSize, QEvent, QTimer, QRectF, Signal, QObject
from PySide6.QtGui import QFont, QPalette, QColor, QFontMetrics, QPainter, QPixmap, QImage, QPen
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QLabel, QLineEdit, QPushButton,
    QHBoxLayout, QVBoxLayout, QGridLayout, QScrollArea, QSplitter, QCheckBox,
    QFrame, QSizePolicy, QGraphicsDropShadowEffect, QMenu, QTextEdit,
    QColorDialog, QSlider, QWidgetAction, QSplitterHandle, QTabWidget, QTabBar,
    QDialog, QDialogButtonBox
)

# ==================== GLOBAL VARIBLES ====================

PROXY = None
ENABLE_GAME_JOIN_INTERCEPT = False
ENABLE_RESERVED_GAME_JOIN_INTERCEPT = False

LAST_accessCode = None
LAST_placeId = None
LAST_jobId = None

# ==================== ADMIN ====================


def ensure_admin_in_powershell():
    try:
        is_admin = ctypes.windll.shell32.IsUserAnAdmin()
    except Exception:
        is_admin = False

    if not is_admin:
        print("Requesting Administrator PowerShell...")

        # Absolute path to current script
        script = os.path.abspath(sys.argv[0])

        # Properly quote all arguments for PowerShell
        args = " ".join(shlex.quote(a) for a in sys.argv[1:])

        # Escape double quotes for PowerShell
        py_path = script.replace('"', '`"')
        exe_path = sys.executable.replace('"', '`"')

        # Construct a fully escaped PowerShell command
        # Using call operator (&) and enclosing everything in single quotes
        ps_command = f"& '{exe_path}' '{py_path}' {args}"

        # Wrap the command inside quotes to protect spaces and special characters
        full_command = f'-ExecutionPolicy Bypass -Command "{ps_command}"'

        powershell_exe = r"C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe"

        # Launch elevated PowerShell
        ctypes.windll.shell32.ShellExecuteW(
            None,
            "runas",
            powershell_exe,
            full_command,
            None,
            1
        )

        sys.exit(0)


ensure_admin_in_powershell()


# ==================== Theming helpers ====================


def _safe_set_dpi_policy():
    try:
        policy_enum = getattr(Qt, "HighDpiScaleFactorRoundingPolicy", None)
        if policy_enum and hasattr(policy_enum, "PassThrough"):
            QApplication.setHighDpiScaleFactorRoundingPolicy(
                policy_enum.PassThrough)
    except Exception:
        pass


def make_shadow(blur=28, dx=0, dy=8, color=QColor(0, 0, 0, 160)):
    eff = QGraphicsDropShadowEffect()
    eff.setBlurRadius(blur)
    eff.setOffset(dx, dy)
    eff.setColor(color)
    return eff


COLORS = {
    "bg_hi": "#151b25",
    "bg": "#12161B",
    "panel_top": "#161B24",
    "panel_bot": "#12161B",
    "border": "rgba(255,255,255,20)",
    "text": "#E5EAF1",
    "muted": "#8594AA",
    "title": "#BFD1FF",
    "chip_bg": "rgba(255,255,255,14)",
    "chip_border": "rgba(255,255,255,22)",
    "input_bg": "#0F131A",
    "accent": "#3B82F6",
    "ghost_bg": "rgba(255,255,255,18)",
    "ghost_border": "rgba(255,255,255,26)"
}


def gen_styles(text_color=None, btn_color=None):
    t = text_color or COLORS["text"]
    accent = btn_color or COLORS["accent"]
    return f"""
        QWidget {{ color: {t}; font-size: 13px; }}
        QLabel#Caption {{ color: {COLORS["muted"]}; }}
        QLabel#CardTitle {{ color: {COLORS["title"]}; letter-spacing: .3px; }}

        QFrame#HeroCard {{
            background: qlineargradient(x1:0,y1:0,x2:0,y2:1, stop:0 {COLORS["bg_hi"]}, stop:1 {COLORS["bg"]});
            border: 1px solid {COLORS["border"]};
            border-radius: 18px;
        }}
        QLabel#HeroSubtitle {{ color: #9bb0d1; }}

        QFrame#Card {{
            background: qlineargradient(x1:0,y1:0,x2:0,y2:1, stop:0 {COLORS["panel_top"]}, stop:1 {COLORS["panel_bot"]});
            border: 1px solid {COLORS["border"]};
            border-radius: 16px;
        }}

        ChromeTabWidget {{
            background: {COLORS["bg"]};
            border: none;
        }}
        
        ChromeTabWidget::pane {{
            border: none;
            background: transparent;
        }}
        
        ChromeTabBar {{
            background: {COLORS["bg"]};
            border: none;
            min-height: 36px;
        }}
        
        ChromeTabBar::tab {{
            background: rgba(255,255,255,8);
            border: 1px solid rgba(255,255,255,12);
            border-bottom: none;
            border-top-left-radius: 8px;
            border-top-right-radius: 8px;
            padding: 8px 16px 6px 16px;
            margin-right: 2px;
            color: {COLORS["muted"]};
            min-width: 120px;
            max-width: 200px;
        }}
        
        ChromeTabBar::tab:selected {{
            background: {COLORS["panel_top"]};
            border: 1px solid {COLORS["border"]};
            border-bottom: none;
            color: {t};
        }}
        
        ChromeTabBar::tab:hover:!selected {{
            background: rgba(255,255,255,15);
            color: {COLORS["text"]};
        }}

        QPushButton#AccentButton {{
            background: {accent}; color: #EAF2FF; border: none;
            border-radius: 12px; padding: 0 12px; font-weight: 600;
            min-height: 34px; max-height: 34px;
        }}

        QPushButton#GhostButton {{
            background: {COLORS["ghost_bg"]}; color: #CFD6E4;
            border: 1px solid {COLORS["ghost_border"]};
            border-radius: 17px; padding: 0 12px;
            min-height: 34px; max-height: 34px;
            font-weight: 600;
        }}

        QPushButton#TabAddButton {{
            background: rgba(255,255,255,8);
            border: 1px solid rgba(255,255,255,12);
            border-radius: 8px;
            color: {COLORS["muted"]};
            font-size: 16px;
            font-weight: bold;
            min-width: 30px;
            max-width: 30px;
            min-height: 30px;
            max-height: 30px;
            margin: 3px;
        }}
        
        QPushButton#TabAddButton:hover {{
            background: rgba(255,255,255,20);
            color: {t};
        }}

        QPushButton#Chip {{
            background: {COLORS["chip_bg"]};
            border: 1px solid {COLORS["chip_border"]};
            border-radius: 14px;
            padding: 0 12px;
            color: #D9E1F2;
            min-height: 28px; max-height: 28px;
        }}

        QCheckBox#PillCheck {{
            color: #CFD6E4 !important;
            background: {COLORS["ghost_bg"]};
            border: 1px solid {COLORS["ghost_border"]};
            border-radius: 17px;
            padding: 0 12px;
            min-height: 34px; max-height: 34px;
            font-weight: 600;
        }}
        QCheckBox#PillCheck::indicator {{
            width: 14px; height: 14px; border-radius: 7px;
            border: 1px solid {COLORS["ghost_border"]};
            background: {COLORS["ghost_bg"]};
            margin: 0 8px 0 0;
        }}
        QCheckBox#PillCheck::indicator:checked {{
            background: {accent}; border: 1px solid {accent};
        }}

        QLineEdit#Search {{
            border-radius: 12px;
            border: 1px solid {COLORS["ghost_border"]};
            background: {COLORS["input_bg"]};
            padding: 9px 12px;
            color: {t};
            selection-background-color: #2563EB;
            selection-color: white;
            min-height: 16px; max-height: 16px;
        }}

        QTextEdit#CodeEditor {{
            background: {COLORS["input_bg"]};
            border: 1px solid {COLORS["ghost_border"]};
            border-radius: 8px;
            color: {t};
            font-family: 'Consolas', 'Monaco', 'Courier New', monospace;
            font-size: 12px;
            selection-background-color: #2563EB;
            selection-color: white;
        }}

        QFrame#PlaceCard {{
            background: #141924;
            border: 1px solid rgba(255,255,255,18);
            border-radius: 14px;
        }}
        QLabel#Thumb {{
            background: rgba(255,255,255,14);
            border-radius: 12px;
        }}

        QScrollArea {{ border: none; background: transparent; }}
        QScrollBar:vertical, QScrollBar:horizontal {{ width: 0px; height: 0px; }}
    """


def set_app_palette(app, theme):
    pal = app.palette()
    if theme == "light":
        pal.setColor(QPalette.Window, QColor(245, 247, 250))
        pal.setColor(QPalette.Base, QColor(255, 255, 255))
        pal.setColor(QPalette.Button, QColor(248, 249, 250))
        pal.setColor(QPalette.ButtonText, QColor(25, 28, 33))
        pal.setColor(QPalette.Text, QColor(25, 28, 33))
        pal.setColor(QPalette.WindowText, QColor(25, 28, 33))
    elif theme == "dark":
        pal.setColor(QPalette.Window, QColor(12, 14, 18))
        pal.setColor(QPalette.Base, QColor(18, 21, 27))
        pal.setColor(QPalette.Button, QColor(26, 30, 38))
        pal.setColor(QPalette.ButtonText, QColor(235, 239, 245))
        pal.setColor(QPalette.Text, QColor(235, 239, 245))
        pal.setColor(QPalette.WindowText, QColor(235, 239, 245))
    app.setPalette(pal)


# ---------------- custom splitter ----------------
HANDLE_HIT = 10
HANDLE_LINE = 2
HANDLE_GUTTER = (HANDLE_HIT - HANDLE_LINE) // 2


class ThinHandle(QSplitterHandle):
    def __init__(self, o, parent):
        super().__init__(o, parent)

    def paintEvent(self, ev):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        w = self.width()
        x = (w - HANDLE_LINE) / 2.0
        r = QRectF(x, 0.0, HANDLE_LINE, self.height())
        color = QColor(255, 255, 255, 30)
        p.setPen(Qt.NoPen)
        p.setBrush(color)
        p.drawRoundedRect(r, 1.6, 1.6)


class ThinSplitter(QSplitter):
    def __init__(self, orientation):
        super().__init__(orientation)
        self.setOpaqueResize(True)

    def createHandle(self):
        return ThinHandle(self.orientation(), self)

# ---------------- micro-widgets ----------------


class Card(QFrame):
    def __init__(self, title=None, object_name="Card", parent=None):
        super().__init__(parent)
        self.setObjectName(object_name)
        self._shadow = make_shadow()
        self.setGraphicsEffect(self._shadow)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        self._l = QVBoxLayout(self)
        self._l.setContentsMargins(16, 16, 16, 16)
        self._l.setSpacing(12)
        if title:
            t = QLabel(title)
            f = QFont()
            f.setPointSize(11)
            f.setBold(True)
            t.setFont(f)
            t.setObjectName("CardTitle")
            t.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
            self._l.addWidget(t)

    def body(self): return self._l


class AccentButton(QPushButton):
    def __init__(self, text):
        super().__init__(text)
        self.setObjectName("AccentButton")
        self.setCursor(Qt.PointingHandCursor)
        self.setMinimumHeight(34)
        self.setMaximumHeight(34)
        self.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)


class GhostButton(QPushButton):
    def __init__(self, text):
        super().__init__(text)
        self.setObjectName("GhostButton")
        self.setCursor(Qt.PointingHandCursor)
        self.setMinimumHeight(34)
        self.setMaximumHeight(34)
        self.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)


class PillCheck(QCheckBox):
    def __init__(self, text):
        super().__init__(text)
        self.setObjectName("PillCheck")
        self.setCursor(Qt.PointingHandCursor)
        self.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        self.setMinimumHeight(34)
        self.setMaximumHeight(34)
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setAutoFillBackground(False)


class Chip(QPushButton):
    def __init__(self, text, width=110, min_pt=9.0, base_pt=12.0):
        super().__init__(text)
        self.setObjectName("Chip")
        self.setCursor(Qt.PointingHandCursor)
        self._chip_width = width
        self._min_pt = min_pt
        self._base_pt = base_pt
        self.setFixedWidth(self._chip_width)
        self.setMinimumHeight(28)
        self.setMaximumHeight(28)
        self.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setAutoFillBackground(True)
        self._fit_text()

    def _fit_text(self):
        padding = 24
        max_text = max(10, self._chip_width - padding)
        f = self.font()
        f.setPointSizeF(self._base_pt)
        fm = QFontMetrics(f)
        while fm.horizontalAdvance(self.text()) > max_text and f.pointSizeF() > self._min_pt:
            f.setPointSizeF(f.pointSizeF() - 0.5)
            fm = QFontMetrics(f)
        self.setFont(f)

    def setChipWidth(self, w):
        self._chip_width = int(w)
        self.setFixedWidth(self._chip_width)
        self._fit_text()


class Search(QLineEdit):
    def __init__(self, ph):
        super().__init__()
        self.setObjectName("Search")
        self.setPlaceholderText(ph)
        self.setMinimumHeight(36)


class ChipFlow(QWidget):
    def __init__(self, labels, parent=None, chip_width=110, hspacing=8, vspacing=8,
                 margins=(10, 8, 10, 10), min_width=90, max_width=240, target_width=110):
        super().__init__(parent)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Minimum)
        self.grid = QGridLayout(self)
        self.grid.setContentsMargins(*margins)
        self.grid.setHorizontalSpacing(hspacing)
        self.grid.setVerticalSpacing(vspacing)
        self.grid.setAlignment(Qt.AlignLeft | Qt.AlignTop)
        self.min_width = int(min_width)
        self.max_width = int(max_width)
        self.target_width = int(target_width)
        self.chips = []
        self.set_labels(labels, chip_width)
        QTimer.singleShot(0, self.reflow)

    def set_labels(self, labels, chip_width=110):
        # clear
        for c in self.chips:
            c.setParent(None)
        self.chips = [Chip(str(s), width=chip_width) for s in labels]
        for c in self.chips:
            self.grid.addWidget(c, 0, 0)
        self.reflow()

    def setTargetWidth(self, w: int):
        self.target_width = max(48, int(w))
        self.reflow()

    def setMinMaxWidth(self, min_w: int, max_w: int):
        self.min_width = int(min_w)
        self.max_width = int(max_w)
        self.reflow()

    def _inner_width(self):
        return max(1, self.contentsRect().width())

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self.reflow()

    def reflow(self):
        if not self.chips:
            return
        l, t, r, b = self.grid.getContentsMargins()
        avail = max(1, self._inner_width() - l - r)
        spacing = self.grid.horizontalSpacing()
        tw = max(self.min_width, self.target_width)
        cols = max(1, (avail + spacing) // (tw + spacing))
        stretched = (avail - (cols - 1) * spacing) // cols
        chip_w = max(self.min_width, min(self.max_width, stretched))
        while self.grid.count():
            it = self.grid.takeAt(0)
            w = it.widget()
            if w is not None:
                w.setParent(self)
        for idx, w in enumerate(self.chips):
            w.setChipWidth(chip_w)
            self.grid.addWidget(w, idx // cols, idx % cols)
        for c in range(cols):
            self.grid.setColumnStretch(c, 0)


class FlowScroll(QScrollArea):
    def __init__(self, flow: ChipFlow):
        super().__init__()
        self.setWidgetResizable(True)
        self.setFrameShape(QFrame.NoFrame)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._flow = flow
        self.setWidget(self._flow)
        self.viewport().installEventFilter(self)

    def eventFilter(self, obj, event):
        if obj is self.viewport() and event.type() == QEvent.Resize:
            self._flow.setMinimumWidth(self.viewport().width())
            self._flow.setMaximumWidth(self.viewport().width())
            self._flow.reflow()
        return super().eventFilter(obj, event)

# ---------------- PlaceCard with callbacks & async thumbnail ----------------


class PlaceCard(QFrame):
    def __init__(self, place, on_join, on_open, thumb_base=(200, 120)):
        super().__init__()
        self.setObjectName("PlaceCard")
        self._shadow = make_shadow(20, 0, 6, QColor(0, 0, 0, 140))
        self.setGraphicsEffect(self._shadow)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self._thumb_base = thumb_base
        # normalize place dict and id keys (some APIs return 'id' or 'placeId')
        self.place = place or {}
        pid = self.place.get('id') or self.place.get(
            'placeId') or self.place.get('place_id') or self.place.get('place')
        if pid is not None:
            try:
                pid = int(pid)
            except Exception:
                pass
        self.place['id'] = pid
        lay = QVBoxLayout(self)
        lay.setContentsMargins(12, 12, 12, 12)
        lay.setSpacing(10)
        self.thumb = QLabel("(thumbnail)")
        self.thumb.setObjectName("Thumb")
        self.thumb.setMinimumSize(*thumb_base)
        self.thumb.setAlignment(Qt.AlignCenter)
        title = f"{self.place.get('name', 'Unknown')} (ID: {self.place.get('id', '?')})"
        if self.place.get('is_root'):
            title += "  ROOT"
        self.title_lbl = QLabel(title)
        self.title_lbl.setWordWrap(True)
        f = QFont()
        f.setPointSize(12)
        f.setBold(True)
        self.title_lbl.setFont(f)
        join_btn = AccentButton("Join")
        open_btn = GhostButton("Open 🌐")
        join_btn.setFixedHeight(34)
        open_btn.setFixedHeight(34)
        join_btn.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        open_btn.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        row = QHBoxLayout()
        row.setSpacing(8)
        row.addWidget(join_btn)
        row.addWidget(open_btn)
        created_ago = self.time_ago(self.place.get('created'))
        updated_ago = self.time_ago(self.place.get('updated'))
        meta = QLabel(f"Created: {created_ago}\nUpdated: {updated_ago}")
        lay.addWidget(self.thumb)
        lay.addWidget(self.title_lbl)
        lay.addWidget(meta)
        lay.addLayout(row)
        self._update_fixed_height()
        # wiring
        join_btn.clicked.connect(lambda: on_join(self.place.get('id')))
        open_btn.clicked.connect(lambda: on_open(self.place.get('id')))

    def _update_fixed_height(self):
        self.adjustSize()
        h = self.sizeHint().height()
        self.setMaximumHeight(h)

    def set_thumb_scale(self, scale: float):
        w = max(140, int(self._thumb_base[0] * scale))
        h = max(84, int(self._thumb_base[1] * scale))
        self.thumb.setMinimumSize(w, h)
        self.thumb.setMaximumHeight(h + 4)
        self._update_fixed_height()

    def time_ago(self, iso_time: str):
        """Convert ISO timestamp (e.g. '2025-09-30T12:35:16.34Z') into 'x days ago'."""
        if not iso_time:
            return "—"
        try:
            # Parse ISO 8601 (Roblox uses UTC Z suffix)
            dt = datetime.fromisoformat(iso_time.replace("Z", "+00:00"))
            now = datetime.now(timezone.utc)
            diff = now - dt
            seconds = diff.total_seconds()

            if seconds < 60:
                return f"{int(seconds)} seconds ago" if int(seconds) != 1 else "1 second ago"
            elif seconds < 3600:
                minutes = int(seconds / 60)
                return f"{minutes} minutes ago" if minutes != 1 else "1 minute ago"
            elif seconds < 86400:
                hours = int(seconds / 3600)
                return f"{hours} hours ago" if hours != 1 else "1 hour ago"
            elif seconds < 2592000:
                days = int(seconds / 86400)
                return f"{days} days ago" if days != 1 else "1 day ago"
            elif seconds < 31536000:
                months = int(seconds / 2592000)
                return f"{months} months ago" if months != 1 else "1 month ago"
            else:
                years = int(seconds / 31536000)
                return f"{years} years ago" if years != 1 else "1 year ago"
        except Exception:
            return iso_time

# -------- collapsible hero --------


class CollapsibleHero(Card):
    def __init__(self, on_theme, on_text_color, on_btn_color, on_grid_size,
                 save_checkbox: QCheckBox, disable_join_checkbox: QCheckBox):
        super().__init__(None, object_name="HeroCard")
        self._chev = GhostButton("▾")
        self._chev.setMinimumWidth(36)
        title = QLabel("Hopr GUI")
        f = QFont()
        f.setPointSize(12)
        f.setBold(True)
        title.setFont(f)
        subtitle = QLabel("Very fire UI🔥 • <-- Trust • Join sublaces! • 🤤😋")
        subtitle.setObjectName("HeroSubtitle")
        header_row = QHBoxLayout()
        header_row.addStretch(1)
        head_center = QVBoxLayout()
        head_center.setSpacing(4)
        title.setAlignment(Qt.AlignCenter)
        subtitle.setAlignment(Qt.AlignCenter)
        head_center.addWidget(title)
        head_center.addWidget(subtitle)
        header_row.addLayout(head_center)
        header_row.addStretch(1)
        header_row.addWidget(self._chev)
        row = QHBoxLayout()
        row.setSpacing(10)
        row.setAlignment(Qt.AlignHCenter)
        theme_btn = GhostButton("Theme")
        theme_menu = QMenu(theme_btn)
        for name, key in [("System", "system"), ("Light", "light"), ("Dark", "dark")]:
            act = theme_menu.addAction(name)
            act.triggered.connect(lambda _, k=key: on_theme(k))
        theme_btn.setMenu(theme_menu)
        theme_btn.clicked.connect(theme_btn.showMenu)
        text_btn = GhostButton("Text Color")
        text_btn.clicked.connect(on_text_color)
        btncol_btn = GhostButton("Button Color")
        btncol_btn.clicked.connect(on_btn_color)
        size_btn = GhostButton("Grid Size")
        size_menu = QMenu(size_btn)
        size_container = QWidget()
        size_layout = QHBoxLayout(size_container)
        size_layout.setContentsMargins(8, 8, 8, 8)
        size_slider = QSlider(Qt.Horizontal)
        size_slider.setRange(200, 420)
        size_slider.setValue(300)
        size_slider.setSingleStep(10)
        size_layout.addWidget(QLabel("Small"))
        size_layout.addWidget(size_slider)
        size_layout.addWidget(QLabel("Large"))
        wa = QWidgetAction(size_menu)
        wa.setDefaultWidget(size_container)
        size_menu.addAction(wa)
        size_btn.setMenu(size_menu)
        size_btn.clicked.connect(size_btn.showMenu)
        size_slider.valueChanged.connect(on_grid_size)
        save_checkbox.setParent(self)
        disable_join_checkbox.setParent(self)
        row.addWidget(theme_btn)
        row.addWidget(text_btn)
        row.addWidget(btncol_btn)
        row.addWidget(size_btn)
        row.addWidget(save_checkbox)
        row.addWidget(disable_join_checkbox)
        self.body().addLayout(header_row)
        self._settings_host = QWidget()
        sh = QHBoxLayout(self._settings_host)
        sh.setContentsMargins(0, 0, 0, 0)
        sh.addLayout(row)
        self.body().addWidget(self._settings_host)
        self._expanded = True
        self._chev.clicked.connect(self._toggle)

    def _toggle(self):
        self._expanded = not self._expanded
        self._settings_host.setVisible(self._expanded)
        self._chev.setText("▾" if self._expanded else "▸")


# ==================== Main Window ====================


class _MainThreadInvoker(QObject):
    call = Signal(object)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.call.connect(self._run, Qt.QueuedConnection)

    def _run(self, fn):
        try:
            print('[DEBUG] _invoker: executing UI callback...')
            fn()
            print('[DEBUG] _invoker: UI callback complete')
        except Exception as e:
            import traceback
            print('[DEBUG] Exception in main-thread invoker:', e)
            traceback.print_exc()


class FFlagWarningDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("FastFlag Editor Warning")
        self.setWindowFlags(Qt.Dialog | Qt.WindowTitleHint)
        self.setModal(True)
        self.setFixedSize(400, 200)

        # Apply the same styling as the main app
        self.setStyleSheet(gen_styles())

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(15)

        # Warning icon and text
        warning_layout = QHBoxLayout()
        warning_layout.setSpacing(15)

        # Warning emoji/icon
        icon_label = QLabel("⚠️")
        icon_label.setStyleSheet("font-size: 32px;")
        icon_label.setAlignment(Qt.AlignCenter)
        warning_layout.addWidget(icon_label)

        # Warning text
        warning_text = QLabel("This can get you banned if you are not careful")
        warning_text.setObjectName("CardTitle")
        warning_text.setWordWrap(True)
        warning_text.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        f = QFont()
        f.setPointSize(12)
        f.setBold(True)
        warning_text.setFont(f)
        warning_layout.addWidget(warning_text, 1)

        layout.addLayout(warning_layout)

        # Additional info
        info_text = QLabel(
            "FastFlags can modify Roblox behavior in ways that may violate Terms of Service. Use at your own risk.")
        info_text.setObjectName("Caption")
        info_text.setWordWrap(True)
        layout.addWidget(info_text)

        layout.addStretch()

        # Don't show again checkbox
        self.dont_show_checkbox = QCheckBox("Don't show this warning again")
        self.dont_show_checkbox.setObjectName("PillCheck")
        layout.addWidget(self.dont_show_checkbox)

        # OK button
        ok_button = AccentButton("OK!")
        ok_button.clicked.connect(self.accept)
        ok_button.setFixedWidth(80)

        button_layout = QHBoxLayout()
        button_layout.addStretch()
        button_layout.addWidget(ok_button)
        layout.addLayout(button_layout)

    def dont_show_again(self):
        return self.dont_show_checkbox.isChecked()


class Window(QMainWindow):
    def __init__(self):
        super().__init__()
        # Ensure queued UI callbacks run
        self._invoker = _MainThreadInvoker(self)

        self.setWindowTitle("Hopr — Advanced Roblox Tools")
        self.resize(1280, 820)
        self.setMinimumSize(780, 560)
        # state
        self._text_color = None
        self._btn_color = None
        self._card_width = 300
        self._theme = "dark"
        self._cards = []
        self.root_place_id = None
        self.thumb_cache = {}  # place_id -> PIL Image
        self._current_places = []  # Store current places for sorting
        self._sort_option = "place_id_asc"  # Default sort option

        # Use same settings path as Tk app for compatibility
        self.settings_path = Path.home() / "AppData/Local/SubplaceJoiner/settings.json"
        self.recent_ids = []
        self.favorites = set()
        self.cookie_visible = False
        self.disable_join_when_proxy = True
        self._proxy_thread = None
        self._proxy_ready = False
        self._search_inflight = False
        self._search_watchdog = None
        self._show_fflag_warning = True  # New setting for warning
        self._fflag_warning_shown = False  # Track if warning was shown this session
        self._apply_theme(self._theme)
        self._build()
        self._apply_styles()
        self._load_settings()
        self._refresh_recents_and_favs()

    # ---------- Theme ----------
    def _apply_theme(self, theme):
        app = QApplication.instance()
        app.setStyle("Fusion")
        set_app_palette(app, theme)

    def _apply_styles(self):
        self.setStyleSheet(gen_styles(self._text_color, self._btn_color))

    # ---------- UI build ----------
    def _build(self):
        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QVBoxLayout(central)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # Create tab system
        self.tab_widget = ChromeTabWidget()

        # Create the main Hopr content
        hopr_content = self._build_hopr_content()
        self.tab_widget.addTab(hopr_content, "Hopr")


        fflag_editor_widget = FFlagEditorWidget()
        self.tab_widget.addTab(fflag_editor_widget, "FastFlag Editor")

        # NEW: Random Stuff tab
        random_stuff_widget = RandomStuffWidget()
        self.tab_widget.addTab(random_stuff_widget, "Random Stuff")

        # Connect tab change signal to show warning if needed
        self.tab_widget.currentChanged.connect(self._on_tab_changed)

        main_layout.addWidget(self.tab_widget)

    def _build_hopr_content(self):
        """Build the original Hopr content as a widget"""
        content_widget = QWidget()
        outer = QVBoxLayout(content_widget)
        outer.setContentsMargins(14, 14, 14, 14)
        outer.setSpacing(12)

        # Settings checkboxes
        self.save_settings_chk = PillCheck("Save Settings")
        self.save_settings_chk.setChecked(True)  # default ON
        self.disable_join_chk = PillCheck(
            "Disable Join while Roblox/Proxy running")
        self.disable_join_chk.setChecked(True)
        hero = CollapsibleHero(
            on_theme=self._on_theme,
            on_text_color=self._on_text_color,
            on_btn_color=self._on_btn_color,
            on_grid_size=self._on_grid_size_changed,
            save_checkbox=self.save_settings_chk,
            disable_join_checkbox=self.disable_join_chk
        )
        outer.addWidget(hero)
        # search card
        search_card = Card()
        srow = QHBoxLayout()
        srow.setSpacing(10)
        self.search = Search("Enter Place ID")
        srow.addWidget(self.search, 2)
        self.search_btn = AccentButton("Search")
        srow.addWidget(self.search_btn)
        self.fav_btn = GhostButton("★ Fav")
        srow.addWidget(self.fav_btn)
        self.search_btn.clicked.connect(
            lambda _checked=False: self.on_search_clicked())
        self.search.returnPressed.connect(lambda: self.on_search_clicked())
        self.fav_btn.clicked.connect(self.on_toggle_favorite)
        search_card.body().addLayout(srow)
        cookie_row = QHBoxLayout()
        cookie_row.setSpacing(10)
        self.cookie_edit = Search(".ROBLOSECURITY cookie (optional)")
        self.cookie_edit.setEchoMode(QLineEdit.Password)
        cookie_row.addWidget(self.cookie_edit, 2)
        self.cookie_toggle = GhostButton("Show")
        self.cookie_toggle.clicked.connect(self.on_toggle_cookie)
        cookie_row.addWidget(self.cookie_toggle)
        search_card.body().addLayout(cookie_row)
        self.error_lbl = QLabel("")
        self.error_lbl.setObjectName("Caption")
        search_card.body().addWidget(self.error_lbl)
        self.debug_lbl = QLabel("")
        self.debug_lbl.setObjectName("Caption")
        search_card.body().addWidget(self.debug_lbl)
        outer.addWidget(search_card)
        search_card._l.setContentsMargins(10, 8, 10, 8)
        search_card._l.setSpacing(67.67)
        search_card.setMinimumHeight(100)
        search_card.setMaximumHeight(100)
        # LEFT
        left_wrap = QWidget()
        self.left_layout = QVBoxLayout(left_wrap)
        self.left_layout.setContentsMargins(0, 0, HANDLE_GUTTER, 0)
        self.left_layout.setSpacing(8)
        self.rec_card = Card("RECENT PLACE IDS")
        self.fav_card = Card("FAVORITES")
        self._chip_target = int(self._card_width * 0.38)
        self.rec_flow = ChipFlow(
            [], chip_width=110, target_width=self._chip_target)
        self.fav_flow = ChipFlow(
            [], chip_width=110, target_width=self._chip_target)
        self.rec_scroll = FlowScroll(self.rec_flow)
        self.fav_scroll = FlowScroll(self.fav_flow)
        self.rec_card.body().addWidget(self.rec_scroll, 1)
        self.fav_card.body().addWidget(self.fav_scroll, 1)
        left_split = QSplitter(Qt.Vertical)
        left_split.setChildrenCollapsible(True)
        left_split.setHandleWidth(4)
        left_split.addWidget(self.rec_card)
        left_split.addWidget(self.fav_card)
        left_split.setSizes([240, 200])
        self.left_layout.addWidget(left_split)
        # RIGHT results grid
        self.right_wrap = QWidget()
        self.right_layout = QVBoxLayout(self.right_wrap)
        self.right_layout.setContentsMargins(HANDLE_GUTTER, 0, 0, 0)
        self.right_layout.setSpacing(0)
        right_card = Card(None)
        # Remove title, we'll add custom header
        right_card.setMinimumWidth(240)

        # Custom header with title and sort dropdown
        header_layout = QHBoxLayout()
        results_title = QLabel("RESULTS")
        f = QFont()
        f.setPointSize(11)
        f.setBold(True)
        results_title.setFont(f)
        results_title.setObjectName("CardTitle")
        results_title.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)

        # Sort dropdown
        self.sort_combo = GhostButton("Sort: Place ID ↑")
        self.sort_combo.setMinimumWidth(140)
        sort_menu = QMenu(self.sort_combo)

        sort_options = [
            ("Place ID ↑", "place_id_asc"),
            ("Place ID ↓", "place_id_desc"),
            ("Date Created ↑", "created_asc"),
            ("Date Created ↓", "created_desc"),
            ("Date Updated ↑", "updated_asc"),
            ("Date Updated ↓", "updated_desc"),
        ]

        for label, key in sort_options:
            action = sort_menu.addAction(label)
            action.triggered.connect(
                lambda checked, k=key, l=label: self._on_sort_changed(k, l))

        self.sort_combo.setMenu(sort_menu)
        self.sort_combo.clicked.connect(self.sort_combo.showMenu)

        header_layout.addWidget(results_title)
        header_layout.addStretch()
        header_layout.addWidget(self.sort_combo)

        # Add header to card body
        right_card.body().addLayout(header_layout)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.NoFrame)
        self.grid_host = QWidget()
        self.grid_host.setSizePolicy(
            QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.grid = QGridLayout(self.grid_host)
        self.grid.setContentsMargins(8, 8, 8, 8)
        self.grid.setHorizontalSpacing(12)
        self.grid.setVerticalSpacing(12)
        self.grid.setAlignment(Qt.AlignTop)
        self.scroll.setWidget(self.grid_host)
        right_card.body().addWidget(self.scroll, 1)
        self.right_layout.addWidget(right_card)
        main_split = ThinSplitter(Qt.Horizontal)
        main_split.setChildrenCollapsible(True)
        main_split.setHandleWidth(HANDLE_HIT)
        main_split.addWidget(left_wrap)
        main_split.addWidget(self.right_wrap)
        main_split.setSizes([320, 900])
        # Fix: setCollapsible after widgets are added
        main_split.setCollapsible(0, True)
        self.main_split = main_split
        self.main_split.splitterMoved.connect(
            lambda *_: (self._snap_left_closed(), self._apply_collapse_margin()))
        outer.addWidget(self.main_split, 1)
        self.grid_host.installEventFilter(self)
        # footer
        foot = QHBoxLayout()
        self.status = QLabel("Ready.")
        self.status.setObjectName("Caption")
        foot.addWidget(self.status)
        foot.addStretch(1)
        outer.addLayout(foot)
        self._reflow_grid()
        self._scale_thumbs()
        QTimer.singleShot(0, self._apply_collapse_margin)

        return content_widget

    # ---------- Event/layout helpers ----------
    def eventFilter(self, obj, event):
        if obj is self.grid_host and event.type() == QEvent.Resize:
            self._reflow_grid()
        return super().eventFilter(obj, event)

    def _reflow_grid(self):
        width = max(self.grid_host.width(), 1)
        cols = max(1, width // self._card_width)
        widgets = []
        while self.grid.count():
            it = self.grid.takeAt(0)
            w = it.widget()
            if w:
                widgets.append(w)
        for i, w in enumerate(widgets):
            self.grid.addWidget(w, i // cols, i % cols)

    def _scale_thumbs(self):
        scale = max(0.55, min(1.45, (self._card_width / 300.0)))
        for i in range(self.grid.count()):
            item = self.grid.itemAt(i)
            w = item.widget()
            if isinstance(w, PlaceCard):
                w.set_thumb_scale(scale)
                # Re-apply thumbnail at new size if it exists
                place_id = w.place.get('id')
                if place_id in self.thumb_cache:
                    pix = self._pil_to_qpix(self.thumb_cache[place_id])
                    if pix:
                        w.thumb.setPixmap(pix.scaled(
                            w.thumb.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation))

    def _apply_collapse_margin(self):
        sizes = self.main_split.sizes()
        if not sizes:
            return
        if sizes[0] == 0:
            shift = -(HANDLE_HIT + HANDLE_GUTTER - HANDLE_LINE)
            self.right_layout.setContentsMargins(shift, 0, 0, 0)
        else:
            self.left_layout.setContentsMargins(0, 0, HANDLE_GUTTER, 0)
            self.right_layout.setContentsMargins(HANDLE_GUTTER, 0, 0, 0)

    def _snap_left_closed(self):
        sizes = self.main_split.sizes()
        if not sizes:
            return
        threshold = max(6, self.main_split.handleWidth() + 4)
        if sizes[0] < threshold:
            total = sum(sizes)
            right = max(1, total - self.main_split.handleWidth())
            self.main_split.setSizes([0, right])

    # ---------- Settings callbacks ----------
    def _on_theme(self, key):
        self._theme = 'dark' if key in ('system', 'dark') else 'light'
        self._apply_theme(self._theme)
        self._apply_styles()
        self._save_settings(force=True)

    def _on_text_color(self):
        c = QColorDialog.getColor(
            QColor(self._text_color or COLORS["text"]), self, "Choose text color")
        if c.isValid():
            self._text_color = c.name()
            self._apply_styles()
            self._save_settings(force=True)

    def _on_btn_color(self):
        c = QColorDialog.getColor(
            QColor(self._btn_color or COLORS["accent"]), self, "Choose button color")
        if c.isValid():
            self._btn_color = c.name()
            self._apply_styles()
            self._save_settings(force=True)

    def _on_grid_size_changed(self, val):
        self._card_width = int(val)
        self._reflow_grid()
        self._scale_thumbs()
        tw = int(max(90, min(240, self._card_width * 0.38)))
        self._chip_target = tw
        self.rec_flow.setTargetWidth(tw)
        self.fav_flow.setTargetWidth(tw)

    # ---------- Search / Results ----------
    def on_search_clicked(self, *_):
        if self._search_inflight:
            print("[SEARCH] ignored: already running")
            return
        place_id = self.search.text().strip()
        if not place_id.isdigit():
            self._set_error("Place ID must be a number")
            return
        self._set_error("")
        self.status.setText("Searching…")
        self.search_btn.setEnabled(False)
        self.search_btn.setText("Searching…")
        self._search_inflight = True
        # history update (always persist)
        if place_id in self.recent_ids:
            self.recent_ids.remove(place_id)
        self.recent_ids.insert(0, place_id)
        self._save_settings(force=True)
        self._refresh_recents_and_favs()
        print(f"[SEARCH] start place={place_id}")
        # watchdog: auto-unstick UI after 15s
        try:
            if self._search_watchdog is not None:
                self._search_watchdog.stop()
        except Exception:
            pass
        self._search_watchdog = QTimer(self)
        self._search_watchdog.setSingleShot(True)
        self._search_watchdog.timeout.connect(self._search_timeout)
        self._search_watchdog.start(15000)
        threading.Thread(target=self._search_worker,
                         args=(place_id,), daemon=True).start()

    def _search_worker(self, place_id: str):
        print("[SEARCH] worker begin")
        try:
            # Step 1: Get universe ID from place
            u = self._get(
                f"https://apis.roblox.com/universes/v1/places/{place_id}/universe", timeout=10)
            u.raise_for_status()
            universe_data = u.json()
            universe_id = universe_data.get("universeId")
            if not universe_id:
                raise Exception("Invalid Place ID or universe not found")

            # Step 1.5: Get the actual root place ID from universe details
            universe_details = self._get(
                f"https://games.roblox.com/v1/games?universeIds={universe_id}", timeout=10)
            universe_details.raise_for_status()
            games_data = universe_details.json().get("data", [])
            if games_data:
                self.root_place_id = games_data[0].get("rootPlaceId")
            else:
                # Fallback: assume searched place is root if we can't get universe details
                self.root_place_id = int(place_id)

            cursor = None
            all_places = []
            seen = set()

            # Step 2: Paginate through all places and display immediately
            while True:
                url = f"https://develop.roblox.com/v1/universes/{universe_id}/places?limit=100"
                if cursor:
                    url += f"&cursor={cursor}"
                r = self._get(url, timeout=10)
                r.raise_for_status()
                data = r.json()
                batch = data.get("data", [])

                if not batch:
                    print("[DEBUG] Empty batch received, stopping.")
                    break

                # Process batch and add to all_places immediately
                for p in batch:
                    pid = p.get("id")
                    if pid in seen:
                        continue
                    seen.add(pid)

                    # Set default values for timestamps
                    p["created"] = None
                    p["updated"] = None

                    # Mark root place - now using the actual root place ID
                    if self.root_place_id and int(pid) == int(self.root_place_id):
                        p["is_root"] = True

                    all_places.append(p)

                # Check next cursor
                next_cursor = data.get("nextPageCursor")
                if not next_cursor or next_cursor == cursor:
                    break
                cursor = next_cursor

            print("[DEBUG] Got all places, displaying immediately:",
                  len(all_places))
            print(f"[DEBUG] Root place ID detected as: {self.root_place_id}")

            # Display results immediately without timestamps
            self._on_main(lambda: (self._debug_api_detected(
                len(all_places)), self.display_results(all_places.copy())))

            # Now load timestamps asynchronously in background
            cookie = self.cookie_edit.text().strip() or self.get_roblosecurity() or ""

            def load_timestamps():
                updated_places = []
                for i, p in enumerate(all_places):
                    pid = p.get("id")

                    while True:
                        try:
                            asset_url = f"https://economy.roblox.com/v2/assets/{pid}/details"
                            response = requests.get(
                                asset_url, cookies={".ROBLOSECURITY": cookie}, timeout=10)
                            response.raise_for_status()
                            asset_data = response.json()

                            p["created"] = asset_data.get("Created")
                            p["updated"] = asset_data.get("Updated")

                            print(
                                f"[DEBUG] Place {pid}: created={p['created']}, updated={p['updated']}")
                            break

                        except requests.HTTPError as err:
                            status = getattr(err.response, "status_code", None)
                            if status in (429, 500, 502, 503, 504):
                                print(
                                    f"[WARN] Rate-limited or server error on {pid} (HTTP {status}); retrying in 1 s…")
                                time.sleep(1)
                                continue
                            else:
                                print(f"[WARN] HTTP error on {pid}: {err}")
                                break

                        except Exception as perr:
                            print(
                                f"[WARN] Could not fetch asset details for {pid}: {perr}")
                            break
                    updated_places.append(p)

                    # Update UI periodically (every 5 places) to show progress
                    if (i + 1) % 5 == 0 or i == len(all_places) - 1:
                        places_copy = updated_places.copy()
                        self._on_main(
                            lambda pc=places_copy: self._update_existing_cards_with_timestamps(pc))

            # Start timestamp loading in separate thread
            threading.Thread(target=load_timestamps, daemon=True).start()

        except Exception as e:
            self._on_main(lambda err=e: self._set_error(f"{err}"))

        finally:
            self._on_main(lambda: self._search_done_ui_reset())

    def _search_done_ui_reset(self):
        try:
            if self._search_watchdog is not None:
                self._search_watchdog.stop()
        except Exception:
            pass
        self._search_inflight = False
        try:
            self.search_btn.setEnabled(True)
            self.search_btn.setText("Search")
            if not self.status.text() or self.status.text().strip().lower() == "searching…":
                self.status.setText("Ready.")
        except Exception:
            pass
        print("[SEARCH] worker end")

    def _debug_api_detected(self, count):
        try:
            msg = f"[DEBUG] API responded with {count} places"
            print(msg)
            self.debug_lbl.setText(msg)
        except Exception as e:
            print("[DEBUG] failed to update debug label", e)

    def display_results(self, places):
        # Store places for sorting
        self._current_places = places.copy() if places else []

        # Sort and display
        if not places:
            while self.grid.count():
                it = self.grid.takeAt(0)
                w = it.widget()
                if w:
                    w.setParent(None)
            self.status.setText("No places found.")
            return

        if isinstance(places, dict):
            places = [places]
            self._current_places = places.copy()

        # Apply current sort
        sorted_places = self._sort_places(places)

        # Clear and display
        while self.grid.count():
            it = self.grid.takeAt(0)
            w = it.widget()
            if w:
                w.setParent(None)

        cols = max(1, max(1, self.grid_host.width() // self._card_width))
        for i, p in enumerate(sorted_places):
            if isinstance(p, dict):
                pid = p.get('id') or p.get('placeId')
                if pid is not None:
                    try:
                        p['id'] = int(pid)
                    except Exception:
                        p['id'] = pid
            card = PlaceCard(p, on_join=self.join_flow,
                             on_open=self.open_in_browser)
            self.grid.addWidget(card, i // cols, i % cols)
            # Start thumbnail loading immediately for each card
            self._load_thumb_async_immediate(p.get('id'), card)
        self._reflow_grid()
        self._scale_thumbs()
        self.status.setText(f"Found {len(places)} places")

    def _load_thumb_async_immediate(self, place_id, card: PlaceCard):
        """Load thumbnail immediately without waiting"""
        def worker():
            try:
                pix = self._fetch_thumb_pixmap(place_id)
                self._on_main(lambda: self._apply_thumb(card, pix))
            except Exception as e:
                print(f"[THUMB] Error loading thumbnail for {place_id}: {e}")
                self._on_main(lambda: card.thumb.setText("(no image)"))
        threading.Thread(target=worker, daemon=True).start()

    def _search_timeout(self):
        print("[SEARCH] watchdog fired — resetting UI")
        self._search_inflight = False
        try:
            self.search_btn.setEnabled(True)
            self.search_btn.setText("Search")
            if not self.status.text() or self.status.text().strip().lower() == "searching…":
                self.status.setText("Timed out. Try again.")
        except Exception:
            pass

    def _update_existing_cards_with_timestamps(self, updated_places):
        """Update existing PlaceCard widgets with new timestamp data and re-sort if needed"""
        try:
            # Update stored places with new timestamp data
            place_map = {p.get('id'): p for p in updated_places}
            for i, stored_place in enumerate(self._current_places):
                place_id = stored_place.get('id')
                if place_id in place_map:
                    self._current_places[i] = place_map[place_id]

            # Re-sort and display if sort is by date
            if self._sort_option.startswith(('created', 'updated')):
                sorted_places = self._sort_places(self._current_places.copy())
                self._display_sorted_places(sorted_places)
            else:
                # Just update existing cards in place
                place_map = {p.get('id'): p for p in updated_places}

                # Update existing cards
                for i in range(self.grid.count()):
                    item = self.grid.itemAt(i)
                    if item and item.widget():
                        card = item.widget()
                        if isinstance(card, PlaceCard):
                            card_id = card.place.get('id')
                            if card_id in place_map:
                                # Update the place data
                                updated_place = place_map[card_id]
                                card.place.update(updated_place)

                                # Update the meta label with new timestamps
                                created_ago = card.time_ago(
                                    updated_place.get('created'))
                                updated_ago = card.time_ago(
                                    updated_place.get('updated'))

                                # Find the meta label and update it
                                for child in card.findChildren(QLabel):
                                    if child.text().startswith("Created:"):
                                        child.setText(
                                            f"Created: {created_ago}\nUpdated: {updated_ago}")
                                        break

        except Exception as e:
            print(f"[DEBUG] Error updating timestamps: {e}")

    def _on_sort_changed(self, sort_key, sort_label):
        """Handle sort option change"""
        self._sort_option = sort_key
        self.sort_combo.setText(f"Sort: {sort_label}")

        # Re-sort and display current places
        if self._current_places:
            sorted_places = self._sort_places(self._current_places.copy())
            self._display_sorted_places(sorted_places)

    def _on_tab_changed(self, index):
        """Handle tab change - show FastFlag warning if needed"""
        # Check if we're switching to the FastFlag Editor tab (index 2)
        if index == 1 and self._show_fflag_warning and not self._fflag_warning_shown:
            self._show_fflag_warning_dialog()

    def _show_fflag_warning_dialog(self):
        """Show the FastFlag warning dialog"""
        dialog = FFlagWarningDialog(self)
        result = dialog.exec()

        if result == QDialog.Accepted:
            self._fflag_warning_shown = True
            if dialog.dont_show_again():
                self._show_fflag_warning = False
                self._save_settings(force=True)

    def _sort_places(self, places):
        """Sort places based on current sort option"""
        if not places:
            return places

        def get_sort_key(place):
            if self._sort_option.startswith("place_id"):
                return int(place.get('id', 0))
            elif self._sort_option.startswith("created"):
                created = place.get('created')
                if not created:
                    return datetime.min.replace(tzinfo=timezone.utc)
                try:
                    return datetime.fromisoformat(created.replace("Z", "+00:00"))
                except:
                    return datetime.min.replace(tzinfo=timezone.utc)
            elif self._sort_option.startswith("updated"):
                updated = place.get('updated')
                if not updated:
                    return datetime.min.replace(tzinfo=timezone.utc)
                try:
                    return datetime.fromisoformat(updated.replace("Z", "+00:00"))
                except:
                    return datetime.min.replace(tzinfo=timezone.utc)
            return 0

        reverse = self._sort_option.endswith("_desc")
        return sorted(places, key=get_sort_key, reverse=reverse)

    def _display_sorted_places(self, places):
        """Display places without changing the stored _current_places"""
        # Clear grid
        while self.grid.count():
            it = self.grid.takeAt(0)
            w = it.widget()
            if w:
                w.setParent(None)

        if not places:
            self.status.setText("No places found.")
            return

        # Add sorted cards to grid
        cols = max(1, max(1, self.grid_host.width() // self._card_width))
        for i, p in enumerate(places):
            card = PlaceCard(p, on_join=self.join_flow,
                             on_open=self.open_in_browser)
            self.grid.addWidget(card, i // cols, i % cols)
            # Apply cached thumbnail if available
            place_id = p.get('id')
            if place_id in self.thumb_cache:
                pix = self._pil_to_qpix(self.thumb_cache[place_id])
                if pix:
                    card.thumb.setPixmap(pix.scaled(
                        card.thumb.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation))
            else:
                # Load thumbnail async
                self._load_thumb_async_immediate(place_id, card)

        self._reflow_grid()
        self._scale_thumbs()

    def _get(self, url, timeout=10):
        try:
            print(f"[HTTP GET] {url}")
            r = requests.get(url, timeout=timeout, proxies={})
            try:
                length = r.headers.get(
                    'Content-Length') or len(r.content or b'')
                snippet = (
                    r.text[:300] + '...') if r.text and len(r.text) > 300 else r.text
                print(f"[HTTP GET DONE] {r.status_code} length={length}")
                ct = r.headers.get('Content-Type', '')
                if 'application/json' in ct.lower() or 'text' in ct.lower():
                    print("[HTTP GET BODY SNIPPET]:", snippet)
            except Exception:
                pass
            return r
        except Exception as e:
            print(f"[HTTP GET ERROR] {url} -> {e}")
            raise

    # ---------- Thumbs ----------
    def _load_thumb_async(self, place_id, card: PlaceCard):
        def worker():
            pix = self._fetch_thumb_pixmap(place_id)
            self._on_main(lambda: self._apply_thumb(card, pix))
        threading.Thread(target=worker, daemon=True).start()

    def _apply_thumb(self, card: PlaceCard, pix: QPixmap | None):
        if pix is None:
            card.thumb.setText("(no image)")
            return
        card.thumb.setPixmap(pix.scaled(
            card.thumb.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation))

    def _fetch_thumb_pixmap(self, place_id) -> QPixmap | None:
        if place_id in self.thumb_cache:
            return self._pil_to_qpix(self.thumb_cache[place_id])
        try:
            meta = self._get(
                f"https://thumbnails.roblox.com/v1/places/gameicons?placeIds={place_id}&size=512x512&format=Png", timeout=10)
            meta.raise_for_status()
            data = meta.json()
            img_url = data.get("data", [{}])[0].get("imageUrl")
            if not img_url:
                return None
            img_response = self._get(img_url, timeout=10)
            img_response.raise_for_status()
            pil = Image.open(BytesIO(img_response.content)).convert("RGBA")
            size = min(pil.width, pil.height)
            img = pil.resize((size, size))
            mask = Image.new("L", (size, size), 0)
            draw = ImageDraw.Draw(mask)
            draw.rounded_rectangle(
                (0, 0, size, size), radius=size//6, fill=255)
            img.putalpha(mask)
            self.thumb_cache[place_id] = img
            return self._pil_to_qpix(img)
        except Exception:
            return None

    def _pil_to_qpix(self, pil_img) -> QPixmap | None:
        if pil_img is None:
            return None
        if ImageQt is None:
            b = BytesIO()
            pil_img.save(b, format='PNG')
            b.seek(0)
            qimg = QImage.fromData(b.read(), 'PNG')
            return QPixmap.fromImage(qimg)
        qimg = ImageQt(pil_img)
        if isinstance(qimg, QImage):
            return QPixmap.fromImage(qimg)
        return QPixmap.fromImage(QImage(qimg))

    # ---------- Favorites / Recents ----------
    def on_toggle_favorite(self):
        pid = self.search.text().strip()
        if not pid.isdigit():
            return
        if pid in self.favorites:
            self.favorites.remove(pid)
            self.status.setText(f"Removed {pid} from favorites")
            self.fav_btn.setText("★ Fav")
        else:
            self.favorites.add(pid)
            self.status.setText(f"Added {pid} to favorites")
            self.fav_btn.setText("★ Faved")
        self._save_settings(force=True)
        self._refresh_recents_and_favs()

    def _refresh_recents_and_favs(self):
        self.rec_flow.set_labels(self.recent_ids[:200])
        self.fav_flow.set_labels(
            sorted(self.favorites, key=lambda x: int(x)) if self.favorites else [])
        for chip in self.rec_flow.chips:
            chip.clicked.connect(lambda _, t=chip.text(): self._quick_search(t))
        for chip in self.fav_flow.chips:
            chip.clicked.connect(lambda _, t=chip.text(): self._quick_search(t))
        cur = self.search.text().strip()
        if cur and cur in self.favorites:
            self.fav_btn.setText("★ Faved")
        else:
            self.fav_btn.setText("★ Fav")

    def _quick_search(self, place_id: str):
        self.search.setText(str(place_id))
        self.on_search_clicked()

    # ---------- Cookie visibility ----------
    def on_toggle_cookie(self):
        self.cookie_visible = not self.cookie_visible
        self.cookie_edit.setEchoMode(
            QLineEdit.Normal if self.cookie_visible else QLineEdit.Password)
        self.cookie_toggle.setText("Hide" if self.cookie_visible else "Show")

    # ---------- Join flow ----------
    def join_flow(self, place_id):

        # Record subplace in recents immediately
        pid = str(place_id)
        if pid.isdigit():
            if pid in self.recent_ids:
                self.recent_ids.remove(pid)
            self.recent_ids.insert(0, pid)
            self._save_settings(force=True)
            self._refresh_recents_and_favs()

        cookie = (self.cookie_edit.text().strip()
                  or self.get_roblosecurity() or "")
        try:
            # Pre-seed join for ROOT explicitly (backend expects root first)
            root = int(self.root_place_id or place_id)
            if cookie:
                ok = self._preseed_join_root(root, cookie)
                if not ok:
                    self._set_error("GameJoin seed failed; launching anyway…")
            self.status.setText("Launching Roblox…")
            print("[DEEPLINK FIRING]",
                  f"roblox://experiences/start?placeId={place_id}", "root", self.root_place_id)
            self.launch_roblox(place_id)
            self.start_proxy_thread()
        except Exception as e:
            self._set_error(f"{e}")
            self.status.setText("Failed to launch Roblox")

    def _new_session(self, cookie: str | None):
        sess = requests.Session()
        # IMPORTANT: avoid inheriting system proxies; don't let mitm catch this pre-seed
        sess.trust_env = False
        sess.proxies = {}
        sess.headers.update({
            "User-Agent": "Roblox/WinInet",
            "Content-Type": "application/json",
            "Accept": "application/json",
            "Referer": "https://www.roblox.com/",
            "Origin": "https://www.roblox.com",
        })
        if cookie:
            sess.headers["Cookie"] = f".ROBLOSECURITY={cookie};"
        # X-CSRF
        try:
            r = sess.post("https://auth.roblox.com/v2/logout", timeout=10)
            token = r.headers.get(
                "x-csrf-token") or r.headers.get("X-CSRF-TOKEN")
            if token:
                sess.headers["X-CSRF-TOKEN"] = token
        except Exception:
            pass
        return sess

    def _preseed_join_root(self, root_place_id: int, cookie: str):
        try:
            sess = self._new_session(cookie)
            payload = {
                "placeId": int(root_place_id),
                "isTeleport": True,
                "isImmersiveAdsTeleport": False,
                "gameJoinAttemptId": str(uuid.uuid4()),
            }
            print("[JOIN PRESEED FIRING]", json.dumps(payload, indent=2))
            r = sess.post("https://gamejoin.roblox.com/v1/join-game",
                          json=payload, timeout=15)
            print("[JOIN PRESEED STATUS]", r.status_code)
            try:
                print("[JOIN PRESEED BODY]", r.text[:800])
            except Exception:
                pass
            data = {}
            try:
                data = r.json()
            except Exception:
                pass
            # Status 2 == ready to join
            return (r.status_code == 200 and data.get("status") == 2)
        except Exception as e:
            print("[JOIN PRESEED ERROR]", e)
            return False

    def start_proxy_thread(self):
        if not MITM_AVAILABLE or psutil is None:
            self.status.setText(
                "Proxy not available. (Install mitmproxy + psutil for full flow)")
            return
        if getattr(self, "_proxy_thread", None) and self._proxy_thread.is_alive():
            return

        def runner():
            asyncio.run(self._proxy_main())
        self._proxy_thread = threading.Thread(target=runner, daemon=True)
        self._proxy_thread.start()
        self.status.setText("Proxy running…")
        if self.disable_join_chk.isChecked():
            self._enable_disable_join_buttons(False)

    async def _proxy_main(self):
        global ENABLE_GAME_JOIN_INTERCEPT
        ENABLE_GAME_JOIN_INTERCEPT = True
        install_cert()
        # Wait for Roblox start & restore settings similar to original

        self._on_main(lambda: self.status.setText(
            "Waiting for Roblox to start…"))
        count = 0
        while True:
            if psutil and any((p.info.get('name') or '').lower() == "robloxplayerbeta.exe" for p in psutil.process_iter(['name'])):
                break
            else:
                count += 1
                if count >= 100:
                    ENABLE_GAME_JOIN_INTERCEPT = False
                    self._on_main(lambda: (self._enable_disable_join_buttons(
                        True), self.status.setText("Roblox did not open.")))
                    return
            await asyncio.sleep(0.1)

        count = 0
        while True:
            if any((p.info.get('name') or '').lower() == "robloxcrashhandler.exe" for p in psutil.process_iter(['name'])):
                break
            if not any((p.info.get('name') or '').lower() == "robloxplayerbeta.exe" for p in psutil.process_iter(['name'])):
                count += 1
                if count >= 50:
                    ENABLE_GAME_JOIN_INTERCEPT = False
                    self._on_main(lambda: (self._enable_disable_join_buttons(
                        True), self.status.setText("Roblox closed unexpectedly.")))
                    return
            else:
                count = 0
            await asyncio.sleep(0.1)

        self._on_main(lambda: self.status.setText("Roblox started"))
        # Wait for exit, then shutdown

        count = 0
        while True:
            if ENABLE_GAME_JOIN_INTERCEPT == False:
                break
            else:
                count += 1
                if count >= 200:
                    ENABLE_GAME_JOIN_INTERCEPT = False
                    self._on_main(lambda: (self._enable_disable_join_buttons(
                        True), self.status.setText("Game join timeout")))
                    return
            await asyncio.sleep(0.1)

        self._on_main(lambda: (self._enable_disable_join_buttons(
            True), self.status.setText("Joined game")))

    def _enable_disable_join_buttons(self, enable: bool):
        for i in range(self.grid.count()):
            w = self.grid.itemAt(i).widget()
            if isinstance(w, PlaceCard):
                for child in w.findChildren(QPushButton):
                    if child.text().startswith("Join"):
                        child.setEnabled(enable)
    # ---------- Launch & helpers ----------

    def launch_roblox(self, place_id):
        roblox_url = f"roblox://experiences/start?placeId={place_id}"
        system = platform.system()
        try:
            if system == "Windows":
                os.startfile(roblox_url)
            elif system == "Darwin":
                subprocess.run(["open", roblox_url], check=False)
            else:
                subprocess.run(["xdg-open", roblox_url], check=False)
        except Exception:
            webbrowser.open(roblox_url)

    def open_in_browser(self, place_id):
        try:
            # Also record to recents when opening in browser
            pid = str(place_id)
            if pid.isdigit():
                if pid in self.recent_ids:
                    self.recent_ids.remove(pid)
                self.recent_ids.insert(0, pid)
                self._save_settings(force=True)
                self._refresh_recents_and_favs()
            webbrowser.open(f"https://www.roblox.com/games/{place_id}")
        except Exception:
            pass

    # ---------- Cookie auto-read (Windows DPAPI) ----------
    def get_roblosecurity(self):
        path = os.path.expandvars(
            r"%LocalAppData%/Roblox/LocalStorage/RobloxCookies.dat")
        try:
            if not os.path.exists(path):
                return None
            with open(path, "r") as f:
                data = json.load(f)
            cookies_data = data.get("CookiesData")
            if not cookies_data or not win32crypt:
                return None
            enc = base64.b64decode(cookies_data)
            dec = win32crypt.CryptUnprotectData(enc, None, None, None, 0)[1]
            s = dec.decode(errors="ignore")
            m = re.search(r"\.ROBLOSECURITY\s+([^\s;]+)", s)
            return m.group(1) if m else None
        except Exception:
            return None

    # ---------- Settings persistence ----------
    def _load_settings(self):
        try:
            d = json.loads(self.settings_path.read_text(encoding="utf-8"))
        except Exception:
            d = {}
        self.recent_ids = list(d.get("recent_ids", []))
        self.favorites = set(x for x in d.get(
            "favorites", []) if str(x).isdigit())
        self._theme = d.get("theme", self._theme)
        self._text_color = d.get("text_color", self._text_color)
        self._btn_color = d.get("btn_color", self._btn_color)
        self._show_fflag_warning = d.get(
            "show_fflag_warning", True)  # Load warning setting
        if d.get("save_settings", True):
            self.save_settings_chk.setChecked(True)
        self._apply_theme(self._theme)
        self._apply_styles()

    def _save_settings(self, force=False):
        # Persist history/favorites regardless; theme/colors guarded by checkbox unless force=True
        d = {
            "recent_ids": self.recent_ids[:200],
            "favorites": sorted(self.favorites, key=lambda x: int(x)),
            "show_fflag_warning": self._show_fflag_warning,  # Always save warning setting
        }
        if self.save_settings_chk.isChecked() or force:
            d.update({
                "theme": self._theme,
                "text_color": self._text_color,
                "btn_color": self._btn_color,
                "save_settings": self.save_settings_chk.isChecked(),
            })
        try:
            self.settings_path.parent.mkdir(parents=True, exist_ok=True)
            self.settings_path.write_text(
                json.dumps(d, indent=2), encoding="utf-8")
        except Exception:
            pass

    # ---------- Misc ----------
    def _set_error(self, text):
        self.error_lbl.setText(text)

    def _on_main(self, fn):
        inv = getattr(self, '_invoker', None)
        if inv is not None:
            print('[DEBUG] _on_main: queuing UI work via signal')
            inv.call.emit(fn)
            return
        print('[DEBUG] _on_main: fallback QTimer.singleShot')
        try:
            QTimer.singleShot(0, fn)
        except Exception as e:
            import traceback
            print('[DEBUG] _on_main fallback failed:', e)
            traceback.print_exc()

# ---------- Tps kill ----------


_iphlp = ctypes.windll.iphlpapi
_kernel32 = ctypes.windll.kernel32
AF_INET = 2
TCP_TABLE_OWNER_PID_ALL = 5
ERROR_INSUFFICIENT_BUFFER = 122
MIB_TCP_STATE_DELETE_TCB = 12


class MIB_TCPROW(ctypes.Structure):
    _fields_ = [
        ("dwState", wintypes.DWORD),
        ("dwLocalAddr", wintypes.DWORD),
        ("dwLocalPort", wintypes.DWORD),
        ("dwRemoteAddr", wintypes.DWORD),
        ("dwRemotePort", wintypes.DWORD),
    ]


_SetTcpEntry = _iphlp.SetTcpEntry
_SetTcpEntry.argtypes = [ctypes.POINTER(MIB_TCPROW)]
_SetTcpEntry.restype = wintypes.DWORD


def _fmt_win_err(code):
    buf = ctypes.create_unicode_buffer(256)
    _kernel32.FormatMessageW(0x00001000, None, code, 0, buf, len(buf), None)
    return buf.value.strip() or f"Err{code}"


def _get_extended_tcp_table_raw():
    size = wintypes.DWORD(0)
    res = _iphlp.GetExtendedTcpTable(None, ctypes.byref(
        size), False, AF_INET, TCP_TABLE_OWNER_PID_ALL, 0)
    if res not in (0, ERROR_INSUFFICIENT_BUFFER):
        raise OSError(
            f"GetExtendedTcpTable failed initial: {res} {_fmt_win_err(res)}")
    buf = ctypes.create_string_buffer(size.value)
    res = _iphlp.GetExtendedTcpTable(buf, ctypes.byref(
        size), False, AF_INET, TCP_TABLE_OWNER_PID_ALL, 0)
    if res != 0:
        raise OSError(f"GetExtendedTcpTable failed: {res} {_fmt_win_err(res)}")
    return buf.raw


def kill_connections_by_name(procname, verbose=True):
    """
    Forcibly remove all IPv4 TCP connections owned by processes whose name exactly matches procname (case-insensitive).
    Requires Administrator on Windows.
    Returns (success_count, fail_count, details)
    """
    try:
        is_admin = ctypes.windll.shell32.IsUserAnAdmin() != 0
    except Exception:
        is_admin = False
    if not is_admin:
        raise PermissionError(
            "Administrator privileges required to forcibly close TCP connections on Windows.")

    target = (procname or "").lower()
    pids = {p.pid for p in psutil.process_iter(['name']) if (
        p.info['name'] or "").lower() == target}
    if not pids:
        if verbose:
            print("No processes found with name:", procname)
        return 0, 0, []

    raw = _get_extended_tcp_table_raw()
    num = struct.unpack_from("<I", raw, 0)[0]
    off = 4
    row_size = 24  # 6 DWORDs: state, la, lp, ra, rp, pid
    rows = []
    for i in range(num):
        s = off + i * row_size
        state, la, lp, ra, rp, pid = struct.unpack_from("<6I", raw, s)
        if pid in pids and ra != 0:
            rows.append((pid, la, lp, ra, rp, state))

    if not rows:
        if verbose:
            print("No active IPv4 TCP remote connections found for", procname)
        return 0, 0, []

    succ = 0
    fail = 0
    details = []
    for pid, la, lp, ra, rp, state in rows:
        mib = MIB_TCPROW()
        mib.dwState = MIB_TCP_STATE_DELETE_TCB
        mib.dwLocalAddr = la
        mib.dwLocalPort = lp
        mib.dwRemoteAddr = ra
        mib.dwRemotePort = rp
        rc = _SetTcpEntry(ctypes.byref(mib))
        msg = "OK" if rc == 0 else _fmt_win_err(rc)
        details.append((pid, la, lp, ra, rp, rc, msg))
        if rc == 0:
            succ += 1
            if verbose:
                print(
                    f"[OK] PID {pid} {socket.inet_ntoa(struct.pack('<I', la))}:{socket.ntohs(lp & 0xFFFF)} -> {socket.inet_ntoa(struct.pack('<I', ra))}:{socket.ntohs(rp & 0xFFFF)}")
        else:
            fail += 1
            if verbose:
                print(f"[FAIL {rc}] {msg} PID {pid} {socket.inet_ntoa(struct.pack('<I', la))}:{socket.ntohs(lp & 0xFFFF)} -> {socket.inet_ntoa(struct.pack('<I', ra))}:{socket.ntohs(rp & 0xFFFF)}")
    return succ, fail, details

# ==================== Proxy functions ====================


class Interceptor:

    # === Constants ===
    WANTED_JOIN_ENDPOINTS = (
        "/v1/join-game",
        "/v1/join-play-together-game",
    )
    ASSET_BATCH_ENDPOINT = "/v1/assets/batch"
    RESERVED_ENDPOINT = "/v1/join-reserved-game"
    JOIN_ENDPOINT = "/v1/join-game"

    # === MITM Request Handler ===
    def request(self, flow: 'http.HTTPFlow') -> None:
        global LAST_accessCode
        global LAST_placeId
        url = flow.request.pretty_url
        parsed_url = urlparse(url)
        content_type = flow.request.headers.get("Content-Type", "").lower()
        if ENABLE_RESERVED_GAME_JOIN_INTERCEPT == False:
            if (parsed_url.path == "/v1/join-reserved-game" or parsed_url.path == "/v1/join-game") and "application/json" in content_type:
                data = flow.request.json()
                print(data)
                if data.get("accessCode"):
                    LAST_accessCode = data.get("accessCode")
                else:
                    LAST_accessCode = None
                if data.get("placeId"):
                    LAST_placeId = data.get("placeId")
                else:
                    LAST_placeId = None

        
        # === Game Join Intercept ===
        if (ENABLE_GAME_JOIN_INTERCEPT and
            any(p in parsed_url.path for p in self.WANTED_JOIN_ENDPOINTS) and
            "gamejoin.roblox.com" in url and
                "application/json" in content_type):

            try:
                body_json = flow.request.json()
            except Exception:
                return

            if "isTeleport" not in body_json:
                body_json["isTeleport"] = True
                print("[JOIN] Added teleport flag")

            body_json.setdefault("gameJoinAttemptId", str(uuid.uuid4()))
            flow.request.set_text(json.dumps(body_json))


        
        elif (ENABLE_RESERVED_GAME_JOIN_INTERCEPT and
              "gamejoin.roblox.com" in url and
              "application/json" in content_type):
            if parsed_url.path == self.JOIN_ENDPOINT:  # exact match
                try:
                    body_json = flow.request.json()
                except Exception:
                    return
                if "isTeleport" not in body_json:
                    body_json["isTeleport"] = True
                    print("[RESERVE] Added teleport flag")
                if LAST_accessCode:
                    body_json["accessCode"] = LAST_accessCode
                    flow.request.url = "https://gamejoin.roblox.com/v1/join-reserved-game"
                elif LAST_jobId:
                    body_json["gameId"] = LAST_jobId
                    flow.request.url = "https://gamejoin.roblox.com/v1/join-game-instance"
                

                body_json.setdefault("gameJoinAttemptId", str(uuid.uuid4()))
                flow.request.set_text(json.dumps(body_json))
                


    def response(self, flow: 'http.HTTPFlow') -> None:
        global ENABLE_GAME_JOIN_INTERCEPT
        global ENABLE_RESERVED_GAME_JOIN_INTERCEPT
        global LAST_jobId
        url = flow.request.pretty_url
        parsed_url = urlparse(url)


        if ENABLE_RESERVED_GAME_JOIN_INTERCEPT == False:
            if (parsed_url.path == "/v1/join-reserved-game" or parsed_url.path == "/v1/join-game"):
                data = flow.response.json()
                if data.get("jobId"):
                    LAST_jobId = data.get("jobId")
                else:
                    LAST_jobId = None




        if ENABLE_GAME_JOIN_INTERCEPT and any(p in url for p in self.WANTED_JOIN_ENDPOINTS):
            

            # If there's no response, print null as JSON
            if not hasattr(flow, "response") or flow.response is None:
                print("null")
                return

            try:
                data = flow.response.json()       # try to get a parsed JSON object
                if data.get("status") == 2:
                    ENABLE_GAME_JOIN_INTERCEPT = False
            except Exception:
                # fallback: get text and output as a JSON string
                pass

            # Always print valid JSON (compact). Use ensure_ascii=False to keep unicode readable.
            #print(json.dumps(data, ensure_ascii=False))
        if ENABLE_RESERVED_GAME_JOIN_INTERCEPT:
            if ENABLE_RESERVED_GAME_JOIN_INTERCEPT and self.JOIN_ENDPOINT in url:
            

                # If there's no response, print null as JSON
                if not hasattr(flow, "response") or flow.response is None:
                    print("null")
                    return

                try:
                    data = flow.response.json()       # try to get a parsed JSON object
                    if data.get("status") == 2:
                        ENABLE_RESERVED_GAME_JOIN_INTERCEPT = False
                except Exception:
                    # fallback: get text and output as a JSON string
                    pass

            # Always print valid JSON (compact). Use ensure_ascii=False to keep unicode readable.
            #print(json.dumps(data, ensure_ascii=False))


async def stop_proxy():
    global PROXY
    print("proxy stopped")
    mode_servers.LocalRedirectorInstance._server = None
    mode_servers.LocalRedirectorInstance._instance = None
    asyncio.to_thread(ctx.master.shutdown)
    PROXY = None


def install_cert():
    ca_path = Path.home() / ".mitmproxy" / "mitmproxy-ca-cert.pem"
    if not ca_path.exists():
        return False
    apps = {
        "Roblox": Path.home() / "AppData/Local/Roblox/Versions",
        "Bloxstrap": Path.home() / "AppData/Local/Bloxstrap/Versions",
        "Fishstrap": Path.home() / "AppData/Local/Fishstrap/Versions",
        "Voidstrap": Path.home() / "AppData/Local/Voidstrap/RblxVersions",
        "Froststrap": Path.home() / "AppData/Local/Froststrap/Versions",
        "Plexity": Path.home() / "AppData/Local/Plexity/Downloads",
    }
    original_settings = {}
    for app_name, path in apps.items():
        if not path.exists():
            continue

        if any(path.glob("*PlayerBeta.exe")):
            verlist = [path]
        else:
            verlist = path.iterdir()

        for version_folder in verlist:
            if not version_folder.is_dir():
                continue
            exe_files = list(version_folder.glob("*PlayerBeta.exe"))
            if not exe_files:
                continue
            # Ensure libcurl bundle includes mitm CA
            ssl_folder = version_folder / "ssl"
            ssl_folder.mkdir(exist_ok=True)
            ca_file = ssl_folder / "cacert.pem"
            try:
                if ca_path.exists():
                    mitm_ca_content = ca_path.read_text(encoding="utf-8")
                    if ca_file.exists():
                        existing_content = ca_file.read_text(
                            encoding="utf-8")
                        if mitm_ca_content not in existing_content:
                            with open(ca_file, "a", encoding="utf-8") as f:
                                f.write("\n" + mitm_ca_content)
                    else:
                        with open(ca_file, "w", encoding="utf-8") as f:
                            f.write(mitm_ca_content)
            except Exception:
                pass
    return True


def start_proxy_t():
    if not MITM_AVAILABLE or psutil is None:
        return

    def runner():
        result = asyncio.run(start_proxy())
        if result is None:
            # MB_ICONERROR (0x10) -> shows error icon; blocks until user clicks OK
            ctypes.windll.user32.MessageBoxW(
                0,
                "Failed to start proxy. The program will now close.",
                "Proxy error",
                0x10
            )
            # immediate, unconditional process termination (no cleanup handlers)
            os._exit(1)
    proxy_thread = threading.Thread(target=runner, daemon=True)
    proxy_thread.start()


async def start_proxy():
    global PROXY
    options = Options(mode=["local:RobloxPlayerBeta.exe"])
    master = DumpMaster(options, with_termlog=True, with_dumper=False)
    master.addons.add(Interceptor())
    kill_connections_by_name("RobloxPlayerBeta.exe")
    PROXY = asyncio.create_task(master.run())

    cert = False
    count = 0
    while True:
        cert = install_cert()
        count += 1
        if count >= 100:
            stop_proxy()
            return None
        if cert:
            break
        await asyncio.sleep(0.1)

    await PROXY
    return master

start_proxy_t()


def find_roblox_exes():
    base = Path.home() / "AppData" / "Local"
    for p in base.rglob("*.exe"):
        if "playerbeta" in p.name.lower():
            print(p)


# find_roblox_exes()


# ---------------- Chrome-like Tab System ----------------


class ChromeTabBar(QTabBar):
    def __init__(self):
        super().__init__()
        self.setObjectName("ChromeTabBar")
        self.setExpanding(False)
        self.setMovable(True)
        self.setTabsClosable(True)


class ChromeTabWidget(QTabWidget):
    def __init__(self):
        super().__init__()
        self.setObjectName("ChromeTabWidget")
        self.setTabBar(ChromeTabBar())
        self.setTabPosition(QTabWidget.North)

        # Add button for new tabs
        self.add_button = QPushButton("+")
        self.add_button.setObjectName("TabAddButton")
        self.add_button.setToolTip("Add new tool tab")
        self.add_button.clicked.connect(self.add_new_tool_tab)

        # Position the add button using the tab widget's corner widget
        self.setCornerWidget(self.add_button, Qt.TopRightCorner)

        # Handle tab closing
        self.tabCloseRequested.connect(self.close_tab)

        self.tool_counter = 1

    def add_new_tool_tab(self):
        """Add a new tool tab - you can customize this to add different tools"""
        # For now, add a simple placeholder - you can replace this with actual tools
        tool_widget = SimpleToolWidget(f"Tool {self.tool_counter}")
        tab_name = f"Tool {self.tool_counter}"
        index = self.addTab(tool_widget, tab_name)
        self.setCurrentIndex(index)
        self.tool_counter += 1
        return tool_widget

    def close_tab(self, index):
        """Close a tab (but don't allow closing the main Hopr tab)"""
        if index == 0:  # Don't close the main Hopr tab
            return
        self.removeTab(index)

# Simple tool widget for new tabs


class SimpleToolWidget(QWidget):
    def __init__(self, tool_name="Tool"):
        super().__init__()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(15)

        # Title
        title = QLabel(f"{tool_name}")
        title.setObjectName("CardTitle")
        f = QFont()
        f.setPointSize(16)
        f.setBold(True)
        title.setFont(f)
        title.setAlignment(Qt.AlignCenter)
        layout.addWidget(title)

        # Placeholder content
        content = QLabel(
            "This is a placeholder tool.\nAdd your functionality here!")
        content.setObjectName("Caption")
        content.setAlignment(Qt.AlignCenter)
        content.setWordWrap(True)
        layout.addWidget(content)

        layout.addStretch()

# NEW: Random Stuff widget


class RandomStuffWidget(QWidget):
    def __init__(self):
        super().__init__()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(15)

        # Title
        title = QLabel("Random Stuff")
        title.setObjectName("CardTitle")
        f = QFont()
        f.setPointSize(16)
        f.setBold(True)
        title.setFont(f)
        title.setAlignment(Qt.AlignCenter)
        layout.addWidget(title)

        # Card with description and button
        card = Card()
        body = card.body()

        desc = QLabel("Attempts to rejoin your current/latest reserved server")
        desc.setObjectName("Caption")
        desc.setWordWrap(True)
        body.addWidget(desc)

        self.rejoin_btn = AccentButton("Rejoin Reserved Server")
        # Optional: no-op click handler to keep UI responsive without implementing logic
        self.rejoin_btn.clicked.connect(self.start_rejoin_thread)
        body.addWidget(self.rejoin_btn, 0, Qt.AlignLeft)

        layout.addWidget(card)
        layout.addStretch()

    def start_rejoin_thread(self):
        """Start rejoin() in a background thread so it doesn’t freeze the GUI."""
        t = threading.Thread(target=self.rejoin, daemon=True)
        t.start()

    def rejoin(self):
        global ENABLE_RESERVED_GAME_JOIN_INTERCEPT
        if LAST_placeId:
            if psutil and any((p.info.get('name') or '').lower() == "robloxplayerbeta.exe" for p in psutil.process_iter(['name'])):
                self._enable_disable_reserved_join_button(False)
                ENABLE_RESERVED_GAME_JOIN_INTERCEPT = True
                install_cert()
                try:
                    cookie = self.get_roblosecurity()
                    if cookie:
                        sess = self._new_session(cookie)
                        r = sess.get(f"https://games.roblox.com/v1/games/multiget-place-details?placeIds={LAST_placeId}", timeout=5)
                        data = r.json()[0]
                        root = data.get("universeRootPlaceId") or LAST_placeId
                    else:
                        root = LAST_placeId
                except Exception:
                    root = LAST_placeId
                if root != LAST_placeId:
                    self.join_root(root)
                self.launch_roblox(LAST_placeId)
                count = 0
                while True:
                    if ENABLE_RESERVED_GAME_JOIN_INTERCEPT == False:
                        self._enable_disable_reserved_join_button(True)
                        break
                    else:
                        count += 1
                        if count >= 200:
                            ENABLE_RESERVED_GAME_JOIN_INTERCEPT = False
                            self._enable_disable_reserved_join_button(True)
                            return
                    time.sleep(0.1)
    
    def launch_roblox(self, place_id):
        roblox_url = f"roblox://experiences/start?placeId={place_id}"
        system = platform.system()
        try:
            if system == "Windows":
                os.startfile(roblox_url)
            elif system == "Darwin":
                subprocess.run(["open", roblox_url], check=False)
            else:
                subprocess.run(["xdg-open", roblox_url], check=False)
        except Exception:
            webbrowser.open(roblox_url)
    
    def _enable_disable_reserved_join_button(self, enable: bool):
        self.rejoin_btn.setEnabled(enable)
    
    def get_roblosecurity(self):
        path = os.path.expandvars(
            r"%LocalAppData%/Roblox/LocalStorage/RobloxCookies.dat")
        try:
            if not os.path.exists(path):
                return None
            with open(path, "r") as f:
                data = json.load(f)
            cookies_data = data.get("CookiesData")
            if not cookies_data or not win32crypt:
                return None
            enc = base64.b64decode(cookies_data)
            dec = win32crypt.CryptUnprotectData(enc, None, None, None, 0)[1]
            s = dec.decode(errors="ignore")
            m = re.search(r"\.ROBLOSECURITY\s+([^\s;]+)", s)
            return m.group(1) if m else None
        except Exception:
            return None

    def join_root(self, root_place_id: int):
        try:
            cookie = self.get_roblosecurity()
            if cookie:
                sess = self._new_session(cookie)
                payload = {
                    "placeId": int(root_place_id),
                    "isTeleport": True,
                    "isImmersiveAdsTeleport": False,
                    "gameJoinAttemptId": str(uuid.uuid4()),
                }
                print("[JOIN PRESEED FIRING]", json.dumps(payload, indent=2))
                r = sess.post("https://gamejoin.roblox.com/v1/join-game",
                            json=payload, timeout=15)
                print("[JOIN PRESEED STATUS]", r.status_code)
                try:
                    print("[JOIN PRESEED BODY]", r.text[:800])
                except Exception:
                    pass
                data = {}
                try:
                    data = r.json()
                except Exception:
                    pass
                # Status 2 == ready to join
                return (r.status_code == 200 and data.get("status") == 2)
        except Exception as e:
            print("[JOIN PRESEED ERROR]", e)
            return False
    
    def _new_session(self, cookie: str | None):
        sess = requests.Session()
        # IMPORTANT: avoid inheriting system proxies; don't let mitm catch this pre-seed
        sess.trust_env = False
        sess.proxies = {}
        sess.headers.update({
            "User-Agent": "Roblox/WinInet",
            "Content-Type": "application/json",
            "Accept": "application/json",
            "Referer": "https://www.roblox.com/",
            "Origin": "https://www.roblox.com",
        })
        if cookie:
            sess.headers["Cookie"] = f".ROBLOSECURITY={cookie};"
        # X-CSRF
        try:
            r = sess.post("https://auth.roblox.com/v2/logout", timeout=10)
            token = r.headers.get(
                "x-csrf-token") or r.headers.get("X-CSRF-TOKEN")
            if token:
                sess.headers["X-CSRF-TOKEN"] = token
        except Exception:
            pass
        return sess




# FastFlag Editor Widget (complete rewrite based on reference)


class FFlagEditorWidget(QWidget):
    def __init__(self):
        super().__init__()
        self.flags = {}
        self.excluded_flags = set()  # Flags to exclude from display/save
        # Use the EXACT same default flags from the original FastFlagEditor.py - these are NEVER shown in the UI
        self.default_flags = {
            "FFlagFilterPurchasePromptInputDispatch_IXPValue": "true;1;InExperience.Performance;InExperience.Performance.Holdout.June2025.CoreUIOnly;532319696;flagbank",
            "FFlagRemovePermissionsButtons_IXPValue": "true;1;InExperience.Performance;InExperience.Performance.Holdout.June2025.CoreUIOnly;1743048710;flagbank",
            "FFlagPlayerListReduceRerenders_IXPValue": "false;1;InExperience.Performance;InExperience.Performance.Holdout.June2025.CoreUIOnly;673415276;flagbank",
            "FFlagAvatarEditorPromptsNoPromptNoRender_IXPValue": "true;1;InExperience.Performance;InExperience.Performance.Holdout.June2025.CoreUIOnly;347969450;flagbank",
            "FFlagPlayerListClosedNoRenderWithTenFoot_IXPValue": "true;1;InExperience.Performance;InExperience.Performance.Holdout.June2025.CoreUIOnly;673415276;flagbank",
            "FFlagUseUserProfileStore4_IXPValue": "true;1;InExperience.Performance;InExperience.Performance.Holdout.June2025.CoreUIOnly;1811976791;flagbank",
            "FFlagPublishAssetPromptNoPromptNoRender_IXPValue": "true;1;InExperience.Performance;InExperience.Performance.Holdout.June2025.CoreUIOnly;347969450;flagbank",
            "FFlagUseNewPlayerList3_IXPValue": "true;1;InExperience.Performance;InExperience.Performance.Holdout.June2025.CoreUIOnly;1196207538;flagbank",
            "FFlagFixLeaderboardCleanup_IXPValue": "true;1;InExperience.Performance;InExperience.Performance.Holdout.June2025.CoreUIOnly;1196207538;flagbank",
            "FFlagMoveNewPlayerListDividers_IXPValue": "true;1;InExperience.Performance;InExperience.Performance.Holdout.June2025.CoreUIOnly;1196207538;flagbank",
            "FFlagFixLeaderboardStatSortTypeMismatch_IXPValue": "true;1;InExperience.Performance;InExperience.Performance.Holdout.June2025.CoreUIOnly;1196207538;flagbank",
            "FFlagFilterNewPlayerListValueStat_IXPValue": "true;1;InExperience.Performance;InExperience.Performance.Holdout.June2025.CoreUIOnly;1196207538;flagbank",
            "FFlagUnreduxChatTransparencyV2_IXPValue": "true;1;ExperienceChat.Performance;FeatureRollout;1952442096;flagbank",
            "FFlagExpChatRemoveMessagesFromAppContainer_IXPValue": "true;1;ExperienceChat.Performance;FeatureRollout;878331096;flagbank",
            "FFlagChatWindowOnlyRenderMessagesOnce_IXPValue": "true;1;ExperienceChat.Performance;FeatureRollout;530774716;flagbank",
            "FFlagUnreduxLastInputTypeChanged_IXPValue": "true;1;ExperienceChat.Performance;FeatureRollout;510908202;flagbank",
            "FFlagChatWindowSemiRoduxMessages_IXPValue": "true;1;ExperienceChat.Performance;FeatureRollout;77621948;flagbank",
            "FFlagInitializeAutocompleteOnlyIfEnabled_IXPValue": "true;1;ExperienceChat.Performance;FeatureRollout;1049260247;flagbank",
            "FFlagChatWindowMessageRemoveState_IXPValue": "true;1;ExperienceChat.Performance;FeatureRollout;1376708965;flagbank",
            "FFlagExpChatUseVoiceParticipantsStore2_IXPValue": "true;1;ExperienceChat.Performance;FeatureRollout;125421786;flagbank",
            "FFlagExpChatMemoBillboardGui_IXPValue": "false;1;ExperienceChat.Performance;FeatureRollout;2065932627;flagbank",
            "FFlagExpChatRemoveBubbleChatAppUserMessagesState_IXPValue": "true;1;ExperienceChat.Performance;FeatureRollout;2065932627;flagbank",
            "FFlagEnableLeaveGameUpsellEntrypoint_IXPValue": "false;1;ExperienceChat.Performance;FeatureRollout;90111814;flagbank",
            "FFlagExpChatUseAdorneeStoreV4_IXPValue": "true;1;ExperienceChat.Performance;FeatureRollout;726159443;flagbank",
            "FFlagEnableChatMicPerfBinding_IXPValue": "true;1;ExperienceChat.Performance;FeatureRollout;1740143267;flagbank",
            "FFlagEnableCreatorSubtitleNavigation_v2_IXPValue": "true;1;PlayerApp.GameDetailsPage.Exposure;Discovery.EDP.MediaGalleryVideoPreview.v3;1531928792;flagbank",
            "FFlagChatOptimizeCommandProcessing_IXPValue": "true;1;ChatWindow.Performance;FeatureRollout;288906352;flagbank",
            "FFlagMemoizeChatReportingMenu_IXPValue": "true;1;ChatWindow.Performance;FeatureRollout;1915032136;flagbank",
            "FFlagMemoizeChatInputApp_IXPValue": "true;1;ChatWindow.Performance;FeatureRollout;1529984850;flagbank",
            "FFlagUseUserProfileStore4_IXPValue": "true;1;ChatWindow.Performance;FeatureRollout;1811976791;flagbank",
            "FFlagVideoHandleEarlyServiceShutdown_IXPValue": "true;1;Portal.VideoPlaybackManagerWithEarlyServiceShutdownHandling-1758059695;VideoPlaybackManagerWithEarlyServiceShutdownHandling;141700402;flagbank",
            "FFlagVideoPlaybackManager2_IXPValue": "true;1;Portal.VideoPlaybackManagerWithEarlyServiceShutdownHandling-1758059695;VideoPlaybackManagerWithEarlyServiceShutdownHandling;1210184318;flagbank",
            "FFlagAppChatNewChatInputBar2_IXPValue": "true;1;Social.AppChat;AppChat.NewChatInputBar;1798109022;dev_controlled",
            "FFlagAppChatNewChatInputBarIxpEnabled_IXPValue": "true;1;Social.AppChat;AppChat.NewChatInputBar;1798109022;dev_controlled",
            "FFlagAppChatRemoveUserProfileTitles2_IXPValue": "true;1;Party.Chat.Performance;FeatureRollout;568652191;dev_controlled",
            "FFlagMacUnifyKeyCodeMapping_IXPValue": "true;1;Portal.MacUnifyKeyCodeMapping-1752599684;FeatureRollout;965638851;flagbank",
            "FFlagProfilePlatformEnableClickToCopyUsername_IXPValue": "true;1;Social.ProfilePeekView;Social.ProfileBackgrounds.GiveViewersAccessToNewBackgrounds;698399716;dev_controlled",
            "FFlagPPVBackgroundEnabled_IXPValue": "true;1;Social.ProfilePeekView;Social.ProfileBackgrounds.GiveViewersAccessToNewBackgrounds;766322282;dev_controlled",
            "FFlagAddPriceBelowCurrentlyWearing_IXPValue": "true;1;Social.Profile.Inventory;FeatureRollout;650888593;flagbank",
            "FFlagEnableDoubleNotifRegistrationFixV2_IXPValue": "true;1;Portal.EnableDoubleNotifRegistrationFixV2-1752599897;FeatureRollout;1249476439;flagbank",
            "FFlagEnableNotApprovedPageV2_IXPValue": "true;1;UserSafety.NotApprovedPage.UserID;UserSafety.NotApprovedPage.UserID.NotApprovedPageRedesign.2025Q3;1032022767;dev_controlled",
            "FFlagEnableNapIxpLayerExposure_IXPValue": "true;1;UserSafety.NotApprovedPage.UserID;UserSafety.NotApprovedPage.UserID.NotApprovedPageRedesign.2025Q3;1032022767;dev_controlled"
        }
        self.flag_entries = []  # List to store flag entry widgets
        self._build_ui()
        self._load_flags()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(15)

        # Title
        title = QLabel("FastFlag Editor")
        title.setObjectName("CardTitle")
        f = QFont()
        f.setPointSize(16)
        f.setBold(True)
        title.setFont(f)
        title.setAlignment(Qt.AlignCenter)
        layout.addWidget(title)

        # Add new flag section
        add_card = Card("Add FastFlag")
        add_layout = QHBoxLayout()
        add_layout.setSpacing(12)

        self.flag_name_input = Search("Flag Name (e.g., DFFlagMyCustomFlag)")
        self.flag_value_input = Search("Flag Value (e.g., true, false, 123)")
        add_btn = AccentButton("Add")
        add_btn.clicked.connect(self.add_flag)

        add_layout.addWidget(self.flag_name_input)
        add_layout.addWidget(self.flag_value_input)
        add_layout.addWidget(add_btn)
        add_card.body().addLayout(add_layout)
        layout.addWidget(add_card)

        # Import JSON section
        import_card = Card("Import JSON")
        import_layout = QHBoxLayout()
        import_layout.setSpacing(12)

        self.json_input = QTextEdit()
        self.json_input.setObjectName("CodeEditor")
        self.json_input.setPlaceholderText(
            '{"FlagName": "value", "AnotherFlag": "true"}')
        self.json_input.setMaximumHeight(80)

        import_btn = GhostButton("Import JSON")
        import_btn.clicked.connect(self.import_json)

        import_layout.addWidget(self.json_input, 3)
        import_layout.addWidget(import_btn)
        import_card.body().addLayout(import_layout)
        layout.addWidget(import_card)

        # Editable Flags display
        display_card = Card("Current Flags")

        # Scroll area for flag entries
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setFrameShape(QFrame.NoFrame)
        self.scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        # Container widget for flag entries
        self.flags_container = QWidget()
        self.flags_layout = QVBoxLayout(self.flags_container)
        self.flags_layout.setContentsMargins(5, 5, 5, 5)
        self.flags_layout.setSpacing(8)

        self.scroll_area.setWidget(self.flags_container)
        display_card.body().addWidget(self.scroll_area, 1)
        layout.addWidget(display_card, 1)

        # Control buttons
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(12)

        load_from_roblox_btn = GhostButton("Load from Roblox")
        load_from_roblox_btn.clicked.connect(self.load_from_roblox)

        refresh_btn = GhostButton("Refresh")
        refresh_btn.clicked.connect(self.refresh_flags)

        clear_btn = GhostButton("Clear All")
        clear_btn.clicked.connect(self.clear_flags)

        save_btn = AccentButton("Save to Roblox")
        save_btn.clicked.connect(self.save_flags)

        btn_layout.addWidget(load_from_roblox_btn)
        btn_layout.addWidget(refresh_btn)
        btn_layout.addWidget(clear_btn)
        btn_layout.addStretch()
        btn_layout.addWidget(save_btn)
        layout.addLayout(btn_layout)

        # Status
        self.status_label = QLabel("Ready")
        self.status_label.setObjectName("Caption")
        self.status_label.setAlignment(Qt.AlignCenter)
        self.status_label.setWordWrap(True)
        layout.addWidget(self.status_label)

    def _create_flag_entry(self, name, value):
        """Create a new editable flag entry widget"""
        entry_widget = QWidget()
        entry_layout = QHBoxLayout(entry_widget)
        entry_layout.setContentsMargins(8, 4, 8, 4)
        entry_layout.setSpacing(12)

        # Flag name input
        name_input = Search("")
        name_input.setText(name)
        name_input.setMinimumWidth(200)
        # Connect textChanged to immediate update function
        name_input.textChanged.connect(
            lambda: self._on_entry_text_changed(entry_widget))
        entry_layout.addWidget(name_input, 1)

        # Equals label
        equals_label = QLabel("=")
        equals_label.setObjectName("Caption")
        equals_label.setAlignment(Qt.AlignCenter)
        equals_label.setFixedWidth(20)
        entry_layout.addWidget(equals_label)

        # Flag value input
        value_input = Search("")
        value_input.setText(value)
        value_input.setMinimumWidth(200)
        # Connect textChanged to immediate update function
        value_input.textChanged.connect(
            lambda: self._on_entry_text_changed(entry_widget))
        entry_layout.addWidget(value_input, 1)

        # Delete button
        delete_btn = QPushButton("×")
        delete_btn.setObjectName("GhostButton")
        delete_btn.setFixedSize(30, 30)
        delete_btn.setStyleSheet("""
            QPushButton {
                background: rgba(231, 76, 60, 0.8);
                color: white;
                border: none;
                border-radius: 15px;
                font-size: 16px;
                font-weight: bold;
            }
            QPushButton:hover {
                background: rgba(231, 76, 60, 1.0);
            }
        """)
        delete_btn.clicked.connect(
            lambda: self._delete_flag_entry(entry_widget))
        entry_layout.addWidget(delete_btn)

        # Store references for easy access
        entry_widget.name_input = name_input
        entry_widget.value_input = value_input
        entry_widget.original_name = name  # Track original name for updates

        return entry_widget

    def _on_entry_text_changed(self, entry_widget):
        """Handle when entry text changes - update flags immediately"""
        old_name = entry_widget.original_name
        new_name = entry_widget.name_input.text().strip()
        new_value = entry_widget.value_input.text().strip()

        # Remove old entry if name changed
        if old_name != new_name and old_name in self.flags:
            del self.flags[old_name]

        # Add/update new entry
        if new_name:
            self.flags[new_name] = new_value
            entry_widget.original_name = new_name

    def _delete_flag_entry(self, entry_widget):
        """Delete a flag entry"""
        if entry_widget in self.flag_entries:
            # Remove from flags dict
            name = entry_widget.original_name
            if name in self.flags:
                del self.flags[name]
            # Remove from UI
            self.flag_entries.remove(entry_widget)
            entry_widget.setParent(None)

    def add_flag(self):
        name = self.flag_name_input.text().strip()
        value = self.flag_value_input.text().strip()
        if not name:
            self.status_label.setText("Enter a flag name!")
            return

        # Auto-add _IXPValue suffix if not present and it's a standard flag
        if name.startswith(('DFFlag', 'FFlag', 'SFFlag')) and not name.endswith('_IXPValue'):
            name += '_IXPValue'

        # Don't allow adding default flags
        if name in self.default_flags:
            self.status_label.setText(
                f"{name} is a default flag and cannot be added!")
            return

        # Check if flag already exists
        existing_entry = None
        for entry in self.flag_entries:
            if entry.name_input.text().strip() == name:
                existing_entry = entry
                break

        if existing_entry:
            # Flag already exists - ask if user wants to overwrite
            from PySide6.QtWidgets import QMessageBox
            reply = QMessageBox.question(
                self,
                "Flag Already Exists",
                f"The flag '{name}' already exists with value '{existing_entry.value_input.text()}'.\n\nWould you like to overwrite it with the new value '{value}'?",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No
            )

            if reply == QMessageBox.Yes:
                # Update existing entry
                existing_entry.value_input.setText(value)
                self.flags[name] = value
                self.status_label.setText(f"Updated {name}")
            else:
                self.status_label.setText("Operation cancelled")

            # Clear inputs either way
            self.flag_name_input.clear()
            self.flag_value_input.clear()
            return

        # Create new flag entry (flag doesn't exist yet)
        entry_widget = self._create_flag_entry(name, value)
        self.flag_entries.append(entry_widget)
        self.flags_layout.addWidget(entry_widget)

        # Add to flags dict
        self.flags[name] = value

        # Clear inputs
        self.flag_name_input.clear()
        self.flag_value_input.clear()

        self.status_label.setText(f"Added {name}")

    def import_json(self):
        json_text = self.json_input.toPlainText().strip()
        if not json_text:
            self.status_label.setText("Paste JSON data to import")
            return

        try:
            data = json.loads(json_text)
            added = 0
            updated = 0
            skipped = 0

            if isinstance(data, dict):
                for k, v in data.items():
                    if str(k) in self.default_flags:
                        skipped += 1
                        continue

                    # Check if flag already exists in entries
                    existing_entry = None
                    for entry in self.flag_entries:
                        if entry.name_input.text().strip() == str(k):
                            existing_entry = entry
                            break

                    if existing_entry:
                        # Update existing entry
                        existing_entry.value_input.setText(str(v))
                        self.flags[str(k)] = str(v)
                        updated += 1
                    else:
                        # Create new entry
                        entry_widget = self._create_flag_entry(str(k), str(v))
                        self.flag_entries.append(entry_widget)
                        self.flags_layout.addWidget(entry_widget)
                        self.flags[str(k)] = str(v)
                        added += 1

            elif isinstance(data, list):
                for item in data:
                    if isinstance(item, dict):
                        for k, v in item.items():
                            if str(k) in self.default_flags:
                                skipped += 1
                                continue

                            # Check if flag already exists
                            existing_entry = None
                            for entry in self.flag_entries:
                                if entry.name_input.text().strip() == str(k):
                                    existing_entry = entry
                                    break

                            if existing_entry:
                                # Update existing entry
                                existing_entry.value_input.setText(str(v))
                                self.flags[str(k)] = str(v)
                                updated += 1
                            else:
                                # Create new entry
                                entry_widget = self._create_flag_entry(
                                    str(k), str(v))
                                self.flag_entries.append(entry_widget)
                                self.flags_layout.addWidget(entry_widget)
                                self.flags[str(k)] = str(v)
                                added += 1

            if added > 0 or updated > 0:
                status_msg = []
                if added > 0:
                    status_msg.append(f"Added {added} flags")
                if updated > 0:
                    status_msg.append(f"updated {updated} flags")
                if skipped > 0:
                    status_msg.append(f"{skipped} default flags skipped")
                self.status_label.setText(" • ".join(status_msg))
                self.json_input.clear()
            else:
                self.status_label.setText("No valid flags found in JSON")

        except json.JSONDecodeError:
            # Try regex parsing for loose format
            import re
            pattern = r'"([^"]+)"\s*:\s*"([^"]*)"'
            matches = re.findall(pattern, json_text)
            added = 0
            updated = 0
            skipped = 0

            if matches:
                for name, value in matches:
                    if name in self.default_flags:
                        skipped += 1
                        continue

                    # Check if flag already exists
                    existing_entry = None
                    for entry in self.flag_entries:
                        if entry.name_input.text().strip() == name:
                            existing_entry = entry
                            break

                    if existing_entry:
                        # Update existing entry
                        existing_entry.value_input.setText(value)
                        self.flags[name] = value
                        updated += 1
                    else:
                        # Create new entry
                        entry_widget = self._create_flag_entry(name, value)
                        self.flag_entries.append(entry_widget)
                        self.flags_layout.addWidget(entry_widget)
                        self.flags[name] = value
                        added += 1

                if added > 0 or updated > 0:
                    status_msg = []
                    if added > 0:
                        status_msg.append(f"Added {added} flags")
                    if updated > 0:
                        status_msg.append(f"updated {updated} flags")
                    if skipped > 0:
                        status_msg.append(f"{skipped} default flags skipped")
                    self.status_label.setText(" • ".join(status_msg))
                    self.json_input.clear()
                else:
                    self.status_label.setText(
                        "Only default flags found - none imported")
            else:
                self.status_label.setText("Invalid JSON format")

    def load_from_roblox(self):
        try:
            home_dir = os.path.expanduser("~")
            file_path = os.path.join(
                home_dir, r"AppData\Local\Roblox\ClientSettings\IxpSettings.json")

            if not os.path.exists(file_path):
                self.status_label.setText("No Roblox settings file found")
                return

            with open(file_path, 'r', encoding='utf-8') as f:
                file_data = json.load(f)

            # Load ONLY differences from defaults - this is the key part!
            loaded = 0
            for key, file_value in file_data.items():
                # Skip if it's a default flag with default value
                if key in self.default_flags and self.default_flags[key] == file_value:
                    continue

                # Check if flag already exists in entries
                exists = False
                for entry in self.flag_entries:
                    if entry.name_input.text().strip() == key:
                        exists = True
                        break

                if not exists:  # Only add if not already present
                    entry_widget = self._create_flag_entry(
                        key, str(file_value))
                    self.flag_entries.append(entry_widget)
                    self.flags_layout.addWidget(entry_widget)
                    self.flags[key] = str(file_value)
                    loaded += 1

            self.status_label.setText(
                f"Loaded {loaded} custom flags from Roblox")

        except Exception as e:
            self.status_label.setText(f"Load error: {str(e)[:50]}...")

    def refresh_flags(self):
        """Refresh the flag list by reloading from Roblox"""
        # Clear current flags
        for entry in self.flag_entries[:]:
            entry.setParent(None)

        self.flag_entries.clear()
        self.flags.clear()

        # Reload from Roblox
        self._load_flags()
        self.status_label.setText("Refreshed flags from Roblox")

    def clear_flags(self):
        if not self.flag_entries:
            self.status_label.setText("No flags to clear")
            return

        count = len(self.flag_entries)

        # Remove all entry widgets
        for entry in self.flag_entries[:]:
            entry.setParent(None)

        self.flag_entries.clear()
        self.flags.clear()
        self.status_label.setText(f"Cleared {count} flags")

    def _load_flags(self):
        """Load flags that differ from defaults (like original does)"""
        try:
            home_dir = os.path.expanduser("~")
            file_path = os.path.join(
                home_dir, r"AppData\Local\Roblox\ClientSettings\IxpSettings.json")
            if os.path.exists(file_path):
                with open(file_path, 'r', encoding='utf-8') as f:
                    file_data = json.load(f)

                # Only load flags that differ from defaults (matching original logic)
                for key, file_value in file_data.items():
                    if key not in self.default_flags or self.default_flags[key] != file_value:
                        entry_widget = self._create_flag_entry(
                            key, str(file_value))
                        self.flag_entries.append(entry_widget)
                        self.flags_layout.addWidget(entry_widget)
                        self.flags[key] = str(file_value)

                if self.flags:
                    self.status_label.setText(
                        f"Loaded {len(self.flags)} custom flags from Roblox")
        except Exception as e:
            self.status_label.setText(f"Load error: {str(e)[:50]}...")

    def save_flags(self):
        try:
            home_dir = os.path.expanduser("~")
            roblox_path = os.path.join(home_dir, r"AppData\Local\Roblox")
            file_path = os.path.join(
                roblox_path, r"ClientSettings\IxpSettings.json")

            if not os.path.exists(roblox_path):
                self.status_label.setText(
                    "Roblox not found - please install Roblox first")
                return

            os.makedirs(os.path.dirname(file_path), exist_ok=True)

            # IMPORTANT: DON'T read existing settings! Only use defaults + custom flags
            # This ensures that when you clear custom flags, they actually get removed
            # Instead of being preserved from the existing file

            # Merge: defaults + user flags ONLY (user flags take priority)
            merged_data = {**self.default_flags, **self.flags}

            # Write to file with proper permissions
            try:
                os.chmod(file_path, stat.S_IWRITE)
            except:
                pass

            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(merged_data, f, indent=4)

            try:
                os.chmod(file_path, stat.S_IREAD)
            except:
                pass

            # Status message
            user_flags_count = len(self.flags)
            if user_flags_count == 0:
                self.status_label.setText(
                    "Saved - reset to default flags only")
            else:
                self.status_label.setText(
                    f"Saved {user_flags_count} custom flags")

        except Exception as e:
            self.status_label.setText(f"Save error: {str(e)[:50]}...")

# ==================== Main Application Entry Point ====================


def main():
    """Main application entry point"""
    # Enable high DPI support
    _safe_set_dpi_policy()

    app = QApplication(sys.argv)
    app.setApplicationName("Hopr")
    app.setApplicationVersion("2.0")
    app.setOrganizationName("Hopr Tools")

    # Set application style
    app.setStyle("Fusion")

    # Create and show main window
    window = Window()
    window.show()

    # Run the application
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
