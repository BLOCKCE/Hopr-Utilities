# mesh_processing.py
# Complete Roblox mesh converter supporting versions 1.x through 7.00
# Handles all mesh formats including Draco-compressed v6/v7 meshes

import struct
import json
import numpy as np

try:
    import DracoPy
    DRACO_AVAILABLE = True
except ImportError:
    DRACO_AVAILABLE = False
    print("Warning: DracoPy not installed. v6/v7 mesh conversion will not work.")
    print("Install with: pip install DracoPy")


# Shared Data Structures

class Vertex:
    """Represents a single vertex with all attributes"""

    def __init__(self):
        # Position
        self.px = self.py = self.pz = 0.0
        # Normal
        self.nx = self.ny = self.nz = 0.0
        # UV coordinates
        self.tu = self.tv = self.tw = 0.0
        # Tangent (signed byte)
        self.tx = self.ty = self.tz = self.ts = 0
        # Color (RGBA)
        self.r = self.g = self.b = self.a = 255


class Face:
    """Represents a triangular face (OBJ uses 1-based indexing)"""

    def __init__(self, a=0, b=0, c=0):
        self.a, self.b, self.c = a, b, c


# Utility Functions

def fix_float(s: str) -> str:
    """Convert comma decimals to period decimals for OBJ format"""
    return s.replace(",", ".")


def read_vertices(data: bytes, offset: int, count: int, vsize: int) -> tuple[list[Vertex], int]:
    """
    Read vertex data from binary mesh formats (v2-v5)

    Args:
        data: Binary mesh data
        offset: Starting position in data
        count: Number of vertices to read
        vsize: Size of each vertex (36 or 40 bytes)

    Returns:
        Tuple of (vertex list, new offset)
    """
    verts = []
    pos = offset

    for _ in range(count):
        v = Vertex()

        # Position (3 floats)
        v.px, = struct.unpack_from("<f", data, pos)
        pos += 4
        v.py, = struct.unpack_from("<f", data, pos)
        pos += 4
        v.pz, = struct.unpack_from("<f", data, pos)
        pos += 4

        # Normal (3 floats)
        v.nx, = struct.unpack_from("<f", data, pos)
        pos += 4
        v.ny, = struct.unpack_from("<f", data, pos)
        pos += 4
        v.nz, = struct.unpack_from("<f", data, pos)
        pos += 4

        # UV coordinates (2 floats)
        v.tu, = struct.unpack_from("<f", data, pos)
        pos += 4
        tv,   = struct.unpack_from("<f", data, pos)
        pos += 4
        v.tv = 1.0 - tv  # Flip V coordinate for Roblox

        # Tangent (4 signed bytes) — always present in standard Roblox v2-v5
        v.tx, = struct.unpack_from("<b", data, pos)
        pos += 1
        v.ty, = struct.unpack_from("<b", data, pos)
        pos += 1
        v.tz, = struct.unpack_from("<b", data, pos)
        pos += 1
        v.ts, = struct.unpack_from("<b", data, pos)
        pos += 1

        # Color (4 unsigned bytes, only in 40-byte format)
        if vsize == 40:
            v.r, = struct.unpack_from("<B", data, pos)
            pos += 1
            v.g, = struct.unpack_from("<B", data, pos)
            pos += 1
            v.b, = struct.unpack_from("<B", data, pos)
            pos += 1
            v.a, = struct.unpack_from("<B", data, pos)
            pos += 1

        verts.append(v)

    return verts, pos


def write_obj_data(v_lines: list[str], n_lines: list[str], t_lines: list[str], f_lines: list[str]) -> str:
    """
    Generate OBJ file content from vertex/normal/texture/face data

    Args:
        v_lines: Vertex position lines
        n_lines: Vertex normal lines
        t_lines: Texture coordinate lines
        f_lines: Face lines

    Returns:
        Complete OBJ file content as string
    """
    lines = ["# Converted from Roblox mesh format\n"]
    lines.append(f"# Vertices: {len(v_lines)}, Faces: {len(f_lines)}\n\n")

    lines.extend(line + "\n" for line in v_lines)
    lines.append("\n")
    lines.extend(line + "\n" for line in n_lines)
    lines.append("\n")
    lines.extend(line + "\n" for line in t_lines)
    lines.append("\n")
    lines.extend(line + "\n" for line in f_lines)

    return "".join(lines)


# Version-Specific Processors

def process_v1(data: bytes) -> str:
    """
    Process version 1.x mesh format (JSON-based)

    Args:
        data: Complete mesh file data

    Returns:
        OBJ file content as string, or None on failure
    """
    try:
        lines = data.decode('utf-8', errors='replace').splitlines()
        if len(lines) < 3:
            print("Invalid v1 mesh: not enough lines")
            return None

        version = lines[0].strip()

        # Parse JSON vertex data (on line 3)
        try:
            # Convert ][  to ],[  for valid JSON array
            content = json.loads("[" + lines[2].replace("][", "],[") + "]")
        except json.JSONDecodeError as e:
            print(f"Failed to parse v1 JSON: {e}")
            return None

        # Each vertex group has 3 elements: position, normal, uv
        groups = len(content) // 3

        verts = []
        norms = []
        uvs = []
        faces = []

        for i in range(groups):
            v = content[i * 3]      # Position [x, y, z]
            n = content[i * 3 + 1]  # Normal [x, y, z]
            uv = content[i * 3 + 2]  # UV [u, v, w]

            verts.append(
                f"v {fix_float(str(v[0]))} {fix_float(str(v[1]))} {fix_float(str(v[2]))}")
            norms.append(
                f"vn {fix_float(str(n[0]))} {fix_float(str(n[1]))} {fix_float(str(n[2]))}")
            uvs.append(
                f"vt {fix_float(str(uv[0]))} {fix_float(str(1 - uv[1]))} {fix_float(str(uv[2]))}")

        # Create faces (every 3 vertices form a triangle)
        for i in range(0, groups, 3):
            idx = i + 1  # OBJ uses 1-based indexing
            faces.append(
                f"f {idx}/{idx}/{idx} {idx+1}/{idx+1}/{idx+1} {idx+2}/{idx+2}/{idx+2}")

        return write_obj_data(verts, norms, uvs, faces)

    except Exception as e:
        print(f"Error processing v1 mesh: {e}")
        return None


def process_v2_to_v5(data: bytes, version_num: str) -> str:
    """
    Process version 2.00 through 5.00 mesh formats

    Args:
        data: Complete mesh file data
        version_num: Version string (e.g., "3.00", "4.01", "5.00")

    Returns:
        OBJ file content as string, or None on failure
    """
    try:
        offset = 13  # Skip "version X.XX\n"

        # Read header
        header_size = struct.unpack_from("<H", data, offset)[0]
        offset += 2

        # Validate header size
        expected_header_size = {
            "2.00": 12, "3.00": 12, "3.01": 12,
            "4.00": 24, "4.01": 24, "5.00": 32
        }

        if version_num in expected_header_size:
            if header_size != expected_header_size[version_num]:
                print(
                    f"Warning: Unexpected header size {header_size} for version {version_num}")

        # Read actual vertex size from header byte (uint8), clamp to known values
        actual_vertex_size = data[offset]  # uint8 at offset+0
        if actual_vertex_size not in (36, 40):
            actual_vertex_size = 40  # safe default — includes color bytes
        lod_type = struct.unpack_from("<H", data, offset)[0]
        offset += 2
        num_verts = struct.unpack_from("<I", data, offset)[0]
        offset += 4
        num_faces = struct.unpack_from("<I", data, offset)[0]
        offset += 4

        num_lods = 0
        num_bones = 0

        if version_num in ("4.00", "4.01"):
            num_lods = struct.unpack_from("<H", data, offset)[0]
            offset += 2
            num_bones = struct.unpack_from("<H", data, offset)[0]
            offset += 2
            _bone_names_buf = struct.unpack_from("<I", data, offset)[0]
            offset += 4
            _num_subsets = struct.unpack_from("<H", data, offset)[0]
            offset += 2
            _num_hq_lods = data[offset]
            offset += 1
            offset += 1

        elif version_num == "5.00":
            # v5 header is 32 bytes total (including the 2-byte sizeof_MeshHeader field).
            # After header_size(2)+lod_type(2)+num_verts(4)+num_faces(4)=12 bytes already read,
            # the remaining 20 bytes are: numLODs(2)+numBones(2)+boneNamesBuf(4)+
            # numSubsets(2)+numHQLODs(1)+unused(1)+facialData(4)+facialData(4).
            if offset + 20 <= len(data):
                num_lods = struct.unpack_from("<H", data, offset)[0]
                offset += 2
                num_bones = struct.unpack_from("<H", data, offset)[0]
                offset += 2
                offset += 4  # sizeof_boneNamesBuffer
                offset += 2  # numSubsets
                offset += 1  # numHighQualityLODs
                offset += 1  # unused byte
                offset += 4  # unused facial data
                offset += 4  # unused facial data
            else:
                remaining = header_size - 12
                if remaining < 0:
                    remaining = 0
                offset += remaining
            actual_vertex_size = 40  # v5 always uses 40-byte vertices (per C# reference)

        else:
            # v2/v3 style
            remaining = header_size - 12
            if remaining < 0:
                remaining = 0
            offset += remaining

        verts, offset = read_vertices(data, offset, num_verts, actual_vertex_size)

        if version_num in ("4.00", "4.01", "5.00") and num_bones > 0:
            bone_bytes = int(num_verts) * 8
            if offset + bone_bytes <= len(data):
                offset += bone_bytes
            else:
                print(
                    f"Invalid v{version_num} bone block: need {bone_bytes} bytes, file ends early")
                return None

        faces = []
        for _ in range(num_faces):
            if offset + 12 > len(data):
                break
            a, b, c = struct.unpack_from("<III", data, offset)
            offset += 12

            if a >= num_verts or b >= num_verts or c >= num_verts:
                continue

            faces.append(Face(a + 1, b + 1, c + 1))

        if version_num in ("4.00", "4.01", "5.00") and num_lods > 0:
            lods = []
            for _ in range(num_lods):
                if offset + 4 > len(data):
                    break
                lods.append(struct.unpack_from("<I", data, offset)[0])
                offset += 4

            # lodType==0 means use all faces; otherwise trim to lods[1] (HQ LOD face count)
            if lod_type != 0 and len(lods) >= 2:
                cut = int(lods[1])
                if 0 < cut < len(faces):
                    faces = faces[:cut]

        # Generate OBJ lines (always append r g b vertex colors)
        v_lines = [
            f"v {fix_float(f'{v.px:.6f}')} {fix_float(f'{v.py:.6f}')} {fix_float(f'{v.pz:.6f}')} "
            f"{fix_float(f'{v.r/255.0:.6f}')} {fix_float(f'{v.g/255.0:.6f}')} {fix_float(f'{v.b/255.0:.6f}')}"
            for v in verts
        ]
        n_lines = [f"vn {fix_float(f'{v.nx:.6f}')} {fix_float(f'{v.ny:.6f}')} {
            fix_float(f'{v.nz:.6f}')}" for v in verts]
        t_lines = [f"vt {fix_float(f'{v.tu:.6f}')} {
            fix_float(f'{v.tv:.6f}')} 0.0" for v in verts]
        f_lines = [
            f"f {f.a}/{f.a}/{f.a} {f.b}/{f.b}/{f.b} {f.c}/{f.c}/{f.c}" for f in faces]

        return write_obj_data(v_lines, n_lines, t_lines, f_lines)

    except Exception as e:
        print(f"Error processing v{version_num} mesh: {e}")
        return None


def process_v6_v7(data: bytes) -> str:
    """
    Process version 6.00 and 7.00 mesh formats (Draco-compressed)

    Args:
        data: Complete mesh file data

    Returns:
        OBJ file content as string, or None on failure
    """
    if not DRACO_AVAILABLE:
        print("DracoPy not available - cannot process v6/v7 meshes")
        return None

    try:
        version = data[:12].decode('utf-8', errors='replace').strip()
        offset = 13  # Skip version header

        coremesh_data = None
        lod_data = None

        # Parse chunk-based format
        while offset < len(data):
            # Read chunk header
            if offset + 16 > len(data):
                break

            chunk_type = data[offset:offset +
                              8].decode('utf-8', errors='ignore').rstrip('\0')
            offset += 8

            chunk_ver = struct.unpack_from("<I", data, offset)[0]
            offset += 4

            chunk_size = struct.unpack_from("<I", data, offset)[0]
            offset += 4

            # Handle version 2 chunks (have additional data_size field)
            if chunk_ver == 2:
                data_size = struct.unpack_from("<I", data, offset)[0]
                offset += 4
            else:
                data_size = chunk_size

            # Extract chunk content
            if offset + data_size > len(data):
                print(f"Warning: Chunk {chunk_type} exceeds file size")
                break

            chunk_content = data[offset:offset + data_size]

            # Store relevant chunks
            if chunk_type == "COREMESH" and chunk_ver == 2:
                coremesh_data = chunk_content
            elif chunk_type == "LODS":
                lod_data = chunk_content

            offset += data_size

        if not coremesh_data:
            print("No COREMESH chunk found in v6/v7 mesh")
            return None

        # Decode Draco-compressed mesh
        try:
            mesh = DracoPy.decode(coremesh_data)

            if mesh is None or not hasattr(mesh, 'points'):
                print("Draco decode failed: invalid mesh data")
                return None

            # Extract vertex positions
            positions = np.array(mesh.points, dtype=np.float32)
            num_verts = len(positions)

            if num_verts == 0:
                print("Draco mesh has no vertices")
                return None

            # Create vertex array
            verts = [Vertex() for _ in range(num_verts)]
            for i in range(num_verts):
                verts[i].px, verts[i].py, verts[i].pz = positions[i]

            # Extract normals if available
            if hasattr(mesh, 'normals') and mesh.normals is not None:
                normals = np.array(mesh.normals, dtype=np.float32)
                if len(normals) == num_verts:
                    for i in range(num_verts):
                        verts[i].nx, verts[i].ny, verts[i].nz = normals[i]
                else:
                    print(
                        f"Warning: Normal count mismatch ({len(normals)} vs {num_verts})")

            # Extract UV coordinates if available
            if hasattr(mesh, 'tex_coords') and mesh.tex_coords is not None:
                tex_coords = np.array(mesh.tex_coords, dtype=np.float32)
                if len(tex_coords) == num_verts:
                    for i in range(num_verts):
                        u, v = tex_coords[i]
                        verts[i].tu = u
                        verts[i].tv = 1.0 - v  # Flip V for Roblox
                else:
                    print(
                        f"Warning: UV count mismatch ({len(tex_coords)} vs {num_verts})")

            # Extract vertex colors via Draco attribute unique ID 4 (Roblox RGBA)
            if hasattr(mesh, 'get_attribute_by_unique_id'):
                try:
                    color_attr = mesh.get_attribute_by_unique_id(4)
                    if color_attr is not None and 'data' in color_attr:
                        colors = np.array(color_attr['data'], dtype=np.uint8)
                        if colors.ndim == 1:
                            colors = colors.reshape(-1, 4)
                        if len(colors) == num_verts:
                            for i in range(num_verts):
                                verts[i].r = colors[i][0]
                                verts[i].g = colors[i][1]
                                verts[i].b = colors[i][2]
                                verts[i].a = colors[i][3]
                        else:
                            print(f"Warning: Color count mismatch ({len(colors)} vs {num_verts})")
                except Exception:
                    pass

            # Extract faces
            faces = []
            if hasattr(mesh, 'faces') and mesh.faces is not None:
                for tri in mesh.faces:
                    a, b, c = map(int, tri)
                    # Reverse winding order and convert to 1-based indexing
                    faces.append(Face(a + 1, c + 1, b + 1))

            print(
                f"Draco mesh decoded: {num_verts:,} vertices, {len(faces):,} faces")

            # Apply LOD trimming if LODS chunk is present
            max_faces = len(faces)
            if lod_data and len(lod_data) > 7:
                try:
                    lod_pos = 0

                    # Skip LOD type (2 bytes)
                    lod_pos += 2

                    # Read number of high quality LODs
                    num_high_quality = lod_data[lod_pos]
                    lod_pos += 1

                    # Read number of LOD values
                    num_offsets = struct.unpack_from(
                        "<I", lod_data, lod_pos)[0]
                    lod_pos += 4

                    if num_offsets >= 2:
                        # lods[0] is always 0, lods[1] is the HQ face count.
                        # Use lods[1] directly (same as v4/v5 C# code uses lods[1]).
                        lod_val0 = struct.unpack_from(
                            "<I", lod_data, lod_pos)[0]
                        lod_pos += 4
                        lod_val1 = struct.unpack_from(
                            "<I", lod_data, lod_pos)[0]

                        # lod_val1 is the face count for HQ LOD (lod_val0 is always 0)
                        hq_faces = lod_val1 if lod_val0 == 0 else (lod_val1 - lod_val0)
                        if 0 < hq_faces < max_faces:
                            max_faces = hq_faces
                            print(
                                f"Applying high-quality LOD: {len(faces):,} -> {max_faces:,} faces")

                except Exception as e:
                    print(f"LOD parsing failed: {e}")

            # Trim faces to LOD limit
            if max_faces < len(faces):
                faces = faces[:max_faces]

            # Generate OBJ lines (always append r g b vertex colors)
            v_lines = [
                f"v {fix_float(f'{v.px:.6f}')} {fix_float(f'{v.py:.6f}')} {fix_float(f'{v.pz:.6f}')} "
                f"{fix_float(f'{v.r/255.0:.6f}')} {fix_float(f'{v.g/255.0:.6f}')} {fix_float(f'{v.b/255.0:.6f}')}"
                for v in verts
            ]
            n_lines = [f"vn {fix_float(f'{v.nx:.6f}')} {fix_float(f'{v.ny:.6f}')} {
                fix_float(f'{v.nz:.6f}')}" for v in verts]
            t_lines = [f"vt {fix_float(f'{v.tu:.6f}')} {
                fix_float(f'{v.tv:.6f}')} 0.0" for v in verts]
            f_lines = [
                f"f {f.a}/{f.a}/{f.a} {f.b}/{f.b}/{f.b} {f.c}/{f.c}/{f.c}" for f in faces]

            return write_obj_data(v_lines, n_lines, t_lines, f_lines)

        except Exception as e:
            print(f"DracoPy decoding error: {e}")
            import traceback
            traceback.print_exc()
            return None

    except Exception as e:
        print(f"Error processing v6/v7 mesh: {e}")
        import traceback
        traceback.print_exc()
        return None


# Main Conversion Function

def convert(data: bytes, output_path: str = None) -> str:
    """
    Convert Roblox mesh data to OBJ format

    Args:
        data: Binary mesh file data
        output_path: Optional path to write OBJ file to

    Returns:
        OBJ file content as string, or None on failure
    """
    if not data or len(data) < 12:
        print("Invalid mesh data: file too small")
        return None

    # Detect version from header
    header = data[:12].decode('utf-8', errors='ignore').strip()
    print(f"Detected mesh version: {header}")

    obj_content = None

    # Route to appropriate processor
    if header.startswith("version 1."):
        obj_content = process_v1(data)

    elif header in ["version 2.00", "version 3.00", "version 3.01",
                    "version 4.00", "version 4.01", "version 5.00"]:
        version_num = header.split()[1]  # Extract "X.XX"
        obj_content = process_v2_to_v5(data, version_num)

    elif header in ["version 6.00", "version 7.00"]:
        obj_content = process_v6_v7(data)

    else:
        print(f"Unsupported mesh version: {header}")
        return None

    # Write to file if path provided
    if obj_content and output_path:
        try:
            with open(output_path, 'w', encoding='utf-8') as f:
                f.write(obj_content)
            print(f"OBJ file written to: {output_path}")
        except Exception as e:
            print(f"Failed to write OBJ file: {e}")

    return obj_content


def decode_loader_obj_mesh(data: bytes):
    """Decode a Roblox v2.00 binary mesh format.

    Vertex layout: 9 floats (px,py,pz, nx,ny,nz, tu,tv,tw) = 36 bytes.
    Optional vertex color: 4 bytes RGBA appended per vertex when vertexSize==40.
    TV is stored flipped (tv_stored = 1 - tv_original), so we undo it.
    Returns OBJ text string, or None on failure.
    """
    try:
        if not data.startswith(b"version 2.00"):
            return None
        # Skip "version 2.00\n" — could be \r\n on Windows
        nl = data.index(b"\n")
        offset = nl + 1

        header_size = struct.unpack_from("<H", data, offset)[0]
        vertex_size = data[offset + 2]   # uint8
        # face_size  = data[offset + 3]  # uint8 (always 12)
        vertex_count = struct.unpack_from("<I", data, offset + 4)[0]
        face_count   = struct.unpack_from("<I", data, offset + 8)[0]
        offset += header_size

        has_colors = (vertex_size >= 40)

        v_lines, n_lines, t_lines, f_lines = [], [], [], []
        for _ in range(vertex_count):
            px, py, pz = struct.unpack_from("<fff", data, offset); offset += 12
            nx, ny, nz = struct.unpack_from("<fff", data, offset); offset += 12
            tu, tv_stored, _ = struct.unpack_from("<fff", data, offset); offset += 12
            if has_colors:
                offset += 4  # skip RGBA
            tv = 1.0 - tv_stored  # undo the stored V flip
            v_lines.append(f"v {px:.6f} {py:.6f} {pz:.6f}")
            n_lines.append(f"vn {nx:.6f} {ny:.6f} {nz:.6f}")
            t_lines.append(f"vt {tu:.6f} {tv:.6f}")

        for _ in range(face_count):
            a, b, c = struct.unpack_from("<III", data, offset); offset += 12
            f_lines.append(f"f {a+1}/{a+1}/{a+1} {b+1}/{b+1}/{b+1} {c+1}/{c+1}/{c+1}")

        lines = ["# Decoded from Roblox v2.00 mesh\n"]
        lines.extend(l + "\n" for l in v_lines)
        lines.append("\n")
        lines.extend(l + "\n" for l in n_lines)
        lines.append("\n")
        lines.extend(l + "\n" for l in t_lines)
        lines.append("\n")
        lines.extend(l + "\n" for l in f_lines)
        return "".join(lines)
    except Exception as e:
        print(f"[decode_loader_obj_mesh] failed: {e}")
        return None


# Standalone Usage

if __name__ == "__main__":
    import sys
    from pathlib import Path

    if len(sys.argv) < 2:
        print("Usage: python mesh_processing.py <mesh_file>")
        print("Example: python mesh_processing.py model.mesh")
        sys.exit(1)

    mesh_path = Path(sys.argv[1])

    if not mesh_path.exists():
        print(f"File not found: {mesh_path}")
        sys.exit(1)

    # Read mesh data
    data = mesh_path.read_bytes()

    # Convert to OBJ
    output_path = mesh_path.with_suffix('.obj')
    obj_content = convert(data, str(output_path))

    if obj_content:
        print(f"\n✓ Conversion successful!")
        print(f"  Input:  {mesh_path}")
        print(f"  Output: {output_path}")
    else:
        print("\n✗ Conversion failed")
        sys.exit(1)
