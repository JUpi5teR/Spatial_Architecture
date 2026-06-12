"""Main application window with Overlay / Side-by-Side mode toggle."""
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
    QSlider,
    QStatusBar,
    QVBoxLayout,
    QWidget,
)

from model.image_manager import ImageCollection
from model.overlay_data import OverlayDataset
from view.comparison_view import ComparisonViewWidget
from view.overlay_view import OverlayViewWidget
from view.status_bar import ParamsWidget, StatusBarWidget
from view.training_curve import TrainingCurveWidget


# ---- Palette definitions ----

_DARK_PALETTE = {
    "Window": (45, 45, 45),
    "WindowText": (220, 220, 220),
    "Base": (30, 30, 30),
    "AlternateBase": (45, 45, 45),
    "ToolTipBase": (220, 220, 220),
    "ToolTipText": (0, 0, 0),
    "Text": (220, 220, 220),
    "Button": (50, 50, 50),
    "ButtonText": (220, 220, 220),
    "BrightText": (255, 100, 100),
    "Link": (42, 130, 218),
    "Highlight": (42, 130, 218),
    "HighlightedText": (220, 220, 220),
}

_LIGHT_PALETTE = {
    "Window": (240, 240, 240),
    "WindowText": (30, 30, 30),
    "Base": (255, 255, 255),
    "AlternateBase": (230, 230, 230),
    "ToolTipBase": (255, 255, 220),
    "ToolTipText": (0, 0, 0),
    "Text": (30, 30, 30),
    "Button": (225, 225, 225),
    "ButtonText": (30, 30, 30),
    "BrightText": (200, 50, 50),
    "Link": (0, 100, 200),
    "Highlight": (0, 120, 215),
    "HighlightedText": (255, 255, 255),
}

# ---- Theme styles ----

_FRAME_DARK = "QFrame { border: 1px solid #555; border-radius: 4px; }"
_FRAME_LIGHT = "QFrame { border: 1px solid #ccc; border-radius: 4px; }"

_NAV_BTN_DARK = (
    "QPushButton { font-size: 16px; border: 1px solid #666; "
    "border-radius: 4px; background: #333; color: #eee; }"
    "QPushButton:hover { background: #555; }"
)
_NAV_BTN_LIGHT = (
    "QPushButton { font-size: 16px; border: 1px solid #bbb; "
    "border-radius: 4px; background: #e0e0e0; color: #222; }"
    "QPushButton:hover { background: #ccc; }"
)

_THEME_BTN_DARK = (
    "QPushButton { font-size: 12px; border: 1px solid #666; "
    "border-radius: 4px; background: #444; color: #eee; }"
    "QPushButton:hover { background: #666; }"
)
_THEME_BTN_LIGHT = (
    "QPushButton { font-size: 12px; border: 1px solid #bbb; "
    "border-radius: 4px; background: #ddd; color: #222; }"
    "QPushButton:hover { background: #ccc; }"
)

_MODE_BTN_DARK = (
    "QPushButton { font-size: 14px; padding: 4px 16px; "
    "border: 1px solid #666; border-radius: 4px; "
    "background: #333; color: #eee; }"
    "QPushButton:hover { background: #555; }"
    "QPushButton:checked { background: #2980b9; color: #fff; border-color: #2980b9; }"
)
_MODE_BTN_LIGHT = (
    "QPushButton { font-size: 14px; padding: 4px 16px; "
    "border: 1px solid #aaa; border-radius: 4px; "
    "background: #f0f0f0; color: #222; }"
    "QPushButton:hover { background: #ddd; }"
    "QPushButton:checked { background: #3498db; color: #fff; border-color: #3498db; }"
)


def apply_theme(dark: bool) -> None:
    """Apply dark or light palette to QApplication."""
    app = QApplication.instance()
    if app is None:
        return
    colors = _DARK_PALETTE if dark else _LIGHT_PALETTE
    palette = QPalette()
    for role_name, rgb in colors.items():
        role = getattr(QPalette.ColorRole, role_name, None)
        if role is not None:
            palette.setColor(role, QColor(*rgb))
    app.setPalette(palette)


class MainWindow(QMainWindow):
    """Main application window with overlay / side-by-side toggle."""

    def __init__(self, controller=None):
        super().__init__()
        self._controller = controller
        self._collection: Optional[ImageCollection] = None
        self._overlay_datasets: list[OverlayDataset] = []
        self._current_index: int = 0
        self._dark_theme: bool = True
        self._is_overlay_mode: bool = False

        self.setWindowTitle("Spatial Clustering Comparison Viewer")
        self.setMinimumSize(1200, 800)
        self._setup_ui()

        self._lazy_timer = QTimer(self)
        self._lazy_timer.setSingleShot(True)
        self._lazy_timer.setInterval(150)
        self._lazy_timer.timeout.connect(self._on_lazy_load)

    def set_controller(self, controller) -> None:
        """Set controller reference for navigation callbacks."""
        self._controller = controller

    def _setup_ui(self) -> None:
        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QVBoxLayout(central)
        main_layout.setContentsMargins(8, 8, 8, 8)
        main_layout.setSpacing(6)

        # ---- Top frame ----
        self.status_bar_widget = StatusBarWidget()
        self.params_widget = ParamsWidget()

        self._top_frame = QFrame()
        self._top_frame.setFrameShape(QFrame.Shape.StyledPanel)
        self._top_frame.setStyleSheet(_FRAME_DARK)
        top_layout = QVBoxLayout(self._top_frame)
        top_layout.setContentsMargins(4, 4, 4, 4)

        top_row = QHBoxLayout()
        top_row.setContentsMargins(0, 0, 0, 0)
        top_row.addWidget(self.status_bar_widget, 1)

        self._theme_btn = QPushButton("☀️ Light")
        self._theme_btn.setFixedSize(100, 26)
        self._theme_btn.setStyleSheet(_THEME_BTN_DARK)
        self._theme_btn.clicked.connect(self._toggle_theme)

        btn_container = QHBoxLayout()
        btn_container.addStretch()
        btn_container.addWidget(self._theme_btn)
        top_row.addLayout(btn_container)

        top_layout.addLayout(top_row)
        top_layout.addWidget(self.params_widget)
        main_layout.addWidget(self._top_frame)

        # ---- Curve frame ----
        self.curve_widget = TrainingCurveWidget()

        self._curve_frame = QFrame()
        self._curve_frame.setFrameShape(QFrame.Shape.StyledPanel)
        self._curve_frame.setStyleSheet(_FRAME_DARK)
        curve_layout = QVBoxLayout(self._curve_frame)
        curve_layout.setContentsMargins(4, 4, 4, 4)
        curve_layout.addWidget(self.curve_widget)
        main_layout.addWidget(self._curve_frame, 2)

        # ---- Comparison frame with mode toggle ----
        self.comparison_widget = ComparisonViewWidget()
        self.overlay_widget = OverlayViewWidget()
        self.overlay_widget.setVisible(False)

        self._comp_frame = QFrame()
        self._comp_frame.setFrameShape(QFrame.Shape.StyledPanel)
        self._comp_frame.setStyleSheet(_FRAME_DARK)
        comp_layout = QVBoxLayout(self._comp_frame)
        comp_layout.setContentsMargins(4, 4, 4, 4)

        # Nav bar with mode toggle
        nav_layout = QHBoxLayout()
        nav_layout.setSpacing(8)

        self._nav_label = QLabel("Image: 0 / 0")
        self._nav_label.setStyleSheet("font-size: 13px;")

        self._prev_btn = QPushButton("◀")
        self._prev_btn.setFixedSize(32, 28)
        self._prev_btn.setStyleSheet(_NAV_BTN_DARK)
        self._prev_btn.clicked.connect(self._prev_image)

        self._next_btn = QPushButton("▶")
        self._next_btn.setFixedSize(32, 28)
        self._next_btn.setStyleSheet(_NAV_BTN_DARK)
        self._next_btn.clicked.connect(self._next_image)

        self._nav_slider = QSlider(Qt.Orientation.Horizontal)
        self._nav_slider.setMinimum(0)
        self._nav_slider.setMaximum(0)
        self._nav_slider.valueChanged.connect(self._on_slider_changed)

        # Mode toggle
        self._overlay_btn = QPushButton("Overlay")
        self._overlay_btn.setFixedSize(90, 28)
        self._overlay_btn.setStyleSheet(_MODE_BTN_DARK)
        self._overlay_btn.setCheckable(True)
        self._overlay_btn.clicked.connect(self._toggle_mode)

        self._sidebyside_btn = QPushButton("Side-by-Side")
        self._sidebyside_btn.setFixedSize(110, 28)
        self._sidebyside_btn.setStyleSheet(_MODE_BTN_DARK)
        self._sidebyside_btn.setCheckable(True)
        self._sidebyside_btn.setChecked(True)
        self._sidebyside_btn.clicked.connect(self._toggle_mode)

        nav_layout.addWidget(self._prev_btn)
        nav_layout.addWidget(self._nav_slider, 1)
        nav_layout.addWidget(self._next_btn)
        nav_layout.addSpacing(8)
        nav_layout.addWidget(self._overlay_btn)
        nav_layout.addWidget(self._sidebyside_btn)

        comp_layout.addLayout(nav_layout)
        comp_layout.addWidget(self.comparison_widget, 1)
        comp_layout.addWidget(self.overlay_widget, 1)
        main_layout.addWidget(self._comp_frame, 3)

        self._qt_status_bar = QStatusBar()
        self.setStatusBar(self._qt_status_bar)

    # ---- Theme ----

    def _toggle_theme(self) -> None:
        self._dark_theme = not self._dark_theme
        apply_theme(self._dark_theme)
        self._theme_btn.setText(
            "☀️ Light" if self._dark_theme else "🌙 Dark"
        )
        style = _FRAME_DARK if self._dark_theme else _FRAME_LIGHT
        self._top_frame.setStyleSheet(style)
        self._curve_frame.setStyleSheet(style)
        self._comp_frame.setStyleSheet(style)

        nav_style = _NAV_BTN_DARK if self._dark_theme else _NAV_BTN_LIGHT
        self._prev_btn.setStyleSheet(nav_style)
        self._next_btn.setStyleSheet(nav_style)
        self._theme_btn.setStyleSheet(
            _THEME_BTN_DARK if self._dark_theme else _THEME_BTN_LIGHT
        )
        mode_style = _MODE_BTN_DARK if self._dark_theme else _MODE_BTN_LIGHT
        self._overlay_btn.setStyleSheet(mode_style)
        self._sidebyside_btn.setStyleSheet(mode_style)

        self.comparison_widget.update_theme(self._dark_theme)
        self.overlay_widget.update_theme(self._dark_theme)
        self.curve_widget.update_theme(self._dark_theme)
        self.status_bar_widget.update_theme(self._dark_theme)
        self.params_widget.update_theme(self._dark_theme)

    # ---- Mode Toggle ----

    def _toggle_mode(self) -> None:
        sender = self.sender()
        if sender is self._overlay_btn:
            self._is_overlay_mode = True
            self._overlay_btn.setChecked(True)
            self._sidebyside_btn.setChecked(False)
        else:
            self._is_overlay_mode = False
            self._overlay_btn.setChecked(False)
            self._sidebyside_btn.setChecked(True)

        self._apply_mode()

    def _apply_mode(self) -> None:
        if self._is_overlay_mode:
            self._switch_to_overlay()
        else:
            self._switch_to_sidebyside()

    def _switch_to_overlay(self) -> None:
        self.comparison_widget.setVisible(False)
        self.overlay_widget.setVisible(True)

        count = len(self._overlay_datasets)
        self._nav_label.setText(
            f"Section: {self._current_index + 1} / {max(count, 1)}"
        )
        self._nav_slider.setMaximum(max(count - 1, 0))
        self._nav_slider.setValue(self._current_index)
        self._prev_btn.setEnabled(count > 1)
        self._next_btn.setEnabled(count > 1)

        if self._controller and self._overlay_datasets:
            self._controller.show_overlay_at(self._current_index)

    def _switch_to_sidebyside(self) -> None:
        self.overlay_widget.setVisible(False)
        self.comparison_widget.setVisible(True)

        if self._collection:
            count = len(self._collection.pairs)
            self._nav_label.setText(
                f"Image: {self._current_index + 1} / {max(count, 1)}"
            )
            self._nav_slider.setMaximum(max(count - 1, 0))
            self._nav_slider.setValue(self._current_index)
            self._prev_btn.setEnabled(count > 1)
            self._next_btn.setEnabled(count > 1)
            self._show_image(self._current_index)

    # ---- Public API ----

    def set_overlay_datasets(self, datasets: list[OverlayDataset]) -> None:
        """Store overlay datasets and show first if in overlay mode."""
        self._overlay_datasets = datasets
        self._current_index = 0

        if not datasets:
            self.overlay_widget.show_no_data()
            return

        self._nav_slider.setMaximum(len(datasets) - 1)
        self._nav_slider.setValue(0)
        self._prev_btn.setEnabled(len(datasets) > 1)
        self._next_btn.setEnabled(len(datasets) > 1)

        if self._is_overlay_mode:
            self._switch_to_overlay()

    def show_overlay_dataset(self, dataset: OverlayDataset, index: int) -> None:
        """Display a specific overlay dataset."""
        self._current_index = index
        count = len(self._overlay_datasets)
        self._nav_label.setText(
            f"Section: {index + 1} / {max(count, 1)}"
        )
        self._nav_slider.setValue(index)
        self.overlay_widget.set_dataset(dataset)

    def set_collection(self, collection: ImageCollection) -> None:
        """Store image collection and show first."""
        self._collection = collection
        self._current_index = 0

        if not collection.pairs:
            self._nav_slider.setMaximum(0)
            self._prev_btn.setEnabled(False)
            self._next_btn.setEnabled(False)
            self._nav_label.setText("Image: 0 / 0")
            self.comparison_widget.show_no_data()
            return

        self._nav_slider.setMaximum(len(collection.pairs) - 1)
        self._nav_slider.setValue(0)
        self._prev_btn.setEnabled(True)
        self._next_btn.setEnabled(True)

        if not self._is_overlay_mode:
            self._show_image(0)

    def show_image(self, index: int) -> None:
        """Show image at index (public for controller)."""
        self._show_image(index)

    def _show_image(self, index: int) -> None:
        if self._is_overlay_mode:
            return
        if not self._collection or not self._collection.pairs:
            return
        if index < 0 or index >= len(self._collection.pairs):
            return

        self._current_index = index
        pair = self._collection.pairs[index]
        self._nav_label.setText(
            f"Image: {index + 1} / {len(self._collection.pairs)}"
        )

        if self._collection.fallback_mode:
            self.comparison_widget.show_fallback(pair)
        else:
            self.comparison_widget.show_pair(pair)

        if self.comparison_widget.sync_locked:
            self.comparison_widget._gt_panel.image_label.reset_view(emit=False)
            self.comparison_widget._pred_panel.image_label.reset_view(emit=False)

    def _prev_image(self) -> None:
        if self._is_overlay_mode:
            if self._current_index > 0:
                self._nav_slider.setValue(self._current_index - 1)
        else:
            if self._current_index > 0:
                self._nav_slider.setValue(self._current_index - 1)

    def _next_image(self) -> None:
        max_idx = (
            len(self._overlay_datasets) - 1
            if self._is_overlay_mode
            else (len(self._collection.pairs) - 1 if self._collection else 0)
        )
        if self._current_index < max_idx:
            self._nav_slider.setValue(self._current_index + 1)

    def _on_slider_changed(self, value: int) -> None:
        self._lazy_timer.start()

    def _on_lazy_load(self) -> None:
        idx = self._nav_slider.value()
        if self._is_overlay_mode:
            if self._controller:
                self._controller.show_overlay_at(idx)
        else:
            self._show_image(idx)

    def show_status_message(self, message: str) -> None:
        self._qt_status_bar.showMessage(message, 5000)
