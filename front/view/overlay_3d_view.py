"""3D acrylic panel view: textured planes front=GT / back=Prediction.

Per the task spec:
- A transparent "acrylic" board, with the GT image printed on the FRONT
  face and the model's Prediction image printed on the BACK face.
- The user can drag the mouse to rotate the panel freely.
- A "Rotate 90°" button (and R key) snaps the view 90 degrees around Z.
- A "Flip" button (and F key) flips the camera to the other side.
- An "Overlay" button (and O key) makes BOTH faces semi-transparent so
  the two layers overlay and mismatched points can be inspected.
- Mismatched spots are rendered as red spheres on the FRONT face.
"""
from __future__ import annotations

from typing import Optional

import numpy as np
import pyvista as pv
from pyvistaqt import QtInteractor
from PySide6.QtCore import Qt, QPoint, Signal
from PySide6.QtGui import QColor, QPainter, QPixmap
from PySide6.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QPushButton,
    QSizePolicy, QSlider, QVBoxLayout, QWidget,
    QGraphicsDropShadowEffect,
)

from model.overlay_data import ErrorType, OverlayDataset
from utils.logger import logger


# ====================================================================
#  Theme colors
# ====================================================================
_BG_DARK = "#101113"
_BG_LIGHT = "#eef0f3"
_PANEL_EDGE_LIGHT = "#d8dde3"
_PANEL_EDGE_DARK = "#3a3a40"

_ERROR_RED = "#ff4d4f"
_ERROR_YELLOW = "#faad14"
_ERROR_ORANGE = "#ff7a45"
_ERROR_NEW = "#faad14"

_POINT_SIZE = 18
_POINT_SIZE_ERR = 26


# ====================================================================
#  Floating controls (right side)
# ====================================================================
_FLOAT_LIGHT = """
QFrame {
    background: rgba(255,255,255,0.92);
    border: 1px solid #e0e0e0;
    border-radius: 10px;
}
QPushButton {
    font-size: 11px; padding: 5px 8px;
    border: 1px solid #ddd; border-radius: 6px;
    background: #fafafa; color: #333;
    text-align: left;
}
QPushButton:hover { background: #eef3fb; border-color: #b9d2f1; }
QPushButton:pressed { background: #e3eefb; }
QPushButton:checked {
    background: #e3eefb; border-color: #5b8fd9; color: #1a6bc0;
    font-weight: 600;
}
QLabel { font-size: 10px; color: #888; }
QLabel#title { font-weight: 700; color: #555; font-size: 10px;
               letter-spacing: 1px; padding: 0 0 4px 0; }
QFrame#stats { background: #f6f8fa; border: 1px solid #e6e9ec;
               border-radius: 8px; }
QLabel#statsTitle { font-size: 10px; font-weight: 700; color: #555; }
QLabel#statsValue { font-size: 14px; font-weight: 700; }
QLabel#statsSub { font-size: 9px; color: #888; }
QPushButton#link {
    font-size: 11px; padding: 2px 0; border: none;
    background: transparent; color: #1a6bc0; text-align: left;
}
QPushButton#link:hover { color: #0a4f9c; text-decoration: underline; }
QSlider::groove:horizontal { height: 3px; background: #e0e0e0; border-radius: 2px; }
QSlider::handle:horizontal { width: 10px; margin: -4px 0; background: #999;
    border-radius: 5px; }
"""

_FLOAT_DARK = """
QFrame {
    background: rgba(35,35,38,0.94);
    border: 1px solid rgba(255,255,255,0.06);
    border-radius: 10px;
}
QPushButton {
    font-size: 11px; padding: 5px 8px;
    border: 1px solid rgba(255,255,255,0.10); border-radius: 6px;
    background: rgba(255,255,255,0.04); color: #d0d0d5;
    text-align: left;
}
QPushButton:hover { background: rgba(100,180,255,0.10); }
QPushButton:pressed { background: rgba(100,180,255,0.15); }
QPushButton:checked {
    background: rgba(100,180,255,0.20); color: #f5f5f7;
    border-color: rgba(100,180,255,0.40); font-weight: 600;
}
QLabel { font-size: 10px; color: #8a8a90; }
QLabel#title { font-weight: 700; color: #b0b0b5; font-size: 10px;
               letter-spacing: 1px; padding: 0 0 4px 0; }
QFrame#stats { background: rgba(255,255,255,0.04);
               border: 1px solid rgba(255,255,255,0.06);
               border-radius: 8px; }
QLabel#statsTitle { font-size: 10px; font-weight: 700; color: #b0b0b5; }
QLabel#statsValue { font-size: 14px; font-weight: 700; color: #f5f5f7; }
QLabel#statsSub { font-size: 9px; color: #8a8a90; }
QPushButton#link {
    font-size: 11px; padding: 2px 0; border: none;
    background: transparent; color: #64b4ff; text-align: left;
}
QPushButton#link:hover { color: #9bcbff; text-decoration: underline; }
QSlider::groove:horizontal { height: 3px; background: rgba(255,255,255,0.08);
    border-radius: 2px; }
QSlider::handle:horizontal { width: 10px; margin: -4px 0; background: #888;
    border-radius: 5px; }
"""


def _hex_to_rgb(h: str) -> tuple:
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) / 255.0 for i in (0, 2, 4))


def _make_qpixmap_icon(text: str, color: str = "#333", size: int = 14) -> QPixmap:
    """Render a small Unicode glyph as a QPixmap icon (used as button decoration)."""
    pm = QPixmap(size, size)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setPen(QColor(color))
    f = p.font()
    f.setPixelSize(int(size * 0.78))
    f.setBold(True)
    p.setFont(f)
    p.drawText(pm.rect(), Qt.AlignmentFlag.AlignCenter, text)
    p.end()
    return pm


# ====================================================================
#  Floating control panel
# ====================================================================
class _FloatingPanel(QFrame):
    """The right-side floating control panel + error statistics card."""

    request_flip = Signal()
    request_overlay = Signal()           # checked state read from the button
    request_reset = Signal()
    request_rotate90 = Signal()
    request_view_details = Signal()
    gt_opacity_changed = Signal(float)
    pred_opacity_changed = Signal(float)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._dark = False
        self.setObjectName("float")
        self.setStyleSheet(_FLOAT_LIGHT)
        self.setFixedWidth(168)

        ly = QVBoxLayout(self)
        ly.setContentsMargins(10, 10, 10, 10)
        ly.setSpacing(6)

        title = QLabel("CONTROLS")
        title.setObjectName("title")
        ly.addWidget(title)

        self._btn_flip = QPushButton("  Flip Side  (F)")
        self._btn_flip.setIcon(_make_qpixmap_icon("\u21C4", "#333"))
        self._btn_flip.clicked.connect(self.request_flip)
        ly.addWidget(self._btn_flip)

        self._btn_rot = QPushButton("  Rotate 90°  (R)")
        self._btn_rot.setIcon(_make_qpixmap_icon("\u21BB", "#333"))
        self._btn_rot.clicked.connect(self.request_rotate90)
        ly.addWidget(self._btn_rot)

        self._btn_overlay = QPushButton("  Overlay  (O)")
        self._btn_overlay.setIcon(_make_qpixmap_icon("\u25CB", "#333"))
        self._btn_overlay.setCheckable(True)
        self._btn_overlay.clicked.connect(self.request_overlay)
        ly.addWidget(self._btn_overlay)
        # Also wire the toggled signal so the handler can read checked state
        self._btn_overlay.toggled.connect(self._on_overlay_toggled)

        self._btn_reset = QPushButton("  Reset View")
        self._btn_reset.setIcon(_make_qpixmap_icon("\u21BA", "#333"))
        self._btn_reset.clicked.connect(self.request_reset)
        ly.addWidget(self._btn_reset)

        # Opacity sliders (visible only in overlay mode)
        self._slider_box = QWidget()
        sl = QVBoxLayout(self._slider_box)
        sl.setContentsMargins(0, 0, 0, 0)
        sl.setSpacing(2)

        gl = QLabel("GT Opacity")
        sl.addWidget(gl)
        self._gt_slider = QSlider(Qt.Orientation.Horizontal)
        self._gt_slider.setRange(0, 100)
        self._gt_slider.setValue(70)
        self._gt_slider.setFixedHeight(16)
        self._gt_slider.valueChanged.connect(
            lambda v: self.gt_opacity_changed.emit(v / 100.0)
        )
        sl.addWidget(self._gt_slider)

        pl = QLabel("Pred Opacity")
        sl.addWidget(pl)
        self._pred_slider = QSlider(Qt.Orientation.Horizontal)
        self._pred_slider.setRange(0, 100)
        self._pred_slider.setValue(70)
        self._pred_slider.setFixedHeight(16)
        self._pred_slider.valueChanged.connect(
            lambda v: self.pred_opacity_changed.emit(v / 100.0)
        )
        sl.addWidget(self._pred_slider)

        ly.addWidget(self._slider_box)
        self._slider_box.setVisible(False)

        # ---- Error statistics card ----
        stats = QFrame()
        stats.setObjectName("stats")
        sl2 = QVBoxLayout(stats)
        sl2.setContentsMargins(10, 8, 10, 8)
        sl2.setSpacing(4)

        t = QLabel("Mismatched Points")
        t.setObjectName("statsTitle")
        sl2.addWidget(t)

        self._stat_total = QLabel("--")
        self._stat_total.setObjectName("statsValue")
        self._stat_total.setStyleSheet(f"color: {_ERROR_RED};")
        sl2.addWidget(self._stat_total)

        # Breakdown rows
        self._rows: dict[ErrorType, tuple[QLabel, QLabel]] = {}
        for et, color, label in [
            (ErrorType.MISCLASSIFIED, _ERROR_RED, "Misclass"),
            (ErrorType.NEW, _ERROR_YELLOW, "New"),
            (ErrorType.MISSING, _ERROR_ORANGE, "Missing"),
        ]:
            row = QHBoxLayout()
            row.setContentsMargins(0, 0, 0, 0)
            row.setSpacing(4)
            dot = QLabel("\u25CF")
            dot.setStyleSheet(f"color: {color}; font-size: 9px;")
            name = QLabel(label)
            name.setStyleSheet("color: #888; font-size: 10px;")
            val = QLabel("0 (0.0%)")
            val.setStyleSheet("color: #555; font-size: 10px;")
            val.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            row.addWidget(dot)
            row.addWidget(name, 1)
            row.addWidget(val)
            sl2.addLayout(row)
            self._rows[et] = (name, val)

        # Separator
        sep = QLabel()
        sep.setFixedHeight(1)
        sep.setStyleSheet("background: rgba(0,0,0,0.06);")
        sl2.addWidget(sep)

        tp_row = QHBoxLayout()
        tp_name = QLabel("Total Points")
        tp_name.setObjectName("statsSub")
        self._stat_total_points = QLabel("0")
        self._stat_total_points.setStyleSheet(
            "color: #555; font-size: 11px; font-weight: 600;"
        )
        self._stat_total_points.setAlignment(Qt.AlignmentFlag.AlignRight)
        tp_row.addWidget(tp_name)
        tp_row.addStretch()
        tp_row.addWidget(self._stat_total_points)
        sl2.addLayout(tp_row)

        self._link_btn = QPushButton("View Details \u2192")
        self._link_btn.setObjectName("link")
        self._link_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._link_btn.clicked.connect(self.request_view_details)
        sl2.addWidget(self._link_btn)

        ly.addWidget(stats)

    def update_theme(self, dark: bool) -> None:
        self._dark = dark
        self.setStyleSheet(_FLOAT_DARK if dark else _FLOAT_LIGHT)
        col = "#b0b0b5" if dark else "#333"
        for btn in (
            self._btn_flip, self._btn_rot, self._btn_overlay, self._btn_reset,
        ):
            btn.setIcon(_make_qpixmap_icon(btn.text().strip().split()[0], col))

    def set_overlay_mode(self, on: bool) -> None:
        self._btn_overlay.setChecked(on)
        self._slider_box.setVisible(on)

    def _on_overlay_toggled(self, checked: bool) -> None:
        # Sync slider visibility when user toggles the button directly
        self._slider_box.setVisible(checked)

    def set_stats(
        self,
        mismatched: int,
        total: int,
        breakdown: dict[ErrorType, int],
    ) -> None:
        pct = (100.0 * mismatched / total) if total else 0.0
        self._stat_total.setText(f"{mismatched:,} ({pct:.2f}%)")
        self._stat_total_points.setText(f"{total:,}")
        for et, (_, lbl) in self._rows.items():
            n = breakdown.get(et, 0)
            p = (100.0 * n / total) if total else 0.0
            lbl.setText(f"{n:,} ({p:.2f}%)")


# ====================================================================
#  Drag-to-rotate hint badge (bottom-left of viewport)
# ====================================================================
class _HintBadge(QFrame):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("hint")
        self.setStyleSheet("""
            QFrame#hint {
                background: rgba(255,255,255,0.92);
                border: 1px solid #e0e0e0; border-radius: 8px;
            }
            QLabel { color: #555; font-size: 10px; }
        """)
        ly = QHBoxLayout(self)
        ly.setContentsMargins(10, 6, 10, 6)
        ly.setSpacing(6)
        ic = QLabel("\u25C9")
        ic.setStyleSheet("color: #888; font-size: 12px;")
        ly.addWidget(ic)
        txt = QVBoxLayout()
        txt.setContentsMargins(0, 0, 0, 0)
        txt.setSpacing(0)
        l1 = QLabel("Drag to rotate")
        l1.setStyleSheet("color: #444; font-size: 10px; font-weight: 600;")
        l2 = QLabel("Scroll to zoom")
        l2.setStyleSheet("color: #888; font-size: 9px;")
        txt.addWidget(l1)
        txt.addWidget(l2)
        ly.addLayout(txt)


# ====================================================================
#  Main 3D widget
# ====================================================================
class Overlay3DViewWidget(QWidget):
    """3D acrylic panel with GT/Pred textures and error highlights."""

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)

        self._dataset: Optional[OverlayDataset] = None
        self._gt_image_path: Optional[str] = None
        self._pred_image_path: Optional[str] = None

        self._plotter: Optional[QtInteractor] = None
        self._overlay_on = False
        self._showing_front = True
        self._rot_z_quarter = 0    # count of 90deg rotations (0..3)
        self._gt_opacity = 1.0
        self._pred_opacity = 1.0

        self._dark = False

        # Geometry
        self._pw = 4.0
        self._ph = 3.0
        self._gap = 0.06

        self._setup_ui()

    # ----------------------------------------------------------------
    #  UI
    # ----------------------------------------------------------------
    def _setup_ui(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # 3D viewport
        self._plotter = QtInteractor(self)
        self._plotter.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )
        self._plotter.enable_anti_aliasing()
        self._plotter.hide_axes()
        self._plotter.enable_trackball_style()
        self._plotter.set_background(_BG_LIGHT)
        outer.addWidget(self._plotter, 1)

        # Floating controls (parented to MainWindow via the QtInteractor overlay)
        # Note: parenting to a QWidget without a layout makes setVisible a no-op,
        # so we re-parent to `self` (Overlay3DViewWidget) and position via
        # setGeometry in resizeEvent.
        self._float = _FloatingPanel(self)
        self._float.setParent(self)
        self._float.request_flip.connect(self._cmd_flip)
        self._float.request_overlay.connect(self._on_overlay_requested)
        self._float.request_reset.connect(self._cmd_reset)
        self._float.request_rotate90.connect(self._cmd_rotate90)
        self._float.request_view_details.connect(self._on_view_details)
        self._float.gt_opacity_changed.connect(self._on_gt_opacity)
        self._float.pred_opacity_changed.connect(self._on_pred_opacity)
        self._float.setVisible(False)
        self._float.raise_()

        # Drag-to-rotate hint
        self._hint = _HintBadge(self)
        self._hint.setParent(self)
        self._hint.resize(150, 46)
        self._hint.setVisible(False)
        self._hint.raise_()

    def resizeEvent(self, e) -> None:
        super().resizeEvent(e)
        w = self.width()
        h = self.height()
        # Position floating panel on the right of the whole widget
        self._float.setGeometry(
            w - self._float.width() - 16, 16,
            self._float.width(),
            min(h - 32, 520),
        )
        # Position hint on the bottom-left
        if self._plotter is not None:
            self._hint.move(
                16, h - self._hint.height() - 16,
            )
        # Keep the floating widgets on top
        self._float.raise_()
        self._hint.raise_()

    # ----------------------------------------------------------------
    #  Public API
    # ----------------------------------------------------------------
    def set_dataset(
        self,
        dataset: Optional[OverlayDataset],
        gt_image_path: Optional[str] = None,
        pred_image_path: Optional[str] = None,
    ) -> None:
        self._dataset = dataset
        self._gt_image_path = gt_image_path
        self._pred_image_path = pred_image_path
        if dataset is None or dataset.cell_count == 0:
            self.show_no_data()
            return
        self._overlay_on = False
        self._showing_front = True
        self._rot_z_quarter = 0
        self._float.setVisible(True)
        self._float.set_overlay_mode(False)
        self._hint.setVisible(True)
        self._build_scene(dataset, gt_image_path, pred_image_path)
        self._update_stats(dataset)

    def update_theme(self, dark: bool) -> None:
        self._dark = dark
        if self._plotter is not None:
            self._plotter.set_background(_BG_DARK if dark else _BG_LIGHT)
            self._plotter.setStyleSheet(
                "background-color: "
                + (_BG_DARK if dark else _BG_LIGHT) + ";"
            )
        if self._float.isVisible():
            self._float.update_theme(dark)

    def show_no_data(self) -> None:
        self._dataset = None
        if self._plotter is not None:
            self._plotter.clear()
        self._float.setVisible(False)
        self._hint.setVisible(False)

    def get_dataset(self) -> Optional[OverlayDataset]:
        return self._dataset

    # ----------------------------------------------------------------
    #  Scene construction
    # ----------------------------------------------------------------
    def _build_scene(
        self,
        ds: OverlayDataset,
        gt_path: Optional[str],
        pred_path: Optional[str],
    ) -> None:
        p = self._plotter
        p.clear()

        hw, hh, gap = self._pw / 2, self._ph / 2, self._gap

        # --- Edge frame (subtle "acrylic" border) ---
        edge_color = _PANEL_EDGE_DARK if self._dark else _PANEL_EDGE_LIGHT
        edge_thickness = 0.04
        edges = []
        # top, bottom, left, right
        edges.append(
            pv.Cube(
                center=(0, hh + edge_thickness / 2, 0),
                x_length=self._pw + edge_thickness * 2,
                y_length=edge_thickness,
                z_length=gap * 1.2,
            )
        )
        edges.append(
            pv.Cube(
                center=(0, -hh - edge_thickness / 2, 0),
                x_length=self._pw + edge_thickness * 2,
                y_length=edge_thickness,
                z_length=gap * 1.2,
            )
        )
        edges.append(
            pv.Cube(
                center=(-hw - edge_thickness / 2, 0, 0),
                x_length=edge_thickness,
                y_length=self._ph,
                z_length=gap * 1.2,
            )
        )
        edges.append(
            pv.Cube(
                center=(hw + edge_thickness / 2, 0, 0),
                x_length=edge_thickness,
                y_length=self._ph,
                z_length=gap * 1.2,
            )
        )
        for i, e in enumerate(edges):
            p.add_mesh(e, color=edge_color, name=f"edge_{i}",
                       opacity=0.85, smooth_shading=True)

        # --- Front face: GT image ---
        front = pv.Plane(
            center=(0, 0, gap / 2),
            direction=(0, 0, 1),
            i_size=self._pw,
            j_size=self._ph,
            i_resolution=1,
            j_resolution=1,
        )
        front.texture_map_to_plane(inplace=True, use_bounds=False)
        if gt_path and _file_exists(gt_path):
            tex = _load_texture(gt_path)
            if tex is not None:
                p.add_mesh(
                    front, texture=tex, name="front_face",
                    opacity=self._gt_opacity,
                )
            else:
                _add_placeholder(p, front, "GT", gap / 2, _ERROR_RED)
        else:
            _add_placeholder(p, front, "GT", gap / 2, _ERROR_RED)

        # --- Back face: Pred image (flipped so it reads correctly from the back) ---
        back = pv.Plane(
            center=(0, 0, -gap / 2),
            direction=(0, 0, -1),
            i_size=self._pw,
            j_size=self._ph,
            i_resolution=1,
            j_resolution=1,
        )
        back.texture_map_to_plane(inplace=True, use_bounds=False)
        if pred_path and _file_exists(pred_path):
            tex = _load_texture(pred_path)
            if tex is not None:
                p.add_mesh(
                    back, texture=tex, name="back_face",
                    opacity=0.0,
                )
            else:
                _add_placeholder(p, back, "Pred", -gap / 2, "#64b4ff")
        else:
            _add_placeholder(p, back, "Pred (missing)", -gap / 2, "#888888")

        # --- Mismatched points: red spheres on the front face ---
        self._add_error_points(ds, gap / 2 + 0.02)

        # --- Camera ---
        p.camera_position = [
            (0, -self._ph * 0.55, self._pw * 0.85),
            (0, 0, 0),
            (0, 0, 1),
        ]
        p.camera.SetParallelProjection(False)
        p.camera.SetViewAngle(40)

        # --- Lights ---
        try:
            p.remove_all_lights()
            p.add_light(pv.Light(
                position=(self._pw, self._ph, self._pw * 0.6),
                light_type="scene_light", intensity=0.75,
            ))
            p.add_light(pv.Light(
                position=(-self._pw, -self._ph, self._pw * 0.4),
                light_type="scene_light", intensity=0.40,
            ))
            p.add_light(pv.Light(
                position=(0, 0, -self._pw),
                light_type="scene_light", intensity=0.20,
            ))
        except Exception:
            pass

        # --- Keyboard shortcuts ---
        p.add_key_event("f", lambda: self._cmd_flip())
        p.add_key_event("o", lambda: self._cmd_overlay(not self._overlay_on))
        p.add_key_event("r", lambda: self._cmd_rotate90())
        # 'escape' -> reset
        p.add_key_event("escape", lambda: self._cmd_reset())

    def _add_error_points(self, ds: OverlayDataset, z: float) -> None:
        p = self._plotter
        mis_pts: list[tuple[float, float, float]] = []
        new_pts: list[tuple[float, float, float]] = []
        miss_pts: list[tuple[float, float, float]] = []

        for c in ds.cells:
            if c.error_type == ErrorType.MISCLASSIFIED:
                mis_pts.append((c.x, c.y, z))
            elif c.error_type == ErrorType.NEW:
                new_pts.append((c.x, c.y, z))
            elif c.error_type == ErrorType.MISSING:
                miss_pts.append((c.x, c.y, z))

        if mis_pts:
            arr = np.array(mis_pts, dtype=np.float64)
            p.add_mesh(
                pv.PolyData(arr),
                color=_hex_to_rgb(_ERROR_RED),
                point_size=_POINT_SIZE_ERR,
                render_points_as_spheres=True,
                opacity=0.0,  # visible only when overlay or front-facing with overlay
                name="err_misclass",
                ambient=0.5, diffuse=0.9,
            )
        if new_pts:
            arr = np.array(new_pts, dtype=np.float64)
            p.add_mesh(
                pv.PolyData(arr),
                color=_hex_to_rgb(_ERROR_YELLOW),
                point_size=_POINT_SIZE_ERR,
                render_points_as_spheres=True,
                opacity=0.0,
                name="err_new",
                ambient=0.5, diffuse=0.9,
            )
        if miss_pts:
            arr = np.array(miss_pts, dtype=np.float64)
            p.add_mesh(
                pv.PolyData(arr),
                color=_hex_to_rgb(_ERROR_ORANGE),
                point_size=_POINT_SIZE_ERR,
                render_points_as_spheres=True,
                opacity=0.0,
                name="err_missing",
                ambient=0.5, diffuse=0.9,
            )

    # ----------------------------------------------------------------
    #  Stats
    # ----------------------------------------------------------------
    def _update_stats(self, ds: OverlayDataset) -> None:
        breakdown: dict[ErrorType, int] = {
            ErrorType.MISCLASSIFIED: 0,
            ErrorType.NEW: 0,
            ErrorType.MISSING: 0,
        }
        for c in ds.cells:
            if c.error_type in breakdown:
                breakdown[c.error_type] += 1
        self._float.set_stats(
            mismatched=ds.error_count,
            total=ds.cell_count,
            breakdown=breakdown,
        )

    # ----------------------------------------------------------------
    #  Commands
    # ----------------------------------------------------------------
    def _cmd_flip(self) -> None:
        if self._dataset is None:
            return
        self._showing_front = not self._showing_front
        self._update_visibility()
        cam = self._plotter.camera
        pos = list(cam.GetPosition())
        fp = list(cam.GetFocalPoint())
        # Mirror camera through focal point
        new_pos = [fp[i] - (pos[i] - fp[i]) for i in range(3)]
        cam.SetPosition(*new_pos)
        self._plotter.render()
        logger.debug("Flip: showing_front=%s", self._showing_front)

    def _on_overlay_requested(self) -> None:
        # Read the checked state from the button (signal has no arg)
        if self._float is None:
            return
        on = self._float._btn_overlay.isChecked()
        self._cmd_overlay(on)

    def _cmd_overlay(self, on: bool) -> None:
        if self._dataset is None:
            return
        self._overlay_on = bool(on)
        self._float.set_overlay_mode(self._overlay_on)
        if self._overlay_on:
            # Snap camera to a clean front view if it's currently behind
            if not self._showing_front:
                self._showing_front = True
            self._gt_opacity = self._float._gt_slider.value() / 100.0
            self._pred_opacity = self._float._pred_slider.value() / 100.0
            # Re-aim camera in front of the panel
            self._plotter.camera_position = [
                (0, -self._ph * 0.55, self._pw * 0.85),
                (0, 0, 0),
                (0, 0, 1),
            ]
            self._rot_z_quarter = 0
        self._update_visibility()
        self._plotter.render()

    def _cmd_reset(self) -> None:
        if self._dataset is None:
            return
        self._showing_front = True
        self._overlay_on = False
        self._rot_z_quarter = 0
        self._float.set_overlay_mode(False)
        self._gt_opacity = 1.0
        self._pred_opacity = 1.0
        self._float._gt_slider.setValue(70)
        self._float._pred_slider.setValue(70)
        self._plotter.camera_position = [
            (0, -self._ph * 0.55, self._pw * 0.85),
            (0, 0, 0),
            (0, 0, 1),
        ]
        self._update_visibility()
        self._plotter.render()

    def _cmd_rotate90(self) -> None:
        if self._dataset is None:
            return
        self._rot_z_quarter = (self._rot_z_quarter + 1) % 4
        cam = self._plotter.camera
        pos = list(cam.GetPosition())
        fp = list(cam.GetFocalPoint())
        # Rotate 90° around Z axis through focal point
        dx, dy = pos[0] - fp[0], pos[1] - fp[1]
        # CCW 90°: (x, y) -> (-y, x)
        new_dx, new_dy = -dy, dx
        cam.SetPosition(fp[0] + new_dx, fp[1] + new_dy, pos[2])
        cam.SetViewUp(0, 0, 1)
        self._plotter.render()
        logger.debug("Rotate 90°: quarter=%d", self._rot_z_quarter)

    def _on_gt_opacity(self, v: float) -> None:
        self._gt_opacity = float(v)
        self._update_visibility()
        self._plotter.render()

    def _on_pred_opacity(self, v: float) -> None:
        self._pred_opacity = float(v)
        self._update_visibility()
        self._plotter.render()

    def _on_view_details(self) -> None:
        """Request the parent window to switch to the Mismatched Points tab."""
        win = self.window()
        if win is not None and hasattr(win, "show_mismatched_points_tab"):
            win.show_mismatched_points_tab()

    # ----------------------------------------------------------------
    #  Visibility logic
    # ----------------------------------------------------------------
    def _update_visibility(self) -> None:
        if self._plotter is None:
            return
        p = self._plotter

        if self._overlay_on:
            front_op = self._gt_opacity
            back_op = self._pred_opacity
            err_op = 1.0
        else:
            if self._showing_front:
                front_op = self._gt_opacity
                back_op = 0.0
                err_op = 0.55  # subtle hint on front
            else:
                front_op = 0.0
                back_op = self._pred_opacity
                err_op = 0.0  # hidden on the back

        # Front / back face opacities
        for name, op in (("front_face", front_op), ("back_face", back_op)):
            try:
                actor = p.actors[name]
                actor.GetProperty().SetOpacity(op)
            except Exception:
                pass

        # Error highlight opacities
        for name in ("err_misclass", "err_new", "err_missing"):
            try:
                actor = p.actors[name]
                actor.GetProperty().SetOpacity(err_op)
            except Exception:
                pass


# ====================================================================
#  Helpers
# ====================================================================
def _file_exists(p) -> bool:
    try:
        from pathlib import Path
        return Path(str(p)).exists()
    except Exception:
        return False


def _load_texture(path: str):
    """Load a PNG as a PyVista texture. Falls back to PIL then numpy."""
    try:
        tex = pv.read_texture(path)
        return tex
    except Exception as exc:
        logger.warning("pv.read_texture failed for %s: %s", path, exc)
    try:
        from PIL import Image
        import vtk
        from vtkmodules.vtkCommonDataModel import vtkImageData
        from vtkmodules.vtkIOImage import vtkImageReader2Factory

        img = Image.open(path).convert("RGB")
        arr = np.asarray(img)
        h, w, _ = arr.shape
        # Build a vtkImageData manually and wrap it
        vimg = vtk.vtkImageData()
        vimg.SetDimensions(w, h, 1)
        vimg.SetSpacing(1.0, 1.0, 1.0)
        vimg.SetOrigin(0.0, 0.0, 0.0)
        vimg.AllocateScalars(vtk.VTK_UNSIGNED_CHAR, 3)
        flat = arr.reshape(-1, 3)
        for i, (r, g, b) in enumerate(flat):
            vimg.SetScalarComponentFromFloat(i % w, i // w, 0, 0, r)
            vimg.SetScalarComponentFromFloat(i % w, i // w, 0, 1, g)
            vimg.SetScalarComponentFromFloat(i % w, i // w, 0, 2, b)
        return vtk.vtkTexture()
        # NOTE: simplest path is pv.read_texture; if it fails, we don't render
    except Exception as exc:
        logger.warning("PIL texture fallback failed for %s: %s", path, exc)
    return None


def _add_placeholder(p, plane, text: str, z: float, color: str) -> None:
    """Render a flat colored plane as a fallback when an image can't load."""
    try:
        p.add_mesh(
            plane, color=color, name=f"{text}_face",
            opacity=0.6, smooth_shading=True,
        )
    except Exception as exc:
        logger.warning("Placeholder render failed: %s", exc)
