"""Image directory scanner for GT/Prediction PNG pairs.

Layout (per section_id):
    GT:     {gt_dir}/{section_id}/{section_id}_gt.png
    Pred:   {pred_dir}/{section_id}/{section_id}_pred.png

When a result folder only contains a CSV with prediction labels
(`<pred_dir>/<section_id>/spatial/tissue_positions_list.csv` with a `pred`
column), the prediction PNG is generated on demand by rendering the per-spot
domain colours over the GT hires image, and cached in a temp directory.
"""
from __future__ import annotations

import tempfile
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Optional

import cv2
import numpy as np

from utils.logger import logger


class DirStatus(str, Enum):
    LOADED = "Loaded"
    MISSING = "Missing"
    ERROR = "Error"


# Prediction / domain palette (RGB 0-255). Mirrors
# front/spatial_viewer.get_domain_color and front/model/overlay_data.
_DOMAIN_BGR = {
    "0": (127, 140, 141), "1": (226, 126, 34), "2": (231, 76, 60),
    "3": (243, 156, 18), "4": (211, 84, 0), "5": (192, 57, 43),
    "6": (241, 196, 15), "7": (169, 50, 38), "8": (229, 152, 102),
    "9": (203, 67, 53), "10": (245, 176, 65), "WM": (127, 140, 141),
}
_FALLBACK_BGR = [
    (139, 0, 139), (0, 128, 128), (0, 100, 85), (30, 144, 255),
    (123, 104, 238), (106, 90, 205), (72, 61, 139), (75, 0, 130),
    (142, 68, 173), (26, 188, 156), (17, 122, 101), (25, 25, 112),
]

_PRED_CACHE_DIR = Path(tempfile.gettempdir()) / "clustroview_pred_cache"


def _domain_color_bgr(label: str) -> tuple:
    """Return BGR tuple for a domain label, e.g. 'Domain3' -> (243,156,18)."""
    if not label:
        return _FALLBACK_BGR[0]
    bare = label[len("Domain"):] if label.startswith("Domain") else label
    if bare in _DOMAIN_BGR:
        return _DOMAIN_BGR[bare]
    if label in _DOMAIN_BGR:
        return _DOMAIN_BGR[label]
    return _FALLBACK_BGR[sum(ord(c) for c in label) % len(_FALLBACK_BGR)]


@dataclass
class ImagePair:
    """A GT / Prediction image pair for a single section."""
    section_id: str
    gt_path: Optional[Path]
    pred_path: Optional[Path]
    filename: str
    pred_missing: bool


@dataclass
class ImageCollection:
    """A collection of image pairs across sections."""
    pairs: list[ImagePair] = field(default_factory=list)
    gt_dir_status: str = "Missing"
    pred_dir_status: str = "Missing"
    has_pred: bool = False
    fallback_mode: bool = False  # True if no prediction images at all


def load_image(path: Optional[Path]) -> Optional[np.ndarray]:
    """Load an image as RGB numpy array (uint8)."""
    if path is None:
        return None
    try:
        raw = np.fromfile(str(path), dtype=np.uint8)
        bgr = cv2.imdecode(raw, cv2.IMREAD_COLOR)
        if bgr is None:
            logger.warning("Failed to decode image: %s", path)
            return None
        return cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
    except Exception as exc:
        logger.error("Exception loading %s: %s", path, exc)
        return None


def _load_pil(path: Path):
    """Optional PIL fallback for high-quality reading (used by PyVista textures)."""
    try:
        from PIL import Image
        return Image.open(path).convert("RGB")
    except Exception as exc:
        logger.warning("PIL load failed for %s: %s", path, exc)
        return None


def load_pil(path: Optional[Path]):
    return _load_pil(path) if path is not None else None


def _dir_status(dir_path: Path, has_files: bool) -> str:
    if not dir_path.exists() or not dir_path.is_dir():
        return DirStatus.MISSING.value
    if not has_files:
        return DirStatus.MISSING.value
    return DirStatus.LOADED.value


def _find_gt_image(folder: Path) -> Optional[Path]:
    """Pick the best representative GT image for a section folder."""
    if not folder.exists() or not folder.is_dir():
        return None
    # Prefer a hires image inside spatial/
    spatial = folder / "spatial"
    if spatial.is_dir():
        for name in ("tissue_hires_image.png", "tissue_lowres_image.png"):
            p = spatial / name
            if p.is_file():
                return p
    # Else take the first PNG anywhere in the folder
    for ext in ("*.png", "*.jpg", "*.jpeg", "*.tif", "*.tiff"):
        for p in sorted(folder.rglob(ext)):
            return p
    return None


def prediction_for_section(
    results_dir: Path,
    section_id: str,
    gt_dir: Optional[Path] = None,
) -> Optional[Path]:
    """Render a per-spot prediction PNG from the results CSV.

    The result CSV is expected at
    ``<results_dir>/<section_id>/spatial/tissue_positions_list.csv``
    with columns ``barcode, in_tissue, pxl_row_in_fullres, pxl_col_in_fullres,
    pred``. The output PNG is drawn over the GT hires image
    (or a blank canvas) and cached in a temp directory.

    Returns the path to the cached PNG, or None on failure.
    """
    csv_candidates = [
        results_dir / section_id / "spatial" / "tissue_positions_list.csv",
        results_dir / section_id / "metadata.tsv",
    ]
    csv_path: Optional[Path] = None
    for cand in csv_candidates:
        if cand.is_file():
            csv_path = cand
            break
    if csv_path is None:
        return None

    sep = "\t" if csv_path.suffix == ".tsv" else ","
    try:
        import csv as _csv
        with open(csv_path, encoding="utf-8") as f:
            reader = _csv.DictReader(f, delimiter=sep)
            if not reader.fieldnames:
                return None
            col_barcode = col_pred = None
            col_in_tissue = col_pix_row = col_pix_col = None
            for col in reader.fieldnames:
                cl = col.strip().lower()
                if cl in ("barcode", "cell_id", "cell", "spot"):
                    col_barcode = col
                elif cl in ("pred", "prediction", "label", "domain"):
                    col_pred = col
                elif cl == "in_tissue":
                    col_in_tissue = col
                elif cl == "pxl_row_in_fullres":
                    col_pix_row = col
                elif cl == "pxl_col_in_fullres":
                    col_pix_col = col
            if not (col_barcode and col_pred and col_pix_row and col_pix_col):
                return None
            spots = []
            for row in reader:
                if col_in_tissue is not None and str(row.get(col_in_tissue, "1")).strip() != "1":
                    continue
                try:
                    pr = int(float(row[col_pix_row]))
                    pc = int(float(row[col_pix_col]))
                except (TypeError, ValueError):
                    continue
                lbl = str(row[col_pred]).strip()
                # Skip negative / sentinel predictions.
                try:
                    if int(float(lbl)) < 0:
                        continue
                except (TypeError, ValueError):
                    pass
                if not lbl or lbl.lower() == "nan":
                    continue
                spots.append((pr, pc, lbl))
    except Exception as exc:
        logger.warning("prediction_for_section: CSV read failed: %s", exc)
        return None

    if not spots:
        return None

    # Determine background image (hires from GT) or blank canvas
    bg_bgr: Optional[np.ndarray] = None
    if gt_dir is not None:
        gt_img_path = _find_gt_image(gt_dir / section_id)
        if gt_img_path is not None:
            bg_bgr = cv2.imdecode(np.fromfile(str(gt_img_path), dtype=np.uint8),
                                  cv2.IMREAD_COLOR)
    if bg_bgr is None:
        # Use a blank canvas sized to the largest pixel coordinate
        max_r = max(pr for pr, _, _ in spots) + 1
        max_c = max(pc for _, pc, _ in spots) + 1
        bg_bgr = np.full((max_r, max_c, 3), 240, dtype=np.uint8)

    H, W = bg_bgr.shape[:2]
    # Cap absurd sizes to keep memory in check
    max_dim = 4096
    if max(H, W) > max_dim:
        scale = max_dim / max(H, W)
        bg_bgr = cv2.resize(bg_bgr, (int(W * scale), int(H * scale)))
        H, W = bg_bgr.shape[:2]
        spots = [(int(pr * scale), int(pc * scale), lbl) for pr, pc, lbl in spots]

    radius = max(2, int(round(min(H, W) / 350.0)))
    for pr, pc, lbl in spots:
        if not (0 <= pr < H and 0 <= pc < W):
            continue
        bgr = _domain_color_bgr(lbl)
        cv2.circle(bg_bgr, (pc, pr), radius, bgr, thickness=-1, lineType=cv2.LINE_AA)

    # Cache to temp dir
    try:
        _PRED_CACHE_DIR.mkdir(parents=True, exist_ok=True)
        out_path = _PRED_CACHE_DIR / f"{section_id}_pred.png"
        cv2.imencode(".png", bg_bgr)[1].tofile(str(out_path))
        return out_path
    except Exception as exc:
        logger.warning("prediction_for_section: write failed: %s", exc)
        return None


def scan_images(
    gt_dir: Path,
    pred_dir: Path,
    section_ids: list[str],
    allow_csv_fallback: bool = True,
) -> ImageCollection:
    """Scan both GT and Pred directories and build pairs.

    When ``pred_dir`` does not contain per-section prediction PNGs, but does
    contain a results CSV with a ``pred`` column, a prediction PNG is
    generated on-the-fly via :func:`prediction_for_section` so the side-by-
    side view can show a real GT vs Prediction comparison.
    """
    pairs: list[ImagePair] = []
    has_any_pred = False

    for sid in section_ids:
        gt_path = _find_gt_image(gt_dir / sid)
        if gt_path is None:
            logger.debug("GT image missing for %s", sid)
            continue

        # Prefer an existing prediction PNG; fall back to auto-generation.
        pred_path: Optional[Path] = None
        for cand_name in (
            f"{sid}_pred.png",
            "predicted_domain.png",
            f"{sid}_ground truth.png",
        ):
            cand = pred_dir / sid / cand_name
            if cand.is_file():
                pred_path = cand
                break
        if pred_path is None and allow_csv_fallback:
            generated = prediction_for_section(pred_dir, sid, gt_dir=gt_dir)
            if generated is not None:
                pred_path = generated

        if pred_path is not None:
            has_any_pred = True

        pairs.append(
            ImagePair(
                section_id=sid,
                gt_path=gt_path,
                pred_path=pred_path,
                filename=sid,
                pred_missing=pred_path is None,
            )
        )

    gt_status = _dir_status(gt_dir, bool(pairs))
    pred_status = (
        DirStatus.LOADED.value
        if has_any_pred
        else _dir_status(pred_dir, pred_dir.exists() and any(pred_dir.iterdir()))
    )

    coll = ImageCollection(
        pairs=pairs,
        gt_dir_status=gt_status,
        pred_dir_status=pred_status,
        has_pred=has_any_pred,
        fallback_mode=not has_any_pred,
    )
    logger.info(
        "scan_images: %d pairs, gt=%s, pred=%s, fallback=%s",
        len(pairs), gt_status, pred_status, coll.fallback_mode,
    )
    return coll
