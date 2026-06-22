# coding: utf-8
"""Datasets page - shows uploaded datasets for the current notebook."""
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QAbstractItemView, QDialog, QDialogButtonBox, QHeaderView,
    QInputDialog, QLabel, QMessageBox, QPushButton,
    QTableWidget, QTableWidgetItem, QTreeWidget, QTreeWidgetItem,
    QVBoxLayout, QWidget,
)
from pathlib import Path

_TITLE = "font-size: 22px; font-weight: 800; color: #1a1a1a; padding: 24px 30px 4px 30px;"


class FilePreviewDialog(QDialog):
    def __init__(self, file_path, name, parent=None):
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

    def _walk(self, parent_item, path, depth):
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


class DatasetsViewWidget(QWidget):
    dataset_activated = Signal(int)

    def __init__(self, ds_mgr, notebook, parent=None):
        super().__init__(parent)
        self._ds_mgr = ds_mgr
        self._notebook = notebook
        self._build_ui()

    def _build_ui(self):
        ly = QVBoxLayout(self)
        ly.setContentsMargins(0, 0, 0, 0)
        ly.addWidget(QLabel("Datasets"))
        title = self.findChild(QLabel)
        if title:
            title.setStyleSheet(_TITLE)
        sub = QLabel("Notebook: " + self._notebook.name)
        sub.setStyleSheet("font-size: 12px; color: #888; padding: 0 30px 16px 30px;")
        ly.addWidget(sub)
        self._table = QTableWidget()
        self._table.setColumnCount(5)
        self._table.setHorizontalHeaderLabels(["Name", "Time", "Path", "", ""])
        self._table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._table.horizontalHeader().setStretchLastSection(True)
        self._table.setMinimumHeight(200)
        self._table.verticalHeader().setDefaultSectionSize(36)
        self._table.horizontalHeader().setMinimumSectionSize(80)
        self._table.setStyleSheet("""
            QTableWidget { background: #fff; border: 1px solid #e8e8e8; border-radius: 8px; font-size: 12px; }
            QTableWidget::item { padding: 6px 10px; }
            QHeaderView::section { background: #fafafa; border: none; border-bottom: 2px solid #e8e8e8; padding: 8px; font-weight: 700; }
        """)
        self._info_label = QLabel("No datasets loaded")
        self._info_label.setStyleSheet("font-size: 13px; color: #888; padding: 8px 30px; font-weight: 400;")
        ly.addWidget(self._info_label)
        ly.addWidget(self._table)

    def refresh(self):
        import logging
        log = logging.getLogger('training_viewer')
        log.info('DatasetsViewWidget.refresh: notebook_id=%s', self._notebook.id)
        try:
            datasets = self._ds_mgr.list_by_notebook(self._notebook.id)
            log.info('DatasetsViewWidget.refresh: found %d datasets', len(datasets))
        except Exception as exc:
            log.error('DatasetsViewWidget.refresh failed: %s', exc, exc_info=True)
            return
        self._table.setRowCount(len(datasets))
        if hasattr(self, '_info_label') and self._info_label:
            self._info_label.setText("Total: %d dataset(s) in this notebook" % len(datasets))
        for i, ds in enumerate(datasets):
            self._table.setItem(i, 0, QTableWidgetItem(ds.name))
            ts = ds.upload_time[:16] if ds.upload_time else "-"
            self._table.setItem(i, 1, QTableWidgetItem(ts))
            self._table.setItem(i, 2, QTableWidgetItem(ds.file_path))
            view_btn = QPushButton("View Files")
            view_btn.setStyleSheet("QPushButton { background: #f5f5f5; border: 1px solid #ddd; border-radius: 4px; padding: 4px 10px; font-size: 11px; }")
            view_btn.clicked.connect(lambda checked, d=ds: self._view(d))
            self._table.setCellWidget(i, 3, view_btn)
            load_btn = QPushButton("Select")
            load_btn.setStyleSheet("QPushButton { background: #1a6bc0; color: #fff; border: none; border-radius: 4px; padding: 4px 14px; font-size: 11px; font-weight: 600; }")
            load_btn.clicked.connect(lambda checked, did=ds.id: self.dataset_activated.emit(did))
            self._table.setCellWidget(i, 4, load_btn)
        self._table.resizeColumnsToContents()

    def _view(self, ds):
        dlg = FilePreviewDialog(ds.file_path, ds.name, self)
        dlg.exec()
