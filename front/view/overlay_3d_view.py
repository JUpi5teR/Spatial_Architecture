"""3D acrylic panel view: scatter-point rendering with GT vs Result comparison.

Front face: GT points colored by cell layer (blue family).
Back face: if results exist, comparison view (correct=layer color,
false positives=bright red, misclassified=orange-red).
If no results, both faces show GT.
"""
from __future__ import annotations

from typing import Optional

import numpy as np
import pyvista as pv
from pyvistaqt import QtInteractor
from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QPushButton,
    QSizePolicy, QSlider, QVBoxLayout, QWidget,
)

from model.overlay_data import (
    ErrorType, OverlayDataset, get_layer_color,
    get_domain_color,
    ERROR_RED_BRIGHT, ERROR_ORANGE_RED,
)
from utils.logger import logger

_BG_DARK = "#141518"
_BG_LIGHT = "#e4e8ec"
_PANEL_EDGE_LIGHT = "#d8dde3"
_PANEL_EDGE_DARK = "#3a3a40"
_POINT_SIZE_NORMAL = 26
_POINT_SIZE_ERROR = 32


_FLOAT_LIGHT = """
QFrame {
    background: rgba(255,255,255,0.92); border: 1px solid #e0e0e0; border-radius: 10px;
}
QPushButton {
    font-size: 11px; padding: 5px 8px; border: 1px solid #ddd; border-radius: 6px;
    background: #fafafa; color: #333; text-align: left;
}
QPushButton:hover { background: #eef3fb; border-color: #b9d2f1; }
QPushButton:pressed { background: #e3eefb; }
QPushButton:checked { background: #e3eefb; border-color: #5b8fd9; color: #1a6bc0; font-weight: 600; }
QLabel { font-size: 10px; color: #888; }
QLabel#title { font-weight: 700; color: #555; font-size: 10px; letter-spacing: 1px; padding: 0 0 4px 0; }
QFrame#stats { background: #f6f8fa; border: 1px solid #e6e9ec; border-radius: 8px; }
QLabel#statsTitle { font-size: 10px; font-weight: 700; color: #555; }
QLabel#statsValue { font-size: 14px; font-weight: 700; }
QLabel#statsSub { font-size: 9px; color: #888; }
QPushButton#link { font-size: 11px; padding: 2px 0; border: none; background: transparent; color: #1a6bc0; text-align: left; }
QPushButton#link:hover { color: #0a4f9c; text-decoration: underline; }
QSlider::groove:horizontal { height: 3px; background: #e0e0e0; border-radius: 2px; }
QSlider::handle:horizontal { width: 10px; margin: -4px 0; background: #999; border-radius: 5px; }
"""

_FLOAT_DARK = """
QFrame {
    background: rgba(35,35,38,0.94); border: 1px solid rgba(255,255,255,0.06); border-radius: 10px;
}
QPushButton {
    font-size: 11px; padding: 5px 8px; border: 1px solid rgba(255,255,255,0.10); border-radius: 6px;
    background: rgba(255,255,255,0.04); color: #d0d0d5; text-align: left;
}
QPushButton:hover { background: rgba(100,180,255,0.10); }
QPushButton:pressed { background: rgba(100,180,255,0.15); }
QPushButton:checked { background: rgba(100,180,255,0.20); color: #f5f5f7; border-color: rgba(100,180,255,0.40); font-weight: 600; }
QLabel { font-size: 10px; color: #8a8a90; }
QLabel#title { font-weight: 700; color: #b0b0b5; font-size: 10px; letter-spacing: 1px; padding: 0 0 4px 0; }
QFrame#stats { background: rgba(255,255,255,0.04); border: 1px solid rgba(255,255,255,0.06); border-radius: 8px; }
QLabel#statsTitle { font-size: 10px; font-weight: 700; color: #b0b0b5; }
QLabel#statsValue { font-size: 14px; font-weight: 700; color: #f5f5f7; }
QLabel#statsSub { font-size: 9px; color: #8a8a90; }
QPushButton#link { font-size: 11px; padding: 2px 0; border: none; background: transparent; color: #64b4ff; text-align: left; }
QPushButton#link:hover { color: #9bcbff; text-decoration: underline; }
QSlider::groove:horizontal { height: 3px; background: rgba(255,255,255,0.08); border-radius: 2px; }
QSlider::handle:horizontal { width: 10px; margin: -4px 0; background: #888; border-radius: 5px; }
"""


def _hex_to_rgb(h: str) -> tuple:
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) / 255.0 for i in (0, 2, 4))


class FloatPanel(QFrame):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("floatPanel")
        self._dark = False
        self.setFixedWidth(195)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Minimum)
        self._setup_ui()

    def _setup_ui(self):
        lay = QVBoxLayout(self)
        lay.setContentsMargins(12, 10, 12, 10)
        lay.setSpacing(5)
        t = QLabel("CONTROLS"); t.setObjectName("title"); lay.addWidget(t)
        self._flip_btn = QPushButton("Flip"); self._flip_btn.setCheckable(False); lay.addWidget(self._flip_btn)
        self._overlay_btn = QPushButton("Overlay"); self._overlay_btn.setCheckable(True); lay.addWidget(self._overlay_btn)
        self._rot_btn = QPushButton("Rotate 90"); self._rot_btn.setCheckable(False); lay.addWidget(self._rot_btn)
        self._reset_btn = QPushButton("Reset"); self._reset_btn.setCheckable(False); lay.addWidget(self._reset_btn)
        sep = QFrame(); sep.setFrameShape(QFrame.Shape.HLine); sep.setStyleSheet("border:none;border-top:1px solid #e0e0e0"); lay.addWidget(sep)
        lay.addWidget(QLabel("GT Opacity"))
        self._gt_slider = QSlider(Qt.Orientation.Horizontal); self._gt_slider.setRange(10, 100); self._gt_slider.setValue(100); lay.addWidget(self._gt_slider)
        lay.addWidget(QLabel("Result Opacity"))
        self._pred_slider = QSlider(Qt.Orientation.Horizontal); self._pred_slider.setRange(10, 100); self._pred_slider.setValue(100); lay.addWidget(self._pred_slider)
        sep2 = QFrame(); sep2.setFrameShape(QFrame.Shape.HLine); sep2.setStyleSheet("border:none;border-top:1px solid #e0e0e0"); lay.addWidget(sep2)
        stats = QFrame(); stats.setObjectName("stats")
        s_lay = QVBoxLayout(stats); s_lay.setContentsMargins(8, 6, 8, 6); s_lay.setSpacing(2)
        st = QLabel("Error Stats"); st.setObjectName("statsTitle"); s_lay.addWidget(st)
        self._stats_val = QLabel("--"); self._stats_val.setObjectName("statsValue"); self._stats_val.setStyleSheet("color: #ff4d4f;"); s_lay.addWidget(self._stats_val)
        self._stats_sub = QLabel(""); self._stats_sub.setObjectName("statsSub"); s_lay.addWidget(self._stats_sub)
        lay.addWidget(stats)
        self._detail_btn = QPushButton("View Details"); self._detail_btn.setObjectName("link"); lay.addWidget(self._detail_btn)
        lay.addStretch()

    def update_theme(self, dark: bool):
        self._dark = dark
        self.setStyleSheet(_FLOAT_DARK if dark else _FLOAT_LIGHT)

    def set_overlay_mode(self, on: bool):
        self._overlay_btn.setChecked(on)

    def set_stats(self, total: int, breakdown: dict):
        mis = breakdown.get(ErrorType.MISCLASSIFIED, 0)
        new = breakdown.get(ErrorType.NEW, 0)
        miss = breakdown.get(ErrorType.MISSING, 0)
        errors = mis + new + miss
        if total == 0:
            self._stats_val.setText("0%"); self._stats_sub.setText("0 errors / 0 cells")
        else:
            rate = errors / total * 100
            self._stats_val.setText(f"{rate:.1f}%")
            self._stats_sub.setText(f"{errors} errors / {total} cells  M:{mis} N:{new} X:{miss}")


class Overlay3DViewWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._dataset: Optional[OverlayDataset] = None
        self._dark = False
        self._pw = 4.0
        self._ph = 3.0
        self._gap = 0.05
        self._overlay_on = False
        self._showing_front = True
        self._rot_z_quarter = 0
        self._gt_opacity = 1.0
        self._pred_opacity = 1.0
        self._layout = QHBoxLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._plotter = QtInteractor(self)
        self._plotter.set_background(_BG_LIGHT)
        self._plotter.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self._layout.addWidget(self._plotter)
        self._float = FloatPanel(self)
        self._float.setVisible(False)
        self._float._flip_btn.clicked.connect(self._cmd_flip)
        self._float._overlay_btn.clicked.connect(lambda checked: self._cmd_overlay(checked))
        self._float._rot_btn.clicked.connect(self._cmd_rotate90)
        self._float._reset_btn.clicked.connect(self._cmd_reset)
        self._float._gt_slider.valueChanged.connect(lambda v: self._on_gt_opacity(v / 100.0))
        self._float._pred_slider.valueChanged.connect(lambda v: self._on_pred_opacity(v / 100.0))
        self._float._detail_btn.clicked.connect(self._on_view_details)
        self._hint = QLabel("Drag rotate | Scroll zoom | R:Rotate | F:Flip | O:Overlay | Esc:Reset", self)
        self._hint.setStyleSheet("color:#999;font-size:10px;background:rgba(255,255,255,0.8);border-radius:4px;padding:3px 8px")
        self._hint.setVisible(False)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._float.move(self.width() - self._float.width() - 8, 8)
        if self._hint.isVisible():
            hw = self._hint.sizeHint().width()
            self._hint.move((self.width() - hw) // 2, self.height() - 28)

    def set_dataset(self, dataset=None, gt_image_path=None, pred_image_path=None):
        self._dataset = dataset
        if dataset is None or dataset.cell_count == 0:
            self.show_no_data()
            return
        self._overlay_on = False
        self._showing_front = True
        self._rot_z_quarter = 0
        self._float.setVisible(True)
        self._float.set_overlay_mode(False)
        self._hint.setVisible(True)
        self._build_scene(dataset)
        self._update_stats(dataset)

    def update_theme(self, dark: bool):
        self._dark = dark
        if self._plotter is not None:
            self._plotter.set_background(_BG_DARK if dark else _BG_LIGHT)
        if self._float.isVisible():
            self._float.update_theme(dark)

    def show_no_data(self):
        self._dataset = None
        if self._plotter is not None:
            self._plotter.clear()
        self._float.setVisible(False)
        self._hint.setVisible(False)

    def get_dataset(self):
        return self._dataset

    def _build_scene(self, ds):
        p = self._plotter
        p.clear()
        hw, hh, gap = self._pw / 2, self._ph / 2, self._gap

        # White opaque border around the panel
        margin = 0.25
        border_w = self._pw + margin * 2
        border_h = self._ph + margin * 2
        border_z = gap * 1.3

        borders = [
            # Top border
            pv.Cube(center=(0, self._ph/2 + margin/2, 0),
                    x_length=border_w, y_length=margin, z_length=border_z),
            # Bottom border
            pv.Cube(center=(0, -self._ph/2 - margin/2, 0),
                    x_length=border_w, y_length=margin, z_length=border_z),
            # Left border
            pv.Cube(center=(-self._pw/2 - margin/2, 0, 0),
                    x_length=margin, y_length=self._ph, z_length=border_z),
            # Right border
            pv.Cube(center=(self._pw/2 + margin/2, 0, 0),
                    x_length=margin, y_length=self._ph, z_length=border_z),
        ]
        for i, b in enumerate(borders):
            p.add_mesh(b, color="#ffffff", name=f"border_{i}", opacity=1.0, smooth_shading=True)

        # Inner transparent acrylic planes (same size as scatter area)
        pc = "#d0d5db" if not self._dark else "#2a2a2e"
        for name, z_pos, direction in [("front_plane", gap/2, (0,0,1)), ("back_plane", -gap/2, (0,0,-1))]:
            plane = pv.Plane(center=(0,0,z_pos), direction=direction, i_size=self._pw, j_size=self._ph, i_resolution=1, j_resolution=1)
            p.add_mesh(plane, color=pc, name=name, opacity=0.08, smooth_shading=True)

        # 3D text labels on the white border area
            self._add_labels(p, ds)
        

        self._add_scatter_gt(ds, gap/2 + 0.01, prefix="front_gt")
        self._add_scatter_result(ds, -gap/2 - 0.01, ds.has_pred)

        p.camera_position = [(0, -self._ph*0.55, self._pw*0.85), (0,0,0), (0,0,1)]
        try:
            p.camera.SetParallelProjection(False)
            p.camera.SetViewAngle(40)
        except Exception:
            pass
        try:
            p.remove_all_lights()
            p.add_light(pv.Light(position=(self._pw, self._ph, self._pw*0.6), light_type="scene_light", intensity=0.75))
            p.add_light(pv.Light(position=(-self._pw, -self._ph, self._pw*0.4), light_type="scene_light", intensity=0.40))
            p.add_light(pv.Light(position=(0, 0, -self._pw), light_type="scene_light", intensity=0.20))
        except Exception:
            pass
        p.add_key_event("f", lambda: self._cmd_flip())
        p.add_key_event("o", lambda: self._cmd_overlay(not self._overlay_on))
        p.add_key_event("r", lambda: self._cmd_rotate90())
        p.add_key_event("escape", lambda: self._cmd_reset())


    def _add_labels(self, p, ds):
        """Add screen-space text labels for GT and Result faces."""
        sid = ds.section_id
        p.add_text(
            f"Ground Truth  [{sid}]",
            position="upper_left", font_size=11, color="#333333",
            font="arial", shadow=False,
        )
        p.add_text(
            f"Prediction  [{sid}]",
            position="upper_right", font_size=11, color="#888888",
            font="arial", shadow=False,
        )

    def _add_scatter_gt(self, ds, z, prefix="gt"):
        p = self._plotter
        layers = {}
        for c in ds.cells:
            layer = c.ground_truth or ""
            if not layer or layer.upper() == "NA":
                continue
            layers.setdefault(layer, []).append((c.x, c.y, z))
        for layer, pts in layers.items():
            arr = np.array(pts, dtype=np.float64)
            color = _hex_to_rgb(get_layer_color(layer))
            p.add_mesh(pv.PolyData(arr), color=color, point_size=_POINT_SIZE_NORMAL,
                       render_points_as_spheres=True, opacity=1.0, lighting=False,
                       name=f"{prefix}_{layer}")

    def _add_scatter_result(self, ds, z, has_results):
        p = self._plotter
        if not has_results:
            # No prediction data: render nothing on back face
            return
        # Render prediction scatter colored by domain (independent of GT)
        from model.overlay_data import get_domain_color
        domains = {}
        for c in ds.cells:
            domain = c.prediction or ""
            if not domain or domain.upper() == "NA":
                domain = "Unknown"
            domains.setdefault(domain, []).append((c.x, c.y, z))
        for domain, pts in domains.items():
            arr = np.array(pts, dtype=np.float64)
            color = _hex_to_rgb(get_domain_color(domain))
            p.add_mesh(pv.PolyData(arr), color=color, point_size=_POINT_SIZE_NORMAL,
                       render_points_as_spheres=True, opacity=1.0, lighting=False,
                       name=f"res_domain_{domain}")

    def _update_stats(self, ds):
        bd = {ErrorType.MISCLASSIFIED: 0, ErrorType.NEW: 0, ErrorType.MISSING: 0}
        for c in ds.cells:
            if c.error_type in bd:
                bd[c.error_type] += 1
        self._float.set_stats(ds.cell_count, bd)

    def _cmd_flip(self):
        if self._dataset is None:
            return
        self._showing_front = not self._showing_front
        cam = self._plotter.camera
        pos = list(cam.GetPosition())
        fp = list(cam.GetFocalPoint())
        dz = pos[2] - fp[2]
        cam.SetPosition(pos[0], pos[1], fp[2] - dz)
        self._plotter.render()

    def _cmd_overlay(self, on):
        self._overlay_on = on
        self._float.set_overlay_mode(on)
        self._update_visibility()
        self._plotter.render()

    def _cmd_reset(self):
        if self._dataset is None:
            return
        self._overlay_on = False
        self._showing_front = True
        self._rot_z_quarter = 0
        self._gt_opacity = 1.0
        self._pred_opacity = 1.0
        self._float._gt_slider.setValue(100)
        self._float._pred_slider.setValue(100)
        self._float.set_overlay_mode(False)
        self._plotter.camera_position = [(0, -self._ph*0.55, self._pw*0.85), (0,0,0), (0,0,1)]
        self._update_visibility()
        self._plotter.render()

    def _cmd_rotate90(self):
        if self._dataset is None:
            return
        self._rot_z_quarter = (self._rot_z_quarter + 1) % 4
        cam = self._plotter.camera
        pos = list(cam.GetPosition())
        fp = list(cam.GetFocalPoint())
        dx, dy = pos[0] - fp[0], pos[1] - fp[1]
        cam.SetPosition(fp[0] - dy, fp[1] + dx, pos[2])
        cam.SetViewUp(0, 0, 1)
        self._plotter.render()

    def _on_gt_opacity(self, v):
        self._gt_opacity = float(v)
        self._update_visibility()
        self._plotter.render()

    def _on_pred_opacity(self, v):
        self._pred_opacity = float(v)
        self._update_visibility()
        self._plotter.render()

    def _on_view_details(self):
        win = self.window()
        if win is not None and hasattr(win, "show_mismatched_points"):
            win.show_mismatched_points()

    def _update_visibility(self):
        if self._plotter is None:
            return
        p = self._plotter
        if self._overlay_on:
            front_op, back_op = self._gt_opacity, self._pred_opacity
        elif self._showing_front:
            front_op, back_op = self._gt_opacity, 0.0
        else:
            front_op, back_op = 0.0, self._pred_opacity

        for name in p.actors:
            try:
                actor = p.actors[name]
                if name.startswith("front_gt_"):
                    actor.GetProperty().SetOpacity(front_op)
                elif name.startswith("back_gt_"):
                    actor.GetProperty().SetOpacity(back_op)
                elif name.startswith("res_"):
                    actor.GetProperty().SetOpacity(back_op)
                elif name.startswith("front_plane"):
                    actor.GetProperty().SetOpacity(0.08 if front_op > 0 else 0.03)
                elif name.startswith("back_plane"):
                    actor.GetProperty().SetOpacity(0.08 if back_op > 0 else 0.03)
            except Exception:
                pass
