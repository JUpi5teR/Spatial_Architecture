# coding: utf-8
# Build: spatial_viewer.py - PySide6 + PyVista spatial transcriptomics viewer

import numpy as np
import json
import csv
import os
from pathlib import Path
import logging
logger = logging.getLogger(__name__)
from typing import Optional
from dataclasses import dataclass, field
from collections import defaultdict

# ============================================================
# DATA LOADER
# ============================================================
@dataclass
class CellData:
    cell_id: str
    x: float
    y: float
    cluster: str
    metadata: dict = field(default_factory=dict)

@dataclass
class SpatialDataset:
    section_id: str
    cells: list[CellData] = field(default_factory=list)
    clusters: dict[str, list[int]] = field(default_factory=dict)  # cluster_name -> cell indices
    panel_w: float = 4.0
    panel_h: float = 3.0

def load_spatial_dataset(data_root: str, section_id: str,
                         gt_column: str = "layer_guess_reordered") -> Optional[SpatialDataset]:
    sec_dir = Path(data_root) / section_id
    meta_path = sec_dir / "metadata.tsv"
    pos_path = sec_dir / "spatial" / "tissue_positions_list.csv"
    scale_path = sec_dir / "spatial" / "scalefactors_json.json"

    if not meta_path.exists() or not pos_path.exists():
        return None

    # Read scale
    scale = 0.15
    if scale_path.exists():
        with open(scale_path) as f:
            scale = float(json.load(f).get("tissue_hires_scalef", 0.15))

    # Read hires dim
    hires_dim = 2000.0
    img_path = sec_dir / "spatial" / "tissue_hires_image.png"
    if img_path.exists():
        try:
            import cv2
            im = cv2.imread(str(img_path))
            if im is not None:
                hires_dim = float(max(im.shape[0], im.shape[1]))
        except:
            pass

    # Read positions (filter in_tissue=1)
    positions = {}
    with open(pos_path) as f:
        for line in f:
            parts = line.strip().split(",")
            if len(parts) >= 6 and parts[1] == "1":
                barcode = parts[0]
                px_row, px_col = float(parts[4]), float(parts[5])
                positions[barcode] = (px_row, px_col)

    # Read metadata
    meta_rows = []
    with open(meta_path, encoding="utf-8") as f:
        reader = csv.DictReader(f, delimiter="\t")
        fieldnames = reader.fieldnames or []
        for row in reader:
            meta_rows.append(row)

    # Build cells
    cells = []
    clusters = defaultdict(list)
    for i, row in enumerate(meta_rows):
        barcode = row.get("barcode", "").strip()
        if barcode not in positions:
            continue
        cluster = row.get(gt_column, "").strip()
        if not cluster or cluster.upper() == "NA":
            continue

        px_row, px_col = positions[barcode]
        hx = px_col * scale
        hy = px_row * scale
        x = (hx / hires_dim) * 4.0 - 2.0
        y = 1.5 - (hy / hires_dim) * 3.0

        metadata = {k: row.get(k, "") for k in fieldnames if k not in ("barcode", gt_column)}

        cells.append(CellData(cell_id=barcode, x=x, y=y, cluster=cluster, metadata=metadata))
        clusters[cluster].append(len(cells) - 1)

    if not cells:
        return None

    return SpatialDataset(
        section_id=section_id,
        cells=cells,
        clusters=dict(clusters),
    )


# ============================================================
# ALPHA SHAPE / CONCAVE HULL (SciPy only)
# ============================================================
def compute_alpha_shape(points_2d: np.ndarray, alpha: float = 0.3) -> list[np.ndarray]:
    """Compute alpha shape boundaries for 2D points using Delaunay triangulation.
    Returns list of boundary polygons (each is Nx2 array), handles multiple regions.
    """
    from scipy.spatial import Delaunay
    if len(points_2d) < 3:
        return [points_2d]

    tri = Delaunay(points_2d)
    # For each triangle, compute circumradius
    # Keep edges that belong to triangles with circumradius <= 1/alpha
    edges_count = defaultdict(int)
    for simplex in tri.simplices:
        a, b, c = points_2d[simplex]
        # Circumradius = abc / (4 * area)
        ab = np.linalg.norm(b - a)
        bc = np.linalg.norm(c - b)
        ca = np.linalg.norm(a - c)
        s = (ab + bc + ca) / 2.0
        area = np.sqrt(max(0, s * (s - ab) * (s - bc) * (s - ca)))
        if area < 1e-10:
            continue
        r = (ab * bc * ca) / (4.0 * area)
        if r <= 1.0 / alpha:
            for i, j in [(0,1), (1,2), (2,0)]:
                edge = tuple(sorted((simplex[i], simplex[j])))
                edges_count[edge] += 1

    # Boundary edges appear exactly once
    boundary_edges = [e for e, c in edges_count.items() if c == 1]

    if not boundary_edges:
        # Fallback: convex hull
        from scipy.spatial import ConvexHull
        hull = ConvexHull(points_2d)
        return [points_2d[hull.vertices]]

    # Build connected components of boundary edges
    adj = defaultdict(list)
    for u, v in boundary_edges:
        adj[u].append(v)
        adj[v].append(u)

    visited = set()
    polygons = []
    for start in adj:
        if start in visited:
            continue
        path = [start]
        visited.add(start)
        cur = start
        while True:
            nxt = None
            for nb in adj[cur]:
                if nb not in visited:
                    nxt = nb
                    break
            if nxt is None:
                # Try to close the loop
                for nb in adj[cur]:
                    if nb == start:
                        break
                break
            path.append(nxt)
            visited.add(nxt)
            cur = nxt
        if len(path) >= 3:
            poly = points_2d[path]
            polygons.append(poly)

    return polygons if polygons else [points_2d]


# ============================================================
# LAYER COLORS
# ============================================================
CLUSTER_COLORS = {
    "Layer1": "#5DADE2", "Layer2": "#2E86C1", "Layer3": "#2874A6",
    "Layer4": "#1F618D", "Layer5": "#1A5276", "Layer6": "#154360",
    "WM":     "#5D6D7E",
}
_FALLBACK = ["#008B8B","#008080","#0E6655","#1E90FF","#7B68EE","#6A5ACD",
             "#483D8B","#4B0082","#8E44AD","#1ABC9C","#117A65","#191970"]

def get_cluster_color(name: str) -> tuple:
    h = CLUSTER_COLORS.get(name)
    if not h:
        h = _FALLBACK[sum(ord(c) for c in name) % len(_FALLBACK)]
    h = h.lstrip("#")
    return tuple(int(h[i:i+2], 16)/255.0 for i in (0,2,4))


# ============================================================
# MAIN VIEWER
# ============================================================
from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QApplication, QFrame, QHBoxLayout, QLabel,
    QPushButton, QSizePolicy, QTextEdit,
    QVBoxLayout, QWidget,
)
import pyvista as pv
try:
    import vtk
    from vtkmodules.vtkRenderingCore import vtkPointPicker, vtkCellPicker
except:
    pass
from pyvistaqt import QtInteractor


class SpatialViewerWidget(QWidget):
    cluster_hovered = Signal(str, int, dict)  # cluster_name, cell_count, metadata_preview

    def __init__(self, parent=None):
        super().__init__(parent)
        self._dataset: Optional[SpatialDataset] = None
        self._mode = "explore"
        self._hovered_cluster: Optional[str] = None
        self._boundary_actors = []
        self._hover_observer_id = None
        self._results_dataset: Optional[SpatialDataset] = None

        self._pw = 4.0
        self._ph = 3.0
        self._gap = 0.05

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self._plotter = QtInteractor(self)
        self._plotter.set_background("#e4e8ec")
        self._plotter.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        layout.addWidget(self._plotter)

        self._setup_scene()

    def closeEvent(self, event):
        """Clean up VTK resources before closing."""
        try:
            self._teardown_hover()
        except:
            pass
        try:
            self._plotter.close()
        except:
            pass
        super().closeEvent(event)

    def set_dark(self, dark: bool):
        """Update plotter background to match theme."""
        bg = "#1e1e21" if dark else "#e4e8ec"
        self._plotter.set_background(bg)
        self._plotter.render()

    def _setup_scene(self):
        p = self._plotter
        p.clear()
        gap = self._gap
        hw, hh = self._pw / 2, self._ph / 2

        # White border
        margin = 0.25
        bw, bh = self._pw + margin * 2, self._ph + margin * 2
        bz = gap * 1.3
        borders = [
            pv.Cube(center=(0, self._ph/2+margin/2, 0), x_length=bw, y_length=margin, z_length=bz),
            pv.Cube(center=(0, -self._ph/2-margin/2, 0), x_length=bw, y_length=margin, z_length=bz),
            pv.Cube(center=(-self._pw/2-margin/2, 0, 0), x_length=margin, y_length=self._ph, z_length=bz),
            pv.Cube(center=(self._pw/2+margin/2, 0, 0), x_length=margin, y_length=self._ph, z_length=bz),
        ]
        for i, b in enumerate(borders):
            p.add_mesh(b, color="#ffffff", name=f"border_{i}", opacity=1.0, smooth_shading=True)

        # Transparent planes
        for name, z_pos in [("front_plane", gap/2), ("back_plane", -gap/2)]:
            plane = pv.Plane(center=(0, 0, z_pos), direction=(0, 0, 1),
                           i_size=self._pw, j_size=self._ph, i_resolution=1, j_resolution=1)
            p.add_mesh(plane, color="#d0d5db", name=name, opacity=0.08, smooth_shading=True)

        # Camera
        p.camera_position = [(0, -self._ph*0.55, self._pw*0.85), (0, 0, 0), (0, 0, 1)]
        p.camera.SetParallelProjection(False)
        p.camera.SetViewAngle(40)

        try:
            p.remove_all_lights()
            p.add_light(pv.Light(position=(self._pw, self._ph, self._pw*0.6), light_type="scene_light", intensity=0.75))
            p.add_light(pv.Light(position=(-self._pw, -self._ph, self._pw*0.4), light_type="scene_light", intensity=0.40))
        except:
            pass

        # Labels
        p.add_text("", position="upper_left", font_size=10, color="#333333", name="label_gt")
        p.add_text("", position="upper_right", font_size=10, color="#333333", name="label_mode")

    def load_section(self, dataset: SpatialDataset, results_dataset: Optional[SpatialDataset] = None):
        self._dataset = dataset
        # Auto-try loading results if not provided
        if results_dataset is None:
            results_root = Path(__file__).resolve().parent.parent / "results" / "DLPFC"
            results_dataset = load_spatial_dataset(str(results_root), dataset.section_id, gt_column="layer_guess_reordered")
        self._results_dataset = results_dataset
        self._hovered_cluster = None
        self._clear_boundaries()
        self._build_point_cloud()
        self._update_labels()
        self._plotter.render()

    def _build_point_cloud(self):
        p = self._plotter
        ds = self._dataset
        if ds is None:
            return

        # Remove old point actors (including highlight)
        for name in list(p.actors.keys()):
            if name.startswith("cell_points"):
                p.remove_actor(name)

        gap = self._gap
        z_gt = -gap / 2 - 0.01   # back side: groundtruth
        z_res = gap / 2 + 0.01   # front side: results

        # ---- Back layer: Ground Truth ----
        n_gt = len(ds.cells)
        pts_gt = np.zeros((n_gt, 3), dtype=np.float32)
        colors_gt = np.zeros((n_gt, 3), dtype=np.float32)
        for i, cell in enumerate(ds.cells):
            pts_gt[i] = [cell.x, cell.y, z_gt]
            colors_gt[i] = get_cluster_color(cell.cluster)

        pdata_gt = pv.PolyData(pts_gt)
        pdata_gt["colors"] = colors_gt
        p.add_mesh(
            pdata_gt, scalars="colors", rgb=True,
            point_size=10, render_points_as_spheres=True,
            opacity=0.75, lighting=False, name="cell_points_gt",
        )

        # ---- Front layer: Results (or GT fallback) ----
        res_ds = self._results_dataset if self._results_dataset is not None else ds
        n_res = len(res_ds.cells)
        pts_res = np.zeros((n_res, 3), dtype=np.float32)
        colors_res = np.zeros((n_res, 3), dtype=np.float32)

        if self._results_dataset is not None and self._results_dataset is not ds:
            # Compare results vs GT: mark mismatches
            gt_pos_set = {(c.x, c.y) for c in ds.cells}
            gt_label_map = {(c.x, c.y): c.cluster for c in ds.cells}
            for i, cell in enumerate(res_ds.cells):
                pts_res[i] = [cell.x, cell.y, z_res]
                pos_key = (cell.x, cell.y)
                if pos_key not in gt_pos_set:
                    colors_res[i] = (1.0, 0.1, 0.1)      # bright red: extra point
                elif gt_label_map.get(pos_key) != cell.cluster:
                    colors_res[i] = (1.0, 0.35, 0.1)     # orange-red: label mismatch
                else:
                    colors_res[i] = get_cluster_color(cell.cluster)
        else:
            # No results: GT on both sides
            for i, cell in enumerate(res_ds.cells):
                pts_res[i] = [cell.x, cell.y, z_res]
                colors_res[i] = get_cluster_color(cell.cluster)

        pdata_res = pv.PolyData(pts_res)
        pdata_res["colors"] = colors_res
        p.add_mesh(
            pdata_res, scalars="colors", rgb=True,
            point_size=10, render_points_as_spheres=True,
            opacity=0.75, lighting=False, name="cell_points_res",
        )

    def _update_labels(self):
        p = self._plotter
        ds = self._dataset
        if ds is None:
            return
        sid = ds.section_id
        mode_str = "Analysis" if self._mode == "analysis" else "Explore"
        try:
            p.actors["label_gt"].SetInput(f"Ground Truth  [{sid}]")
            if self._results_dataset is not None and self._results_dataset is not ds:
                p.actors["label_mode"].SetInput(f"Results  [{sid}]  |  {mode_str}")
            else:
                p.actors["label_mode"].SetInput(f"GT (both sides)  [{sid}]  |  {mode_str}")
        except:
            pass

    def set_mode(self, mode: str):
        self._mode = mode
        p = self._plotter

        if mode == "analysis":
            p.camera.SetParallelProjection(True)
            p.camera.SetParallelScale(1.8)
            self._view_front()
            self._setup_hover()
        else:
            p.camera.SetParallelProjection(False)
            p.camera.SetViewAngle(40)
            self._teardown_hover()
            self._clear_highlight()
            self._clear_boundaries()

        self._update_labels()
        p.render()

    def _setup_hover(self):
        """Setup VTK mouse move observer for hover interaction (debounced)."""
        try:
            import vtk
            iren = self._plotter.iren.interactor
            self._hover_observer_id = iren.AddObserver("MouseMoveEvent", self._on_mouse_move)
            self._picker = vtk.vtkPointPicker()
            self._picker.SetTolerance(0.005)
            self._hover_timer = QTimer(self)
            self._hover_timer.setSingleShot(True)
            self._hover_timer.setInterval(140)
            self._hover_timer.timeout.connect(self._process_hover)
            self._pending_hover_xy = None
        except Exception as exc:
            logger.warning("Failed to setup hover: %s", exc)

    def _teardown_hover(self):
        try:
            if hasattr(self, "_hover_observer_id") and self._hover_observer_id is not None:
                self._plotter.iren.interactor.RemoveObserver(self._hover_observer_id)
                self._hover_observer_id = None
        except:
            pass
        try:
            if hasattr(self, "_hover_timer") and self._hover_timer is not None:
                self._hover_timer.stop()
                self._hover_timer = None
        except:
            pass

    def _on_mouse_move(self, obj, event):
        """Queue hover processing - only fires when mouse is still for 140ms."""
        if self._dataset is None or self._mode != "analysis":
            return
        try:
            iren = obj
            if not hasattr(iren, "GetEventPosition"):
                return
            x, y = iren.GetEventPosition()
            self._pending_hover_xy = (x, y)
            # Restart debounce timer
            if self._hover_timer is not None:
                self._hover_timer.start()
        except:
            pass

    def _process_hover(self):
        """Actually perform the hover pick after debounce delay."""
        if self._pending_hover_xy is None or self._dataset is None:
            return
        try:
            x, y = self._pending_hover_xy
            self._pending_hover_xy = None
            self._picker.Pick(x, y, 0, self._plotter.renderer)
            pid = self._picker.GetPointId()
            if pid < 0:
                return

            # Determine which dataset was picked by checking the actual dataset
            target_ds = self._dataset  # default: GT
            try:
                picked_ds = self._picker.GetDataSet()
                if picked_ds is not None:
                    p = self._plotter
                    for name in ("cell_points_res", "cell_points_res_hl"):
                        actor = p.actors.get(name)
                        if actor is not None:
                            try:
                                if actor.GetMapper().GetInput() is picked_ds:
                                    target_ds = self._results_dataset if self._results_dataset is not None else self._dataset
                                    break
                            except:
                                continue
            except:
                pass

            if 0 <= pid < len(target_ds.cells):
                cluster = target_ds.cells[pid].cluster
                if cluster != self._hovered_cluster:
                    self._hovered_cluster = cluster
                    self._highlight_cluster(cluster)
        except:
            pass

    def _highlight_cluster(self, cluster: str):
        """Dim non-matching cells (small+transparent), enlarge matching cells (big+opaque)."""
        if self._dataset is None:
            return
        ds = self._dataset
        p = self._plotter

        indices = set(ds.clusters.get(cluster, []))
        n = len(ds.cells)
        dim_color = (0.82, 0.82, 0.82)

        # ---- GT Layer: dim all, then overlay highlight ----
        gt_colors = np.zeros((n, 3), dtype=np.float32)
        for i, cell in enumerate(ds.cells):
            gt_colors[i] = dim_color
        try:
            actor = p.actors["cell_points_gt"]
            actor.GetProperty().SetPointSize(5)
            actor.GetProperty().SetOpacity(0.30)
            pdata = actor.GetMapper().GetInput()
            pdata["colors"] = gt_colors
            actor.GetMapper().Modified()
        except:
            pass

        # Create highlight points for GT layer
        if indices:
            gt_highlight_pts = np.array([[ds.cells[i].x, ds.cells[i].y, self._gap/2 + 0.015] for i in indices])
            gt_highlight_colors = np.array([get_cluster_color(ds.cells[i].cluster) for i in indices])
            gt_hl_pdata = pv.PolyData(gt_highlight_pts)
            gt_hl_pdata["colors"] = gt_highlight_colors
            for name in list(p.actors.keys()):
                if name.startswith("cell_points_gt_hl"):
                    p.remove_actor(name)
            p.add_mesh(
                gt_hl_pdata, scalars="colors", rgb=True,
                point_size=28, render_points_as_spheres=True,
                opacity=1.0, lighting=False, name="cell_points_gt_hl",
            )

        # ---- Results Layer ----
        res_ds = self._results_dataset
        if res_ds is not None and res_ds is not ds:
            r_indices = set(res_ds.clusters.get(cluster, []))
            rn = len(res_ds.cells)
            res_colors = np.zeros((rn, 3), dtype=np.float32)
            for i, cell in enumerate(res_ds.cells):
                res_colors[i] = dim_color
            try:
                actor = p.actors["cell_points_res"]
                actor.GetProperty().SetPointSize(5)
                actor.GetProperty().SetOpacity(0.30)
                pdata = actor.GetMapper().GetInput()
                pdata["colors"] = res_colors
                actor.GetMapper().Modified()
            except:
                pass
            if r_indices:
                z_res = self._gap / 2 + 0.015
                res_hl_pts = np.array([[res_ds.cells[i].x, res_ds.cells[i].y, z_res] for i in r_indices])
                res_hl_colors = np.array([get_cluster_color(res_ds.cells[i].cluster) for i in r_indices])
                res_hl_pdata = pv.PolyData(res_hl_pts)
                res_hl_pdata["colors"] = res_hl_colors
                for name in list(p.actors.keys()):
                    if name.startswith("cell_points_res_hl"):
                        p.remove_actor(name)
                p.add_mesh(
                    res_hl_pdata, scalars="colors", rgb=True,
                    point_size=28, render_points_as_spheres=True,
                    opacity=1.0, lighting=False, name="cell_points_res_hl",
                )
        else:
            # Both sides same: dim Res layer too
            try:
                actor = p.actors["cell_points_res"]
                actor.GetProperty().SetPointSize(5)
                actor.GetProperty().SetOpacity(0.30)
                pdata = actor.GetMapper().GetInput()
                pdata["colors"] = gt_colors
                actor.GetMapper().Modified()
            except:
                pass
            # Reuse GT highlight for Res side
            if indices:
                z_res = self._gap / 2 + 0.015
                res_hl_pts = np.array([[ds.cells[i].x, ds.cells[i].y, z_res] for i in indices])
                res_hl_colors = np.array([get_cluster_color(ds.cells[i].cluster) for i in indices])
                res_hl_pdata = pv.PolyData(res_hl_pts)
                res_hl_pdata["colors"] = res_hl_colors
                for name in list(p.actors.keys()):
                    if name.startswith("cell_points_res_hl"):
                        p.remove_actor(name)
                p.add_mesh(
                    res_hl_pdata, scalars="colors", rgb=True,
                    point_size=28, render_points_as_spheres=True,
                    opacity=1.0, lighting=False, name="cell_points_res_hl",
                )

        self._clear_boundaries()
        if indices:
            cluster_pts = np.array([[ds.cells[i].x, ds.cells[i].y] for i in indices])
            self._add_boundaries(cluster_pts, cluster)
        self._update_cluster_info(cluster)
        p.render()

    def _clear_highlight(self):
        """Restore all cells to original colors, size, and opacity."""
        if self._dataset is None:
            return
        self._hovered_cluster = None
        ds = self._dataset
        n = len(ds.cells)
        colors = np.zeros((n, 3), dtype=np.float32)
        for i, cell in enumerate(ds.cells):
            colors[i] = get_cluster_color(cell.cluster)

        # Restore GT layer
        try:
            actor = self._plotter.actors["cell_points_gt"]
            actor.GetProperty().SetPointSize(10)
            actor.GetProperty().SetOpacity(0.75)
            pdata = actor.GetMapper().GetInput()
            pdata["colors"] = colors
            actor.GetMapper().Modified()
        except:
            pass

        # Restore results layer
        res_ds = self._results_dataset
        if res_ds is not None and res_ds is not ds:
            rn = len(res_ds.cells)
            r_colors = np.zeros((rn, 3), dtype=np.float32)
            for i, cell in enumerate(res_ds.cells):
                r_colors[i] = get_cluster_color(cell.cluster)
            try:
                actor = self._plotter.actors["cell_points_res"]
                actor.GetProperty().SetPointSize(10)
                actor.GetProperty().SetOpacity(0.75)
                pdata = actor.GetMapper().GetInput()
                pdata["colors"] = r_colors
                actor.GetMapper().Modified()
            except:
                pass
        else:
            try:
                actor = self._plotter.actors["cell_points_res"]
                actor.GetProperty().SetPointSize(10)
                actor.GetProperty().SetOpacity(0.75)
                pdata = actor.GetMapper().GetInput()
                pdata["colors"] = colors
                actor.GetMapper().Modified()
            except:
                pass

        # Remove highlight actors
        for name in list(self._plotter.actors.keys()):
            if name.startswith("cell_points_gt_hl") or name.startswith("cell_points_res_hl"):
                self._plotter.remove_actor(name)

        self._clear_boundaries()
        self._plotter.render()

    def _add_boundaries(self, pts: np.ndarray, cluster: str):
        """Add alpha shape boundary for the highlighted cluster."""
        if len(pts) < 3:
            return
        p = self._plotter
        z_b = self._gap / 2 + 0.02  # slightly above points
        color = get_cluster_color(cluster)

        try:
            polygons = compute_alpha_shape(pts, alpha=0.3)
            for poly in polygons:
                # Close the polygon
                if len(poly) < 3:
                    continue
                poly_3d = np.column_stack([poly, np.full(len(poly), z_b)])
                # Create line for outline
                lines = np.arange(len(poly_3d) + 1) % len(poly_3d)
                line_mesh = pv.PolyData(poly_3d, lines=np.column_stack([lines[:-1], lines[1:]]))
                self._boundary_actors.append(
                    p.add_mesh(line_mesh, color=color, line_width=3, name=f"boundary_{cluster}", opacity=0.9)
                )
        except Exception:
            pass

    def _clear_boundaries(self):
        p = self._plotter
        for name in list(p.actors.keys()):
            if name.startswith("boundary_"):
                p.remove_actor(name)
        self._boundary_actors.clear()

    def _update_cluster_info(self, cluster: str):
        ds = self._dataset
        if ds is None:
            return
        indices = ds.clusters.get(cluster, [])
        count = len(indices)
        if indices:
            meta = ds.cells[indices[0]].metadata
            meta_dict = {k: str(v)[:60] for k, v in list(meta.items())[:5]}
        else:
            meta_dict = {}
        self.cluster_hovered.emit(cluster, count, meta_dict)

    def _view_front(self):
        self._plotter.camera_position = [(0, -self._ph*0.55, self._pw*0.85), (0, 0, 0), (0, 0, 1)]
        self._plotter.render()

    def _view_back(self):
        self._plotter.camera_position = [(0, self._ph*0.55, -self._pw*0.85), (0, 0, 0), (0, 0, 1)]
        self._plotter.render()

    def view_front(self):
        self._view_front()

    def view_back(self):
        self._view_back()


# ============================================================
# MAIN WINDOW
# ============================================================
SECTION_IDS = [
    "151507", "151508", "151509", "151510",
    "151669", "151670", "151671", "151672",
    "151673", "151674", "151675", "151676",
]


def main():
    import sys
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    w = QWidget()
    w.setWindowTitle("Spatial Transcriptomics Viewer")
    w.resize(1200, 800)
    layout = QHBoxLayout(w)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(8)

    viewer = SpatialViewerWidget()
    layout.addWidget(viewer, 1)

    panel = QFrame()
    panel.setFixedWidth(220)
    panel.setStyleSheet("""
        QFrame {
            background: rgba(30,30,35,0.92);
            border: 1px solid rgba(255,255,255,0.10);
            border-radius: 10px;
        }
    """)
    playout = QVBoxLayout(panel)
    playout.setContentsMargins(12, 10, 12, 10)
    playout.setSpacing(4)

    t = QLabel("Spatial Viewer")
    t.setStyleSheet("font-size:13px;font-weight:700;color:#e8e8ec;")
    playout.addWidget(t)

    combo = QComboBox()
    combo.addItems(SECTION_IDS)
    playout.addWidget(combo)

    def on_section(sid):
        data_root = Path(__file__).resolve().parent.parent / "dataset" / "DLPFC"
        ds = load_spatial_dataset(str(data_root), sid)
        if ds:
            viewer.load_section(ds)

    combo.currentTextChanged.connect(on_section)

    fv = QPushButton("Front View")
    fv.clicked.connect(viewer.view_front)
    playout.addWidget(fv)

    bv = QPushButton("Back View")
    bv.clicked.connect(viewer.view_back)
    playout.addWidget(bv)

    playout.addStretch()
    layout.addWidget(panel, 0)

    # Load first section
    on_section(SECTION_IDS[0])

    w.show()
    sys.exit(app.exec())


