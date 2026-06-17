"""Main controller - coordinates between model and view.

Owns the data lifecycle:
- Scans DLPFC result directories for GT/Pred PNG pairs
- Reads metadata.tsv + tissue positions to build overlay cell datasets
- Optionally loads a training log (xlsx) - missing is OK
- Pushes data into the view and reacts to view events
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional

from PySide6.QtCore import QObject

from model.image_manager import ImageCollection, scan_images
from model.overlay_data import (
    OverlayDataset,
    load_all_overlay_datasets,
)
from model.training_log import (
    TrainingLog,
    get_plot_columns,
    load_training_log,
)
from utils.logger import logger
from view.main_window import MainWindow


# === Data paths ===
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
DATA_ROOT = _PROJECT_ROOT / "DLPFC"
GT_IMAGE_DIR = DATA_ROOT / "DLPFC_result"
PRED_DIR = DATA_ROOT / "DLPFC_result"          # gt.png and pred.png live in the same folder
LOG_DIR = _PROJECT_ROOT / "logs" / "training"  # optional; missing -> no curve

SECTION_IDS = [
    "151507", "151508", "151509", "151510",
    "151669", "151670", "151671", "151672",
    "151673", "151674", "151675", "151676",
]


class MainController(QObject):
    """Coordinates between model and view."""

    def __init__(self, window: MainWindow):
        super().__init__()
        self._window = window
        self._training_log: Optional[TrainingLog] = None
        self._collection: Optional[ImageCollection] = None
        self._overlay_datasets: list[OverlayDataset] = []
        self._overlay_index: int = 0
        self._image_index: int = 0

        self._window.set_controller(self)

    def initialize(self) -> None:
        """Load all data and populate the view."""
        logger.info("=== Application Start ===")
        self._window.show_status_message("Loading data...")

        # 1) Training log (optional, non-fatal if missing)
        self._load_training_data()

        # 2) Image collection (drives section selector and visualization)
        self._load_image_data()

        # 3) Overlay datasets (drives error analysis in the 3D view + data tabs)
        self._load_overlay_data()

        # 4) Render the first section
        if self._overlay_datasets:
            self.show_overlay_at(0)
        elif self._collection and self._collection.pairs:
            self.show_image_at(0)
        else:
            self._window.show_status_message(
                "No data found - check DLPFC and DLPFC_result directories"
            )

    # ----------------------------------------------------------------
    #  Training log
    # ----------------------------------------------------------------
    def _load_training_data(self) -> None:
        self._training_log = load_training_log(LOG_DIR)
        logger.info("Training data loaded: status=%s", self._training_log.status)

    # ----------------------------------------------------------------
    #  Overlay data
    # ----------------------------------------------------------------
    def _load_overlay_data(self) -> None:
        if not DATA_ROOT.exists():
            logger.warning("Data root not found: %s", DATA_ROOT)
            return

        # Choose GT and prediction columns
        has_pred_results = (
            PRED_DIR.exists() and any(PRED_DIR.iterdir())
        )
        gt_col = "layer_guess"
        pred_col = "GraphBased" if has_pred_results else "layer_guess"
        logger.info(
            "Overlay columns: gt=%s, pred=%s (pred_dir=%s)",
            gt_col, pred_col, has_pred_results,
        )

        self._overlay_datasets = load_all_overlay_datasets(
            DATA_ROOT, SECTION_IDS,
            gt_column=gt_col,
            pred_column=pred_col,
        )
        if self._overlay_datasets:
            self._window.set_overlay_datasets(self._overlay_datasets)
            logger.info(
                "Overlay data loaded: %d sections", len(self._overlay_datasets),
            )
        else:
            logger.warning("No overlay datasets loaded")

    # ----------------------------------------------------------------
    #  Image data
    # ----------------------------------------------------------------
    def _load_image_data(self) -> None:
        self._collection = scan_images(GT_IMAGE_DIR, PRED_DIR, SECTION_IDS)
        self._window.set_collection(self._collection)
        self._window.show_status_message(
            f"Loaded {len(self._collection.pairs)} image pairs"
        )
        logger.info("Image data loaded: %d pairs", len(self._collection.pairs))

    # ----------------------------------------------------------------
    #  Public navigation hooks
    # ----------------------------------------------------------------
    def overlay_count(self) -> int:
        return len(self._overlay_datasets)

    def image_count(self) -> int:
        if self._collection is None:
            return 0
        return len(self._collection.pairs)

    def show_overlay_at(self, index: int) -> None:
        if 0 <= index < len(self._overlay_datasets):
            self._overlay_index = index
            ds = self._overlay_datasets[index]
            self._window.show_overlay_dataset(ds, index)

    def show_image_at(self, index: int) -> None:
        if self._collection is None:
            return
        if 0 <= index < len(self._collection.pairs):
            self._image_index = index
            self._window.show_image(index)

    def on_section_changed(self, index: int) -> None:
        """Called by the main window when the section dropdown changes."""
        # In 3D Flip mode we prefer overlay data (richer)
        if self._is_3d_mode():
            self.show_overlay_at(index)
        else:
            self.show_image_at(index)

    def _is_3d_mode(self) -> bool:
        # Avoid touching private UI; check via the window's exposed attr if any
        return getattr(self._window, "_is_3dflip_mode", True)
