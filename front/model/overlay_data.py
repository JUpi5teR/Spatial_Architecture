'''Overlay cell data: GT vs Prediction error analysis.'''
from __future__ import annotations

import json
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd

from utils.logger import logger


class ErrorType(str, Enum):
    CORRECT = "Correct"
    MISCLASSIFIED = "Misclassified"
    NEW = "New"
    MISSING = "Missing"


# Layer color palette - blue family with adjacent hues, no near-white
_LAYER_COLORS = {
    "Layer1": "#5DADE2",
    "Layer2": "#2E86C1",
    "Layer3": "#2874A6",
    "Layer4": "#1F618D",
    "Layer5": "#1A5276",
    "Layer6": "#154360",
    "WM":     "#5D6D7E",
}

_FALLBACK_COLORS = [
    "#008B8B", "#008080", "#0E6655", "#1E90FF",
    "#7B68EE", "#6A5ACD", "#483D8B", "#4B0082",
    "#8E44AD", "#1ABC9C", "#117A65", "#191970",
]

# Prediction/domain color palette - warm family (orange/red/pink)
_DOMAIN_COLORS = {
    "1": "#E67E22",
    "2": "#E74C3C",
    "3": "#F39C12",
    "4": "#D35400",
    "5": "#C0392B",
    "6": "#F1C40F",
    "7": "#A93226",
    "8": "#E59866",
    "9": "#CB4335",
    "10": "#F5B041",
    "0": "#7F8C8D",
    "WM": "#7F8C8D",
}

ERROR_RED_BRIGHT = "#FF0000"
ERROR_ORANGE_RED = "#FF4500"


def get_layer_color(layer_name: str) -> str:
    if layer_name in _LAYER_COLORS:
        return _LAYER_COLORS[layer_name]
    if not layer_name or layer_name == "Unknown":
        return "#BDBDBD"
    h = sum(ord(c) for c in layer_name) % len(_FALLBACK_COLORS)
    return _FALLBACK_COLORS[h]


def get_domain_color(domain_label: str) -> str:
    if domain_label in _DOMAIN_COLORS:
        return _DOMAIN_COLORS[domain_label]
    if not domain_label or domain_label == "Unknown":
        return "#BDBDBD"
    h = sum(ord(c) for c in domain_label) % len(_FALLBACK_COLORS)
    return _FALLBACK_COLORS[h]


@dataclass
class OverlayCellData:
    cell_id: str
    x: float
    y: float
    ground_truth: str
    prediction: str
    error_type: ErrorType
    gt_id: Optional[int] = None
    pred_id: Optional[int] = None


@dataclass
class ClusterStat:
    gt_name: str
    gt_id: Optional[int]
    pred_name: str
    pred_id: Optional[int]
    n_true: int
    n_pred: int
    n_match: int
    n_new: int
    n_misclass: int
    n_missing: int
    agreement: float


@dataclass
class OverlayDataset:
    section_id: str
    cells: list[OverlayCellData] = field(default_factory=list)
    hires_dim: float = 2000.0
    panel_w: float = 4.0
    panel_h: float = 3.0
    has_pred: bool = False
    cell_count: int = 0
    error_count: int = 0
    error_rate: float = 0.0
    gt_clusters: list[str] = field(default_factory=list)
    pred_clusters: list[str] = field(default_factory=list)
    cluster_stats: list[ClusterStat] = field(default_factory=list)
    confusion: dict[tuple[str, str], int] = field(default_factory=dict)

    def cells_by_type(self, etype: ErrorType) -> list[OverlayCellData]:
        return [c for c in self.cells if c.error_type == etype]


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
    img_path = spatial_dir / "tissue_hires_image.png"
    if img_path.exists():
        try:
            import cv2
            import numpy as np
            raw = np.fromfile(str(img_path), dtype=np.uint8)
            im = cv2.imdecode(raw, cv2.IMREAD_COLOR)
            if im is not None:
                return float(max(im.shape[0], im.shape[1]))
        except Exception:
            pass
    return _HIRES_DEFAULT


def _read_positions_with_header(pos_path: Path) -> dict[str, tuple[float, float]]:
    """Read positions from CSV with header row (like Results CSV)."""
    positions: dict[str, tuple[float, float]] = {}
    try:
        df = pd.read_csv(pos_path, dtype=str)
        # Detect column mapping
        barcode_col = None
        in_tissue_col = None
        px_row_col = None
        px_col_col = None
        for col in df.columns:
            cl = col.strip().lower()
            if cl in ("barcode", "cell_id", "cell", "spot"):
                barcode_col = col
            elif cl == "in_tissue":
                in_tissue_col = col
            elif cl in ("pxl_row", "pxl_row_in_fullres", "imagerow"):
                px_row_col = col
            elif cl in ("pxl_col", "pxl_col_in_fullres", "imagecol"):
                px_col_col = col
        if barcode_col is None:
            barcode_col = df.columns[0]
        if in_tissue_col is None:
            in_tissue_col = df.columns[1] if len(df.columns) > 1 else None
        if px_row_col is None:
            px_row_col = df.columns[4] if len(df.columns) > 4 else None
        if px_col_col is None:
            px_col_col = df.columns[5] if len(df.columns) > 5 else None
        if px_row_col is None or px_col_col is None:
            logger.warning("Cannot find position columns in %s", pos_path)
            return positions
        for _, row in df.iterrows():
            if in_tissue_col:
                in_tissue = str(row[in_tissue_col]).strip()
                if in_tissue != "1":
                    continue
            barcode = str(row[barcode_col]).strip()
            px_row = float(row[px_row_col])
            px_col = float(row[px_col_col])
            positions[barcode] = (px_row, px_col)
    except Exception as exc:
        logger.error("Failed to read positions from %s: %s", pos_path, exc)
    return positions


def _read_positions(pos_path: Path) -> dict[str, tuple[float, float]]:
    positions: dict[str, tuple[float, float]] = {}
    try:
        df = pd.read_csv(pos_path, header=None, dtype=str)
        for _, row in df.iterrows():
            in_tissue = str(row[1]).strip()
            if in_tissue != "1":
                continue
            barcode = str(row[0]).strip()
            px_row = float(row[4])
            px_col = float(row[5])
            positions[barcode] = (px_row, px_col)
    except Exception as exc:
        logger.error("Failed to read positions from %s: %s", pos_path, exc)
    return positions


def _load_results_labels(result_root: Path, section_id: str) -> dict[str, str]:
    result_dir = result_root / section_id
    if not result_dir.exists() or not result_dir.is_dir():
        return {}
    data_files = list(result_dir.glob("*.csv")) + list(result_dir.glob("*.tsv"))
    if not data_files:
        spatial_dir = result_dir / "spatial"
        if spatial_dir.is_dir():
            data_files = list(spatial_dir.glob("*.csv")) + list(spatial_dir.glob("*.tsv"))
    if not data_files:
        return {}
    data_path = data_files[0]
    logger.info("Loading results from %s", data_path)
    try:
        if data_path.suffix == ".csv":
            df = pd.read_csv(data_path, dtype=str)
        else:
            df = pd.read_csv(data_path, sep="\t", dtype=str)
        barcode_col = None
        label_col = None
        for col in df.columns:
            cl = col.strip().lower()
            if cl in ("barcode", "cell_id", "cell", "spot"):
                barcode_col = col
            elif cl in ("prediction", "label", "cluster", "graphbased", "pred", "pred_label", "predict", "domain"):
                label_col = col
        if barcode_col is None:
            barcode_col = df.columns[0]
        if label_col is None:
            candidates = [c for c in df.columns if c != barcode_col]
            label_col = candidates[-1] if candidates else df.columns[-1]
        result: dict[str, str] = {}
        for _, row in df.iterrows():
            b = str(row[barcode_col]).strip()
            l = str(row[label_col]).strip()
            if b and b.lower() != "nan" and l and l.lower() != "nan":
                result[b] = l
        logger.info("Loaded %d result labels for %s", len(result), section_id)
        return result
    except Exception as exc:
        logger.warning("Failed to load results for %s: %s", section_id, exc)
        return {}


def load_overlay_dataset(
    data_root: Path,
    section_id: str,
    gt_column: str = "layer_guess_reordered",
    pred_column: str = "GraphBased",
    result_root: Optional[Path] = None,
    panel_w: float = 4.0,
    panel_h: float = 3.0,
) -> Optional[OverlayDataset]:
    sec_dir = data_root / section_id
    meta_path = sec_dir / "metadata.tsv"
    pos_path = sec_dir / "spatial" / "tissue_positions_list.csv"

    if not meta_path.exists():
        logger.warning("Metadata not found: %s", meta_path)
        return None
    if not pos_path.exists():
        logger.warning("Positions not found: %s", pos_path)
        return None

    try:
        meta_df = pd.read_csv(meta_path, sep="\t", dtype=str)
    except Exception as exc:
        logger.error("Failed to read metadata: %s", exc)
        return None

    gt_map: dict[str, str] = {}
    internal_pred_map: dict[str, str] = {}
    has_internal_pred = pred_column in meta_df.columns

    for _, row in meta_df.iterrows():
        barcode = str(row.get("barcode", "")).strip()
        if not barcode or barcode.lower() == "nan":
            continue
        gt_val = str(row.get(gt_column, "")).strip()
        if gt_val and gt_val.lower() != "nan":
            gt_map[barcode] = gt_val
        if has_internal_pred:
            p_val = str(row.get(pred_column, "")).strip()
            if p_val and p_val.lower() != "nan":
                internal_pred_map[barcode] = p_val

    external_pred_map: dict[str, str] = {}
    has_results = False
    if result_root is not None and result_root.exists():
        external_pred_map = _load_results_labels(result_root, section_id)
        has_results = len(external_pred_map) > 0

    if has_results:
        pred_map = external_pred_map
        has_pred = True
    elif has_internal_pred:
        pred_map = internal_pred_map
        has_pred = True
    else:
        pred_map = {}
        has_pred = False

    # Read GT positions from GT CSV
    pos_meta = _read_positions(pos_path)
    hires = _hires_dim(sec_dir / "spatial")
    scale = _read_scale(sec_dir / "spatial")

    # Also read Results positions from Results CSV (for prediction side)
    res_pos_meta = {}
    if result_root is not None and result_root.exists():
        res_pos_path = result_root / section_id / "spatial" / "tissue_positions_list.csv"
        if res_pos_path.exists():
            res_pos_meta = _read_positions_with_header(res_pos_path)

    cells: list[OverlayCellData] = []
    for barcode, (px_row, px_col) in pos_meta.items():
        hx = float(px_col) * scale
        hy = float(px_row) * scale
        x = (hx / hires) * panel_w - panel_w / 2
        y = panel_h / 2 - (hy / hires) * panel_h

        gt_label = gt_map.get(barcode, "")
        pred_label = pred_map.get(barcode, "")

        # Skip impurity points: empty or NA ground truth
        if not gt_label or gt_label.upper() == "NA":
            continue

        gt_id = _normalize_to_id(gt_label)
        pred_id = _normalize_to_id(pred_label)

        if not has_pred:
            error_type = ErrorType.CORRECT
        elif not pred_label:
            error_type = ErrorType.MISSING if gt_label else ErrorType.CORRECT
        elif not gt_label:
            error_type = ErrorType.NEW
        elif gt_id == pred_id:
            error_type = ErrorType.CORRECT
        else:
            error_type = ErrorType.MISCLASSIFIED

        cells.append(OverlayCellData(
            cell_id=barcode, x=x, y=y,
            ground_truth=gt_label, prediction=pred_label,
            error_type=error_type, gt_id=gt_id, pred_id=pred_id,
        ))

    if not cells:
        logger.warning("No cells for section %s", section_id)
        return None

    gt_names = set(c.ground_truth for c in cells if c.ground_truth)
    pred_names = set(c.prediction for c in cells if c.prediction)
    gt_names_sorted = _sort_cluster_names(gt_names)
    pred_names_sorted = _sort_cluster_names(pred_names)

    cell_count = len(cells)
    error_cells = [c for c in cells if c.error_type != ErrorType.CORRECT]
    error_count = len(error_cells)
    error_rate = error_count / cell_count if cell_count else 0.0

    confusion = _build_confusion(cells)
    cluster_stats = _build_cluster_stats(cells, gt_names_sorted, pred_names_sorted)

    logger.info("Section %s: %d cells, %d errors, pred=%s", section_id, cell_count, error_count, has_pred)

    return OverlayDataset(
        section_id=section_id, cells=cells,
        hires_dim=hires, panel_w=panel_w, panel_h=panel_h,
        has_pred=has_pred, cell_count=cell_count,
        error_count=error_count, error_rate=error_rate,
        gt_clusters=gt_names_sorted, pred_clusters=pred_names_sorted,
        cluster_stats=cluster_stats, confusion=confusion,
    )


def load_all_overlay_datasets(
    data_root: Path,
    section_ids: list[str],
    gt_column: str = "layer_guess_reordered",
    pred_column: str = "GraphBased",
    result_root: Optional[Path] = None,
    panel_w: float = 4.0,
    panel_h: float = 3.0,
) -> list[OverlayDataset]:
    datasets: list[OverlayDataset] = []
    for sid in section_ids:
        ds = load_overlay_dataset(
            data_root, sid, gt_column, pred_column,
            result_root=result_root,
            panel_w=panel_w, panel_h=panel_h,
        )
        if ds is not None:
            datasets.append(ds)
        else:
            logger.warning("Section %s skipped", sid)
    return datasets


def _normalize_to_id(val) -> Optional[int]:
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
    try:
        return int(s)
    except ValueError:
        return None


def _sort_cluster_names(names: set[str]) -> list[str]:
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


def _build_cluster_stats(cells, gt_names, pred_names):
    by_gt = {n: [] for n in gt_names}
    for c in cells:
        by_gt.setdefault(c.ground_truth, []).append(c)
    stats = []
    for gt_name in gt_names:
        g_cells = by_gt[gt_name]
        n_true = len(g_cells)
        preds_in_gt = [c.prediction for c in g_cells if c.prediction]
        if preds_in_gt:
            from collections import Counter
            pred_name = Counter(preds_in_gt).most_common(1)[0][0]
        else:
            pred_name = gt_name
        n_pred = sum(1 for c in cells if c.prediction == pred_name)
        n_match = sum(1 for c in g_cells if c.error_type == ErrorType.CORRECT and c.prediction == pred_name)
        n_misclass = sum(1 for c in g_cells if c.error_type == ErrorType.MISCLASSIFIED)
        n_new = sum(1 for c in cells if c.prediction == pred_name and c.ground_truth != gt_name)
        n_missing = sum(1 for c in cells if c.ground_truth == gt_name and c.prediction != pred_name)
        agreement = (n_match / n_true) if n_true else 0.0
        gt_id = g_cells[0].gt_id if g_cells else None
        pred_id = None
        for c in g_cells:
            if c.prediction == pred_name and c.pred_id is not None:
                pred_id = c.pred_id
                break
        stats.append(ClusterStat(
            gt_name=gt_name, gt_id=gt_id, pred_name=pred_name, pred_id=pred_id,
            n_true=n_true, n_pred=n_pred, n_match=n_match,
            n_new=n_new, n_misclass=n_misclass, n_missing=n_missing,
            agreement=agreement,
        ))
    return stats


def _build_confusion(cells):
    conf = {}
    for c in cells:
        key = (c.ground_truth, c.prediction)
        conf[key] = conf.get(key, 0) + 1
    return conf
