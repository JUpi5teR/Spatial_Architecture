# coding: utf-8

"""ClustroView main window - root navigation shell.



Architecture (upgraded):

    MainWindow (QStackedWidget)

    +-- Page 0: HomepageView (notebook list, DB panel, trash)

    +-- Page 1: NotebookWorkspace (sidebar + module stack per notebook)



Themes: light by default, dark toggleable.

"""

from __future__ import annotations



from pathlib import Path

from typing import Any, Optional



from PySide6.QtCore import Qt

from PySide6.QtGui import QPalette, QColor

from PySide6.QtWidgets import (

    QApplication, QStackedWidget, QMainWindow, QStatusBar, QWidget,

)



from backend.models import Notebook, NotebookManager

from model.data_path import DataPathManager

from utils.logger import logger

from view.homepage_view import HomepageView

from view.notebook_workspace import NotebookWorkspace





# ====================================================================

# Palette

# ====================================================================

_DARK = {

   "Window": (18, 18, 20), "WindowText": (245, 245, 247),

   "Base": (30, 30, 33), "AlternateBase": (24, 24, 26),

   "Text": (245, 245, 247), "Button": (40, 40, 44),

   "ButtonText": (245, 245, 247), "BrightText": (255, 77, 79),

   "Link": (100, 180, 255), "Highlight": (100, 180, 255),

   "HighlightedText": (18, 18, 20),

}



_LIGHT = {

   "Window": (250, 250, 250), "WindowText": (46, 46, 46),

   "Base": (255, 255, 255), "AlternateBase": (245, 245, 245),

   "Text": (46, 46, 46), "Button": (245, 245, 245),

   "ButtonText": (46, 46, 46), "BrightText": (255, 77, 79),

   "Link": (50, 130, 220), "Highlight": (50, 130, 220),

   "HighlightedText": (250, 250, 250),

}







def apply_theme(dark: bool) -> None:

    app = QApplication.instance()

    if app is None:

        return

    pal = QPalette()

    src = _DARK if dark else _LIGHT

    for name, rgb in src.items():

        role = getattr(QPalette.ColorRole, name, None)

        if role is not None:

            pal.setColor(role, QColor(*rgb))

    app.setPalette(pal)





# ====================================================================

# MainWindow

# ====================================================================

class MainWindow(QMainWindow):

    """Root window that switches between Homepage and Notebook workspace."""



    def __init__(self) -> None:

        super().__init__()

        self.setWindowTitle("ClustroView - Spatial Transcriptomics Analysis")

        self.resize(1400, 880)

        self.setMinimumSize(960, 600)



        self._controller: Any = None

        self._path_mgr = DataPathManager()

        self._nb_mgr = NotebookManager()

        self._current_notebook: Optional[Notebook] = None

        self._notebook_workspace: Optional[NotebookWorkspace] = None
        self._dark = False



        # Central: stacked pages

        self._stack = QStackedWidget()



        # Page 0: Homepage

        self._homepage = HomepageView()

        self._homepage.notebook_opened.connect(self.open_notebook)

        self._stack.addWidget(self._homepage)



        self.setCentralWidget(self._stack)



        # Status bar

        self._status = QStatusBar()

        self._status.setStyleSheet(

            "QStatusBar { background: #fafafa; border-top: 1px solid #ececec; font-size: 11px; color: #888; }"

        )

        self.setStatusBar(self._status)



        self.show_homepage()



    # ================================================================

    # Navigation

    # ================================================================

    def show_homepage(self) -> None:

        self._current_notebook = None

        self._notebook_workspace = None

        self._homepage.refresh()

        self._stack.setCurrentWidget(self._homepage)



    def open_notebook(self, notebook_id: int) -> None:

        nb = self._nb_mgr.get_by_id(notebook_id)

        if nb is None:

            self.show_status_message(f"Notebook {notebook_id} not found")

            return



        self._current_notebook = nb



        # Create notebook workspace

        try:
            self._notebook_workspace = NotebookWorkspace(nb, self._path_mgr, dark=self._dark)
        except Exception as exc:
            import traceback
            traceback.print_exc()
            logger.error("Failed to create NotebookWorkspace: %s", exc)
            self.show_status_message("Error opening notebook: " + str(exc))
            return

        self._notebook_workspace.back_to_homepage.connect(self.show_homepage)
        self._notebook_workspace.theme_toggled.connect(self._on_theme_toggled)

        self._notebook_workspace.notebook_updated.connect(self._homepage.refresh)



        # Replace or add to stack

        if self._stack.count() > 1:

            old = self._stack.widget(1)

            self._stack.removeWidget(old)

            if old:

                old.deleteLater()



        self._stack.addWidget(self._notebook_workspace)

        self._stack.setCurrentWidget(self._notebook_workspace)



        if self._controller:

            self._notebook_workspace.set_controller(self._controller)



        logger.info("Opened notebook: id=%s name=%s", nb.id, nb.name)



    # ================================================================

    # Controller & path manager

    # ================================================================

    def set_controller(self, controller: Any) -> None:

        self._controller = controller



    def set_path_manager(self, mgr: DataPathManager) -> None:

        self._path_mgr = mgr



    @property

    def notebook_workspace(self) -> Optional[NotebookWorkspace]:

        return self._notebook_workspace



    @property

    def current_notebook(self) -> Optional[Notebook]:

        return self._current_notebook



    # ================================================================

    # Status

    # ================================================================

    def show_status_message(self, msg: str, timeout: int = 5000) -> None:

        self._status.showMessage(msg, timeout)

    def _on_theme_toggled(self, dark: bool) -> None:
        self._dark = dark
        apply_theme(dark)
