# coding: utf-8
"""ClustroView - Spatial Transcriptomics Analysis Platform.

Entry point.
Architecture: Homepage -> Notebook Workspace -> Analysis Modules
"""
import os as _os

# Fix: conda + user-site PySide6 can't find the Qt platform plugin.
import PySide6 as _ps6
if "QT_PLUGIN_PATH" not in _os.environ:
    _plug = _os.path.join(_os.path.dirname(_ps6.__file__), "plugins")
    if _os.path.isdir(_plug):
        _os.environ["QT_PLUGIN_PATH"] = _plug
    del _plug
del _os, _ps6

import sys
from pathlib import Path

# Ensure project root is on sys.path so 'backend' is importable
_PROJ_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJ_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJ_ROOT))

from PySide6.QtWidgets import QApplication

from controller.main_controller import MainController
from utils.logger import logger
from view.main_window import MainWindow, apply_theme


def main() -> None:
    """Application entry point."""
    logger.info("Starting ClustroView")
    logger.info("Python version: %s", sys.version)

    app = QApplication(sys.argv)
    app.setStyle("Fusion")

    apply_theme(dark=False)

    window = MainWindow()
    controller = MainController(window)

    try:
        controller.initialize()
    except Exception as exc:
        logger.critical("Initialization failed: %s", exc, exc_info=True)
        window.show_status_message(f"Initialization error: {exc}")

    window.show()
    logger.info("Window displayed")

    exit_code = app.exec()
    logger.info("Application exited with code %d", exit_code)
    sys.exit(exit_code)


if __name__ == "__main__":
    main()