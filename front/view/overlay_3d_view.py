"""3D acrylic panel view: pv.Cube body, front=GT, back=Prediction.

Per updated spec:
- pv.Box() thin panel, 4:3 aspect, ~1% thickness
- Front face (z=+e): Ground Truth scatter
- Back face (z=-e): Prediction scatter
- Acrylic: opacity 0.25, specular 0.7, specular_power 80, ambient 0.2
- Trackball interaction, perspective camera
- Overlay mode: both GT+Pred on front, errors=RED, opacity sliders
"""
from typing import Optional

import numpy as np
import pyvista as pv
from pyvistaqt import QtInteractor
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QPushButton,
    QSizePolicy, QSlider, QVBoxLayout, QWidget,
)
from model.overlay_data import OverlayDataset
from utils.logger import logger


# ====================================================================
#  Cluster palette (vibrant but not neon)
# ====================================================================
_CLUSTER_COLORS = {
    "Layer1": "#5ba0d0", "Layer2": "#3cba9a", "Layer3": "#4caf6e",
    "Layer4": "#d4b030", "Layer5": "#d48840", "Layer6": "#d47068", "WM": "#9b6ab8",
}
_PRED_EXTRA = {
    "1": "#6aaede", "2": "#4ec8aa", "3": "#5eb87c",
    "4": "#dcb840", "5": "#dc9050", "6": "#dc7870",
}
_FALLBACK = "#a0a8b0"
_ERROR_RED = "#ff4d4f"

# Acrylic material
_ACRYLIC = dict(opacity=0.30, pbr=True, metallic=0.02, roughness=0.15,
                specular=0.95, specular_power=130, ambient=0.08, diffuse=0.5,
                smooth_shading=True)

_POINT_SIZE = 16
_ERROR_POINT_SIZE = 22

# Background and acrylic panel colors per theme
_BG_DARK = "#101113"
_BG_LIGHT = "#e4e4e8"
_ACRYLIC_DARK = "#a8aeb6"   # lighter than dark bg
_ACRYLIC_LIGHT = "#f0f0f4"  # lighter than light bg


def _rgb(h: str) -> tuple:
    h = h.lstrip("#"); return tuple(int(h[i:i+2],16)/255.0 for i in (0,2,4))


# ====================================================================
#  Floating panel (right side)
# ====================================================================
_FLOAT_LIGHT = (
    "QFrame { background: rgba(255,255,255,0.92); border: 1px solid #e0e0e0;"
    " border-radius: 10px; }"
    "QPushButton { font-size: 10px; padding: 3px 8px; border: 1px solid #ddd;"
    " border-radius: 5px; background: #fafafa; color: #555; }"
    "QPushButton:hover { background: #eee; }"
    "QLabel { font-size: 9px; color: #888; }"
    "QSlider::groove:horizontal { height: 3px; background: #e0e0e0; border-radius: 2px; }"
    "QSlider::handle:horizontal { width: 10px; margin: -4px 0; background: #bbb;"
    " border-radius: 5px; }"
)

_FLOAT_DARK = (
    "QFrame { background: rgba(35,35,38,0.94); border: 1px solid rgba(255,255,255,0.06);"
    " border-radius: 10px; }"
    "QPushButton { font-size: 10px; padding: 3px 8px; border: 1px solid rgba(255,255,255,0.08);"
    " border-radius: 5px; background: rgba(255,255,255,0.04); color: #b0b0b5; }"
    "QPushButton:hover { background: rgba(255,255,255,0.08); }"
    "QLabel { font-size: 9px; color: #8a8a90; }"
    "QSlider::groove:horizontal { height: 3px; background: rgba(255,255,255,0.08); border-radius: 2px; }"
    "QSlider::handle:horizontal { width: 10px; margin: -4px 0; background: #666;"
    " border-radius: 5px; }"
)


class _FloatingPanel(QFrame):
    def __init__(self, parent, on_flip, on_overlay_toggle, on_reset,
                 on_gt_opacity, on_pred_opacity):
        super().__init__(parent)
        self._dark = False
        self.setStyleSheet(_FLOAT_LIGHT)
        self.setFixedWidth(130)

        ly = QVBoxLayout(self); ly.setContentsMargins(8,8,8,8); ly.setSpacing(4)

        self._title_label = QLabel("CONTROLS")
        ly.addWidget(self._title_label)

        bf = QPushButton(chr(0x21C4)+" Flip (F)"); bf.clicked.connect(on_flip); ly.addWidget(bf)

        self._btn_ov = QPushButton(chr(0x25CB)+" Overlay (O)")
        self._btn_ov.setCheckable(True); self._btn_ov.clicked.connect(on_overlay_toggle)
        ly.addWidget(self._btn_ov)

        br = QPushButton(chr(0x21BA)+" Reset"); br.clicked.connect(on_reset); ly.addWidget(br)
        ly.addSpacing(4)

        self._slider_box = QWidget()
        sl = QVBoxLayout(self._slider_box); sl.setContentsMargins(0,0,0,0); sl.setSpacing(2)

        gl = QLabel("GT Opacity"); sl.addWidget(gl)
        self._gt_slider = QSlider(Qt.Orientation.Horizontal)
        self._gt_slider.setRange(0,100); self._gt_slider.setValue(100)
        self._gt_slider.setFixedHeight(16)
        self._gt_slider.valueChanged.connect(on_gt_opacity); sl.addWidget(self._gt_slider)

        pl = QLabel("Pred Opacity"); sl.addWidget(pl)
        self._pred_slider = QSlider(Qt.Orientation.Horizontal)
        self._pred_slider.setRange(0,100); self._pred_slider.setValue(100)
        self._pred_slider.setFixedHeight(16)
        self._pred_slider.valueChanged.connect(on_pred_opacity); sl.addWidget(self._pred_slider)

        ly.addWidget(self._slider_box)
        self._slider_box.setVisible(False)
        ly.addStretch()

    def update_theme(self, dark: bool):
        self._dark = dark
        self.setStyleSheet(_FLOAT_DARK if dark else _FLOAT_LIGHT)
        self._title_label.setStyleSheet(
            "font-weight:600; color:#b0b0b5;" if dark
            else "font-weight:600; color:#555;"
        )

    def set_overlay_mode(self, on: bool):
        self._btn_ov.setChecked(on)
        self._slider_box.setVisible(on)


class Overlay3DViewWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._dataset = None
        self._plotter = None
        self._overlay_on = False
        self._showing_front = True
        self._gt_actors = []   # actor names for GT scatter
        self._pred_actors = []  # actor names for Pred scatter
        self._panel_actor = None

        layout = QVBoxLayout(self); layout.setContentsMargins(4,4,4,4); layout.setSpacing(2)

        self._plotter = QtInteractor(self)
        self._plotter.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self._plotter.enable_anti_aliasing()
        self._plotter.set_background(_BG_LIGHT)  # overridden by update_theme
        self._plotter.hide_axes()
        self._plotter.enable_trackball_style()
        layout.addWidget(self._plotter, 1)

        self._float = _FloatingPanel(
            self._plotter,
            self._cmd_flip, self._cmd_overlay, self._cmd_reset,
            self._on_gt_opacity, self._on_pred_opacity,
        )
        self._float.setVisible(False)

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self._float.setGeometry(self.width()-146, 12, 130, min(self.height()-24, 420))

    # ==================================================================
    #  Public
    # ==================================================================
    def set_dataset(self, ds):
        self._dataset = ds
        if ds is None or ds.cell_count == 0:
            self._plotter.clear(); self._float.setVisible(False); return
        self._overlay_on = False; self._showing_front = True
        self._float.setVisible(True); self._float.set_overlay_mode(False)
        self._plotter.setVisible(True)
        self._build_scene(ds)

    def update_theme(self, dark):
        self._plotter.set_background(_BG_LIGHT if not dark else _BG_DARK)
        self._dark = dark
        # Fix rounded corner artifacts: set Qt widget background to match pyvista bg
        self._plotter.setStyleSheet(
            "background-color: " + (_BG_DARK if dark else _BG_LIGHT) + ";"
        )
        # Update acrylic panel color if scene is built
        if hasattr(self, "_plotter") and self._dataset is not None:
            try:
                panel = self._plotter.actors.get("acrylic_panel")
                if panel is not None:
                    col = _rgb(_ACRYLIC_DARK if dark else _ACRYLIC_LIGHT)
                    panel.GetProperty().SetColor(*col)
                    self._plotter.render()
            except Exception:
                pass
        if hasattr(self, "_float") and self._float.isVisible():
            self._float.update_theme(dark)

    def show_no_data(self):
        self._dataset = None; self._plotter.clear()
        self._float.setVisible(False)

    def get_dataset(self):
        return self._dataset

    # ==================================================================
    #  Scene
    # ==================================================================
    def _build_scene(self, ds):
        p = self._plotter; p.clear()
        self._gt_actors = []; self._pred_actors = []

        xs = np.array([c.x for c in ds.cells], dtype=np.float64)
        ys = np.array([c.y for c in ds.cells], dtype=np.float64)
        cx = (xs.min()+xs.max())/2; cy = (ys.min()+ys.max())/2
        dw = xs.max()-xs.min(); dh = ys.max()-ys.min()
        margin = 1.08

        # 4:3 panel
        if dw/dh > 4/3:
            pw = dw*margin; ph = pw*3/4
        else:
            ph = dh*margin; pw = ph*4/3
        thickness = pw*0.015
        hw, hh, ht = pw/2, ph/2, thickness/2

        self._cx=cx; self._cy=cy; self._dw=dw; self._dh=dh
        self._hw=hw; self._hh=hh; self._ht=ht

        # ---- Acrylic panel ----
        box = pv.Cube(center=(0,0,0), x_length=pw, y_length=ph, z_length=thickness)
        panel_color = _ACRYLIC_DARK if getattr(self, "_dark", True) else _ACRYLIC_LIGHT
        p.add_mesh(box, color=panel_color, name="acrylic_panel",
                   opacity=0.35, pbr=True, metallic=0.03, roughness=0.20,
                   specular=0.95, specular_power=120, ambient=0.10,
                   diffuse=0.5, smooth_shading=True)

        # ---- Scatter: GT (front, +Z) ----
        def _map(cells_in, z_off):
            px = np.array([(c.x-cx)/(dw/2)*(hw*0.96) for c in cells_in], dtype=np.float64)
            py = np.array([(c.y-cy)/(dh/2)*(hh*0.96) for c in cells_in], dtype=np.float64)
            return px, py, np.full_like(px, z_off)

        gt_by_lb = {}
        for c in ds.cells:
            gt_by_lb.setdefault(c.ground_truth, []).append(c)
        for lb, cells in gt_by_lb.items():
            px, py, pz = _map(cells, ht+3.0)
            col = _rgb(_CLUSTER_COLORS.get(lb, _FALLBACK))
            nm = "gt_"+str(lb)
            p.add_mesh(pv.PolyData(np.column_stack([px,py,pz])),
                       color=col, point_size=_POINT_SIZE,
                       render_points_as_spheres=True,
                       opacity=1.0, name=nm, ambient=0.5, diffuse=0.8)
            self._gt_actors.append(nm)

        # ---- Scatter: Pred (back, -Z) ----
        pred_by_lb = {}
        for c in ds.cells:
            pred_by_lb.setdefault(c.prediction, []).append(c)
        for lb, cells in pred_by_lb.items():
            px, py, pz = _map(cells, -ht-3.0)
            col = _rgb(_PRED_EXTRA.get(lb, _FALLBACK))
            nm = "pred_"+str(lb)
            p.add_mesh(pv.PolyData(np.column_stack([px,py,pz])),
                       color=col, point_size=_POINT_SIZE,
                       render_points_as_spheres=True,
                       opacity=0.0, name=nm, ambient=0.5, diffuse=0.8)
            self._pred_actors.append(nm)

        # ---- Lighting ----
        p.remove_all_lights()
        p.add_light(pv.Light(position=(pw,ph,pw*0.5), light_type="scene_light", intensity=0.70))
        p.add_light(pv.Light(position=(-pw,-ph,pw*0.3), light_type="scene_light", intensity=0.35))
        p.add_light(pv.Light(position=(0,0,-pw), light_type="scene_light", intensity=0.18))

        # ---- Camera ----
        p.camera_position = [(0, -ph*0.7, pw*0.55), (0,0,0), (0,0,1)]
        p.camera.SetParallelProjection(False); p.camera.SetViewAngle(40)

        self._update_visibility()
        p.add_key_event("f", lambda: self._cmd_flip())
        p.add_key_event("o", lambda: self._cmd_overlay(not self._overlay_on))

    # ==================================================================
    #  Visibility
    # ==================================================================
    def _update_visibility(self):
        p = self._plotter
        if self._overlay_on:
            # Both visible on front
            for n in self._gt_actors:
                try: p.actors[n].GetProperty().SetOpacity(self._gt_opacity_val)
                except: pass
            for n in self._pred_actors:
                try:
                    act = p.actors[n]
                    act.GetProperty().SetOpacity(self._pred_opacity_val)
                    # Move Pred points to front face in overlay mode
                    pts = act.GetMapper().GetInput()
                    # Keep on front but offset slightly behind GT
                except: pass
            # Also make back-facing Pred copies visible
            self._render_overlay_errors()
        else:
            # Normal: front=GT, back=Pred
            for n in self._gt_actors:
                try: p.actors[n].GetProperty().SetOpacity(1.0 if self._showing_front else 0.0)
                except: pass
            for n in self._pred_actors:
                try: p.actors[n].GetProperty().SetOpacity(0.0 if self._showing_front else 1.0)
                except: pass
            # Remove overlay error points if any
            for key in list(p.actors.keys()):
                if isinstance(key, str) and key.startswith("overlay_err"):
                    try: p.remove_actor(key)
                    except: pass

    def _render_overlay_errors(self):
        if self._dataset is None or not self._overlay_on:
            return
        p = self._plotter
        # Remove old overlay errors
        for key in list(p.actors.keys()):
            if isinstance(key, str) and key.startswith("overlay_err"):
                try: p.remove_actor(key)
                except: pass

        # Find misclassified cells, map to panel surface
        xs_mis, ys_mis, zs_mis = [], [], []
        cx_v = self._cx; cy_v = self._cy
        dw_v = max(self._dw, 1); dh_v = max(self._dh, 1)
        for c in self._dataset.cells:
            if c.ground_truth != c.prediction:
                px = (c.x-cx_v)/(dw_v/2)*(self._hw*0.96)
                py = (c.y-cy_v)/(dh_v/2)*(self._hh*0.96)
                xs_mis.append(px); ys_mis.append(py)
                zs_mis.append(self._ht+3.0)  # front face

        if xs_mis:
            x = np.array(xs_mis, dtype=np.float64)
            y = np.array(ys_mis, dtype=np.float64)
            z = np.array(zs_mis, dtype=np.float64)
            p.add_mesh(pv.PolyData(np.column_stack([x,y,z])),
                       color=_rgb(_ERROR_RED), point_size=_ERROR_POINT_SIZE,
                       render_points_as_spheres=True,
                       opacity=1.0, name="overlay_err",
                       ambient=0.6, diffuse=0.8)

        p.render()

    # ==================================================================
    #  Commands
    # ==================================================================
    def _cmd_flip(self):
        if self._dataset is None: return
        self._showing_front = not self._showing_front
        self._update_visibility()
        cam = self._plotter.camera
        pos = list(cam.GetPosition()); fp = list(cam.GetFocalPoint())
        pos[0]=fp[0]-(pos[0]-fp[0]); pos[1]=fp[1]-(pos[1]-fp[1])
        cam.SetPosition(*pos); self._plotter.render()

    def _cmd_overlay(self, on):
        if self._dataset is None: return
        self._overlay_on = on
        self._float.set_overlay_mode(on)
        self._gt_opacity_val = 1.0; self._pred_opacity_val = 1.0

        if on:
            # Rotate to front view
            self._showing_front = True
            if hasattr(self, "_hw"):
                self._plotter.camera_position = [
                    (0, -self._hh*1.0, self._hw*0.6), (0,0,0), (0,0,1)
                ]
        self._update_visibility()
        self._plotter.render()

    def _cmd_reset(self):
        if self._dataset is None: return
        self._showing_front = True; self._overlay_on = False
        self._float.set_overlay_mode(False)
        xs = np.array([c.x for c in self._dataset.cells])
        ys = np.array([c.y for c in self._dataset.cells])
        dw, dh = xs.max()-xs.min(), ys.max()-ys.min()
        pw = (dw*1.08) if dw/dh>4/3 else (dh*1.08*4/3)
        ph = pw*3/4
        self._plotter.camera_position = [(0,-ph*0.7,pw*0.55),(0,0,0),(0,0,1)]
        self._update_visibility(); self._plotter.render()

    def _on_gt_opacity(self, v):
        self._gt_opacity_val = v/100.0; self._update_visibility(); self._plotter.render()

    def _on_pred_opacity(self, v):
        self._pred_opacity_val = v/100.0; self._update_visibility(); self._plotter.render()
