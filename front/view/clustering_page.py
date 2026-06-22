# coding: utf-8
"""Clustering page - Side-by-Side comparison + Spatial 3D viewer with hover panel."""
from __future__ import annotations

from pathlib import Path
from typing import Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QComboBox, QFrame, QHBoxLayout, QLabel, QPushButton,
    QSlider, QStackedWidget, QTextEdit, QVBoxLayout, QWidget, QSizePolicy,
)

from model.image_manager import ImagePair
from view.comparison_view import ComparisonViewWidget

from utils.logger import logger
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
    error_toggled = Signal(bool)
    tolerance_changed = Signal(float)
    strict_toggled = Signal(bool)

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
        self._mode_btn = QPushButton("Explore")
        self._mode_btn.setCheckable(True)
        self._mode_btn.setChecked(False)
        self._mode_btn.clicked.connect(self._toggle_mode)
        ly.addWidget(self._mode_btn)

        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet("border: none; border-top: 1px solid #e0e0e0;")
        ly.addWidget(sep)

        ly.addWidget(QLabel("View:"))
        self._view_btn = QPushButton("Front")
        self._view_btn.setCheckable(True)
        self._view_btn.setChecked(False)
        self._view_btn.clicked.connect(self._toggle_view)
        ly.addWidget(self._view_btn)

        self._error_btn = QPushButton("Show Error Points")
        self._error_btn.setCheckable(True)
        self._error_btn.setChecked(False)
        self._error_btn.clicked.connect(lambda: self.error_toggled.emit(self._error_btn.isChecked()))
        ly.addWidget(self._error_btn)

        # Strict mode toggle
        self._strict_btn = QPushButton("Strict Mode (OFF)")
        self._strict_btn.setCheckable(True)
        self._strict_btn.setChecked(False)
        self._strict_btn.clicked.connect(lambda: self._on_strict_toggle(self._strict_btn.isChecked()))
        ly.addWidget(self._strict_btn)

        # Tolerance radius slider
        tol_label = QLabel("Tolerance: 0.15")
        ly.addWidget(tol_label)
        self._tol_slider = QSlider(Qt.Orientation.Horizontal)
        self._tol_slider.setRange(2, 50)  # 0.02 to 0.50
        self._tol_slider.setValue(15)      # default 0.15
        self._tol_slider.setTickInterval(5)
        self._tol_slider.setTickPosition(QSlider.TickPosition.TicksBelow)
        self._tol_slider.valueChanged.connect(
            lambda v: self._on_tolerance_change(v, tol_label)
        )
        ly.addWidget(self._tol_slider)

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

    def set_dark(self, dark: bool) -> None:
        """Update right-side panel for theme."""
        bg = "#1e1e21" if dark else "#fafafa"
        border = "#2a2a2e" if dark else "#ececec"
        fg = "#d0d0d5" if dark else "#555"
        btn_bg = "#2a2a2e" if dark else "#fff"
        btn_fg = "#d0d0d5" if dark else "#333"
        btn_border = "#3a3a3e" if dark else "#ddd"
        btn_hover_bg = "#3a3a50" if dark else "#eef3fb"
        btn_hover_border = "#5a6a7a" if dark else "#b9d2f1"
        sep_color = "#3a3a3e" if dark else "#e0e0e0"
        title_color = "#64b4ff" if dark else "#1a6bc0"
        combo_bg = "#2a2a2e" if dark else "#fff"
        combo_fg = "#e8e8ec" if dark else "#333"
        combo_border = "#3a3a3e" if dark else "#e0e0e0"
        text_bg = "#1a1a1e" if dark else "#fff"
        text_fg = "#d0d0d5" if dark else "#333"
        text_border = "#3a3a3e" if dark else "#eee"
        self.setStyleSheet(
            f"QFrame#hoverPanel {{ background: {bg}; border-left: 1px solid {border}; padding: 10px; }}"
            f"QLabel {{ font-size: 11px; color: {fg}; }}"
            f"QPushButton {{ background: {btn_bg}; color: {btn_fg}; border: 1px solid {btn_border}; border-radius: 4px; padding: 6px 10px; font-size: 11px; }}"
            f"QPushButton:hover {{ background: {btn_hover_bg}; border-color: {btn_hover_border}; }}"
        )
        # Section combo
        if hasattr(self, '_section_combo'):
            self._section_combo.setStyleSheet(
                f"QComboBox {{ background: {combo_bg}; color: {combo_fg}; border: 1px solid {combo_border}; border-radius: 6px; padding: 4px 10px; font-size: 12px; min-width: 120px; }}"
                f"QComboBox:hover {{ border-color: {btn_hover_border}; }}"
                f"QComboBox QAbstractItemView {{ background: {combo_bg}; color: {combo_fg}; selection-background-color: #3a3a50; }}"
            )
        # Cluster info text edit
        if hasattr(self, '_cluster_info'):
            self._cluster_info.setStyleSheet(
                f"QTextEdit {{ background: {text_bg}; color: {text_fg}; border: 1px solid {text_border}; border-radius: 4px; font-size: 10px; }}"
            )
        # SPATIAL 3D title
        for lbl in self.findChildren(QLabel):
            if lbl.text() == "SPATIAL 3D":
                lbl.setStyleSheet(f"font-size: 12px; font-weight: 800; color: {title_color}; padding-bottom: 4px;")
        # Separators
        for sep in self.findChildren(QFrame):
            if sep.frameShape() == QFrame.Shape.HLine:
                sep.setStyleSheet(f"border: none; border-top: 1px solid {sep_color};")

    def _on_tolerance_change(self, value, label):
        radius = value / 100.0
        label.setText(f"Tolerance: {radius:.2f}")
        self.tolerance_changed.emit(radius)

    def _on_strict_toggle(self, checked):
        self._strict_btn.setText("Strict Mode (ON)" if checked else "Strict Mode (OFF)")
        self.strict_toggled.emit(checked)

    def _set_mode(self, mode):
        self._mode_btn.setText("Explore" if mode == "explore" else "Analysis")
        self._mode_btn.setChecked(mode == "analysis")
        self.mode_changed.emit(mode)

    def _toggle_mode(self):
        if self._mode_btn.isChecked():
            self._set_mode("analysis")
        else:
            self._set_mode("explore")

    def _toggle_view(self):
        if self._view_btn.isChecked():
            self._view_btn.setText("Back")
            self.view_requested.emit("back")
        else:
            self._view_btn.setText("Front")
            self.view_requested.emit("front")

    def set_mode(self, mode):
        self._mode_btn.setText("Explore" if mode == "explore" else "Analysis")
        self._mode_btn.setChecked(mode == "analysis")

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

    def set_current_section(self, section_id):
        """Select a section without emitting signal."""
        self._section_combo.blockSignals(True)
        idx = self._section_combo.findText(section_id)
        if idx >= 0:
            self._section_combo.setCurrentIndex(idx)
        self._section_combo.blockSignals(False)


class ClusteringPage(QWidget):
    """Combined clustering page: Side-by-Side + Spatial 3D."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._mode = "sbs"
        self._collection = None
        self._res_root = None
        self._current_index = 0
        self._data_root = ""
        self._section_ids = []
        self._dark = False
        self._build_ui()

    def set_dark(self, dark: bool) -> None:
        self._dark = dark
        bg = "#1e1e21" if dark else "#fafafa"
        fg = "#d0d0d5" if dark else "#1a1a1a"
        self.setStyleSheet(f"ClusteringPage {{ background-color: {bg}; }}")
        if self._comparison_view:
            self._comparison_view.update_theme(dark)
        if self._spatial_viewer:
            try:
                self._spatial_viewer.set_dark(dark)
            except Exception:
                pass
        if self._hover_panel:
            self._hover_panel.set_dark(dark)

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
        self._comparison_view.section_changed.connect(self._on_sbs_section_changed)
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
            self._hover_panel.error_toggled.connect(self._on_error_toggle)
            self._hover_panel.tolerance_changed.connect(self._on_tolerance_change)
            self._hover_panel.strict_toggled.connect(self._on_strict_toggle)
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
            # Show current section in side-by-side
            if self._section_ids and self._current_index < len(self._section_ids):
                sid = self._section_ids[self._current_index]
                self._comparison_view.set_current_section(sid)
                self._comparison_view.show_overlay_pair(sid)
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
        # Sync side-by-side view
        if sid in self._section_ids:
            self._current_index = self._section_ids.index(sid)
        self._comparison_view.set_current_section(sid)
        self._comparison_view.show_overlay_pair(sid)

    def _on_hover_view(self, view):
        if self._spatial_viewer:
            if view == "front":
                self._spatial_viewer.view_front()
            else:
                self._spatial_viewer.view_back()

    def _on_error_toggle(self, show):
        if self._spatial_viewer:
            self._spatial_viewer.toggle_error_visibility(show)

    def _on_tolerance_change(self, radius):
        if self._spatial_viewer:
            self._spatial_viewer.set_tolerance(radius)

    def _on_strict_toggle(self, strict):
        if self._spatial_viewer:
            self._spatial_viewer.set_strict_mode(strict)

    # ----------------------------------------------------------------
    # Data loading
    # ----------------------------------------------------------------
    def load_data(self, collection, data_root="", section_ids=None, res_root=None):
        self._collection = collection
        self._data_root = data_root
        self._res_root = res_root
        self._section_ids = section_ids or []

        # Pass data roots to comparison view for overlay rendering
        self._comparison_view.set_data_roots(data_root, res_root or "")

        if collection and collection.pairs:
            ids = [p.section_id for p in collection.pairs]
            self._section_ids = ids
            self._current_index = 0

            # Show first section as overlay (tissue image + scatter points)
            first_sid = ids[0]
            self._comparison_view.show_overlay_pair(first_sid)

            # Populate section selectors in both views
            self._comparison_view.set_sections(self._section_ids)
            if self._hover_panel:
                self._hover_panel.set_sections(self._section_ids)

            # Load first section in spatial
            if self._mode == "spatial" and self._spatial_viewer:
                self._load_spatial(ids[0])
    def _on_sbs_section_changed(self, sid):
        """Handle section change from side-by-side view."""
        if sid in self._section_ids:
            self._current_index = self._section_ids.index(sid)
        # Update hover panel section combo
        if self._hover_panel and sid:
            self._hover_panel.set_current_section(sid)
        # Load overlay for the new section
        self._comparison_view.show_overlay_pair(sid)

    def _load_spatial(self, sid):
        if not HAS_SPATIAL or not self._spatial_viewer:
            return
        from spatial_viewer import load_results_dataset
        try:
            ds = load_spatial_dataset(str(self._data_root), sid)
        except Exception as e:
            logger.error("load_spatial_dataset failed for %s: %s", sid, e)
            return
        if ds is None:
            logger.warning("load_spatial_dataset returned None for %s (data_root=%s)", sid, self._data_root)
            return
        res_ds = None
        if self._res_root:
            try:
                res_ds = load_results_dataset(str(self._res_root), sid)
            except Exception as e:
                logger.error("load_results_dataset failed for %s: %s", sid, e)
        res_info = "%d cells" % len(res_ds.cells) if res_ds else "None"
        logger.info("3D spatial: %s GT=%d cells, Results=%s", sid, len(ds.cells), res_info)
        self._spatial_viewer.load_section(ds, results_dataset=res_ds)


    @property
    def comparison_view(self):
        return self._comparison_view
