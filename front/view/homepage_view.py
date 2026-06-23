# coding: utf-8
"""Homepage view - notebook management entry point.

Layout:
    [Header: Title + Search + Create Notebook]  [Tabs: Notebooks | Database]
    [Notebook cards grid / Database table]
    [Trash button (bottom-left)]
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QApplication, QDialog, QDialogButtonBox, QFrame, QGridLayout,
    QHBoxLayout, QInputDialog, QLabel, QLineEdit, QMenu, QMessageBox,
    QPushButton, QScrollArea, QSizePolicy, QTabWidget, QTableWidget,
    QTableWidgetItem, QTextEdit, QVBoxLayout, QWidget,
    QHeaderView, QAbstractItemView,
    
)

from backend.models import Notebook, NotebookManager, DatasetManager
from utils.logger import logger


# ====================================================================
# Styles
# ====================================================================
_CARD_STYLE_LIGHT = """
QFrame#notebookCard {
    background: #ffffff; border: 1px solid #e8e8e8; border-radius: 8px;
}
QFrame#notebookCard:hover {
    border-color: #b9d2f1; background: #fafcff;
}
"""
_CARD_STYLE_DARK = """
QFrame#notebookCard {
    background: #2a2a2e; border: 1px solid #3a3a3e; border-radius: 8px;
}
QFrame#notebookCard:hover {
    border-color: #4a6a9a; background: #303036;
}
"""
_CARD_STYLE = _CARD_STYLE_LIGHT
_CARD_TITLE = "font-size: 13px; font-weight: 700; color: #1a1a1a;"
_CARD_SUBTITLE = "font-size: 11px; color: #888;"
_CARD_COUNT = "font-size: 11px; color: #1a6bc0; font-weight: 600;"
_HOME_TITLE = "font-size: 28px; font-weight: 800; color: #1a1a1a;"
_HOME_SUBTITLE = "font-size: 13px; color: #888;"

_BTN_PRIMARY = """
QPushButton {
    background: #1a6bc0; color: #fff; border: none; border-radius: 8px;
    font-size: 13px; padding: 10px 22px; font-weight: 600;
}
QPushButton:hover { background: #155a9e; }
"""

_BTN_TRASH = """
QPushButton {
    background: transparent; color: #999; border: 1px solid #ddd;
    border-radius: 8px; font-size: 12px; padding: 8px 16px;
}
QPushButton:hover { background: #fef0f0; color: #d32f2f; border-color: #d32f2f; }
"""

_SEARCH_STYLE = """
QLineEdit {
    background: #ffffff; color: #333; border: 1px solid #e0e0e0;
    border-radius: 8px; padding: 8px 14px; font-size: 13px;
    min-width: 240px;
}
QLineEdit:focus { border-color: #1a6bc0; }
"""

_TAB_STYLE = """
QTabWidget::pane { border: none; background: transparent; }
QTabBar::tab {
    background: transparent; color: #888; border: none;
    padding: 8px 20px; font-size: 13px; font-weight: 600;
    border-bottom: 2px solid transparent;
}
QTabBar::tab:selected { color: #1a6bc0; border-bottom: 2px solid #1a6bc0; }
QTabBar::tab:hover { color: #333; }
"""

_TAB_STYLE_DARK = """
QTabWidget::pane { border: none; background: transparent; }
QTabBar::tab {
    background: transparent; color: #8a8a90; border: none;
    padding: 8px 20px; font-size: 13px; font-weight: 600;
    border-bottom: 2px solid transparent;
}
QTabBar::tab:selected { color: #7ab7ef; border-bottom: 2px solid #7ab7ef; }
QTabBar::tab:hover { color: #d0d0d5; }
"""


# ====================================================================
# Create Notebook Dialog
# ====================================================================
class CreateNotebookDialog(QDialog):
    """Modal dialog for creating a new notebook."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Create Notebook")
        self.setFixedSize(420, 240)
        self.setStyleSheet("""
            QDialog { background: #ffffff; }
            QLabel { font-size: 13px; color: #333; }
            QLineEdit {
                background: #fafafa; border: 1px solid #e0e0e0;
                border-radius: 6px; padding: 8px 12px; font-size: 13px;
            }
            QLineEdit:focus { border-color: #1a6bc0; }
        """)
        self._build()

    def _build(self):
        ly = QVBoxLayout(self)
        ly.setContentsMargins(24, 20, 24, 16)
        ly.setSpacing(14)

        title = QLabel("Create New Notebook")
        title.setStyleSheet("font-size: 18px; font-weight: 700; color: #1a1a1a;")
        self._title_label = title
        ly.addWidget(self._title_label)

        name_lbl = QLabel("Notebook Name")
        ly.addWidget(name_lbl)

        from datetime import datetime as dt
        default_name = "Notebook_" + dt.now().strftime("%Y%m%d_%H%M%S")
        self._name_input = QLineEdit(default_name)
        self._name_input.selectAll()
        ly.addWidget(self._name_input)

        desc_lbl = QLabel("Description (optional)")
        ly.addWidget(desc_lbl)

        self._desc_input = QLineEdit()
        self._desc_input.setPlaceholderText("Brief description of this notebook...")
        ly.addWidget(self._desc_input)

        ly.addStretch()

        btns = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok |
                                 QDialogButtonBox.StandardButton.Cancel)
        btns.button(QDialogButtonBox.StandardButton.Ok).setText("Create")
        btns.button(QDialogButtonBox.StandardButton.Ok).setStyleSheet("""
            QPushButton {
                background: #1a6bc0; color: #fff; border: none;
                border-radius: 6px; padding: 8px 20px; font-weight: 600;
            }
            QPushButton:hover { background: #155a9e; }
        """)
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        ly.addWidget(btns)

    def notebook_name(self):
        name = self._name_input.text().strip()
        return name if name else self._name_input.placeholderText()


# ====================================================================
# Notebook Card
# ====================================================================
class NotebookCard(QFrame):

    clicked = Signal(int)
    rename_requested = Signal(int, str)
    delete_requested = Signal(int)

    def __init__(self, notebook, dataset_count, cover_path=None, parent=None):
        super().__init__(parent)
        self.setObjectName("notebookCard")
        self.setStyleSheet(_CARD_STYLE)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedSize(240, 230)
        self._notebook = notebook
        self._dataset_count = dataset_count
        self._cover_path = cover_path
        self._build_ui()

    def _build_ui(self):
        ly = QVBoxLayout(self)
        ly.setContentsMargins(0, 0, 0, 0)
        ly.setSpacing(0)

        # Cover image
        if self._cover_path:
            cover = QLabel()
            cover.setFixedHeight(100)
            cover.setAlignment(Qt.AlignmentFlag.AlignCenter)
            cover.setStyleSheet(
                "border-top-left-radius: 8px; border-top-right-radius: 8px; background: #f0f0f3;"
            )
            pixmap = QPixmap(self._cover_path)
            if not pixmap.isNull():
                scaled = pixmap.scaled(240, 100, Qt.AspectRatioMode.KeepAspectRatioByExpanding, Qt.TransformationMode.SmoothTransformation)
                cover.setPixmap(scaled)
                cover.setScaledContents(True)
            cover.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
            ly.addWidget(cover)

        # Info area
        info = QFrame()
        info.setStyleSheet("background: transparent;")

        info_ly = QVBoxLayout(info)
        info_ly.setContentsMargins(12, 8, 12, 8)
        info_ly.setSpacing(2)

        # Name (truncated) + menu inline
        name_row = QHBoxLayout()
        name_row.setSpacing(2)
        display_name = self._notebook.name
        if len(display_name) > 18:
            display_name = display_name[:16] + "..."
        name_lbl = QLabel(display_name)
        name_lbl.setStyleSheet("font-size: 12px; font-weight: 700; color: #1a1a1a;")
        name_lbl.setWordWrap(False)
        name_lbl.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        name_row.addWidget(name_lbl)
        name_row.addStretch()

        self._menu_btn = QPushButton("⋮")
        self._menu_btn.setFixedSize(22, 22)
        self._menu_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._menu_btn.setStyleSheet("QPushButton { background: transparent; border: none; font-size: 14px; color: #aaa; } QPushButton:hover { color: #333; }")
        self._menu_btn.clicked.connect(self._show_menu)
        name_row.addWidget(self._menu_btn)
        info_ly.addLayout(name_row)

        # Dataset count
        count_lbl = QLabel(str(self._dataset_count) + " dataset(s)")
        count_lbl.setStyleSheet("font-size: 10px; color: #1a6bc0; font-weight: 600;")
        info_ly.addWidget(count_lbl)

        # Time
        time_lbl = QLabel(self._fmt(self._notebook.updated_at))
        time_lbl.setStyleSheet("font-size: 9px; color: #aaa;")
        info_ly.addWidget(time_lbl)

        ly.addWidget(info)

        # Install event filter + name menu button
        self.installEventFilter(self)
        self._menu_btn.setObjectName("menuBtn")

        # Clickable area
        for child in self.findChildren(QLabel):
            child.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)

    def set_dark(self, dark):
        """Update card colors for theme."""
        fg = "#d0d0d5" if dark else "#1a1a1a"
        sub = "#8a8a90" if dark else "#aaa"
        count_color = "#64b4ff" if dark else "#1a6bc0"
        for lbl in self.findChildren(QLabel):
            t = lbl.text()
            if t == self._notebook.name or (len(t) > 0 and t == self._notebook.name[:16] + "..."):
                lbl.setStyleSheet(f"font-size: 12px; font-weight: 700; color: {fg};")
            elif "dataset" in t.lower():
                lbl.setStyleSheet(f"font-size: 10px; color: {count_color}; font-weight: 600;")
            else:
                lbl.setStyleSheet(f"font-size: 9px; color: {sub};")

    def mousePressEvent(self, event):
        self.clicked.emit(self._notebook.id)
        super().mousePressEvent(event)

    def eventFilter(self, obj, event):
        if event.type() == event.Type.MouseButtonPress:
            if obj is not self._menu_btn:
                self.clicked.emit(self._notebook.id)
        return super().eventFilter(obj, event)

    def _show_menu(self):
        menu = QMenu(self)
        menu.addAction("Rename").triggered.connect(self._on_rename)
        menu.addAction("Delete").triggered.connect(self._on_delete)
        menu.exec(self.sender().mapToGlobal(self.sender().rect().bottomLeft()))

    def _on_rename(self):
        new_name, ok = QInputDialog.getText(self, "Rename Notebook", "New name:", QLineEdit.EchoMode.Normal, self._notebook.name)
        if ok and new_name.strip():
            self.rename_requested.emit(self._notebook.id, new_name.strip())

    def _on_delete(self):
        reply = QMessageBox.question(self, "Delete Notebook", 'Move "' + self._notebook.name + '" to Trash?', QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if reply == QMessageBox.StandardButton.Yes:
            self.delete_requested.emit(self._notebook.id)

    @staticmethod
    def _fmt(ts):
        if ts is None:
            return ""
        s = str(ts)
        return s[:16] if len(s) >= 16 else s


# ====================================================================
# Notebook Grid with Search
# ====================================================================
class NotebookGrid(QWidget):

    notebook_selected = Signal(int)
    notebook_renamed = Signal(int, str)
    notebook_deleted = Signal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._nb_mgr = NotebookManager()
        self._ds_mgr = DatasetManager()
        self._cards = []
        self._build_ui()

    def _build_ui(self):
        ly = QVBoxLayout(self)
        ly.setContentsMargins(0, 0, 0, 0)

        # Search bar
        search_row = QHBoxLayout()
        search_row.setContentsMargins(30, 8, 30, 4)
        self._search = QLineEdit()
        self._search.setPlaceholderText("Search notebooks by name...")
        self._search.setStyleSheet(_SEARCH_STYLE)
        self._search.textChanged.connect(self._on_search)
        search_row.addWidget(self._search)
        search_row.addStretch()
        ly.addLayout(search_row)

        # Grid
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setStyleSheet("QScrollArea { background: transparent; border: none; }")

        self._grid_widget = QWidget()
        self._grid_widget.setStyleSheet("background: transparent;")
        self._grid_layout = QGridLayout(self._grid_widget)
        self._grid_layout.setContentsMargins(30, 20, 30, 20)
        self._grid_layout.setSpacing(20)
        self._grid_layout.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)

        scroll.setWidget(self._grid_widget)
        ly.addWidget(scroll)

    def _on_search(self, text):
        query = text.strip().lower()
        for card in self._cards:
            if not query:
                card.setVisible(True)
            else:
                card.setVisible(query in card._notebook.name.lower())

    def refresh(self):
        self._clear_grid()
        notebooks = self._nb_mgr.list_active()

        if not notebooks:
            empty = QLabel('No notebooks yet.\nClick "+ New Notebook" to get started.')
            empty.setStyleSheet("font-size: 15px; color: #aaa; padding: 60px;")
            empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self._grid_layout.addWidget(empty, 0, 0)
            return

        cols = 4
        for i, nb in enumerate(notebooks):
            count = self._ds_mgr.count_by_notebook(nb.id)
            cover_path = self._find_notebook_cover(nb.id)
            card = NotebookCard(nb, count, cover_path)
            card.clicked.connect(self.notebook_selected.emit)
            card.rename_requested.connect(self._on_rename)
            card.delete_requested.connect(self._on_delete)
            self._cards.append(card)
            self._grid_layout.addWidget(card, i // cols, i % cols)

    def _find_notebook_cover(self, notebook_id):
        try:
            datasets = self._ds_mgr.list_by_notebook(notebook_id)
            if not datasets:
                return None
            from view.datasets_view import _find_cover_image
            for ds in datasets:
                gt_path = getattr(ds, "ground_truth_path", None) or ds.file_path
                path = _find_cover_image(gt_path)
                if path:
                    return path
        except Exception:
            pass
        return None

    def _clear_grid(self):
        self._cards.clear()
        while self._grid_layout.count():
            item = self._grid_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

    def _on_rename(self, nb_id, new_name):
        self._nb_mgr.update_name(nb_id, new_name)
        self.notebook_renamed.emit(nb_id, new_name)
        self.refresh()

    def _on_delete(self, nb_id):
        self._nb_mgr.soft_delete(nb_id)
        self.notebook_deleted.emit(nb_id)
        self.refresh()


# ====================================================================
# Database Panel
# ====================================================================
class DatabasePanel(QWidget):

    dataset_selected = Signal(int, int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._ds_mgr = DatasetManager()
        self._build_ui()

    def _build_ui(self):
        ly = QVBoxLayout(self)
        ly.setContentsMargins(30, 20, 30, 20)

        self._table = QTableWidget()
        self._table.setColumnCount(5)
        self._table.setHorizontalHeaderLabels([
            "Dataset Name", "Notebook", "Upload Time", "File Path", "Status"
        ])
        self._table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._table.setAlternatingRowColors(True)
        self._table.horizontalHeader().setStretchLastSection(True)
        self._table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        self._table.setStyleSheet("""
            QTableWidget {
                background: #ffffff; border: 1px solid #e8e8e8;
                border-radius: 8px; gridline-color: #f0f0f0;
                font-size: 12px; color: #333;
            }
            QTableWidget::item { padding: 6px 10px; }
            QTableWidget::item:selected { background: #e3eefb; color: #1a6bc0; }
            QHeaderView::section {
                background: #fafafa; border: none; border-bottom: 2px solid #e8e8e8;
                padding: 8px 10px; font-size: 11px; font-weight: 700; color: #666;
            }
        """)
        ly.addWidget(self._table)

    def refresh(self):
        datasets = self._ds_mgr.list_all_active()
        self._table.setRowCount(len(datasets))
        for i, ds in enumerate(datasets):
            self._table.setItem(i, 0, QTableWidgetItem(ds.name))
            nb_name = getattr(ds, "notebook_name", str(ds.notebook_id))
            self._table.setItem(i, 1, QTableWidgetItem(nb_name))
            self._table.setItem(i, 2, QTableWidgetItem(self._fmt(ds.upload_time)))
            self._table.setItem(i, 3, QTableWidgetItem(ds.file_path))
            self._table.setItem(i, 4, QTableWidgetItem(ds.status))
        self._table.resizeColumnsToContents()

    @staticmethod
    def _fmt(ts):
        try:
            dt = datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
            return dt.strftime("%Y-%m-%d %H:%M")
        except (ValueError, TypeError):
            return str(ts)[:16]


# ====================================================================
# Trash Panel (right-side slide-out with dimming overlay)
# ====================================================================
class TrashPanel(QFrame):

    closed = Signal()
    restored = Signal(int)
    permanently_deleted = Signal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._nb_mgr = NotebookManager()
        self._dark = False
        self.setObjectName("trashPanel")
        self.setFixedWidth(420)
        self._apply_theme()
        self._build_ui()

    def set_dark(self, dark: bool) -> None:
        self._dark = dark
        self._apply_theme()

    def _apply_theme(self):
        dark = self._dark
        bg = "#2a2a2e" if dark else "#ffffff"
        border = "#3a3a3e" if dark else "#ddd"
        fg = "#d0d0d5" if dark else "#333"
        title_fg = "#f5f5f7" if dark else "#333"
        close_color = "#8a8a90" if dark else "#aaa"
        close_hover = "#d0d0d5" if dark else "#333"
        card_bg = "#1e1e21" if dark else "#fafafa"
        card_border = "#3a3a3e" if dark else "#eee"
        card_fg = "#d0d0d5" if dark else "#333"
        time_fg = "#6a6a70" if dark else "#999"
        self.setStyleSheet(
            f"QFrame#trashPanel {{ background: {bg}; border-left: 1px solid {border}; }}"
        )
        # Update child widgets
        for lbl in self.findChildren(QLabel):
            t = lbl.text()
            if t.startswith('♻'):
                lbl.setStyleSheet(f"font-size: 18px; font-weight: 700; color: {title_fg};")
            elif "Deleted:" in t:
                lbl.setStyleSheet(f"font-size: 10px; color: {time_fg};")
            else:
                lbl.setStyleSheet(f"font-size: 13px; font-weight: 600; color: {card_fg};")
        for btn in self.findChildren(QPushButton):
            if btn.text() == '✕':
                btn.setStyleSheet(
                    f"QPushButton {{ background: transparent; border: none; font-size: 16px; color: {close_color}; }}"
                    f"QPushButton:hover {{ color: {close_hover}; }}"
                )
            elif btn.text() == 'Restore':
                btn.setStyleSheet(
                    f"QPushButton {{ background: {'#1a3a2e' if dark else '#e8f5e9'}; color: {'#81c784' if dark else '#2e7d32'}; border: none; border-radius: 4px; padding: 5px 14px; font-size: 11px; font-weight: 600; }}"
                    f"QPushButton:hover {{ background: {'#1e4e3a' if dark else '#c8e6c9'}; }}"
                )
            elif btn.text() == 'Delete Forever':
                btn.setStyleSheet(
                    f"QPushButton {{ background: {'#3a1a1a' if dark else '#ffebee'}; color: {'#ef9a9a' if dark else '#c62828'}; border: none; border-radius: 4px; padding: 5px 14px; font-size: 11px; font-weight: 600; }}"
                    f"QPushButton:hover {{ background: {'#4e2a2a' if dark else '#ffcdd2'}; }}"
                )
        # Update dynamically created cards
        for card in self.findChildren(QFrame):
            if card.objectName() == '' and card is not self and not isinstance(card, QScrollArea):
                card.setStyleSheet(
                    f"QFrame {{ background: {card_bg}; border: 1px solid {card_border}; border-radius: 8px; padding: 12px; }}"
                )

    def _build_ui(self):
        ly = QVBoxLayout(self)
        ly.setContentsMargins(20, 16, 20, 16)
        ly.setSpacing(12)

        # Header
        header = QHBoxLayout()
        title = QLabel("\u267B  Trash")
        title.setStyleSheet("font-size: 18px; font-weight: 700; color: #333;")
        header.addWidget(title)
        header.addStretch()
        close_btn = QPushButton("\u2715")
        close_btn.setFixedSize(28, 28)
        close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        close_btn.setStyleSheet(
            "QPushButton { background: transparent; border: none; font-size: 16px; color: #aaa; }"
            "QPushButton:hover { color: #333; }"
        )
        close_btn.clicked.connect(self.closed.emit)
        header.addWidget(close_btn)
        ly.addLayout(header)

        # Scroll area for cards
        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setFrameShape(QFrame.Shape.NoFrame)
        self._scroll.setStyleSheet("QScrollArea { background: transparent; border: none; }")

        self._card_container = QWidget()
        self._card_container.setStyleSheet("background: transparent;")
        self._card_layout = QVBoxLayout(self._card_container)
        self._card_layout.setContentsMargins(0, 0, 0, 0)
        self._card_layout.setSpacing(10)
        self._card_layout.addStretch()

        self._scroll.setWidget(self._card_container)
        ly.addWidget(self._scroll)
        self._refresh()

    def _refresh(self):
        # Clear existing cards
        while self._card_layout.count():
            item = self._card_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        notebooks = self._nb_mgr.list_trash()
        for nb in notebooks:
            card = QFrame()
            card_bg = "#1e1e21" if self._dark else "#fafafa"
            card_border = "#3a3a3e" if self._dark else "#eee"
            card.setStyleSheet(f"QFrame {{ background: {card_bg}; border: 1px solid {card_border}; border-radius: 8px; padding: 12px; }}")
            card_ly = QVBoxLayout(card)
            card_ly.setSpacing(6)

            name_lbl = QLabel(nb.name)
            card_fg = "#d0d0d5" if self._dark else "#333"
            name_lbl.setStyleSheet(f"font-size: 13px; font-weight: 600; color: {card_fg};")
            name_lbl.setWordWrap(True)
            card_ly.addWidget(name_lbl)

            ts = str(nb.deleted_at)[:16] if nb.deleted_at else "-"
            time_lbl = QLabel("Deleted: " + ts)
            time_color = "#6a6a70" if self._dark else "#999"
            time_lbl.setStyleSheet(f"font-size: 10px; color: {time_color};")
            card_ly.addWidget(time_lbl)

            btn_ly = QHBoxLayout()
            btn_ly.setSpacing(8)

            restore_btn = QPushButton("Restore")
            restore_btn.setCursor(Qt.CursorShape.PointingHandCursor)
            rst_bg = "#1a3a2e" if self._dark else "#e8f5e9"
            rst_fg = "#81c784" if self._dark else "#2e7d32"
            rst_hover = "#1e4e3a" if self._dark else "#c8e6c9"
            restore_btn.setStyleSheet(
                f"QPushButton {{ background: {rst_bg}; color: {rst_fg}; border: none; border-radius: 4px; padding: 5px 14px; font-size: 11px; font-weight: 600; }}"
                f"QPushButton:hover {{ background: {rst_hover}; }}"
            )
            restore_btn.clicked.connect(lambda _, nid=nb.id: self._restore(nid))
            btn_ly.addWidget(restore_btn)

            perm_btn = QPushButton("Delete Forever")
            perm_btn.setCursor(Qt.CursorShape.PointingHandCursor)
            prm_bg = "#3a1a1a" if self._dark else "#ffebee"
            prm_fg = "#ef9a9a" if self._dark else "#c62828"
            prm_hover = "#4e2a2a" if self._dark else "#ffcdd2"
            perm_btn.setStyleSheet(
                f"QPushButton {{ background: {prm_bg}; color: {prm_fg}; border: none; border-radius: 4px; padding: 5px 14px; font-size: 11px; font-weight: 600; }}"
                f"QPushButton:hover {{ background: {prm_hover}; }}"
            )
            perm_btn.clicked.connect(lambda _, nid=nb.id: self._perm_delete(nid))
            btn_ly.addWidget(perm_btn)
            btn_ly.addStretch()

            card_ly.addLayout(btn_ly)
            self._card_layout.addWidget(card)

        self._card_layout.addStretch()

    def _restore(self, nb_id):
        self._nb_mgr.restore(nb_id)
        self.restored.emit(nb_id)
        self._refresh()

    def _perm_delete(self, nb_id):
        reply = QMessageBox.warning(
            self, "Permanent Delete",
            "This action cannot be undone. Continue?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            self._nb_mgr.permanent_delete(nb_id)
            self.permanently_deleted.emit(nb_id)
            self._refresh()


# ====================================================================
# Dimming overlay for trash panel
# ====================================================================
class DimOverlay(QWidget):

    clicked_outside = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet("background: rgba(0, 0, 0, 0.45);")
        self.hide()

    def mousePressEvent(self, event):
        self.clicked_outside.emit()
        event.accept()

# Homepage View
# ====================================================================
class HomepageView(QWidget):

    notebook_opened = Signal(int)
    theme_toggled = Signal(bool)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._trash_panel = None
        self._dim_overlay = None
        self._dark = False
        self._build_ui()

    def _build_ui(self):
        ly = QVBoxLayout(self)
        ly.setContentsMargins(0, 0, 0, 0)
        ly.setSpacing(0)

        # Top bar
        top = QHBoxLayout()
        top.setContentsMargins(30, 20, 30, 12)

        title_block = QVBoxLayout()
        title_block.setSpacing(2)
        self._home_title_label = QLabel("ClustroView")
        self._home_title_label.setStyleSheet(_HOME_TITLE)
        self._home_subtitle_label = QLabel("Spatial Transcriptomics Analysis Platform")
        self._home_subtitle_label.setStyleSheet(_HOME_SUBTITLE)
        title_block.addWidget(self._home_title_label)
        title_block.addWidget(self._home_subtitle_label)
        top.addLayout(title_block)
        top.addStretch()

        new_btn = QPushButton("+ New Notebook")
        new_btn.setStyleSheet(_BTN_PRIMARY)
        new_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        new_btn.clicked.connect(self._create_notebook)
        top.addWidget(new_btn)
        ly.addLayout(top)

        # Tabs
        self._tabs = QTabWidget()
        self._tabs.setStyleSheet(_TAB_STYLE)

        self._notebook_grid = NotebookGrid()
        self._notebook_grid.notebook_selected.connect(self.notebook_opened.emit)
        self._notebook_grid.notebook_renamed.connect(self._on_refresh)
        self._notebook_grid.notebook_deleted.connect(self._on_refresh)

        self._tabs.addTab(self._notebook_grid, "Notebooks")
        ly.addWidget(self._tabs)

        # Bottom bar
        bottom = QHBoxLayout()
        bottom.setContentsMargins(30, 10, 30, 16)
        bottom.addStretch()
        self._theme_btn = QPushButton("\u263E  Dark")
        self._theme_btn.setStyleSheet(_BTN_TRASH)
        self._theme_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._theme_btn.clicked.connect(self._toggle_theme)
        bottom.addWidget(self._theme_btn)

        trash_btn = QPushButton("\u267B  Trash")
        trash_btn.setStyleSheet(_BTN_TRASH)
        trash_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        trash_btn.clicked.connect(self._show_trash)
        bottom.addWidget(trash_btn)
        ly.addLayout(bottom)

    def refresh(self):
        self._notebook_grid.refresh()

    def _create_notebook(self):
        dlg = CreateNotebookDialog(self)
        if self._dark:
            dlg.set_dark(True)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            name = dlg.notebook_name()
            nb_mgr = NotebookManager()
            nb = nb_mgr.create(name)
            self.refresh()
            self.notebook_opened.emit(nb.id)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self, "_trash_panel") and self._trash_panel is not None and self._trash_panel.isVisible():
            w = self.width()
            self._dim_overlay.setGeometry(0, 0, w, self.height())
            self._trash_panel.setGeometry(w - 420, 0, 420, self.height())

    def set_dark(self, dark):
        self._dark = dark
        global _CARD_STYLE
        _CARD_STYLE = _CARD_STYLE_DARK if dark else _CARD_STYLE_LIGHT
        style = _CARD_STYLE
        for card in self._notebook_grid._cards:
            card.setStyleSheet(style)
            card.set_dark(dark)
        # Update title colors
        bg = "#1e1e21" if dark else "#fafafa"
        fg = "#d0d0d5" if dark else "#1a1a1a"
        sub_fg = "#8a8a90" if dark else "#888"
        self.setStyleSheet(f"HomepageView {{ background-color: {bg}; }}")
        if hasattr(self, "_home_title_label"):
            self._home_title_label.setStyleSheet(f"font-size: 28px; font-weight: 800; color: {fg};")
        if hasattr(self, "_home_subtitle_label"):
            self._home_subtitle_label.setStyleSheet(f"font-size: 13px; color: {sub_fg};")
        # Update search box (on NotebookGrid)
        if hasattr(self, "_notebook_grid") and hasattr(self._notebook_grid, "_search"):
            self._notebook_grid._search.setStyleSheet(
                f"QLineEdit {{ background: {'#2a2a2e' if dark else '#fff'};"
                f" color: {fg}; border: 1px solid {'#3a3a3e' if dark else '#ddd'};"
                f" border-radius: 6px; padding: 6px 10px; font-size: 12px; }}"
            )
        # Update tabs style
        if hasattr(self, "_tabs"):
            self._tabs.setStyleSheet(
                _TAB_STYLE_DARK if dark else _TAB_STYLE
            )
        # Update trash panel
        if hasattr(self, "_trash_panel") and self._trash_panel is not None:
            self._trash_panel.set_dark(dark)
        # Update theme button text
        if hasattr(self, "_theme_btn"):
            self._theme_btn.setText("\u2600  Light" if dark else "\u263E  Dark")

    def _on_refresh(self, *args):
        self.refresh()

    def _toggle_theme(self):
        if getattr(self, '_theme_switching', False):
            return
        self._theme_switching = True
        try:
            self._dark = not self._dark
            self.setUpdatesEnabled(False)
            try:
                from view.main_window import apply_theme
                apply_theme(self._dark)
                self.set_dark(self._dark)
            finally:
                self.setUpdatesEnabled(True)
            self.theme_toggled.emit(self._dark)
            self._theme_btn.setText("\u2600  Light" if self._dark else "\u263E  Dark")
        finally:
            self._theme_switching = False

    def _show_trash(self):
        if self._trash_panel is None:
            self._trash_panel = TrashPanel(self)
            self._trash_panel.closed.connect(self._hide_trash)
            self._trash_panel.restored.connect(self._on_refresh)
            self._trash_panel.permanently_deleted.connect(self._on_refresh)
        if self._dim_overlay is None:
            self._dim_overlay = DimOverlay(self)
            self._dim_overlay.clicked_outside.connect(self._hide_trash)
        w = self.width()
        self._dim_overlay.setGeometry(0, 0, w, self.height())
        self._trash_panel.setGeometry(w - 420, 0, 420, self.height())
        self._dim_overlay.show()
        self._dim_overlay.raise_()
        self._trash_panel.show()
        self._trash_panel.raise_()

    def _hide_trash(self):
        if self._trash_panel:
            self._trash_panel.hide()
        if self._dim_overlay:
            self._dim_overlay.hide()
