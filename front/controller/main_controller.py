"""Main controller ? coordinates between model and view."""
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
DATA_ROOT = Path(r"E:\Code\AI_exercise\dataset\DLPFC")
GT_IMAGE_DIR = DATA_ROOT / "DLPFC_result"
LOG_DIR = Path(r"E:\Code\AI_exercise\logs\training")
PRED_DIR = Path(r"E:\Code\AI_exercise\result")

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

        self._load_training_data()
        self._load_overlay_data()
        self._load_image_data()

    def _load_training_data(self) -> None:
        """Load training log and populate status + params + curve."""
        self._training_log = load_training_log(LOG_DIR)

        self._window.status_bar_widget.training_status.set_status(
            self._training_log.status
        )

        if self._training_log:
            self._window.params_widget.set_params(self._training_log.last_row)
            log = self._training_log
            x_col, y1_col, y2_col = get_plot_columns(log)

            if x_col == "epoch":
                x_values = [e.epoch for e in log.epochs]
            else:
                x_values = list(range(1, len(log.epochs) + 1))

            y1_values = (
                [e.metrics.get(y1_col, 0) for e in log.epochs] if y1_col else []
            )
            y2_values = (
                [e.metrics.get(y2_col, 0) for e in log.epochs] if y2_col else []
            )

            if y1_col:
                self._window.curve_widget.plot(
                    epochs=x_values,
                    y1_name=y1_col or "",
                    y1_values=y1_values,
                    y2_name=y2_col,
                    y2_values=y2_values,
                )
            else:
                self._window.curve_widget.show_no_data()
        else:
            self._window.params_widget.clear()
            self._window.curve_widget.show_no_data()

        logger.info(
            "Training data loaded: status=%s", self._training_log.status
        )

    def _load_overlay_data(self) -> None:
        """Load overlay datasets from DLPFC metadata/CSV files.

        When prediction results exist, compare GT vs Pred.
        When no prediction, fall back to self-comparison (GT vs GT = all correct).
        """
        if not DATA_ROOT.exists():
            logger.warning("Data root not found: %s", DATA_ROOT)
            return

        # Check if prediction result data is available
        has_pred_results = PRED_DIR.exists() and any(PRED_DIR.iterdir())

        if has_pred_results:
            gt_col = "layer_guess"
            pred_col = "GraphBased"
            self._window.status_bar_widget.result_status.set_status("Loaded")
            logger.info("Prediction results found, comparing %s vs %s", gt_col, pred_col)
        else:
            # No prediction: self-comparison, all points correct
            gt_col = "layer_guess"
            pred_col = "layer_guess"
            self._window.status_bar_widget.result_status.set_status("Missing (GT fallback)")
            logger.info("No prediction results, self-comparison: all correct")

        self._overlay_datasets = load_all_overlay_datasets(
            DATA_ROOT, SECTION_IDS,
            gt_column=gt_col,
            pred_column=pred_col,
        )

        if self._overlay_datasets:
            self._window.status_bar_widget.gt_status.set_status("Loaded")
            self._window.set_overlay_datasets(self._overlay_datasets)
            logger.info(
                "Overlay data loaded: %d sections", len(self._overlay_datasets)
            )
        else:
            logger.warning("No overlay datasets loaded")

    def _load_image_data(self) -> None:
        """Scan image directories and populate the comparison view."""
        self._collection = scan_images(GT_IMAGE_DIR, PRED_DIR)

        if not self._overlay_datasets:
            self._window.status_bar_widget.gt_status.set_status(
                self._collection.gt_dir_status
            )
        self._window.status_bar_widget.result_status.set_status(
            "Loaded"
            if self._collection.has_pred
            else self._collection.pred_dir_status
        )

        self._window.set_collection(self._collection)
        self._window.show_status_message(
            f"Loaded {len(self._collection.pairs)} image pairs"
        )
        logger.info("Image data loaded: %d pairs", len(self._collection.pairs))

    # === Navigation ===

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
