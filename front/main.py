"""Training Validation Viewer — Entry Point."""
import sys

from PySide6.QtWidgets import QApplication

from controller.main_controller import MainController
from utils.logger import logger
from view.main_window import MainWindow, apply_theme


def main() -> None:
    """Application entry point."""
    logger.info("Starting Training Validation Viewer")
    logger.info("Python version: %s", sys.version)

    app = QApplication(sys.argv)
    app.setStyle("Fusion")

    apply_theme(dark=True)

    window = MainWindow()
    controller = MainController(window)
    window._controller = controller

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
