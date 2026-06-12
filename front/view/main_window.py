"""ClustroView - Clustering Comparison page.

Layout: left fixed nav sidebar + right scrollable content.
Single toggle: Side-by-Side / 3D Flip (per request.md).
"""
from typing import Optional

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QPalette, QColor
from PySide6.QtWidgets import (
    QApplication,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QPushButton,
    QScrollArea,
    QSlider,
    QStatusBar,
    QVBoxLayout,
    QWidget,
    QSizePolicy,
)

from model.image_manager import ImageCollection
from model.overlay_data import OverlayDataset
from view.comparison_view import ComparisonViewWidget
from view.overlay_3d_view import Overlay3DViewWidget
from view.status_bar import ParamsWidget, StatusBarWidget
from view.training_curve import TrainingCurveWidget


# ====================================================================
#  Palette
# ====================================================================

_DARK = {
    "Window": (23, 23, 23), "WindowText": (245, 245, 247),
    "Base": (35, 35, 38), "AlternateBase": (30, 30, 33),
    "Text": (245, 245, 247), "Button": (40, 40, 44),
    "ButtonText": (245, 245, 247), "BrightText": (255, 77, 79),
    "Link": (100, 180, 255), "Highlight": (100, 180, 255),
    "HighlightedText": (23, 23, 23),
}

_LIGHT = {
    "Window": (250, 250, 250), "WindowText": (46, 46, 46),
    "Base": (245, 245, 245), "AlternateBase": (240, 240, 240),
    "Text": (46, 46, 46), "Button": (235, 235, 235),
    "ButtonText": (46, 46, 46), "BrightText": (255, 77, 79),
    "Link": (50, 130, 220), "Highlight": (50, 130, 220),
    "HighlightedText": (250, 250, 250),
}

# ====================================================================
#  Glass sidebar
# ====================================================================

_SB_DARK = (
    "QFrame { background: #1e1e21;"
    " border-right: 1px solid rgba(255,255,255,0.06); }"
)
_SB_LIGHT = (
    "QFrame { background: #f5f5f5;"
    " border-right: 1px solid #e6e6e6; }"
)

_LBL_D = "color: #8a8a90; font-size: 9px; letter-spacing: 1px;"
_LBL_L = "color: #8a8a8a; font-size: 9px; letter-spacing: 1px;"

_SEP_D = "color: rgba(255,255,255,0.06); font-size: 8px;"
_SEP_L = "color: rgba(0,0,0,0.08); font-size: 8px;"

_CNT_D = "color: #8a8a90; font-size: 10px;"
_CNT_L = "color: rgba(0,0,0,0.38); font-size: 10px;"

# ---- Single mode toggle button ----
_TOGGLE_D = (
    "QPushButton { font-size: 10px; padding: 5px 0;"
    " border: 1px solid rgba(255,255,255,0.08); border-radius: 8px;"
    " background: rgba(255,255,255,0.04); color: #8a8a90; }"
    "QPushButton:hover { background: rgba(255,255,255,0.08); }"
    "QPushButton:checked {"
    " background: rgba(100,180,255,0.15); color: #f5f5f7;"
    " border-color: rgba(100,180,255,0.30); font-weight: 600; }"
)
_TOGGLE_L = (
    "QPushButton { font-size: 10px; padding: 5px 0;"
    " border: 1px solid rgba(0,0,0,0.07); border-radius: 6px;"
    " background: rgba(0,0,0,0.02); color: rgba(0,0,0,0.45); }"
    "QPushButton:hover { background: rgba(0,0,0,0.05); }"
    "QPushButton:checked {"
    " background: rgba(50,130,220,0.15); color: #1a6bc0;"
    " border-color: rgba(50,130,220,0.35); font-weight: 600; }"
)

_NAV_D = (
    "QPushButton { font-size: 11px; min-width: 24px; max-width: 24px;"
    " min-height: 20px; max-height: 20px;"
    " border: 1px solid rgba(255,255,255,0.06); border-radius: 6px;"
    " background: rgba(255,255,255,0.03); color: #8a8a90; }"
    "QPushButton:hover { background: rgba(255,255,255,0.08); }"
)
_NAV_L = (
    "QPushButton { font-size: 11px; min-width: 24px; max-width: 24px;"
    " min-height: 20px; max-height: 20px;"
    " border: 1px solid rgba(0,0,0,0.05); border-radius: 4px;"
    " background: rgba(0,0,0,0.02); color: rgba(0,0,0,0.40); }"
    "QPushButton:hover { background: rgba(0,0,0,0.05); }"
)

_THM_D = (
    "QPushButton { font-size: 10px; padding: 4px 10px;"
    " border: 1px solid rgba(255,255,255,0.06); border-radius: 8px;"
    " background: rgba(255,255,255,0.03); color: #8a8a90; }"
    "QPushButton:hover { background: rgba(255,255,255,0.08); }"
)
_THM_L = (
    "QPushButton { font-size: 10px; padding: 3px 8px;"
    " border: 1px solid rgba(0,0,0,0.05); border-radius: 5px;"
    " background: rgba(0,0,0,0.02); color: rgba(0,0,0,0.38); }"
    "QPushButton:hover { background: rgba(0,0,0,0.04); }"
)

_CONT_D = "background-color: #171717;"
_CONT_L = "background-color: #fafafa;"


def apply_theme(dark: bool):
    app = QApplication.instance()
    if app is None: return
    palette = QPalette()
    src = _DARK if dark else _LIGHT
    for role_name, rgb in src.items():
        role = getattr(QPalette.ColorRole, role_name, None)
        if role is not None:
            palette.setColor(role, QColor(*rgb))
    app.setPalette(palette)


# ====================================================================
#  Main window
# ====================================================================

class MainWindow(QMainWindow):
    SIDEBAR_W = 220

    def __init__(self, controller=None):
        super().__init__()
        self._controller = controller
        self._collection: Optional[ImageCollection] = None
        self._overlay_datasets: list[OverlayDataset] = []
        self._current_index = 0
        self._dark_theme = False  # default light per request.md
        self._is_3dflip_mode = False

        self.setWindowTitle("ClustroView - Clustering Comparison")
        self.setMinimumSize(1050, 650)
        self._setup_ui()

        self._lazy = QTimer(self); self._lazy.setSingleShot(True)
        self._lazy.setInterval(100)
        self._lazy.timeout.connect(self._on_lazy)

    def set_controller(self, c):
        self._controller = c

    # ================================================================
    #  UI
    # ================================================================

    def _setup_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        root = QHBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0); root.setSpacing(0)

        # --- Sidebar ---
        self._sidebar = QFrame()
        self._sidebar.setFixedWidth(self.SIDEBAR_W)
        self._sidebar.setStyleSheet(_SB_LIGHT)  # light by default
        sb = QVBoxLayout(self._sidebar)
        sb.setContentsMargins(10, 14, 10, 12); sb.setSpacing(5)

        # Single mode toggle
        ml = QLabel("VIEW MODE"); ml.setStyleSheet(_LBL_L); sb.addWidget(ml)
        self._btn_sbs = QPushButton("Side-by-Side")
        self._btn_sbs.setCheckable(True); self._btn_sbs.setChecked(True)
        self._btn_sbs.clicked.connect(lambda: self._set_mode(False))
        self._btn_sbs.setStyleSheet(_TOGGLE_L)
        self._btn_3df = QPushButton("3D Flip")
        self._btn_3df.setCheckable(True)
        self._btn_3df.clicked.connect(lambda: self._set_mode(True))
        self._btn_3df.setStyleSheet(_TOGGLE_L)
        tr = QHBoxLayout(); tr.setSpacing(4)
        tr.addWidget(self._btn_sbs, 1); tr.addWidget(self._btn_3df, 1)
        sb.addLayout(tr); sb.addSpacing(8)

        # Nav
        nl = QLabel("NAVIGATION"); nl.setStyleSheet(_LBL_L); sb.addWidget(nl)
        nr = QHBoxLayout(); nr.setSpacing(4)
        self._prev = QPushButton(chr(0x25C0)); self._prev.setStyleSheet(_NAV_L)
        self._prev.clicked.connect(self._go_prev)
        self._next = QPushButton(chr(0x25B6)); self._next.setStyleSheet(_NAV_L)
        self._next.clicked.connect(self._go_next)
        self._slider = QSlider(Qt.Orientation.Horizontal)
        self._slider.setMinimum(0); self._slider.setMaximum(0)
        self._slider.valueChanged.connect(self._on_slider)
        nr.addWidget(self._prev); nr.addWidget(self._slider, 1); nr.addWidget(self._next)
        sb.addLayout(nr)
        self._nav_label = QLabel("Image: 0 / 0")
        self._nav_label.setStyleSheet(_CNT_L)
        self._nav_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        sb.addWidget(self._nav_label); sb.addSpacing(6)

        s1 = QLabel(chr(0x2500)*12); s1.setStyleSheet(_SEP_L)
        s1.setAlignment(Qt.AlignmentFlag.AlignCenter); sb.addWidget(s1)

        self.status_bar_widget = StatusBarWidget(); sb.addWidget(self.status_bar_widget)
        sb.addSpacing(2)
        s2 = QLabel(chr(0x2500)*12); s2.setStyleSheet(_SEP_L)
        s2.setAlignment(Qt.AlignmentFlag.AlignCenter); sb.addWidget(s2)

        self.params_widget = ParamsWidget(); sb.addWidget(self.params_widget)
        sb.addStretch()

        self._theme_btn = QPushButton(chr(0x2600)+"  Light")
        self._theme_btn.setStyleSheet(_THM_L)
        self._theme_btn.clicked.connect(self._toggle_theme); sb.addWidget(self._theme_btn)

        self._s_lbls = [ml, nl]; self._s_seps = [s1, s2]

        # --- Right content ---
        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setStyleSheet("QScrollArea { border: none; " + _CONT_D + " }")
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        cw = QWidget(); cw.setStyleSheet(_CONT_D)
        cl = QVBoxLayout(cw); cl.setContentsMargins(12, 12, 12, 12); cl.setSpacing(6)

        # Title area
        title_row = QHBoxLayout()
        title_l = QLabel("Clustering Comparison")
        title_l.setStyleSheet(
            "font-size: 18px; font-weight: 700; color: #2e2e2e; padding: 0;"
        )
        subtitle_l = QLabel("Compare ground truth vs prediction results")
        subtitle_l.setStyleSheet(
            "font-size: 11px; color: #999; padding: 2px 0 0 0;"
        )
        tv = QVBoxLayout()
        tv.addWidget(title_l); tv.addWidget(subtitle_l)
        title_row.addLayout(tv, 1)
        ds_label = QLabel("DLPFC")
        ds_label.setStyleSheet(
            "font-size: 11px; color: #666; padding: 4px 10px;"
            " border: 1px solid #ddd; border-radius: 4px; background: #fafafa;"
        )
        title_row.addWidget(ds_label)
        cl.addLayout(title_row)
        cl.addSpacing(4)

        # Comparison content
        self.comparison_widget = ComparisonViewWidget()
        self.comparison_widget.setMinimumHeight(350)
        self._3d_widget = Overlay3DViewWidget()
        self._3d_widget.setMinimumHeight(350); self._3d_widget.setVisible(False)

        cl.addWidget(self.comparison_widget, 4)
        cl.addWidget(self._3d_widget, 4)

        # Curve
        self._curve_label = QLabel("Training Progress")
        self._curve_label.setStyleSheet(
            "color: #999; font-size: 10px; font-weight: 600; padding: 4px 0 2px;"
        )
        cl.addWidget(self._curve_label)
        self.curve_widget = TrainingCurveWidget()
        self.curve_widget.setFixedHeight(170)
        cl.addWidget(self.curve_widget)
        cl.addStretch()

        self._scroll.setWidget(cw)
        root.addWidget(self._sidebar)
        root.addWidget(self._scroll, 1)

        self._qt_status = QStatusBar(); self.setStatusBar(self._qt_status)

        # Apply initial theme
        apply_theme(False)

    # ================================================================
    #  Theme
    # ================================================================

    def _toggle_theme(self):
        self._dark_theme = not self._dark_theme
        d = self._dark_theme
        apply_theme(d)
        self._theme_btn.setText((chr(0x263E)+"  Dark") if d else (chr(0x2600)+"  Light"))

        self._sidebar.setStyleSheet(_SB_DARK if d else _SB_LIGHT)
        ls = _LBL_D if d else _LBL_L
        for w in self._s_lbls: w.setStyleSheet(ls)
        self._nav_label.setStyleSheet(_CNT_D if d else _CNT_L)
        ss = _SEP_D if d else _SEP_L
        for w in self._s_seps: w.setStyleSheet(ss)

        ts = _TOGGLE_D if d else _TOGGLE_L
        self._btn_sbs.setStyleSheet(ts); self._btn_3df.setStyleSheet(ts)
        ns = _NAV_D if d else _NAV_L
        self._prev.setStyleSheet(ns); self._next.setStyleSheet(ns)
        self._theme_btn.setStyleSheet(_THM_D if d else _THM_L)

        self._scroll.setStyleSheet(
            "QScrollArea { border: none; " + (_CONT_D if d else _CONT_L) + " }"
        )
        self._scroll.widget().setStyleSheet(_CONT_D if d else _CONT_L)
        self._curve_label.setStyleSheet(
            ("color: rgba(255,255,255,0.35);" if d else "color: #999;")
            + " font-size: 10px; font-weight: 600; padding: 4px 0 2px;"
        )
        self.comparison_widget.update_theme(d)
        self._3d_widget.update_theme(d)
        self.curve_widget.update_theme(d)
        self.status_bar_widget.update_theme(d)
        self.params_widget.update_theme(d)

    # ================================================================
    #  Mode
    # ================================================================

    def _set_mode(self, is_3dflip):
        self._is_3dflip_mode = is_3dflip
        self._btn_sbs.setChecked(not is_3dflip)
        self._btn_3df.setChecked(is_3dflip)
        self._apply_mode()

    def _apply_mode(self):
        if self._is_3dflip_mode:
            self.comparison_widget.setVisible(False)
            self._3d_widget.setVisible(True)
            n = len(self._overlay_datasets)
            self._nav_label.setText(
                "Section: " + str(self._current_index+1) + " / " + str(max(n,1))
            )
            self._slider.setMaximum(max(n-1,0)); self._slider.setValue(self._current_index)
            self._prev.setEnabled(n>1); self._next.setEnabled(n>1)
            if self._controller and self._overlay_datasets:
                self._controller.show_overlay_at(self._current_index)
        else:
            self._3d_widget.setVisible(False)
            self.comparison_widget.setVisible(True)
            if self._collection:
                n = len(self._collection.pairs)
                self._nav_label.setText(
                    "Image: " + str(self._current_index+1) + " / " + str(max(n,1))
                )
                self._slider.setMaximum(max(n-1,0)); self._slider.setValue(self._current_index)
                self._prev.setEnabled(n>1); self._next.setEnabled(n>1)
                self._show_image(self._current_index)

    # ================================================================
    #  Public
    # ================================================================

    def set_overlay_datasets(self, dss):
        self._overlay_datasets = dss; self._current_index = 0
        if not dss:
            self._3d_widget.show_no_data(); return
        self._slider.setMaximum(len(dss)-1); self._slider.setValue(0)
        self._prev.setEnabled(len(dss)>1); self._next.setEnabled(len(dss)>1)
        if self._is_3dflip_mode: self._apply_mode()

    def show_overlay_dataset(self, ds, idx):
        self._current_index = idx
        n = len(self._overlay_datasets)
        self._nav_label.setText("Section: "+str(idx+1)+" / "+str(max(n,1)))
        self._slider.setValue(idx)
        self._3d_widget.set_dataset(ds)

    def set_collection(self, coll):
        self._collection = coll; self._current_index = 0
        if not coll.pairs:
            self._slider.setMaximum(0)
            self._prev.setEnabled(False); self._next.setEnabled(False)
            self._nav_label.setText("Image: 0 / 0")
            self.comparison_widget.show_no_data(); return
        self._slider.setMaximum(len(coll.pairs)-1); self._slider.setValue(0)
        self._prev.setEnabled(True); self._next.setEnabled(True)
        if not self._is_3dflip_mode: self._show_image(0)

    def show_image(self, idx): self._show_image(idx)

    def _show_image(self, idx):
        if self._is_3dflip_mode: return
        if not self._collection or not self._collection.pairs: return
        if idx < 0 or idx >= len(self._collection.pairs): return
        self._current_index = idx
        p = self._collection.pairs[idx]
        self._nav_label.setText("Image: "+str(idx+1)+" / "+str(len(self._collection.pairs)))
        if self._collection.fallback_mode:
            self.comparison_widget.show_fallback(p)
        else:
            self.comparison_widget.show_pair(p)
        if self.comparison_widget.sync_locked:
            self.comparison_widget._gt_panel.image_label.reset_view(emit=False)
            self.comparison_widget._pred_panel.image_label.reset_view(emit=False)

    # ================================================================
    #  Nav
    # ================================================================

    def _go_prev(self):
        if self._current_index > 0: self._slider.setValue(self._current_index-1)
    def _go_next(self):
        mx = (len(self._overlay_datasets)-1 if self._is_3dflip_mode
              else (len(self._collection.pairs)-1 if self._collection else 0))
        if self._current_index < mx: self._slider.setValue(self._current_index+1)
    def _on_slider(self, v): self._lazy.start()
    def _on_lazy(self):
        idx = self._slider.value()
        if self._is_3dflip_mode:
            if self._controller: self._controller.show_overlay_at(idx)
        else:
            self._show_image(idx)

    def show_status_message(self, msg):
        self._qt_status.showMessage(msg, 4000)
