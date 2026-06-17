"""Image directory scanner for GT/Prediction PNG pairs.

Layout (per section_id):
    GT:     {gt_dir}/{section_id}/{section_id}_gt.png
    Pred:   {pred_dir}/{section_id}/{section_id}_pred.png
"""
from __future__ import annotations

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
        bgr = cv2.imread(str(path), cv2.IMREAD_COLOR)
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


def scan_images(
    gt_dir: Path,
    pred_dir: Path,
    section_ids: list[str],
) -> ImageCollection:
    """Scan both GT and Pred directories and build pairs.

    Both directories are expected to use the same structure:
        {root}/{section_id}/{section_id}_gt.png
        {root}/{section_id}/{section_id}_pred.png
    """
    pairs: list[ImagePair] = []
    has_any_pred = False

    for sid in section_ids:
        gt_path = gt_dir / sid / f"{sid}_ground truth.png"
        pred_path = pred_dir / sid / "predicted_domain.png"

        gt_exists = gt_path.exists() and gt_path.is_file()
        pred_exists = pred_path.exists() and pred_path.is_file()

        if not gt_exists:
            logger.debug("GT image missing for %s: %s", sid, gt_path)
            continue

        if pred_exists:
            has_any_pred = True

        pairs.append(
            ImagePair(
                section_id=sid,
                gt_path=gt_path if gt_exists else None,
                pred_path=pred_path if pred_exists else None,
                filename=sid,
                pred_missing=not pred_exists,
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
