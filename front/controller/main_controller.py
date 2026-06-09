from pathlib import Path
from typing import Optional

from PySide6.QtCore import QObject

from model.image_manager import ImageCollection, scan_images
from model.training_log import (
    TrainingLog,
    get_plot_columns,
    load_training_log,
)
from utils.logger import logger
from view.main_window import MainWindow


class MainController(QObject):
    """Coordinates between model and view."""

    def __init__(self, window: MainWindow):
        super().__init__()
        self._window = window
        self._training_log: Optional[TrainingLog] = None
        self._collection: Optional[ImageCollection] = None

        self._log_dir = Path("logs/training")
        self._gt_dir = Path("DLPFC_result")
        self._pred_dir = Path("result")

    def initialize(self) -> None:
        """Load all data and populate the view."""
        logger.info("=== Application Start ===")
        self._window.show_status_message("Loading data...")

        self._load_training_data()
        self._load_image_data()

    def _load_training_data(self) -> None:
        """Load training log and populate status + params + curve."""
        self._training_log = load_training_log(self._log_dir)

        self._window.status_bar_widget.training_status.set_status(self._training_log.status)

        if self._training_log:
            self._window.params_widget.set_params(self._training_log.last_row)
            log = self._training_log
            x_col, y1_col, y2_col = get_plot_columns(log)

            if x_col == "epoch":
                x_values = [e.epoch for e in log.epochs]
            else:
                x_values = list(range(1, len(log.epochs) + 1))

            y1_values = [e.metrics.get(y1_col, 0) for e in log.epochs] if y1_col else []
            y2_values = [e.metrics.get(y2_col, 0) for e in log.epochs] if y2_col else []

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

        logger.info("Training data loaded: status=%s", self._training_log.status)

    def _load_image_data(self) -> None:
        """Scan image directories and populate the comparison view."""
        self._collection = scan_images(self._gt_dir, self._pred_dir)

        self._window.status_bar_widget.gt_status.set_status(self._collection.gt_dir_status)
        self._window.status_bar_widget.result_status.set_status(
            "Loaded" if self._collection.has_pred else self._collection.pred_dir_status
        )

        self._window.set_collection(self._collection)
        self._window.show_status_message(
            f"Loaded {len(self._collection.pairs)} image pairs"
        )
        logger.info("Image data loaded: %d pairs", len(self._collection.pairs))
