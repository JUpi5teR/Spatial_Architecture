# coding: utf-8

"""Upload Data page - system data entry.



Supports folder selection and .zip auto-extraction.

Displays expected folder structure (always visible).

Scans and validates data via DataPathManager.

"""

from __future__ import annotations



import shutil

import tempfile

import zipfile

from pathlib import Path

from typing import Optional



from PySide6.QtCore import Qt, Signal

from PySide6.QtWidgets import (

    QFileDialog, QFrame, QHBoxLayout, QLabel, QMessageBox,

    QProgressBar, QPushButton, QTextEdit,

    QTreeWidget, QTreeWidgetItem, QVBoxLayout, QWidget,

)



from model.data_path import DataPathManager, DataStructure

from utils.logger import logger





_FORMAT_HINT = """\

Expected folder structure:



main_file/

+-- Ground_Truth/

|   +-- <sample_id>/

|       +-- metadata.tsv

|       +-- spatial/

|           +-- tissue_positions_list.csv

|           +-- tissue_hires_image.png

|           +-- tissue_lowres_image.png

+-- Results/               (same structure as Ground_Truth)

|   +-- <sample_id>/

|       +-- metadata.tsv

|       +-- spatial/

|           +-- ...

+-- train_log/             (optional, training metrics)

    +-- loss.csv

    +-- ari.csv

    +-- nmi.csv

    +-- hs.csv

    +-- cs.csv"""





class UploadViewWidget(QWidget):

    """Upload data page.



    Signals

    -------

    folder_registered(Path)

        Emitted after a folder is selected and registered.

    """



    folder_registered = Signal(Path)



    def __init__(self, path_mgr: DataPathManager, parent: Optional[QWidget] = None):

        super().__init__(parent)

        self._mgr = path_mgr

        self._structure: Optional[DataStructure] = None
        self._pending_path: Optional[Path] = None

        self._dark = False
        self._build_ui()



    # ----------------------------------------------------------------

    # UI

    # ----------------------------------------------------------------

    def _build_ui(self) -> None:

        root_ly = QVBoxLayout(self)

        root_ly.setContentsMargins(40, 34, 40, 34)

        root_ly.setSpacing(16)



        title = QLabel("Upload Data")

        title.setStyleSheet("font-size: 24px; font-weight: 800; color: #1a1a1a;")

        root_ly.addWidget(title)



        # ---- Buttons ----

        btn_row = QHBoxLayout()

        btn_row.setSpacing(12)



        self._btn_folder = QPushButton("Select Folder...")

        self._btn_folder.setCursor(Qt.CursorShape.PointingHandCursor)

        self._btn_folder.setMinimumHeight(38)

        self._btn_folder.setStyleSheet(_BTN_STYLE)

        self._btn_folder.clicked.connect(self._on_select_folder)

        btn_row.addWidget(self._btn_folder)



        self._btn_zip = QPushButton("Select Zip...")

        self._btn_zip.setCursor(Qt.CursorShape.PointingHandCursor)

        self._btn_zip.setMinimumHeight(38)

        self._btn_zip.setStyleSheet(_BTN_STYLE)

        self._btn_zip.clicked.connect(self._on_select_zip)

        btn_row.addWidget(self._btn_zip)



        self._btn_clear = QPushButton("Clear")

        self._btn_clear.setCursor(Qt.CursorShape.PointingHandCursor)

        self._btn_clear.setMinimumHeight(38)

        self._btn_clear.setStyleSheet(_BTN_SECONDARY)

        self._btn_clear.clicked.connect(self._on_clear)

        self._btn_clear.setEnabled(False)

        btn_row.addWidget(self._btn_clear)

        self._btn_confirm = QPushButton("Confirm Upload")
        self._btn_confirm.setCursor(Qt.CursorShape.PointingHandCursor)
        self._btn_confirm.setMinimumHeight(38)
        self._btn_confirm.setStyleSheet(_BTN_CONFIRM)
        self._btn_confirm.setEnabled(False)
        self._btn_confirm.clicked.connect(self._on_confirm)
        btn_row.addWidget(self._btn_confirm)

        btn_row.addStretch()

        root_ly.addLayout(btn_row)



        # ---- Current path ----

        self._path_label = QLabel("No folder selected")

        self._path_label.setStyleSheet("color: #888; font-size: 12px;")

        self._path_label.setWordWrap(True)

        root_ly.addWidget(self._path_label)



        # ---- Progress bar ----

        self._progress = QProgressBar()

        self._progress.setMaximum(100)

        self._progress.setValue(0)

        self._progress.setFixedHeight(6)

        self._progress.setTextVisible(False)

        self._progress.setVisible(False)

        root_ly.addWidget(self._progress)



        sep = QFrame()

        sep.setFrameShape(QFrame.Shape.HLine)

        sep.setStyleSheet("background: #ececec; max-height: 1px; min-height: 1px;")

        root_ly.addWidget(sep)



        # ---- Structure preview ----

        preview_label = QLabel("Folder structure preview")

        preview_label.setStyleSheet("font-size: 14px; font-weight: 700; color: #333;")

        root_ly.addWidget(preview_label)



        self._tree = QTreeWidget()

        self._tree.setHeaderHidden(True)

        self._tree.setStyleSheet(_TREE_STYLE)

        self._tree.setMinimumHeight(160)

        root_ly.addWidget(self._tree)



        # ---- Validation status ----

        self._validation_label = QLabel("")

        self._validation_label.setStyleSheet("font-size: 13px; padding: 8px;")

        self._validation_label.setWordWrap(True)

        self._validation_label.setVisible(False)

        root_ly.addWidget(self._validation_label)



        # ---- File structure guide (always visible) ----

        guide_label = QLabel("Expected folder structure")

        guide_label.setStyleSheet("font-size: 13px; font-weight: 700; color: #555;")

        root_ly.addWidget(guide_label)



        self._hint_text = QTextEdit()

        self._hint_text.setReadOnly(True)

        self._hint_text.setPlainText(_FORMAT_HINT)

        self._hint_text.setStyleSheet(

            "QTextEdit { background: #fafafa; border: 1px solid #ececec; border-radius: 6px;"

            " font-family: Consolas, monospace; font-size: 11px; color: #555; padding: 10px; }"

        )

        self._hint_text.setMaximumHeight(260)

        root_ly.addWidget(self._hint_text)



    # ----------------------------------------------------------------

    # File selection callbacks

    # ----------------------------------------------------------------

    def _on_select_folder(self) -> None:

        path_str = QFileDialog.getExistingDirectory(self, "Select data folder")

        if not path_str:

            return

        self._register(Path(path_str))



    def _on_select_zip(self) -> None:

        path_str, _ = QFileDialog.getOpenFileName(

            self, "Select zip file", "", "Zip files (*.zip)"

        )

        if not path_str:

            return

        zip_path = Path(path_str)

        if not zip_path.is_file():

            QMessageBox.warning(self, "Error", f"File not found: {zip_path}")

            return



        self._progress.setVisible(True)

        self._progress.setValue(20)



        try:

            extract_dir = Path(tempfile.mkdtemp(prefix="clustroview_"))

            with zipfile.ZipFile(zip_path, "r") as zf:

                zf.extractall(extract_dir)

            self._progress.setValue(80)

            children = list(extract_dir.iterdir())

            if len(children) == 1 and children[0].is_dir():

                extract_dir = children[0]

            self._progress.setValue(100)

            logger.info("Zip extracted to %s", extract_dir)

            self._register(extract_dir)

        except zipfile.BadZipFile:

            QMessageBox.critical(self, "Error", "Invalid zip file.")

        except Exception as exc:

            QMessageBox.critical(self, "Error", f"Extraction failed: {exc}")

            logger.error("Zip extraction failed: %s", exc)

        finally:

            self._progress.setVisible(False)

            self._progress.setValue(0)



    def _on_confirm(self) -> None:
        """User clicks Confirm Upload button."""
        if self._pending_path:
            self._do_confirm()

    def _do_confirm(self) -> None:
        root = self._pending_path
        self._pending_path = None
        self._btn_confirm.setText("Confirmed")
        self._btn_confirm.setStyleSheet("QPushButton { background: #c8e6c9; color: #2e7d32; border: none; border-radius: 6px; font-size: 13px; padding: 8px 18px; font-weight: 600; }")
        self._btn_confirm.setEnabled(False)
        self._btn_confirm.update()
        self.folder_registered.emit(root)
        self._path_label.setStyleSheet("color: #2e7d32; font-size: 13px; font-weight: 600;")
        self._path_label.setText("Data confirmed: " + str(root))

    def _on_clear(self) -> None:

        self._mgr.clear()

        self._structure = None

        self._tree.clear()

        self._path_label.setText("No folder selected")

        self._path_label.setStyleSheet("color: #888; font-size: 12px;")

        self._btn_clear.setEnabled(False)

        self._validation_label.setVisible(False)

        self.folder_registered.emit(None)



    # ----------------------------------------------------------------

    # Registration & preview

    # ----------------------------------------------------------------

    def _register(self, root: Path, auto_confirm: bool = False) -> None:
        if root is None:
            return

        structure = self._mgr.set_root(root)

        self._structure = structure

        self._show_structure(structure)

        self._show_validation(structure)

        self._btn_clear.setEnabled(True)
        self._btn_confirm.setText("Confirm Upload")
        self._btn_confirm.setStyleSheet(_BTN_CONFIRM)
        self._btn_confirm.setEnabled(True)

        self._path_label.setText(f"Current path: {root}")

        self._path_label.setStyleSheet("color: #1a6bc0; font-size: 12px;")

        # Store pending path for Confirm button; do NOT emit yet
        self._pending_path = root



    def _show_structure(self, st: DataStructure) -> None:

        self._tree.clear()

        if st is None:

            return

        root_it = QTreeWidgetItem(self._tree, [st.root.name])

        root_it.setToolTip(0, str(st.root))



        if st.gt_root:

            gt = QTreeWidgetItem(root_it, ["Ground_Truth"])

            for sid in sorted([p.name for p in st.gt_root.iterdir() if p.is_dir()]):

                sec = QTreeWidgetItem(gt, [sid])

                _add_file_children(sec, st.gt_root / sid)

        else:

            QTreeWidgetItem(root_it, ["Ground_Truth (not found)"])



        if st.results_root and st.results_root != st.gt_root:

            res = QTreeWidgetItem(root_it, ["Results"])

            for sid in sorted([p.name for p in st.results_root.iterdir() if p.is_dir()]):

                sec = QTreeWidgetItem(res, [sid])

                _add_file_children(sec, st.results_root / sid)

        elif st.results_root and st.results_root == st.gt_root:

            QTreeWidgetItem(root_it, ["Results = Ground_Truth (single-dir mode)"])

        else:

            QTreeWidgetItem(root_it, ["Results (not found)"])



        if st.has_train_log:

            tlog = QTreeWidgetItem(root_it, ["train_log"])

            for metric in st.train_log_metrics:

                QTreeWidgetItem(tlog, [f"{metric}.csv"])

        else:

            QTreeWidgetItem(root_it, ["train_log (not found, optional)"])



        self._tree.expandAll()



    def _show_validation(self, st: DataStructure) -> None:

        if not st.warnings and st.is_valid:

            msg = f"Validation passed: {len(st.section_ids)} samples found - "

            msg += ", ".join(st.section_ids or ["(none)"])

            self._validation_label.setText(msg)

            self._validation_label.setStyleSheet(

                "font-size: 13px; padding: 8px; background: #e8f5e9; color: #2e7d32; border-radius: 6px;"

            )

        elif st.warnings:

            lines = ["Validation warnings:"]

            lines.extend(f"  * {w}" for w in st.warnings)

            if st.is_valid:

                lines.append(f"\nBasic validation passed ({len(st.section_ids)} samples), with warnings above.")

            else:

                lines.append("\nBasic validation failed. Check folder structure.")

            self._validation_label.setText("\n".join(lines))

            bg = "#fff3e0" if st.is_valid else "#ffebee"

            fg = "#e65100" if st.is_valid else "#c62828"

            self._validation_label.setStyleSheet(

                f"font-size: 13px; padding: 8px; background: {bg}; color: {fg}; border-radius: 6px;"

            )

        self._validation_label.setVisible(True)





# -------------------------------------------------------------------

# Helpers

# -------------------------------------------------------------------

def _add_file_children(parent: QTreeWidgetItem, directory: Path) -> None:

    for path in sorted(directory.iterdir()):

        if path.is_dir():

            sub = QTreeWidgetItem(parent, [path.name])

            for fpath in sorted(path.iterdir()):

                QTreeWidgetItem(sub, [fpath.name])

        else:

            QTreeWidgetItem(parent, [path.name])





# -------------------------------------------------------------------

# Styles

# -------------------------------------------------------------------

_BTN_STYLE = """

QPushButton {

    background: #1a6bc0; color: #fff; border: none; border-radius: 6px;

    font-size: 13px; padding: 8px 18px; font-weight: 600;

}

QPushButton:hover { background: #155a9e; }

QPushButton:pressed { background: #104a82; }

"""



_BTN_CONFIRM = """
QPushButton {
    background: #2e7d32; color: #fff; border: none; border-radius: 6px;
    font-size: 13px; padding: 8px 18px; font-weight: 600;
}
QPushButton:hover { background: #1b5e20; }
QPushButton:disabled { background: #ccc; color: #999; }
"""

_BTN_SECONDARY = """

QPushButton {

    background: #f5f5f5; color: #666; border: 1px solid #ddd; border-radius: 6px;

    font-size: 13px; padding: 8px 18px;

}

QPushButton:hover { background: #e8e8e8; color: #333; }

"""



_TREE_STYLE = """

QTreeWidget {

    background: #fafafa; border: 1px solid #ececec; border-radius: 6px;

    font-family: Consolas, monospace; font-size: 12px; color: #333;

    padding: 6px;

}

QTreeWidget::item { padding: 2px 0; }

QTreeWidget::item:hover { background: #eef3fb; }

"""


