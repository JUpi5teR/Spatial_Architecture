"""Overlay cell data: GT vs Prediction error analysis.

Reads structured data from `metadata.tsv` and `tissue_positions_list.csv`
in each section folder, plus the hires scale factor for pixel -> image mapping.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd

from utils.logger import logger


# ====================================================================
#  Error types and visual encoding
# ====================================================================

class ErrorType(str, Enum):
    CORRECT = "Correct"
    MISCLASSIFIED = "Misclassified"   # GT != Pred, both present
    NEW = "New"                       # Pred has, GT doesn't
    MISSING = "Missing"               # GT has, Pred doesn't


ERROR_COLORS: dict[ErrorType, str] = {
    ErrorType.CORRECT: "#69b1ff",        # light blue (match)
    ErrorType.MISCLASSIFIED: "#ff4d4f",  # high-saturation red
    ErrorType.NEW: "#faad14",            # high-saturation yellow
    ErrorType.MISSING: "#ff7a45",        # high-saturation orange
}

ERROR_SHAPES: dict[ErrorType, str] = {
    ErrorType.CORRECT: "o",
    ErrorType.MISCLASSIFIED: "D",
    ErrorType.NEW: "^",
    ErrorType.MISSING: "v",
}

ERROR_ALPHA: dict[ErrorType, float] = {
    ErrorType.CORRECT: 0.40,
    ErrorType.MISCLASSIFIED: 1.00,
    ErrorType.NEW: 1.00,
    ErrorType.MISSING: 1.00,
}

ERROR_SIZE: dict[ErrorType, int] = {
    ErrorType.CORRECT: 6,
    ErrorType.MISCLASSIFIED: 16,
    ErrorType.NEW: 14,
    ErrorType.MISSING: 14,
}


# ====================================================================
#  Data classes
# ====================================================================

@dataclass
class OverlayCellData:
    cell_id: str
    x: float                  # panel-space x (after mapping hires -> panel)
    y: float                  # panel-space y
    ground_truth: str
    prediction: str
    error_type: ErrorType
    gt_id: Optional[int] = None
    pred_id: Optional[int] = None


@dataclass
class ClusterStat:
    """Per-cluster statistics for summary tables."""
    gt_name: str
    gt_id: Optional[int]
    pred_name: str
    pred_id: Optional[int]
    n_true: int
    n_pred: int
    n_match: int
    n_new: int           # in Pred but not in GT
    n_misclass: int
    n_missing: int       # in GT but not in Pred
    agreement: float     # 0..1


@dataclass
class OverlayDataset:
    section_id: str
    cells: list[OverlayCellData] = field(default_factory=list)

    # Image dimensions
    hires_dim: float = 2000.0   # tissue_hires_image.png side length
    panel_w: float = 4.0
    panel_h: float = 3.0

    # Status
    has_pred: bool = False
    image_path: Optional[Path] = None  # hires image (for background reference)

    # Aggregates
    cell_count: int = 0
    error_count: int = 0
    error_rate: float = 0.0
    gt_clusters: list[str] = field(default_factory=list)
    pred_clusters: list[str] = field(default_factory=list)
    cluster_stats: list[ClusterStat] = field(default_factory=list)
    confusion: dict[tuple[str, str], int] = field(default_factory=dict)

    def cells_by_type(self, etype: ErrorType) -> list[OverlayCellData]:
        return [c for c in self.cells if c.error_type == etype]


# ====================================================================
#  Loaders
# ====================================================================

_HIRES_DEFAULT = 2000.0


def _read_scale(spatial_dir: Path) -> float:
    scale_path = spatial_dir / "scalefactors_json.json"
    if not scale_path.exists():
        return 0.15
    try:
        with open(scale_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return float(data.get("tissue_hires_scalef", 0.15))
    except Exception as exc:
        logger.warning("Failed to read scale: %s", exc)
        return 0.15


def _hires_dim(spatial_dir: Path) -> float:
    """Infer the hires image side length from PNG shape if possible."""
    img_path = spatial_dir / "tissue_hires_image.png"
    if img_path.exists():
        try:
            import cv2
            im = cv2.imread(str(img_path), cv2.IMREAD_COLOR)
            if im is not None:
                # Use the max side as the reference square dimension
                return float(max(im.shape[0], im.shape[1]))
        except Exception:
            pass
    return _HIRES_DEFAULT


def load_overlay_dataset(
    data_root: Path,
    section_id: str,
    gt_column: str = "layer_guess",
    pred_column: str = "GraphBased",
    panel_w: float = 4.0,
    panel_h: float = 3.0,
) -> Optional[OverlayDataset]:
    """Load overlay data for a single section.

    Reads:
        {data_root}/{section_id}/metadata.tsv
        {data_root}/{section_id}/spatial/tissue_positions_list.csv
        {data_root}/{section_id}/spatial/scalefactors_json.json
    """
    section_root = data_root / section_id
    meta_path = section_root / "metadata.tsv"
    spatial_dir = section_root / "spatial"
    pos_path = spatial_dir / "tissue_positions_list.csv"

    if not meta_path.exists() or not pos_path.exists():
        logger.warning("Missing files for section %s", section_id)
        return None

    try:
        meta = pd.read_csv(meta_path, sep="\t")
    except Exception as exc:
        logger.error("Failed to read %s: %s", meta_path, exc)
        return None

    try:
        pos = pd.read_csv(
            pos_path,
            header=None,
            names=["barcode", "in_tissue", "array_row", "array_col", "pxl_col", "pxl_row"],
        )
        pos = pos[pos["in_tissue"] == 1]
    except Exception as exc:
        logger.error("Failed to read %s: %s", pos_path, exc)
        return None

    if gt_column not in meta.columns:
        logger.warning("GT column %s not in metadata for %s", gt_column, section_id)
        return None

    has_pred = pred_column in meta.columns
    hires_scalef = _read_scale(spatial_dir)
    hires_dim = _hires_dim(spatial_dir)

    df = meta.merge(pos[["barcode", "pxl_col", "pxl_row"]], on="barcode", how="inner")
    df = df.dropna(subset=[gt_column])

    # To panel coordinates (panel is panel_w x panel_h, centered at origin)
    df["panel_x"] = (df["pxl_col"] * hires_scalef / hires_dim - 0.5) * panel_w
    df["panel_y"] = (df["pxl_row"] * hires_scalef / hires_dim - 0.5) * panel_h

    cells: list[OverlayCellData] = []
    gt_set: set[str] = set()
    pred_set: set[str] = set()

    for _, row in df.iterrows():
        gt_val = row[gt_column]
        gt_str = str(gt_val).strip()
        gt_set.add(gt_str)

        # Normalize GT to a numeric id for fair comparison
        gt_id_norm = _normalize_to_id(gt_val)

        if has_pred and pd.notna(row[pred_column]):
            try:
                pred_id = int(row[pred_column])
            except (ValueError, TypeError):
                pred_id = -1
            pred_str = f"Cluster{pred_id}"
        else:
            pred_id = gt_id_norm
            pred_str = gt_str  # fallback: treat as match

        pred_set.add(pred_str)

        # Compare on normalized id; both missing -> correct
        if (gt_id_norm is not None and pred_id is not None
                and gt_id_norm == pred_id):
            etype = ErrorType.CORRECT
        else:
            etype = ErrorType.MISCLASSIFIED

        # Extract a display id for the GT (Layer1->1, WM->0, etc.)
        gt_id_val: Optional[int] = gt_id_norm

        cells.append(
            OverlayCellData(
                cell_id=row["barcode"],
                x=float(row["panel_x"]),
                y=float(row["panel_y"]),
                ground_truth=gt_str,
                prediction=pred_str,
                error_type=etype,
                gt_id=gt_id_val,
                pred_id=pred_id,
            )
        )

    error_count = sum(1 for c in cells if c.error_type != ErrorType.CORRECT)
    cell_count = len(cells)
    error_rate = (error_count / cell_count) if cell_count else 0.0

    # Cluster stats (per GT cluster)
    gt_names_sorted = _sort_cluster_names(gt_set)
    pred_names_sorted = _sort_cluster_names(pred_set)
    cluster_stats = _build_cluster_stats(cells, gt_names_sorted, pred_names_sorted)
    confusion = _build_confusion(cells)

    return OverlayDataset(
        section_id=section_id,
        cells=cells,
        hires_dim=hires_dim,
        panel_w=panel_w,
        panel_h=panel_h,
        has_pred=has_pred,
        image_path=spatial_dir / "tissue_hires_image.png",
        cell_count=cell_count,
        error_count=error_count,
        error_rate=error_rate,
        gt_clusters=gt_names_sorted,
        pred_clusters=pred_names_sorted,
        cluster_stats=cluster_stats,
        confusion=confusion,
    )


def load_all_overlay_datasets(
    data_root: Path,
    section_ids: list[str],
    gt_column: str = "layer_guess",
    pred_column: str = "GraphBased",
    panel_w: float = 4.0,
    panel_h: float = 3.0,
) -> list[OverlayDataset]:
    datasets: list[OverlayDataset] = []
    for sid in section_ids:
        ds = load_overlay_dataset(
            data_root, sid, gt_column, pred_column, panel_w, panel_h
        )
        if ds is not None:
            datasets.append(ds)
        else:
            logger.warning("Section %s skipped (no overlay data)", sid)
    return datasets


# ====================================================================
#  Helpers
# ====================================================================

def _normalize_to_id(val) -> Optional[int]:
    """Normalize a GT/Pred cell label to a comparable integer id.

    DLPFC GT uses:
      - "Layer1".."Layer6" -> 1..6
      - "WM" -> 0

    Pred columns are usually integers (e.g. GraphBased -> 1..6).
    """
    if val is None or (isinstance(val, float) and np.isnan(val)):
        return None
    if isinstance(val, (int, np.integer)):
        return int(val)
    s = str(val).strip()
    if not s:
        return None
    if s == "WM":
        return 0
    if s.startswith("Layer"):
        try:
            return int(s[5:])
        except ValueError:
            return None
    if s.startswith("Cluster"):
        try:
            return int(s[7:])
        except ValueError:
            return None
    # plain integer string
    try:
        return int(s)
    except ValueError:
        return None


def _sort_cluster_names(names: set[str]) -> list[str]:
    """Sort cluster names: Layer1, Layer2, ..., WM, ClusterN, others."""
    def key(name: str):
        if name.startswith("Layer"):
            try:
                return (0, int(name[5:]))
            except ValueError:
                return (0, 999)
        if name == "WM":
            return (1, 0)
        if name.startswith("Cluster"):
            try:
                return (2, int(name[7:]))
            except ValueError:
                return (2, 999)
        return (3, name)
    return sorted(names, key=key)


def _build_cluster_stats(
    cells: list[OverlayCellData],
    gt_names: list[str],
    pred_names: list[str],
) -> list[ClusterStat]:
    by_gt: dict[str, list[OverlayCellData]] = {n: [] for n in gt_names}
    for c in cells:
        by_gt.setdefault(c.ground_truth, []).append(c)

    stats: list[ClusterStat] = []
    for gt_name in gt_names:
        g_cells = by_gt[gt_name]
        n_true = len(g_cells)
        # Pred name for the same cluster: use first non-empty pred from this gt
        preds_in_gt = [c.prediction for c in g_cells if c.prediction]
        if preds_in_gt:
            from collections import Counter
            pred_name = Counter(preds_in_gt).most_common(1)[0][0]
        else:
            pred_name = gt_name

        n_pred = sum(1 for c in cells if c.prediction == pred_name)
        n_match = sum(
            1 for c in g_cells
            if c.error_type == ErrorType.CORRECT and c.prediction == pred_name
        )
        n_misclass = sum(1 for c in g_cells if c.error_type == ErrorType.MISCLASSIFIED)
        n_new = sum(1 for c in cells if c.prediction == pred_name and c.ground_truth != gt_name)
        n_missing = sum(
            1 for c in cells
            if c.ground_truth == gt_name and c.prediction != pred_name
        )
        agreement = (n_match / n_true) if n_true else 0.0

        try:
            gt_id = g_cells[0].gt_id if g_cells else None
        except Exception:
            gt_id = None
        try:
            pred_id = None
            for c in g_cells:
                if c.prediction == pred_name and c.pred_id is not None:
                    pred_id = c.pred_id
                    break
        except Exception:
            pred_id = None

        stats.append(
            ClusterStat(
                gt_name=gt_name,
                gt_id=gt_id,
                pred_name=pred_name,
                pred_id=pred_id,
                n_true=n_true,
                n_pred=n_pred,
                n_match=n_match,
                n_new=n_new,
                n_misclass=n_misclass,
                n_missing=n_missing,
                agreement=agreement,
            )
        )
    return stats


def _build_confusion(cells: list[OverlayCellData]) -> dict[tuple[str, str], int]:
    conf: dict[tuple[str, str], int] = {}
    for c in cells:
        key = (c.ground_truth, c.prediction)
        conf[key] = conf.get(key, 0) + 1
    return conf
