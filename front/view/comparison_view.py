"""Side-by-side image comparison view with zoom, pan, and sync."""
from __future__ import annotations
from typing import Optional

import numpy as np
from PySide6.QtCore import Qt, QPoint, Signal
from PySide6.QtGui import QImage, QPixmap, QPainter
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
    QFrame,
)

from model.image_manager import ImagePair, load_image
from utils.logger import logger


# ---- Theme styles ----

_IMAGE_BG_DARK = "#1a1a1e"
_IMAGE_BG_LIGHT = "#f0f0f3"

_TITLE_DARK = (
    "font-weight: bold; font-size: 13px; color: #d0d0d5; padding: 2px 8px;"
)
_TITLE_LIGHT = (
    "font-weight: bold; font-size: 13px; color: #2c3e50; padding: 2px 8px;"
)

_SCROLL_DARK = "background-color: #1a1a1e; border: none;"
_SCROLL_LIGHT = "background-color: #f0f0f3; border: none;"

_BTN_DARK = (
    "QPushButton { font-size: 12px; padding: 2px 12px; "
    "border: 1px solid rgba(255,255,255,0.08); border-radius: 6px; "
    "background: rgba(255,255,255,0.04); color: #b0b0b5; }"
    "QPushButton:hover { background: rgba(255,255,255,0.08); }"
    "QPushButton:checked { background: rgba(46,204,113,0.20); color: #2ecc71; border-color: rgba(46,204,113,0.3); }"
)
_BTN_LIGHT = (
    "QPushButton { font-size: 12px; padding: 2px 12px; "
    "border: 1px solid #bbb; border-radius: 4px; background: #eee; color: #222; }"
    "QPushButton:hover { background: #ddd; }"
    "QPushButton:checked { background: #2ecc71; color: #fff; border-color: #2ecc71; }"
)

_NO_DATA_DARK = "color: #6a6a70; font-size: 18px;"
_NO_DATA_LIGHT = "color: #7f8c8d; font-size: 18px;"

_LABEL_DARK = "color: #8a8a90; font-size: 11px; padding: 2px 8px;"
_LABEL_LIGHT = "color: #7f8c8d; font-size: 11px; padding: 2px 8px;"


class ZoomableImageLabel(QLabel):
    """A QLabel that supports zoom, pan, and double-click reset."""

    zoom_changed = Signal(float)
    pan_changed = Signal(QPoint)

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self._original_pixmap: Optional[QPixmap] = None
        self._zoom_factor: float = 1.0
        self._min_zoom: float = 0.1
        self._max_zoom: float = 10.0
        self._pan_start: Optional[QPoint] = None
        self._pan_offset: QPoint = QPoint(0, 0)
        self._drag_active: bool = False
        self._dark: bool = True

        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )
        self.setMinimumSize(200, 150)
        self.setMouseTracking(True)
        self._apply_bg()

    def _apply_bg(self) -> None:
        bg = _IMAGE_BG_DARK if self._dark else _IMAGE_BG_LIGHT
        self.setStyleSheet(f"background-color: {bg};")

    def update_theme(self, dark: bool) -> None:
        self._dark = dark
        self._apply_bg()

    # ---- Public control API ----

    def set_image(self, image: np.ndarray) -> None:
        h, w, ch = image.shape
        bytes_per_line = ch * w
        qimage = QImage(
            image.data, w, h, bytes_per_line, QImage.Format.Format_RGB888
        )
        self._original_pixmap = QPixmap.fromImage(qimage)
        self._zoom_factor = 1.0
        self._pan_offset = QPoint(0, 0)
        self._update_display()

    def clear_image(self) -> None:
        self._original_pixmap = None
        self._zoom_factor = 1.0
        self._pan_offset = QPoint(0, 0)
        self.clear()
        self.setText("No Image")

    def is_default_state(self) -> bool:
        return (
            abs(self._zoom_factor - 1.0) < 0.001
            and self._pan_offset == QPoint(0, 0)
        )

    def reset_view(self, emit: bool = True) -> None:
        self._apply_zoom(1.0, emit=emit)
        self._apply_pan(QPoint(0, 0), emit=emit)

    def set_zoom_silent(self, factor: float) -> None:
        self._apply_zoom(factor, emit=False)

    def set_pan_silent(self, offset: QPoint) -> None:
        self._apply_pan(offset, emit=False)

    # ---- Internal ----

    def _apply_zoom(self, factor: float, emit: bool = True) -> None:
        self._zoom_factor = max(self._min_zoom, min(factor, self._max_zoom))
        self._update_display()
        if emit:
            self.zoom_changed.emit(self._zoom_factor)

    def _apply_pan(self, offset: QPoint, emit: bool = True) -> None:
        self._pan_offset = offset
        self._update_display()
        if emit:
            self.pan_changed.emit(self._pan_offset)

    def _update_display(self) -> None:
        if self._original_pixmap is None:
            return
        scaled = self._original_pixmap.scaled(
            int(self._original_pixmap.width() * self._zoom_factor),
            int(self._original_pixmap.height() * self._zoom_factor),
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        pm = QPixmap(scaled.size())
        pm.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pm)
        painter.drawPixmap(self._pan_offset, scaled)
        painter.end()
        self.setPixmap(pm)

    # ---- Events ----

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_active = True
            self._pan_start = event.position().toPoint()
            self.setCursor(Qt.CursorShape.ClosedHandCursor)

    def mouseMoveEvent(self, event) -> None:
        if not self._drag_active or self._pan_start is None:
            return
        delta = event.position().toPoint() - self._pan_start
        self._pan_start = event.position().toPoint()
        new_offset = self._pan_offset + delta
        self._apply_pan(new_offset)

    def mouseReleaseEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_active = False
            self._pan_start = None
            self.setCursor(Qt.CursorShape.ArrowCursor)

    def mouseDoubleClickEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self.reset_view()

    def wheelEvent(self, event) -> None:
        delta = event.angleDelta().y()
        factor = 1.15 if delta > 0 else 1.0 / 1.15
        self._apply_zoom(self._zoom_factor * factor)


class ImagePanel(QWidget):
    """Single image panel with title, image, and optional label."""

    def __init__(self, title: str, parent: QWidget | None = None):
        super().__init__(parent)
        self._dark: bool = True

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)

        self._title = QLabel(title)
        self._title.setStyleSheet(_TITLE_DARK)

        self.image_label = ZoomableImageLabel(self)

        self._label = QLabel("")
        self._label.setStyleSheet(_LABEL_DARK)
        self._label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        layout.addWidget(self._title)
        layout.addWidget(self.image_label, 1)
        layout.addWidget(self._label)

    def update_theme(self, dark: bool) -> None:
        self._dark = dark
        self._title.setStyleSheet(_TITLE_DARK if dark else _TITLE_LIGHT)
        self._label.setStyleSheet(_LABEL_DARK if dark else _LABEL_LIGHT)
        self.image_label.update_theme(dark)

    def show_image(
        self,
        image: np.ndarray,
        filename: str,
        label: str = "",
    ) -> None:
        self.image_label.set_image(image)
        self._title.setText(f"{self._title.text().split(':')[0]}: {filename}")
        self._label.setText(label)

    def clear(self) -> None:
        self.image_label.clear_image()
        self._label.setText("")


# ---- Comparison View ----

class ComparisonViewWidget(QWidget):
    """Side-by-side GT vs Prediction image comparison."""

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self._dark: bool = True
        self._syncing: bool = False
        self._sync_locked: bool = False

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        # Sync controls
        ctrl_layout = QHBoxLayout()
        ctrl_layout.setContentsMargins(0, 0, 0, 0)

        self._sync_btn = QPushButton("🔓 Lock Sync")
        self._sync_btn.setCheckable(True)
        self._sync_btn.setStyleSheet(_BTN_DARK)
        self._sync_btn.clicked.connect(self._on_sync_toggled)
        ctrl_layout.addWidget(self._sync_btn)
        ctrl_layout.addStretch()
        layout.addLayout(ctrl_layout)

        # Panels
        panels_layout = QHBoxLayout()
        panels_layout.setContentsMargins(0, 0, 0, 0)
        panels_layout.setSpacing(0)

        # No visible separator border per request.md
        self._gt_panel = ImagePanel("Ground Truth")
        self._pred_panel = ImagePanel("Prediction")

        panels_layout.addWidget(self._gt_panel, 1)
        panels_layout.addWidget(self._pred_panel, 1)
        layout.addLayout(panels_layout, 1)

        # No-data overlay
        self._no_data_label = QLabel("No Ground Truth Dataset Found")
        self._no_data_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._no_data_label.setStyleSheet(_NO_DATA_DARK)
        self._no_data_label.setVisible(False)

        # Connect sync signals
        self._gt_panel.image_label.zoom_changed.connect(self._on_gt_zoom)
        self._gt_panel.image_label.pan_changed.connect(self._on_gt_pan)
        self._pred_panel.image_label.zoom_changed.connect(self._on_pred_zoom)
        self._pred_panel.image_label.pan_changed.connect(self._on_pred_pan)

    def update_theme(self, dark: bool) -> None:
        self._dark = dark
        bg = _IMAGE_BG_DARK if dark else _IMAGE_BG_LIGHT
        self.setStyleSheet(f"ComparisonViewWidget {{ background-color: {bg}; }}")
        self._sync_btn.setStyleSheet(_BTN_DARK if dark else _BTN_LIGHT)
        self._no_data_label.setStyleSheet(
            _NO_DATA_DARK if dark else _NO_DATA_LIGHT
        )
        self._gt_panel.update_theme(dark)
        self._pred_panel.update_theme(dark)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._no_data_label.setGeometry(self.rect())

    @property
    def sync_locked(self) -> bool:
        return self._sync_locked

    # ---- Sync handlers ----

    def _on_sync_toggled(self, checked: bool) -> None:
        self._sync_locked = checked
        if checked:
            self._sync_btn.setText("🔒 Sync Locked")
            if not self._gt_panel.image_label.is_default_state():
                self._gt_panel.image_label.reset_view(emit=False)
            if not self._pred_panel.image_label.is_default_state():
                self._pred_panel.image_label.reset_view(emit=False)
        else:
            self._sync_btn.setText("🔓 Lock Sync")

    def _on_gt_zoom(self, factor: float) -> None:
        if self._sync_locked and not self._syncing:
            self._syncing = True
            self._pred_panel.image_label.set_zoom_silent(factor)
            self._syncing = False

    def _on_pred_zoom(self, factor: float) -> None:
        if self._sync_locked and not self._syncing:
            self._syncing = True
            self._gt_panel.image_label.set_zoom_silent(factor)
            self._syncing = False

    def _on_gt_pan(self, offset: QPoint) -> None:
        if self._sync_locked and not self._syncing:
            self._syncing = True
            self._pred_panel.image_label.set_pan_silent(offset)
            self._syncing = False

    def _on_pred_pan(self, offset: QPoint) -> None:
        if self._sync_locked and not self._syncing:
            self._syncing = True
            self._gt_panel.image_label.set_pan_silent(offset)
            self._syncing = False

    # ---- Public API ----

    def show_pair(self, pair: ImagePair) -> None:
        """Show a GT/Prediction pair.

        When prediction is missing, silently fall back to showing GT on both sides.
        """
        self._no_data_label.setVisible(False)
        self._gt_panel.setVisible(True)
        self._pred_panel.setVisible(True)
        self._sync_btn.setVisible(True)

        gt_img = load_image(pair.gt_path) if pair.gt_path else None
        if gt_img is not None:
            self._gt_panel.show_image(gt_img, pair.filename, label="Ground Truth")
        else:
            self._gt_panel.clear()

        if pair.pred_path and not pair.pred_missing:
            pred_img = load_image(pair.pred_path)
            if pred_img is not None:
                self._pred_panel.show_image(pred_img, pair.filename, label="Prediction")
            else:
                # Prediction image failed to load, show GT fallback
                if gt_img is not None:
                    self._pred_panel.show_image(
                        gt_img, pair.filename, label="(GT fallback)"
                    )
                else:
                    self._pred_panel.clear()
        else:
            # No prediction available: silently show GT on both sides
            if gt_img is not None:
                self._pred_panel.show_image(
                    gt_img, pair.filename, label="(GT fallback)"
                )
            else:
                self._pred_panel.clear()

    def show_fallback(self, pair: ImagePair) -> None:
        """Fallback mode: show GT on both sides."""
        self._no_data_label.setVisible(False)
        self._gt_panel.setVisible(True)
        self._pred_panel.setVisible(True)
        self._sync_btn.setVisible(True)

        gt_img = load_image(pair.gt_path) if pair.gt_path else None
        if gt_img is not None:
            self._gt_panel.show_image(gt_img, pair.filename, label="Ground Truth")
            self._pred_panel.show_image(
                gt_img, pair.filename, label="(GT fallback)"
            )
        else:
            self._gt_panel.clear()
            self._pred_panel.clear()

    def show_no_data(self) -> None:
        self._gt_panel.setVisible(False)
        self._pred_panel.setVisible(False)
        self._sync_btn.setVisible(False)
        self._no_data_label.setVisible(True)
        self._no_data_label.setText("No Ground Truth Dataset Found")
