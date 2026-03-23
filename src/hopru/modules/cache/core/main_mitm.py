"""MITM proxy request/response handlers for the cache module."""

from shared.threading_utils import _MainThreadInvoker
from shared.menu_utils import StayOpenMenu
from shared.audio_player import AudioPlayer
from shared.ui_loader import load_ui
from shared.delegates import HoverDelegate
from shared.models import SortProxy
from shared.utils import strip_cache_header, get_roblosecurity, isnumeric, has_cache_data, batch_location
from shared.constants import CLOG_RAW_URL, ASSET_TYPES, adapter
import urllib.request
from requests.adapters import HTTPAdapter
import gc
from datetime import datetime
from urllib.parse import urlparse, urlunparse
from mutagen import File as MutagenFile
from shiboken6 import isValid
from pathlib import Path
import xml.etree.ElementTree as ET
from PIL import Image
import numpy as np
import importlib
import uuid
import shutil
import struct
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
import sys
import tempfile
import json
import time
import win32crypt
import base64
import re
import threading
import requests
import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
try:
    from mitmproxy import http
except Exception:
    http = None


class _SyntheticResponse:
    """Minimal synthetic response compatible with MockSyntheticResponse duck-typing."""
    def __init__(self, status_code: int, content: bytes, headers: dict):
        self.status_code = status_code
        self.content = content if isinstance(content, bytes) else content.encode("utf-8")
        self.headers = headers


def _make_response(status_code: int, content: bytes, headers: dict):
    """Create a synthetic response, using mitmproxy's http.Response if available."""
    if http is not None:
        return http.Response.make(status_code, content, headers)
    return _SyntheticResponse(status_code, content, headers)


# SolidModel / vertex-color helpers

_ZSTD_MAGIC_SM = b'\x28\xb5\x2f\xfd'
_GZIP_MAGIC_SM = b'\x1f\x8b'


def _looks_like_obj(data: bytes) -> bool:
    """Return True if data looks like a Wavefront OBJ file."""
    try:
        text = data[:1024].decode('utf-8', errors='ignore')
        return bool(re.search(r'(?m)^v\s+', text))
    except Exception:
        return False


def _looks_like_roblox_mesh(data: bytes) -> bool:
    """Return True if data looks like a Roblox .mesh file (any version)."""
    return data[:8].startswith(b'version ')


def _roblox_mesh_to_obj_bytes(mesh_data: bytes) -> bytes:
    """Convert Roblox .mesh bytes to Wavefront OBJ text bytes."""
    import shared.mesh_processing as mesh_processing
    obj_text = mesh_processing.convert(mesh_data)
    if not obj_text:
        raise ValueError('mesh_processing.convert produced no output')
    return obj_text.encode('utf-8') if isinstance(obj_text, str) else obj_text


def _inject_obj_bytes_into_solidmodel(bin_data: bytes, obj_bytes: bytes) -> bytes:
    """Replace the MeshData of a SolidModel CDN binary with OBJ geometry.

    Decompresses the CDN binary if needed, deserializes it, injects the new
    CSGMDL, sets Part.Color to white so vertex colors display correctly, then
    re-serializes as binary RBXM.
    """
    try:
        from tools.solidmodel_converter.obj_to_csg import export_csg_mesh
        from tools.solidmodel_converter.converter import deserialize_rbxm
        from tools.solidmodel_converter.rbxm.serializer import write_rbxm
        from tools.solidmodel_converter.rbxm.types import PropertyFormat, RbxProperty
    except ImportError as exc:
        print(f'[SolidModel] Import failed: {exc}')
        return bin_data

    # Decompress CDN payload if needed
    if bin_data[:4] == _ZSTD_MAGIC_SM:
        try:
            import zstandard
            bin_data = zstandard.ZstdDecompressor().decompress(
                bin_data, max_output_size=64 * 1024 * 1024
            )
            print(
                f'[SolidModel] Decompressed zstd CDN payload: {len(bin_data)} bytes')
        except Exception as exc:
            print(f'[SolidModel] zstd decompress failed: {exc}')
    elif bin_data[:2] == _GZIP_MAGIC_SM:
        try:
            bin_data = gzip.decompress(bin_data)
            print(
                f'[SolidModel] Decompressed gzip CDN payload: {len(bin_data)} bytes')
        except Exception as exc:
            print(f'[SolidModel] gzip decompress failed: {exc}')

    # Write OBJ bytes to a temp file so export_csg_mesh can read it
    import tempfile as _tempfile
    import os as _os
    tmp_path = None
    try:
        with _tempfile.NamedTemporaryFile(suffix='.obj', delete=False, mode='wb') as f:
            if isinstance(obj_bytes, str):
                f.write(obj_bytes.encode('utf-8'))
            else:
                f.write(obj_bytes)
            tmp_path = f.name

        csg_bytes = export_csg_mesh(Path(tmp_path))
    except Exception as exc:
        print(f'[SolidModel] export_csg_mesh failed: {exc}')
        return bin_data
    finally:
        if tmp_path and _os.path.exists(tmp_path):
            _os.unlink(tmp_path)

    doc = deserialize_rbxm(bin_data)

    _INJECTABLE = frozenset({
        'PartOperationAsset', 'UnionOperation', 'NegateOperation', 'PartOperation',
    })
    injected = 0
    for inst in doc.roots:
        if inst.class_name in _INJECTABLE:
            inst.properties['MeshData'] = RbxProperty(
                name='MeshData',
                fmt=PropertyFormat.STRING,
                value=csg_bytes,
            )
            # Force Part.Color to white so vertex colors from the OBJ are
            # rendered as-is (Roblox multiplies Part.Color × vertex color).
            inst.properties['Color'] = RbxProperty(
                name='Color',
                fmt=PropertyFormat.COLOR3UINT8,
                value={'R': 255, 'G': 255, 'B': 255},
            )
            injected += 1

    if injected == 0:
        print(
            f'[SolidModel] No injectable root found (roots: {[r.class_name for r in doc.roots]})')
        return bin_data

    print(f'[SolidModel] Injected CSGMDL into {injected} root(s)')
    return write_rbxm(doc)


_session_cache: dict = {}
_session_lock = threading.Lock()

# CDN URL cache for replacement assets
# Avoids a blocking sess.post() on every fts.rbxcdn.com hit for the same
# replacement asset.  Key = (use_val, cookie_key) -> (cdn_url, timestamp).
_cdn_url_cache: dict = {}
_cdn_url_lock = threading.Lock()
_CDN_URL_TTL = 20 * 60  # 20 minutes

# Cache for URL-mode replacement content (GitHub raw files, etc.)
# Key = url -> (content_bytes, timestamp)
_url_content_cache: dict = {}
_url_content_lock = threading.Lock()
_URL_CONTENT_TTL = 10 * 60  # 10 minutes

# Cache for fetched assetId-mode replacement content.
# Key = (use_val, cookie_key) -> (content_bytes, timestamp)
_asset_content_cache: dict = {}
_asset_content_lock = threading.Lock()
_ASSET_CONTENT_TTL = 30 * 60  # 30 minutes


def _get_cached_asset_content(use_val: str, cookie: str | None):
    key = (use_val, cookie or "")
    with _asset_content_lock:
        entry = _asset_content_cache.get(key)
    if entry:
        data, ts = entry
        if time.time() - ts < _ASSET_CONTENT_TTL:
            return data
    return None


def _set_cached_asset_content(use_val: str, cookie: str | None, data: bytes):
    key = (use_val, cookie or "")
    with _asset_content_lock:
        _asset_content_cache[key] = (data, time.time())


def _fetch_asset_content(use_val: str, cookie: str | None) -> bytes | None:
    """Resolve CDN URL for use_val and download the content. Returns None on failure."""
    cached = _get_cached_asset_content(use_val, cookie)
    if cached is not None:
        return cached
    try:
        sess = _get_cached_session(cookie)
        r = sess.post(
            "https://assetdelivery.roblox.com/v2/assets/batch",
            json=[{"assetId": int(use_val), "requestId": "1"}],
            headers={"Content-Type": "application/json", "X-Preview-Bypass": "1"},
            timeout=8,
            verify=False,
        )
        if not r.ok:
            return None
        d = r.json()
        cdn_url = batch_location(d[0]) if isinstance(d, list) and d else ""
        if not cdn_url:
            return None
        _set_cached_cdn_url(use_val, cookie, cdn_url)
        resp = sess.get(cdn_url, timeout=10, verify=False)
        if not resp.ok:
            return None
        data = resp.content
        _set_cached_asset_content(use_val, cookie, data)
        return data
    except Exception as e:
        print(f"[MITM] asset content fetch failed for {use_val}: {e}")
        return None


def _get_cached_url_content(url: str):
    with _url_content_lock:
        entry = _url_content_cache.get(url)
    if entry:
        data, ts = entry
        if time.time() - ts < _URL_CONTENT_TTL:
            return data
    return None


def _set_cached_url_content(url: str, data: bytes):
    with _url_content_lock:
        _url_content_cache[url] = (data, time.time())


def _infer_ctype_from_url(url: str) -> str:
    path = url.split("?")[0]
    ext = path.rsplit(
        ".", 1)[-1].lower() if "." in path.rsplit("/", 1)[-1] else ""
    return {
        "png": "image/png",
        "jpg": "image/jpeg",
        "jpeg": "image/jpeg",
        "gif": "image/gif",
        "webp": "image/webp",
        "ogg": "audio/ogg",
        "mp3": "audio/mpeg",
        "wav": "audio/wav",
        "rbxm": "application/octet-stream",
        "rbxmx": "application/xml",
        "xml": "application/xml",
        "json": "application/json",
    }.get(ext, "application/octet-stream")


def _get_cached_cdn_url(use_val: str, cookie: str | None) -> str | None:
    key = (use_val, cookie or "")
    with _cdn_url_lock:
        entry = _cdn_url_cache.get(key)
    if entry:
        url, ts = entry
        if time.time() - ts < _CDN_URL_TTL:
            return url
    return None


def _set_cached_cdn_url(use_val: str, cookie: str | None, url: str) -> None:
    key = (use_val, cookie or "")
    with _cdn_url_lock:
        _cdn_url_cache[key] = (url, time.time())


def _get_cached_session(cookie: str | None) -> requests.Session:
    """Return a cached Session for *cookie*, building it once per unique value."""
    key = cookie or ""
    with _session_lock:
        if key in _session_cache:
            return _session_cache[key]
    # Build outside the lock so we don't block other threads during network I/O
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
    with _session_lock:
        _session_cache[key] = sess
    return sess


def parse_body(self, content: bytes, encoding: str):
    if encoding == "gzip":
        try:
            content = gzip.decompress(content)
        except OSError:
            pass
    try:
        return json.loads(content)
    except Exception as e:
        print("Failed to parse JSON:", e)
        return None


def rebuild_body(self, data, encoding: str) -> bytes:
    raw = json.dumps(data, separators=(",", ":")).encode()

    if encoding == "gzip":
        return gzip.compress(raw)

    return raw


def _new_session(self, cookie: str | None, xCSRF=False):
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
    # X-CSRF
    if xCSRF:
        try:
            r = sess.post("https://auth.roblox.com/v2/logout", timeout=10)
            token = r.headers.get(
                "x-csrf-token") or r.headers.get("X-CSRF-TOKEN")
            if token:
                sess.headers["X-CSRF-TOKEN"] = token
        except Exception:
            pass
    return sess


def event(self, event):
    if event.type() == QEvent.Resize:

        self._on_column_resized(-1, 0, 0, self.table_view)
        self._on_column_resized(-1, 0, 0, self.loader_table)
        self._on_column_resized(-1, 0, 0, self.preset_tree)

        # debounce so it doesn't rebuild 200 times while dragging
        if not getattr(self, "_preset_relayout_pending", False):
            self._preset_relayout_pending = True

            def run():
                self._preset_relayout_pending = False
                self._relayout_preset_cards()

            QTimer.singleShot(0, run)

    return False


def _split_csv(self, s: str):
    if not s:
        return []
    return [x.strip() for x in s.replace("\n", ",").split(",") if x.strip()]


def request(self, flow):
    url = flow.request.pretty_url
    parsed_url = urlparse(url)
    content_encoding = flow.request.headers.get(
        "Content-Encoding", "").lower()

    if flow.request.headers.get("X-Preview-Bypass") == "1":
        return

    if parsed_url.hostname == "assetdelivery.roblox.com":

        raw_content = flow.request.raw_content
        if raw_content:
            data = self.parse_body(raw_content, content_encoding)
            if isinstance(data, list):

                modified = False

                for entry in data:
                    if not isinstance(entry, dict):
                        continue
                    if "assetId" not in entry:
                        continue

                    # Strip CPL from Image entries so the server returns a PNG URL
                    if entry.get("assetType") == "Image" and "contentRepresentationPriorityList" in entry:
                        del entry["contentRepresentationPriorityList"]
                        modified = True

                    original_id = entry["assetId"]

                    _rules = getattr(self, "_loader_index", {}
                                     ).get(str(original_id))
                    if not _rules:
                        asset_type_str = entry.get("assetType", "").lower()
                        _rules = getattr(self, "_type_loader_index", {}).get(
                            asset_type_str)
                    if _rules:
                        mode, use_val, _ = _rules[0]
                        if mode == "assetId" and isnumeric(use_val):
                            pass  # handled in CDN response()
                        elif mode == "inline":
                            # Pre-register SolidModel OBJ injection by requestId so
                            # response() can map CDN URL -> obj_bytes without relying
                            # on assetTypeId being present in the batch response.
                            is_sm = (
                                entry.get(
                                    "assetType", "").lower() == "solidmodel"
                                or entry.get("assetTypeId") == 39
                            )
                            req_id = entry.get("requestId")
                            if is_sm and req_id:
                                _sm_obj_bytes_batch = None
                                if _looks_like_obj(use_val):
                                    _sm_obj_bytes_batch = use_val
                                elif _looks_like_roblox_mesh(use_val):
                                    try:
                                        _sm_obj_bytes_batch = _roblox_mesh_to_obj_bytes(
                                            use_val)
                                        print(
                                            f'[SolidModel] .mesh -> OBJ (batch) for requestId {req_id}')
                                    except Exception as _exc:
                                        print(
                                            f'[SolidModel] .mesh->OBJ (batch) failed: {_exc}')
                                if _sm_obj_bytes_batch is not None:
                                    if not hasattr(self, '_sm_reqid_pending'):
                                        self._sm_reqid_pending = {}
                                    self._sm_reqid_pending[req_id] = _sm_obj_bytes_batch

                if modified:
                    flow.request.raw_content = self.rebuild_body(
                        data, content_encoding)
                    flow.request.headers["Content-Length"] = str(
                        len(flow.request.raw_content))

    if "fts.rbxcdn.com" == parsed_url.hostname:
        req_base = url.split("?")[0]
        # Fast path: use reverse index if available (built/updated in response()),
        # otherwise fall back to linear scan.
        url_index = getattr(self, "_cache_url_index", None)
        if url_index is not None:
            candidates = [url_index.get(req_base)]
            candidates = [c for c in candidates if c is not None]
        else:
            candidates = [
                asset_id for asset_id, info in self.cache_logs.items()
                if isinstance(info, dict) and info.get("location", "").split("?")[0] == req_base
            ]

        for asset_id in candidates:
            info = self.cache_logs.get(asset_id)
            if not isinstance(info, dict):
                continue
            _rules = getattr(self, "_loader_index", {}).get(str(asset_id))
            if not _rules:
                asset_type_id = info.get("assetTypeId")
                if asset_type_id is not None:
                    _type_id_to_name = {at[0]: at[1].lower()
                                        for at in ASSET_TYPES}
                    type_name = _type_id_to_name.get(asset_type_id, "")
                    if type_name:
                        _rules = getattr(
                            self, "_type_loader_index", {}).get(type_name)
            if _rules:
                mode, use_val, use_ctype = _rules[0]
                if mode == "assetId" and isnumeric(use_val):
                    cookie = get_roblosecurity()
                    content = _fetch_asset_content(use_val, cookie)
                    if content:
                        flow.response = _make_response(
                            200, content,
                            {"Content-Type": "application/octet-stream",
                             "Content-Length": str(len(content))}
                        )
                        print(f"[replace] {asset_id} -> asset {use_val} ({len(content):,} B)")

                elif mode == "url" and use_val:
                    content = _get_cached_url_content(use_val)
                    if content is None:
                        # Fetch in background; first request may miss but subsequent ones hit
                        def _bg_fetch(u=use_val):
                            try:
                                resp = requests.get(
                                    u, timeout=10, verify=False)
                                if resp.ok:
                                    _set_cached_url_content(u, resp.content)
                            except Exception as e:
                                print(f"[MITM] URL fetch failed for {u}: {e}")
                        threading.Thread(target=_bg_fetch, daemon=True).start()
                    else:
                        ctype = _infer_ctype_from_url(use_val)
                        flow.response = _make_response(
                            200,
                            content,
                            {"Content-Type": ctype,
                                "Content-Length": str(len(content))}
                        )
                        print(f"[replace] {asset_id} -> {use_val}")

                else:
                    if use_ctype is None:
                        use_ctype = "application/octet-stream"
                    use_val = strip_cache_header(use_val)

                    # SolidModel OBJ injection: let the CDN request through and
                    # intercept the response to inject the OBJ geometry.
                    asset_type_id = info.get(
                        "assetTypeId") if isinstance(info, dict) else None
                    _sm_obj_bytes = None
                    if asset_type_id == 39:
                        if _looks_like_obj(use_val):
                            _sm_obj_bytes = use_val
                        elif _looks_like_roblox_mesh(use_val):
                            try:
                                _sm_obj_bytes = _roblox_mesh_to_obj_bytes(
                                    use_val)
                                print(
                                    f'[SolidModel] .mesh -> OBJ for asset {asset_id}')
                            except Exception as _exc:
                                print(
                                    f'[SolidModel] .mesh->OBJ failed: {_exc}')
                    if _sm_obj_bytes is not None:
                        if not hasattr(self, '_solidmodel_pending'):
                            self._solidmodel_pending = {}
                        self._solidmodel_pending[req_base] = _sm_obj_bytes
                        print(
                            f"[replace] {asset_id} -> solidmodel OBJ injection")
                        return  # Let CDN request go through; handle in response()

                    # OBJ -> V2.00 mesh auto-conversion for Mesh/MeshPart assets
                    if asset_type_id in (4, 40) and _looks_like_obj(use_val):
                        try:
                            from tools.solidmodel_converter.obj_to_mesh import parse_obj_for_mesh, export_v2_mesh
                            obj_text = use_val.decode(
                                'utf-8', errors='replace')
                            verts, colors, faces = parse_obj_for_mesh(obj_text)
                            if verts and faces:
                                use_val = export_v2_mesh(verts, colors, faces)
                                use_ctype = 'application/octet-stream'
                                print(
                                    f'[Mesh] Auto-converted OBJ -> V2.00 mesh for asset {asset_id}')
                        except Exception as exc:
                            print(f'[Mesh] OBJ->mesh conversion failed: {exc}')

                    print(
                        f"[replace] {asset_id} -> {use_ctype} ({len(use_val):,} B)")
                    flow.response = _make_response(
                        200,
                        use_val,
                        {"Content-Type": use_ctype,
                            "Content-Length": str(len(use_val))}
                    )


def response(self, flow):
    if flow.request.headers.get("X-Preview-Bypass") == "1":
        return

    url = flow.request.pretty_url
    parsed_url = urlparse(url)
    req_content_encoding = flow.request.headers.get(
        "Content-Encoding", ""
    ).lower()
    content_encoding = flow.response.headers.get(
        "Content-Encoding", ""
    ).lower()

    if "assetdelivery.roblox.com" == parsed_url.hostname:
        if parsed_url.path.endswith("/assets/batch"):
            body_req_json = self.parse_body(
                flow.request.content, req_content_encoding)
            body_res_json = self.parse_body(
                flow.response.content, content_encoding)
            if not body_res_json or not body_req_json:
                return
            if not isinstance(body_req_json, list) or not isinstance(body_res_json, list):
                return

            # Resolve SolidModel OBJ injections tracked in request() by requestId.
            # Uses the full unfiltered response so no entries are missed.
            _sm_req = getattr(self, '_sm_reqid_pending', {})
            if _sm_req:
                for _item in body_res_json:
                    _req_id = _item.get("requestId")
                    if _req_id and _req_id in _sm_req:
                        _location = batch_location(_item)
                        if _location:
                            if not hasattr(self, '_solidmodel_pending'):
                                self._solidmodel_pending = {}
                            self._solidmodel_pending[_location.split(
                                "?")[0]] = _sm_req.pop(_req_id)
                            print(
                                f'[SolidModel] Pre-registered injection -> {_location.split("?")[0]}')

            request_ids_to_remove = []

            for i, req1 in enumerate(body_req_json):
                if "contentRepresentationPriorityList" in req1:
                    for j, req2 in enumerate(body_req_json):
                        if i != j and req2.get("assetId") == req1.get("assetId") and "contentRepresentationPriorityList" not in req2:
                            request_ids_to_remove.append(req1["requestId"])
                            request_ids_to_remove.append(req2["requestId"])
                            asset_id = req2.get("assetId")

                            res_entry = next(
                                (r for r in body_res_json if r.get(
                                    "requestId") == req2["requestId"]), None
                            )

                            if res_entry and "assetTypeId" in res_entry and batch_location(res_entry):
                                location_url = batch_location(res_entry)
                                asset_type_id = res_entry["assetTypeId"]

                                if asset_id not in self.cache_logs:
                                    self.cache_logs[asset_id] = {
                                        "location": location_url,
                                        "assetTypeId": asset_type_id
                                    }
                                    # Keep reverse index up to date
                                    if not hasattr(self, "_cache_url_index"):
                                        self._cache_url_index = {}
                                    self._cache_url_index[location_url.split("?")[
                                        0]] = asset_id

                                    threading.Thread(
                                        target=self.fetch_and_process, args=(
                                            location_url, asset_id), daemon=True
                                    ).start()

            body_req_json = [
                r for r in body_req_json if r.get("requestId") not in request_ids_to_remove
            ]
            body_res_json = [
                r for r in body_res_json if r.get("requestId") not in request_ids_to_remove
            ]
            # Build a requestId -> response-entry lookup so we match by ID,
            # not by array index.  Roblox's batch API does not guarantee that
            # the response array preserves the same order as the request, so
            # index-based matching produced wrong CDN-URL->assetId mappings
            # (wrong replacement rule fires -> incompatible content -> load fail).
            # If requestId is absent from the request item, fall back to
            # index-based matching to preserve compatibility.
            res_by_req_id = {
                r.get("requestId"): r
                for r in body_res_json
                if r.get("requestId") is not None
            }

            for req_idx, item in enumerate(body_req_json):
                if "assetId" not in item:
                    continue

                ID = item["assetId"]

                if ID in self.cache_logs:
                    continue

                req_id = item.get("requestId")
                if req_id is not None:
                    res_item = res_by_req_id.get(req_id)
                elif req_idx < len(body_res_json):
                    res_item = body_res_json[req_idx]
                else:
                    res_item = None

                if res_item is None:
                    continue

                # Safely get fields
                location = batch_location(res_item)
                asset_type = res_item.get("assetTypeId")

                if location:
                    self.cache_logs[ID] = {"location": location}
                    if asset_type is not None:
                        self.cache_logs[ID]["assetTypeId"] = asset_type
                    # Keep reverse index up to date
                    if not hasattr(self, "_cache_url_index"):
                        self._cache_url_index = {}
                    self._cache_url_index[location.split("?")[0]] = ID
                    if asset_type == 63:
                        self._prefetch_texturepack_xml(ID)

    if "fts.rbxcdn.com" == parsed_url.hostname:
        req_base = url.split("?")[0]

        # SolidModel OBJ injection: intercept CDN binary and inject our geometry
        pending_sm = getattr(self, '_solidmodel_pending', {})
        if req_base in pending_sm:
            obj_bytes = pending_sm.pop(req_base)
            body = getattr(flow.response, 'content', None)
            if flow.response and body:
                try:
                    modified = _inject_obj_bytes_into_solidmodel(
                        body, obj_bytes)
                    # Use .content (works for both MockResponse and mitmproxy)
                    flow.response.content = modified
                    flow.response.headers['Content-Type'] = 'application/octet-stream'
                    flow.response.headers['Content-Length'] = str(
                        len(modified))
                    # Strip Content-Encoding — MockResponse.content getter already
                    # decompresses and removes it; mitmproxy needs explicit pop()
                    try:
                        flow.response.headers.pop('Content-Encoding', None)
                    except AttributeError:
                        pass
                    print(
                        f'[SolidModel] Injected OBJ into CDN response ({len(modified)} bytes)')
                except Exception as exc:
                    print(f'[SolidModel] Injection failed: {exc}')
            return  # Skip normal asset processing for this URL

        url_index = getattr(self, "_cache_url_index", None)
        if url_index is not None:
            asset_id = url_index.get(req_base)
            if asset_id is not None:
                # assetId-mode replacement: fetch replacement content and swap in
                _rules = getattr(self, "_loader_index", {}).get(str(asset_id))
                if not _rules:
                    _type_id = self.cache_logs.get(asset_id, {}).get("assetTypeId")
                    if _type_id is not None:
                        _type_name = {at[0]: at[1].lower() for at in ASSET_TYPES}.get(_type_id, "")
                        if _type_name:
                            _rules = getattr(self, "_type_loader_index", {}).get(_type_name)
                if _rules:
                    _mode, _use_val, _ = _rules[0]
                    if _mode == "assetId" and isnumeric(_use_val):
                        _content = _fetch_asset_content(_use_val, get_roblosecurity())
                        if _content:
                            flow.response.content = _content
                            print(f"[replace] {asset_id} -> asset {_use_val} ({len(_content):,} B)")
                info = self.cache_logs.get(asset_id, {})
                if isinstance(info, dict) and not has_cache_data(info):
                    self.process_asset_row(
                        flow.response.content,
                        flow.response.status_code,
                        parsed_url,
                        asset_id,
                    )
        else:
            for asset_id, info in self.cache_logs.items():
                if not isinstance(info, dict):
                    continue
                location = info.get("location")
                if not location:
                    continue
                if has_cache_data(info):
                    continue
                cached_base = location.split("?")[0]
                if cached_base == req_base:
                    # assetId-mode replacement
                    _rules = getattr(self, "_loader_index", {}).get(str(asset_id))
                    if _rules:
                        _mode, _use_val, _ = _rules[0]
                        if _mode == "assetId" and isnumeric(_use_val):
                            _content = _fetch_asset_content(_use_val, get_roblosecurity())
                            if _content:
                                flow.response.content = _content
                                print(f"[replace] {asset_id} -> asset {_use_val} ({len(_content):,} B)")
                    self.process_asset_row(
                        flow.response.content,
                        flow.response.status_code,
                        parsed_url,
                        asset_id,
                    )
                    break
