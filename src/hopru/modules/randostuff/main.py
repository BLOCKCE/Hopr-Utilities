import os
import json
import threading
import uuid
import base64
import re
from urllib.parse import urlparse

import requests

from PySide6.QtCore import QObject, Qt, Signal
from PySide6.QtWidgets import QWidget, QPushButton, QLabel, QCheckBox, QLineEdit, QFileDialog
import ctypes
import ctypes.wintypes as wintypes

try:
    import win32crypt  # type: ignore
except Exception:
    win32crypt = None


def _get_roblosecurity():
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


def _detect_extension(data: bytes) -> str:
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return ".png"
    if data[:3] == b"\xff\xd8\xff":
        return ".jpg"
    if data[:6] in (b"GIF87a", b"GIF89a"):
        return ".gif"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return ".webp"
    if data[:4] == b"OggS":
        return ".ogg"
    if data[:3] == b"ID3" or (len(data) >= 2 and data[0] == 0xFF and data[1] in (0xFB, 0xF3, 0xF2)):
        return ".mp3"
    if data[:4] == b"fLaC":
        return ".flac"
    if data[:4] == b"RIFF" and data[8:12] == b"WAVE":
        return ".wav"
    if data[:8] == b"version " or data[:7] == b"version":
        return ".mesh"
    if data[:9] == b"<roblox!":
        return ".rbxm"
    if data[:7] == b"<roblox" or data[:5] == b"<?xml":
        return ".rbxmx"
    return ".bin"


def _make_session(cookie):
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
    return sess


class _Invoker(QObject):
    call = Signal(object)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.call.connect(self._run, Qt.QueuedConnection)

    def _run(self, fn):
        try:
            fn()
        except Exception as e:
            print(f"[randostuff] invoker error: {e}")


class Main(QObject):
    def __init__(self, tab_widget):
        super().__init__(tab_widget)
        self.tab_widget = tab_widget
        self._invoker = _Invoker(self)

        self._last_place_id = None
        self._last_access_code = None
        self._last_session_id = None
        self._doing_rejoin = False
        self._awaiting_rejoin_response = False
        self._lock = threading.Lock()

        self._multi_stop = threading.Event()
        self._multi_thread = None

        self._btn = tab_widget.findChild(QPushButton, "rejoinReserved")
        self._lbl_place = tab_widget.findChild(QLabel, "placeID")
        self._lbl_access = tab_widget.findChild(QLabel, "accessCode")
        self._multi_chk = tab_widget.findChild(QCheckBox, "MultiInstance")
        self._asset_id_edit = tab_widget.findChild(
            QLineEdit, "assetIdLineEdit")
        self._place_id_edit = tab_widget.findChild(
            QLineEdit, "placeIdLineEdit")
        self._download_btn = tab_widget.findChild(QPushButton, "download")

        if self._btn:
            self._btn.clicked.connect(self._on_rejoin_clicked)
        if self._multi_chk:
            self._multi_chk.toggled.connect(self._on_multi_instance_toggled)
        if self._download_btn:
            self._download_btn.clicked.connect(self._on_download_clicked)

    def _on_download_clicked(self):
        asset_id_text = self._asset_id_edit.text().strip() if self._asset_id_edit else ""
        place_id_text = self._place_id_edit.text().strip() if self._place_id_edit else ""

        try:
            asset_id = int(asset_id_text)
        except ValueError:
            print("[randostuff] Invalid asset ID — enter a numeric asset ID.")
            return

        try:
            place_id = int(place_id_text)
        except ValueError:
            print("[randostuff] Invalid place ID — enter a numeric place ID.")
            return

        threading.Thread(
            target=self._download_private_asset,
            args=(asset_id, place_id),
            daemon=True,
        ).start()

    def _download_private_asset(self, asset_id, place_id):
        try:
            cookie = _get_roblosecurity()
            sess = _make_session(cookie)

            extra_headers = {
                "X-Preview-Bypass": "1",
                "User-Agent": "Roblox/WinInetRobloxApp",
                "Roblox-Play-Session-Id": str(uuid.uuid4()),
                "Roblox-Game-Id": str(uuid.uuid4()),
            }

            extra_headers["Roblox-Place-Id"] = str(place_id)
            try:
                uid_resp = sess.get(
                    f"https://apis.roblox.com/universes/v1/places/{place_id}/universe",
                    timeout=8,
                    verify=False,
                )
                if uid_resp.ok:
                    uid = uid_resp.json().get("universeId")
                    if uid:
                        extra_headers["Roblox-Universe-Id"] = str(uid)
            except Exception as e:
                print(
                    f"[randostuff] Universe ID lookup failed for place {place_id}: {e}")

            batch_resp = sess.post(
                "https://assetdelivery.roblox.com/v1/assets/batch",
                json=[{"assetId": asset_id, "requestId": "0", "assetTypeId": 0}],
                timeout=15,
                verify=False,
                headers=extra_headers,
            )
            if not batch_resp.ok:
                print(
                    f"[randostuff] Batch request for asset {asset_id} returned HTTP {batch_resp.status_code}")
                return
            batch_data = batch_resp.json()
            if not isinstance(batch_data, list) or not batch_data or "location" not in batch_data[0]:
                print(
                    f"[randostuff] No location in batch response for asset {asset_id}")
                return

            cdn_resp = sess.get(
                batch_data[0]["location"],
                timeout=15,
                verify=False,
                headers=extra_headers,
            )
            if not cdn_resp.ok:
                print(
                    f"[randostuff] CDN fetch for asset {asset_id} returned HTTP {cdn_resp.status_code}")
                return

            data = cdn_resp.content

            def _save(d=data, aid=asset_id):
                ext = _detect_extension(d)
                path, _ = QFileDialog.getSaveFileName(
                    self.tab_widget,
                    f"Save Asset {aid}",
                    f"asset_{aid}{ext}",
                    "All Files (*)",
                )
                if path:
                    with open(path, "wb") as f:
                        f.write(d)
                    print(f"[randostuff] Saved asset {aid} to {path}")

            self._invoker.call.emit(_save)

        except Exception as e:
            print(f"[randostuff] Failed to download asset {asset_id}: {e}")

    def _on_rejoin_clicked(self):
        with self._lock:
            if self._last_place_id is None or self._last_access_code is None:
                print("[randostuff] No reserved server logged yet — join one first.")
                return
            self._doing_rejoin = True

        print(
            f"[randostuff] Rejoin triggered — placeId={self._last_place_id}, accessCode={self._last_access_code}")
        os.startfile("roblox://placeId=1818")

    def _update_labels(self, place_id, access_code):
        def _do():
            if self._lbl_place:
                self._lbl_place.setText(f"Last placeID = {place_id}")
            if self._lbl_access:
                self._lbl_access.setText(f"Last accessCode = {access_code}")
        self._invoker.call.emit(_do)

    # Multi-instance

    def _on_multi_instance_toggled(self, checked):
        if checked:
            self._multi_stop.clear()
            self._multi_thread = threading.Thread(
                target=self._multi_instance_loop, daemon=True)
            self._multi_thread.start()
            print("[multiinstance] Enabled — watching for ROBLOX_singletonEvent")
        else:
            self._multi_stop.set()
            print("[multiinstance] Disabled")

    def _multi_instance_loop(self):
        while not self._multi_stop.wait(0.5):
            try:
                self._close_singleton_event()
            except Exception as e:
                print(f"[multiinstance] Error: {e}")

    def _close_singleton_event(self):
        ntdll = ctypes.windll.ntdll
        kernel32 = ctypes.windll.kernel32

        kernel32.OpenEventW.restype = wintypes.HANDLE
        kernel32.OpenProcess.restype = wintypes.HANDLE
        kernel32.GetCurrentProcess.restype = wintypes.HANDLE
        kernel32.DuplicateHandle.restype = wintypes.BOOL
        kernel32.CloseHandle.restype = wintypes.BOOL
        kernelbase = ctypes.windll.kernelbase
        kernelbase.CompareObjectHandles.restype = wintypes.BOOL
        kernel32.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
        kernel32.Process32FirstW.restype = wintypes.BOOL
        kernel32.Process32NextW.restype = wintypes.BOOL
        ntdll.NtQueryInformationProcess.restype = ctypes.c_ulong

        STATUS_INFO_LENGTH_MISMATCH = 0xC0000004
        STATUS_SUCCESS = 0x00000000
        TH32CS_SNAPPROCESS = 0x00000002
        SYNCHRONIZE = 0x00100000
        PROCESS_DUP_HANDLE = 0x0040
        PROCESS_QUERY_INFORMATION = 0x0400
        DUPLICATE_CLOSE_SOURCE = 0x00000001
        DUPLICATE_SAME_ACCESS = 0x00000002
        ProcessHandleInformation = 51

        class PROCESSENTRY32W(ctypes.Structure):
            _fields_ = [
                ("dwSize",             wintypes.DWORD),
                ("cntUsage",           wintypes.DWORD),
                ("th32ProcessID",      wintypes.DWORD),
                ("th32DefaultHeapID",  ctypes.c_size_t),
                ("th32ModuleID",       wintypes.DWORD),
                ("cntThreads",         wintypes.DWORD),
                ("th32ParentProcessID", wintypes.DWORD),
                ("pcPriClassBase",     ctypes.c_long),
                ("dwFlags",            wintypes.DWORD),
                ("szExeFile",          ctypes.c_wchar * 260),
            ]

        # PROCESS_HANDLE_TABLE_ENTRY_INFO
        class _ProcHandleEntry(ctypes.Structure):
            _fields_ = [
                ("HandleValue",      ctypes.c_size_t),
                ("HandleCount",      ctypes.c_size_t),
                ("PointerCount",     ctypes.c_size_t),
                ("GrantedAccess",    wintypes.ULONG),
                ("ObjectTypeIndex",  wintypes.ULONG),
                ("HandleAttributes", wintypes.ULONG),
                ("Reserved",         wintypes.ULONG),
            ]

        proc_entry_size = ctypes.sizeof(_ProcHandleEntry)
        proc_header_size = ctypes.sizeof(
            ctypes.c_size_t) * 2  # NumberOfHandles + Reserved

        # Step 1: find all Roblox PIDs
        snap = kernel32.CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0)
        if not snap:
            return

        roblox_pids = []
        try:
            pe = PROCESSENTRY32W()
            pe.dwSize = ctypes.sizeof(PROCESSENTRY32W)
            if kernel32.Process32FirstW(snap, ctypes.byref(pe)):
                while True:
                    if "robloxplayerbeta" in pe.szExeFile.lower():
                        roblox_pids.append(pe.th32ProcessID)
                    if not kernel32.Process32NextW(snap, ctypes.byref(pe)):
                        break
        finally:
            kernel32.CloseHandle(snap)

        if not roblox_pids:
            return

        # Step 2: open our own copy of the event for comparison
        our_handle = kernel32.OpenEventW(
            SYNCHRONIZE, False, "ROBLOX_singletonEvent")
        if not our_handle:
            return

        current_proc = ctypes.c_void_p(-1)  # GetCurrentProcess() pseudo-handle

        try:
            for pid in roblox_pids:
                proc = kernel32.OpenProcess(
                    PROCESS_DUP_HANDLE | PROCESS_QUERY_INFORMATION, False, pid)
                if not proc:
                    continue
                try:
                    # Query the handle list for this process only
                    size = 4096
                    while True:
                        buf = (ctypes.c_ubyte * size)()
                        ret_len = wintypes.ULONG(0)
                        status = ntdll.NtQueryInformationProcess(
                            proc, ProcessHandleInformation,
                            buf, size, ctypes.byref(ret_len))
                        if status == STATUS_INFO_LENGTH_MISMATCH:
                            size = ret_len.value + 4096
                            continue
                        break

                    if status != STATUS_SUCCESS:
                        continue

                    buf_bytes = bytes(buf)
                    num = ctypes.c_size_t.from_buffer_copy(
                        buf_bytes[:ctypes.sizeof(ctypes.c_size_t)]).value

                    offset = proc_header_size
                    for _ in range(num):
                        e = _ProcHandleEntry.from_buffer_copy(
                            buf_bytes[offset:offset + proc_entry_size])
                        offset += proc_entry_size

                        # Duplicate the handle to our process for comparison
                        dup = wintypes.HANDLE()
                        ok = kernel32.DuplicateHandle(
                            proc, wintypes.HANDLE(e.HandleValue),
                            current_proc, ctypes.byref(dup),
                            0, False, DUPLICATE_SAME_ACCESS)
                        if not ok:
                            continue

                        is_same = kernelbase.CompareObjectHandles(
                            our_handle, dup)
                        kernel32.CloseHandle(dup)

                        if not is_same:
                            continue

                        # Found it — close the handle inside Roblox's process
                        dup2 = wintypes.HANDLE()
                        kernel32.DuplicateHandle(
                            proc, wintypes.HANDLE(e.HandleValue),
                            current_proc, ctypes.byref(dup2),
                            0, False, DUPLICATE_CLOSE_SOURCE)
                        kernel32.CloseHandle(dup2)
                        print(
                            f"[multiinstance] Closed ROBLOX_singletonEvent in PID {pid}")
                        break
                finally:
                    kernel32.CloseHandle(proc)
        finally:
            kernel32.CloseHandle(our_handle)

    # Proxy interceptor

    _WANTED_ENDPOINTS = (
        "/v1/join-game",
        "/v1/join-play-together-game",
        "/v1/join-game-instance",
    )

    def request(self, flow):
        url = flow.request.pretty_url
        if "gamejoin.roblox.com" not in url:
            return

        parsed = urlparse(url)

        # Log placeId + accessCode + session ID whenever Roblox joins a reserved server
        if parsed.path == "/v1/join-reserved-game":
            try:
                body = json.loads(flow.request.content)
                place_id = body.get("placeId")
                access_code = body.get("accessCode")
                session_id = flow.request.headers.get("Roblox-Session-Id", "")
                if place_id is not None and access_code is not None:
                    with self._lock:
                        self._last_place_id = place_id
                        self._last_access_code = access_code
                        self._last_session_id = session_id or None
                    print(
                        f"[randostuff] Logged reserved server — placeId={place_id}, accessCode={access_code}, Roblox-Session-Id={session_id or '(none)'}")
                    self._update_labels(place_id, access_code)
            except Exception as e:
                print(
                    f"[randostuff] Failed to parse join-reserved-game body: {e}")
            return

        # Intercept normal join endpoints and rewrite to join-reserved-game
        if parsed.path not in self._WANTED_ENDPOINTS:
            return

        with self._lock:
            doing = self._doing_rejoin
            place_id = self._last_place_id
            access_code = self._last_access_code
            session_id = self._last_session_id
            if doing:
                self._doing_rejoin = False

        if not doing:
            return

        if place_id is None or access_code is None:
            print(
                "[randostuff] Rejoin flag set but no reserved server stored — aborting.")
            return

        new_payload = {
            "placeId": place_id,
            "accessCode": access_code,
            "isTeleport": True,
            "isImmersiveAdsTeleport": False,
        }

        flow.request.url = "https://gamejoin.roblox.com/v1/join-reserved-game"
        flow.request.raw_content = json.dumps(new_payload).encode("utf-8")
        if session_id:
            flow.request.headers["Roblox-Session-Id"] = session_id

        print(
            f"[randostuff] Rejoin request -> POST gamejoin.roblox.com/v1/join-reserved-game")
        print(f"[randostuff] Rejoin request body: {json.dumps(new_payload)}")
        print(
            f"[randostuff] Rejoin request Roblox-Session-Id: {session_id or '(none)'}")
        with self._lock:
            self._awaiting_rejoin_response = True

    def response(self, flow):
        if "gamejoin.roblox.com" not in flow.request.pretty_url:
            return

        with self._lock:
            waiting = self._awaiting_rejoin_response
            if waiting:
                self._awaiting_rejoin_response = False

        if not waiting:
            return

        resp = flow.response
        if resp is None:
            print("[randostuff] Rejoin response: (none)")
            return

        print(f"[randostuff] Rejoin response status: {resp.status_code}")
        try:
            print(
                f"[randostuff] Rejoin response body: {resp.content.decode('utf-8', errors='replace')}")
        except Exception as e:
            print(f"[randostuff] Could not read rejoin response body: {e}")
