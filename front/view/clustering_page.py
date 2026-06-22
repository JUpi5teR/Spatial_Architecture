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
        self._gt_root = ""
        self._results_root = ""
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

        # Section navigator
        nav = QHBoxLayout()
        nav.setSpacing(6)
        self._btn_prev = QPushButton("‹ Prev")
        self._btn_prev.setCursor(Qt.CursorShape.PointingHandCursor)
        self._btn_prev.setStyleSheet(_BTN_STYLE)
        self._btn_prev.clicked.connect(self._on_prev_section)
        nav.addWidget(self._btn_prev)

        self._section_label = QLabel("-- / --")
        self._section_label.setStyleSheet(
            "font-size: 12px; color: #555; padding: 0 8px; min-width: 130px;"
        )
        self._section_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        nav.addWidget(self._section_label)

        self._btn_next = QPushButton("Next ›")
        self._btn_next.setCursor(Qt.CursorShape.PointingHandCursor)
        self._btn_next.setStyleSheet(_BTN_STYLE)
        self._btn_next.clicked.connect(self._on_next_section)
        nav.addWidget(self._btn_next)

        nav_w = QWidget()
        nav_w.setLayout(nav)
        bar.addWidget(nav_w)

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
            if self._spatial_viewer and self._gt_root and self._section_ids:
                idx = min(self._current_index, len(self._section_ids) - 1)
                if idx >= 0:
                    self._load_spatial(self._section_ids[idx])

    # ----------------------------------------------------------------
    # Hover panel callbacks
    # ----------------------------------------------------------------
    def _on_hover_section(self, sid):
        if HAS_SPATIAL and self._gt_root:
            if sid in self._section_ids:
                self._current_index = self._section_ids.index(sid)
                self._update_section_label()
                self._show_pair_at(self._current_index)
            self._load_spatial(sid)

    def _on_hover_view(self, view):
        if self._spatial_viewer:
            if view == "front":
                self._spatial_viewer.view_front()
            else:
                self._spatial_viewer.view_back()

    # ----------------------------------------------------------------
    # Section navigator
    # ----------------------------------------------------------------
    def _on_prev_section(self):
        if not self._section_ids:
            return
        self._current_index = (self._current_index - 1) % len(self._section_ids)
        self._show_current_section()

    def _on_next_section(self):
        if not self._section_ids:
            return
        self._current_index = (self._current_index + 1) % len(self._section_ids)
        self._show_current_section()

    def _show_current_section(self):
        idx = self._current_index
        if idx < 0 or idx >= len(self._section_ids):
            return
        sid = self._section_ids[idx]
        self._update_section_label()
        # Update side-by-side image pair
        self._show_pair_at(idx)
        # Update spatial 3D
        if HAS_SPATIAL and self._gt_root:
            self._load_spatial(sid)
        # Keep hover panel combo in sync
        if self._hover_panel is not None:
            cb = self._hover_panel._section_combo
            if cb.currentIndex() != idx:
                cb.blockSignals(True)
                cb.setCurrentIndex(idx)
                cb.blockSignals(False)

    def _show_pair_at(self, idx):
        if self._collection is None or not self._collection.pairs:
            return
        if idx < 0 or idx >= len(self._collection.pairs):
            return
        p = self._collection.pairs[idx]
        if p.pred_missing:
            self._comparison_view.show_fallback(p)
        else:
            self._comparison_view.show_pair(p)

    def _update_section_label(self):
        total = len(self._section_ids)
        if total == 0:
            self._section_label.setText("-- / --")
            return
        idx = min(self._current_index, total - 1)
        sid = self._section_ids[idx] if 0 <= idx < total else "-"
        self._section_label.setText(f"{sid}   ({idx + 1} / {total})")

    # ----------------------------------------------------------------
    # Data loading
    # ----------------------------------------------------------------
    def load_data(self, collection, gt_root="", results_root="", section_ids=None):
        self._collection = collection
        self._gt_root = gt_root
        self._results_root = results_root
        self._section_ids = list(section_ids) if section_ids else []

        if collection and collection.pairs:
            self._section_ids = [p.section_id for p in collection.pairs]
            self._current_index = min(self._current_index, len(self._section_ids) - 1)
            if self._current_index < 0:
                self._current_index = 0

            self._show_pair_at(self._current_index)
            self._update_section_label()

            # Populate hover panel section combo
            if self._hover_panel:
                self._hover_panel.set_sections(self._section_ids)
        else:
            self._update_section_label()

        # Always try to load the current section into the 3D view, so the
        # Spatial 3D tab shows real data even if Side-by-Side is empty.
        if (
            HAS_SPATIAL
            and self._spatial_viewer is not None
            and self._gt_root
            and self._section_ids
        ):
            sid = self._section_ids[min(self._current_index,
                                        len(self._section_ids) - 1)]
            self._load_spatial(sid)

    def _load_spatial(self, sid):
        if not HAS_SPATIAL or not self._spatial_viewer or not self._gt_root:
            return
        try:
            gt_ds = load_spatial_dataset(str(self._gt_root), sid)
            res_ds = None
            if self._results_root:
                res_ds = load_spatial_dataset(
                    str(self._results_root), sid,
                    results_dir=str(self._results_root),
                    pred_mode=True,
                )
            if gt_ds is not None:
                self._spatial_viewer.load_section(gt_ds, res_ds)
        except Exception as exc:
            from utils.logger import logger
            logger.warning("Failed to load spatial section %s: %s", sid, exc)

    def show_no_data(self):
        self._collection = None
        self._section_ids = []
        self._update_section_label()
        self._comparison_view.show_no_data()

    def set_dark(self, dark: bool):
        """Forward theme change to comparison view + 3D viewer."""
        if self._comparison_view is not None and hasattr(
            self._comparison_view, "update_theme"
        ):
            try:
                self._comparison_view.update_theme(dark)
            except Exception:
                pass
        if self._spatial_viewer is not None and hasattr(
            self._spatial_viewer, "set_dark"
        ):
            try:
                self._spatial_viewer.set_dark(dark)
            except Exception:
                pass

    @property
    def comparison_view(self):
        return self._comparison_view

    @property
    def gt_root(self) -> str:
        return self._gt_root

    @property
    def results_root(self) -> str:
        return self._results_root
