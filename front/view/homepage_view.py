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
_CARD_STYLE = """
QFrame#notebookCard {
    background: #ffffff;
    border: 1px solid #e8e8e8;
    border-radius: 10px;
}
QFrame#notebookCard:hover {
    border-color: #b9d2f1;
    background: #fafcff;
}
"""
_CARD_TITLE = "font-size: 15px; font-weight: 700; color: #1a1a1a;"
_CARD_SUBTITLE = "font-size: 11px; color: #888;"
_CARD_COUNT = "font-size: 12px; color: #1a6bc0; font-weight: 600;"
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
        ly.addWidget(title)

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

    def __init__(self, notebook, dataset_count, parent=None):
        super().__init__(parent)
        self.setObjectName("notebookCard")
        self.setStyleSheet(_CARD_STYLE)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setMinimumSize(220, 150)
        self.setMaximumWidth(280)
        self._notebook = notebook
        self._dataset_count = dataset_count
        self._build_ui()

    def _build_ui(self):
        ly = QVBoxLayout(self)
        ly.setContentsMargins(18, 16, 18, 14)
        ly.setSpacing(8)

        title_row = QHBoxLayout()
        title_row.setSpacing(4)
        name = QLabel(self._notebook.name)
        name.setStyleSheet(_CARD_TITLE)
        name.setWordWrap(True)
        name.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        name.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        title_row.addWidget(name)

        menu_btn = QPushButton("\u22EE")
        menu_btn.setFixedSize(28, 28)
        menu_btn.setStyleSheet(
            "QPushButton { background: transparent; border: none; font-size: 16px; color: #aaa; }"
            "QPushButton:hover { color: #333; }"
        )
        menu_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        menu_btn.clicked.connect(self._show_menu)
        title_row.addWidget(menu_btn)
        ly.addLayout(title_row)

        count = QLabel(str(self._dataset_count) + " dataset(s)")
        count.setStyleSheet(_CARD_COUNT)
        ly.addWidget(count)
        ly.addStretch()

        created = QLabel("Created: " + self._fmt(self._notebook.created_at))
        created.setStyleSheet(_CARD_SUBTITLE)
        ly.addWidget(created)

        updated = QLabel("Modified: " + self._fmt(self._notebook.updated_at))
        updated.setStyleSheet(_CARD_SUBTITLE)
        ly.addWidget(updated)

        # Make all child labels pass mouse events to the card
        for child in self.findChildren(QLabel):
            child.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)

    def _show_menu(self):
        menu = QMenu(self)
        menu.addAction("Rename").triggered.connect(self._on_rename)
        menu.addAction("Delete").triggered.connect(self._on_delete)
        menu.exec(self.sender().mapToGlobal(self.sender().rect().bottomLeft()))

    def _on_rename(self):
        new_name, ok = QInputDialog.getText(
            self, "Rename Notebook", "New name:",
            QLineEdit.EchoMode.Normal, self._notebook.name
        )
        if ok and new_name.strip():
            self.rename_requested.emit(self._notebook.id, new_name.strip())

    def _on_delete(self):
        reply = QMessageBox.question(
            self, "Delete Notebook",
            'Move "' + self._notebook.name + '" to Trash?',
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            self.delete_requested.emit(self._notebook.id)

    def mousePressEvent(self, event):
        self.clicked.emit(self._notebook.id)
        super().mousePressEvent(event)

    @staticmethod
    def _fmt(ts):
        if not ts:
            return "-"
        try:
            dt = datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
            return dt.strftime("%Y-%m-%d %H:%M")
        except (ValueError, TypeError):
            return str(ts)[:16]


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
            card = NotebookCard(nb, count)
            card.clicked.connect(self.notebook_selected.emit)
            card.rename_requested.connect(self._on_rename)
            card.delete_requested.connect(self._on_delete)
            self._cards.append(card)
            self._grid_layout.addWidget(card, i // cols, i % cols)

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
# Trash Dialog
# ====================================================================
class TrashDialog(QWidget):

    closed = Signal()
    restored = Signal(int)
    permanently_deleted = Signal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._nb_mgr = NotebookManager()
        self.setWindowFlags(Qt.WindowType.Popup | Qt.WindowType.FramelessWindowHint)
        self.setFixedSize(500, 400)
        self.setStyleSheet("""
            QWidget#trashDialog {
                background: #ffffff; border: 1px solid #ddd; border-radius: 12px;
            }
        """)
        self.setObjectName("trashDialog")
        self._build_ui()

    def _build_ui(self):
        ly = QVBoxLayout(self)
        ly.setContentsMargins(20, 16, 20, 16)
        header = QHBoxLayout()
        title = QLabel("\u267B  Trash")
        title.setStyleSheet("font-size: 18px; font-weight: 700; color: #333;")
        header.addWidget(title)
        header.addStretch()
        close_btn = QPushButton("\u2715")
        close_btn.setFixedSize(28, 28)
        close_btn.setStyleSheet(
            "QPushButton { background: transparent; border: none; font-size: 16px; color: #aaa; }"
            "QPushButton:hover { color: #333; }"
        )
        close_btn.clicked.connect(self.closed.emit)
        header.addWidget(close_btn)
        ly.addLayout(header)

        self._table = QTableWidget()
        self._table.setColumnCount(4)
        self._table.setHorizontalHeaderLabels(["Name", "Deleted At", "", ""])
        self._table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._table.horizontalHeader().setStretchLastSection(True)
        self._table.setStyleSheet("""
            QTableWidget {
                background: #fafafa; border: 1px solid #eee;
                border-radius: 6px; font-size: 12px;
            }
            QHeaderView::section {
                background: #fafafa; border: none; border-bottom: 1px solid #eee;
                padding: 6px; font-size: 11px; font-weight: 600; color: #888;
            }
        """)
        ly.addWidget(self._table)
        self._refresh()

    def _refresh(self):
        notebooks = self._nb_mgr.list_trash()
        self._table.setRowCount(len(notebooks))
        for i, nb in enumerate(notebooks):
            self._table.setItem(i, 0, QTableWidgetItem(nb.name))
            self._table.setItem(i, 1, QTableWidgetItem(
                str(nb.deleted_at)[:16] if nb.deleted_at else "-"
            ))
            restore_btn = QPushButton("Restore")
            restore_btn.setStyleSheet(
                "QPushButton { background: #e8f5e9; color: #2e7d32; border: none; "
                "border-radius: 4px; padding: 4px 12px; font-size: 11px; }"
                "QPushButton:hover { background: #c8e6c9; }"
            )
            restore_btn.clicked.connect(lambda _, nid=nb.id: self._restore(nid))
            self._table.setCellWidget(i, 2, restore_btn)

            perm_btn = QPushButton("Delete Forever")
            perm_btn.setStyleSheet(
                "QPushButton { background: #ffebee; color: #c62828; border: none; "
                "border-radius: 4px; padding: 4px 12px; font-size: 11px; }"
                "QPushButton:hover { background: #ffcdd2; }"
            )
            perm_btn.clicked.connect(lambda _, nid=nb.id: self._perm_delete(nid))
            self._table.setCellWidget(i, 3, perm_btn)
        self._table.resizeColumnsToContents()

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
# Homepage View
# ====================================================================
class HomepageView(QWidget):

    notebook_opened = Signal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._trash_dialog = None
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
        t = QLabel("ClustroView")
        t.setStyleSheet(_HOME_TITLE)
        st = QLabel("Spatial Transcriptomics Analysis Platform")
        st.setStyleSheet(_HOME_SUBTITLE)
        title_block.addWidget(t)
        title_block.addWidget(st)
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
        if dlg.exec() == QDialog.DialogCode.Accepted:
            name = dlg.notebook_name()
            nb_mgr = NotebookManager()
            nb = nb_mgr.create(name)
            self.refresh()
            self.notebook_opened.emit(nb.id)

    def _on_refresh(self, *args):
        self.refresh()

    def _toggle_theme(self):
        from view.main_window import apply_theme
        self._dark = not self._dark
        apply_theme(self._dark)
        self._theme_btn.setText("\u2600  Light" if self._dark else "\u263E  Dark")

    def _show_trash(self):
        if self._trash_dialog is None:
            self._trash_dialog = TrashDialog()
            self._trash_dialog.closed.connect(self._hide_trash)
            self._trash_dialog.restored.connect(self._on_refresh)
            self._trash_dialog.permanently_deleted.connect(self._on_refresh)
        btn = self.findChild(QPushButton)
        if btn:
            pos = btn.mapToGlobal(btn.rect().bottomLeft())
            self._trash_dialog.move(pos.x() - 430, pos.y() - 420)
        self._trash_dialog.show()
        self._trash_dialog.raise_()

    def _hide_trash(self):
        if self._trash_dialog:
            self._trash_dialog.hide()
