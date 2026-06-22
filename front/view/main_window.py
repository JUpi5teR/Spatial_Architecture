"""ClustroView main window.

Layout (per ideal front-end image):
    [ Sidebar |  QStackedWidget module pages ]
                  - Page 0: Clustering (3D Spatial / Side-by-Side)
                  - Pages 1+: Overview, Upload, Datasets, etc.

Themes: light by default, dark toggleable via sidebar.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QPalette, QColor
from PySide6.QtWidgets import (
    QApplication, QComboBox, QFrame, QHBoxLayout, QLabel, QMainWindow,
    QMessageBox, QPushButton, QScrollArea, QSizePolicy, QStackedWidget, QStatusBar,
    QTextEdit, QVBoxLayout, QWidget,
)

from model.image_manager import ImageCollection, ImagePair
from model.overlay_data import OverlayDataset
from utils.logger import logger
from model.data_path import DataPathManager
from view.upload_view import UploadViewWidget
from view.statistics_view import StatisticsViewWidget
from view.plots_view import PlotsViewWidget
from view.heatmap_view import HeatmapViewWidget
from view.comparison_view import ComparisonViewWidget
from view.data_area import DataAreaWidget
from spatial_viewer import SpatialViewerWidget, load_spatial_dataset, SECTION_IDS as SPATIAL_SECTION_IDS
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
# _CONTENT_DARK = "background-color: #121214;"  # unused after module stack
# _CONTENT_LIGHT = "background-color: #ffffff;"  # unused after module stack

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

class HoverPanel(QFrame):
    """Panel for cluster info and controls. Supports light/dark theme."""
    section_changed = Signal(str)
    mode_changed = Signal(str)
    view_requested = Signal(str)

    _DARK_SS = """
        HoverPanel {
            background: rgba(30,30,35,0.92);
            border: 1px solid rgba(255,255,255,0.10);
            border-radius: 10px;
        }
        QLabel { color: #c8c8cc; font-size: 10px; }
        QLabel#title { font-size: 13px; font-weight: 700; color: #e8e8ec; padding: 2px 0; }
        QLabel#mode_label { font-size: 11px; font-weight: 600; padding: 2px 0; }
        QPushButton {
            font-size: 10px; padding: 5px 8px; border-radius: 5px;
            border: 1px solid rgba(255,255,255,0.12); color: #d0d0d5;
            background: rgba(255,255,255,0.06);
        }
        QPushButton:hover { background: rgba(100,180,255,0.15); }
        QComboBox {
            padding: 4px; font-size: 10px; color: #d0d0d5;
            border: 1px solid rgba(255,255,255,0.12); border-radius: 4px;
            background: rgba(255,255,255,0.06);
        }
        QComboBox QAbstractItemView {
            background: #1e1e21; color: #d0d0d5;
            border: 1px solid rgba(255,255,255,0.12);
            selection-background-color: rgba(100,180,255,0.25);
        }
        QTextEdit {
            background: rgba(255,255,255,0.06); color: #c8c8cc;
            border: 1px solid rgba(255,255,255,0.08); border-radius: 6px;
            padding: 6px; font-size: 10px;
        }
        QLabel#info_title { font-size: 10px; font-weight: 600; color: #999; padding: 4px 0 2px 0; }
    """

    _LIGHT_SS = """
        HoverPanel {
            background: rgba(255,255,255,0.95);
            border: 1px solid rgba(0,0,0,0.08);
            border-radius: 10px;
        }
        QLabel { color: #555; font-size: 10px; }
        QLabel#title { font-size: 13px; font-weight: 700; color: #222; padding: 2px 0; }
        QLabel#mode_label { font-size: 11px; font-weight: 600; padding: 2px 0; }
        QPushButton {
            font-size: 10px; padding: 5px 8px; border-radius: 5px;
            border: 1px solid #d0d0d5; color: #444;
            background: #f5f5f7;
        }
        QPushButton:hover { background: #e3eefb; border-color: #b9d2f1; }
        QComboBox {
            padding: 4px; font-size: 10px; color: #333;
            border: 1px solid #d0d0d5; border-radius: 4px;
            background: #f5f5f7;
        }
        QComboBox QAbstractItemView {
            background: #ffffff; color: #333;
            border: 1px solid #d0d0d5;
            selection-background-color: #e3eefb;
        }
        QTextEdit {
            background: #f9f9fb; color: #444;
            border: 1px solid #e0e0e3; border-radius: 6px;
            padding: 6px; font-size: 10px;
        }
        QLabel#info_title { font-size: 10px; font-weight: 600; color: #888; padding: 4px 0 2px 0; }
    """

    def __init__(self, parent=None, dark: bool = False):
        super().__init__(parent)
        self._dark = dark
        self.setFixedWidth(220)
        self._apply_theme()
        self._build()

    def _apply_theme(self):
        self.setStyleSheet(self._DARK_SS if self._dark else self._LIGHT_SS)

    def set_dark(self, dark: bool):
        self._dark = dark
        self._apply_theme()

    def _build(self):
        lay = QVBoxLayout(self)
        lay.setContentsMargins(12, 10, 12, 10)
        lay.setSpacing(4)

        t = QLabel("Spatial Viewer")
        t.setObjectName("title")
        lay.addWidget(t)

        self._section_combo = QComboBox()
        self._section_combo.addItems(SPATIAL_SECTION_IDS)
        self._section_combo.currentTextChanged.connect(self.section_changed.emit)
        lay.addWidget(self._section_combo)

        self._mode_label = QLabel("Explore")
        self._mode_label.setObjectName("mode_label")
        self._mode_label.setStyleSheet("color:#1a6bc0;" if not self._dark else "color:#64b4ff;")
        lay.addWidget(self._mode_label)

        self._enter_btn = QPushButton("Analysis Mode")
        self._enter_btn.clicked.connect(lambda: self.mode_changed.emit("analysis"))
        lay.addWidget(self._enter_btn)

        self._exit_btn = QPushButton("Exit Analysis")
        self._exit_btn.clicked.connect(lambda: self.mode_changed.emit("explore"))
        self._exit_btn.setVisible(False)
        lay.addWidget(self._exit_btn)

        fv = QPushButton("Front View")
        fv.clicked.connect(lambda: self.view_requested.emit("front"))
        lay.addWidget(fv)

        bv = QPushButton("Back View")
        bv.clicked.connect(lambda: self.view_requested.emit("back"))
        lay.addWidget(bv)

        il = QLabel("Cluster Info")
        il.setObjectName("info_title")
        lay.addWidget(il)
        self._cluster_info = QTextEdit()
        self._cluster_info.setReadOnly(True)
        self._cluster_info.setMinimumHeight(100)
        self._cluster_info.setMaximumHeight(140)
        self._cluster_info.setPlaceholderText("Hover in Analysis mode")
        lay.addWidget(self._cluster_info)

    def set_mode(self, mode: str):
        a_color = "#ff7a45" if self._dark else "#d4380d"
        e_color = "#64b4ff" if self._dark else "#1a6bc0"
        if mode == "analysis":
            self._mode_label.setText("Analysis")
            self._mode_label.setStyleSheet(f"color:{a_color}; font-weight:700; font-size:11px;")
            self._enter_btn.setVisible(False)
            self._exit_btn.setVisible(True)
        else:
            self._mode_label.setText("Explore")
            self._mode_label.setStyleSheet(f"color:{e_color}; font-weight:700; font-size:11px;")
            self._enter_btn.setVisible(True)
            self._exit_btn.setVisible(False)

    def set_cluster_info(self, cluster: str, count: int, meta: dict):
        items = "".join(f"<b>{k}</b>: {v}<br>" for k, v in meta.items())
        info = f"<b>Cluster:</b> {cluster}<br><b>Cells:</b> {count}<br><br>{items}"
        self._cluster_info.setHtml(info)
class MainWindow(QMainWindow):
    def __init__(self, controller=None):
        super().__init__()
        self._controller = controller
        self._collection: Optional[ImageCollection] = None
        self._overlay_datasets: list[OverlayDataset] = []
        self._current_index: int = 0
        self._dark_theme: bool = False
        self._is_3dflip_mode: bool = True  # default per spec

        # ---- Data path & sub-page widgets ----
        self._path_mgr = DataPathManager()
        self._upload_widget: Any = None
        self._statistics_widget: Any = None
        self._plots_widget: Any = None
        self._heatmap_widget: Any = None
        self._no_path_overlay: Any = None
        self._spatial_mode: bool = False  # spatial viewer mode
        self._view_mode: str = "spatial"  # sbs / spatial
        self._module_data: dict[str, dict] = {}  # module page metadata for theming

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
        # Default to Spatial 3D mode
        self._set_view_mode("spatial")

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

        # ---- Module pages stack ----
        self._module_stack = QStackedWidget()
        self._module_index = {"clustering": 0}
        self._module_pages = {}

        # Page 0: Clustering (existing content, unchanged)
        self._clustering_page = QWidget()
        cl = QVBoxLayout(self._clustering_page)
        cl.setContentsMargins(24, 20, 24, 20)
        cl.setSpacing(12)
        self._build_title_row(cl)
        self._build_visualization_area(cl)
        self._build_data_area(cl)
        cl.addStretch()
        self._module_stack.addWidget(self._clustering_page)

        # Pages 1+: other modules
        _MODULE_PAGES = [
            ("overview", "Overview", "⌂", "Dataset overview and summary statistics."),
            ("datasets", "Datasets", "▤", "Browse and manage available datasets."),
            ("preprocessing", "Preprocessing", "⚙", "Data preprocessing and quality control."),
            ("marker_genes", "Marker Genes", "⚗", "Identify differentially expressed marker genes."),
            ("dimensionality", "Dimensionality", "∿", "Dimensionality reduction methods: PCA, t-SNE, UMAP."),
            ("trajectory", "Trajectory", "⤳", "Trajectory inference and pseudotime analysis."),
            ("comparison", "Comparison", "⊕", "Compare results across multiple analyses."),
        ]
        for i, (key, title, icon, desc) in enumerate(_MODULE_PAGES, start=1):
            page, meta = self._create_module_page(title, icon, desc)
            self._module_stack.addWidget(page)
            self._module_index[key] = i
            self._module_pages[key] = page
            self._module_data[key] = meta

        self._module_stack.setCurrentIndex(0)

        # ---- Upload Data page (custom widget) ----
        upload_idx = len(_MODULE_PAGES) + 1
        self._upload_widget = UploadViewWidget(self._path_mgr)
        self._upload_widget.folder_registered.connect(self._on_folder_registered)
        self._module_stack.addWidget(self._upload_widget)
        self._module_index["upload"] = upload_idx
        self._module_pages["upload"] = self._upload_widget

        # ---- Statistics page (custom widget) ----
        stat_idx = upload_idx + 1
        self._statistics_widget = StatisticsViewWidget(self._path_mgr)
        self._module_stack.addWidget(self._statistics_widget)
        self._module_index["statistics"] = stat_idx
        self._module_pages["statistics"] = self._statistics_widget

        # ---- Plots page (custom widget) ----
        plots_idx = stat_idx + 1
        self._plots_widget = PlotsViewWidget(self._path_mgr)
        self._module_stack.addWidget(self._plots_widget)
        self._module_index["plots"] = plots_idx
        self._module_pages["plots"] = self._plots_widget

        # ---- Heatmap page (custom widget) ----
        heat_idx = plots_idx + 1
        self._heatmap_widget = HeatmapViewWidget(self._path_mgr)
        self._module_stack.addWidget(self._heatmap_widget)
        self._module_index["heatmaps"] = heat_idx
        self._module_pages["heatmaps"] = self._heatmap_widget

        self._scroll.setWidget(self._module_stack)

        # ---- No-path overlay ----
        self._no_path_overlay = QLabel(
            "\u26A0  \u8BF7\u5148\u4E0A\u4F20\u6587\u4EF6\u5939\n\n"
            "\u8BF7\u5207\u6362\u5230 Upload Data \u9875\u9762\uFF0C\u9009\u62E9\u6570\u636E\u4E3B\u6587\u4EF6\u5939\u3002\n"
            "\u652F\u6301\u76F4\u63A5\u9009\u62E9\u6587\u4EF6\u5939\u6216\u4E0A\u4F20 .zip \u538B\u7F29\u5305\u3002"
        )
        self._no_path_overlay.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._no_path_overlay.setStyleSheet("color: #888; font-size: 18px; background: #fafafa;")
        self._no_path_overlay.setWordWrap(True)

        self._body_stack = QStackedWidget()
        self._body_stack.addWidget(self._scroll)
        self._body_stack.addWidget(self._no_path_overlay)
        self._body_stack.setCurrentIndex(0)

        root.addWidget(self._body_stack, 1)

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

        # Mode toggle (Side-by-Side / Spatial 3D) - top right
        self._btn_sbs = QPushButton("Side-by-Side")
        self._btn_sbs.setCheckable(True)
        self._btn_sbs.setChecked(False)
        self._btn_sbs.setCursor(Qt.CursorShape.PointingHandCursor)
        self._btn_sbs.setStyleSheet(_MODE_BTN_LIGHT)
        self._btn_sbs.clicked.connect(lambda: self._set_view_mode("sbs"))

        self._btn_spatial = QPushButton("Spatial 3D")
        self._btn_spatial.setCheckable(True)
        self._btn_spatial.setChecked(True)
        self._btn_spatial.setCursor(Qt.CursorShape.PointingHandCursor)
        self._btn_spatial.setStyleSheet(_MODE_BTN_LIGHT)
        self._btn_spatial.clicked.connect(lambda: self._set_view_mode("spatial"))

        mode_box = QHBoxLayout()
        mode_box.setSpacing(4)
        mode_box.addWidget(self._btn_sbs)
        mode_box.addWidget(self._btn_spatial)
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
        self._comparison_widget.setFixedHeight(550)
        self._comparison_widget.setVisible(False)

        # ---- Spatial viewer with floating hover panel ----
        self._view_3d_container = QWidget()
        self._view_3d_container.setMinimumHeight(420)
        self._view_3d_container.setVisible(False)
        sv_layout = QHBoxLayout(self._view_3d_container)
        sv_layout.setContentsMargins(0, 0, 0, 0)
        sv_layout.setSpacing(0)

        self._spatial_viewer = SpatialViewerWidget()
        self._spatial_viewer.setMinimumHeight(420)
        sv_layout.addWidget(self._spatial_viewer, 1)

        self._hover_panel = HoverPanel(dark=self._dark_theme)
        self._hover_panel.setFixedWidth(220)
        sv_layout.addWidget(self._hover_panel, 0)

        # Connect signals
        self._hover_panel.section_changed.connect(self._on_spatial_section)
        self._hover_panel.mode_changed.connect(self._on_spatial_mode)
        self._hover_panel.view_requested.connect(self._on_spatial_view)
        self._spatial_viewer.cluster_hovered.connect(self._hover_panel.set_cluster_info)

        parent_layout.addWidget(self._comparison_widget, 0)
        parent_layout.addWidget(self._view_3d_container, 0)

    def _build_data_area(self, parent_layout: QVBoxLayout) -> None:
        self._data_area = DataAreaWidget(dark=self._dark_theme)
        parent_layout.addWidget(self._data_area, 0)

    # ================================================================
    #  Mode
    # ================================================================
    def _set_view_mode(self, mode: str) -> None:
        """Switch between sbs (side-by-side) and spatial modes."""
        self._spatial_mode = (mode == "spatial")
        self._is_3dflip_mode = (mode == "spatial")  # True for spatial, False for sbs
        self._view_mode = mode

        self._comparison_widget.setVisible(mode == "sbs")
        self._view_3d_container.setVisible(mode == "spatial")

        self._btn_sbs.setChecked(mode == "sbs")
        self._btn_spatial.setChecked(mode == "spatial")

        if mode == "spatial":
            # Load current section in spatial viewer
            sid = self._section_combo.currentText()
            if not sid and self._hover_panel._section_combo.count() > 0:
                sid = self._hover_panel._section_combo.itemText(0)
            if sid:
                self._on_spatial_section(sid)
        else:
            self._refresh_current()

    def _refresh_current(self) -> None:
        """Re-render the currently-selected section in the active view mode."""
        if self._spatial_mode:
            return
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
        self._data_area.set_dark(self._dark_theme)
        self._comparison_widget.update_theme(self._dark_theme)
        self._hover_panel.set_dark(self._dark_theme)
        self._spatial_viewer.set_dark(self._dark_theme)

    def _apply_widget_theme(self, dark: bool) -> None:
        apply_theme(dark)
        self._title_label.setStyleSheet(_TITLE_DARK if dark else _TITLE_LIGHT)
        self._subtitle_label.setStyleSheet(_SUBTITLE_DARK if dark else _SUBTITLE_LIGHT)
        self._scroll.setStyleSheet(
            f"QScrollArea {{ border: none; background-color: "
            f"{'#121214' if dark else '#ffffff'}; }}"
        )
        self._dataset_combo.setStyleSheet(_DROPDOWN_DARK if dark else _DROPDOWN_LIGHT)
        self._section_combo.setStyleSheet(_DROPDOWN_DARK if dark else _DROPDOWN_LIGHT)
        mb = _MODE_BTN_DARK if dark else _MODE_BTN_LIGHT
        self._btn_sbs.setStyleSheet(mb); self._btn_spatial.setStyleSheet(mb)
        self._notice.setStyleSheet(_NOTICE_DARK if dark else _NOTICE_LIGHT)
        self._notice_label.setStyleSheet(
            "color: #f5b04a; font-size: 11px;" if dark else
            "color: #ad6800; font-size: 11px;"
        )
        self._comparison_widget.update_theme(dark)
        # Update module pages theme
        _ICON_C = "#64b4ff" if dark else "#1a6bc0"
        _TITLE_C = "#f5f5f7" if dark else "#1a1a1a"
        _DESC_C = "#8a8a90" if dark else "#888"
        _INFO_C = "#8a8a90" if dark else "#666"
        _SEP_C = "#2a2a2e" if dark else "#ececec"
        _CA_BG = "#1a1a1e" if dark else "#fafafa"
        _CA_BD = "#2a2a2e" if dark else "#ececec"
        _PAGE_BG = "#121214" if dark else "#ffffff"
        for key, meta in self._module_data.items():
            meta["icon"].setStyleSheet(f"font-size: 28px; color: {_ICON_C};")
            meta["title"].setStyleSheet(f"color: {_TITLE_C}; font-size: 24px; font-weight: 800;")
            meta["desc"].setStyleSheet(f"color: {_DESC_C}; font-size: 13px;")
            meta["info"].setStyleSheet(f"color: {_INFO_C}; font-size: 12px;")
            meta["sep"].setStyleSheet(f"background: {_SEP_C}; max-height: 1px; min-height: 1px;")
            meta["content"].setStyleSheet(f"""
QFrame#moduleContent {{
    background: {_CA_BG};
    border: 1px solid {_CA_BD};
    border-radius: 8px;
}}
""")
            meta["page"].setStyleSheet(f"background-color: {_PAGE_BG};")

    # ================================================================
    #  Module pages
    # ================================================================
    def _create_module_page(self, title: str, icon: str, description: str):
        """Create a consistent-styled module page with icon, title, description and content area."""
        dark = self._dark_theme
        page = QWidget()
        bg = "#121214" if dark else "#ffffff"
        page.setStyleSheet(f"background-color: {bg};")
        layout = QVBoxLayout(page)
        layout.setContentsMargins(40, 40, 40, 40)
        layout.setSpacing(16)

        # Icon + Title row
        title_row = QHBoxLayout()
        title_row.setSpacing(12)

        icon_label = QLabel(icon)
        icon_lb_color = "#64b4ff" if dark else "#1a6bc0"
        icon_label.setStyleSheet(f"font-size: 28px; color: {icon_lb_color};")
        icon_label.setFixedSize(44, 44)
        icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title_row.addWidget(icon_label)

        text_col = QVBoxLayout()
        text_col.setSpacing(4)
        title_lb = QLabel(title)
        title_c = "#f5f5f7" if dark else "#1a1a1a"
        title_lb.setStyleSheet(f"color: {title_c}; font-size: 24px; font-weight: 800;")
        text_col.addWidget(title_lb)

        desc_lb = QLabel(description)
        desc_c = "#8a8a90" if dark else "#888"
        desc_lb.setStyleSheet(f"color: {desc_c}; font-size: 13px;")
        desc_lb.setWordWrap(True)
        text_col.addWidget(desc_lb)

        title_row.addLayout(text_col, 1)
        layout.addLayout(title_row)

        # Separator
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep_c = "#2a2a2e" if dark else "#ececec"
        sep.setStyleSheet(f"background: {sep_c}; max-height: 1px; min-height: 1px;")
        layout.addWidget(sep)

        # Content area
        content_area = QFrame()
        content_area.setObjectName("moduleContent")
        ca_bg = "#1a1a1e" if dark else "#fafafa"
        ca_bd = "#2a2a2e" if dark else "#ececec"
        content_area.setStyleSheet(f"""
QFrame#moduleContent {{
    background: {ca_bg};
    border: 1px solid {ca_bd};
    border-radius: 8px;
}}
""")
        content_ly = QVBoxLayout(content_area)
        content_ly.setContentsMargins(20, 20, 20, 20)

        info = QLabel(f"The {title} module is ready. Configure your analysis parameters and run workflows from this page.")
        info_c = "#8a8a90" if dark else "#666"
        info.setStyleSheet(f"color: {info_c}; font-size: 12px;")
        info.setWordWrap(True)
        content_ly.addWidget(info)
        content_ly.addStretch()

        layout.addWidget(content_area, 1)

        meta = {
            "icon": icon_label,
            "title": title_lb,
            "desc": desc_lb,
            "sep": sep,
            "content": content_area,
            "info": info,
            "page": page,
        }
        return page, meta

    # ================================================================
    #  Sidebar module selection
    # ================================================================
    def _on_module_selected(self, key: str) -> None:
        idx = self._module_index.get(key)
        if idx is None:
            return

        has_path = self._controller is not None and self._controller.has_data_path()
        if key == "upload":
            self._body_stack.setCurrentIndex(0)
            self._module_stack.setCurrentIndex(idx)
        elif not has_path:
            self._no_path_overlay.setText(
                "\u26A0  \u8BF7\u5148\u4E0A\u4F20\u6587\u4EF6\u5939\n\n"
                "\u8BF7\u5207\u6362\u5230 Upload Data \u9875\u9762\uFF0C\u9009\u62E9\u6570\u636E\u4E3B\u6587\u4EF6\u5939\u3002\n"
                "\u652F\u6301\u76F4\u63A5\u9009\u62E9\u6587\u4EF6\u5939\u6216\u4E0A\u4F20 .zip \u538B\u7F29\u5305\u3002"
            )
            self._body_stack.setCurrentIndex(1)
        else:
            self._body_stack.setCurrentIndex(0)
            self._module_stack.setCurrentIndex(idx)
            if key == "statistics" and self._statistics_widget is not None:
                self._statistics_widget.load_data()
            elif key == "plots" and self._plots_widget is not None:
                self._plots_widget.load_data()
            elif key == "heatmaps" and self._heatmap_widget is not None:
                self._heatmap_widget.load_data()

        title_map = {
            "clustering": "Clustering Comparison",
            "overview": "Overview",
            "upload": "Upload Data",
            "datasets": "Datasets",
            "preprocessing": "Preprocessing",
            "marker_genes": "Marker Genes",
            "dimensionality": "Dimensionality Reduction",
            "statistics": "Statistics",
            "plots": "Plots",
            "heatmaps": "Heatmaps",
            "trajectory": "Trajectory Analysis",
            "comparison": "Comparison",
        }
        name = title_map.get(key, key.capitalize())
        self.setWindowTitle(f"ClustroView - {name}")

    # ================================================================
    #  Public API used by controller
    # ================================================================
    def set_path_manager(self, mgr) -> None:
        """Inject shared DataPathManager from controller."""
        self._path_mgr = mgr

    def _on_folder_registered(self, root_path):
        """Upload page registered a new folder."""
        if self._controller is not None:
            self._controller.reload_from_path(root_path)

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

    def _on_spatial_section(self, sid: str):
        data_root = Path(__file__).resolve().parent.parent.parent / "dataset" / "DLPFC"
        ds = load_spatial_dataset(str(data_root), sid)
        if ds:
            self._spatial_viewer.load_section(ds)
            # Switch to spatial viewer mode
            self._spatial_mode = True
            self._comparison_widget.setVisible(False)
            self._view_3d_container.setVisible(True)
            self._btn_sbs.setChecked(False)
            # Sync main section combo
            for i in range(self._section_combo.count()):
                if self._section_combo.itemText(i) == sid:
                    self._section_combo.blockSignals(True)
                    self._section_combo.setCurrentIndex(i)
                    self._section_combo.blockSignals(False)
                    self._current_index = i
                    break

    def _on_spatial_mode(self, mode: str):
        self._spatial_viewer.set_mode(mode)
        self._hover_panel.set_mode(mode)

    def _on_spatial_view(self, view: str):
        if view == "front":
            self._spatial_viewer.view_front()
        else:
            self._spatial_viewer.view_back()

    def resizeEvent(self, event):
        super().resizeEvent(event)

    def _on_section_changed(self, idx: int) -> None:
        self._lazy.start()

    def _on_lazy(self) -> None:
        idx = self._section_combo.currentIndex()
        if idx < 0:
            return
        self._current_index = idx
        # If in spatial mode, also update spatial viewer
        if self._spatial_mode:
            sid = self._section_combo.itemText(idx)
            data_root = Path(__file__).resolve().parent.parent.parent / "dataset" / "DLPFC"
            ds = load_spatial_dataset(str(data_root), sid)
            if ds:
                self._spatial_viewer.load_section(ds)
                # Sync hover panel combo
                hp_idx = self._hover_panel._section_combo.findText(sid)
                if hp_idx >= 0:
                    self._hover_panel._section_combo.blockSignals(True)
                    self._hover_panel._section_combo.setCurrentIndex(hp_idx)
                    self._hover_panel._section_combo.blockSignals(False)
        self._refresh_current()
        if self._controller is not None:
            self._controller.on_section_changed(idx)
