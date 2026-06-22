# coding: utf-8
"""Clustering page - Side-by-Side comparison + Spatial 3D viewer with hover panel."""
from __future__ import annotations

from pathlib import Path
from typing import Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QComboBox, QFrame, QHBoxLayout, QLabel, QPushButton,
    QStackedWidget, QTextEdit, QVBoxLayout, QWidget, QSizePolicy,
)

from model.image_manager import ImagePair
from view.comparison_view import ComparisonViewWidget

try:
    from spatial_viewer import SpatialViewerWidget, load_spatial_dataset
    HAS_SPATIAL = True
except ImportError:
    HAS_SPATIAL = False


_BTN_STYLE = """
QPushButton {
    font-size: 12px; padding: 6px 14px; border: 1px solid #e0e0e0;
    border-radius: 6px; background: #ffffff; color: #555; font-weight: 600;
}
QPushButton:hover { background: #eef3fb; border-color: #b9d2f1; color: #1a6bc0; }
QPushButton:checked {
    background: #e3eefb; border-color: #5b8fd9; color: #1a6bc0;
}
"""

_COMBO_STYLE = """
QComboBox {
    background: #fff; color: #333; border: 1px solid #e0e0e0;
    border-radius: 6px; padding: 4px 10px; font-size: 12px; min-width: 120px;
}
QComboBox:hover { border-color: #b9d2f1; }
"""


class HoverPanel(QFrame):
    """Right-side panel for Spatial 3D controls and hover info."""

    section_changed = Signal(str)
    mode_changed = Signal(str)
    view_requested = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("hoverPanel")
        self.setFixedWidth(200)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Expanding)
        self.setStyleSheet("""
            QFrame#hoverPanel {
                background: #fafafa; border-left: 1px solid #ececec;
                padding: 10px;
            }
            QLabel { font-size: 11px; color: #555; }
            QPushButton {
                background: #fff; color: #333; border: 1px solid #ddd;
                border-radius: 4px; padding: 6px 10px; font-size: 11px;
            }
            QPushButton:hover { background: #eef3fb; border-color: #b9d2f1; }
        """)
        self._build()

    def _build(self):
        ly = QVBoxLayout(self)
        ly.setContentsMargins(10, 10, 10, 10)
        ly.setSpacing(6)

        t = QLabel("SPATIAL 3D")
        t.setStyleSheet("font-size: 12px; font-weight: 800; color: #1a6bc0; padding-bottom: 4px;")
        ly.addWidget(t)

        ly.addWidget(QLabel("Section:"))
        self._section_combo = QComboBox()
        self._section_combo.setStyleSheet(_COMBO_STYLE)
        self._section_combo.currentTextChanged.connect(self.section_changed.emit)
        ly.addWidget(self._section_combo)

        ly.addWidget(QLabel("Mode:"))
        self._explore_btn = QPushButton("Explore")
        self._explore_btn.setCheckable(True)
        self._explore_btn.setChecked(True)
        self._explore_btn.clicked.connect(lambda: self._set_mode("explore"))
        ly.addWidget(self._explore_btn)

        self._analysis_btn = QPushButton("Analysis")
        self._analysis_btn.setCheckable(True)
        self._analysis_btn.clicked.connect(lambda: self._set_mode("analysis"))
        ly.addWidget(self._analysis_btn)

        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet("border: none; border-top: 1px solid #e0e0e0;")
        ly.addWidget(sep)

        ly.addWidget(QLabel("View:"))
        fv = QPushButton("Front View")
        fv.clicked.connect(lambda: self.view_requested.emit("front"))
        ly.addWidget(fv)
        bv = QPushButton("Back View")
        bv.clicked.connect(lambda: self.view_requested.emit("back"))
        ly.addWidget(bv)

        sep2 = QFrame()
        sep2.setFrameShape(QFrame.Shape.HLine)
        sep2.setStyleSheet("border: none; border-top: 1px solid #e0e0e0;")
        ly.addWidget(sep2)

        ly.addWidget(QLabel("Cluster Info:"))
        self._cluster_info = QTextEdit()
        self._cluster_info.setReadOnly(True)
        self._cluster_info.setMinimumHeight(80)
        self._cluster_info.setMaximumHeight(120)
        self._cluster_info.setPlaceholderText("Hover over clusters...")
        self._cluster_info.setStyleSheet(
            "QTextEdit { background: #fff; border: 1px solid #eee; border-radius: 4px; font-size: 10px; }"
        )
        ly.addWidget(self._cluster_info)
        ly.addStretch()

    def _set_mode(self, mode):
        self._explore_btn.setChecked(mode == "explore")
        self._analysis_btn.setChecked(mode == "analysis")
        self.mode_changed.emit(mode)

    def set_mode(self, mode):
        self._set_mode(mode)

    def set_cluster_info(self, cluster, count, meta):
        self._cluster_info.setText(
            "Cluster: " + str(cluster) + "\n"
            "Count: " + str(count) + "\n"
            + str(meta) if meta else ""
        )

    def set_sections(self, section_ids):
        self._section_combo.blockSignals(True)
        self._section_combo.clear()
        self._section_combo.addItems(section_ids)
        self._section_combo.blockSignals(False)


class ClusteringPage(QWidget):
    """Combined clustering page: Side-by-Side + Spatial 3D."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._mode = "sbs"
        self._collection = None
        self._current_index = 0
        self._data_root = ""
        self._section_ids = []
        self._build_ui()

    def _build_ui(self):
        ly = QVBoxLayout(self)
        ly.setContentsMargins(0, 0, 0, 0)
        ly.setSpacing(0)

        # ---- Top bar ----
        bar = QHBoxLayout()
        bar.setContentsMargins(16, 10, 16, 6)

        title = QLabel("Clustering")
        title.setStyleSheet("font-size: 22px; font-weight: 800; color: #1a1a1a;")
        bar.addWidget(title)
        bar.addStretch()

        self._btn_sbs = QPushButton("Side-by-Side")
        self._btn_sbs.setCheckable(True)
        self._btn_sbs.setChecked(True)
        self._btn_sbs.setCursor(Qt.CursorShape.PointingHandCursor)
        self._btn_sbs.setStyleSheet(_BTN_STYLE)
        self._btn_sbs.clicked.connect(lambda: self._set_mode("sbs"))
        bar.addWidget(self._btn_sbs)

        if HAS_SPATIAL:
            self._btn_3d = QPushButton("Spatial 3D")
            self._btn_3d.setCheckable(True)
            self._btn_3d.setCursor(Qt.CursorShape.PointingHandCursor)
            self._btn_3d.setStyleSheet(_BTN_STYLE)
            self._btn_3d.clicked.connect(lambda: self._set_mode("spatial"))
            bar.addWidget(self._btn_3d)
        else:
            self._btn_3d = None

        ly.addLayout(bar)

        # ---- Content ----
        content = QHBoxLayout()
        content.setContentsMargins(0, 0, 0, 0)
        content.setSpacing(0)

        self._content_stack = QStackedWidget()

        # Page 0: Side-by-Side
        self._comparison_view = ComparisonViewWidget()
        self._content_stack.addWidget(self._comparison_view)

        # Page 1: Spatial 3D
        if HAS_SPATIAL:
            spatial_container = QWidget()
            sp_ly = QHBoxLayout(spatial_container)
            sp_ly.setContentsMargins(0, 0, 0, 0)
            sp_ly.setSpacing(0)

            self._spatial_viewer = SpatialViewerWidget()
            self._spatial_viewer.setMinimumHeight(400)
            sp_ly.addWidget(self._spatial_viewer, 1)

            self._hover_panel = HoverPanel()
            self._hover_panel.section_changed.connect(self._on_hover_section)
            self._hover_panel.mode_changed.connect(self._spatial_viewer.set_mode)
            self._hover_panel.view_requested.connect(self._on_hover_view)
            if hasattr(self._spatial_viewer, 'cluster_hovered'):
                self._spatial_viewer.cluster_hovered.connect(
                    self._hover_panel.set_cluster_info
                )
            sp_ly.addWidget(self._hover_panel)

            self._content_stack.addWidget(spatial_container)
        else:
            self._spatial_viewer = None
            self._hover_panel = None
            placeholder = QLabel(
                "Spatial 3D requires pyvista.\nInstall: pip install pyvista pyvistaqt"
            )
            placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
            placeholder.setStyleSheet("font-size: 14px; color: #aaa; padding: 60px;")
            self._content_stack.addWidget(placeholder)

        content.addWidget(self._content_stack)
        ly.addLayout(content)

    # ----------------------------------------------------------------
    # Mode
    # ----------------------------------------------------------------
    def _set_mode(self, mode):
        self._mode = mode
        self._btn_sbs.setChecked(mode == "sbs")
        if self._btn_3d:
            self._btn_3d.setChecked(mode == "spatial")
        if mode == "sbs":
            self._content_stack.setCurrentIndex(0)
        else:
            self._content_stack.setCurrentIndex(1)
            if self._spatial_viewer and self._data_root and self._section_ids:
                idx = min(self._current_index, len(self._section_ids) - 1)
                if idx >= 0:
                    self._load_spatial(self._section_ids[idx])

    # ----------------------------------------------------------------
    # Hover panel callbacks
    # ----------------------------------------------------------------
    def _on_hover_section(self, sid):
        if HAS_SPATIAL and self._data_root:
            self._load_spatial(sid)

    def _on_hover_view(self, view):
        if self._spatial_viewer:
            if view == "front":
                self._spatial_viewer.view_front()
            else:
                self._spatial_viewer.view_back()

    # ----------------------------------------------------------------
    # Data loading
    # ----------------------------------------------------------------
    def load_data(self, collection, data_root="", section_ids=None):
        self._collection = collection
        self._data_root = data_root
        self._section_ids = section_ids or []

        if collection and collection.pairs:
            ids = [p.section_id for p in collection.pairs]
            self._section_ids = ids
            self._current_index = 0

            # Show first image in side-by-side
            p = collection.pairs[0]
            if p.pred_missing:
                self._comparison_view.show_fallback(p)
            else:
                self._comparison_view.show_pair(p)

            # Populate hover panel section combo
            if self._hover_panel:
                self._hover_panel.set_sections(self._section_ids)

            # Load first section in spatial
            if self._mode == "spatial" and self._spatial_viewer:
                self._load_spatial(ids[0])

    def _load_spatial(self, sid):
        if not HAS_SPATIAL or not self._spatial_viewer:
            return
        try:
            ds = load_spatial_dataset(str(self._data_root), sid)
            if ds:
                self._spatial_viewer.load_section(ds)
        except Exception:
            pass

    def show_no_data(self):
        self._comparison_view.show_no_data()

    @property
    def comparison_view(self):
        return self._comparison_view
