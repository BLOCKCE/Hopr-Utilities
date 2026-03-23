"""Small utility helpers used by the cache module."""


def batch_location(entry: dict) -> str:
    """Extract the CDN location URL from a v1 or v2 /assets/batch response entry.

    v1: {"location": "https://...", ...}
    v2: {"locations": [{"assetFormat": "source", "location": "https://..."}, ...], ...}
    """
    # v1 direct key
    loc = entry.get("location")
    if loc:
        return loc
    # v2 nested array
    locations = entry.get("locations")
    if isinstance(locations, list):
        for item in locations:
            if isinstance(item, dict):
                loc = item.get("location")
                if loc:
                    return loc
    return ""

import os
import json
import base64
import re
import struct

try:
    import win32crypt  # type: ignore
except Exception:
    win32crypt = None


def strip_cache_header(data: bytes) -> bytes:
    if not data:
        return data

    if len(data) >= 12 and data[:4] == b"RBXH":
        ver, url_len = struct.unpack("<II", data[4:12])
        if 0 < url_len < 4096 and 12 + url_len <= len(data):
            data = data[12 + url_len:]

    search_limit = min(len(data), 8192)
    signatures = [
        b"\x89PNG\r\n\x1a\n",
        b"GIF87a", b"GIF89a",
        b"\xff\xd8\xff",
        b"OggS",
        b"ID3",
        b"RIFF",
        b"<?xml",
        b"<roblox",
    ]

    best = None
    for sig in signatures:
        idx = data[:search_limit].find(sig)
        if idx != -1 and (best is None or idx < best):
            best = idx

    if best is not None and best > 0:
        return data[best:]

    return data


def get_roblosecurity():
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


def isnumeric(s):
    """Check if a string represents a number (integer)"""
    if not s:
        return False
    s = str(s).strip()
    if not s:
        return False
    try:
        int(s)
        return True
    except (ValueError, TypeError):
        return False


def has_cache_data(info: dict) -> bool:
    """Return True if cache data exists for this entry (on disk or in memory)."""
    return "cache_data_path" in info or "cache_data" in info


def get_cache_data(info: dict):
    """Return cache data bytes for this entry, reading from disk if needed."""
    path = info.get("cache_data_path")
    if path:
        try:
            with open(path, "rb") as f:
                return f.read()
        except Exception:
            pass
    return info.get("cache_data")


def github_blob_to_raw_url(url: str) -> str:
    """Convert a GitHub blob URL to a raw.githubusercontent.com URL.

    https://github.com/user/repo/blob/branch/path/file.ext?raw=true
    -> https://raw.githubusercontent.com/user/repo/branch/path/file.ext
    """
    try:
        clean = url.split("?")[0]
        if "github.com/" in clean and "/blob/" in clean:
            after_host = clean.split("github.com/", 1)[1]
            repo_part, rest = after_host.split("/blob/", 1)
            return f"https://raw.githubusercontent.com/{repo_part}/{rest}"
    except Exception:
        pass
    return url
