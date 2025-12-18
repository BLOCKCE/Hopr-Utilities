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
import gzip
from urllib.parse import urlparse, urlunparse
from ctypes import wintypes
from datetime import datetime, timezone
from pathlib import Path
from io import BytesIO
from shiboken6 import isValid

# ensure Requests ignores system proxies to avoid hangs

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

from PySide6.QtCore import Qt, QSize, QEvent, QTimer, QRectF, Signal, QObject, QThread
from PySide6.QtGui import QFont, QPalette, QColor, QFontMetrics, QPainter, QPixmap, QImage, QPen
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QLabel, QLineEdit, QPushButton,
    QHBoxLayout, QVBoxLayout, QGridLayout, QScrollArea, QSplitter, QCheckBox,
    QFrame, QSizePolicy, QGraphicsDropShadowEffect, QMenu, QTextEdit,
    QColorDialog, QSlider, QWidgetAction, QSplitterHandle, QTabWidget, QTabBar,
    QDialog, QDialogButtonBox, QInputDialog, QMessageBox, QFileDialog, QComboBox
)

# GLOBAL VARIBLES

PROXY = None
ENABLE_GAME_JOIN_INTERCEPT = False
ENABLE_RESERVED_GAME_JOIN_INTERCEPT = False

LAST_accessCode = None
LAST_placeId = None
LAST_jobId = None


DELAY_REQUESTS = False
DELAY_REQUESTS_LIST = {}
CURRENT_FILTER = "All"

CACHES_BY_SOURCE = {}
CACHELOGS = {}


asset_types = {
    1: "Image",
    2: "TShirt",
    3: "Audio",
    4: "Mesh",
    5: "Lua",
    8: "Hat",
    9: "Place",
    10: "Model",
    11: "Shirt",
    12: "Pants",
    13: "Decal",
    17: "Head",
    18: "Face",
    19: "Gear",
    21: "Badge",
    24: "Animation",
    27: "Torso",
    28: "RightArm",
    29: "LeftArm",
    30: "LeftLeg",
    31: "RightLeg",
    32: "Package",
    34: "GamePass",
    38: "Plugin",
    40: "MeshPart",
    41: "HairAccessory",
    42: "FaceAccessory",
    43: "NeckAccessory",
    44: "ShoulderAccessory",
    45: "FrontAccessory",
    46: "BackAccessory",
    47: "WaistAccessory",
    48: "ClimbAnimation",
    49: "DeathAnimation",
    50: "FallAnimation",
    51: "IdleAnimation",
    52: "JumpAnimation",
    53: "RunAnimation",
    54: "SwimAnimation",
    55: "WalkAnimation",
    56: "PoseAnimation",
    57: "EarAccessory",
    58: "EyeAccessory",
    61: "EmoteAnimation",
    62: "Video",
    64: "TShirtAccessory",
    65: "ShirtAccessory",
    66: "PantsAccessory",
    67: "JacketAccessory",
    68: "SweaterAccessory",
    69: "ShortsAccessory",
    70: "LeftShoeAccessory",
    71: "RightShoeAccessory",
    72: "DressSkirtAccessory",
    73: "FontFamily",
    76: "EyebrowAccessory",
    77: "EyelashAccessory",
    78: "MoodAnimation",
    79: "DynamicHead",
    88: "FaceMakeup",
    89: "LipMakeup",
    90: "EyeMakeup",
}

# ADMIN


def ensure_admin_in_powershell():
    try:
        # Check admin privilege
        is_admin = ctypes.windll.shell32.IsUserAnAdmin()
    except:
        is_admin = False

    if not is_admin:
        print("Requesting Administrator PowerShell...")

        # Absolute path of current script
        script = os.path.abspath(sys.argv[0])

        # Include arguments passed to this script
        params = " ".join([f'"{arg}"' for arg in sys.argv[1:]])

        # Build PowerShell command line
        ps_command = f'& "{sys.executable}" "{script}" {params}'

        # Path to 64-bit PowerShell
        powershell_exe = r"C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe"

        # Launch elevated PowerShell
        ctypes.windll.shell32.ShellExecuteW(
            None,
            "runas",  # triggers UAC
            powershell_exe,
            f'-NoExit -Command {ps_command}',
            None,
            1
        )

        sys.exit(0)  # Exit the non-admin instance


ensure_admin_in_powershell()


# Theming helpers


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


# custom splitter
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

# micro-widgets


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

# PlaceCard with callbacks & async thumbnail


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

# collapsible hero


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


# Main Window


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


class CacheWarningDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Cache Editing Warning")
        self.setWindowFlags(Qt.Dialog | Qt.WindowTitleHint)
        self.setModal(True)
        self.setFixedSize(400, 200)

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
        warning_text = QLabel(
            "This can get you banned from some games if you are not careful")
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
            "Some games could flag you with their anti-cheat systems if your modified caches are too abusive or blatant.")
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
        self._invoker = _MainThreadInvoker(self)

        self.setWindowTitle("Hopr — Super cool thingaling👽")
        self.resize(1280, 820)
        self.setMinimumSize(780, 560)
        self._text_color = None
        self._btn_color = None
        self._card_width = 300
        self._theme = "dark"
        self._cards = []
        self.root_place_id = None
        self.thumb_cache = {}
        self._current_places = []
        self._results_gen = 0
        self._sort_option = "place_id_asc"

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
        self._show_cache_warning = True
        self._cache_warning_shown = False
        self._apply_theme(self._theme)
        self._build()
        self._apply_styles()
        self._load_settings()
        self._refresh_recents_and_favs()

    # Theme
    def _apply_theme(self, theme):
        app = QApplication.instance()
        app.setStyle("Fusion")
        set_app_palette(app, theme)

    def _apply_styles(self):
        self.setStyleSheet(gen_styles(self._text_color, self._btn_color))

    # UI build
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

        # Cache Editing tab --- muehehhehe 🤫
        cache_editing_widget = CacheEditingWidget()
        self.tab_widget.addTab(cache_editing_widget, "Cache Editing 👽")

        # Random Stuff tab
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
        filter_row = QHBoxLayout()
        filter_row.setSpacing(10)
        self.subplace_filter = Search("Filter subplaces (name or ID)…")
        self._filter_timer = QTimer(self)
        self._filter_timer.setSingleShot(True)
        self._filter_timer.timeout.connect(
            lambda: self._apply_subplace_filter(self.subplace_filter.text())
        )
        self.subplace_filter.textChanged.connect(
            lambda: self._filter_timer.start(120))
        filter_row.addWidget(self.subplace_filter, 2)
        self.clear_filter_btn = GhostButton("Clear")
        self.clear_filter_btn.clicked.connect(
            lambda: self.subplace_filter.setText(""))
        filter_row.addWidget(self.clear_filter_btn)
        search_card.body().addLayout(filter_row)
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
        main_split.setCollapsible(0, True)
        self.main_split = main_split
        self.main_split.splitterMoved.connect(
            lambda *_: (self._snap_left_closed(), self._apply_collapse_margin()))
        outer.addWidget(self.main_split, 1)
        self.grid_host.installEventFilter(self)
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

    # Event/layout helpers
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

    def _clear_results_grid(self):
        while self.grid.count():
            it = self.grid.takeAt(0)
            w = it.widget()
            if w is not None:
                w.setParent(None)
                w.deleteLater()

    def _scale_thumbs(self):
        scale = max(0.55, min(1.45, (self._card_width / 300.0)))
        for i in range(self.grid.count()):
            item = self.grid.itemAt(i)
            w = item.widget()
            if isinstance(w, PlaceCard):
                w.set_thumb_scale(scale)
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

    # Settings callbacks
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

    # Search / Results
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
        if place_id in self.recent_ids:
            self.recent_ids.remove(place_id)
        self.recent_ids.insert(0, place_id)
        self._save_settings(force=True)
        self._refresh_recents_and_favs()
        print(f"[SEARCH] start place={place_id}")
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

                    # Mark root place
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
            cookie = self.get_roblosecurity() or ""

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

        self._results_gen += 1
        gen = self._results_gen

        # Store places for sorting
        self._current_places = places.copy() if places else []

        # Sort and display
        self._clear_results_grid()

        if isinstance(places, dict):
            places = [places]
            self._current_places = places.copy()

        # Apply current sort
        sorted_places = self._sort_places(places)

        # Clear and display
        self._clear_results_grid()

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
            self._load_thumb_async_immediate(p.get('id'), card, gen)
        self._reflow_grid()
        self._scale_thumbs()
        self.status.setText(f"Found {len(places)} places")

    def _load_thumb_async_immediate(self, place_id, card: PlaceCard, gen: int):
        def worker():
            try:
                pix = self._fetch_thumb_pixmap(place_id)
                self._on_main(lambda: self._apply_thumb(card, pix, gen))
            except Exception as e:
                print(f"[THUMB] Error loading thumbnail for {place_id}: {e}")
                self._on_main(lambda: self._apply_thumb(card, None, gen))
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
        """Handle tab change - show Cache warning if needed"""
        # Check if we're switching to the Cache Editor tab (index 1)
        if index == 1 and self._show_cache_warning and not self._cache_warning_shown:
            self._show_cache_warning_dialog()

    def _show_cache_warning_dialog(self):
        """Show the Cache warning dialog"""
        dialog = CacheWarningDialog(self)
        result = dialog.exec()

        if result == QDialog.Accepted:
            self._cache_warning_shown = True
            if dialog.dont_show_again():
                self._show_cache_warning = False
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
        self._clear_results_grid()

        if not places:
            self.status.setText("No places found.")
            return

        self._results_gen += 1
        gen = self._results_gen

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
                self._load_thumb_async_immediate(place_id, card, gen)

        self._reflow_grid()
        self._scale_thumbs()

    def _apply_subplace_filter(self, text: str = ""):
        q = (text or "").strip().lower()

        base = self._current_places.copy() if self._current_places else []
        if not q:
            self._display_sorted_places(self._sort_places(base))
            self.status.setText(f"Found {len(base)} places")
            return

        def match(p: dict) -> bool:
            pid = str(p.get("id", "")).lower()
            name = str(p.get("name", "")).lower()
            return (q in pid) or (q in name)

        filtered = [p for p in base if isinstance(p, dict) and match(p)]
        self._display_sorted_places(self._sort_places(filtered))
        self.status.setText(f"Filtered: {len(filtered)}/{len(base)} places")

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

    # Thumbs
    def _load_thumb_async(self, place_id, card: PlaceCard):
        def worker():
            pix = self._fetch_thumb_pixmap(place_id)
            self._on_main(lambda: self._apply_thumb(card, pix))
        threading.Thread(target=worker, daemon=True).start()

    def _apply_thumb(self, card: PlaceCard, pix: QPixmap | None, gen: int):
        if gen != getattr(self, "_results_gen", 0):
            return

        if not isValid(card) or not hasattr(card, "thumb") or not isValid(card.thumb):
            return

        if pix is None:
            card.thumb.setText("(no image)")
            return

        card.thumb.setPixmap(pix.scaled(
            card.thumb.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation
        ))

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

    # Favorites / Recents
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
            chip.clicked.connect(lambda _, t=chip.text()                                 : self._quick_search(t))
        for chip in self.fav_flow.chips:
            chip.clicked.connect(lambda _, t=chip.text()                                 : self._quick_search(t))
        cur = self.search.text().strip()
        if cur and cur in self.favorites:
            self.fav_btn.setText("★ Faved")
        else:
            self.fav_btn.setText("★ Fav")

    def _quick_search(self, place_id: str):
        self.search.setText(str(place_id))
        self.on_search_clicked()

    # Cookie visibility
    def on_toggle_cookie(self):
        self.cookie_visible = not self.cookie_visible
        self.cookie_edit.setEchoMode(
            QLineEdit.Normal if self.cookie_visible else QLineEdit.Password)
        self.cookie_toggle.setText("Hide" if self.cookie_visible else "Show")

    # Join flow
    def join_flow(self, place_id):

        # Record subplace in recents immediately
        pid = str(place_id)
        if pid.isdigit():
            if pid in self.recent_ids:
                self.recent_ids.remove(pid)
            self.recent_ids.insert(0, pid)
            self._save_settings(force=True)
            self._refresh_recents_and_favs()

        cookie = self.get_roblosecurity() or ""
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
    # Launch & helpers

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

    # Cookie auto-read (Windows DPAPI)
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

    # Settings persistence
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
        self._show_cache_warning = d.get(
            "show_cache_warning", True)  # Load warning setting
        if d.get("save_settings", True):
            self.save_settings_chk.setChecked(True)
        self._apply_theme(self._theme)
        self._apply_styles()

    def _save_settings(self, force=False):
        # Persist history/favorites regardless; theme/colors guarded by checkbox unless force=True
        d = {
            "recent_ids": self.recent_ids[:200],
            "favorites": sorted(self.favorites, key=lambda x: int(x)),
            "show_cache_warning": self._show_cache_warning,
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

    # Misc
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

# Tps kill


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

# Proxy functions


def is_base64(s: str) -> bool:
    if not isinstance(s, str):
        return False
    try:
        # base64 MUST decode without errors AND re-encode to the same string (ignoring padding)
        decoded = base64.b64decode(s, validate=True)
        encoded = base64.b64encode(decoded).decode("ascii").rstrip("=")
        return s.rstrip("=") == encoded
    except Exception:
        return False


def send_delayed_request(key: str):
    """Send a single delayed request by its ID."""
    global DELAY_REQUESTS_LIST

    flow = DELAY_REQUESTS_LIST.get(key)
    if not flow:
        print(f"[DELAY] No delayed request with ID {key}")
        return

    # Resume / send the request
    flow.resume()
    print(f"[DELAY] Sent delayed request {key} -> {flow.request.pretty_url}")

    # Remove it from the queue
    DELAY_REQUESTS_LIST.pop(key, None)


def send_all_delayed_requests():
    """Send all delayed requests."""
    global DELAY_REQUESTS_LIST

    keys = list(DELAY_REQUESTS_LIST.keys())
    for key in keys:
        send_delayed_request(key)


def set_delay_requests(enabled: bool):
    global DELAY_REQUESTS
    DELAY_REQUESTS = enabled
    print(f"[DELAY] Delay mode {'enabled' if enabled else 'disabled'}")

    if not DELAY_REQUESTS:
        print("[DELAY] Sending all delayed requests because delay was disabled")
        send_all_delayed_requests()


class Interceptor:

    # Constants
    WANTED_JOIN_ENDPOINTS = (
        "/v1/join-game",
        "/v1/join-play-together-game",
        "/v1/join-game-instance",
    )
    WANTED_REJOIN_ENDPOINTS = (
        "/v1/join-reserved-game",
        "/v1/join-game-instance",
    )
    RESERVED_ENDPOINT = "/v1/join-reserved-game"
    JOIN_ENDPOINT = "/v1/join-game"
    DELIVERY_ENDPOINT = "/v1/assets/batch"

    def parse_body(self, content: bytes, encoding: str):
        if encoding == "gzip":
            try:
                content = gzip.decompress(content)
            except OSError:
                # Not actually gzipped, just fall back to raw bytes
                pass
        try:
            return json.loads(content)
        except Exception as e:
            print("Failed to parse JSON:", e)
            return None

    # MITM Request Handler
    def request(self, flow: 'http.HTTPFlow') -> None:
        global LAST_accessCode
        global LAST_placeId
        global CACHELOGS
        global DELAY_REQUESTS
        global DELAY_REQUESTS_LIST
        url = flow.request.pretty_url
        parsed_url = urlparse(url)
        content_type = flow.request.headers.get("Content-Type", "").lower()
        content_encoding = flow.request.headers.get(
            "Content-Encoding", "").lower()

        if DELAY_REQUESTS and "fts.rbxcdn.com" in url:
            req_base = url.split("?")[0]
            # print(response_base)
            asset_type_id = None

            # Search CACHELOGS for a matching location
            for info in CACHELOGS.values():
                if not isinstance(info, dict):
                    continue
                location = info.get("location")
                if not location:
                    continue
                cached_base = location.split("?")[0]
                if cached_base == req_base:
                    asset_type_id = info.get("assetTypeId")
                    break
            if asset_type_id is not None:
                asset_type_name = asset_types.get(asset_type_id, "Unknown")
                print(
                    f"[DELAY] Asset type ID: {asset_type_id}, Type: {asset_type_name}")

                # Only delay if it matches the CURRENT_FILTER or CURRENT_FILTER is "All"
                if CURRENT_FILTER == "All" or CURRENT_FILTER == asset_type_name:
                    key = str(uuid.uuid4())  # unique ID for this request
                    DELAY_REQUESTS_LIST[key] = flow
                    print(f"[DELAY]")

                    # Prevent the request from actually sending
                    flow.intercept()
                    return

        if ENABLE_RESERVED_GAME_JOIN_INTERCEPT == False:
            if (parsed_url.path == "/v1/join-reserved-game" or parsed_url.path == "/v1/join-game") and "application/json" in content_type:
                data = flow.request.json()
                if data.get("accessCode"):
                    LAST_accessCode = data.get("accessCode")
                    print("SET LAST_accessCode:", LAST_accessCode)
                else:
                    LAST_accessCode = None
                if data.get("placeId"):
                    print("SET LAST_placeId:", data.get("placeId"))
                    LAST_placeId = data.get("placeId")
                else:
                    LAST_placeId = None

        # Game Join Intercept
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
            if parsed_url.path == self.JOIN_ENDPOINT:
                print("[RESERVE] Intercepting reserved game join")
                try:
                    body_json = flow.request.json()
                except Exception:
                    return
                if "isTeleport" not in body_json:
                    body_json["isTeleport"] = True
                    print("[RESERVE] Added teleport flag")
                if LAST_accessCode:
                    body_json["accessCode"] = LAST_accessCode
                    print("USING LAST_accessCode:", LAST_accessCode)
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
        req_content_encoding = flow.request.headers.get(
            "Content-Encoding", ""
        ).lower()
        content_encoding = flow.response.headers.get(
            "Content-Encoding", ""
        ).lower()

        if "assetdelivery.roblox.com" in url:
            if parsed_url.path == self.DELIVERY_ENDPOINT:
                body_req_json = self.parse_body(
                    flow.request.content, req_content_encoding)
                body_res_json = self.parse_body(
                    flow.response.content, content_encoding)
                if not body_res_json or not body_req_json:
                    return

                for index, item in enumerate(body_req_json):
                    if "assetId" in item:
                        ID = item["assetId"]

                        if index < len(body_res_json):
                            res_item = body_res_json[index]

                            # Safely get fields
                            location = res_item.get("location")
                            asset_type = res_item.get("assetTypeId")

                            if location is not None and asset_type is not None:
                                CACHELOGS[ID] = {}
                                CACHELOGS[ID]["location"] = location
                                CACHELOGS[ID]["assetTypeId"] = asset_type

        response_base = url.split("?")[0]
        # print(response_base)
        for ID, info in CACHELOGS.items():
            if "location" in info:
                cached_base = info["location"].split("?")[0]

                if cached_base == response_base:

                    def matches(c):
                        if not c.get("enabled", True):
                            return False

                        replace_kind = c.get("replace_kind")
                        replace_hash = c.get("replace_hash")

                        # Case: replace by ID
                        if replace_kind == "id":
                            return str(replace_hash) == str(ID)

                        # Case: replace by hash
                        elif replace_kind == "hash":
                            current_hash = base64.b64encode(
                                flow.response.content).decode("ascii")

                            # only compare if replace_hash is valid base64
                            if not is_base64(str(replace_hash)):
                                return False

                            return str(replace_hash) == current_hash

                        return False

                    cache_item = next(
                        (c for c in CACHES_BY_SOURCE.get(
                            "Default", []) if matches(c)),
                        None
                    )

                    # Always update log
                    CACHELOGS[ID]["Hash"] = flow.response.content

                    if cache_item:

                        # Case: ID → we expect binary to be valid base64
                        if cache_item.get("hash_kind") == "id" and "binary" in cache_item:
                            if is_base64(cache_item["binary"]):
                                flow.response.content = base64.b64decode(
                                    cache_item["binary"])

                        # Case: Hash → use_hash must be valid base64
                        elif cache_item.get("hash_kind") == "hash" and "use_hash" in cache_item:
                            if is_base64(cache_item["use_hash"]):
                                flow.response.content = base64.b64decode(
                                    cache_item["use_hash"])

                    break

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
                data = flow.response.json()
                if data.get("status") == 2:
                    ENABLE_GAME_JOIN_INTERCEPT = False
            except Exception:
                # fallback: get text and output as a JSON string
                pass

            # Always print valid JSON (compact). Use ensure_ascii=False to keep unicode readable.
            # print(json.dumps(data, ensure_ascii=False))
        if ENABLE_RESERVED_GAME_JOIN_INTERCEPT:
            if any(p in url for p in self.WANTED_REJOIN_ENDPOINTS):

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


# Chrome-like Tab System


class ChromeTabBar(QTabBar):
    def __init__(self):
        super().__init__()
        self.setObjectName("ChromeTabBar")
        self.setExpanding(False)
        self.setMovable(True)
        self.setTabsClosable(False)


class ChromeTabWidget(QTabWidget):
    def __init__(self):
        super().__init__()
        self.setObjectName("ChromeTabWidget")
        self.setTabBar(ChromeTabBar())
        self.setTabPosition(QTabWidget.North)

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

# Random Stuff widget


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

        btn_row = QHBoxLayout()

        self.rejoin_btn = AccentButton("Rejoin Reserved Server")
        self.rejoin_btn.clicked.connect(self.start_rejoin_thread)
        btn_row.addWidget(self.rejoin_btn)

        body.addLayout(btn_row)

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
                        r = sess.get(
                            f"https://games.roblox.com/v1/games/multiget-place-details?placeIds={LAST_placeId}", timeout=5)
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

# Cache Editing Main Widget with Child Tabs


class CacheEditingWidget(QWidget):
    def __init__(self):
        super().__init__()
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(15)

        # Title
        title = QLabel("Cache Editing 👽")
        title.setObjectName("CardTitle")
        f = QFont()
        f.setPointSize(16)
        f.setBold(True)
        title.setFont(f)
        title.setAlignment(Qt.AlignCenter)
        layout.addWidget(title)

        # Child tab widget
        self.child_tabs = ChromeTabWidget()

        # Add the three child tabs
        cache_loader_widget = CacheLoaderWidget()
        self.child_tabs.addTab(cache_loader_widget, "Cache Loader")

        # pass both "get current caches" *and* "set caches from collection"
        collections_widget = CollectionsWidget(
            cache_loader_widget.get_all_enabled_caches,
            cache_loader_widget.set_caches_from_collection,
        )
        self.child_tabs.addTab(collections_widget, "Collections")

        cache_finder_widget = CacheFinderWidget()
        self.child_tabs.addTab(cache_finder_widget, "Cache Finder")

        layout.addWidget(self.child_tabs)

# Cache Loader Widget


class CacheLoaderWidget(QWidget):

    def __init__(self):
        super().__init__()

        self.cache_entries = []

        self.sources = ["Default"]
        self.current_source = "Default"

        self.caches_file = self._ensure_caches_file()
        self._rebuild_state_from_disk()

        self._build_ui()
        self.refresh_caches()
        self.selected_index = -1

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 15, 0, 0)
        layout.setSpacing(15)

        # Source selection
        source_card = Card("Cache Loader")
        source_layout = QHBoxLayout()
        source_layout.setSpacing(12)

        source_layout.addWidget(QLabel("Source:"))

        self.source_combo = GhostButton(self.current_source)
        self.source_menu = QMenu(self.source_combo)
        self._rebuild_source_menu()
        self.source_combo.setMenu(self.source_menu)
        self.source_combo.clicked.connect(self.source_combo.showMenu)

        source_layout.addWidget(self.source_combo)
        source_layout.addStretch()

        source_card.body().addLayout(source_layout)
        layout.addWidget(source_card)

        # Search area
        search_card = Card()
        search_layout = QVBoxLayout()
        search_layout.setSpacing(10)

        # Search available
        search_available_layout = QHBoxLayout()
        search_available_layout.setSpacing(12)

        search_available_layout.addWidget(QLabel("Search available"))
        self.search_input = Search("Search available...")
        search_available_layout.addWidget(self.search_input)

        search_layout.addLayout(search_available_layout)

        # Search loaded
        search_loaded_layout = QHBoxLayout()
        search_loaded_layout.setSpacing(12)

        search_loaded_layout.addWidget(QLabel("Search loaded"))
        self.search_loaded_input = Search("Search loaded...")
        search_loaded_layout.addWidget(self.search_loaded_input)

        self.search_input.textChanged.connect(self.refresh_caches)
        self.search_loaded_input.textChanged.connect(self.refresh_caches)

        search_layout.addLayout(search_loaded_layout)

        search_card.body().addLayout(search_layout)
        layout.addWidget(search_card)

        # Loaded caches list
        results_card = Card("Loaded Caches")

        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setFrameShape(QFrame.NoFrame)
        self.scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        self.cache_container = QWidget()
        self.cache_layout = QVBoxLayout(self.cache_container)
        self.cache_layout.setContentsMargins(5, 5, 5, 5)
        self.cache_layout.setSpacing(8)

        self.scroll_area.setWidget(self.cache_container)
        results_card.body().addWidget(self.scroll_area, 1)
        layout.addWidget(results_card, 1)

        # Bottom buttons
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(12)

        self.create_cache_btn = GhostButton("Create cache")
        self.db_btn = GhostButton("Delete DB")
        self.refresh_btn = GhostButton("Refresh")

        btn_layout.addWidget(self.create_cache_btn)
        btn_layout.addWidget(self.db_btn)
        btn_layout.addWidget(self.refresh_btn)
        btn_layout.addStretch()

        layout.addLayout(btn_layout)

        # Connect buttons
        self.create_cache_btn.clicked.connect(self.create_cache)
        self.db_btn.clicked.connect(self.delete_db)
        self.refresh_btn.clicked.connect(self.refresh_caches)

    # Source menu helpers
    def _set_source(self, source: str):
        global CACHES_BY_SOURCE
        self.current_source = source
        self.source_combo.setText(source)
        if source not in CACHES_BY_SOURCE:
            CACHES_BY_SOURCE[source] = []
        self.refresh_caches()
        self._rebuild_source_menu()

    def _rebuild_source_menu(self):
        self.source_menu.clear()

        # existing sources
        for source in self.sources:
            action = self.source_menu.addAction(source)
            action.triggered.connect(
                lambda checked=False, s=source: self._set_source(s)
            )

        self.source_menu.addSeparator()

        add_action = self.source_menu.addAction("Add source…")
        add_action.triggered.connect(self._prompt_add_source)

        if self.source_combo.text() != "Default":
            rem_action = self.source_menu.addAction("Remove current source")
            rem_action.triggered.connect(self._remove_current_source)

    def _prompt_add_source(self):
        name, ok = QInputDialog.getText(self, "Add source", "Source name:")
        if not ok:
            return
        name = name.strip()
        if not name:
            return
        if name not in self.sources:
            self.sources.append(name)
        self._set_source(name)
        self._rebuild_source_menu()
        self._save_caches()

    def _remove_current_source(self):
        global CACHES_BY_SOURCE
        cur = self.source_combo.text()
        if cur != "Default" and cur in self.sources:
            self.sources.remove(cur)
            CACHES_BY_SOURCE.pop(cur, None)
        self._set_source("Default")
        self._rebuild_source_menu()
        self._save_caches()

    # disk helpers for caches
    def _ensure_caches_file(self) -> str:
        local_appdata = os.getenv("LOCALAPPDATA") or ""
        base_dir = os.path.join(local_appdata, "SubplaceJoiner")
        os.makedirs(base_dir, exist_ok=True)

        file_path = os.path.join(base_dir, "caches.json")
        if not os.path.exists(file_path):
            with open(file_path, "w", encoding="utf-8") as f:
                json.dump({"sources": ["Default"], "items": []}, f, indent=2)
        return file_path

    def _load_caches(self):
        try:
            with open(self.caches_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            if not isinstance(data, list):
                data = []
        except Exception:
            data = []
        return data

    def _rebuild_state_from_disk(self):
        global CACHES_BY_SOURCE
        """
        Read caches.json and rebuild:
          - self.sources          (list of source names)
          - self.CACHES_BY_SOURCE (source -> list of caches)
          - self.current_source   (selected source)
        Supports both:
          * old format: [ {..cache..}, ... ]
          * new format: { "sources": [...], "items": [ {...}, ... ] }
        """
        self.sources = []
        CACHES_BY_SOURCE = {}

        try:
            with open(self.caches_file, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception:
            data = []

        flat = []
        if isinstance(data, dict):
            file_sources = data.get("sources")
            if isinstance(file_sources, list):
                self.sources = [str(s) for s in file_sources if str(s).strip()]
            flat = data.get("items", [])
        elif isinstance(data, list):
            flat = data

        for item in flat or []:
            src = item.get("source") or "Default"
            if src not in self.sources:
                self.sources.append(src)

            # make sure "enabled" always exists (default True)
            if "enabled" not in item:
                item["enabled"] = True

            clean = {
                k: v for k, v in item.items()
                if k != "widget"
            }
            CACHES_BY_SOURCE.setdefault(src, []).append(clean)

        if not self.sources:
            self.sources = ["Default"]
        if not getattr(self, "current_source", None) or self.current_source not in self.sources:
            self.current_source = self.sources[0]
        for s in self.sources:
            CACHES_BY_SOURCE.setdefault(s, [])

    def _save_caches(self):
        global CACHES_BY_SOURCE

        # 1) Ensure currently visible rows push their checkbox state into the dicts
        #    (this only touches *live* widgets in self.cache_entries)
        if hasattr(self, "_sync_enabled_states"):
            self._sync_enabled_states()

        try:
            items = []

            for src, lst in CACHES_BY_SOURCE.items():
                for cache in lst:
                    d = {}

                    # Trust the cache dict as the source of truth
                    enabled_val = cache.get("enabled", True)

                    # copy all JSON-safe primitive fields
                    for key, value in cache.items():
                        if isinstance(value, (str, int, float, bool)) or value is None:
                            d[key] = value

                    # force the authoritative enabled value
                    d["enabled"] = bool(enabled_val)
                    d["source"] = src

                    items.append(d)

            data = {
                "sources": self.sources,
                "items": items,
            }

            with open(self.caches_file, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)

        except Exception as e:
            print("Failed to save caches:", e)

    def _shorten_preview(self, value: str, limit: int = 5) -> str:
        if value is None:
            return ""
        s = str(value)
        if len(s) <= limit:
            return s
        return s[:limit] + "..."

    # Cache row helpers
    def _create_cache_entry(self, cache: dict) -> QWidget:
        entry_widget = QWidget()
        entry_layout = QVBoxLayout(entry_widget)
        entry_layout.setContentsMargins(8, 4, 8, 4)
        entry_layout.setSpacing(4)

        # Header
        header_widget = QWidget()
        header_widget.setAttribute(Qt.WA_StyledBackground, True)
        header_widget.setStyleSheet(
            "background: transparent; border-radius: 8px;"
        )

        header_layout = QHBoxLayout(header_widget)
        header_layout.setContentsMargins(8, 2, 8, 2)
        header_layout.setSpacing(8)

        # Checkbox
        checkbox = QCheckBox()
        checkbox.setChecked(cache.get("enabled", True))

        # Make sure it saves the state
        def on_checkbox_state_changed(state, c=cache):
            c["enabled"] = (state == Qt.Checked)
            self._save_caches()

        checkbox.stateChanged.connect(on_checkbox_state_changed)

        checkbox.setAttribute(Qt.WA_TranslucentBackground, True)
        checkbox.setStyleSheet("background: transparent;")
        checkbox.setStyleSheet("""
            QCheckBox {
                background: transparent;
            }

            QCheckBox::indicator {
                width: 16px;
                height: 16px;
                border-radius: 3px;
                background: rgba(0,0,0,40);
                border: 1px solid rgba(255,255,255,120);
            }

            QCheckBox::indicator:checked {
                background: #3B82F6;
                border: 1px solid #3B82F6;
                image: url(:/qt-project.org/styles/commonstyle/images/checkmark.png);
            }

            QCheckBox::indicator:unchecked {
                image: none;
            }
        """)
        header_layout.addWidget(checkbox)

        # Name input (read-only)
        name_input = Search("")
        name_input.setText(cache.get("name", ""))
        name_input.setReadOnly(True)
        name_input.setFocusPolicy(Qt.NoFocus)
        name_input.setCursor(Qt.PointingHandCursor)
        name_input.setMinimumWidth(200)
        header_layout.addWidget(name_input, 1)

        # Caption showing hash mapping
        use_hash = cache.get("use_hash") or cache.get("hash", "")
        replace_hash = cache.get("replace_hash") or cache.get("replace", "")

        use_display = self._shorten_preview(use_hash, 5)
        replace_display = self._shorten_preview(replace_hash, 5)

        mapping_label = QLabel(
            f"use {use_display}  (replace {replace_display})")
        mapping_label.setObjectName("CacheMappingLabel")
        mapping_label.setCursor(Qt.PointingHandCursor)
        mapping_label.setAlignment(Qt.AlignVCenter | Qt.AlignRight)
        mapping_label.setStyleSheet("""
            QLabel#CacheMappingLabel {
                background-color: transparent;
                padding: 0;
                margin: 0;
            }
        """)

        header_layout.addWidget(mapping_label, 0)
        entry_layout.addWidget(header_widget)

        # Checkbox → highlight sync
        def update_header_highlight():
            if checkbox.isChecked():
                header_widget.setStyleSheet(
                    "background-color: rgba(59,130,246,35); border-radius: 8px;"
                )
                name_input.setStyleSheet(
                    "border:1px solid #3B82F6; border-radius:10px; background:rgba(59,130,246,40);"
                )
            else:
                header_widget.setStyleSheet(
                    "background: transparent; border-radius: 8px;"
                )
                name_input.setStyleSheet(
                    "border:1px solid rgba(255,255,255,26); border-radius:10px; background:transparent;"
                )

        checkbox.stateChanged.connect(update_header_highlight)
        update_header_highlight()

        # Toggle checkbox when clicking anywhere on the row
        def make_toggle(widget):
            old = widget.mousePressEvent

            def handler(event):
                if event.button() == Qt.LeftButton:
                    checkbox.toggle()
                if old:
                    old(event)

            widget.mousePressEvent = handler

        make_toggle(header_widget)
        make_toggle(name_input)
        make_toggle(mapping_label)

        # Context menu on the whole row
        entry_widget.setContextMenuPolicy(Qt.CustomContextMenu)
        entry_widget.customContextMenuRequested.connect(
            lambda pos, w=entry_widget: self._show_cache_context_menu(w, pos)
        )

        # Store references on the row
        cache["widget"] = entry_widget
        entry_widget.checkbox = checkbox
        entry_widget.name_input = name_input
        entry_widget.header_widget = header_widget
        entry_widget.mapping_label = mapping_label
        entry_widget.cache_data = cache

        entry_widget.installEventFilter(self)
        name_input.setContextMenuPolicy(Qt.NoContextMenu)
        name_input.installEventFilter(self)
        mapping_label.installEventFilter(self)

        return entry_widget

    def eventFilter(self, obj, event):
        if event.type() == QEvent.MouseButtonPress:
            if hasattr(event, "button") and event.button() != Qt.LeftButton:
                return False

            if obj in self.cache_entries:
                idx = self.cache_entries.index(obj)
                self._on_entry_clicked(idx)
                return False

            for i, row in enumerate(self.cache_entries):
                if getattr(row, "name_input", None) is obj:
                    self._on_entry_clicked(i)
                    return True

        if event.type() == QEvent.ContextMenu:
            for i, row in enumerate(self.cache_entries):
                name_input = getattr(row, "name_input", None)
                if name_input is obj:
                    try:
                        global_pos = event.globalPos()
                        local_pos = row.mapFromGlobal(global_pos)
                    except Exception:
                        from PySide6.QtCore import QPoint
                        local_pos = QPoint(0, 0)

                    self._show_cache_context_menu(row, local_pos)
                    return True

        return super().eventFilter(obj, event)

    def _on_entry_clicked(self, index: int):
        """Single-select + toggle the checkbox for this cache row."""
        if index < 0 or index >= len(self.cache_entries):
            return

        # Update selected index + visuals
        self.selected_index = index
        self._update_selection_styles()

        # Toggle the checkbox
        row = self.cache_entries[index]
        checkbox = getattr(row, "checkbox", None)
        if checkbox is not None:
            checkbox.setChecked(not checkbox.isChecked())

    def _update_selection_styles(self):
        """Highlight selected cache like collections (outline the text in blue)."""

        for i, row in enumerate(self.cache_entries):
            header = getattr(row, "header_widget", None)
            name_input = getattr(row, "name_input", None)

            if not name_input:
                continue

            if i == self.selected_index:
                if header is not None:
                    header.setStyleSheet("""
                        QWidget#CacheHeader {
                            background-color: rgba(59, 130, 246, 35);
                            border-radius: 8px;
                        }
                    """)

                name_input.setStyleSheet("""
                    QLineEdit {
                        border: 1px solid #3B82F6;
                        border-radius: 10px;
                        background-color: rgba(59, 130, 246, 40);
                    }
                """)
            else:
                if header is not None:
                    header.setStyleSheet("""
                        QWidget#CacheHeader {
                            background-color: transparent;
                            border-radius: 8px;
                        }
                    """)

                name_input.setStyleSheet("""
                    QLineEdit {
                        border: 1px solid rgba(255, 255, 255, 26);
                        border-radius: 10px;
                        background-color: transparent;
                    }
                """)

    def _show_cache_context_menu(self, entry_widget: QWidget, pos):
        cache = getattr(entry_widget, "cache_data", None)
        if not cache:
            return

        menu = QMenu(entry_widget)

        # Move submenu
        move_menu = menu.addMenu("Move to source")

        for src in self.sources:
            if src == self.current_source:
                continue
            act = move_menu.addAction(src)
            act.triggered.connect(
                lambda checked=False, s=src, c=cache: self._move_cache_to_source(
                    c, s)
            )

        if not move_menu.actions():
            move_menu.setEnabled(False)

        # delete option
        menu.addSeparator()
        delete_act = menu.addAction("Delete cache")
        delete_act.triggered.connect(
            lambda checked=False, c=cache: self._delete_cache(c)
        )

        menu.exec(entry_widget.mapToGlobal(pos))

    def _move_cache_to_source(self, cache: dict, target_source: str):
        global CACHES_BY_SOURCE
        src = cache.get("source", self.current_source)
        if target_source == src:
            return

        # remove from current
        if src in CACHES_BY_SOURCE:
            try:
                CACHES_BY_SOURCE[src].remove(cache)
            except ValueError:
                pass

        # add to target
        CACHES_BY_SOURCE.setdefault(target_source, []).append(cache)
        cache["source"] = target_source

        if target_source not in self.sources:
            self.sources.append(target_source)
            self._rebuild_source_menu()

        # refresh view (still on current_source)
        self.refresh_caches()
        self._save_caches()

    def _delete_cache(self, cache: dict):
        global CACHES_BY_SOURCE
        """Delete a single cache from its source and refresh/save."""
        src = cache.get("source", self.current_source)

        # Remove from data model
        if src in CACHES_BY_SOURCE:
            try:
                CACHES_BY_SOURCE[src].remove(cache)
            except ValueError:
                pass

        # Refresh UI + persist
        self.refresh_caches()
        self._save_caches()

    # This is the one CollectionsWidget will call
    def get_current_caches(self):
        global CACHES_BY_SOURCE
        """
        Return list of dicts for caches that are *enabled* in the
        current source:

        [{ "name": ..., "hash": <hash to USE>, "replace_hash": ... }, ...]
        Collections already reads "name" and "hash"; we add "replace_hash".
        """
        caches = []
        for cache in CACHES_BY_SOURCE.get(self.current_source, []):
            if cache.get("enabled", True):
                caches.append(
                    {
                        "name": cache.get("name", ""),
                        "hash": cache.get("use_hash") or cache.get("hash", ""),
                        "replace_hash": cache.get("replace_hash") or cache.get("replace", ""),
                    }
                )
        return caches

    def get_all_enabled_caches(self):
        global CACHES_BY_SOURCE

        self._sync_enabled_states()

        items = []
        for src, lst in CACHES_BY_SOURCE.items():
            for cache in lst:
                if cache.get("enabled", True):
                    items.append({
                        "source": src,
                        "name": cache.get("name", ""),
                        "hash": cache.get("use_hash") or cache.get("hash", ""),
                        "replace_hash": cache.get("replace_hash") or cache.get("replace", ""),
                    })
        return items

    def set_caches_from_collection(self, items):
        global CACHES_BY_SOURCE

        self._clear_ui_rows()
        self.cache_entries.clear()

        for item in (items or []):
            src = (item.get("source") or "Default").strip() or "Default"
            name = (item.get("name") or "").strip()
            if not name:
                continue

            use_hash = item.get("hash", "")
            replace_hash = item.get("replace_hash", "")

            CACHES_BY_SOURCE.setdefault(src, [])

            found = None
            for c in CACHES_BY_SOURCE[src]:
                if (c.get("name") or "").strip() == name:
                    found = c
                    break

            if found:
                found["use_hash"] = use_hash
                found["replace_hash"] = replace_hash
                found["enabled"] = True
                found["source"] = src
            else:
                CACHES_BY_SOURCE[src].append({
                    "id": str(uuid.uuid4()),
                    "source": src,
                    "name": name,
                    "use_hash": use_hash,
                    "replace_hash": replace_hash,
                    "enabled": True,
                })

        self.refresh_caches()
        self._save_caches()

    def apply_cache(self):
        global CACHES_BY_SOURCE
        active = [
            c for c in CACHES_BY_SOURCE.get(self.current_source, [])
            if c.get("enabled", True)
        ]
        print(
            f"Apply cache clicked; {len(active)} active cache(s) "
            f"for source '{self.current_source}'"
        )

    def create_cache(self):
        global CACHES_BY_SOURCE
        source = self.current_source
        if not source:
            return

        # 1) Name
        name, ok = QInputDialog.getText(
            self,
            "Cache name",
            "Name for this cache:",
        )
        if not ok:
            return
        name = name.strip()
        if not name:
            return

        # 2) Hash/ID to USE
        use_value, ok = self._prompt_hash_with_import(
            "Hash/ID to use",
            "Hash/ID that should be used:",
        )
        if not ok:
            return
        use_value = use_value.strip()
        if not use_value:
            return

        # 3) Hash/ID to REPLACE
        replace_value, ok = self._prompt_hash_with_import(
            "Hash/ID to replace",
            "Hash/ID that should be replaced:",
        )
        if not ok:
            return
        replace_value = replace_value.strip()
        if not replace_value:
            return

        # classify both
        use_kind = self._classify_hash_or_id(use_value)
        replace_kind = self._classify_hash_or_id(replace_value)

        # debug print
        print(
            f"[CacheLoader] New cache '{name}': "
            f"use={use_value} ({use_kind}), replace={replace_value} ({replace_kind})"
        )

        cache = {
            "id": str(uuid.uuid4()),
            "name": name,
            "use_hash": use_value,
            "replace_hash": replace_value,
            "hash_kind": use_kind,
            "replace_kind": replace_kind,
            "enabled": False,
            "source": source,
        }

        CACHES_BY_SOURCE.setdefault(source, []).append(cache)
        self.refresh_caches()
        self._save_caches()

        self.fetch_new_assets()

    def _classify_hash_or_id(self, value: str) -> str:
        """
        Very simple classifier:
        - only digits      -> 'id'
        - any letters      -> 'hash'
        - anything else    -> 'unknown'
        """
        v = value.strip()
        if not v:
            return "unknown"

        has_digit = any(c.isdigit() for c in v)
        has_alpha = any(c.isalpha() for c in v)

        if v.isdigit():
            return "id"

        if has_alpha:
            return "hash"

        return "unknown"

    def _prompt_hash_with_import(self, title: str, label: str, initial: str = ""):
        """Ask for a hash, with an 'Import from file' option."""
        dlg = QDialog(self)
        dlg.setWindowTitle(title)
        dlg.setModal(True)
        dlg.setStyleSheet(self.styleSheet())  # keep theming

        v = QVBoxLayout(dlg)
        v.setContentsMargins(14, 14, 14, 14)
        v.setSpacing(10)

        lbl = QLabel(label)
        v.addWidget(lbl)

        edit = QTextEdit()
        edit.setText(initial)
        v.addWidget(edit)

        btn_row = QHBoxLayout()
        btn_row.addStretch(1)

        ok_btn = AccentButton("OK")
        import_btn = GhostButton("Import from file")
        cancel_btn = GhostButton("Cancel")

        btn_row.addWidget(ok_btn)
        btn_row.addWidget(import_btn)   # between OK and Cancel
        btn_row.addWidget(cancel_btn)
        v.addLayout(btn_row)

        result = {"accepted": False}

        def on_ok():
            result["accepted"] = True
            dlg.accept()

        def on_cancel():
            dlg.reject()

        def on_import():
            path, _ = QFileDialog.getOpenFileName(
                dlg,
                "Select file containing hash",
                "",
                "Text files (*.txt);;All files (*.*)",
            )
            if not path:
                return
            try:
                with open(path, "rb") as f:
                    content_bytes = f.read()

                # Convert to base64 string for preview
                preview = base64.b64encode(content_bytes).decode("ascii")
                edit.setText(preview)
            except Exception as e:
                print("[CacheLoaderWidget] Failed to import hash from file:", e)

        ok_btn.clicked.connect(on_ok)
        cancel_btn.clicked.connect(on_cancel)
        import_btn.clicked.connect(on_import)

        if dlg.exec() == QDialog.Accepted and result["accepted"]:
            return edit.toPlainText().strip(), True
        return "", False

    def delete_db(self):
        base = Path(os.getenv("LOCALAPPDATA") or "") / "Roblox"
        candidates = []
        for root, _, files in os.walk(base):
            for f in files:
                if f.lower().endswith((".db", ".sqlite")):
                    candidates.append(str(Path(root) / f))
        if not candidates:
            QMessageBox.information(
                self, "No DBs", "No .db/.sqlite files found under LocalAppData\\Roblox")
            return
        if QMessageBox.question(self, "Delete", f"Delete {len(candidates)} database file(s)?") != QMessageBox.Yes:
            return
        deleted = 0
        for p in candidates:
            try:
                os.remove(p)
                deleted += 1
            except Exception as e:
                print("Failed:", p, e)
        QMessageBox.information(self, "Done", f"Deleted {deleted} file(s).")

    def delete_cache(self):
        print("Delete cache clicked")

    def _clear_ui_rows(self):
        for entry in self.cache_entries[:]:
            cache = getattr(entry, "cache_data", None)
            if isinstance(cache, dict):
                cache.pop("widget", None)

            entry.setParent(None)
            entry.deleteLater()
        self.cache_entries.clear()

    def remove_selected(self):
        global CACHES_BY_SOURCE
        src = self.current_source
        original = CACHES_BY_SOURCE.get(src, [])
        remaining = []
        for cache in original:
            w = cache.get("widget")
            if w is not None and getattr(w, "checkbox", None) is not None:
                if w.checkbox.isChecked():
                    # drop this one
                    continue
            remaining.append(cache)
        CACHES_BY_SOURCE[src] = remaining
        self.refresh_caches()
        self._save_caches()

    def remove_all(self):
        global CACHES_BY_SOURCE
        src = self.current_source
        CACHES_BY_SOURCE[src] = []
        self._clear_ui_rows()
        self._save_caches()

    def _sync_enabled_states(self):
        """Update the cache dicts with the current checkbox states before refresh."""
        for widget in self.cache_entries:
            cache = widget.cache_data
            cache["enabled"] = widget.checkbox.isChecked()

    def refresh_caches(self):
        global CACHES_BY_SOURCE
        print("Refresh caches clicked")

        self._sync_enabled_states()
        self._clear_ui_rows()
        self.cache_entries.clear()

        q_avail = (self.search_input.text() or "").strip().lower()
        q_loaded = (self.search_loaded_input.text() or "").strip().lower()

        src = self.current_source
        for cache in CACHES_BY_SOURCE.get(src, []):
            enabled = bool(cache.get("enabled", True))
            hay = (cache.get("name", "") or "").lower()

            if q_avail and enabled:
                continue
            if q_avail and (q_avail not in hay):
                continue

            if q_loaded and (not enabled):
                continue
            if q_loaded and (q_loaded not in hay):
                continue

            entry = self._create_cache_entry(cache)
            self.cache_entries.append(entry)
            self.cache_layout.addWidget(entry)

        # Reset selection highlight
        self.selected_index = -1
        for entry in self.cache_entries:
            header = getattr(entry, "header_widget", None)
            if header is not None:
                header.setProperty("selected", False)
                header.style().unpolish(header)
                header.style().polish(header)

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

    def fetch_new_assets(self):
        """
        Fetch binary content for all caches with 'id' and no 'binary' yet.
        Stores base64-encoded binary in the cache under 'binary'.
        """
        global CACHES_BY_SOURCE
        src = self.current_source
        caches = CACHES_BY_SOURCE.get(src, [])

        # Collect IDs that need fetching
        to_fetch = []
        id_to_cache = {}
        for cache in caches:
            asset_id = cache.get("use_hash") if cache.get(
                "hash_kind") == "id" else None
            if asset_id and "binary" not in cache:
                to_fetch.append(int(asset_id))
                id_to_cache[int(asset_id)] = cache

        if not to_fetch:
            return  # nothing to fetch

        # Prepare batch POST
        batch_url = "https://assetdelivery.roblox.com/v1/assets/batch"
        body = [{"assetId": str(aid), "requestId": str(i)}
                for i, aid in enumerate(to_fetch)]
        headers = {"Content-Type": "application/json",
                   "User-Agent": "Roblox/WinInet"}

        cookie = self.get_roblosecurity()
        cookies = {".ROBLOSECURITY": cookie} if cookie else None

        try:
            resp = requests.post(batch_url, json=body,
                                 headers=headers, cookies=cookies)
            resp.raise_for_status()
            batch_data = resp.json()
        except Exception as e:
            print("Batch request failed:", e)
            return

        for item in batch_data:
            request_id = int(item["requestId"])
            asset_id = to_fetch[request_id]
            cache = id_to_cache.get(asset_id)
            location = item.get("location")

            if cache and location:
                try:
                    asset_resp = requests.get(location, cookies=cookies)

                    if asset_resp.status_code == 200:
                        cache["binary"] = base64.b64encode(
                            asset_resp.content).decode("ascii")
                    else:
                        cache["binary"] = None

                except Exception as e:
                    print(f"Failed to fetch asset {asset_id}:", e)
                    cache["binary"] = None

        self._save_caches()

# Collections Widget


class CollectionsWidget(QWidget):
    def __init__(self, get_caches_callback, apply_caches_callback):
        super().__init__()
        # callbacks from CacheLoaderWidget
        self.get_caches = get_caches_callback
        self.apply_caches = apply_caches_callback

        self.collection_entries = []   # list of row widgets
        # [{ "name": str, "items": [ {name,hash}, ... ] }]
        self.collections = []
        self.selected_index = -1       # which row is selected

        self.collections_file = self._ensure_collections_file()
        self._load_collections()
        self._build_ui()

    # disk helpers
    def _ensure_collections_file(self) -> str:
        local_appdata = os.getenv("LOCALAPPDATA") or ""
        base_dir = os.path.join(local_appdata, "SubplaceJoiner")
        os.makedirs(base_dir, exist_ok=True)

        file_path = os.path.join(base_dir, "collections.json")
        if not os.path.exists(file_path):
            with open(file_path, "w", encoding="utf-8") as f:
                json.dump([], f)
        return file_path

    def _load_collections(self):
        try:
            with open(self.collections_file, "r", encoding="utf-8") as f:
                self.collections = json.load(f)
            if not isinstance(self.collections, list):
                self.collections = []
        except Exception:
            self.collections = []

    def _save_collections(self):
        try:
            with open(self.collections_file, "w", encoding="utf-8") as f:
                json.dump(self.collections, f, indent=4)
        except Exception as e:
            print("Failed to save collections:", e)

    # UI
    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 15, 0, 0)
        layout.setSpacing(15)

        collections_card = Card("Collections")

        # Scroll area for rows
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setFrameShape(QFrame.NoFrame)
        self.scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        self.collections_container = QWidget()
        self.collections_layout = QVBoxLayout(self.collections_container)
        self.collections_layout.setContentsMargins(5, 5, 5, 5)
        self.collections_layout.setSpacing(8)

        self.scroll_area.setWidget(self.collections_container)
        collections_card.body().addWidget(self.scroll_area, 1)
        layout.addWidget(collections_card, 1)

        # Bottom buttons
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(12)

        self.apply_collection_btn = AccentButton("Apply Collection")
        self.create_collection_btn = GhostButton("Create Collection")
        self.delete_collection_btn = GhostButton("Delete Collection")
        self.refresh_collections_btn = GhostButton("Refresh")

        btn_layout.addWidget(self.apply_collection_btn)
        btn_layout.addWidget(self.create_collection_btn)
        btn_layout.addWidget(self.delete_collection_btn)
        btn_layout.addWidget(self.refresh_collections_btn)
        btn_layout.addStretch()
        layout.addLayout(btn_layout)

        # Connect buttons
        self.apply_collection_btn.clicked.connect(self.apply_collection)
        self.create_collection_btn.clicked.connect(self.create_collection)
        self.delete_collection_btn.clicked.connect(self.delete_collection)
        self.refresh_collections_btn.clicked.connect(self.refresh_collections)

        # build rows from loaded data
        self._rebuild_collection_ui()

    # render / rows
    def _rebuild_collection_ui(self):
        # clear old rows
        for entry in self.collection_entries:
            entry.setParent(None)
            entry.deleteLater()
        self.collection_entries.clear()

        # recreate rows... nya~~ <--- wjhat??!? freaky coding *o*, bro what am i doing... ok free robux generator 5000
        for idx, col in enumerate(self.collections):
            entry = self._create_collection_entry(
                col.get("name", f"Collection {idx+1}"),
                col.get("items", []),
                idx,
            )

            self.collection_entries.append(entry)
            self.collections_layout.addWidget(entry)

            # only event filters, no mousePress monkeypatching
            entry.installEventFilter(self)
            entry.name_input.installEventFilter(self)

        self._update_selection_styles()

    def eventFilter(self, obj, event):
        # Only care about mouse presses
        if event.type() == QEvent.MouseButtonPress:
            # Click directly on the row widget
            if obj in self.collection_entries:
                index = self.collection_entries.index(obj)
                self._on_entry_clicked(index)
                return False  # let normal handling continue

            # Click on the name input inside a row
            for i, w in enumerate(self.collection_entries):
                if getattr(w, "name_input", None) is obj:
                    self._on_entry_clicked(i)
                    return False

        # Fallback to normal behavior
        return super().eventFilter(obj, event)

    def _create_collection_entry(self, name, items, index):
        entry_widget = QWidget()
        entry_layout = QVBoxLayout(entry_widget)
        entry_layout.setContentsMargins(8, 4, 8, 4)
        entry_layout.setSpacing(4)

        # header widget
        header_widget = QWidget()
        header_widget.setObjectName("CollectionHeader")
        header_widget.setAttribute(Qt.WA_StyledBackground, True)

        header_layout = QHBoxLayout(header_widget)
        header_layout.setContentsMargins(0, 0, 0, 0)
        header_layout.setSpacing(8)

        toggle_btn = QPushButton("▸")
        toggle_btn.setFixedSize(24, 24)
        toggle_btn.setStyleSheet("""
            QPushButton {
                background: transparent;
                border: none;
                color: rgba(255,255,255,180);
                font-size: 14px;
            }
            QPushButton:hover { color: white; }
        """)

        name_input = Search("")
        name_input.setText(name)
        name_input.setMinimumWidth(200)
        name_input.setReadOnly(True)

        header_layout.addWidget(toggle_btn)
        header_layout.addWidget(name_input, 1)
        header_layout.addStretch()

        delete_btn = QPushButton("×")
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
            lambda _=False, i=index: self._delete_collection_index(i)
        )
        header_layout.addWidget(delete_btn)

        # add header widget to the row layout
        entry_layout.addWidget(header_widget)

        # Details
        details_widget = QWidget()
        details_layout = QVBoxLayout(details_widget)
        details_layout.setContentsMargins(32, 4, 4, 4)
        details_layout.setSpacing(2)

        if items:
            for item in items:
                if isinstance(item, dict):
                    label_text = f"- {item.get('name', '')} = {item.get('hash', '')}"
                else:
                    label_text = f"- {item}"
                lbl = QLabel(label_text)
                lbl.setObjectName("Caption")
                details_layout.addWidget(lbl)
        else:
            placeholder = QLabel("Empty collection")
            placeholder.setObjectName("Caption")
            details_layout.addWidget(placeholder)

        details_widget.setVisible(False)
        entry_layout.addWidget(details_widget)

        # stash refs
        entry_widget.toggle_btn = toggle_btn
        entry_widget.details_widget = details_widget
        entry_widget.name_input = name_input
        entry_widget.header_widget = header_widget

        toggle_btn.clicked.connect(
            lambda _=False, w=entry_widget: self._toggle_collection_details(w)
        )

        return entry_widget

    def _toggle_collection_details(self, entry_widget):
        visible = entry_widget.details_widget.isVisible()
        entry_widget.details_widget.setVisible(not visible)
        entry_widget.toggle_btn.setText("▾" if not visible else "▸")

    def _on_entry_clicked(self, index: int):
        """Select a collection row (single-select)."""
        if index < 0 or index >= len(self.collection_entries):
            return
        self.selected_index = index
        self._update_selection_styles()

    def _update_selection_styles(self):
        selected_lineedit = """
            QLineEdit {
                border: 1px solid #3B82F6;
                border-radius: 10px;
                background-color: rgba(59, 130, 246, 40);
            }
        """

        unselected_lineedit = """
            QLineEdit {
                border: 1px solid rgba(255,255,255,26);
                border-radius: 10px;
                background-color: transparent;
            }
        """

        for i, w in enumerate(self.collection_entries):
            header = getattr(w, "header_widget", None)
            if i == self.selected_index:
                if header is not None:
                    header.setStyleSheet("""
                        QWidget#CollectionHeader {
                            background-color: rgba(59, 130, 246, 35);
                            border-radius: 8px;
                        }
                    """)
                w.name_input.setStyleSheet(selected_lineedit)
            else:
                if header is not None:
                    header.setStyleSheet("""
                        QWidget#CollectionHeader {
                            background-color: transparent;
                            border-radius: 8px;
                        }
                    """)
                w.name_input.setStyleSheet(unselected_lineedit)

    def _delete_collection_index(self, index: int):
        if 0 <= index < len(self.collections):
            self.collections.pop(index)

            if self.selected_index == index:
                self.selected_index = -1
            elif self.selected_index > index:
                self.selected_index -= 1

            self._save_collections()
            self._rebuild_collection_ui()

    # button actions
    def apply_collection(self):
        """Send selected collection's caches back into CacheLoaderWidget."""
        if self.selected_index < 0 or self.selected_index >= len(self.collections):
            print("Apply Collection: no collection selected")
            return

        col = self.collections[self.selected_index]
        items = col.get("items", [])

        if not items:
            print("Apply Collection: selected collection is empty")
            return

        if self.apply_caches:
            self.apply_caches(items)
            print(f"Applied collection: {col.get('name', 'Unnamed')}")

    def create_collection(self):
        if not self.get_caches:
            print("No cache callback wired into CollectionsWidget")
            return

        caches = self.get_caches() or []
        if not caches:
            print("No caches selected / loaded to save into a collection.")
            return

        default_name = f"Collection {len(self.collections) + 1}"
        name, ok = QInputDialog.getText(
            self, "Create Collection", "Collection name:", text=default_name
        )
        if not ok:
            return
        name = (name or default_name).strip() or default_name

        self.collections.append({
            "name": name,
            "items": caches,   # list of {"name","hash"}
        })
        self._save_collections()
        self._rebuild_collection_ui()
        print(f"Created collection: {name}")

    def delete_collection(self):
        if not self.collections:
            return
        last_index = len(self.collections) - 1
        self.collections.pop()
        if self.selected_index >= last_index:
            self.selected_index = -1
        self._save_collections()
        self._rebuild_collection_ui()
        print("Delete collection clicked")

    def refresh_collections(self):
        self._load_collections()
        if self.selected_index >= len(self.collections):
            self.selected_index = -1
        self._rebuild_collection_ui()
        print("Collections reloaded from disk")

# Cache Finder Widget


def extract_asset_hash(url: str) -> str:
    """
    Extract the asset ID from a URL like:
    fts.rbxcdn.com/sc5/509f6133bf6be400729363b38fb7c148?encoding=gzip
    Returns '509f6133bf6be400729363b38fb7c148'
    """
    try:
        path = url.split("?")[0]  # remove query
        parts = path.split("/")    # split by slash
        return parts[-1]           # last part is ID
    except Exception:
        return url  # fallback to full URL if parsing fails


class AssetNameFetcher(QObject):
    finished = Signal(str, object)  # asset_id, name or None

    def __init__(self, asset_id: str, cookie: str, max_retries: int = 3, retry_delay: float = 1.0):
        """
        :param asset_id: Roblox asset ID to fetch
        :param cookie: .ROBLOSECURITY cookie string
        :param max_retries: number of retries on failure
        :param retry_delay: seconds to wait before retry
        """
        super().__init__()
        self.asset_id = asset_id
        self.cookie = cookie
        self.max_retries = max_retries
        self.retry_delay = retry_delay
        self._thread = threading.Thread(target=self.run)
        self._thread.daemon = True  # won't block app exit

    def start(self):
        self._thread.start()

    def run(self):
        attempt = 0
        name = None

        while attempt < self.max_retries:
            attempt += 1
            try:
                url = f"https://develop.roblox.com/v1/assets?assetIds={self.asset_id}"
                headers = {
                    "Cookie": f".ROBLOSECURITY={self.cookie}",
                    "User-Agent": "Roblox/WinInet"
                }
                resp = requests.get(url, headers=headers, timeout=5)
                resp.raise_for_status()
                data = resp.json().get("data", [])
                if data:
                    name = data[0].get("name")
                break  # success, exit loop
            except Exception as e:
                print(
                    f"[ASSET NAME] Attempt {attempt} failed for {self.asset_id}: {e}")
                if attempt < self.max_retries:
                    time.sleep(self.retry_delay)  # wait before retry
                else:
                    name = None

        self.finished.emit(self.asset_id, name)


class CacheFinderWidget(QWidget):
    def __init__(self):
        super().__init__()
        self._name_fetch_threads = {}  # asset_id -> QThread
        self._delayed_rows = {}  # key: request ID, value: row widget
        self._asset_name_cache = {}  # asset_id -> name or None
        self._selected_row = None
        self._selected_request_data = None  # stores dict of last selected request
        self.filter_mode = "All"
        self._build_ui()
        self.start_delayed_request_sync()

        self.setStyleSheet("""
            QWidget#resultRow {
                border: 1px solid transparent;
                border-radius: 6px;
            }
            QWidget#resultRow[selected="true"] {
                border: 2px solid #3b82f6;
            }
        """)

    # small helpers

    def _clear_results(self):
        while self.results_layout.count():
            item = self.results_layout.takeAt(0)
            w = item.widget()
            if w is not None:
                w.setParent(None)
                w.deleteLater()

    def _add_result_row(self, text: str):
        row = QWidget(self.results_host)
        row.setObjectName("resultRow")

        row.mousePressEvent = lambda e, r=row: self._select_row(r)

        row_layout = QHBoxLayout(row)
        row_layout.setContentsMargins(0, 0, 0, 0)
        row_layout.setSpacing(0)

        line = Search("")
        line.setReadOnly(True)
        line.setFocusPolicy(Qt.NoFocus)
        line.setAttribute(Qt.WA_TransparentForMouseEvents)

        line.setStyleSheet("""
            QLineEdit {
                border-radius: 10px;
                border: 1px solid rgba(255,255,255,26);
                background-color: transparent;
                padding: 9px 12px;
                selection-background-color: #2563EB;
                selection-color: white;
                min-height: 16px;
                max-height: 16px;
            }
        """)

        line.setText(" ".join(text.splitlines()))

        row_layout.addWidget(line)

        self.results_layout.insertWidget(
            self.results_layout.count() - 1, row
        )

        return row  # return the widget for tracking

    def add_delayed_request_row(self, request_id: str, url: str, asset_id: str):
        if request_id in self._delayed_rows:
            return  # already exists

        asset_hash = extract_asset_hash(url)

        display_right = asset_hash  # default: show hash
        text = f"{asset_id} → {display_right}"

        row = self._add_result_row(text)

        # Persist data
        row.request_id = request_id       # store the request ID
        row.asset_id = asset_id
        row.asset_hash = asset_hash
        row.asset_name = None  # not fetched yet
        row.full_url = url

        # Clicking the row updates Current API and Hash boxes
        row.mousePressEvent = lambda e, r=row: self._select_row_and_set_current(
            r)

        self._delayed_rows[request_id] = row

        if self.show_names_checkbox.isChecked():
            self._ensure_asset_name_async(asset_id)
            line_edit = row.findChild(QLineEdit)
            if line_edit:
                line_edit.setText(f"{asset_id} → Loading…")

    def _select_row_and_set_current(self, row):
        self._select_row(row)

        # Update the top status boxes
        self.api_status.setText(row.full_url)
        self.api_status.setCursorPosition(0)
        self.id_status.setText(row.asset_id)  # short asset ID

    def remove_delayed_request_row(self, request_id: str):
        row = self._delayed_rows.pop(request_id, None)
        if row:
            # Clear selection if this row was selected
            if getattr(self, "_selected_row", None) is row:
                self._selected_row = None

            self.results_layout.removeWidget(row)
            row.setParent(None)
            row.deleteLater()

    def start_delayed_request_sync(self):
        self._sync_timer = QTimer(self)
        self._sync_timer.timeout.connect(self.sync_delayed_requests)
        self._sync_timer.start(500)  # check every 0.5 seconds

    def sync_delayed_requests(self):
        global DELAY_REQUESTS_LIST

        # Add new delayed requests
        for key, flow in list(DELAY_REQUESTS_LIST.items()):
            if key not in self._delayed_rows:
                url = getattr(flow.request, "pretty_url", str(flow))
                asset_id = None
                req_base = url.split("?")[0]

                # Search CACHELOGS for a matching location
                for id_, info in CACHELOGS.items():
                    if not isinstance(info, dict):
                        continue
                    location = info.get("location")
                    if not location:
                        continue
                    cached_base = location.split("?")[0]
                    if cached_base == req_base:
                        asset_id = id_  # use the index/key from CACHELOGS
                        break

                asset_type_name = str(
                    asset_id) if asset_id is not None else "Unknown"
                self.add_delayed_request_row(key, url, asset_type_name)

        # Remove rows that no longer exist in the global list
        for key in list(self._delayed_rows.keys()):
            if key not in DELAY_REQUESTS_LIST:
                self.remove_delayed_request_row(key)

    def _select_row(self, row: QWidget):
        # Clear previous selection
        if getattr(self, "_selected_row", None):
            self._selected_row.setProperty("selected", False)
            self._selected_row.style().unpolish(self._selected_row)
            self._selected_row.style().polish(self._selected_row)

        # Mark new selection
        self._selected_row = row
        row.setProperty("selected", True)
        row.style().unpolish(row)
        row.style().polish(row)

        # Store the request data for future reference
        self._selected_request_data = {
            "request_id": getattr(row, "request_id", None),
            "asset_id": getattr(row, "asset_id", None),
            "asset_hash": getattr(row, "asset_hash", None),
            "asset_name": getattr(row, "asset_name", None),
            "full_url": getattr(row, "full_url", None),
        }

        # Update UI top boxes
        self.api_status.setText(self._selected_request_data["full_url"] or "")
        self.api_status.setCursorPosition(0)
        self.id_status.setText(self._selected_request_data["asset_id"] or "")

    def _set_finder_message(self, text: str):
        """Convenience to show a single message in the results list."""
        self._clear_results()
        self._add_result_row(text)

    def _append_log_entry(self, text: str):
        """Append a new line to the cache finder log without clearing it."""
        self._add_result_row(text)

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

    def _fetch_asset_name(self, asset_id: str) -> str | None:
        if not asset_id or asset_id in self._asset_name_cache:
            return self._asset_name_cache.get(asset_id)

        cookie = self.get_roblosecurity()
        if not cookie:
            self._asset_name_cache[asset_id] = None
            return None

        try:
            url = f"https://develop.roblox.com/v1/assets?assetIds={asset_id}"
            headers = {
                "Cookie": f".ROBLOSECURITY={cookie}",
                "User-Agent": "Roblox/WinInet"
            }

            resp = requests.get(url, headers=headers, timeout=5)
            resp.raise_for_status()

            data = resp.json().get("data", [])
            if not data:
                self._asset_name_cache[asset_id] = None
                return None

            name = data[0].get("name")
            self._asset_name_cache[asset_id] = name
            return name

        except Exception as e:
            print(f"[ASSET NAME] Failed for {asset_id}: {e}")
            self._asset_name_cache[asset_id] = None
            return None

    def _update_log_hash_visibility(self, checked: bool):
        for row in self._delayed_rows.values():
            asset_id = row.asset_id

            if checked:
                # Trigger async fetch if missing
                if row.asset_name is None:
                    self._ensure_asset_name_async(asset_id)
                    display = "Loading…"
                else:
                    display = row.asset_name
            else:
                display = row.asset_hash

            line_edit = row.findChild(QLineEdit)
            if line_edit:
                line_edit.setText(f"{asset_id} → {display}")

    def _ensure_asset_name_async(self, asset_id: str):
        if asset_id in self._asset_name_cache:
            return

        cookie = self.get_roblosecurity()
        if not cookie:
            self._asset_name_cache[asset_id] = None
            return

        fetcher = AssetNameFetcher(asset_id, cookie)
        fetcher.finished.connect(self._on_asset_name_fetched)
        fetcher.start()

    def _on_asset_name_fetched(self, asset_id: str, name: str | None):
        print(f"[ASSET NAME] Fetched name for {asset_id}: {name}")
        self._asset_name_cache[asset_id] = name or "Unknown asset"
        self._name_fetch_threads.pop(asset_id, None)  # remove reference

        if not self.show_names_checkbox.isChecked():
            return

        for row in self._delayed_rows.values():
            if row.asset_id == asset_id:
                row.asset_name = name or "Unknown asset"
                line_edit = row.findChild(QLineEdit)
                if line_edit:
                    line_edit.setText(f"{asset_id} → {row.asset_name}")

    # UI build

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 15, 0, 0)
        layout.setSpacing(15)

        # Top "Cache Finder" status card
        status_card = Card("Cache Finder")
        status_layout = QVBoxLayout()
        status_layout.setSpacing(10)

        # Current API and hash info
        info_layout = QGridLayout()
        info_layout.setSpacing(8)

        info_layout.addWidget(QLabel("Current API in queue:"), 0, 0)
        self.api_status = Search("")
        self.api_status.setReadOnly(True)
        self.api_status.setText("No API in queue")
        info_layout.addWidget(self.api_status, 0, 1)

        info_layout.addWidget(QLabel("Current id:"), 1, 0)
        self.id_status = Search("")
        self.id_status.setReadOnly(True)
        self.id_status.setText("No id")
        info_layout.addWidget(self.id_status, 1, 1)

        status_layout.addLayout(info_layout)

        # Auto-progress + filter row
        progress_layout = QHBoxLayout()
        progress_layout.setSpacing(8)

        self.auto_progress_btn = GhostButton("Stop Auto-progress")
        self.auto_progress_btn.setCheckable(True)
        progress_layout.addWidget(self.auto_progress_btn)

        progress_layout.addWidget(QLabel("Filter:"))
        self.filter_combo = QComboBox()
        self.filter_combo.addItem("All")
        self.filter_combo.addItems(asset_types.values())

        self.filter_combo.setCurrentIndex(0)
        self.filter_combo.setMinimumWidth(130)

        def on_filter_changed(index):
            global CURRENT_FILTER
            CURRENT_FILTER = self.filter_combo.currentText()
            print(f"[FILTER] CURRENT_FILTER updated: {CURRENT_FILTER}")

        self.filter_combo.currentIndexChanged.connect(on_filter_changed)

        progress_layout.addWidget(self.filter_combo)

        self.show_names_checkbox = QCheckBox("Show names")
        self.show_names_checkbox.setChecked(False)
        self.show_names_checkbox.setStyleSheet("""
            QCheckBox {
                background: transparent;
            }

            QCheckBox::indicator {
                width: 16px;
                height: 16px;
                border-radius: 3px;
                background: rgba(0,0,0,40);
                border: 1px solid rgba(255,255,255,120);
            }

            QCheckBox::indicator:checked {
                background: #3B82F6;
                border: 1px solid #3B82F6;
                image: url(:/qt-project.org/styles/commonstyle/images/checkmark.png);
            }

            QCheckBox::indicator:unchecked {
                image: none;
            }
        """)
        self.show_names_checkbox.toggled.connect(
            self._update_log_hash_visibility)
        progress_layout.addWidget(self.show_names_checkbox)

        progress_layout.addStretch()
        status_layout.addLayout(progress_layout)

        status_card.body().addLayout(status_layout)
        layout.addWidget(status_card)

        # "Cache Results" log card
        finder_card = Card("Cache Results")

        # scroll area so the log doesn't grow forever
        self.results_scroll = QScrollArea()
        self.results_scroll.setWidgetResizable(True)
        self.results_scroll.setFrameShape(QFrame.NoFrame)

        # host widget inside the scroll area
        self.results_host = QWidget()
        self.results_layout = QVBoxLayout(self.results_host)
        self.results_layout.setContentsMargins(8, 8, 8, 8)
        self.results_layout.setSpacing(10)

        # keep rows packed at the top
        self.results_layout.addStretch()

        self.results_scroll.setWidget(self.results_host)
        finder_card.body().addWidget(self.results_scroll, 1)
        layout.addWidget(finder_card, 1)
        # self._add_result_row("Cache Finder initialized.")
        # self._add_result_row("Cached")
        # self._add_result_row("Cache sss")

        # Bottom buttons
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(12)

        self.delete_db_btn = GhostButton("Delete DB")
        self.progress_api_btn = AccentButton("Progress 1 API request")
        self.progress_all_btn = GhostButton("Progress all")
        self.download_hash_btn = GhostButton("Download hash")
        self.copy_hash_contents_btn = GhostButton("Copy hash contents")

        self.download_hash_btn.clicked.connect(self.download_hash)
        self.copy_hash_contents_btn.clicked.connect(self.copy_hash_contents)

        btn_layout.addWidget(self.delete_db_btn)
        btn_layout.addWidget(self.progress_api_btn)
        btn_layout.addWidget(self.progress_all_btn)
        btn_layout.addWidget(self.download_hash_btn)
        btn_layout.addWidget(self.copy_hash_contents_btn)
        btn_layout.addStretch()

        layout.addLayout(btn_layout)

        # Connect buttons / filter
        self.delete_db_btn.clicked.connect(self.delete_db)
        self.progress_api_btn.clicked.connect(self.progress_one_api)
        self.progress_all_btn.clicked.connect(self.progress_all)
        self.auto_progress_btn.clicked.connect(self.toggle_auto_progress)
        self.filter_combo.currentIndexChanged.connect(self._on_filter_changed)
        self.download_hash_btn.clicked.connect(lambda: None)
        self.copy_hash_contents_btn.clicked.connect(lambda: None)

    # button handlers (updated to use _set_finder_message)

    def _on_filter_changed(self, index: int):
        """Handle changes in the filter dropdown."""
        mode = self.filter_combo.currentText()
        print(f"Cache Finder filter changed to: {mode}")
        # blockceeeeeeeee
        # e.g. re-render self.results_layout based on `mode`

    def delete_db(self):
        base = Path(os.getenv("LOCALAPPDATA") or "") / "Roblox"
        candidates = []
        for root, _, files in os.walk(base):
            for f in files:
                if f.lower().endswith((".db", ".sqlite")):
                    candidates.append(str(Path(root) / f))
        if not candidates:
            QMessageBox.information(
                self, "No DBs", "No .db/.sqlite files found under LocalAppData\\Roblox")
            return
        if QMessageBox.question(self, "Delete", f"Delete {len(candidates)} database file(s)?") != QMessageBox.Yes:
            return
        deleted = 0
        for p in candidates:
            try:
                os.remove(p)
                deleted += 1
            except Exception as e:
                print("Failed:", p, e)
        QMessageBox.information(self, "Done", f"Deleted {deleted} file(s).")

    def progress_one_api(self):
        global DELAY_REQUESTS_LIST

        if not DELAY_REQUESTS_LIST:
            print("[DELAY] No delayed requests to send")
            return

        # Determine which request to forward
        selected_key = None
        if getattr(self, "_selected_row", None):
            selected_row = self._selected_row
            for key, row in self._delayed_rows.items():
                if row is selected_row:
                    selected_key = key
                    break

        # If no selected row or key not found, pick the oldest request
        if not selected_key:
            selected_key = next(iter(DELAY_REQUESTS_LIST))

        # Before removing the row, store its data as the last selected request
        row = self._delayed_rows.get(selected_key)
        if row:
            self._selected_request_data = {
                "request_id": getattr(row, "request_id", None),
                "asset_id": getattr(row, "asset_id", None),
                "asset_hash": getattr(row, "asset_hash", None),
                "asset_name": getattr(row, "asset_name", None),
                "full_url": getattr(row, "full_url", None),
            }

            # Update the top UI boxes BEFORE removal
            self.api_status.setText(
                self._selected_request_data["full_url"] or "")
            self.api_status.setCursorPosition(0)
            self.id_status.setText(
                self._selected_request_data["asset_id"] or "")

        # Send the request
        send_delayed_request(selected_key)

        # Remove its row from the UI
        self.remove_delayed_request_row(selected_key)

    def progress_all(self):
        if not DELAY_REQUESTS_LIST:
            print("[DELAY] No delayed requests to send")
            return

        send_all_delayed_requests()

        # Remove all rows from UI
        for key in list(self._delayed_rows.keys()):
            self.remove_delayed_request_row(key)

    def toggle_auto_progress(self, checked):
        if checked:
            self.auto_progress_btn.setText("Auto-progress queue")
            set_delay_requests(True)
            print("Auto-progress disabled")
        else:
            self.auto_progress_btn.setText("Stop auto-progress")
            set_delay_requests(False)
            print("Auto-progress enabled")

    # --- Download hash button ---

    def download_hash(self):
        if not self._selected_request_data:
            print("[DOWNLOAD HASH] No request selected")
            return

        url = self._selected_request_data.get("full_url")
        asset_hash = self._selected_request_data.get("asset_hash")
        if not url or not asset_hash:
            print("[DOWNLOAD HASH] Missing URL or hash")
            return

        try:
            response = requests.get(url, timeout=5)  # just a copy

            # Downloads folder path
            downloads_dir = Path.home() / "Downloads"
            downloads_dir.mkdir(exist_ok=True)  # ensure it exists
            file_path = downloads_dir / asset_hash  # file name is just the hash

            with open(file_path, "wb") as f:
                f.write(response.content)

            print(f"[DOWNLOAD HASH] Response saved to {file_path}")
        except Exception as e:
            print(f"[DOWNLOAD HASH] Failed: {e}")

    # --- Copy hash contents button ---

    def copy_hash_contents(self):
        if not self._selected_request_data:
            print("[COPY CONTENT] No request selected")
            return

        url = self._selected_request_data.get("full_url")
        if not url:
            print("[COPY CONTENT] No URL available")
            return

        try:
            response = requests.get(url, timeout=5)
            QApplication.clipboard().setText(response.text)
            print(f"[COPY CONTENT] Response copied to clipboard")
        except Exception as e:
            print(f"[COPY CONTENT] Failed: {e}")


# Main Application Entry Point


async def pr():
    while True:
        # for src, lst in CACHES_BY_SOURCE.items():
        # for cache in lst:
        # print({
        #    k: v for k, v in cache.items()
        #    if k != "widget"
        # })
        await asyncio.sleep(1)


def start_asyncio_loop():
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.create_task(pr())
    loop.run_forever()


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
    threading.Thread(target=start_asyncio_loop, daemon=True).start()
    # Run the application
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
