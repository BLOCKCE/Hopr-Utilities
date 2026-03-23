"""Intermediary conversion helpers for .mesh and binary CSG (.bin) files.

Both formats need to be decompiled to an OBJ "pivot" so the rest of the
pipeline (solidmodel injection or OBJ->.mesh) can handle them without
format-awareness.

The converted OBJ is written to APP_CACHE_DIR and re-used on subsequent
calls as long as the source file has not been modified.
"""

from __future__ import annotations

import gzip
import hashlib
import math
from pathlib import Path

from ._utils import APP_CACHE_DIR, log_buffer

_ZSTD_MAGIC = b'\x28\xb5\x2f\xfd'
_GZIP_MAGIC = b'\x1f\x8b'


def _decompress(data: bytes) -> bytes:
    """Strip zstd or gzip application-level wrapping if present."""
    if data[:4] == _ZSTD_MAGIC:
        import zstandard  # type: ignore[import-untyped]
        data = zstandard.ZstdDecompressor().decompress(
            data, max_output_size=64 * 1024 * 1024
        )
    elif data[:2] == _GZIP_MAGIC:
        data = gzip.decompress(data)
    return data


_RBXM_BINARY_SIG = b'<roblox!'


def is_binary_rbxm(data: bytes) -> bool:
    """Return True if data looks like a binary RBXM."""
    return data[:8] == _RBXM_BINARY_SIG


def _cache_obj_path(source: Path) -> Path:
    """Return a deterministic APP_CACHE_DIR OBJ path for source."""
    h = hashlib.md5(str(source.resolve()).encode('utf-8')).hexdigest()
    return APP_CACHE_DIR / f'{source.stem}_{h}.obj'


def _is_cache_fresh(source: Path, cached: Path) -> bool:
    """Return True if cached exists and is at least as new as source."""
    return cached.exists() and source.stat().st_mtime <= cached.stat().st_mtime


def mesh_file_to_cached_obj(mesh_path: Path) -> Path:
    """Convert a Roblox .mesh file to a cached Wavefront OBJ.

    Uses mesh_processing.convert which handles all mesh versions
    (v1.x through v7.00, including Draco-compressed v6/v7).
    """
    # Lazy import — mesh_processing.py lives at modules/cache/mesh_processing.py
    # which is on sys.path when running under the module loader.
    # type: ignore[import]
    from shared.mesh_processing import convert as mesh_to_obj_str

    mesh_path = Path(mesh_path).resolve()
    if not mesh_path.exists():
        raise FileNotFoundError(f'Mesh file not found: {mesh_path}')

    APP_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cached_obj = _cache_obj_path(mesh_path)

    if _is_cache_fresh(mesh_path, cached_obj):
        log_buffer.log(
            'Intermediary', f'Using cached OBJ for .mesh: {cached_obj.name}')
        return cached_obj

    log_buffer.log('Intermediary', f'Converting .mesh -> OBJ: {mesh_path.name}')
    data = mesh_path.read_bytes()
    obj_content = mesh_to_obj_str(data)

    if not obj_content:
        raise ValueError(
            f'mesh_processing.convert produced no output for: {mesh_path}')

    cached_obj.write_text(obj_content, encoding='utf-8')
    log_buffer.log(
        'Intermediary',
        f'.mesh -> OBJ done: {cached_obj.name} (source {len(data)} bytes)',
    )
    return cached_obj


def _csg_vertices_to_obj(vertices, indices: list[int]) -> str:
    """Serialize a (CSGVertex list, flat index list) pair as OBJ text.

    Vertex colors are included in v lines as normalized floats.
    The V coordinate is un-flipped here (1.0 - v.v) because the
    CSGVertex stores the already-flipped value.
    """
    lines: list[str] = [
        '# Converted from Roblox CSGMDL format\n',
        f'# Vertices: {len(vertices)}, Faces: {len(indices) // 3}\n',
        '\n',
    ]

    for v in vertices:
        r = v.cr / 255.0
        g = v.cg / 255.0
        b = v.cb / 255.0
        lines.append(
            f'v {v.px:.6f} {v.py:.6f} {v.pz:.6f} {r:.6f} {g:.6f} {b:.6f}\n'
        )

    lines.append('\n')

    for v in vertices:
        lines.append(f'vn {v.nx:.6f} {v.ny:.6f} {v.nz:.6f}\n')

    lines.append('\n')

    for v in vertices:
        lines.append(f'vt {v.u:.6f} {1.0 - v.v:.6f} 0.0\n')

    lines.append('\n')

    for i in range(0, len(indices), 3):
        a = indices[i] + 1
        b = indices[i + 1] + 1
        c = indices[i + 2] + 1
        lines.append(f'f {a}/{a}/{a} {b}/{b}/{b} {c}/{c}/{c}\n')

    return ''.join(lines)


#: Instance class names that carry a MeshData property inside a CSG RBXM.
_INJECTABLE = frozenset({
    'PartOperationAsset',
    'UnionOperation',
    'NegateOperation',
    'PartOperation',
})


def bin_file_to_cached_obj(bin_path: Path) -> Path:
    """Convert a Roblox binary CSG .bin file to a cached Wavefront OBJ.

    Steps:
    1. Decompress if needed (zstd/gzip).
    2. Deserialize the binary RBXM.
    3. Extract MeshData from the first injectable root.
    4. Decrypt/parse CSGMDL -> (vertices, indices).
    5. Write a Wavefront OBJ to APP_CACHE_DIR and return its path.
    """
    from .converter import deserialize_rbxm
    from .csg_mesh import parse_csg_mesh

    bin_path = Path(bin_path).resolve()
    if not bin_path.exists():
        raise FileNotFoundError(f'CSG .bin file not found: {bin_path}')

    APP_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cached_obj = _cache_obj_path(bin_path)

    if _is_cache_fresh(bin_path, cached_obj):
        log_buffer.log(
            'Intermediary', f'Using cached OBJ for .bin: {cached_obj.name}')
        return cached_obj

    log_buffer.log(
        'Intermediary', f'Converting .bin (CSG) -> OBJ: {bin_path.name}')

    raw = bin_path.read_bytes()
    data = _decompress(raw)

    if not is_binary_rbxm(data):
        raise ValueError(
            f'.bin file does not look like a binary RBXM (got header '
            f'{data[:8]!r}): {bin_path}'
        )

    doc = deserialize_rbxm(data)

    mesh_data: bytes | None = None
    for inst in doc.roots:
        if inst.class_name in _INJECTABLE:
            prop = inst.properties.get('MeshData')
            if prop is not None and prop.value:
                mesh_data = prop.value
                break

    if not mesh_data:
        raise ValueError(
            f'No MeshData found in any injectable root of: {bin_path}\n'
            f'  roots: {[r.class_name for r in doc.roots]}'
        )

    vertices, indices = parse_csg_mesh(mesh_data)

    if not vertices or not indices:
        raise ValueError(f'CSGMDL in {bin_path} produced no usable geometry')

    obj_content = _csg_vertices_to_obj(vertices, indices)
    cached_obj.write_text(obj_content, encoding='utf-8')

    log_buffer.log(
        'Intermediary',
        f'.bin -> OBJ done: {cached_obj.name} '
        f'({len(vertices)} verts, {len(indices) // 3} tris)',
    )
    return cached_obj
