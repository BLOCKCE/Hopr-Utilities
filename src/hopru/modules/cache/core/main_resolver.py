"""Asset and creator name resolver loops for the cache module."""

import os
import json
import time
import threading
import requests
from pathlib import Path
from urllib.parse import urlparse
from datetime import datetime

from shared.constants import ASSET_TYPES
from shared.utils import get_roblosecurity, has_cache_data

def fetch_creator_names(self, user_ids, cookie):
    if not cookie or not user_ids:
        return None

    sess = self._new_session(cookie, xCSRF=True)
    url = "https://apis.roblox.com/user-profile-api/v1/user/profiles/get-profiles"

    payload = {
        "userIds": [int(uid) for uid in user_ids],
        "fields": ["names.combinedName", "names.username", "names.displayName", "names.alias"],
    }

    try:
        r = sess.post(url, json=payload, timeout=10)
        r.raise_for_status()
        j = r.json()
    except Exception as e:
        print(f"[fetch_creator_names] Failed: {e}")
        return None

    profiles = j.get("profileDetails") if isinstance(j, dict) else None
    if not profiles:
        return None

    out = {}
    for p in profiles:
        uid = p.get("userId")
        names = p.get("names") or {}
        best = (
            names.get("combinedName")
            or names.get("displayName")
            or names.get("username")
            or names.get("alias")
        )
        if uid is not None and best:
            out[int(uid)] = best

    return out


def fetch_asset_names(self, asset_ids, cookie):
    if not cookie or not asset_ids:
        return None

    sess = self._new_session(cookie)
    base_url = "https://develop.roblox.com/v1/assets"
    query = ",".join(str(aid) for aid in asset_ids)
    url = f"{base_url}?assetIds={query}"

    try:
        r = sess.get(url, timeout=10)
        r.raise_for_status()
    except Exception as e:
        print(f"[fetch_asset_names] Failed to fetch {asset_ids}: {e}")
        return None

    data = r.json().get("data", [])
    result = {}
    for item in data:
        asset_id = item.get("id")
        name = item.get("name", "Unknown")

        creator = item.get("creator") or {}
        creator_id = creator.get("targetId")

        if asset_id is not None:
            result[asset_id] = {
                "name": name,
                "creatorId": creator_id,
            }

    return result


def name_resolver_loop(self):
    while True:
        if not self.show_names_action.isChecked():
            time.sleep(0.2)
            continue
        cookie = get_roblosecurity()
        if not cookie:
            print(
                "[Name Resolver] No .ROBLOSECURITY cookie found. Please log in to Roblox.")
            time.sleep(5)
            continue

        pending_assets = [
            asset_id
            for asset_id, info in list(self.cache_logs.items())
            if isinstance(info, dict)
            and info.get("resolved_name") is None
            and info.get("name_index") is not None
        ]

        if not pending_assets:
            time.sleep(0.2)
            continue

        batch_size = 50
        delay = 0.2 if len(pending_assets) > 50 else 0.5

        batch = pending_assets[:batch_size]

        try:
            names = self.fetch_asset_names(batch, cookie)
        except Exception as e:
            print(f"[Name Resolver] Fetch failed: {e}")
            # Retry next loop
            time.sleep(delay)
            continue

        if not names:
            time.sleep(delay)
            continue

        name_updates = {}
        for asset_id, meta in names.items():
            info = self.cache_logs.get(asset_id)
            if not info or info.get("name_index") is None:
                continue

            if isinstance(meta, str):
                name = meta
                creator_id = None
            else:
                name = (meta or {}).get("name", "Unknown")
                creator_id = (meta or {}).get("creatorId")

            info["resolved_name"] = name
            info["creator_user_id"] = creator_id
            info.setdefault("creator_name", None)

            self._queue_cache_index_update(
                asset_id,
                resolved_name=name,
                creator_user_id=creator_id,
            )

            if self.show_names_action.isChecked():
                name_updates[asset_id] = name

        if name_updates:
            # Post all name updates as one batch — one repaint instead of N
            self._on_main(lambda u=name_updates: self._batch_update_row_names(u))

        time.sleep(delay)


def creator_resolver_loop(self):
    while True:
        cookie = get_roblosecurity()
        if not cookie:
            time.sleep(2)
            continue

        pending = []
        for asset_id, info in list(self.cache_logs.items()):
            uid = info.get("creator_user_id")
            if uid and not info.get("creator_name"):
                pending.append(int(uid))

        if not pending:
            time.sleep(0.2)
            continue

        pending = list(dict.fromkeys(pending))
        batch = pending[:200]

        names = self.fetch_creator_names(batch, cookie)
        if not names:
            time.sleep(0.5)
            continue

        creator_updates = {}
        for asset_id, info in list(self.cache_logs.items()):
            uid = info.get("creator_user_id")
            if not uid:
                continue
            cname = names.get(int(uid))
            if not cname:
                continue

            info["creator_name"] = cname
            creator_updates[asset_id] = cname
            self._queue_cache_index_update(asset_id, creator_name=cname)

        if creator_updates:
            # Post all creator updates as one batch — one repaint instead of N
            self._on_main(lambda u=creator_updates: self._batch_update_row_creators(u))

        time.sleep(0.2)


def _on_show_names_toggled(self, checked: bool):
    tv = getattr(self, "table_view", None)
    if tv is not None:
        tv.setUpdatesEnabled(False)
    try:
        for asset_id, info in list(self.cache_logs.items()):
            idx = info.get("name_index")
            if not idx or not idx.isValid():
                continue

            if checked:
                resolved = info.get("resolved_name")
                if resolved:
                    self._update_row_name(asset_id, resolved)
                else:
                    continue
            else:
                location = info.get("location")
                if location:
                    parsed_location = urlparse(location)
                    cache_hash = parsed_location.path.rsplit('/', 1)[-1]
                else:
                    cache_hash = "Unknown"

                self._update_row_name(asset_id, cache_hash)
    finally:
        if tv is not None:
            tv.setUpdatesEnabled(True)


def process_asset_row(self, content: bytes, status_code: int, parsed_url, asset_id):

    if asset_id not in self.cache_logs:
        return

    info = self.cache_logs[asset_id]

    if has_cache_data(info):
        return

    # Get content size
    content_size_bytes = len(content) if content else 0

    # Write cache data to a persistent .bin file in the app cache directory.
    bin_path = self._get_cache_bin_path(asset_id)
    try:
        bin_path.write_bytes(content)
        info["cache_data_path"] = str(bin_path)
    except Exception:
        info["cache_data"] = content
    info["cache_status"] = status_code
    info["cache_fetched_at"] = time.time()

    # Hash/name
    cache_hash = parsed_url.path.rsplit('/', 1)[-1]

    # Determine asset type name
    asset_type_id = info.get("assetTypeId")
    asset_type = "Unknown"
    for at_id, at_name in ASSET_TYPES:
        if at_id == asset_type_id:
            asset_type = at_name
            break

    # Format size text
    if content_size_bytes == 0:
        size_text = "0 B"
    elif content_size_bytes < 1024:
        size_text = f"{content_size_bytes} B"
    elif content_size_bytes < 1024 * 1024:
        size_text = f"{content_size_bytes / 1024:.2f} KB"
    else:
        size_text = f"{content_size_bytes / (1024 * 1024):.2f} MB"

    # Date info
    now = datetime.utcnow()
    date_text = now.strftime("%a %b %d %H:%M:%S %Y")
    date_sort = int(time.time())

    # Determine display type
    display_type = asset_type
    if asset_type_id == 4 and content:
        file_type = self._identify_file_type(content)
        if file_type.startswith("Mesh"):
            display_type = file_type

    if not getattr(self, "_log_finder", True):
        return

    # Add row
    self.add_row(
        name=cache_hash,
        asset_id=asset_id,
        type_name=display_type,
        size_text=size_text,
        size_bytes=float(content_size_bytes),
        date_text=date_text,
        date_sort=date_sort,
    )

    # Persist to index
    self._queue_cache_index_update(
        asset_id,
        cache_hash=cache_hash,
        location=info.get("location", ""),
        asset_type_id=info.get("assetTypeId"),
        asset_type=display_type,
        size_text=size_text,
        size=content_size_bytes,
        date_text=date_text,
        date_sort=date_sort,
    )


def fetch_and_process(self, location_url, asset_id):
    try:
        resp = requests.get(location_url, verify=False)
        if resp.status_code == 200:
            parsed_url = urlparse(location_url)
            self.process_asset_row(
                content=resp.content,
                status_code=resp.status_code,
                parsed_url=parsed_url,
                asset_id=asset_id,
            )
    except Exception as e:
        print(f"Failed to fetch asset {asset_id}: {e}")


def _on_export_raw_toggled(self, checked: bool):
    pass


def _on_export_converted_toggled(self, checked: bool):
    pass


def _cache_dir(self) -> Path:
    base = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
    d = Path(base) / "SubplaceJoiner" / "Cache"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _cache_index_path(self) -> Path:
    return self._cache_dir() / "index.json"


def _get_cache_bin_path(self, asset_id) -> Path:
    return self._cache_dir() / f"{asset_id}.bin"


def _queue_cache_index_update(self, asset_id, **fields):
    lock = getattr(self, "_cache_index_lock", None)
    if lock is None:
        return
    with lock:
        key = str(asset_id)
        pending = getattr(self, "_cache_index_pending", {})
        cur = pending.get(key, {})
        cur.update(fields)
        pending[key] = cur
        self._cache_index_pending = pending
        old_t = getattr(self, "_cache_index_timer", None)
        if old_t is not None:
            old_t.cancel()
        t = threading.Timer(0.5, self._flush_cache_index)
        t.daemon = True
        t.start()
        self._cache_index_timer = t


def _flush_cache_index(self):
    lock = getattr(self, "_cache_index_lock", None)
    if lock is None:
        return
    with lock:
        pending = dict(getattr(self, "_cache_index_pending", {}))
        self._cache_index_pending = {}
        self._cache_index_timer = None
    if not pending:
        return
    path = self._cache_index_path()
    with lock:
        try:
            idx = json.loads(path.read_text(encoding="utf-8", errors="ignore")) if path.exists() else {"version": 2, "assets": {}}
        except Exception:
            idx = {"version": 2, "assets": {}}
        if not isinstance(idx, dict):
            idx = {"version": 2, "assets": {}}
        idx.setdefault("version", 2)
        idx.setdefault("assets", {})
        for key, flds in pending.items():
            cur = idx["assets"].get(key, {})
            cur.update(flds)
            idx["assets"][key] = cur
        try:
            path.write_text(json.dumps(idx, indent=2), encoding="utf-8")
        except Exception as e:
            print(f"[Cache index] Flush failed: {e}")


def _delete_cache_entry(self, asset_id):
    bin_path = self._get_cache_bin_path(asset_id)
    try:
        if bin_path.exists():
            bin_path.unlink()
    except Exception as e:
        print(f"[Cache] Failed to delete {bin_path}: {e}")
    lock = getattr(self, "_cache_index_lock", None)
    if lock is None:
        return
    with lock:
        pending = getattr(self, "_cache_index_pending", {})
        pending.pop(str(asset_id), None)
        path = self._cache_index_path()
        try:
            idx = json.loads(path.read_text(encoding="utf-8", errors="ignore")) if path.exists() else {}
        except Exception:
            return
        if isinstance(idx, dict):
            idx.get("assets", {}).pop(str(asset_id), None)
            try:
                path.write_text(json.dumps(idx, indent=2), encoding="utf-8")
            except Exception as e:
                print(f"[Cache index] Delete entry failed: {e}")


def _load_persistent_cache(self):
    idx_path = self._cache_index_path()
    if not idx_path.exists():
        return
    try:
        idx = json.loads(idx_path.read_text(encoding="utf-8", errors="ignore"))
    except Exception:
        return
    if not isinstance(idx, dict):
        return
    assets = idx.get("assets", {})
    if not assets:
        return

    # Drop entries whose .bin file is missing
    to_remove = [k for k in assets if not self._get_cache_bin_path(k).exists()]
    for k in to_remove:
        del assets[k]
    if to_remove:
        try:
            idx_path.write_text(json.dumps(idx, indent=2), encoding="utf-8")
        except Exception:
            pass

    for asset_id_str, entry in assets.items():
        try:
            asset_id = int(asset_id_str)
        except (ValueError, TypeError):
            continue
        if asset_id in self.cache_logs:
            continue
        bin_path = self._get_cache_bin_path(asset_id)
        self.cache_logs[asset_id] = {
            "location": entry.get("location", ""),
            "assetTypeId": entry.get("asset_type_id"),
            "cache_data_path": str(bin_path),
            "cache_status": 200,
            "cache_fetched_at": entry.get("date_sort", 0),
            "resolved_name": entry.get("resolved_name"),
            "creator_name": entry.get("creator_name"),
            "creator_user_id": entry.get("creator_user_id"),
        }
        self.add_row(
            name=entry.get("resolved_name") or entry.get("cache_hash") or asset_id_str,
            asset_id=asset_id,
            type_name=entry.get("asset_type", "Unknown"),
            size_text=entry.get("size_text", ""),
            size_bytes=float(entry.get("size", 0)),
            date_text=entry.get("date_text", ""),
            date_sort=entry.get("date_sort", 0),
            creator_name=entry.get("creator_name") or "",
        )
