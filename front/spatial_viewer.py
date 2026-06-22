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
            import cv2, numpy as np
            raw = np.fromfile(str(img_path), dtype=np.uint8)
            im = cv2.imdecode(raw, cv2.IMREAD_COLOR)
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


def load_results_dataset(results_root: str, section_id: str) -> Optional[SpatialDataset]:
    sec_dir = Path(results_root) / section_id
    pos_path = sec_dir / "spatial" / "tissue_positions_list.csv"
    scale_path = sec_dir / "spatial" / "scalefactors_json.json"

    if not pos_path.exists():
        return None

    scale = 0.15
    if scale_path.exists():
        with open(scale_path) as f:
            scale = float(json.load(f).get("tissue_hires_scalef", 0.15))

    hires_dim = 2000.0
    img_path = sec_dir / "spatial" / "tissue_hires_image.png"
    if img_path.exists():
        try:
            import cv2
            import numpy as np
            raw = np.fromfile(str(img_path), dtype=np.uint8)
            im = cv2.imdecode(raw, cv2.IMREAD_COLOR)
            if im is not None:
                hires_dim = float(max(im.shape[0], im.shape[1]))
        except:
            pass

    positions = {}
    with open(pos_path) as f:
        reader = csv.DictReader(f)
        for row in reader:
            in_tissue = row.get("in_tissue", "0").strip()
            if in_tissue != "1":
                continue
            barcode = row.get("barcode", "").strip()
            domain = row.get("domain", "").strip()
            if not barcode or not domain:
                continue
            px_row = float(row.get("pxl_row", 0))
            px_col = float(row.get("pxl_col", 0))
            positions[barcode] = (px_row, px_col, domain)

    if not positions:
        return None

    cells = []
    clusters = defaultdict(list)
    for barcode, (px_row, px_col, domain) in positions.items():
        hx = px_col * scale
        hy = px_row * scale
        x = (hx / hires_dim) * 4.0 - 2.0
        y = 1.5 - (hy / hires_dim) * 3.0
        cells.append(CellData(cell_id=barcode, x=x, y=y, cluster=domain, metadata={}))
        clusters[domain].append(len(cells) - 1)

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
    "ERR_POSITION": "#FF1A1A", "ERR_LABEL": "#FF5A1A",
    "TOLERATED": "#FFD700",
    "Unlabeled": "#000000",
}
_FALLBACK = ["#008B8B","#008080","#0E6655","#1E90FF","#7B68EE","#6A5ACD",
             "#483D8B","#4B0082","#8E44AD","#1ABC9C","#117A65","#191970"]

def _normalize_label(label: str):
    """Normalize label strings to comparable numeric IDs.
    'Layer1' -> 1, '1' -> 1, 'WM' -> 0, '' -> None.
    """
    if not label or label.upper() == "NA":
        return None
    s = str(label).strip()
    if s.startswith("Layer"):
        try:
            return int(s[5:])
        except ValueError:
            pass
    if s == "WM":
        return 0
    try:
        return int(s)
    except ValueError:
        return None


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



def _point_to_segment_distance(px, py, x1, y1, x2, y2):
    """Minimum distance from point (px,py) to line segment (x1,y1)-(x2,y2)."""
    dx, dy = x2 - x1, y2 - y1
    if dx == 0 and dy == 0:
        return np.sqrt((px - x1) ** 2 + (py - y1) ** 2)
    t = max(0.0, min(1.0, ((px - x1) * dx + (py - y1) * dy) / (dx * dx + dy * dy)))
    cx, cy = x1 + t * dx, y1 + t * dy
    return np.sqrt((px - cx) ** 2 + (py - cy) ** 2)


def _point_to_polygon_distance(px, py, poly):
    """Minimum distance from point to polygon boundary edges."""
    min_dist = float("inf")
    n = len(poly)
    for i in range(n):
        x1, y1 = poly[i]
        x2, y2 = poly[(i + 1) % n]
        d = _point_to_segment_distance(px, py, x1, y1, x2, y2)
        if d < min_dist:
            min_dist = d
    return min_dist


# Adjacent layer pairs for boundary tolerance
_LAYER_ADJACENCIES = [(1, 2), (2, 3), (3, 4), (4, 5), (5, 6), (6, 0)]  # 0 = WM

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
        self._view_side: str = "front"  # front or back
        self._tolerance_radius: float = 0.15
        self._strict_mode: bool = False
        self._layer_buffer_zones: dict = {}
        self._tolerated_indices: set = set()
        self._camera_lock_observer = None

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
            self._teardown_camera_lock()
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
        self._results_dataset = results_dataset
        self._hovered_cluster = None
        self._clear_boundaries()
        self._build_layer_buffer_zones()
        self._build_point_cloud()
        self._update_labels()
        self._plotter.render()

    def _build_layer_buffer_zones(self):
        """Compute buffer zones between adjacent GT layers for tolerance check."""
        ds = self._dataset
        if ds is None:
            self._layer_buffer_zones = {}
            return

        # Group GT points by normalized layer id
        layer_pts = {}
        for cell in ds.cells:
            nid = _normalize_label(cell.cluster)
            if nid is not None:
                layer_pts.setdefault(nid, []).append((cell.x, cell.y))

        tolerance = self._tolerance_radius
        buffer_zones = {}

        for la, lb in _LAYER_ADJACENCIES:
            pts_a = np.array(layer_pts.get(la, []), dtype=np.float64)
            pts_b = np.array(layer_pts.get(lb, []), dtype=np.float64)
            if len(pts_a) < 3 or len(pts_b) < 3:
                continue

            # Alpha shape boundaries for both layers
            bounds_a = compute_alpha_shape(pts_a)
            bounds_b = compute_alpha_shape(pts_b)

            # Build buffer: points in layer_b near layer_a boundary AND vice versa
            zone = set()
            for px, py in pts_b:
                for boundary in bounds_a:
                    if _point_to_polygon_distance(px, py, boundary) < tolerance:
                        zone.add((round(px, 4), round(py, 4)))
                        break
            for px, py in pts_a:
                for boundary in bounds_b:
                    if _point_to_polygon_distance(px, py, boundary) < tolerance:
                        zone.add((round(px, 4), round(py, 4)))
                        break

            if zone:
                buffer_zones[(la, lb)] = zone

        self._layer_buffer_zones = buffer_zones

    def set_tolerance(self, radius: float):
        """Update tolerance radius and recompute boundaries + colors."""
        self._tolerance_radius = max(0.02, min(0.50, radius))
        self._build_layer_buffer_zones()
        self._build_point_cloud()
        self._update_labels()
        self._plotter.render()

    def set_strict_mode(self, strict: bool):
        """Toggle strict (no boundary tolerance) vs relaxed mode."""
        self._strict_mode = strict
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
            opacity=1.0, lighting=False, name="cell_points_gt",
        )

        # ---- Front layer: Results (or GT fallback) ----
        if self._results_dataset is None:
            # No results: render nothing on front face
            return
        res_ds = self._results_dataset
        n_res = len(res_ds.cells)

        # Build full results point cloud
        pts_res = np.zeros((n_res, 3), dtype=np.float32)
        colors_res = np.zeros((n_res, 3), dtype=np.float32)
        # Override cluster labels for error points
        res_clusters = {}  # cluster_name -> list of indices (for hover linkage)
        error_extra_indices = set()
        error_label_indices = set()
        self._tolerated_indices = set()

        # Build two color arrays: normal + error-highlighted
        colors_normal = np.zeros((n_res, 3), dtype=np.float32)
        colors_error = np.zeros((n_res, 3), dtype=np.float32)

        if self._results_dataset is not None and self._results_dataset is not ds:
            # Match by barcode instead of float position to avoid precision errors
            gt_barcode_set = {c.cell_id for c in ds.cells}
            gt_label_map = {c.cell_id: _normalize_label(c.cluster) for c in ds.cells}

            for i, cell in enumerate(res_ds.cells):
                pts_res[i] = [cell.x, cell.y, z_res]
                barcode = cell.cell_id
                gt_id = gt_label_map.get(barcode)
                pred_id = _normalize_label(cell.cluster)

                # Normal color: domain mapped to GT layer color
                if pred_id is not None and 1 <= pred_id <= 6:
                    colors_normal[i] = get_cluster_color("Layer" + str(pred_id))
                elif pred_id == 0:
                    colors_normal[i] = get_cluster_color("WM")
                elif pred_id is not None:
                    colors_normal[i] = get_cluster_color(cell.cluster)
                else:
                    colors_normal[i] = (0.0, 0.0, 0.0)

                # Error color: comparison view
                # Check by barcode: cell present in both datasets?
                in_gt = barcode in gt_barcode_set
                if not in_gt:
                    # Position error: point only exists in results
                    colors_error[i] = (1.0, 0.1, 0.1)
                    error_extra_indices.add(i)
                    res_clusters.setdefault("ERR_POSITION", []).append(i)
                elif gt_id is None and pred_id is None:
                    colors_error[i] = (0.0, 0.0, 0.0)
                    res_clusters.setdefault("Unlabeled", []).append(i)
                elif gt_id is None:
                    colors_error[i] = (0.0, 0.0, 0.0)
                    res_clusters.setdefault("Unlabeled", []).append(i)
                elif pred_id is None:
                    colors_error[i] = (0.0, 0.0, 0.0)
                    res_clusters.setdefault("Unlabeled", []).append(i)
                elif gt_id != pred_id:
                    # Boundary-aware check: is this in the overlap zone?
                    pos_key = (round(cell.x, 4), round(cell.y, 4))
                    tolerated = False
                    if not self._strict_mode:
                        la, lb = min(gt_id, pred_id), max(gt_id, pred_id)
                        zone = self._layer_buffer_zones.get((la, lb), set())
                        if pos_key in zone:
                            tolerated = True
                    if tolerated:
                        colors_error[i] = get_cluster_color("TOLERATED")
                        self._tolerated_indices.add(i)
                        res_clusters.setdefault("TOLERATED", []).append(i)
                    else:
                        colors_error[i] = (1.0, 0.35, 0.1)
                        error_label_indices.add(i)
                        res_clusters.setdefault("ERR_LABEL", []).append(i)
                else:
                    colors_error[i] = get_cluster_color(cell.cluster)
                    res_clusters.setdefault(cell.cluster, []).append(i)
        else:
            for i, cell in enumerate(res_ds.cells):
                pts_res[i] = [cell.x, cell.y, z_res]
                pred_id = _normalize_label(cell.cluster)
                if pred_id is not None and 1 <= pred_id <= 6:
                    c = get_cluster_color("Layer" + str(pred_id))
                elif pred_id == 0:
                    c = get_cluster_color("WM")
                elif pred_id is not None:
                    c = get_cluster_color(cell.cluster)
                else:
                    c = (0.0, 0.0, 0.0)
                    res_clusters.setdefault("Unlabeled", []).append(i)
                colors_normal[i] = c
                colors_error[i] = c

        # Store cluster mapping and both color sets
        self._res_clusters = res_clusters
        self._res_colors_normal = colors_normal.copy()
        self._res_colors_error = colors_error.copy()

        pdata_res = pv.PolyData(pts_res)
        pdata_res["colors"] = colors_normal  # default: normal view
        p.add_mesh(
            pdata_res, scalars="colors", rgb=True,
            point_size=10, render_points_as_spheres=True,
            opacity=0.75, lighting=False, name="cell_points_res",
        )

        # Error overlay markers (opaque, shown only when toggle ON)
        if error_extra_indices:
            ee_pts = np.array([[res_ds.cells[i].x, res_ds.cells[i].y, z_res + 0.025] for i in error_extra_indices], dtype=np.float32)
            ee_colors = np.full((len(error_extra_indices), 3), (1.0, 0.1, 0.1), dtype=np.float32)
            pdata_ee = pv.PolyData(ee_pts)
            pdata_ee["colors"] = ee_colors
            p.add_mesh(
                pdata_ee, scalars="colors", rgb=True,
                point_size=12, render_points_as_spheres=True,
                opacity=0.0, lighting=False, name="cell_points_res_err_extra",
            )

        if error_label_indices:
            el_pts = np.array([[res_ds.cells[i].x, res_ds.cells[i].y, z_res + 0.025] for i in error_label_indices], dtype=np.float32)
            el_colors = np.full((len(error_label_indices), 3), (1.0, 0.35, 0.1), dtype=np.float32)
            pdata_el = pv.PolyData(el_pts)
            pdata_el["colors"] = el_colors
            p.add_mesh(
                pdata_el, scalars="colors", rgb=True,
                point_size=12, render_points_as_spheres=True,
                opacity=0.0, lighting=False, name="cell_points_res_err_label",
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
            # Lock camera: snap back after any user drag
            self._setup_camera_lock()
        else:
            self._teardown_camera_lock()
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

    def _setup_camera_lock(self):
        try:
            import vtk
            self._camera_lock_observer = self._plotter.iren.interactor.AddObserver(
                "EndInteractionEvent", self._on_camera_lock
            )
        except Exception:
            self._camera_lock_observer = None

    def _teardown_camera_lock(self):
        try:
            if hasattr(self, "_camera_lock_observer") and self._camera_lock_observer is not None:
                self._plotter.iren.interactor.RemoveObserver(self._camera_lock_observer)
                self._camera_lock_observer = None
        except:
            pass

    def _on_camera_lock(self, obj, event):
        if self._mode != "analysis":
            return
        if self._view_side == "front":
            self._view_front()
        else:
            self._view_back()

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

            side = self._view_side
            p = self._plotter

            # Determine which layer was picked
            picked_layer = None  # "gt" or "res"
            try:
                picked_ds = self._picker.GetDataSet()
                if picked_ds is not None:
                    for name in ("cell_points_res", "cell_points_res_hl"):
                        actor = p.actors.get(name)
                        if actor is not None:
                            try:
                                if actor.GetMapper().GetInput() is picked_ds:
                                    picked_layer = "res"
                                    break
                            except:
                                continue
                    if picked_layer is None:
                        for name in ("cell_points_gt", "cell_points_gt_hl"):
                            actor = p.actors.get(name)
                            if actor is not None:
                                try:
                                    if actor.GetMapper().GetInput() is picked_ds:
                                        picked_layer = "gt"
                                        break
                                except:
                                    continue
            except:
                pass

            # Enforce view side
            if side == "front" and picked_layer == "gt":
                return  # front view, ignore GT picks
            if side == "back" and picked_layer == "res":
                return  # back view, ignore results picks

            # Select target dataset based on picked layer
            if picked_layer == "res":
                target_ds = self._results_dataset if self._results_dataset is not None else self._dataset
                layer_name = "Results"
            else:
                target_ds = self._dataset
                layer_name = "Ground Truth"

            if 0 <= pid < len(target_ds.cells):
                cluster = target_ds.cells[pid].cluster

                self._hovered_layer = layer_name
                if cluster != self._hovered_cluster:
                    self._hovered_cluster = cluster
                    self._highlight_cluster(cluster, layer_name)
        except:
            pass

    def _highlight_cluster(self, cluster: str, layer_name: str = "Ground Truth"):
        """Highlight cluster on the specified layer only (GT or Results)."""
        if self._dataset is None:
            return
        ds = self._dataset
        p = self._plotter
        dim_color = (0.82, 0.82, 0.82)

        highlight_gt = (layer_name == "Ground Truth")
        highlight_res = (layer_name == "Results")

        # ---- GT Layer ----
        if highlight_gt:
            indices = set(ds.clusters.get(cluster, []))
            n = len(ds.cells)
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
            for name in list(p.actors.keys()):
                if name.startswith("cell_points_gt_hl"):
                    p.remove_actor(name)
            if indices:
                gt_hl_pts = np.array([[ds.cells[i].x, ds.cells[i].y, -self._gap/2 - 0.015] for i in indices], dtype=np.float32)
                gt_hl_colors = np.array([get_cluster_color(ds.cells[i].cluster) for i in indices], dtype=np.float32)
                gt_hl_pdata = pv.PolyData(gt_hl_pts)
                gt_hl_pdata["colors"] = gt_hl_colors
                p.add_mesh(
                    gt_hl_pdata, scalars="colors", rgb=True,
                    point_size=28, render_points_as_spheres=True,
                    opacity=1.0, lighting=False, name="cell_points_gt_hl",
                )
            gt_indices = indices
        else:
            self._restore_gt_base()
            gt_indices = set()

        # ---- Results Layer ----
        if highlight_res:
            res_ds = self._results_dataset if self._results_dataset is not None else ds
            r_indices = set(res_ds.clusters.get(cluster, []))
            rn = len(res_ds.cells)
            res_colors = np.zeros((rn, 3), dtype=np.float32)
            for i in range(rn):
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
            for name in list(p.actors.keys()):
                if name.startswith("cell_points_res_hl"):
                    p.remove_actor(name)
            if r_indices:
                z_res = self._gap / 2 + 0.015
                res_hl_pts = np.array([[res_ds.cells[i].x, res_ds.cells[i].y, z_res] for i in r_indices], dtype=np.float32)
                res_hl_colors = np.array([get_cluster_color(res_ds.cells[i].cluster) for i in r_indices], dtype=np.float32)
                res_hl_pdata = pv.PolyData(res_hl_pts)
                res_hl_pdata["colors"] = res_hl_colors
                p.add_mesh(
                    res_hl_pdata, scalars="colors", rgb=True,
                    point_size=28, render_points_as_spheres=True,
                    opacity=1.0, lighting=False, name="cell_points_res_hl",
                )
            for err_name in ("cell_points_res_err_extra", "cell_points_res_err_label"):
                try:
                    e_actor = p.actors.get(err_name)
                    if e_actor is not None:
                        e_actor.GetProperty().SetPointSize(6)
                        e_actor.GetProperty().SetOpacity(0.25)
                except:
                    pass
        else:
            self._restore_results_base()

        self._clear_boundaries()
        if highlight_gt and gt_indices:
            cluster_pts = np.array([[ds.cells[i].x, ds.cells[i].y] for i in gt_indices])
            self._add_boundaries(cluster_pts, cluster)
        elif highlight_res:
            rd = self._results_dataset if self._results_dataset is not None else ds
            r_idx2 = rd.clusters.get(cluster, [])
            if r_idx2:
                cluster_pts = np.array([[rd.cells[i].x, rd.cells[i].y] for i in r_idx2])
                self._add_boundaries(cluster_pts, cluster)

        self._update_cluster_info(cluster)
        p.render()

    def _restore_gt_base(self):
        """Restore GT base layer to default appearance."""
        ds = self._dataset
        if ds is None:
            return
        n = len(ds.cells)
        colors = np.zeros((n, 3), dtype=np.float32)
        for i, cell in enumerate(ds.cells):
            colors[i] = get_cluster_color(cell.cluster)
        try:
            actor = self._plotter.actors.get("cell_points_gt")
            if actor is not None:
                actor.GetProperty().SetPointSize(10)
                actor.GetProperty().SetOpacity(0.75)
                pdata = actor.GetMapper().GetInput()
                pdata["colors"] = colors
                actor.GetMapper().Modified()
        except:
            pass

    def _restore_results_base(self):
        """Restore results base layer to default (normal) appearance."""
        ds = self._dataset
        if ds is None:
            return
        res_ds = self._results_dataset
        if res_ds is not None and res_ds is not ds:
            saved_colors = getattr(self, "_res_colors_normal", None)
            if saved_colors is not None and len(saved_colors) == len(res_ds.cells):
                r_colors = saved_colors.copy()
            else:
                rn = len(res_ds.cells)
                r_colors = np.zeros((rn, 3), dtype=np.float32)
                for i, cell in enumerate(res_ds.cells):
                    pred_id = _normalize_label(cell.cluster)
                    if pred_id is not None and 1 <= pred_id <= 6:
                        r_colors[i] = get_cluster_color("Layer" + str(pred_id))
                    elif pred_id == 0:
                        r_colors[i] = get_cluster_color("WM")
                    elif pred_id is not None:
                        r_colors[i] = get_cluster_color(cell.cluster)
            try:
                actor = self._plotter.actors.get("cell_points_res")
                if actor is not None:
                    actor.GetProperty().SetPointSize(10)
                    actor.GetProperty().SetOpacity(0.75)
                    pdata = actor.GetMapper().GetInput()
                    pdata["colors"] = r_colors
                    actor.GetMapper().Modified()
            except:
                pass
        else:
            r_colors = getattr(self, "_res_colors_normal", None)
            try:
                actor = self._plotter.actors.get("cell_points_res")
                if actor is not None and r_colors is not None:
                    actor.GetProperty().SetPointSize(10)
                    actor.GetProperty().SetOpacity(0.75)
                    pdata = actor.GetMapper().GetInput()
                    pdata["colors"] = colors
                    actor.GetMapper().Modified()
            except:
                pass

    def _clear_highlight(self):
        """Restore all cells to original state."""
        if self._dataset is None:
            return
        self._hovered_cluster = None
        self._hovered_layer = None
        self._restore_gt_base()
        self._restore_results_base()
        # Remove highlight actors
        for name in list(self._plotter.actors.keys()):
            if name.startswith("cell_points_gt_hl") or name.startswith("cell_points_res_hl"):
                self._plotter.remove_actor(name)
        # Restore error overlay actors
        for err_name in ("cell_points_res_err_extra", "cell_points_res_err_label"):
            try:
                e_actor = self._plotter.actors.get(err_name)
                if e_actor is not None:
                    e_actor.GetProperty().SetPointSize(12)
                    e_actor.GetProperty().SetOpacity(1.0)
            except:
                pass
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
        layer = getattr(self, "_hovered_layer", "Ground Truth")
        if cluster in ("ERR_POSITION", "ERR_LABEL", "TOLERATED", "Unlabeled"):
            r_clusters = getattr(self, "_res_clusters", {})
            indices = r_clusters.get(cluster, [])
            count = len(indices)
            if cluster == "ERR_POSITION":
                err_type = "Position Error"
            elif cluster == "ERR_LABEL":
                err_type = "Label Mismatch"
            elif cluster == "TOLERATED":
                err_type = "Tolerated Mismatch"
            else:
                err_type = "No Label"
            self.cluster_hovered.emit(f"[{layer}] {cluster}", count, {"type": err_type, "layer": layer})
            return
        indices = ds.clusters.get(cluster, [])
        count = len(indices)
        if indices:
            meta = ds.cells[indices[0]].metadata
            meta_dict = {k: str(v)[:60] for k, v in list(meta.items())[:5]}
        else:
            meta_dict = {}
        meta_dict["layer"] = layer
        self.cluster_hovered.emit(f"[{layer}] {cluster}", count, meta_dict)

    def _view_front(self):
        self._view_side = "front"
        self._plotter.camera_position = [(0, -self._ph*0.55, self._pw*0.85), (0, 0, 0), (0, 0, 1)]
        self._plotter.render()

    def _view_back(self):
        self._view_side = "back"
        self._plotter.camera_position = [(0, self._ph*0.55, -self._pw*0.85), (0, 0, 0), (0, 0, 1)]
        self._plotter.render()

    def view_front(self):
        self._view_front()

    def view_back(self):
        self._view_back()

    def toggle_error_visibility(self, show: bool):
        """Toggle between normal view and error-highlighted view."""
        p = self._plotter
        # Swap the main results layer colors
        try:
            actor = p.actors.get("cell_points_res")
            if actor is not None:
                pdata = actor.GetMapper().GetInput()
                if show:
                    colors = getattr(self, "_res_colors_error", None)
                else:
                    colors = getattr(self, "_res_colors_normal", None)
                if colors is not None and len(colors) > 0:
                    pdata["colors"] = colors
                    actor.GetMapper().Modified()
        except:
            pass
        # Toggle error overlay visibility
        for err_name in ("cell_points_res_err_extra", "cell_points_res_err_label"):
            try:
                actor = p.actors.get(err_name)
                if actor is not None:
                    actor.GetProperty().SetOpacity(1.0 if show else 0.0)
            except:
                pass
        p.render()


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


