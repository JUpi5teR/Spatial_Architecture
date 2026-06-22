# coding: utf-8
"""Datasets page - card panel layout with cover images."""
from __future__ import annotations

from pathlib import Path
from typing import Optional

from PySide6.QtCore import Qt, Signal, QSize
from PySide6.QtGui import QPixmap, QFont
from PySide6.QtWidgets import (
    QDialog, QDialogButtonBox, QFrame, QGridLayout, QInputDialog, QLabel,
    QMessageBox, QPushButton, QScrollArea, QTreeWidget, QTreeWidgetItem,
    QVBoxLayout, QWidget, QSizePolicy,
)

from utils.logger import logger

_TITLE = "font-size: 22px; font-weight: 800; color: #1a1a1a; padding: 24px 30px 4px 30px;"
_CARD_STYLE = """
QFrame#datasetCard {
    background: #fff; border: 1px solid #e8e8e8; border-radius: 10px;
}
QFrame#datasetCard:hover {
    border-color: #b9d2f1; background: #fafcff;
}
"""
_CARD_IMG_STYLE = "border-top-left-radius: 10px; border-top-right-radius: 10px; background: #f0f0f3;"


class FilePreviewDialog(QDialog):
    """Dialog showing the file tree of a dataset."""

    def __init__(self, file_path: str, name: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Files - " + name)
        self.setMinimumSize(500, 400)
        ly = QVBoxLayout(self)
        ly.setContentsMargins(16, 16, 16, 16)
        path_lbl = QLabel("Path: " + file_path)
        path_lbl.setWordWrap(True)
        path_lbl.setStyleSheet("font-size: 11px; color: #888;")
        ly.addWidget(path_lbl)
        self._tree = QTreeWidget()
        self._tree.setHeaderLabels(["Name", "Type"])
        self._tree.setStyleSheet("QTreeWidget { font-size: 12px; }")
        try:
            p = Path(file_path)
            if p.exists():
                self._walk(self._tree.invisibleRootItem(), p, 0)
        except Exception:
            QTreeWidgetItem(self._tree.invisibleRootItem(), ["(error reading path)"])
        self._tree.expandAll()
        ly.addWidget(self._tree)
        btns = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok)
        btns.button(QDialogButtonBox.StandardButton.Ok).setText("Close")
        btns.accepted.connect(self.accept)
        ly.addWidget(btns)

    def _walk(self, parent_item, path: Path, depth: int):
        if depth >= 3:
            return
        try:
            for f in sorted(path.iterdir()):
                item = QTreeWidgetItem(parent_item)
                item.setText(0, f.name)
                item.setText(1, "Folder" if f.is_dir() else "File")
                if f.is_dir():
                    self._walk(item, f, depth + 1)
        except PermissionError:
            pass


def _find_cover_image(ground_truth_path: str) -> Optional[str]:
    """Recursively search for any image file in the ground truth directory.

    Searches every subdirectory level by level until an image is found.
    Only returns None if no image exists anywhere in the tree.
    """
    root = Path(ground_truth_path) if ground_truth_path else None
    if root is None or not root.exists():
        return None

    image_exts = {".png", ".jpg", ".jpeg", ".bmp", ".gif", ".tif", ".tiff"}

    # Breadth-first search: check each directory level
    dirs_to_search = [root]
    while dirs_to_search:
        current = dirs_to_search.pop(0)
        try:
            entries = sorted(current.iterdir())
        except PermissionError:
            continue
        subdirs = []
        for entry in entries:
            if entry.is_file() and entry.suffix.lower() in image_exts:
                return str(entry)
            elif entry.is_dir():
                subdirs.append(entry)
        dirs_to_search.extend(subdirs)

    return None


class DatasetCard(QFrame):
    """A card widget displaying one dataset."""

    dataset_selected = Signal(int)
    dataset_renamed = Signal(int, str)
    dataset_deleted = Signal(int)

    def __init__(self, ds, is_loaded=False, parent=None):
        super().__init__(parent)
        self.setObjectName("datasetCard")
        self.setStyleSheet(_CARD_STYLE)
        self.setFixedSize(280, 400)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._ds = ds
        self._is_loaded = is_loaded

        ly = QVBoxLayout(self)
        ly.setContentsMargins(0, 0, 0, 0)
        ly.setSpacing(0)

        # ---- Cover image ----
        self._image_label = QLabel()
        self._image_label.setFixedHeight(180)
        self._image_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._image_label.setStyleSheet(_CARD_IMG_STYLE)
        self._image_label.setScaledContents(False)
        self._load_cover()
        ly.addWidget(self._image_label)

        # ---- Info section ----
        info_frame = QFrame()
        info_frame.setStyleSheet("background: transparent;")
        info_ly = QVBoxLayout(info_frame)
        info_ly.setContentsMargins(14, 12, 14, 10)
        info_ly.setSpacing(4)

        name_lbl = QLabel(ds.name)
        name_lbl.setFont(QFont("", 12, QFont.Weight.Bold))
        name_lbl.setStyleSheet("color: #1a1a1a;")
        name_lbl.setWordWrap(True)
        info_ly.addWidget(name_lbl)

        ts = ds.upload_time[:16] if ds.upload_time else "-"
        time_lbl = QLabel(ts)
        time_lbl.setStyleSheet("font-size: 11px; color: #999;")
        info_ly.addWidget(time_lbl)

        # Path (truncated)
        path_text = ds.file_path
        if len(path_text) > 40:
            path_text = "..." + path_text[-37:]
        path_lbl = QLabel(path_text)
        path_lbl.setStyleSheet("font-size: 10px; color: #bbb;")
        path_lbl.setWordWrap(True)
        info_ly.addWidget(path_lbl)

        info_ly.addStretch()

        # ---- Buttons ----
        btn_ly = QVBoxLayout()
        btn_ly.setContentsMargins(14, 0, 14, 12)
        btn_ly.setSpacing(4)

        select_btn = QPushButton("Selected" if self._is_loaded else "Select Dataset")
        select_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        if self._is_loaded:
            select_btn.setEnabled(False)
            select_btn.setStyleSheet(
                "QPushButton { background: #ccc; color: #888; border: none;"
                " border-radius: 4px; padding: 6px 10px; font-size: 12px; font-weight: 600; }"
            )
        else:
            select_btn.setStyleSheet(
                "QPushButton { background: #1a6bc0; color: #fff; border: none;"
                " border-radius: 4px; padding: 6px 10px; font-size: 12px; font-weight: 600; }"
                "QPushButton:hover { background: #155aa0; }"
            )
            select_btn.clicked.connect(lambda: self.dataset_selected.emit(self._ds.id))
        btn_ly.addWidget(select_btn)

        view_btn = QPushButton("View Files")
        view_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        view_btn.setStyleSheet(
            "QPushButton { background: #f5f5f5; border: 1px solid #ddd;"
            " border-radius: 4px; padding: 4px 10px; font-size: 11px; color: #555; }"
            "QPushButton:hover { background: #e8e8e8; }"
        )
        view_btn.clicked.connect(lambda: self._view_files())
        btn_ly.addWidget(view_btn)

        rename_btn = QPushButton("Rename")
        rename_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        rename_btn.setStyleSheet(
            "QPushButton { background: #fff; border: 1px solid #ddd;"
            " border-radius: 4px; padding: 4px 10px; font-size: 11px; color: #555; }"
            "QPushButton:hover { background: #eef3fb; border-color: #b9d2f1; }"
        )
        rename_btn.clicked.connect(self._rename)
        btn_ly.addWidget(rename_btn)

        delete_btn = QPushButton("Delete")
        delete_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        delete_btn.setStyleSheet(
            "QPushButton { background: #fff; border: 1px solid #e0c0c0;"
            " border-radius: 4px; padding: 4px 10px; font-size: 11px; color: #c0392b; }"
            "QPushButton:hover { background: #fdf0f0; border-color: #e74c3c; }"
        )
        delete_btn.clicked.connect(self._confirm_delete)
        btn_ly.addWidget(delete_btn)

        info_ly.addLayout(btn_ly)
        ly.addWidget(info_frame)

    def _load_cover(self):
        """Load the cover image into the card."""
        gt_path = getattr(self._ds, "ground_truth_path", None) or self._ds.file_path
        cover_path = _find_cover_image(gt_path)
        if cover_path:
            pixmap = QPixmap(cover_path)
            if not pixmap.isNull():
                scaled = pixmap.scaled(
                    280, 180,
                    Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                    Qt.TransformationMode.SmoothTransformation,
                )
                self._image_label.setPixmap(scaled)
                self._image_label.setScaledContents(True)
                return
        # No image found - show placeholder
        self._image_label.setText("No Preview")
        self._image_label.setStyleSheet(
            _CARD_IMG_STYLE + " color: #bbb; font-size: 14px;"
        )

    def _rename(self):
        new_name, ok = QInputDialog.getText(
            self, "Rename Dataset", "New name:",
            text=self._ds.name
        )
        if ok and new_name.strip() and new_name.strip() != self._ds.name:
            self.dataset_renamed.emit(self._ds.id, new_name.strip())

    def _confirm_delete(self):
        msg = "Are you sure you want to delete \"" + self._ds.name + "\"?\n\nThis action cannot be undone."
        reply = QMessageBox.question(
            self, "Delete Dataset", msg,
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            self.dataset_deleted.emit(self._ds.id)

    def _view_files(self):
        dlg = FilePreviewDialog(self._ds.file_path, self._ds.name, self)
        dlg.exec()


class DatasetsViewWidget(QWidget):
    """Card-based datasets page."""

    dataset_activated = Signal(int)
    dataset_renamed = Signal(int, str)
    dataset_deleted = Signal(int)

    def __init__(self, ds_mgr, notebook, parent=None):
        super().__init__(parent)
        self._ds_mgr = ds_mgr
        self._notebook = notebook
        self._current_dataset_id = None
        self._dark = False
        self._build_ui()

    def set_dark(self, dark: bool) -> None:
        self._dark = dark
        bg = "#1e1e21" if dark else "#fafafa"
        fg = "#d0d0d5" if dark else "#1a1a1a"
        sub_fg = "#8a8a90" if dark else "#888"
        self.setStyleSheet(f"DatasetsViewWidget {{ background-color: {bg}; }}")
        for lbl in self.findChildren(QLabel):
            t = lbl.text()
            if t == "Datasets":
                lbl.setStyleSheet(f"font-size: 22px; font-weight: 800; color: {fg}; padding: 24px 30px 4px 30px;")
            elif "Notebook:" in t:
                lbl.setStyleSheet(f"font-size: 12px; color: {sub_fg}; padding: 0 30px 16px 30px;")
            elif "Total:" in t or "No datasets" in t:
                lbl.setStyleSheet(f"font-size: 13px; color: {sub_fg}; padding: 4px 30px 12px 30px;")
        # Card background
        card_bg = "#2a2a2e" if dark else "#ffffff"
        card_border = "#3a3a3e" if dark else "#e8e8e8"
        for card in self.findChildren(QFrame):
            if card.objectName() == "datasetCard":
                card.setStyleSheet(
                    f"QFrame#datasetCard {{ background: {card_bg}; border: 1px solid {card_border}; border-radius: 10px; }}"
                    f"QFrame#datasetCard:hover {{ border-color: #b9d2f1; background: {'#303036' if dark else '#fafcff'}; }}"
                )

    def _build_ui(self):
        ly = QVBoxLayout(self)
        ly.setContentsMargins(0, 0, 0, 0)

        # Title
        title = QLabel("Datasets")
        title.setStyleSheet(_TITLE)
        ly.addWidget(title)

        sub = QLabel("Notebook: " + self._notebook.name)
        sub.setStyleSheet("font-size: 12px; color: #888; padding: 0 30px 16px 30px;")
        ly.addWidget(sub)

        # Info label
        self._info_label = QLabel("No datasets loaded")
        self._info_label.setStyleSheet(
            "font-size: 13px; color: #888; padding: 4px 30px 12px 30px;"
        )
        ly.addWidget(self._info_label)

        # Scroll area for cards
        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setFrameShape(QFrame.Shape.NoFrame)
        self._scroll.setStyleSheet("QScrollArea { background: transparent; border: none; }")

        self._card_container = QWidget()
        self._card_container.setStyleSheet("background: transparent;")
        self._card_layout = QGridLayout(self._card_container)
        self._card_layout.setContentsMargins(30, 0, 30, 20)
        self._card_layout.setSpacing(16)
        self._card_layout.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)

        self._scroll.setWidget(self._card_container)
        ly.addWidget(self._scroll)

    def set_current_dataset(self, dataset_id):
        self._current_dataset_id = dataset_id
        self.refresh()

    def refresh(self):
        """Rebuild the card grid with current datasets."""
        try:
            datasets = self._ds_mgr.list_by_notebook(self._notebook.id)
        except Exception as exc:
            logger.error("DatasetsViewWidget.refresh failed: %s", exc, exc_info=True)
            return

        # Clear existing cards
        while self._card_layout.count():
            item = self._card_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        n = len(datasets)
        self._info_label.setText(f"Total: {n} dataset(s) in this notebook")

        if n == 0:
            empty = QLabel("No datasets yet.\nUpload data to get started.")
            empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
            empty.setStyleSheet("font-size: 16px; color: #bbb; padding: 60px;")
            self._card_layout.addWidget(empty, 0, 0)
            return

        # Calculate columns based on available width (default: 3-4 columns)
        cols = 4
        for i, ds in enumerate(datasets):
            is_loaded = (self._current_dataset_id is not None and self._current_dataset_id == ds.id)
            card = DatasetCard(ds, is_loaded)
            card.dataset_selected.connect(self.dataset_activated.emit)
            card.dataset_renamed.connect(self.dataset_renamed.emit)
            card.dataset_deleted.connect(self.dataset_deleted.emit)
            row, col = divmod(i, cols)
            self._card_layout.addWidget(card, row, col)
