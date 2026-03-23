"""Asset preview rendering for the cache module."""

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
from PySide6.QtGui import QStandardItemModel, QStandardItem, QPixmap, QImage, QPainter, QGuiApplication, QPalette
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
from shared.utils import strip_cache_header, get_roblosecurity, isnumeric, batch_location
from shared.models import SortProxy
from shared.delegates import HoverDelegate
from shared.ui_loader import load_ui
from shared.audio_player import AudioPlayer
from shared.menu_utils import StayOpenMenu
from shared.threading_utils import _MainThreadInvoker


def _extract_cam_state(state: dict):
    """Return camera state from whichever GL widget is currently live, or the last saved one."""
    for key, attr in (("anim_viewer", "_gl"), ("mesh_gl", None)):
        widget = state.get(key)
        if widget is None:
            continue
        gl = getattr(widget, attr, widget) if attr else widget
        try:
            cam = gl.get_camera_state()
            state["_last_camera"] = cam
            return cam
        except Exception:
            pass
    return state.get("_last_camera")


def _load_preview_prefs() -> dict:
    try:
        _p = os.path.join(os.environ.get("LOCALAPPDATA", os.path.expanduser("~")),
                          "SubplaceJoiner", "preview_prefs.json")
        with open(_p, "r", encoding="utf-8") as _f:
            return json.load(_f)
    except Exception:
        return {}


def _save_preview_prefs(prefs: dict) -> None:
    try:
        _p = os.path.join(os.environ.get("LOCALAPPDATA", os.path.expanduser("~")),
                          "SubplaceJoiner", "preview_prefs.json")
        os.makedirs(os.path.dirname(_p), exist_ok=True)
        with open(_p, "w", encoding="utf-8") as _f:
            json.dump(prefs, _f)
    except Exception:
        pass


def _clear_layout(self, layout):
    """Remove and delete all widgets and nested layouts from a Qt layout."""
    if layout is None:
        return
    while layout.count():
        item = layout.takeAt(0)
        if item is None:
            continue
        w = item.widget()
        if w is not None:
            try:
                w.setParent(None)
            except Exception:
                pass
            try:
                w.deleteLater()
            except Exception:
                pass
            continue
        child_layout = item.layout()
        if child_layout is not None:
            _clear_layout(self, child_layout)
            try:
                child_layout.setParent(None)
            except Exception:
                pass


def display_preview_enhanced(
    self,
    cache_data,
    asset_type_id,
    asset_id,
    asset_name,
    preview_frame
):
    self._frame_preview_gen = getattr(self, "_frame_preview_gen", {})
    _fpg = self._frame_preview_gen.get(preview_frame, 0) + 1
    self._frame_preview_gen[preview_frame] = _fpg
    gen = _fpg

    if not cache_data:
        return
    from shared.utils import strip_cache_header
    cache_data = strip_cache_header(cache_data)
    if not cache_data:
        return
    cache_data = _decompress_asset(cache_data)
    ext = self._get_extension_for_type(asset_type_id, cache_data)
    file_type = self._identify_file_type(cache_data)

    kind = "misc"
    if asset_type_id == 24:
        kind = "animation"
    elif file_type in ["PNG", "GIF", "JPEG", "JFIF"]:
        kind = "image"
    elif file_type in ["OGG", "MP3"]:
        kind = "audio"
    elif file_type.startswith("Mesh"):
        kind = "mesh"
    elif file_type == "TEXTURE":
        kind = "texture"
    elif file_type == "Translation (JSON)":
        kind = "json"
    elif file_type in ["XML", "EXTM3U"]:
        kind = "text"

    # Extract camera state from any live GL widget BEFORE close_preview wipes
    # _preview_state entirely (it calls self._preview_state.pop(preview_frame)).
    _prev_cam = _extract_cam_state(
        getattr(self, "_preview_state", {}).get(preview_frame, {}))

    self.close_preview(preview_frame, hide=False)
    state = {}
    self._preview_state[preview_frame] = state
    if _prev_cam is not None:
        state["_last_camera"] = _prev_cam
    state["kind"] = kind

    out_path = self._make_sj_temp_file(kind, asset_id, ext, asset_name)
    out_path.write_bytes(cache_data)
    temp_path = str(out_path)

    old_token = self._preview_token.get(preview_frame)

    new_token = self._start_new_preview_session(preview_frame)
    self._track_temp(preview_frame, temp_path, token=new_token)

    if not preview_frame.layout():
        preview_frame.setLayout(QVBoxLayout())

    if asset_type_id == 39:
        file_type = "SolidModel"
    elif asset_type_id == 24:
        file_type = "RBXM Animation"

    def run_thread(fn):
        threading.Thread(target=fn, daemon=True).start()

    if file_type in ["PNG", "GIF", "JPEG", "JFIF"]:
        run_thread(lambda: self._display_image_preview(
            temp_path, preview_frame, gen
        ))

    elif file_type in ["OGG", "MP3"]:
        run_thread(lambda: self._display_audio_preview(
            temp_path, preview_frame, gen
        ))

    elif file_type.startswith("Mesh"):
        run_thread(lambda: self._display_mesh_preview(
            cache_data, temp_path, asset_id, asset_name, preview_frame, gen
        ))

    elif file_type == "Translation (JSON)":
        run_thread(lambda: self._display_localization_preview(
            cache_data, preview_frame, gen
        ))

    elif file_type in ["JSON", "TTF (JSON)"]:
        run_thread(lambda: self._display_json_preview(
            cache_data, preview_frame, gen
        ))

    elif file_type in ["XML", "EXTM3U"]:
        run_thread(lambda: self._display_text_preview(
            cache_data, preview_frame, gen
        ))

    elif file_type == "SolidModel":
        run_thread(lambda: self._display_solidmodel_preview(
            cache_data, asset_id, asset_name, preview_frame, gen
        ))

    elif file_type == "RBXM Animation":
        run_thread(lambda tok=new_token: self._display_animation_preview(
            cache_data, temp_path, asset_id, asset_name, preview_frame, gen, tok
        ))

    elif file_type == "TEXTURE":
        _loading_lbl = QLabel("Loading textures…")
        _loading_lbl.setAlignment(Qt.AlignCenter)
        preview_frame.layout().addWidget(_loading_lbl)
        run_thread(lambda: self._display_texture_preview(
            temp_path, asset_id, asset_name, preview_frame, gen
        ))

    else:
        self._display_file_info(temp_path, file_type, preview_frame)

    preview_frame.show()
    preview_frame.update()

    QTimer.singleShot(
        0, lambda: self._on_column_resized(-1, 0, 0, self.table_view)
    )


def read_texturepack_xml(self, xml_text: str):
    wrapped = f"<root>{xml_text}</root>"
    root = ET.fromstring(wrapped)

    wanted = {
        "texturepack_version",
        "alphamode",
        "tiling",
        "color",
        "normal",
        "metalness",
        "roughness",
    }

    packs = []
    for roblox_node in root.findall("roblox"):
        pack = {}
        for child in roblox_node:
            tag = child.tag.strip()
            if tag in wanted and child.text:
                try:
                    pack[tag] = int(child.text.strip())
                except ValueError:
                    pass
        packs.append(pack)

    return packs


def _decompress_asset(data: bytes) -> bytes:
    """Decompress gzip or zstd asset data if needed."""
    if not data:
        return data
    if data[:2] == b'\x1f\x8b':
        try:
            return gzip.decompress(data)
        except Exception:
            pass
    if data[:4] == b'\x28\xb5\x2f\xfd':
        try:
            import zstandard
            return zstandard.ZstdDecompressor().decompress(data, max_output_size=64 * 1024 * 1024)
        except Exception:
            pass
    return data


def _identify_file_type(self, data):
    if not data or len(data) < 12:
        return "Unknown"

    begin = data[:min(48, len(data))].decode('utf-8', errors='ignore')
    begin_long = data[:min(512, len(data))].decode('utf-8', errors='ignore')

    if "PNG\r\n" in begin or data[:8] == b'\x89PNG\r\n\x1a\n':
        return "PNG"
    elif begin.startswith("GIF8"):
        return "GIF"
    elif "JFIF" in begin or data[:2] == b'\xff\xd8':
        return "JPEG"
    elif "OggS" in begin:
        return "OGG"
    elif any(x in begin for x in ["TSSE", "Lavf", "ID3"]) or data[:3] == b'ID3':
        return "MP3"
    elif "<roblox!" in begin:
        return "RBXM Animation"
    elif 'assettype="animation"' in begin_long:
        return "RBXM Animation"
    elif "<roblox xml" in begin or begin.startswith("<?xml"):
        return "XML"
    elif begin.startswith("version"):
        header = begin.splitlines()[0].strip()
        short = header.replace("version ", "V").replace("version", "V")
        return f"Mesh ({short})"
    elif '{"locale":"' in begin:
        return "Translation (JSON)"
    elif '"name": "' in begin or begin.strip().startswith('{'):
        return "JSON"
    elif begin.startswith("#EXTM3U"):
        return "EXTM3U"
    elif begin.startswith("<roblox>"):
        info = self.read_texturepack_xml(data.decode('utf-8', errors='ignore'))
        if not info:
            return "Unknown"
        texture = info[0]

        if "texturepack_version" in texture and texture["texturepack_version"] in (1, 2):
            return "TEXTURE"
        else:
            return "Unknown"
    else:
        return "Unknown"


def _get_game_name_from_placeid(self, place_id: int) -> tuple[str | None, str, str]:
    try:
        r1 = self.net.get(
            f"https://apis.roblox.com/universes/v1/places/{place_id}/universe", timeout=10)
        r1.raise_for_status()
        universe_id = r1.json().get("universeId")
        if not universe_id:
            return None, "", ""

        r2 = self.net.get(
            f"https://games.roblox.com/v1/games?universeIds={universe_id}", timeout=10)
        r2.raise_for_status()
        data = r2.json().get("data", [])
        if not data:
            return None, "", ""

        entry = data[0]
        return entry.get("name"), entry.get("created", ""), entry.get("updated", "")
    except Exception as e:
        print(f"[GAME META] name fetch failed for {place_id}: {e}")
        return None, "", ""


def _fetch_place_icon_pixmap(self, place_id: int) -> QPixmap | None:
    try:
        meta = self.net.get(
            f"https://thumbnails.roblox.com/v1/places/gameicons?placeIds={place_id}&size=512x512&format=Png",
            timeout=10
        )
        meta.raise_for_status()
        img_url = (meta.json().get("data") or [{}])[0].get("imageUrl")
        if not img_url:
            return None

        img = self.net.get(img_url, timeout=10)
        img.raise_for_status()

        pix = QPixmap()
        if pix.loadFromData(img.content):
            return pix
        return None
    except Exception as e:
        print(f"[THUMB] failed for {place_id}: {e}")
        return None


def _get_extension_for_type(self, asset_type_id, data):
    ftype = self._identify_file_type(data)

    ext_map = {
        "PNG": ".png",
        "GIF": ".gif",
        "JPEG": ".jpg",
        "JFIF": ".jpg",
        "OGG": ".ogg",
        "MP3": ".mp3",
        "XML": ".xml",
        "JSON": ".json",
        "EXTM3U": ".m3u",
        "TEXTURE": ".xml",
    }

    if ftype.startswith("Mesh"):
        return ".mesh"

    return ext_map.get(ftype, ".bin")


def _display_image_preview(self, filepath, preview_frame, gen):
    layout = preview_frame.layout()

    # Load via QImage - safe to use from any thread (unlike QPixmap)
    image = QImage(filepath).scaled(
        400, 400, Qt.KeepAspectRatio, Qt.SmoothTransformation
    )

    if self._frame_preview_gen.get(preview_frame, 0) != gen:
        return

    def _set():
        # Guard: if a newer preview has started, discard this result.
        if self._frame_preview_gen.get(preview_frame, 0) != gen:
            return

        # Convert to QPixmap on the main thread (required by Qt)
        pixmap = QPixmap.fromImage(image)
        self._preview_state = getattr(self, "_preview_state", {})
        state = self._preview_state.setdefault(preview_frame, {})

        # close_preview (called e.g. from clear_all_rows) deletes widgets via
        # deleteLater but may not clear _preview_state, leaving stale C++
        # object references.  Drop any invalid widget before trying to reuse it.
        img_label = state.get("image_label")
        if img_label is not None and not isValid(img_label):
            state.pop("image_label", None)
            state.pop("image_info_label", None)
            img_label = None

        if img_label is None:
            img_label = QLabel()
            img_label.setAlignment(Qt.AlignCenter)
            img_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
            layout.addWidget(img_label, stretch=1)
            state["image_label"] = img_label

        img_label.setPixmap(pixmap)
        info_label = state.get("image_info_label")
        if info_label is None or not isValid(info_label):
            info_label = QLabel()
            layout.addWidget(info_label)
            state["image_info_label"] = info_label

        size = os.path.getsize(filepath)
        info_text = f"Size: {self._format_size(size)} | Dimensions: {pixmap.width()}x{pixmap.height()}"
        info_label.setText(info_text)
        old_buttons = state.get("image_buttons_frame")
        if old_buttons is not None:
            old_buttons.deleteLater()

        new_buttons = self._add_preview_buttons(filepath, preview_frame)
        state["image_buttons_frame"] = new_buttons

        preview_frame.show()
        preview_frame.update()

    self._on_main(_set)


def _display_audio_preview(self, filepath, preview_frame, gen):
    def _set():
        if self._frame_preview_gen.get(preview_frame, 0) != gen:
            return

        if preview_frame in self.audio_players:
            try:
                self.audio_players[preview_frame].stop()
            except Exception:
                pass
            try:
                if hasattr(pygame.mixer.music, "unload"):
                    pygame.mixer.music.unload()
            except Exception:
                pass
            try:
                del self.audio_players[preview_frame]
            except Exception:
                pass

        layout = preview_frame.layout()
        if layout:
            while layout.count():
                child = layout.takeAt(0)
                w = child.widget()
                if w:
                    w.deleteLater()

        player = AudioPlayer(self, filepath, preview_frame)
        self.audio_players[preview_frame] = player

        preview_frame.show()
        preview_frame.update()

    self._on_main(_set)


def _convert_srgb_to_linear(self, png_path):
    try:
        im = Image.open(png_path)
        has_alpha = im.mode == "RGBA"
        arr = np.asarray(im.convert("RGBA" if has_alpha else "RGB")).astype(np.float32)

        rgb = arr[..., :3] / 255.0
        # Vectorized sRGB -> linear conversion
        linear = np.where(
            rgb <= 0.0404482362771082,
            rgb / 12.92,
            ((rgb + 0.055) / 1.055) ** 2.4,
        )
        result = np.floor(linear / 2058.61501702 * 255).clip(0, 255).astype(np.uint8)

        if has_alpha:
            out = np.concatenate([result, arr[..., 3:4].astype(np.uint8)], axis=-1)
            newim = Image.fromarray(out, "RGBA")
        else:
            newim = Image.fromarray(result, "RGB")

        newim.save(png_path)
    except Exception as e:
        print(f"Failed to apply sRGB conversion: {e}")


def _display_mesh_preview(self, mesh_data, temp_path, asset_id, asset_name, preview_frame, gen):
    try:
        obj_path = self._convert_mesh_to_obj(
            mesh_data, asset_id, asset_name)

        if obj_path and os.path.exists(obj_path):
            if self._frame_preview_gen.get(preview_frame, 0) == gen:
                self._track_temp(preview_frame, obj_path)

                def _set():
                    self._display_3d_model(obj_path, preview_frame, gen)
                self._on_main(_set)
        else:
            if self._frame_preview_gen.get(preview_frame, 0) == gen:
                def _set():
                    self._display_file_info(
                        temp_path, "Mesh", preview_frame)
                self._on_main(_set)
    except Exception as e:
        print(f"Failed to display mesh: {e}")
        if self._frame_preview_gen.get(preview_frame, 0) == gen:
            def _set():
                self._display_file_info(temp_path, "Mesh", preview_frame)
            self._on_main(_set)


def _convert_mesh_to_obj(self, mesh_data, asset_id, asset_name=None):
    try:
        import shared.mesh_processing as mesh_processing
        obj_path = self._make_sj_temp_file(
            "mesh", asset_id, ".obj", asset_name)
        obj_content = mesh_processing.convert(
            mesh_data, output_path=str(obj_path)
        )

        if obj_content and obj_path.exists() and obj_path.stat().st_size > 0:
            print(f"Successfully converted mesh to OBJ: {obj_path}")
            return str(obj_path)
        else:
            print("Mesh conversion produced empty or invalid OBJ file")
            return None

    except ImportError:
        print(
            "mesh_processing module not found. Please ensure mesh_processing.py is in the same directory."
        )
        return None
    except Exception as e:
        print(f"Mesh conversion failed: {e}")
        import traceback
        traceback.print_exc()
        return None


def _parse_obj_to_gl_mesh(obj_path: str) -> "dict | None":
    """Parse an OBJ file directly into GL-ready numpy arrays, bypassing PyVista.

    Computes normals from face geometry (weighted cross products) rather than
    using the normals stored in the file — Roblox's stored normals can be in a
    different coordinate convention, causing incorrect lighting.  Auto-orients
    them outward using the mesh centroid (same approach as VTK auto_orient_normals).

    Returns dict with keys: verts, norms, idx, colors, bounds, n_points, n_cells
    """
    positions = []
    colors = []
    faces = []
    has_real_colors = False

    try:
        with open(obj_path, 'r', encoding='utf-8', errors='replace') as f:
            for line in f:
                if line.startswith('v '):
                    parts = line.split()
                    if len(parts) < 4:
                        continue
                    x, y, z = float(parts[1]), float(parts[2]), float(parts[3])
                    positions.append((x, y, z))
                    if len(parts) >= 7:
                        r, g, b = float(parts[4]), float(parts[5]), float(parts[6])
                        if r > 1.0 or g > 1.0 or b > 1.0:
                            r, g, b = r / 255.0, g / 255.0, b / 255.0
                        r, g, b = min(1.0, max(0.0, r)), min(1.0, max(0.0, g)), min(1.0, max(0.0, b))
                        colors.append((r, g, b))
                        if not (r > 0.98 and g > 0.98 and b > 0.98):
                            has_real_colors = True
                    else:
                        colors.append((1.0, 1.0, 1.0))
                elif line.startswith('f '):
                    parts = line.split()
                    if len(parts) < 4:
                        continue
                    def _vi(s):
                        return int(s.split('/')[0]) - 1
                    face_verts = [_vi(p) for p in parts[1:]]
                    n_pos = len(positions)
                    for j in range(1, len(face_verts) - 1):
                        a, b, c = face_verts[0], face_verts[j], face_verts[j + 1]
                        if a < n_pos and b < n_pos and c < n_pos:
                            faces.append((a, b, c))
    except Exception as e:
        print(f'[_parse_obj_to_gl_mesh] Error: {e}')
        return None

    if not positions or not faces:
        return None

    verts_orig = np.array(positions, dtype=np.float32)
    idx_orig   = np.array(faces,     dtype=np.uint32)

    # Compute face normals from geometry.
    v0 = verts_orig[idx_orig[:, 0]]
    v1 = verts_orig[idx_orig[:, 1]]
    v2 = verts_orig[idx_orig[:, 2]]
    fn = np.cross(v1 - v0, v2 - v0).astype(np.float32)

    # Per-face orient: flip any face whose normal points toward the centroid.
    centroid     = verts_orig.mean(axis=0)
    face_centers = (v0 + v1 + v2) / 3.0
    face_outward = face_centers - centroid
    flip_mask    = np.sum(fn * face_outward, axis=1) < 0
    fn[flip_mask] = -fn[flip_mask]

    # Normalize face normals.
    fn_len = np.linalg.norm(fn, axis=1, keepdims=True)
    fn /= np.where(fn_len < 1e-8, 1.0, fn_len)

    # Expand to per-face vertices (flat shading).
    # Each triangle gets its own 3 unique verts so normals are never averaged
    # across faces — avoids smooth-shading on shared-vertex meshes (e.g. cubes).
    colors_orig = np.array(colors, dtype=np.float32) if has_real_colors else np.ones((len(positions), 3), dtype=np.float32)
    flat_idx    = idx_orig.reshape(-1)                        # (n_tris*3,)
    verts      = np.ascontiguousarray(verts_orig[flat_idx])   # (n_tris*3, 3)
    norms      = np.ascontiguousarray(np.repeat(fn, 3, axis=0))  # (n_tris*3, 3)
    colors_arr = np.ascontiguousarray(colors_orig[flat_idx])  # (n_tris*3, 3)
    idx        = np.arange(len(flat_idx), dtype=np.uint32).reshape(-1, 3)
    n          = len(verts)

    mn = verts_orig.min(axis=0)
    mx = verts_orig.max(axis=0)
    bounds = (float(mn[0]), float(mx[0]), float(mn[1]), float(mx[1]), float(mn[2]), float(mx[2]))

    return {
        'verts':    np.ascontiguousarray(verts),
        'norms':    np.ascontiguousarray(norms),
        'idx':      np.ascontiguousarray(idx),
        'colors':   colors_arr,
        'bounds':   bounds,
        'n_points': n,
        'n_cells':  len(faces),
    }


def _parse_obj_vertex_colors(obj_path: str) -> "np.ndarray | None":
    """Parse per-vertex RGB colors from 'v x y z r g b' lines in an OBJ file.

    Returns a float32 Nx3 array in [0,1] range, or None if no real colors found.
    """
    colors = []
    has_real_colors = False
    try:
        with open(obj_path, 'r', encoding='utf-8', errors='replace') as f:
            for line in f:
                if not line.startswith('v '):
                    continue
                parts = line.split()
                if len(parts) >= 7:
                    try:
                        r, g, b = float(parts[4]), float(parts[5]), float(parts[6])
                        if r > 1.0 or g > 1.0 or b > 1.0:
                            r, g, b = r / 255.0, g / 255.0, b / 255.0
                        colors.append([r, g, b])
                        if not (r > 0.98 and g > 0.98 and b > 0.98):
                            has_real_colors = True
                    except ValueError:
                        colors.append([1.0, 1.0, 1.0])
                else:
                    colors.append([1.0, 1.0, 1.0])
    except Exception:
        return None
    if not colors or not has_real_colors:
        return None
    return np.array(colors, dtype=np.float32)


def _display_3d_model(self, obj_path, preview_frame, gen):
    """Render an OBJ mesh directly via OpenGL (AnimGLWidget) — no off-screen plotter.

    Mesh data is built on the background thread; the GL widget is created on
    the main thread and renders at native GPU speed like the anim preview.
    """
    if self._frame_preview_gen.get(preview_frame, 0) != gen:
        return

    try:
        # Ensure anim_gl_widget is importable (same dir as animpreview.py)
        animpreview_dir = os.path.dirname(os.path.abspath(self.animpreview_script))
        if animpreview_dir not in sys.path:
            sys.path.insert(0, animpreview_dir)
        from anim_gl_widget import AnimGLWidget

        # Parse OBJ directly — preserves Roblox's own normals without going through
        # PyVista/VTK, which can silently discard or recompute vn normals incorrectly.
        parsed = _parse_obj_to_gl_mesh(obj_path)
        if parsed is None:
            raise RuntimeError("OBJ parse returned no geometry")

        gl_mesh      = {k: parsed[k] for k in ('verts', 'norms', 'idx', 'colors')}
        scene_bounds = parsed['bounds']
        n_points     = parsed['n_points']
        n_cells      = parsed['n_cells']

        vc = gl_mesh.get('colors')
        has_vertex_colors = vc is not None and not np.allclose(vc, 1.0)
        print(f'[3DModel] n_points={n_points} n_cells={n_cells} has_vc={has_vertex_colors}')
        # White tint when vertex colors are present; warm neutral otherwise.
        mesh_color = (1.0, 1.0, 1.0, 1.0) if has_vertex_colors else (0.91, 0.90, 0.88, 1.0)

    except Exception as e:
        err_msg = str(e)
        print(f"Failed to display 3D model: {err_msg}")
        if self._frame_preview_gen.get(preview_frame, 0) == gen:
            def _err(m=err_msg):
                layout = preview_frame.layout()
                if layout:
                    layout.addWidget(QLabel(f"Error loading 3D model: {m}"))
            self._on_main(_err)
        return

    if self._frame_preview_gen.get(preview_frame, 0) != gen:
        return

    def _set():
        if self._frame_preview_gen.get(preview_frame, 0) != gen:
            return

        # Stop audio if playing in this frame.
        if preview_frame in getattr(self, "audio_players", {}):
            try:
                self.audio_players[preview_frame].stop()
            except Exception:
                pass
            del self.audio_players[preview_frame]

        # Clear existing layout content.
        layout = preview_frame.layout()
        if layout:
            while layout.count():
                child = layout.takeAt(0)
                if child.widget():
                    child.widget().hide()
                    child.widget().setParent(None)
                    child.widget().deleteLater()

        self._preview_state = getattr(self, "_preview_state", {})
        state = self._preview_state.setdefault(preview_frame, {})

        # Save camera state BEFORE clearing — checks any live GL widget (anim or mesh)
        # so cross-type asset switches also preserve the camera angle.
        _cam_state = _extract_cam_state(state)

        # Suppress repaints on the top-level window during GL context creation
        # to prevent the initial OpenGL HWND setup from causing a flash.
        # Use preview_frame.update() (not _top.update()) afterwards so only
        # the preview area repaints — not the entire dialog or main window.
        _top = preview_frame.window()
        _top.setUpdatesEnabled(False)
        try:
            _main_mod = sys.modules.get('__main__')
            _is_dark = True
            _sys_is_dark = getattr(_main_mod, 'system_is_dark', None)
            if _sys_is_dark:
                _is_dark = _sys_is_dark()
            _bg = (0.118, 0.118, 0.129) if _is_dark else (0.88, 0.90, 0.93)

            # Use vertex colors when present, otherwise light-blue uniform tint
            gl = AnimGLWidget(
                gl_meshes={0: gl_mesh},
                colors={0: mesh_color},
                initial_transforms={0: np.eye(4, dtype=np.float32)},
                scene_bounds=scene_bounds,
                parent=preview_frame,
                bg_color=_bg,
                initial_camera=_cam_state,
            )
            layout.addWidget(gl, stretch=1)
            state["mesh_gl"] = gl

            # Apply saved wireframe / fps-mode / grid / auto-rotate prefs
            _saved = _load_preview_prefs()
            if _saved.get("wireframe", False):
                gl.toggle_wireframe()
            if _saved.get("fps_mode", False):
                gl.toggle_fps()
            if not _saved.get("show_grid", True):
                gl.toggle_grid()
            if _saved.get("auto_rotate", False):
                gl.toggle_auto_rotate()

            info_label = QLabel(f"3D Model | Vertices: {n_points} | Faces: {n_cells}")
            layout.addWidget(info_label)
            state["mesh_info_label"] = info_label

            buttons_frame = self._add_preview_buttons(
                obj_path, preview_frame,
                show_obj_options=True,
                wireframe_fn=gl.toggle_wireframe,
                fps_fn=gl.toggle_fps,
                grid_fn=gl.toggle_grid,
                auto_rotate_fn=gl.toggle_auto_rotate,
                reset_view_fn=gl.reset_view,
            )
            state["mesh_buttons_frame"] = buttons_frame
        finally:
            _top.setUpdatesEnabled(True)
            preview_frame.update()

        preview_frame.show()

    self._on_main(_set)


def _display_solidmodel_preview(self, cache_data, asset_id, asset_name, preview_frame, gen):
    """Preview a SolidModel (asset type 39) by extracting and rendering its CSG mesh."""
    try:
        import sys as _sys, os as _os, gzip as _gzip
        _cache_dir = _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))
        if _cache_dir not in _sys.path:
            _sys.path.insert(0, _cache_dir)

        from tools.solidmodel_converter.converter import (
            deserialize_rbxm, _get_top_level_mesh_data, _try_extract_child_data,
        )
        from tools.solidmodel_converter.csg_mesh import parse_csg_mesh_full, export_obj

        _ZSTD = b'\x28\xb5\x2f\xfd'
        _GZIP = b'\x1f\x8b'
        data = cache_data
        if data[:4] == _ZSTD:
            import zstandard
            data = zstandard.ZstdDecompressor().decompress(data, max_output_size=64 * 1024 * 1024)
        elif data[:2] == _GZIP:
            data = _gzip.decompress(data)

        doc = deserialize_rbxm(data)
        print(f'[SolidModel] roots: {[r.class_name for r in doc.roots]}')

        mesh_data = _get_top_level_mesh_data(doc)

        if mesh_data is None:
            child_doc = _try_extract_child_data(doc)
            if child_doc is not None:
                print(f'[SolidModel] ChildData roots: {[r.class_name for r in child_doc.roots]}')
                mesh_data = _get_top_level_mesh_data(child_doc)

        if mesh_data is None:
            # Last-resort: any instance with non-empty bytes MeshData property
            for inst in list(doc.roots) + list(doc.instances.values()):
                prop = inst.properties.get('MeshData')
                if prop is not None and isinstance(prop.value, bytes) and len(prop.value) > 0:
                    mesh_data = prop.value
                    print(f'[SolidModel] Found MeshData on {inst.class_name} (fallback)')
                    break

        if mesh_data is None:
            # SolidModel has no precomputed mesh — it's a build-time CSG
            # (Parts + operations) that requires client-side evaluation.
            def _no_mesh():
                if self._frame_preview_gen.get(preview_frame, 0) != gen:
                    return
                layout = preview_frame.layout()
                if layout:
                    layout.addWidget(QLabel(
                        'SolidModel has no precomputed mesh.\n'
                        'This asset uses client-side CSG and cannot be previewed.'
                    ))
            self._on_main(_no_mesh)
            return

        try:
            result = parse_csg_mesh_full(mesh_data)
        except ValueError as ve:
            err_msg = str(ve)
            print(f'[SolidModel] parse failed: {err_msg}')
            def _fmt_err(m=err_msg):
                if self._frame_preview_gen.get(preview_frame, 0) != gen:
                    return
                layout = preview_frame.layout()
                if layout:
                    layout.addWidget(QLabel(f'Cannot preview SolidModel:\n{m}'))
            self._on_main(_fmt_err)
            return

        vertices = result.vertices
        indices = result.indices
        if result.submesh_boundaries and len(result.submesh_boundaries) > 1:
            indices = indices[:result.submesh_boundaries[1]]

        obj_path = self._make_sj_temp_file('mesh', asset_id, '.obj', asset_name)
        export_obj(vertices, indices, obj_path, object_name=asset_name or 'SolidModel')

        self._display_3d_model(str(obj_path), preview_frame, gen)

    except Exception as e:
        err_msg = str(e)
        print(f'[SolidModel preview] Failed: {err_msg}')
        import traceback; traceback.print_exc()
        if self._frame_preview_gen.get(preview_frame, 0) == gen:
            def _err(m=err_msg):
                layout = preview_frame.layout()
                if layout:
                    layout.addWidget(QLabel(f'Failed to build SolidModel preview: {m}'))
            self._on_main(_err)


def _display_localization_preview(self, cache_data, preview_frame, gen):
    """Preview LocalizationTable as raw text (JSON)."""
    try:
        raw = strip_cache_header(cache_data)
        txt = raw.decode("utf-8", errors="replace")
    except Exception:
        # Fall back to generic JSON preview if decoding fails
        return self._display_json_preview(cache_data, preview_frame, gen)

    # Pretty-print JSON when possible, otherwise show raw.
    try:
        obj = json.loads(txt)
        txt_to_show = json.dumps(obj, indent=2, ensure_ascii=False)
    except Exception:
        txt_to_show = txt

    def _set():
        if self._frame_preview_gen.get(preview_frame, 0) != gen:
            return

        if not preview_frame.layout():
            preview_frame.setLayout(QVBoxLayout())
        layout = preview_frame.layout()
        self._clear_layout(layout)

        editor = QTextEdit(preview_frame)
        editor.setReadOnly(True)
        try:
            editor.setLineWrapMode(QTextEdit.NoWrap)
        except Exception:
            pass
        editor.setPlainText(txt_to_show)

        layout.addWidget(editor, 1)

    self._on_main(_set)


def _display_json_preview(self, data, preview_frame, gen):
    import json
    layout = preview_frame.layout()

    try:
        json_obj = json.loads(data)
        formatted = json.dumps(json_obj, indent=2)
    except:
        formatted = data.decode('utf-8', errors='ignore')

    if self._frame_preview_gen.get(preview_frame, 0) == gen:
        def _set():
            text_edit = QTextEdit()
            text_edit.setReadOnly(True)
            text_edit.setPlainText(formatted)
            layout.addWidget(text_edit)
            self._add_preview_buttons(None, preview_frame)
        self._on_main(_set)


def _display_text_preview(self, data, preview_frame, gen):
    layout = preview_frame.layout()

    text = data.decode('utf-8', errors='ignore')
    if self._frame_preview_gen.get(preview_frame, 0) == gen:
        def _set():
            text_edit = QTextEdit()
            text_edit.setReadOnly(True)
            text_edit.setPlainText(text)
            layout.addWidget(text_edit)
            self._add_preview_buttons(None, preview_frame)
        self._on_main(_set)


def _rbxm_to_rbxmx_xml(data: bytes, animpreview_dir: str) -> str:
    """Parse binary RBXM and generate RBXMX XML compatible with animpreview."""
    if animpreview_dir not in sys.path:
        sys.path.insert(0, animpreview_dir)
    import rbxm_parser as _rbxm_parser

    instances = _rbxm_parser.parse_rbxm(data)
    ks_list = _rbxm_parser.find_by_class(instances, "KeyframeSequence")
    if not ks_list:
        raise ValueError("No KeyframeSequence found in RBXM data")
    ks = ks_list[0]

    def cframe_xml(name: str, cf: dict) -> str:
        pos = cf.get("position", (0.0, 0.0, 0.0))
        rot = cf.get("rotation", [1, 0, 0, 0, 1, 0, 0, 0, 1])
        keys = ("R00", "R01", "R02", "R10", "R11", "R12", "R20", "R21", "R22")
        rot_xml = "".join(f"<{k}>{rot[i]}</{k}>" for i, k in enumerate(keys))
        return (f'<CoordinateFrame name="{name}">'
                f'<X>{pos[0]}</X><Y>{pos[1]}</Y><Z>{pos[2]}</Z>'
                f'{rot_xml}</CoordinateFrame>')

    def render_pose(inst, indent: str) -> str:
        name = inst.properties.get("Name", "")
        cf = inst.properties.get("CFrame", {"position": (
            0, 0, 0), "rotation": [1, 0, 0, 0, 1, 0, 0, 0, 1]})
        children_xml = "".join(render_pose(c, indent + "  ")
                               for c in inst.children if c.class_name == "Pose")
        return (f'{indent}<Item class="Pose" referent="{inst.referent}">\n'
                f'{indent}  <Properties>\n'
                f'{indent}    <string name="Name">{name}</string>\n'
                f'{indent}    {cframe_xml("CFrame", cf)}\n'
                f'{indent}  </Properties>\n'
                f'{children_xml}'
                f'{indent}</Item>\n')

    def render_keyframe(inst, indent: str) -> str:
        time_val = inst.properties.get("Time", 0.0)
        poses_xml = "".join(render_pose(c, indent + "  ")
                            for c in inst.children if c.class_name == "Pose")
        return (f'{indent}<Item class="Keyframe" referent="{inst.referent}">\n'
                f'{indent}  <Properties>\n'
                f'{indent}    <float name="Time">{time_val}</float>\n'
                f'{indent}  </Properties>\n'
                f'{poses_xml}'
                f'{indent}</Item>\n')

    keyframes_xml = "".join(render_keyframe(c, "    ")
                            for c in ks.children if c.class_name == "Keyframe")
    return (f'<roblox version="4">\n'
            f'  <Item class="KeyframeSequence" referent="{ks.referent}">\n'
            f'    <Properties/>\n'
            f'{keyframes_xml}'
            f'  </Item>\n'
            f'</roblox>\n')


def _display_animation_preview(self, data: bytes, temp_path: str, asset_id: int, asset_name, preview_frame, gen, token):
    layout = preview_frame.layout()

    # Basic checks
    if not os.path.exists(self.animpreview_script):
        if self._frame_preview_gen.get(preview_frame, 0) == gen:
            def _set():
                layout.addWidget(
                    QLabel(f"animpreview.py not found: {self.animpreview_script}"))
                self._add_preview_buttons(temp_path, preview_frame)
            self._on_main(_set)
        return

    # If data is already RBXMX (XML animation), skip rojo entirely
    data_start = data[:min(512, len(data))].decode("utf-8", errors="ignore")
    is_already_rbxmx = 'assettype="animation"' in data_start

    def run_preview() -> tuple:
        workdir_p = self._make_sj_temp_dir(
            "animation", asset_id, "animpreview")
        workdir_p.mkdir(parents=True, exist_ok=True)

        if is_already_rbxmx:
            out_anim = workdir_p / "output_anim.rbxmx"
            out_anim.write_bytes(data)
            return str(out_anim), str(workdir_p)

        animpreview_dir = os.path.dirname(
            os.path.abspath(self.animpreview_script))

        xml_str = _rbxm_to_rbxmx_xml(data, animpreview_dir)
        out_anim = workdir_p / "output_anim.rbxmx"
        out_anim.write_text(xml_str, encoding="utf-8")
        return str(out_anim), str(workdir_p)

    # call build once
    try:
        out_anim_path, workdir = run_preview()
        self._track_temp(preview_frame, workdir, token=token)
    except Exception as e:
        if self._frame_preview_gen.get(preview_frame, 0) == gen:
            _err_msg = str(e)
            def _set_err(msg=_err_msg):
                layout.addWidget(QLabel(f"Failed to build preview: {msg}"))
                self._add_preview_buttons(temp_path, preview_frame)
            self._on_main(_set_err)
        return

    # Decide rig type from built rbxmx
    try:
        anim_text = Path(out_anim_path).read_text(
            encoding="utf-8", errors="ignore")
    except Exception:
        anim_text = ""

    is_r15 = any(k in anim_text for k in (
        "UpperTorso", "LowerTorso",
        "LeftUpperArm", "LeftLowerArm", "LeftHand",
        "RightUpperArm", "RightLowerArm", "RightHand",
        "LeftUpperLeg", "LeftLowerLeg", "LeftFoot",
        "RightUpperLeg", "RightLowerLeg", "RightFoot",
    ))
    is_r6 = "Torso" in anim_text and "UpperTorso" not in anim_text
    is_placeholder = not is_r15 and not is_r6
    rig_path = self.animpreview_r15_rig if is_r15 else self.animpreview_r6_rig

    # import animpreview & pre-load all heavy data on the background thread
    animpreview_dir = os.path.dirname(
        os.path.abspath(self.animpreview_script))
    if animpreview_dir not in sys.path:
        sys.path.insert(0, animpreview_dir)

    animpreview = importlib.import_module("animpreview")

    mesh_dir = os.path.join(animpreview_dir, "R15AndR6Parts")

    # Pre-load rig, animation keyframes, and all OBJ meshes here on the
    # background thread so the main thread only has to create Qt/VTK widgets.
    try:
        _keys = animpreview.load_animation(out_anim_path)
        if is_placeholder:
            _parts, _motors = animpreview.build_placeholder_rig(_keys)
            _prefix = "R15"
        else:
            _parts, _motors = animpreview.load_rig(rig_path)
            _prefix = animpreview.detect_rig_prefix(_parts)
        _meshes = {
            ref: animpreview.load_obj_mesh(mesh_dir, _prefix, p.name, p.size)
            for ref, p in _parts.items()
        }
        preloaded = {
            "parts": _parts,
            "motors": _motors,
            "keys": _keys,
            "prefix": _prefix,
            "meshes": _meshes,
            "is_placeholder": is_placeholder,
        }
    except Exception as e:
        if self._frame_preview_gen.get(preview_frame, 0) == gen:
            def _set_err_preload():
                preview_frame.layout().addWidget(
                    QLabel(f"Animation pre-load failed: {e}"))
                self._add_preview_buttons(temp_path, preview_frame)
            self._on_main(_set_err_preload)
        return

    if self._frame_preview_gen.get(preview_frame, 0) == gen:
        def _swap_in():
            if self._frame_preview_gen.get(preview_frame, 0) != gen:
                return

            self._preview_state = getattr(self, "_preview_state", {})
            state = self._preview_state.setdefault(preview_frame, {})
            layout = preview_frame.layout()

            # Stop any audio playing in this frame
            if preview_frame in getattr(self, "audio_players", {}):
                try:
                    self.audio_players[preview_frame].stop()
                except Exception:
                    pass
                try:
                    del self.audio_players[preview_frame]
                except Exception:
                    pass

            # Close any 3D plotter in this frame
            plotter = getattr(self, "_plotters", {}).pop(preview_frame, None)
            if plotter is not None:
                try:
                    plotter.close()
                except Exception:
                    pass

            # Save camera state BEFORE clearing so the new widget can restore it.
            # _extract_cam_state checks any live GL widget (anim or mesh) and falls
            # back to the last saved state, so cross-type switches are preserved.
            _cam_state = _extract_cam_state(state)

            # Clear all existing layout content (handles stale widgets from
            # any previous preview type, including inline_b64 mesh which
            # bypasses display_preview_enhanced and may leave a plotter behind)
            if layout:
                while layout.count():
                    child = layout.takeAt(0)
                    if child.widget():
                        child.widget().deleteLater()

            # Drop stale state widget refs — the objects were just deleted above
            state.pop("anim_viewer", None)
            state.pop("anim_buttons_frame", None)

            preview_frame.setUpdatesEnabled(False)
            try:
                _main_mod = sys.modules.get('__main__')
                _sys_is_dark = getattr(_main_mod, 'system_is_dark', None)
                _is_dark = _sys_is_dark() if _sys_is_dark else True
                _anim_bg = (0.118, 0.118, 0.129) if _is_dark else (0.88, 0.90, 0.93)

                viewer = animpreview.AnimPreviewWidget(
                    rig_path, out_anim_path, mesh_dir=mesh_dir,
                    preloaded=preloaded,
                    open_externally_fn=lambda: self._open_externally(temp_path),
                    initial_camera=_cam_state,
                    bg_color=_anim_bg,
                )
                layout.addWidget(viewer)
                state["anim_viewer"] = viewer

                state["anim_buttons_frame"] = self._add_preview_buttons(
                    None, preview_frame, options_menu=viewer.options_menu)
            finally:
                preview_frame.setUpdatesEnabled(True)
                preview_frame.update()

        self._on_main(_swap_in)


def _display_texture_preview(self, xml_filepath, asset_id, asset_name, preview_frame, gen):
    # Bail early if the user already moved to a different item
    if self._frame_preview_gen.get(preview_frame, 0) != gen:
        return

    def _clear_loading():
        if self._frame_preview_gen.get(preview_frame, 0) != gen:
            return
        lo = preview_frame.layout()
        if lo:
            while lo.count():
                w = lo.takeAt(0).widget()
                if w:
                    w.deleteLater()

    try:
        # Read XML
        with open(xml_filepath, "r", encoding="utf-8") as f:
            xml_text = f.read()

        # Parse texture pack
        packs = self.read_texturepack_xml(xml_text)
        if not packs:
            self._on_main(_clear_loading)
            return

        pack = packs[0]

        # Collect map IDs
        map_ids = {
            k: pack[k]
            for k in ("color", "normal", "metalness", "roughness")
            if k in pack
        }

        if not map_ids:
            self._on_main(_clear_loading)
            return

        # Roblox session - bypass header prevents these preview requests from
        # appearing in the cache finder.
        cookie = get_roblosecurity()
        sess = self._new_session(cookie)
        sess.headers["X-Preview-Bypass"] = "1"

        # Batch request
        payload = []
        id_to_key = {}
        for i, (map_key, map_aid) in enumerate(map_ids.items()):
            payload.append({"assetId": map_aid, "requestId": str(i)})
            id_to_key[str(i)] = map_key

        r = sess.post(
            "https://assetdelivery.roblox.com/v2/assets/batch",
            json=payload,
            timeout=15
        )
        if not r.ok:
            self._on_main(_clear_loading)
            return

        # Download textures
        urls_map = {}
        for entry in r.json():
            map_key = id_to_key.get(entry.get("requestId", ""))
            loc = batch_location(entry)
            if map_key and loc:
                urls_map[map_key] = loc

        # Download textures using plain threading
        downloaded = {}

        def worker(wkey, url):
            try:
                resp = sess.get(url, timeout=20)
                if resp.ok:
                    tex_path = self._sj_temp_root() / "texture" / \
                        f"tex_{wkey}_{asset_id}.png"
                    tex_path.parent.mkdir(parents=True, exist_ok=True)
                    tex_path.write_bytes(resp.content)
                    downloaded[wkey] = str(tex_path)
                    self._track_temp(preview_frame, str(tex_path))
            except Exception:
                pass

        threads = []
        for wkey, url in urls_map.items():
            t = threading.Thread(target=worker, args=(wkey, url))
            t.start()
            threads.append(t)

        for t in threads:
            t.join()

        # Render flat material preview
        color_path = downloaded.get("color")
        normal_path = downloaded.get("normal")
        metal_path = downloaded.get("metalness")
        rough_path = downloaded.get("roughness")

        if not color_path and not normal_path:
            self._on_main(_clear_loading)
            return

        # Create temp preview path
        preview_path = self._sj_temp_root() / "texture" / \
            f"ASSET_{asset_id}_preview.png"
        preview_path.parent.mkdir(parents=True, exist_ok=True)
        temp_preview_path = str(preview_path)
        self._track_temp(preview_frame, temp_preview_path)

        self.render_flat_material(
            color_map=color_path if color_path else None,
            normal_map=normal_path if normal_path else None,
            metal_map=metal_path if metal_path else None,
            rough_map=rough_path if rough_path else None,
            output_png=temp_preview_path
        )

        # Display in Qt
        layout = preview_frame.layout()

        if self._frame_preview_gen.get(preview_frame, 0) == gen:
            def _set():
                while layout.count():
                    w = layout.takeAt(0).widget()
                    if w:
                        w.deleteLater()

                pixmap = QPixmap(temp_preview_path).scaled(
                    400, 400, Qt.KeepAspectRatio, Qt.SmoothTransformation
                )

                img_label = QLabel()
                img_label.setPixmap(pixmap)
                img_label.setAlignment(Qt.AlignCenter)
                img_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
                layout.addWidget(img_label, stretch=1)

                size = os.path.getsize(temp_preview_path)
                info = f"Size: {self._format_size(size)} | {pixmap.width()}x{pixmap.height()}"

                layout.addWidget(QLabel(info))

                self._add_preview_buttons(temp_preview_path, preview_frame)
            self._on_main(_set)

    except Exception as e:
        print(f"[TexturePack preview] render failed: {e}")
        import traceback
        traceback.print_exc()
        self._on_main(_clear_loading)


def render_flat_material(
    self,
    color_map,
    normal_map=None,
    metal_map=None,
    rough_map=None,
    output_png="preview.png",
    light_dir=(0.3, 0.6, 1.0),
    ambient=0.25,
    max_size=512,
):

    # Load albedo or use default gray
    if color_map:
        albedo = Image.open(color_map).convert("RGB")
        if max(albedo.size) > max_size:
            albedo.thumbnail((max_size, max_size), Image.LANCZOS)
        w, h = albedo.size
        albedo_np = np.asarray(albedo).astype(np.float32) / 255.0
    else:
        # default gray 512x512
        w, h = max_size, max_size
        albedo_np = np.ones((h, w, 3), dtype=np.float32) * 0.5

    # Normal map
    if normal_map:
        normal = Image.open(normal_map).convert("RGB").resize((w, h), Image.LANCZOS)
        n = np.asarray(normal).astype(np.float32) / 255.0
        normals = n * 2.0 - 1.0
    else:
        normals = np.zeros((h, w, 3), dtype=np.float32)
        normals[:, :, 2] = 1.0

    # Metalness
    if metal_map:
        metal = np.asarray(Image.open(metal_map).convert(
            "L").resize((w, h), Image.LANCZOS)).astype(np.float32) / 255.0
    else:
        metal = np.zeros((h, w), dtype=np.float32)

    # Roughness
    if rough_map:
        rough = np.asarray(Image.open(rough_map).convert(
            "L").resize((w, h), Image.LANCZOS)).astype(np.float32) / 255.0
    else:
        rough = np.ones((h, w), dtype=np.float32) * 0.8

    # Lighting
    L = np.array(light_dir, dtype=np.float32)
    L /= np.linalg.norm(L)
    NdotL = np.clip(
        normals[:, :, 0] * L[0] +
        normals[:, :, 1] * L[1] +
        normals[:, :, 2] * L[2],
        0.0, 1.0
    )

    # Diffuse + Specular
    diffuse = albedo_np * (ambient + (1.0 - ambient) * NdotL[:, :, None])
    spec = (1.0 - rough) * (0.04 + metal * 0.96)
    specular = spec[:, :, None] * (NdotL[:, :, None] ** 16)
    result = np.clip(diffuse + specular, 0.0, 1.0)

    # Save
    Image.fromarray((result * 255).astype(np.uint8)).save(output_png)


def _start_new_preview_session(self, preview_frame):
    token = uuid.uuid4().hex
    self._preview_token[preview_frame] = token
    self.temp_files[(preview_frame, token)] = []
    return token


def _track_temp(self, preview_frame, path_or_dir, token=None):
    tok = token or self._preview_token.get(preview_frame)
    if not tok:
        tok = self._start_new_preview_session(preview_frame)

    self.temp_files.setdefault(
        (preview_frame, tok), []).append(path_or_dir)


def _display_file_info(self, filepath, file_type, preview_frame):
    layout = preview_frame.layout()

    size = os.path.getsize(filepath)

    layout.addWidget(QLabel(f"File Type: {file_type}"))
    layout.addWidget(QLabel(f"File Size: {self._format_size(size)}"))

    self._add_preview_buttons(filepath, preview_frame)


def _add_preview_buttons(self, filepath, preview_frame, show_obj_options=False, wireframe_fn=None, fps_fn=None, grid_fn=None, auto_rotate_fn=None, reset_view_fn=None, options_menu=None):
    layout = preview_frame.layout()

    # Prevent stacking multiple button bars when a preview refreshes
    self._preview_state = getattr(self, "_preview_state", {})
    state = self._preview_state.setdefault(preview_frame, {})
    old_bar = state.get("buttons_frame")
    if old_bar is not None:
        try:
            old_bar.deleteLater()
        except Exception:
            pass
        state["buttons_frame"] = None

    # Detect loader panes so we can add mode label + nav buttons
    is_uses = (preview_frame is getattr(self, "_uses_content_frame", None))
    is_replaces = (preview_frame is getattr(
        self, "_replaces_content_frame", None))

    button_frame = QFrame()
    outer_vbox = QVBoxLayout(button_frame)
    outer_vbox.setContentsMargins(0, 0, 0, 0)
    outer_vbox.setSpacing(2)

    # Mode label above button row (loader panes only)
    if is_uses or is_replaces:
        mode_lbl = QLabel()
        if is_uses:
            mode_lbl.setText("Previewing: Uses")
        else:
            ids = getattr(self, "_replace_preview_ids", [])
            idx = getattr(self, "_replace_preview_idx", 0)
            mode_lbl.setText(
                f"Previewing: Replaces ({idx + 1}/{len(ids)})" if ids
                else "Previewing: Replaces"
            )
        mode_lbl.setStyleSheet(
            "color: #aaaaaa; font-size: 11px; padding: 1px 4px;")
        outer_vbox.addWidget(mode_lbl)
        state["mode_label"] = mode_lbl

    # Horizontal button row
    row_widget = QWidget()
    button_layout = QHBoxLayout(row_widget)
    button_layout.setContentsMargins(0, 0, 0, 0)
    button_layout.setSpacing(4)

    close_btn = QPushButton("Close Preview")
    close_btn.clicked.connect(
        lambda: self.close_preview(preview_frame, deselect=True))
    button_layout.addWidget(close_btn)

    if options_menu is not None:
        opt_btn = QPushButton("Options")
        opt_btn.setMenu(options_menu)
        button_layout.addWidget(opt_btn)
    elif wireframe_fn is not None or fps_fn is not None or grid_fn is not None or auto_rotate_fn is not None or reset_view_fn is not None:
        options_btn = QPushButton("Options")
        options_menu = QMenu(preview_frame)
        _prefs = _load_preview_prefs()
        if reset_view_fn is not None:
            options_menu.addAction("Reset View", reset_view_fn)
            options_menu.addSeparator()
        if wireframe_fn is not None:
            wf_action = options_menu.addAction("Wireframe Mode")
            wf_action.setCheckable(True)
            wf_action.setChecked(bool(_prefs.get("wireframe", False)))
            def _on_wf(checked, fn=wireframe_fn):
                _p = _load_preview_prefs(); _p["wireframe"] = checked; _save_preview_prefs(_p)
                fn()
            wf_action.toggled.connect(_on_wf)
        if fps_fn is not None:
            fps_action = options_menu.addAction("FPS Freecam")
            fps_action.setCheckable(True)
            fps_action.setChecked(bool(_prefs.get("fps_mode", False)))
            def _on_fps(checked, fn=fps_fn):
                _p = _load_preview_prefs(); _p["fps_mode"] = checked; _save_preview_prefs(_p)
                fn()
            fps_action.toggled.connect(_on_fps)
            # Sync checkbox when WASD triggers FPS mode directly on the GL widget
            _gl = getattr(fps_fn, '__self__', None)
            if _gl is not None and hasattr(_gl, 'fps_mode_changed'):
                def _sync_fps(checked, _a=fps_action):
                    _a.blockSignals(True)
                    _a.setChecked(checked)
                    _a.blockSignals(False)
                    _p = _load_preview_prefs(); _p["fps_mode"] = checked; _save_preview_prefs(_p)
                _gl.fps_mode_changed.connect(_sync_fps)
        if grid_fn is not None:
            grid_action = options_menu.addAction("Show Grid")
            grid_action.setCheckable(True)
            grid_action.setChecked(bool(_prefs.get("show_grid", True)))
            def _on_grid(checked, fn=grid_fn):
                _p = _load_preview_prefs(); _p["show_grid"] = checked; _save_preview_prefs(_p)
                fn()
            grid_action.toggled.connect(_on_grid)
        if auto_rotate_fn is not None:
            ar_action = options_menu.addAction("Auto Rotate")
            ar_action.setCheckable(True)
            ar_action.setChecked(bool(_prefs.get("auto_rotate", False)))
            def _on_ar(checked, fn=auto_rotate_fn):
                _p = _load_preview_prefs(); _p["auto_rotate"] = checked; _save_preview_prefs(_p)
                fn()
            ar_action.toggled.connect(_on_ar)
        if filepath:
            options_menu.addSeparator()
            if show_obj_options:
                options_menu.addAction("Open with Default",
                                       lambda: self._open_externally(filepath))
                options_menu.addAction("Select Program",
                                       lambda: self._select_program_to_open(filepath))
            else:
                options_menu.addAction("Open Externally",
                                       lambda: self._open_externally(filepath))
        options_btn.setMenu(options_menu)
        button_layout.addWidget(options_btn)
    elif filepath:
        if show_obj_options:
            open_btn = QPushButton("Open OBJ")
            open_menu = QMenu(preview_frame)
            open_menu.addAction("Open with Default",
                                lambda: self._open_externally(filepath))
            open_menu.addAction(
                "Select Program", lambda: self._select_program_to_open(filepath))
            open_btn.setMenu(open_menu)
            button_layout.addWidget(open_btn)
        else:
            open_btn = QPushButton("Open Externally")
            open_btn.clicked.connect(
                lambda: self._open_externally(filepath))
            button_layout.addWidget(open_btn)

    # Previous / Next navigation for the replaces pane
    if is_replaces:
        ids = getattr(self, "_replace_preview_ids", [])
        idx = getattr(self, "_replace_preview_idx", 0)

        prev_btn = QPushButton("Previous")
        prev_btn.setEnabled(idx > 0)
        prev_btn.clicked.connect(lambda: self._navigate_replace_preview(-1))
        button_layout.addWidget(prev_btn)

        next_btn = QPushButton("Next")
        next_btn.setEnabled(idx < len(ids) - 1)
        next_btn.clicked.connect(lambda: self._navigate_replace_preview(1))
        button_layout.addWidget(next_btn)

        state["prev_btn"] = prev_btn
        state["next_btn"] = next_btn

    outer_vbox.addWidget(row_widget)
    layout.addWidget(button_frame)
    state["buttons_frame"] = button_frame
    return button_frame


def close_preview(self, preview_frame, deselect=False, hide=True):
    token_to_delete = self._preview_token.get(preview_frame)

    # Explicitly clean up AnimPreviewWidget before the layout is cleared.
    # deleteLater() is deferred, so the timer and VTK HWND stay alive until
    # the next event loop tick — setParent(None) detaches the Win32 HWND from
    # the main window immediately so resize events stop reaching it.
    state = getattr(self, "_preview_state", {}).get(preview_frame, {})

    anim_viewer = state.get("anim_viewer")
    if anim_viewer is not None:
        try:
            anim_viewer.timer.stop()
        except Exception:
            pass
        # GL cleanup is handled by AnimGLWidget.aboutToBeDestroyed signal
        state.pop("anim_viewer", None)

    # Stop audio if playing
    if preview_frame in self.audio_players:
        self.audio_players[preview_frame].stop()
        try:
            if hasattr(pygame.mixer.music, "unload"):
                pygame.mixer.music.unload()
        except Exception:
            pass
        del self.audio_players[preview_frame]

    plotter = getattr(self, "_plotters", {}).pop(preview_frame, None)
    if plotter is not None:
        try:
            plotter.close()
        except Exception:
            pass

    # Clear layout.  setParent(None) is called before deleteLater() so that any
    # embedded native Win32 HWNDs (VTK interactors) are detached from the main
    # window hierarchy immediately — not deferred — stopping them from receiving
    # WM_SIZE messages on subsequent main-window resizes.
    if preview_frame.layout():
        while preview_frame.layout().count():
            child = preview_frame.layout().takeAt(0)
            w = child.widget()
            if w is not None:
                w.hide()
                w.setParent(None)
                w.deleteLater()
            elif child.layout():
                while child.layout().count():
                    sub = child.layout().takeAt(0)
                    sw = sub.widget()
                    if sw is not None:
                        sw.hide()
                        sw.setParent(None)
                        sw.deleteLater()
                child.layout().deleteLater()

    # Drop all widget references for this frame so that any in-flight _set
    # callbacks (queued via _on_main) cannot pick up a stale C++ pointer.
    if hasattr(self, "_preview_state"):
        self._preview_state.pop(preview_frame, None)
    if hide:
        preview_frame.hide()

    if deselect:
        self.table_view.clearSelection()

    self._on_column_resized(-1, 0, 0, self.table_view)


def _delete_preview_temp_files(self, preview_frame, token, tries=12):
    key = (preview_frame, token)
    if key not in self.temp_files:
        return

    remaining = []
    for temp_item in self.temp_files.get(key, []):
        try:
            if os.path.isdir(temp_item):
                shutil.rmtree(temp_item)
            elif os.path.exists(temp_item):
                os.remove(temp_item)
        except PermissionError:
            remaining.append(temp_item)
        except Exception as e:
            print(f"Failed to delete temp file/dir '{temp_item}': {e}")

    if remaining and tries > 0:
        self.temp_files[key] = remaining
        QTimer.singleShot(150, lambda pf=preview_frame,
                          tok=token: self._delete_preview_temp_files(pf, tok, tries - 1))
        return

    self.temp_files.pop(key, None)


def _open_externally(self, filepath):
    if not os.path.exists(filepath):
        print(f"File does not exist: {filepath}")
        return
    try:
        os.startfile(filepath)
    except Exception as e:
        print(f"Failed to open file: {e}")


def _select_program_to_open(self, filepath):
    program = QFileDialog.getOpenFileName(
        self.tab_widget,
        "Select Program",
        "",
        "Executable files (*.exe);;All files (*.*)"
    )[0]

    if program:
        try:
            subprocess.run([program, filepath], check=True)
        except Exception as e:
            print(f"Failed to open with selected program: {e}")


def _format_size(self, size_in_bytes):
    for unit in ['B', 'KB', 'MB', 'GB']:
        if size_in_bytes < 1024.0:
            return f"{size_in_bytes:.2f} {unit}"
        size_in_bytes /= 1024.0
    return f"{size_in_bytes:.2f} TB"
