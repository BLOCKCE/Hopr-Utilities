"""Shared constants and one-time library setup for the cache module."""

from requests.adapters import HTTPAdapter

CLOG_RAW_URL = "https://github.com/qrhrqiohj/PFTEST/raw/main/CLOG.json"

adapter = HTTPAdapter(pool_connections=200, pool_maxsize=200)

# Asset types used throughout the UI.
ASSET_TYPES = [
    (1, "Image"),
    (3, "Audio"),
    (4, "Mesh"),
    (5, "Lua"),
    (19, "Gear"),
    (24, "Animation"),
    (27, "Torso"),
    (28, "RightArm"),
    (29, "LeftArm"),
    (30, "RightLeg"),
    (31, "LeftLeg"),
    (39, "SolidModel"),
    (40, "MeshPart"),
    (60, "LocalizationTableTranslation"),
    (63, "TexturePack"),
    (73, "FontFamily"),
    (74, "FontFace"),
    (75, "MeshHiddenSurfaceRemoval"),
]
