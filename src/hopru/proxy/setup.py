"""Proxy environment setup: hosts file redirection and Roblox cert injection."""

import os
import glob
import string
import threading
import winreg
from pathlib import Path

try:
    import pythoncom
    import win32com.client
    _WMI_AVAILABLE = True
except ImportError:
    _WMI_AVAILABLE = False

try:
    from mitmproxy import certs as mitm_certs
except Exception:
    mitm_certs = None

HOME = os.environ.get("USERPROFILE", os.path.expanduser("~"))
MITM_CA_PEM = os.path.join(HOME, ".mitmproxy", "mitmproxy-ca.pem")
MITM_CA_CERT = os.path.join(HOME, ".mitmproxy", "mitmproxy-ca-cert.pem")
HOSTS_FILE = r"C:\Windows\System32\drivers\etc\hosts"
HOSTS_MARKER = "# HoprU-proxy"
TARGET_DOMAINS = [
    "assetdelivery.roblox.com",
    "fts.rbxcdn.com",
    "gamejoin.roblox.com",
]
ROBLOX_PATHS = {
    "Roblox":    os.path.join(HOME, "AppData", "Local", "Roblox",    "Versions"),
    "Bloxstrap": os.path.join(HOME, "AppData", "Local", "Bloxstrap", "Versions"),
    "Fishstrap": os.path.join(HOME, "AppData", "Local", "Fishstrap", "Versions"),
    "Voidstrap": os.path.join(HOME, "AppData", "Local", "Voidstrap", "RblxVersions"),
    "Plexity":   os.path.join(HOME, "AppData", "Local", "Plexity"),
}


# Hosts file

def _add_hosts():
    text = Path(HOSTS_FILE).read_text(encoding="utf-8", errors="replace")
    lines = [l for l in text.splitlines() if HOSTS_MARKER not in l]
    for d in TARGET_DOMAINS:
        lines.append(f"127.0.0.1 {d} {HOSTS_MARKER}")
    Path(HOSTS_FILE).write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"[proxy] hosts: redirected {', '.join(TARGET_DOMAINS)}")


def _remove_hosts():
    try:
        text = Path(HOSTS_FILE).read_text(encoding="utf-8", errors="replace")
        lines = [l for l in text.splitlines() if HOSTS_MARKER not in l]
        Path(HOSTS_FILE).write_text("\n".join(lines) + "\n", encoding="utf-8")
        print("[proxy] hosts: cleaned up")
    except Exception as e:
        print(f"[proxy] hosts cleanup error: {e}")


# Roblox cacert.pem injection

def ensure_mitm_cert() -> bool:
    """Generate mitmproxy CA if it doesn't exist yet."""
    confdir = Path.home() / ".mitmproxy"
    confdir.mkdir(exist_ok=True)
    if mitm_certs is not None:
        try:
            mitm_certs.CertStore.from_store(str(confdir), "mitmproxy", 2048)
        except Exception as e:
            print(f"[proxy] CertStore.from_store failed: {e}")
    return (confdir / "mitmproxy-ca-cert.pem").exists()


# Discovery helpers

def _scan_for_player_dirs(base_dir: str, max_depth: int) -> list:
    """Return list of dirs that directly contain RobloxPlayerBeta.exe, up to max_depth levels."""
    found = []
    if not os.path.isdir(base_dir):
        return found

    def _walk(path, depth):
        if depth > max_depth:
            return
        try:
            for entry in os.scandir(path):
                try:
                    if entry.is_file(follow_symlinks=False):
                        if entry.name.lower() == "robloxplayerbeta.exe":
                            found.append(path)
                    elif entry.is_dir(follow_symlinks=False):
                        _walk(entry.path, depth + 1)
                except OSError:
                    pass
        except PermissionError:
            pass

    _walk(base_dir, 0)
    return found


def _find_via_launcher_registry() -> list:
    """
    Read HKCU\\Software\\Classes\\roblox-player\\shell\\open\\command (Default),
    extract the launcher exe path, then scan from that directory (depth 3) for
    RobloxPlayerBeta.exe.
    """
    try:
        key = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Classes\roblox-player\shell\open\command",
        )
        value, _ = winreg.QueryValueEx(key, "")
        winreg.CloseKey(key)
    except Exception:
        return []

    value = value.strip()
    if value.startswith('"'):
        end = value.index('"', 1)
        exe_path = value[1:end]
    else:
        exe_path = value.split()[0]

    if not os.path.isfile(exe_path):
        return []

    launcher_dir = os.path.dirname(exe_path)
    print(f"[cert] launcher registry -> scanning {launcher_dir}")
    return _scan_for_player_dirs(launcher_dir, max_depth=3)


def _find_via_xbox_games() -> list:
    """Scan C:\\XboxGames\\Roblox up to 2 layers deep for RobloxPlayerBeta.exe."""
    return _scan_for_player_dirs(r"C:\XboxGames\Roblox", max_depth=2)


def _find_via_extra_paths() -> list:
    """
    Scan C:\\Program Files, C:\\Program Files (x86), C:\\Fishstrap, and the root
    of every non-C drive (up to 3 levels deep) for RobloxPlayerBeta.exe.
    """
    bases = [
        r"C:\Program Files",
        r"C:\Program Files (x86)",
        r"C:\Fishstrap",
    ]
    for letter in string.ascii_uppercase:
        if letter == "C":
            continue
        drive = f"{letter}:\\"
        if os.path.isdir(drive):
            bases.append(drive)

    found = []
    for base in bases:
        found.extend(_scan_for_player_dirs(base, max_depth=3))
    return found


def _find_via_player_path_registry() -> list:
    """
    Search HKCU\\Software one layer deep.  For each sub-key that has a REG_SZ
    value named 'PlayerPath', treat the value as a folder (or exe whose parent
    is the folder).  If the folder directly contains RobloxPlayerBeta.exe use
    it; otherwise scan one layer inside it.
    """
    found = []
    try:
        software_key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software")
    except Exception:
        return found

    i = 0
    while True:
        try:
            subkey_name = winreg.EnumKey(software_key, i)
            i += 1
        except OSError:
            break
        try:
            subkey = winreg.OpenKey(software_key, subkey_name)
        except Exception:
            continue
        try:
            val, typ = winreg.QueryValueEx(subkey, "PlayerPath")
            if typ == winreg.REG_SZ and isinstance(val, str):
                candidate = val.strip()
                if candidate.lower().endswith(".exe"):
                    candidate = os.path.dirname(candidate)
                if os.path.isdir(candidate):
                    if os.path.isfile(os.path.join(candidate, "RobloxPlayerBeta.exe")):
                        print(f"[cert] PlayerPath registry -> {candidate}")
                        found.append(candidate)
                    else:
                        extra = _scan_for_player_dirs(candidate, max_depth=1)
                        if extra:
                            print(
                                f"[cert] PlayerPath registry (1-deep) -> {extra}")
                        found.extend(extra)
        except FileNotFoundError:
            pass
        except Exception:
            pass
        finally:
            winreg.CloseKey(subkey)

    winreg.CloseKey(software_key)
    return found


def _inject_cert_into_dirs(our_cert: str, dirs: list, label: str):
    """Inject our_cert into ssl/cacert.pem inside each directory in dirs."""
    for d in dirs:
        cacert_path = os.path.join(d, "ssl", "cacert.pem")
        if not os.path.isfile(cacert_path):
            continue
        try:
            content = Path(cacert_path).read_text(encoding="utf-8")
            if our_cert in content:
                print(
                    f"[cert] already present, skipping ({label}) -> ...{cacert_path[-50:]}")
                continue
            content = content.rstrip() + "\n\n" + our_cert + "\n"
            Path(cacert_path).write_text(content, encoding="utf-8")
            print(f"[cert] injected ({label}) -> ...{cacert_path[-50:]}")
        except Exception as e:
            print(f"[cert] inject error ({label}): {e}")


def install_cert() -> bool:
    if not ensure_mitm_cert():
        return False
    if not os.path.isfile(MITM_CA_CERT):
        return False
    our_cert = Path(MITM_CA_CERT).read_text(encoding="utf-8").strip()

    for name, base in ROBLOX_PATHS.items():
        if not os.path.isdir(base):
            continue
        try:
            for entry in os.scandir(base):
                if not entry.is_dir():
                    continue
                is_roblox = (
                    glob.glob(os.path.join(entry.path, "*PlayerBeta.exe")) or
                    glob.glob(os.path.join(entry.path, "*StudioBeta.exe"))
                )
                if is_roblox:
                    cacert_path = os.path.join(entry.path, "ssl", "cacert.pem")
                    if not os.path.isfile(cacert_path):
                        continue
                    content = Path(cacert_path).read_text(encoding="utf-8")
                    if our_cert in content:
                        print(
                            f"[proxy] cert already present, skipping -> {name}: ...{cacert_path[-50:]}")
                        continue
                    content = content.rstrip() + "\n\n" + our_cert + "\n"
                    Path(cacert_path).write_text(content, encoding="utf-8")
                    print(
                        f"[proxy] cert injected -> {name}: ...{cacert_path[-50:]}")
        except PermissionError:
            pass

    extra_dirs: list = []
    extra_dirs.extend(_find_via_launcher_registry())
    extra_dirs.extend(_find_via_xbox_games())
    extra_dirs.extend(_find_via_extra_paths())
    extra_dirs.extend(_find_via_player_path_registry())

    seen: set = set()
    deduped: list = []
    for d in extra_dirs:
        norm = os.path.normcase(os.path.normpath(d))
        if norm not in seen:
            seen.add(norm)
            deduped.append(d)

    _inject_cert_into_dirs(our_cert, deduped, "scan")
    return True


def install_cert_async():
    """Fire install_cert() on a daemon thread so it never blocks the UI or proxy startup."""
    threading.Thread(target=install_cert, daemon=True,
                     name="cert-injector").start()


_watcher_thread: threading.Thread | None = None
_watcher_stop = threading.Event()


def _process_watcher_loop(stop_event: threading.Event):
    """Background thread: watches for RobloxPlayerBeta.exe launches via WMI and injects cert."""
    pythoncom.CoInitialize()
    try:
        wmi_svc = win32com.client.GetObject("winmgmts://./root/cimv2")
        query = (
            "SELECT * FROM __InstanceCreationEvent WITHIN 1 "
            "WHERE TargetInstance ISA 'Win32_Process' "
            "AND TargetInstance.Name = 'RobloxPlayerBeta.exe'"
        )
        watcher = wmi_svc.ExecNotificationQuery(query)
        print("[cert-watcher] watching for RobloxPlayerBeta.exe")
        while not stop_event.is_set():
            try:
                event = watcher.NextEvent(1000)
            except Exception:
                continue
            if event is None:
                continue
            try:
                exe_path = event.TargetInstance.ExecutablePath
                if exe_path:
                    player_dir = os.path.dirname(exe_path)
                    if os.path.isfile(MITM_CA_CERT):
                        our_cert = Path(MITM_CA_CERT).read_text(
                            encoding="utf-8").strip()
                        _inject_cert_into_dirs(
                            our_cert, [player_dir], "process-watcher")
            except Exception as e:
                print(f"[cert-watcher] error handling event: {e}")
    except Exception as e:
        print(f"[cert-watcher] WMI setup error: {e}")
    finally:
        pythoncom.CoUninitialize()


def start_process_watcher():
    """Start a background thread that injects the cert whenever RobloxPlayerBeta.exe launches."""
    global _watcher_thread, _watcher_stop
    if not _WMI_AVAILABLE:
        print("[cert-watcher] pywin32 not available, skipping process watcher")
        return
    if _watcher_thread and _watcher_thread.is_alive():
        return
    _watcher_stop.clear()
    _watcher_thread = threading.Thread(
        target=_process_watcher_loop,
        args=(_watcher_stop,),
        daemon=True,
        name="cert-process-watcher",
    )
    _watcher_thread.start()


def stop_process_watcher():
    """Signal the process watcher thread to stop."""
    _watcher_stop.set()


def remove_cert():
    if not os.path.isfile(MITM_CA_CERT):
        return
    try:
        our_cert = Path(MITM_CA_CERT).read_text(encoding="utf-8").strip()
        for name, base in ROBLOX_PATHS.items():
            if not os.path.isdir(base):
                continue
            try:
                for entry in os.scandir(base):
                    if not entry.is_dir():
                        continue
                    is_roblox = (
                        glob.glob(os.path.join(entry.path, "*PlayerBeta.exe")) or
                        glob.glob(os.path.join(entry.path, "*StudioBeta.exe"))
                    )
                    if is_roblox:
                        cacert_path = os.path.join(
                            entry.path, "ssl", "cacert.pem")
                        if not os.path.isfile(cacert_path):
                            continue
                        content = Path(cacert_path).read_text(encoding="utf-8")
                        if our_cert in content:
                            content = content.replace(
                                our_cert, "").rstrip() + "\n"
                            Path(cacert_path).write_text(
                                content, encoding="utf-8")
                            print(f"[proxy] cert removed from {name}")
            except PermissionError:
                pass
    except Exception as e:
        print(f"[proxy] cert remove error: {e}")
