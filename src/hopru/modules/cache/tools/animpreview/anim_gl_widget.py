"""
Direct OpenGL animation viewer — replaces the off-screen PyVista screenshot pipeline.

Renders straight to the window surface at native GPU speed.
"""
import math
import time as _time
import numpy as np

from PySide6.QtOpenGLWidgets import QOpenGLWidget
from PySide6.QtGui import QSurfaceFormat, QGuiApplication
from PySide6.QtCore import Qt, QTimer, Signal

try:
    from OpenGL.GL import (
        glClear, glClearColor, glEnable, glDisable, glBlendFunc, glViewport, glPolygonMode,
        glScissor, glLineWidth, GL_MULTISAMPLE, GL_SCISSOR_TEST,
        glGenVertexArrays, glBindVertexArray, glDeleteVertexArrays,
        glGenBuffers, glBindBuffer, glBufferData, glDeleteBuffers,
        glEnableVertexAttribArray, glVertexAttribPointer,
        glDrawElements, glDrawArrays,
        glCreateShader, glShaderSource, glCompileShader, glGetShaderiv,
        glGetShaderInfoLog, glCreateProgram, glAttachShader, glLinkProgram,
        glGetProgramiv, glGetProgramInfoLog, glDeleteShader, glDeleteProgram,
        glUseProgram, glGetUniformLocation,
        glUniformMatrix4fv, glUniform3f, glUniform1f,
        GL_COLOR_BUFFER_BIT, GL_DEPTH_BUFFER_BIT,
        GL_DEPTH_TEST, GL_BLEND, GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA,
        GL_TRIANGLES, GL_LINES, GL_UNSIGNED_INT, GL_FLOAT, GL_FALSE, GL_TRUE,
        GL_ARRAY_BUFFER, GL_ELEMENT_ARRAY_BUFFER, GL_STATIC_DRAW,
        GL_VERTEX_SHADER, GL_FRAGMENT_SHADER, GL_COMPILE_STATUS, GL_LINK_STATUS,
        GL_FRONT_AND_BACK, GL_FILL, GL_LINE,
    )
    _HAS_GL = True
except ImportError:
    _HAS_GL = False

# GLSL shaders

_MESH_VERT = """\
#version 330 core
layout(location=0) in vec3 aPos;
layout(location=1) in vec3 aNorm;
layout(location=2) in vec3 aColor;
uniform mat4 uMVP;
uniform mat4 uModel;
out vec3 vNorm;
out vec3 vPos;
out vec3 vColor;
void main(){
    gl_Position = uMVP   * vec4(aPos, 1.0);
    vPos        = vec3(uModel * vec4(aPos, 1.0));
    vNorm       = normalize(mat3(uModel) * aNorm);  // normalize after model transform
    vColor      = aColor;
}
"""

_MESH_FRAG = """\
#version 330 core
in vec3 vNorm;
in vec3 vPos;
in vec3 vColor;
uniform vec3  uColor;
uniform float uOpacity;
uniform vec3  uCamPos;
uniform vec3  uCamR;
uniform vec3  uCamU;
out vec4 fragColor;
void main(){
    vec3 n = normalize(vNorm);

    // Camera-relative orthonormal frame (passed as uniforms, stable across all fragments)
    vec3 V    = normalize(uCamPos - vPos);
    vec3 camR = uCamR;
    vec3 camU = uCamU;

    // Three lights defined in camera space
    vec3 l0 = normalize(V + camR * 0.6 + camU * 0.8);          // key:  upper-right of cam
    vec3 l1 = normalize(-camR * 1.0 + camU * 0.3 - V * 0.5);  // fill: left, slightly behind
    vec3 l2 = normalize(-V + camU * 0.5);                       // rim:  behind model, upper

    vec3 keyCol  = vec3(1.00, 0.93, 0.82);   // warm yellow-white
    vec3 fillCol = vec3(0.60, 0.72, 1.00);   // cool sky-blue
    vec3 rimCol  = vec3(0.75, 0.80, 0.90);   // neutral-cool
    vec3 ambient = vec3(0.38, 0.38, 0.42);
    vec3 light = ambient
               + keyCol  * max(dot(n, l0), 0.0) * 0.85
               + fillCol * max(dot(n, l1), 0.0) * 0.22
               + rimCol  * max(dot(n, l2), 0.0) * 0.22;
    fragColor = vec4(vColor * uColor * clamp(light, 0.0, 1.0), uOpacity);
}
"""

_GRID_VERT = """\
#version 330 core
layout(location=0) in vec3 aPos;
uniform mat4 uVP;
void main(){ gl_Position = uVP * vec4(aPos, 1.0); }
"""

_GRID_FRAG = """\
#version 330 core
out vec4 fragColor;
void main(){ fragColor = vec4(0.5, 0.5, 0.62, 0.55); }
"""

_AXES_VERT = """\
#version 330 core
layout(location=0) in vec3 aPos;
layout(location=1) in vec3 aColor;
uniform mat4 uMVP;
out vec3 vColor;
void main(){ gl_Position = uMVP * vec4(aPos, 1.0); vColor = aColor; }
"""

_AXES_FRAG = """\
#version 330 core
in vec3 vColor;
out vec4 fragColor;
void main(){ fragColor = vec4(vColor, 1.0); }
"""

# Math helpers (pure numpy — no Qt math types needed)


def _perspective(fov_deg: float, aspect: float, near: float, far: float) -> np.ndarray:
    f = 1.0 / math.tan(math.radians(fov_deg) * 0.5)
    nf = 1.0 / (near - far)
    return np.array([
        [f / aspect, 0,  0,                    0],
        [0,          f,  0,                    0],
        [0,          0,  (far + near) * nf,    2 * far * near * nf],
        [0,          0, -1,                    0],
    ], dtype=np.float32)


def _look_at(eye: np.ndarray, target: np.ndarray, up: np.ndarray = None) -> np.ndarray:
    if up is None:
        up = np.array([0.0, 1.0, 0.0], dtype=np.float32)
    f = target - eye
    fn = float(np.linalg.norm(f))
    if fn < 1e-8:
        return np.eye(4, dtype=np.float32)
    f /= fn
    r = np.cross(f, up)
    rn = float(np.linalg.norm(r))
    if rn < 1e-8:                          # looking straight up/down
        up = np.array([0.0, 0.0, 1.0], dtype=np.float32)
        r = np.cross(f, up)
        rn = float(np.linalg.norm(r))
    r /= rn
    u = np.cross(r, f)
    return np.array([
        [r[0],  r[1],  r[2], -float(np.dot(r, eye))],
        [u[0],  u[1],  u[2], -float(np.dot(u, eye))],
        [-f[0], -f[1], -f[2],  float(np.dot(f, eye))],
        [0,     0,     0,     1],
    ], dtype=np.float32)


def _make_grid(cx: float, cz: float, y: float, half: float, n: int = 10) -> np.ndarray:
    v: list = []
    step = half * 2 / n
    for i in range(n + 1):
        t = -half + i * step
        v += [cx + t, y, cz - half,  cx + t, y, cz + half]
        v += [cx - half, y, cz + t,  cx + half, y, cz + t]
    return np.array(v, dtype=np.float32)

# Shader helpers


def _compile_shader(src: str, kind: int) -> int:
    s = glCreateShader(kind)
    glShaderSource(s, src)
    glCompileShader(s)
    if not glGetShaderiv(s, GL_COMPILE_STATUS):
        raise RuntimeError(glGetShaderInfoLog(s).decode())
    return s


def _link_program(vert_src: str, frag_src: str) -> int:
    v = _compile_shader(vert_src, GL_VERTEX_SHADER)
    f = _compile_shader(frag_src, GL_FRAGMENT_SHADER)
    p = glCreateProgram()
    glAttachShader(p, v)
    glAttachShader(p, f)
    glLinkProgram(p)
    if not glGetProgramiv(p, GL_LINK_STATUS):
        raise RuntimeError(glGetProgramInfoLog(p).decode())
    glDeleteShader(v)
    glDeleteShader(f)
    return p

# Main widget


_IDENTITY = np.eye(4, dtype=np.float32)
_SCAN_W = 0x11
_SCAN_A = 0x1E
_SCAN_S = 0x1F
_SCAN_D = 0x20
_SCAN_Q = 0x10
_SCAN_E = 0x12
_SCAN_SPACE = 0x39
_SCAN_LSHIFT = 0x2A
_SCAN_WASD = {_SCAN_W, _SCAN_A, _SCAN_S, _SCAN_D}


_CAMERA_FOV = 45.0   # shared FOV for both orbit and FPS - keeps transition seamless


class AnimGLWidget(QOpenGLWidget):
    # emitted when FPS mode is toggled by any means
    fps_mode_changed = Signal(bool)

    """
    GPU-direct OpenGL animation viewer.

    No screenshots, no numpy->QPixmap pipeline, no off-screen plotter.
    Renders directly to the window surface at full GPU speed.

    Parameters
    gl_meshes : dict[ref, dict]
        ref -> {'verts': float32 Nx3, 'norms': float32 Nx3, 'idx': uint32 Mx3}
    colors : dict[ref, tuple]
        ref -> (r, g, b, opacity)
    initial_transforms : dict[ref, np.ndarray]
        ref -> 4×4 row-major float32 world matrix (from vtk_to_np)
    scene_bounds : tuple
        (xmin, xmax, ymin, ymax, zmin, zmax) for camera and grid placement
    """

    def __init__(self, gl_meshes, colors, initial_transforms, scene_bounds, parent=None, bg_color=None, initial_camera=None):
        super().__init__(parent)

        fmt = QSurfaceFormat()
        fmt.setDepthBufferSize(24)
        fmt.setSamples(0)
        fmt.setVersion(3, 3)
        fmt.setProfile(QSurfaceFormat.CoreProfile)
        self.setFormat(fmt)

        self.setMinimumSize(100, 100)
        self.setMouseTracking(True)

        self._gl_meshes = gl_meshes
        self._colors = colors
        self._transforms = {ref: t.copy()
                            for ref, t in initial_transforms.items()}

        xmin, xmax, ymin, ymax, zmin, zmax = scene_bounds
        cx = (xmin + xmax) / 2
        cy = (ymin + ymax) / 2
        cz = (zmin + zmax) / 2
        size = max(xmax - xmin, ymax - ymin, zmax - zmin)

        self._target = np.array([cx, cy, cz], dtype=np.float32)
        self._dist = size * 3.5 if size > 0 else 10.0
        self._near = max(0.001, self._dist * 0.001)
        self._far = self._dist * 50.0
        self._az = 205.0   # azimuth  (degrees)
        self._el = 20.0    # elevation (degrees)

        # Store defaults for reset_view()
        self._default_target = self._target.copy()
        self._default_dist = self._dist
        self._default_az = self._az
        self._default_el = self._el

        # FPS camera state
        self.setFocusPolicy(Qt.StrongFocus)
        self._fps_mode = False
        self._cam_yaw = self._az
        self._cam_pitch = self._el
        self._cam_pos = self._eye()   # start at the same position as the orbit eye
        self._keys_pressed: set = set()
        self._fps_last_tick: float = 0.0
        self._fps_timer = QTimer(self)
        self._fps_timer.setInterval(16)     # ~60 Hz movement tick
        self._fps_timer.timeout.connect(self._fps_tick)

        self._auto_rotate = False
        self._auto_rotate_timer = QTimer(self)
        self._auto_rotate_timer.setInterval(16)
        self._auto_rotate_timer.timeout.connect(self._auto_rotate_tick)

        grid_half = max(xmax - xmin, zmax - zmin) * 1.5 if size > 0 else 10.0
        self._grid_verts = _make_grid(cx, cz, float(ymin), grid_half)

        self._bg_color = bg_color if bg_color is not None else (
            0.118, 0.118, 0.129)
        self._wireframe = False
        self._show_grid = True
        self._drag_last = None

        # Restore camera from a previous view so switching assets doesn't reset it
        if initial_camera is not None:
            self._az = initial_camera.get("az",    self._az)
            self._el = initial_camera.get("el",    self._el)
            self._dist = initial_camera.get("dist",  self._dist)
            if "target" in initial_camera:
                self._target = initial_camera["target"].copy()
            self._near = max(0.001, self._dist * 0.001)
            self._far = self._dist * 50.0
            self._fps_mode = initial_camera.get("fps_mode", False)
            self._cam_yaw = initial_camera.get("cam_yaw",  -self._az)
            self._cam_pitch = initial_camera.get("cam_pitch", self._el)
            self._cam_pos = initial_camera["cam_pos"].copy(
            ) if "cam_pos" in initial_camera else self._eye().copy()
            if self._fps_mode:
                self._fps_last_tick = _time.perf_counter()
                self._fps_timer.start()

        # GL handles (filled in initializeGL)
        self._prog = 0
        self._grid_prog = 0
        self._axes_prog = 0
        self._vaos:      dict = {}
        self._vbos:      dict = {}
        self._idx_counts: dict = {}
        self._grid_vao = 0
        self._grid_vbo = 0
        self._grid_n = 0
        self._axes_vao = 0
        self._axes_vbo = (0, 0)
        self._ready = False
        self._u: dict = {}  # cached uniform locations (filled in initializeGL)
        self._vp_cache: np.ndarray = np.eye(4, dtype=np.float32)
        self._axes_vp_cache: np.ndarray = np.eye(4, dtype=np.float32)
        self._vp_dirty: bool = True   # recompute VP on first paint

    # Public API

    def set_transforms(self, world: dict) -> None:
        """Update per-part world matrices. world: ref -> np.ndarray (4×4 float32)"""
        self._transforms.update(world)

    def toggle_wireframe(self) -> None:
        self._wireframe = not self._wireframe
        self.update()

    def toggle_grid(self) -> None:
        self._show_grid = not self._show_grid
        self.update()

    def reset_view(self) -> None:
        """Restore the camera to the original scene-fitted position."""
        if self._fps_mode:
            self._fps_mode = False
            self._fps_timer.stop()
            self._keys_pressed.clear()
            self.fps_mode_changed.emit(False)
            if self._auto_rotate:
                self._auto_rotate_timer.start()
        self._target = self._default_target.copy()
        self._dist = self._default_dist
        self._az = self._default_az
        self._el = self._default_el
        self._near = max(0.001, self._dist * 0.001)
        self._far = self._dist * 50.0
        self._cam_pos = self._eye().copy()
        self._vp_dirty = True
        self.update()

    def toggle_auto_rotate(self) -> None:
        self._auto_rotate = not self._auto_rotate
        if self._auto_rotate:
            self._auto_rotate_timer.start()
        else:
            self._auto_rotate_timer.stop()

    def get_camera_state(self) -> dict:
        return {
            "az":        self._az,
            "el":        self._el,
            "dist":      self._dist,
            "target":    self._target.copy(),
            "fps_mode":  self._fps_mode,
            "cam_pos":   self._cam_pos.copy(),
            "cam_yaw":   self._cam_yaw,
            "cam_pitch": self._cam_pitch,
        }

    def toggle_fps(self) -> None:
        """Toggle between orbit and FPS camera modes."""
        if self._fps_mode:
            # Exit FPS: sync orbit angles so the view doesn't jump
            self._az = -self._cam_yaw
            self._el = self._cam_pitch
            self._fps_mode = False
            self._fps_timer.stop()
            self._keys_pressed.clear()
            self._vp_dirty = True
            if self._auto_rotate:
                self._auto_rotate_timer.start()
            self.fps_mode_changed.emit(False)
        else:
            self._transition_to_fps()
        self.update()

    # QOpenGLWidget overrides

    def initializeGL(self) -> None:
        if not _HAS_GL:
            return
        try:
            self.context().aboutToBeDestroyed.connect(self._cleanup_gl)

            glClearColor(*self._bg_color, 1.0)
            glEnable(GL_DEPTH_TEST)
            glEnable(GL_BLEND)
            glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)

            self._prog = _link_program(_MESH_VERT, _MESH_FRAG)
            self._grid_prog = _link_program(_GRID_VERT, _GRID_FRAG)

            for ref, md in self._gl_meshes.items():
                vao = glGenVertexArrays(1)
                glBindVertexArray(vao)

                pos_vbo = glGenBuffers(1)
                glBindBuffer(GL_ARRAY_BUFFER, pos_vbo)
                glBufferData(GL_ARRAY_BUFFER,
                             md['verts'].nbytes, md['verts'], GL_STATIC_DRAW)
                glEnableVertexAttribArray(0)
                glVertexAttribPointer(0, 3, GL_FLOAT, GL_FALSE, 0, None)

                nrm_vbo = glGenBuffers(1)
                glBindBuffer(GL_ARRAY_BUFFER, nrm_vbo)
                glBufferData(GL_ARRAY_BUFFER,
                             md['norms'].nbytes, md['norms'], GL_STATIC_DRAW)
                glEnableVertexAttribArray(1)
                glVertexAttribPointer(1, 3, GL_FLOAT, GL_FALSE, 0, None)

                col_data = md.get('colors')
                if col_data is None:
                    col_data = np.ones((len(md['verts']), 3), dtype=np.float32)
                col_vbo = glGenBuffers(1)
                glBindBuffer(GL_ARRAY_BUFFER, col_vbo)
                glBufferData(GL_ARRAY_BUFFER, col_data.nbytes,
                             col_data, GL_STATIC_DRAW)
                glEnableVertexAttribArray(2)
                glVertexAttribPointer(2, 3, GL_FLOAT, GL_FALSE, 0, None)

                idx_vbo = glGenBuffers(1)
                glBindBuffer(GL_ELEMENT_ARRAY_BUFFER, idx_vbo)
                glBufferData(GL_ELEMENT_ARRAY_BUFFER,
                             md['idx'].nbytes, md['idx'], GL_STATIC_DRAW)

                glBindVertexArray(0)

                self._vaos[ref] = vao
                self._vbos[ref] = (pos_vbo, nrm_vbo, col_vbo, idx_vbo)
                self._idx_counts[ref] = int(md['idx'].size)

            # Grid
            self._grid_vao = glGenVertexArrays(1)
            glBindVertexArray(self._grid_vao)
            self._grid_vbo = glGenBuffers(1)
            glBindBuffer(GL_ARRAY_BUFFER, self._grid_vbo)
            glBufferData(GL_ARRAY_BUFFER, self._grid_verts.nbytes,
                         self._grid_verts, GL_STATIC_DRAW)
            glEnableVertexAttribArray(0)
            glVertexAttribPointer(0, 3, GL_FLOAT, GL_FALSE, 0, None)
            glBindVertexArray(0)
            self._grid_n = len(self._grid_verts) // 3

            # Axes indicator (X=red, Y=green, Z=blue)
            self._axes_prog = _link_program(_AXES_VERT, _AXES_FRAG)
            _ax_pos = np.array([
                0, 0, 0, 1, 0, 0,
                0, 0, 0, 0, 1, 0,
                0, 0, 0, 0, 0, 1,
            ], dtype=np.float32)
            _ax_col = np.array([
                1, 0.15, 0.15,  1, 0.15, 0.15,
                0.15, 0.85, 0.15, 0.15, 0.85, 0.15,
                0.25, 0.45, 1,  0.25, 0.45, 1,
            ], dtype=np.float32)
            self._axes_vao = glGenVertexArrays(1)
            glBindVertexArray(self._axes_vao)
            _vbo_p = glGenBuffers(1)
            glBindBuffer(GL_ARRAY_BUFFER, _vbo_p)
            glBufferData(GL_ARRAY_BUFFER, _ax_pos.nbytes,
                         _ax_pos, GL_STATIC_DRAW)
            glEnableVertexAttribArray(0)
            glVertexAttribPointer(0, 3, GL_FLOAT, GL_FALSE, 0, None)
            _vbo_c = glGenBuffers(1)
            glBindBuffer(GL_ARRAY_BUFFER, _vbo_c)
            glBufferData(GL_ARRAY_BUFFER, _ax_col.nbytes,
                         _ax_col, GL_STATIC_DRAW)
            glEnableVertexAttribArray(1)
            glVertexAttribPointer(1, 3, GL_FLOAT, GL_FALSE, 0, None)
            glBindVertexArray(0)
            self._axes_vbo = (_vbo_p, _vbo_c)

            # Cache uniform locations - avoids synchronous driver round-trips every frame
            self._u["mvp"] = glGetUniformLocation(self._prog,      b"uMVP")
            self._u["model"] = glGetUniformLocation(self._prog,      b"uModel")
            self._u["color"] = glGetUniformLocation(self._prog,      b"uColor")
            self._u["opacity"] = glGetUniformLocation(
                self._prog,      b"uOpacity")
            self._u["cam_pos"] = glGetUniformLocation(
                self._prog,      b"uCamPos")
            self._u["cam_r"] = glGetUniformLocation(self._prog,      b"uCamR")
            self._u["cam_u"] = glGetUniformLocation(self._prog,      b"uCamU")
            self._u["vp"] = glGetUniformLocation(self._grid_prog, b"uVP")
            self._u["axes_mvp"] = glGetUniformLocation(
                self._axes_prog, b"uMVP")

            self._ready = True

        except Exception as e:
            print(f"[AnimGLWidget] initializeGL error: {e}")
            import traceback
            traceback.print_exc()

    def resizeGL(self, w: int, h: int) -> None:
        if _HAS_GL:
            glViewport(0, 0, w, h)
        self._vp_dirty = True

    def paintGL(self) -> None:
        if not _HAS_GL:
            return
        if not self._ready:
            glClear(GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT)
            return
        try:
            glClear(GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT)

            cam_changed = self._vp_dirty
            vp = self._vp_matrix()

            glPolygonMode(GL_FRONT_AND_BACK,
                          GL_LINE if self._wireframe else GL_FILL)

            # mesh pass
            glUseProgram(self._prog)
            l_mvp = self._u["mvp"]
            l_model = self._u["model"]
            l_col = self._u["color"]
            l_op = self._u["opacity"]

            eye = self._cam_pos if self._fps_mode else self._eye()
            glUniform3f(self._u["cam_pos"], float(
                eye[0]), float(eye[1]), float(eye[2]))
            view = getattr(self, "_view_cache", None)
            if view is None:
                self._vp_matrix()
                view = self._view_cache
            cam_r = view[0, :3]
            cam_u = view[1, :3]
            glUniform3f(self._u["cam_r"], float(cam_r[0]),
                        float(cam_r[1]), float(cam_r[2]))
            glUniform3f(self._u["cam_u"], float(cam_u[0]),
                        float(cam_u[1]), float(cam_u[2]))

            for ref, vao in self._vaos.items():
                model = self._transforms.get(ref, _IDENTITY)
                mvp = vp @ model
                col = self._colors.get(ref, (0.82, 0.82, 0.84, 1.0))

                glUniformMatrix4fv(l_mvp,   1, GL_TRUE, mvp.ravel())
                glUniformMatrix4fv(l_model, 1, GL_TRUE, model.ravel())
                glUniform3f(l_col, col[0], col[1], col[2])
                glUniform1f(l_op,  col[3] if len(col) > 3 else 1.0)

                glBindVertexArray(vao)
                glDrawElements(
                    GL_TRIANGLES, self._idx_counts[ref], GL_UNSIGNED_INT, None)

            glBindVertexArray(0)

            # grid pass
            if self._show_grid:
                glUseProgram(self._grid_prog)
                glUniformMatrix4fv(self._u["vp"], 1, GL_TRUE, vp.ravel())
                glBindVertexArray(self._grid_vao)
                glDrawArrays(GL_LINES, 0, self._grid_n)
                glBindVertexArray(0)

            # axes indicator (bottom-left corner)
            dpr = max(self.devicePixelRatio(), 1.0)
            phys_w = int(self.width() * dpr)
            phys_h = int(self.height() * dpr)
            axes_px = max(60, int(80 * dpr))

            glViewport(0, 0, axes_px, axes_px)
            glEnable(GL_SCISSOR_TEST)
            glScissor(0, 0, axes_px, axes_px)
            glClear(GL_DEPTH_BUFFER_BIT)
            glDisable(GL_DEPTH_TEST)
            glPolygonMode(GL_FRONT_AND_BACK, GL_FILL)
            try:
                if cam_changed:
                    if self._fps_mode:
                        _az = math.radians(self._cam_yaw)
                        _el = math.radians(self._cam_pitch)
                    else:
                        _az = math.radians(self._az)
                        _el = math.radians(self._el)
                    _d = 2.5
                    _eye_a = np.array([
                        _d * math.cos(_el) * math.sin(_az),
                        _d * math.sin(_el),
                        _d * math.cos(_el) * math.cos(_az),
                    ], dtype=np.float32)
                    self._axes_vp_cache = _perspective(
                        _CAMERA_FOV, 1.0, 0.1, 20.0) @ _look_at(_eye_a, np.zeros(3, dtype=np.float32))

                glUseProgram(self._axes_prog)
                glUniformMatrix4fv(self._u["axes_mvp"], 1, GL_TRUE, self._axes_vp_cache.ravel())
                glBindVertexArray(self._axes_vao)
                glDrawArrays(GL_LINES, 0, 6)
                glBindVertexArray(0)
            finally:
                glDisable(GL_SCISSOR_TEST)
                glEnable(GL_DEPTH_TEST)
                glViewport(0, 0, phys_w, phys_h)

        except Exception as e:
            print(f"[AnimGLWidget] paintGL error: {e}")

    # Camera

    def _eye(self) -> np.ndarray:
        az = math.radians(self._az)
        el = math.radians(self._el)
        d = self._dist
        return self._target + np.array([
            d * math.cos(el) * math.sin(az),
            d * math.sin(el),
            d * math.cos(el) * math.cos(az),
        ], dtype=np.float32)

    def _vp_matrix(self) -> np.ndarray:
        if not self._vp_dirty:
            return self._vp_cache
        dpr = max(self.devicePixelRatio(), 1.0)
        w = max(self.width() * dpr, 1)
        h = max(self.height() * dpr, 1)
        if self._fps_mode:
            proj = _perspective(_CAMERA_FOV, w / h, 0.01, 10000.0)
            fwd, _ = self._fps_forward_right()
            view = _look_at(self._cam_pos, self._cam_pos + fwd)
        else:
            proj = _perspective(_CAMERA_FOV, w / h, self._near, self._far)
            el_r = math.radians(self._el)
            az_r = math.radians(self._az)
            orbit_up = np.array([
                -math.sin(el_r) * math.sin(az_r),
                math.cos(el_r),
                -math.sin(el_r) * math.cos(az_r),
            ], dtype=np.float32)
            view = _look_at(self._eye(), self._target, up=orbit_up)
        self._view_cache = view
        self._vp_cache = proj @ view
        self._vp_dirty = False
        return self._vp_cache

    # Mouse / wheel

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.LeftButton:
            self._drag_last = event.pos()

    def mouseReleaseEvent(self, event) -> None:
        if event.button() == Qt.LeftButton:
            self._drag_last = None

    def mouseMoveEvent(self, event) -> None:
        if self._drag_last is None or not (event.buttons() & Qt.LeftButton):
            return
        dx = event.pos().x() - self._drag_last.x()
        dy = event.pos().y() - self._drag_last.y()
        self._drag_last = event.pos()

        if event.modifiers() & Qt.ShiftModifier:
            view = getattr(self, "_view_cache", None)
            if view is not None:
                cam_right = view[0, :3]
                cam_up = view[1, :3]
            else:
                cam_right = np.array([1.0, 0.0, 0.0], dtype=np.float32)
                cam_up = np.array([0.0, 1.0, 0.0], dtype=np.float32)
            speed = self._dist * 0.0015
            pan = (-dx * cam_right + dy * cam_up) * speed
            if self._fps_mode:
                self._cam_pos = self._cam_pos + pan
            else:
                self._target = self._target + pan
        elif self._fps_mode:
            self._cam_yaw += dx * 0.5
            self._cam_pitch = max(-89.0, min(89.0, self._cam_pitch + dy * 0.5))
        else:
            self._az -= dx * 0.5
            self._el += dy * 0.5
        self._vp_dirty = True
        self.update()

    def wheelEvent(self, event) -> None:
        if self._fps_mode:
            delta_notches = event.angleDelta().y() / 120.0
            fwd, _ = self._fps_forward_right()
            self._cam_pos = self._cam_pos + fwd * \
                (delta_notches * self._dist * 0.15)
        else:
            self._dist = max(0.1, self._dist *
                             (1.0 - event.angleDelta().y() / 1200.0))
        self._vp_dirty = True
        self.update()

    def keyPressEvent(self, event) -> None:
        scan = event.nativeScanCode()
        if not self._fps_mode and scan in _SCAN_WASD:
            self._transition_to_fps()
        self._keys_pressed.add(scan)
        super().keyPressEvent(event)

    def keyReleaseEvent(self, event) -> None:
        self._keys_pressed.discard(event.nativeScanCode())
        super().keyReleaseEvent(event)

    def focusOutEvent(self, event) -> None:
        self._keys_pressed.clear()
        super().focusOutEvent(event)

    # FPS helpers

    def _auto_rotate_tick(self) -> None:
        if self._auto_rotate and not self._fps_mode:
            self._az -= 0.25        # degrees per frame (~15°/sec at 60 fps)
            self._vp_dirty = True
            self.update()

    def _transition_to_fps(self) -> None:
        if self._fps_mode:
            return
        self._fps_mode = True
        self._cam_yaw = -self._az
        self._cam_pitch = self._el
        self._cam_pos = self._eye().copy()
        self._fps_last_tick = _time.perf_counter()
        self._vp_dirty = True
        self._auto_rotate_timer.stop()   # auto-rotate is orbit-only
        self._fps_timer.start()
        self.fps_mode_changed.emit(True)

    def _fps_forward_right(self):
        """Return (forward, right) unit vectors from current FPS yaw/pitch."""
        yaw_r = math.radians(self._cam_yaw)
        pitch_r = math.radians(self._cam_pitch)
        forward = np.array([
            math.cos(pitch_r) * math.sin(yaw_r),
            -math.sin(pitch_r),
            -math.cos(pitch_r) * math.cos(yaw_r),
        ], dtype=np.float32)
        right = np.array(
            [math.cos(yaw_r), 0.0, math.sin(yaw_r)], dtype=np.float32)
        return forward, right

    def _fps_tick(self) -> None:
        if not self._fps_mode:
            self._fps_timer.stop()
            return
        now = _time.perf_counter()
        dt = now - self._fps_last_tick
        self._fps_last_tick = now
        if dt > 0.1:
            dt = 0.016

        speed = self._dist * 0.5 * dt
        if _SCAN_E in self._keys_pressed:
            speed *= 3.0
        if _SCAN_Q in self._keys_pressed:
            speed *= 0.33

        fwd, right = self._fps_forward_right()
        up = np.array([0.0, 1.0, 0.0], dtype=np.float32)

        moved = False
        if _SCAN_W in self._keys_pressed:
            self._cam_pos = self._cam_pos + fwd * speed
            moved = True
        if _SCAN_S in self._keys_pressed:
            self._cam_pos = self._cam_pos - fwd * speed
            moved = True
        if _SCAN_A in self._keys_pressed:
            self._cam_pos = self._cam_pos - right * speed
            moved = True
        if _SCAN_D in self._keys_pressed:
            self._cam_pos = self._cam_pos + right * speed
            moved = True
        if _SCAN_SPACE in self._keys_pressed:
            self._cam_pos = self._cam_pos + up * speed
            moved = True
        if _SCAN_LSHIFT in self._keys_pressed:
            mods = QGuiApplication.keyboardModifiers()
            if not (mods & (Qt.ControlModifier | Qt.AltModifier | Qt.MetaModifier)):
                self._cam_pos = self._cam_pos - up * speed
                moved = True

        if moved:
            self._vp_dirty = True
            self.update()

    # GL cleanup

    def _cleanup_gl(self) -> None:
        if not self._ready or not _HAS_GL:
            return
        try:
            for ref in list(self._vaos):
                glDeleteVertexArrays(1, [self._vaos[ref]])
                for vbo in self._vbos[ref]:
                    glDeleteBuffers(1, [vbo])
            if self._grid_vao:
                glDeleteVertexArrays(1, [self._grid_vao])
            if self._grid_vbo:
                glDeleteBuffers(1, [self._grid_vbo])
            if self._axes_vao:
                glDeleteVertexArrays(1, [self._axes_vao])
            for _vbo in self._axes_vbo:
                if _vbo:
                    glDeleteBuffers(1, [_vbo])
            if self._prog:
                glDeleteProgram(self._prog)
            if self._grid_prog:
                glDeleteProgram(self._grid_prog)
            if self._axes_prog:
                glDeleteProgram(self._axes_prog)
        except Exception:
            pass
        self._ready = False
