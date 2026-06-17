"""ClustroView main window.

Layout (per ideal front-end image):
    [ Sidebar |  Scrollable right panel  ]
                  - Title row (Clustering Comparison + section selector)
                  - Visualization area (acrylic 3D panel + floating controls)
                  - Data area (5 tabs)

Themes: light by default, dark toggleable via sidebar.
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QPalette, QColor
from PySide6.QtWidgets import (
    QApplication, QComboBox, QFrame, QHBoxLayout, QLabel, QMainWindow,
    QMessageBox, QPushButton, QScrollArea, QSizePolicy, QStatusBar,
    QVBoxLayout, QWidget,
)

from model.image_manager import ImageCollection, ImagePair
from model.overlay_data import OverlayDataset
from utils.logger import logger
from view.comparison_view import ComparisonViewWidget
from view.data_area import DataAreaWidget
from view.overlay_3d_view import Overlay3DViewWidget
from view.sidebar import Sidebar


# ====================================================================
#  Palette
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
#  Styles for the right panel
# ====================================================================
_CONTENT_DARK = "background-color: #121214;"
_CONTENT_LIGHT = "background-color: #ffffff;"

_TITLE_LIGHT = "color: #1a1a1a; font-size: 24px; font-weight: 800;"
_TITLE_DARK = "color: #f5f5f7; font-size: 24px; font-weight: 800;"

_SUBTITLE_LIGHT = "color: #888; font-size: 12px;"
_SUBTITLE_DARK = "color: #8a8a90; font-size: 12px;"

_DROPDOWN_LIGHT = """
QComboBox {
    background: #ffffff; color: #1a1a1a;
    border: 1px solid #e0e0e0; border-radius: 6px;
    padding: 6px 12px; font-size: 12px;
    min-height: 22px;
}
QComboBox:hover { border-color: #b9d2f1; }
QComboBox::drop-down { border: none; width: 18px; }
QComboBox QAbstractItemView {
    background: #ffffff; color: #1a1a1a;
    border: 1px solid #e0e0e0; selection-background-color: #e3eefb;
    selection-color: #1a6bc0;
    padding: 4px;
}
"""

_DROPDOWN_DARK = """
QComboBox {
    background: #1e1e21; color: #f5f5f7;
    border: 1px solid #2a2a2e; border-radius: 6px;
    padding: 6px 12px; font-size: 12px;
    min-height: 22px;
}
QComboBox:hover { border-color: rgba(100,180,255,0.5); }
QComboBox::drop-down { border: none; width: 18px; }
QComboBox QAbstractItemView {
    background: #1e1e21; color: #f5f5f7;
    border: 1px solid #2a2a2e; selection-background-color: rgba(100,180,255,0.25);
    padding: 4px;
}
"""

_MODE_BTN_LIGHT = """
QPushButton {
    font-size: 11px; padding: 5px 10px; border: 1px solid #e0e0e0;
    border-radius: 5px; background: #ffffff; color: #555;
}
QPushButton:hover { background: #eef3fb; border-color: #b9d2f1; color: #1a6bc0; }
QPushButton:checked {
    background: #e3eefb; border-color: #5b8fd9; color: #1a6bc0; font-weight: 600;
}
"""

_MODE_BTN_DARK = """
QPushButton {
    font-size: 11px; padding: 5px 10px; border: 1px solid #2a2a2e;
    border-radius: 5px; background: #1e1e21; color: #c0c0c5;
}
QPushButton:hover { background: rgba(100,180,255,0.10); color: #f5f5f7; }
QPushButton:checked {
    background: rgba(100,180,255,0.20); border-color: rgba(100,180,255,0.40);
    color: #f5f5f7; font-weight: 600;
}
"""

_NOTICE_LIGHT = """
QFrame#notice {
    background: #fff7e6; border: 1px solid #ffe7ba;
    border-radius: 6px;
}
QLabel#noticeText { color: #ad6800; font-size: 11px; }
"""

_NOTICE_DARK = """
QFrame#notice {
    background: rgba(245, 154, 35, 0.12); border: 1px solid rgba(245, 154, 35, 0.4);
    border-radius: 6px;
}
QLabel#noticeText { color: #f5b04a; font-size: 11px; }
"""


# ====================================================================
#  Main window
# ====================================================================
class MainWindow(QMainWindow):
    def __init__(self, controller=None):
        super().__init__()
        self._controller = controller
        self._collection: Optional[ImageCollection] = None
        self._overlay_datasets: list[OverlayDataset] = []
        self._current_index: int = 0
        self._dark_theme: bool = False
        self._is_3dflip_mode: bool = True  # default per spec

        self.setWindowTitle("ClustroView - Clustering Comparison")
        self.setMinimumSize(1180, 760)

        # Cache for image paths of the current section
        self._gt_image_path: Optional[str] = None
        self._pred_image_path: Optional[str] = None

        # Lazy-loading debounce
        self._lazy = QTimer(self)
        self._lazy.setSingleShot(True)
        self._lazy.setInterval(120)
        self._lazy.timeout.connect(self._on_lazy)

        self._build_ui()
        self._apply_widget_theme(False)

    # ================================================================
    #  UI build
    # ================================================================
    def _build_ui(self) -> None:
        central = QWidget()
        self.setCentralWidget(central)
        root = QHBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ---- Sidebar ----
        self._sidebar = Sidebar(
            active_key="clustering",
            on_theme_toggle=self._toggle_theme,
            theme_is_dark=self._dark_theme,
        )
        self._sidebar.module_selected.connect(self._on_module_selected)
        root.addWidget(self._sidebar)

        # ---- Right scrollable panel ----
        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setFrameShape(QFrame.Shape.NoFrame)
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        self._content = QWidget()
        self._content.setStyleSheet(_CONTENT_LIGHT)
        cl = QVBoxLayout(self._content)
        cl.setContentsMargins(24, 20, 24, 20)
        cl.setSpacing(12)

        self._build_title_row(cl)
        self._build_visualization_area(cl)
        self._build_data_area(cl)
        cl.addStretch()

        self._scroll.setWidget(self._content)
        root.addWidget(self._scroll, 1)

        # Status bar
        self._qt_status = QStatusBar()
        self.setStatusBar(self._qt_status)

    def _build_title_row(self, parent_layout: QVBoxLayout) -> None:
        row = QHBoxLayout()
        row.setSpacing(8)

        # Title + subtitle (left)
        title_col = QVBoxLayout()
        title_col.setSpacing(2)
        self._title_label = QLabel("Clustering Comparison")
        self._title_label.setStyleSheet(_TITLE_LIGHT)
        self._subtitle_label = QLabel("Compare ground truth vs prediction results")
        self._subtitle_label.setStyleSheet(_SUBTITLE_LIGHT)
        title_col.addWidget(self._title_label)
        title_col.addWidget(self._subtitle_label)
        row.addLayout(title_col, 1)

        # Mode toggle (Side-by-Side / 3D Flip) - small, top right
        self._btn_sbs = QPushButton("Side-by-Side")
        self._btn_sbs.setCheckable(True)
        self._btn_sbs.setCursor(Qt.CursorShape.PointingHandCursor)
        self._btn_sbs.setStyleSheet(_MODE_BTN_LIGHT)
        self._btn_sbs.clicked.connect(lambda: self._set_mode(False))

        self._btn_3df = QPushButton("3D Flip")
        self._btn_3df.setCheckable(True)
        self._btn_3df.setChecked(True)
        self._btn_3df.setCursor(Qt.CursorShape.PointingHandCursor)
        self._btn_3df.setStyleSheet(_MODE_BTN_LIGHT)
        self._btn_3df.clicked.connect(lambda: self._set_mode(True))

        mode_box = QHBoxLayout()
        mode_box.setSpacing(4)
        mode_box.addWidget(self._btn_sbs)
        mode_box.addWidget(self._btn_3df)
        row.addLayout(mode_box)

        # Dataset + section dropdowns
        self._dataset_combo = QComboBox()
        self._dataset_combo.addItem("DLPFC")
        self._dataset_combo.setFixedWidth(96)
        self._dataset_combo.setStyleSheet(_DROPDOWN_LIGHT)
        self._dataset_combo.setCursor(Qt.CursorShape.PointingHandCursor)

        self._section_combo = QComboBox()
        self._section_combo.setFixedWidth(110)
        self._section_combo.setStyleSheet(_DROPDOWN_LIGHT)
        self._section_combo.setCursor(Qt.CursorShape.PointingHandCursor)
        self._section_combo.currentIndexChanged.connect(self._on_section_changed)

        row.addSpacing(8)
        row.addWidget(self._dataset_combo)
        row.addWidget(self._section_combo)

        parent_layout.addLayout(row)

        # Notice bar (for fallback / missing-pred)
        self._notice = QFrame()
        self._notice.setObjectName("notice")
        self._notice.setStyleSheet(_NOTICE_LIGHT)
        self._notice.setVisible(False)
        nl = QHBoxLayout(self._notice)
        nl.setContentsMargins(10, 6, 10, 6)
        self._notice_label = QLabel("")
        self._notice_label.setObjectName("noticeText")
        self._notice_label.setStyleSheet("color: #ad6800; font-size: 11px;")
        nl.addWidget(self._notice_label)
        nl.addStretch()
        parent_layout.addWidget(self._notice)

    def _build_visualization_area(self, parent_layout: QVBoxLayout) -> None:
        # Side-by-side widget (hidden by default)
        self._comparison_widget = ComparisonViewWidget()
        self._comparison_widget.setMinimumHeight(420)
        self._comparison_widget.setVisible(False)

        # 3D Flip widget (default)
        self._view_3d = Overlay3DViewWidget()
        self._view_3d.setMinimumHeight(420)
        self._view_3d.setVisible(True)

        parent_layout.addWidget(self._view_3d, 0)
        parent_layout.addWidget(self._comparison_widget, 0)

    def _build_data_area(self, parent_layout: QVBoxLayout) -> None:
        self._data_area = DataAreaWidget(dark=self._dark_theme)
        parent_layout.addWidget(self._data_area, 0)

    # ================================================================
    #  Mode
    # ================================================================
    def _set_mode(self, is_3dflip: bool) -> None:
        self._is_3dflip_mode = is_3dflip
        self._btn_sbs.setChecked(not is_3dflip)
        self._btn_3df.setChecked(is_3dflip)
        self._view_3d.setVisible(is_3dflip)
        self._comparison_widget.setVisible(not is_3dflip)
        self._refresh_current()

    def _refresh_current(self) -> None:
        """Re-render the currently-selected section in the active view mode."""
        if self._is_3dflip_mode:
            if self._overlay_datasets and 0 <= self._current_index < len(self._overlay_datasets):
                self._show_overlay_at(self._current_index)
            else:
                self._view_3d.show_no_data()
        else:
            if self._collection and self._collection.pairs and 0 <= self._current_index < len(self._collection.pairs):
                self._show_image(self._current_index)
            else:
                self._comparison_widget.show_no_data()

    # ================================================================
    #  Theme
    # ================================================================
    def _toggle_theme(self) -> None:
        self._dark_theme = not self._dark_theme
        self._apply_widget_theme(self._dark_theme)
        self._sidebar.set_dark(self._dark_theme)
        self._view_3d.update_theme(self._dark_theme)
        self._data_area.set_dark(self._dark_theme)
        self._comparison_widget.update_theme(self._dark_theme)

    def _apply_widget_theme(self, dark: bool) -> None:
        apply_theme(dark)
        self._title_label.setStyleSheet(_TITLE_DARK if dark else _TITLE_LIGHT)
        self._subtitle_label.setStyleSheet(_SUBTITLE_DARK if dark else _SUBTITLE_LIGHT)
        self._content.setStyleSheet(_CONTENT_DARK if dark else _CONTENT_LIGHT)
        self._scroll.setStyleSheet(
            f"QScrollArea {{ border: none; background-color: "
            f"{'#121214' if dark else '#ffffff'}; }}"
        )
        self._dataset_combo.setStyleSheet(_DROPDOWN_DARK if dark else _DROPDOWN_LIGHT)
        self._section_combo.setStyleSheet(_DROPDOWN_DARK if dark else _DROPDOWN_LIGHT)
        mb = _MODE_BTN_DARK if dark else _MODE_BTN_LIGHT
        self._btn_sbs.setStyleSheet(mb); self._btn_3df.setStyleSheet(mb)
        self._notice.setStyleSheet(_NOTICE_DARK if dark else _NOTICE_LIGHT)
        self._notice_label.setStyleSheet(
            "color: #f5b04a; font-size: 11px;" if dark else
            "color: #ad6800; font-size: 11px;"
        )

    # ================================================================
    #  Sidebar module selection
    # ================================================================
    def _on_module_selected(self, key: str) -> None:
        if key == "clustering":
            return
        # All other modules: not implemented yet
        QMessageBox.information(
            self,
            "Module not implemented",
            f"The module \"{key}\" is part of the ClustroView platform navigation\n"
            f"but is not yet implemented. Only the Clustering Comparison page is\n"
            f"available in this build.",
        )

    # ================================================================
    #  Public API used by controller
    # ================================================================
    def set_controller(self, c) -> None:
        self._controller = c

    def set_collection(self, coll: ImageCollection) -> None:
        self._collection = coll
        ids = [p.section_id for p in coll.pairs]
        self._section_combo.blockSignals(True)
        self._section_combo.clear()
        if ids:
            self._section_combo.addItems(ids)
        self._section_combo.blockSignals(False)
        if not coll.pairs:
            self._view_3d.show_no_data()
            self._comparison_widget.show_no_data()
            self._data_area.update_dataset(None)
            self._show_notice("No image pairs found in DLPFC_result/")
            return
        self._current_index = 0
        self._section_combo.setCurrentIndex(0)
        self._refresh_current()

    def set_overlay_datasets(self, datasets: list[OverlayDataset]) -> None:
        self._overlay_datasets = datasets

    def show_overlay_dataset(self, ds: OverlayDataset, idx: int) -> None:
        self._current_index = idx
        # Section combo is already in sync (controller drives it)
        self._show_overlay_at(idx)

    def show_image(self, idx: int) -> None:
        self._show_image(idx)

    def show_status_message(self, msg: str, timeout: int = 4000) -> None:
        self._qt_status.showMessage(msg, timeout)

    def show_mismatched_points_tab(self) -> None:
        self._data_area.show_mismatched_points()

    # ================================================================
    #  Internal: show data
    # ================================================================
    def _show_overlay_at(self, idx: int) -> None:
        if not (0 <= idx < len(self._overlay_datasets)):
            return
        self._current_index = idx
        ds = self._overlay_datasets[idx]
        gt_path, pred_path = self._resolve_image_paths(ds.section_id)
        self._gt_image_path = gt_path
        self._pred_image_path = pred_path
        # If the pred image is missing, show the notice
        if pred_path is None:
            self._show_notice(
                f"Prediction image for {ds.section_id} is missing. "
                f"Showing GT on both sides."
            )
        else:
            self._hide_notice()
        # If the dataset has no pred column either, also show the notice
        if not ds.has_pred:
            self._show_notice(
                f"No prediction column found in metadata for {ds.section_id}. "
                f"Showing GT only."
            )
        self._view_3d.set_dataset(ds)
        self._data_area.update_dataset(ds)

    def _show_image(self, idx: int) -> None:
        if not self._collection or not self._collection.pairs:
            return
        if not (0 <= idx < len(self._collection.pairs)):
            return
        self._current_index = idx
        p = self._collection.pairs[idx]
        if self._collection.fallback_mode or p.pred_missing:
            self._comparison_widget.show_fallback(p)
        else:
            self._comparison_widget.show_pair(p)
        self._section_combo.blockSignals(True)
        self._section_combo.setCurrentIndex(idx)
        self._section_combo.blockSignals(False)

    def _resolve_image_paths(self, section_id: str) -> tuple[Optional[str], Optional[str]]:
        """Find GT and Pred PNG paths for a section (matches the image_manager
        layout)."""
        if self._controller is None or self._collection is None:
            return None, None
        for pair in self._collection.pairs:
            if pair.section_id == section_id:
                gt = str(pair.gt_path) if pair.gt_path else None
                pr = str(pair.pred_path) if (pair.pred_path and not pair.pred_missing) else None
                return gt, pr
        return None, None

    # ================================================================
    #  Internal: notice bar
    # ================================================================
    def _show_notice(self, text: str) -> None:
        self._notice_label.setText(text)
        self._notice.setVisible(True)

    def _hide_notice(self) -> None:
        self._notice.setVisible(False)

    # ================================================================
    #  Internal: section change
    # ================================================================
    def _on_section_changed(self, idx: int) -> None:
        self._lazy.start()

    def _on_lazy(self) -> None:
        idx = self._section_combo.currentIndex()
        if idx < 0:
            return
        self._current_index = idx
        self._refresh_current()
        if self._controller is not None:
            self._controller.on_section_changed(idx)
