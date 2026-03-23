import sys
import math
import os
import json
import time as _time
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from typing import Dict, List, Tuple, Optional

from PySide6.QtCore import QTimer, Qt
from PySide6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QSlider, QLabel, QMenu, QWidgetAction,
)

import numpy as np

from anim_gl_widget import AnimGLWidget


# XML helpers

def _text(elem: Optional[ET.Element], default="") -> str:
    return elem.text if elem is not None and elem.text is not None else default


def find_prop(props: ET.Element, tag: str, names: List[str]) -> Optional[ET.Element]:
    for n in names:
        e = props.find(f"{tag}[@name='{n}']")
        if e is not None:
            return e
    for child in props:
        if child.tag != tag:
            continue
        nm = child.attrib.get("name", "")
        for n in names:
            if nm.lower() == n.lower():
                return child
    return None


def parse_vector3(elem: ET.Element) -> Tuple[float, float, float]:
    return (
        float(_text(elem.find("X"), "0")),
        float(_text(elem.find("Y"), "0")),
        float(_text(elem.find("Z"), "0")),
    )


def parse_cframe(elem: ET.Element) -> Tuple[Tuple[float, float, float], List[float]]:
    x = float(_text(elem.find("X"), "0"))
    y = float(_text(elem.find("Y"), "0"))
    z = float(_text(elem.find("Z"), "0"))
    r = []
    for k in ("R00", "R01", "R02", "R10", "R11", "R12", "R20", "R21", "R22"):
        if k in ("R00", "R11", "R22"):
            r.append(float(_text(elem.find(k), "1")))
        else:
            r.append(float(_text(elem.find(k), "0")))
    return (x, y, z), r


def lerp(a: float, b: float, t: float) -> float:
    return a + (b - a) * t


# Some thing

# Numpy matrix helpers — replaces vtk matrix operations in the hot path

_NP_IDENT = np.eye(4, dtype=np.float32)


def np_from_cframe(pos: tuple, r: list) -> np.ndarray:
    """Build a 4×4 float32 matrix from a CFrame (position + 3×3 rotation row-major)."""
    return np.array([
        [r[0], r[1], r[2], pos[0]],
        [r[3], r[4], r[5], pos[1]],
        [r[6], r[7], r[8], pos[2]],
        [0.0,  0.0,  0.0,  1.0],
    ], dtype=np.float32)


def np_inv_rigid(m: np.ndarray) -> np.ndarray:
    """Inverse of a rigid-body (rotation + translation) 4×4 matrix."""
    R = m[:3, :3]
    t = m[:3, 3]
    out = np.eye(4, dtype=np.float32)
    out[:3, :3] = R.T
    out[:3, 3] = -(R.T @ t)
    return out


def quat_from_rot3(r):
    trace = r[0][0] + r[1][1] + r[2][2]
    if trace > 0.0:
        s = math.sqrt(trace + 1.0) * 2.0
        w = 0.25 * s
        x = (r[2][1] - r[1][2]) / s
        y = (r[0][2] - r[2][0]) / s
        z = (r[1][0] - r[0][1]) / s
    elif (r[0][0] > r[1][1]) and (r[0][0] > r[2][2]):
        s = math.sqrt(1.0 + r[0][0] - r[1][1] - r[2][2]) * 2.0
        w = (r[2][1] - r[1][2]) / s
        x = 0.25 * s
        y = (r[0][1] + r[1][0]) / s
        z = (r[0][2] + r[2][0]) / s
    elif r[1][1] > r[2][2]:
        s = math.sqrt(1.0 + r[1][1] - r[0][0] - r[2][2]) * 2.0
        w = (r[0][2] - r[2][0]) / s
        x = (r[0][1] + r[1][0]) / s
        y = 0.25 * s
        z = (r[1][2] + r[2][1]) / s
    else:
        s = math.sqrt(1.0 + r[2][2] - r[0][0] - r[1][1]) * 2.0
        w = (r[1][0] - r[0][1]) / s
        x = (r[0][2] + r[2][0]) / s
        y = (r[1][2] + r[2][1]) / s
        z = 0.25 * s
    n = math.sqrt(w*w + x*x + y*y + z*z) or 1.0
    return (w/n, x/n, y/n, z/n)


def rot3_from_quat(q):
    w, x, y, z = q
    xx, yy, zz = x*x, y*y, z*z
    xy, xz, yz = x*y, x*z, y*z
    wx, wy, wz = w*x, w*y, w*z
    return [
        [1 - 2*(yy+zz), 2*(xy - wz),     2*(xz + wy)],
        [2*(xy + wz),   1 - 2*(xx+zz),   2*(yz - wx)],
        [2*(xz - wy),   2*(yz + wx),     1 - 2*(xx+yy)],
    ]


def quat_slerp(q0, q1, t):
    w0, x0, y0, z0 = q0
    w1, x1, y1, z1 = q1
    dot = w0*w1 + x0*x1 + y0*y1 + z0*z1
    if dot < 0.0:
        dot = -dot
        w1, x1, y1, z1 = -w1, -x1, -y1, -z1
    if dot > 0.9995:
        w = w0 + (w1 - w0)*t
        x = x0 + (x1 - x0)*t
        y = y0 + (y1 - y0)*t
        z = z0 + (z1 - z0)*t
        n = math.sqrt(w*w + x*x + y*y + z*z) or 1.0
        return (w/n, x/n, y/n, z/n)
    theta_0 = math.acos(max(-1.0, min(1.0, dot)))
    sin_0 = math.sin(theta_0) or 1e-8
    theta = theta_0 * t
    s0 = math.sin(theta_0 - theta) / sin_0
    s1 = math.sin(theta) / sin_0
    return (w0*s0 + w1*s1, x0*s0 + x1*s1, y0*s0 + y1*s1, z0*s0 + z1*s1)


def matrix_trs_lerp(m0: np.ndarray, m1: np.ndarray, t: float) -> np.ndarray:
    tt = m0[:3, 3] + (m1[:3, 3] - m0[:3, 3]) * t
    q0 = quat_from_rot3(m0[:3, :3])
    q1 = quat_from_rot3(m1[:3, :3])
    qt = quat_slerp(q0, q1, t)
    rt = rot3_from_quat(qt)
    out = np.eye(4, dtype=np.float32)
    out[:3, :3] = rt
    out[:3, 3] = tt
    return out


# Data models

@dataclass
class Part:
    referent: str
    name: str
    size: Tuple[float, float, float]
    cframe: np.ndarray  # 4×4 float32


@dataclass
class Motor6D:
    name: str
    part0_ref: str
    part1_ref: str
    c0: np.ndarray       # 4×4 float32
    c1_inv: np.ndarray   # 4×4 float32 (pre-inverted C1)


@dataclass
class Keyframe:
    time: float
    pose_by_part_name: Dict[str, np.ndarray]


# Parse rig

def load_rig(rig_path: str) -> Tuple[Dict[str, Part], List[Motor6D]]:
    tree = ET.parse(rig_path)
    root = tree.getroot()

    parts: Dict[str, Part] = {}
    motors: List[Motor6D] = []

    for item in root.iter("Item"):
        cls = item.attrib.get("class", "")
        ref = item.attrib.get("referent", "")
        props = item.find("Properties")
        if props is None:
            continue

        size_elem = find_prop(
            props, "Vector3", ["size", "Size", "InitialSize"])
        cf_elem = find_prop(props, "CoordinateFrame", ["CFrame"]) or find_prop(
            props, "CFrame", ["CFrame"])

        if size_elem is not None and cf_elem is not None:
            name = _text(find_prop(props, "string", ["Name"]), cls)
            size = parse_vector3(size_elem)
            pos, r = parse_cframe(cf_elem)
            parts[ref] = Part(ref, name, size, np_from_cframe(pos, r))

        if cls == "Motor6D":
            name = _text(find_prop(props, "string", ["Name"]))

            p0 = find_prop(props, "Ref", ["Part0"])
            p1 = find_prop(props, "Ref", ["Part1"])
            c0e = find_prop(props, "CoordinateFrame", ["C0"]) or find_prop(
                props, "CFrame", ["C0"])
            c1e = find_prop(props, "CoordinateFrame", ["C1"]) or find_prop(
                props, "CFrame", ["C1"])
            if p0 is None or p1 is None or c0e is None or c1e is None:
                continue

            pos0, r0 = parse_cframe(c0e)
            pos1, r1 = parse_cframe(c1e)

            motors.append(Motor6D(
                name=name,
                part0_ref=_text(p0),
                part1_ref=_text(p1),
                c0=np_from_cframe(pos0, r0),
                c1_inv=np_inv_rigid(np_from_cframe(pos1, r1)),
            ))

    return parts, motors


# Parse anim

def load_animation(anim_path: str) -> List[Keyframe]:
    tree = ET.parse(anim_path)
    root = tree.getroot()

    keys: List[Keyframe] = []
    for item in root.iter("Item"):
        if item.attrib.get("class") != "Keyframe":
            continue
        props = item.find("Properties")
        if props is None:
            continue

        t_elem = find_prop(props, "float", ["Time"])
        if t_elem is None:
            continue
        t = float(_text(t_elem, "0"))

        poses: Dict[str, np.ndarray] = {}
        for pose_item in item.iter("Item"):
            if pose_item.attrib.get("class") != "Pose":
                continue
            pprops = pose_item.find("Properties")
            if pprops is None:
                continue

            pname = _text(find_prop(pprops, "string", ["Name"]))
            cf = find_prop(pprops, "CoordinateFrame", ["CFrame"]) or find_prop(
                pprops, "CFrame", ["CFrame"])
            if not pname or cf is None:
                continue

            pos, r = parse_cframe(cf)
            poses[pname] = np_from_cframe(pos, r)

        keys.append(Keyframe(t, poses))

    keys.sort(key=lambda k: k.time)
    return keys


def sample_keys(keys: List[Keyframe], t: float) -> Tuple[Keyframe, Keyframe, float]:
    if t <= keys[0].time:
        return keys[0], keys[0], 0.0
    if t >= keys[-1].time:
        return keys[-1], keys[-1], 0.0
    for i in range(len(keys) - 1):
        a, b = keys[i], keys[i+1]
        if a.time <= t <= b.time:
            span = (b.time - a.time) or 1e-6
            return a, b, (t - a.time) / span
    return keys[-1], keys[-1], 0.0


# Root picking

def pick_root_ref(parts: Dict[str, Part]) -> str:
    preferred = ("HumanoidRootPart", "LowerTorso",
                 "Torso", "UpperTorso", "Head")
    for want in preferred:
        for ref, p in parts.items():
            if p.name == want:
                return ref
    return next(iter(parts.keys()))


# OBJ loading

def detect_rig_prefix(parts: Dict[str, Part]) -> str:
    # R6 has these part names; R15 has UpperTorso/LowerTorso etc.
    names = {p.name for p in parts.values()}
    if "Torso" in names and "UpperTorso" not in names:
        return "R6"
    return "R15"


def build_placeholder_rig(keys: List[Keyframe]) -> Tuple[Dict[str, Part], List]:
    """Build placeholder cube-parts for non-rig animations (tools, vehicles, etc.).

    Creates one small cube per unique pose name, laid out in a grid.
    Returns an empty motors list since there is no joint hierarchy.
    """
    all_names: set = set()
    for k in keys:
        all_names.update(k.pose_by_part_name.keys())

    parts: Dict[str, Part] = {}
    for idx, name in enumerate(sorted(all_names)):
        m = np.eye(4, dtype=np.float32)
        grid_x = idx % 5
        grid_z = idx // 5
        m[0, 3] = grid_x * 1.5 - 3.0
        m[2, 3] = grid_z * 1.5
        ref = f"__placeholder_{idx}__"
        parts[ref] = Part(ref, name, (0.5, 0.5, 0.5), m)

    return parts, []


def obj_path_for_part(mesh_dir: str, prefix: str, part_name: str) -> str:
    return os.path.join(mesh_dir, f"{prefix}{part_name}.obj")


def _obj_to_gl_mesh(path: str) -> dict:
    """Parse an OBJ file directly into a GL-ready numpy dict."""
    positions = []
    faces = []
    try:
        with open(path, 'r', encoding='utf-8', errors='replace') as f:
            for line in f:
                if line.startswith('v '):
                    p = line.split()
                    positions.append((float(p[1]), float(p[2]), float(p[3])))
                elif line.startswith('f '):
                    p = line.split()[1:]
                    idxs = [int(t.split('/')[0]) - 1 for t in p]
                    for i in range(1, len(idxs) - 1):
                        faces.append((idxs[0], idxs[i], idxs[i + 1]))
    except Exception as e:
        print(f"[WARN] OBJ parse failed for {path}: {e}")
        return _cube_gl_mesh(1.0, 1.0, 1.0)

    if not positions or not faces:
        return _cube_gl_mesh(1.0, 1.0, 1.0)

    pts = np.array(positions, dtype=np.float32)
    tri = np.array(faces, dtype=np.int64)
    v0, v1, v2 = pts[tri[:, 0]], pts[tri[:, 1]], pts[tri[:, 2]]
    face_norms = np.cross(v1 - v0, v2 - v0).astype(np.float32)
    lengths = np.linalg.norm(face_norms, axis=1, keepdims=True)
    face_norms /= np.where(lengths < 1e-8, 1.0, lengths)
    verts = np.stack([v0, v1, v2], axis=1).reshape(-1, 3)
    norms = np.repeat(face_norms, 3, axis=0)
    n_verts = len(verts)
    idx = np.arange(n_verts, dtype=np.uint32).reshape(-1, 3)
    colors = np.ones((n_verts, 3), dtype=np.float32)
    return {
        'verts':  np.ascontiguousarray(verts),
        'norms':  np.ascontiguousarray(norms),
        'idx':    np.ascontiguousarray(idx),
        'colors': np.ascontiguousarray(colors),
    }


def _cube_gl_mesh(sx: float, sy: float, sz: float) -> dict:
    """Build a GL-ready numpy dict for a box mesh."""
    hw, hh, hd = sx / 2, sy / 2, sz / 2
    v = np.array([
        [-hw, -hh, -hd], [hw, -hh, -hd], [hw, hh, -hd], [-hw, hh, -hd],
        [-hw, -hh,  hd], [hw, -hh,  hd], [hw, hh,  hd], [-hw, hh,  hd],
    ], dtype=np.float32)
    quads = [(0,1,2,3),(5,4,7,6),(4,0,3,7),(1,5,6,2),(3,2,6,7),(4,5,1,0)]
    quad_norms = [
        np.array([0,0,-1],dtype=np.float32), np.array([0,0,1],dtype=np.float32),
        np.array([-1,0,0],dtype=np.float32), np.array([1,0,0],dtype=np.float32),
        np.array([0,1,0],dtype=np.float32),  np.array([0,-1,0],dtype=np.float32),
    ]
    all_v, all_n, all_i, cur = [], [], [], 0
    for (a,b,c,d), n in zip(quads, quad_norms):
        for tri in [(a,b,c),(a,c,d)]:
            for vi in tri:
                all_v.append(v[vi])
                all_n.append(n)
            all_i.append([cur, cur+1, cur+2])
            cur += 3
    verts  = np.array(all_v, dtype=np.float32)
    norms  = np.array(all_n, dtype=np.float32)
    idx    = np.array(all_i, dtype=np.uint32)
    colors = np.ones((len(verts), 3), dtype=np.float32)
    return {
        'verts':  np.ascontiguousarray(verts),
        'norms':  np.ascontiguousarray(norms),
        'idx':    np.ascontiguousarray(idx),
        'colors': np.ascontiguousarray(colors),
    }


def load_obj_mesh(mesh_dir: str, prefix: str, part_name: str,
                  fallback_size: Tuple[float, float, float]) -> dict:
    candidates = [obj_path_for_part(mesh_dir, prefix, part_name)]
    other = "R15" if prefix == "R6" else "R6"
    candidates.append(obj_path_for_part(mesh_dir, other, part_name))
    for path in candidates:
        if os.path.exists(path):
            return _obj_to_gl_mesh(path)
    return _cube_gl_mesh(*fallback_size)


def _compute_scene_bounds(parts) -> tuple:
    """Return (xmin, xmax, ymin, ymax, zmin, zmax) from part CFrames + sizes."""
    all_x, all_y, all_z = [], [], []
    for p in parts.values():
        cx = float(p.cframe[0, 3])
        cy = float(p.cframe[1, 3])
        cz = float(p.cframe[2, 3])
        sx, sy, sz = p.size
        all_x += [cx - sx / 2, cx + sx / 2]
        all_y += [cy - sy / 2, cy + sy / 2]
        all_z += [cz - sz / 2, cz + sz / 2]
    if not all_x:
        return (-1.0, 1.0, -1.0, 1.0, -1.0, 1.0)
    return (min(all_x), max(all_x), min(all_y), max(all_y), min(all_z), max(all_z))


def _prefs_path() -> str:
    base = os.environ.get("LOCALAPPDATA", os.path.expanduser("~"))
    return os.path.join(base, "SubplaceJoiner", "preview_prefs.json")


def load_preview_prefs() -> dict:
    try:
        with open(_prefs_path(), "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def save_preview_prefs(prefs: dict) -> None:
    try:
        path = _prefs_path()
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(prefs, f)
    except Exception:
        pass


class AnimPreviewWidget(QWidget):
    SLIDER_STEPS = 1000

    def __init__(self, rig_path: str, anim_path: str, mesh_dir: str = "R15AndR6Parts", parent=None, preloaded: dict = None, freeze_widgets=None, open_externally_fn=None, initial_camera=None, bg_color=None):
        super().__init__(parent)

        self._playing = True
        self._slider_dragging = False
        self._freeze_widgets = list(freeze_widgets) if freeze_widgets else []

        # Load rig / animation data
        if preloaded is not None:
            self.parts = preloaded["parts"]
            self.motors = preloaded["motors"]
            self.keys = preloaded["keys"]
            self.prefix = preloaded["prefix"]
            _meshes = preloaded["meshes"]
            self._is_placeholder = preloaded.get("is_placeholder", False)
        else:
            self.parts, self.motors = load_rig(rig_path)
            self.prefix = detect_rig_prefix(self.parts)
            self.keys = load_animation(anim_path)
            _meshes = None
            self._is_placeholder = False

        if not self.parts:
            raise RuntimeError(
                "Loaded 0 parts from rig. Wrong rig file or unexpected format.")
        if not self.keys:
            raise RuntimeError(
                "Loaded 0 keyframes from animation. output.rbxmx must be a KeyframeSequence export.")

        # Build per-part GL-ready numpy dicts
        gl_meshes = {}
        for ref, p in self.parts.items():
            gl_meshes[ref] = (
                _meshes[ref] if _meshes is not None
                else load_obj_mesh(mesh_dir, self.prefix, p.name, p.size)
            )

        # Per-part colors and initial world transforms
        colors = {}
        initial_transforms = {}
        for ref, p in self.parts.items():
            is_hrp = p.name.lower() == "humanoidrootpart"
            colors[ref] = (1.0, 0.2, 0.2, 0.5) if is_hrp else (
                0.86, 0.86, 0.88, 1.0)
            initial_transforms[ref] = p.cframe

        scene_bounds = _compute_scene_bounds(self.parts)

        # Layout
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Direct OpenGL widget — renders to screen at GPU speed, no screenshot pipeline
        self._gl = AnimGLWidget(gl_meshes, colors, initial_transforms, scene_bounds,
                                parent=self, initial_camera=initial_camera, bg_color=bg_color)
        layout.addWidget(self._gl, stretch=1)

        # Control bar
        ctrl = QWidget(self)
        ctrl.setFixedHeight(36)
        ctrl_layout = QHBoxLayout(ctrl)
        ctrl_layout.setContentsMargins(4, 2, 4, 2)
        ctrl_layout.setSpacing(6)

        self._play_btn = QPushButton("Pause")
        self._play_btn.setFixedWidth(80)
        self._play_btn.clicked.connect(self._toggle_play)
        ctrl_layout.addWidget(self._play_btn)

        self._slider = QSlider(Qt.Horizontal)
        self._slider.setRange(0, self.SLIDER_STEPS)
        self._slider.setValue(0)
        self._slider.sliderPressed.connect(self._on_slider_press)
        self._slider.sliderMoved.connect(self._on_slider_move)
        self._slider.sliderReleased.connect(self._on_slider_release)
        ctrl_layout.addWidget(self._slider, stretch=1)

        self._time_label = QLabel("0.00 / 0.00s")
        self._time_label.setFixedWidth(90)
        self._time_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        ctrl_layout.addWidget(self._time_label)

        # Options button — wireframe, FPS mode, timescale
        self.timescale = 1.0
        _prefs = load_preview_prefs()

        self.options_menu = QMenu(self)

        reset_action = self.options_menu.addAction("Reset View")
        reset_action.triggered.connect(lambda: self._gl.reset_view())
        self.options_menu.addSeparator()

        wf_action = self.options_menu.addAction("Wireframe")
        wf_action.setCheckable(True)
        wf_action.setChecked(bool(_prefs.get("wireframe", False)))
        wf_action.toggled.connect(self._on_wireframe_toggled)

        self._fps_action = self.options_menu.addAction("FPS Freecam")
        self._fps_action.setCheckable(True)
        self._fps_action.setChecked(bool(_prefs.get("fps_mode", False)))
        self._fps_action.toggled.connect(self._on_fps_toggled)

        grid_action = self.options_menu.addAction("Show Grid")
        grid_action.setCheckable(True)
        grid_action.setChecked(bool(_prefs.get("show_grid", True)))
        grid_action.toggled.connect(self._on_grid_toggled)

        auto_rotate_action = self.options_menu.addAction("Auto Rotate")
        auto_rotate_action.setCheckable(True)
        auto_rotate_action.setChecked(bool(_prefs.get("auto_rotate", False)))
        auto_rotate_action.toggled.connect(self._on_auto_rotate_toggled)

        self.options_menu.addSeparator()

        ts_container = QWidget()
        ts_layout = QVBoxLayout(ts_container)
        ts_layout.setContentsMargins(10, 2, 10, 2)
        ts_layout.setSpacing(0)
        self._ts_label = QLabel("Timescale: 1.0x")
        ts_layout.addWidget(self._ts_label)
        ts_slider = QSlider(Qt.Horizontal)
        ts_slider.setRange(1, 80)   # 0.1x – 8.0x
        ts_slider.setValue(10)
        ts_slider.setFixedWidth(120)
        ts_slider.valueChanged.connect(self._on_timescale_changed)
        ts_layout.addWidget(ts_slider)
        ts_wa = QWidgetAction(self)
        ts_wa.setDefaultWidget(ts_container)
        self.options_menu.addAction(ts_wa)

        if open_externally_fn is not None:
            self.options_menu.addSeparator()
            self.options_menu.addAction("Open Externally", open_externally_fn)

        # Apply saved prefs to the GL widget
        if _prefs.get("wireframe", False):
            self._gl.toggle_wireframe()
        if _prefs.get("fps_mode", False):
            self._gl.toggle_fps()
        if not _prefs.get("show_grid", True):
            self._gl.toggle_grid()
        if _prefs.get("auto_rotate", False):
            self._gl.toggle_auto_rotate()

        layout.addWidget(ctrl)

        # Root + timing
        self.root_ref = pick_root_ref(self.parts)
        self.root_name = self.parts[self.root_ref].name
        self.base_root_world = self.parts[self.root_ref].cframe

        self.time = 0.0
        self.duration = max(self.keys[-1].time, 1e-6)
        self._update_time_label()

        self._last_tick_time = _time.perf_counter()
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.tick)
        hz = QApplication.primaryScreen().refreshRate()
        self.timer.start(max(16, int(1000 / hz)))  # cap at ~60 fps
        self._apply_freeze()  # freeze companion widgets since we start in playing state

        # Sync the FPS checkbox when WASD triggers FPS mode directly
        self._gl.fps_mode_changed.connect(self._sync_fps_checkbox)

    def _apply_freeze(self) -> None:
        """Freeze companion widgets (e.g. the table view) while playing to avoid
        expensive repaints competing with the GL animation loop."""
        for w in self._freeze_widgets:
            try:
                w.setUpdatesEnabled(not self._playing)
            except Exception:
                pass

    # playback controls

    def _toggle_play(self):
        self._playing = not self._playing
        self._play_btn.setText("Pause" if self._playing else "Play")
        self._apply_freeze()

    def _on_slider_press(self):
        self._slider_dragging = True

    def _on_slider_move(self, value: int):
        self.time = (value / self.SLIDER_STEPS) * self.duration
        self._update_time_label()
        self._render_frame()

    def _on_slider_release(self):
        self._slider_dragging = False

    def _update_time_label(self):
        self._time_label.setText(f"{self.time:.2f} / {self.duration:.2f}s")

    def _update_slider(self):
        if not self._slider_dragging:
            val = int((self.time / self.duration) * self.SLIDER_STEPS)
            self._slider.setValue(val)

    # animation tick

    def tick(self):
        now = _time.perf_counter()
        # cap at 100 ms to avoid big jumps after lag
        dt = min(now - self._last_tick_time, 0.1)
        self._last_tick_time = now
        if self._playing and not self._slider_dragging:
            self.time += dt * self.timescale
            if self.time > self.duration:
                self.time = 0.0
            self._update_slider()
            self._update_time_label()
            self._render_frame()

    def _render_frame(self):
        k0, k1, alpha = sample_keys(self.keys, self.time)

        pose: Dict[str, np.ndarray] = {}
        names = set(k0.pose_by_part_name.keys()) | set(
            k1.pose_by_part_name.keys())

        for n in names:
            a = k0.pose_by_part_name.get(n)
            b = k1.pose_by_part_name.get(n)
            if a is None:
                pose[n] = b if b is not None else _NP_IDENT
            elif b is None:
                pose[n] = a
            else:
                pose[n] = matrix_trs_lerp(a, b, alpha)

        if self._is_placeholder:
            world: Dict[str, np.ndarray] = {}
            for ref, p in self.parts.items():
                T = pose.get(p.name, _NP_IDENT)
                world[ref] = p.cframe @ T
        else:
            root_pose = pose.get(self.root_name, _NP_IDENT)
            world = {self.root_ref: self.base_root_world @ root_pose}

            for _ in range(min(len(self.motors) + 2, 15)):
                changed = False
                for m in self.motors:
                    if m.part0_ref not in world:
                        continue
                    if m.part1_ref in world:
                        continue
                    child = self.parts.get(m.part1_ref)
                    if child is None:
                        continue
                    T = pose.get(child.name, _NP_IDENT)
                    world[m.part1_ref] = world[m.part0_ref] @ m.c0 @ T @ m.c1_inv
                    changed = True
                if not changed:
                    break

        self._gl.set_transforms(world)
        self._gl.update()

    def _on_wireframe_toggled(self, checked: bool) -> None:
        if self._gl._wireframe != checked:
            self._gl.toggle_wireframe()
        prefs = load_preview_prefs()
        prefs["wireframe"] = checked
        save_preview_prefs(prefs)

    def _sync_fps_checkbox(self, checked: bool) -> None:
        """Called by the GL widget signal — updates checkbox without re-triggering toggle."""
        self._fps_action.blockSignals(True)
        self._fps_action.setChecked(checked)
        self._fps_action.blockSignals(False)
        prefs = load_preview_prefs()
        prefs["fps_mode"] = checked
        save_preview_prefs(prefs)

    def _on_fps_toggled(self, checked: bool) -> None:
        if self._gl._fps_mode != checked:
            self._gl.toggle_fps()
        prefs = load_preview_prefs()
        prefs["fps_mode"] = checked
        save_preview_prefs(prefs)

    def _on_grid_toggled(self, checked: bool) -> None:
        if self._gl._show_grid != checked:
            self._gl.toggle_grid()
        prefs = load_preview_prefs()
        prefs["show_grid"] = checked
        save_preview_prefs(prefs)

    def _on_auto_rotate_toggled(self, checked: bool) -> None:
        if self._gl._auto_rotate != checked:
            self._gl.toggle_auto_rotate()
        prefs = load_preview_prefs()
        prefs["auto_rotate"] = checked
        save_preview_prefs(prefs)

    def _on_timescale_changed(self, value: int) -> None:
        self.timescale = value / 10.0
        if hasattr(self, "_ts_label"):
            self._ts_label.setText(f"Timescale: {self.timescale:.1f}x")

    def closeEvent(self, event):
        try:
            self.timer.stop()
        except Exception:
            pass
        self._playing = False
        self._apply_freeze()  # always re-enable frozen widgets on close
        # AnimGLWidget cleans up its own GL resources via aboutToBeDestroyed signal
        super().closeEvent(event)


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: python animpreview.py <RIG.rbxmx> <ANIM.rbxmx>")
        sys.exit(2)

    app = QApplication(sys.argv)
    w = AnimPreviewWidget(sys.argv[1], sys.argv[2], mesh_dir="R15AndR6Parts")
    w.resize(1100, 800)
    w.show()
    sys.exit(app.exec())
