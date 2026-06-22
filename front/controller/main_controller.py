# coding: utf-8
"""Main controller - coordinates application lifecycle.

Responsibilities:
- Initialise database connection
- Manage notebook-level navigation
- Coordinate between model and view layers
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional

from PySide6.QtCore import QObject

from backend.database import get_db
from backend.models import NotebookManager, DatasetManager
from model.data_path import DataPathManager
from model.image_manager import ImageCollection, scan_images
from model.overlay_data import OverlayDataset, load_all_overlay_datasets
from model.training_log import TrainingLog, get_plot_columns, load_training_log
from utils.logger import logger
from view.main_window import MainWindow


# === Default data paths (fallback when no notebook is selected) ===
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
DATA_ROOT = _PROJECT_ROOT / "dataset" / "DLPFC"
GT_IMAGE_DIR = _PROJECT_ROOT / "dataset" / "DLPFC" / "DLPFC_result"
PRED_IMAGE_DIR = _PROJECT_ROOT / "results" / "DLPFC"
RESULT_ROOT = _PROJECT_ROOT / "results" / "DLPFC"
LOG_DIR = _PROJECT_ROOT / "logs" / "training"

SECTION_IDS = [
    "151507", "151508", "151509", "151510",
    "151669", "151670", "151671", "151672",
    "151673", "151674", "151675", "151676",
]


class MainController(QObject):
    """Application-level controller."""

    def __init__(self, window: MainWindow):
        super().__init__()
        self._window = window
        self._nb_mgr = NotebookManager()
        self._ds_mgr = DatasetManager()

        self._window.set_controller(self)

    def initialize(self) -> None:
        logger.info("=== Application Start ===")
        self._window.show_status_message("Initializing database...")

        # Init database
        try:
            db = get_db()
            db.connect()
            db.init_tables()
            logger.info("Database initialised")
        except Exception as exc:
            logger.error("Database init failed: %s", exc)
            self._window.show_status_message(f"Database error: {exc}")

        # Show homepage by default
        self._window.show_homepage()
        self._window.show_status_message("Ready")
        logger.info("Application initialised successfully")

    # ================================================================
    # Notebook management (convenience wrappers)
    # ================================================================
    def create_notebook(self, name: str) -> int:
        nb = self._nb_mgr.create(name)
        return nb.id

    def open_notebook(self, notebook_id: int) -> None:
        self._window.open_notebook(notebook_id)

    def delete_notebook(self, notebook_id: int) -> None:
        self._nb_mgr.soft_delete(notebook_id)
        self._window.show_homepage()