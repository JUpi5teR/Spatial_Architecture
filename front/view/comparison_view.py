from typing import Optional

import numpy as np
from PySide6.QtCore import Qt, QPoint, Signal
from PySide6.QtGui import QImage, QPixmap, QPainter, QMouseEvent, QWheelEvent
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

_IMAGE_BG_DARK = "#1e1e1e"
_IMAGE_BG_LIGHT = "#555555"

_TITLE_STYLE_DARK = "font-weight: bold; font-size: 14px; color: #ecf0f1; padding: 4px;"
_TITLE_STYLE_LIGHT = "font-weight: bold; font-size: 14px; color: #2c3e50; padding: 4px;"

_SCROLL_DARK = "background-color: #1e1e1e; border: 1px solid #444;"
_SCROLL_LIGHT = "background-color: #555555; border: 1px solid #bbb;"

_SEP_DARK = "color: #555;"
_SEP_LIGHT = "color: #ccc;"

_BTN_DARK = (
    "QPushButton { font-size: 12px; padding: 2px 12px; "
    "border: 1px solid #666; border-radius: 4px; background: #333; color: #eee; }"
    "QPushButton:hover { background: #555; }"
    "QPushButton:checked { background: #27ae60; color: #fff; border-color: #27ae60; }"
)
_BTN_LIGHT = (
    "QPushButton { font-size: 12px; padding: 2px 12px; "
    "border: 1px solid #aaa; border-radius: 4px; background: #f0f0f0; color: #222; }"
    "QPushButton:hover { background: #ddd; }"
    "QPushButton:checked { background: #27ae60; color: #fff; border-color: #27ae60; }"
)

_NO_DATA_DARK = "color: #95a5a6; font-size: 18px;"
_NO_DATA_LIGHT = "color: #7f8c8d; font-size: 18px;"


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
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
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
        qimage = QImage(image.data, w, h, bytes_per_line, QImage.Format.Format_RGB888)
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

    # ---- Event handlers ----

    def wheelEvent(self, event: QWheelEvent) -> None:
        if self._original_pixmap is None:
            return
        delta = event.angleDelta().y()
        if delta > 0:
            new_zoom = min(self._zoom_factor * 1.15, self._max_zoom)
        else:
            new_zoom = max(self._zoom_factor / 1.15, self._min_zoom)
        self._apply_zoom(new_zoom)
        event.accept()

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton and self._original_pixmap:
            self._drag_active = True
            self._pan_start = event.position().toPoint()
            self.setCursor(Qt.CursorStyle.ClosedHandCursor)
            event.accept()
        else:
            super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if self._drag_active and self._pan_start:
            delta = event.position().toPoint() - self._pan_start
            new_offset = self._pan_offset + delta
            self._pan_start = event.position().toPoint()
            self._apply_pan(new_offset)
            event.accept()
        else:
            super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton and self._drag_active:
            self._drag_active = False
            self.setCursor(Qt.CursorStyle.ArrowCursor)
            event.accept()
        else:
            super().mouseReleaseEvent(event)

    def mouseDoubleClickEvent(self, event: QMouseEvent) -> None:
        if self._original_pixmap:
            self.reset_view(emit=True)
        event.accept()


class ImagePanel(QWidget):
    """One side of the comparison view (image + filename label)."""

    def __init__(self, title: str = "", parent: QWidget | None = None):
        super().__init__(parent)
        self._dark: bool = True

        layout = QVBoxLayout(self)
        layout.setContentsMargins(2, 2, 2, 2)
        layout.setSpacing(4)

        self._title = QLabel(title)
        self._title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._title.setStyleSheet(_TITLE_STYLE_DARK)

        self._notice = QLabel("")
        self._notice.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._notice.setStyleSheet("color: #f39c12; font-size: 12px;")

        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setStyleSheet(_SCROLL_DARK)
        self._image_label = ZoomableImageLabel()
        self._scroll.setWidget(self._image_label)

        layout.addWidget(self._title)
        layout.addWidget(self._notice)
        layout.addWidget(self._scroll, 1)

    def update_theme(self, dark: bool) -> None:
        self._dark = dark
        self._title.setStyleSheet(_TITLE_STYLE_DARK if dark else _TITLE_STYLE_LIGHT)
        self._scroll.setStyleSheet(_SCROLL_DARK if dark else _SCROLL_LIGHT)
        self._image_label.update_theme(dark)

    @property
    def image_label(self) -> ZoomableImageLabel:
        return self._image_label

    def show_image(
        self, image: np.ndarray, filename: str, notice: str = ""
    ) -> None:
        self._title.setText(filename)
        if notice:
            self._notice.setText(notice)
        else:
            self._notice.clear()
        self._image_label.set_image(image)

    def clear(self) -> None:
        self._title.setText("")
        self._notice.clear()
        self._image_label.clear_image()


class ComparisonViewWidget(QWidget):
    """Bottom comparison view with lock-sync support."""

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self._dark: bool = True

        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)

        # Sync toggle button
        self._sync_btn = QPushButton("🔓 锁定同步")
        self._sync_btn.setCheckable(True)
        self._sync_btn.setFixedHeight(28)
        self._sync_btn.setStyleSheet(_BTN_DARK)
        self._sync_btn.toggled.connect(self._on_sync_toggled)

        # Image panels
        panels_layout = QHBoxLayout()
        panels_layout.setContentsMargins(0, 0, 0, 0)

        self._gt_panel = ImagePanel("Ground Truth")
        self._pred_panel = ImagePanel("Prediction")

        self._sep = QFrame()
        self._sep.setFrameShape(QFrame.Shape.VLine)
        self._sep.setStyleSheet(_SEP_DARK)

        panels_layout.addWidget(self._gt_panel, 1)
        panels_layout.addWidget(self._sep)
        panels_layout.addWidget(self._pred_panel, 1)

        # No-data label
        self._no_data_label = QLabel("No Ground Truth Dataset Found")
        self._no_data_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._no_data_label.setStyleSheet(_NO_DATA_DARK)

        layout.addWidget(self._sync_btn)
        layout.addLayout(panels_layout, 1)

        self._no_data_label.setParent(self)
        self._no_data_label.setVisible(False)

        # Sync state
        self._sync_locked: bool = False
        self._syncing: bool = False

        # Wire signals
        self._gt_panel.image_label.zoom_changed.connect(self._on_gt_zoom)
        self._gt_panel.image_label.pan_changed.connect(self._on_gt_pan)
        self._pred_panel.image_label.zoom_changed.connect(self._on_pred_zoom)
        self._pred_panel.image_label.pan_changed.connect(self._on_pred_pan)

    def update_theme(self, dark: bool) -> None:
        """Propagate theme to all children."""
        self._dark = dark
        self._sync_btn.setStyleSheet(_BTN_DARK if dark else _BTN_LIGHT)
        self._sep.setStyleSheet(_SEP_DARK if dark else _SEP_LIGHT)
        self._no_data_label.setStyleSheet(_NO_DATA_DARK if dark else _NO_DATA_LIGHT)
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
            self._sync_btn.setText("🔒 同步已锁定")
            if not self._gt_panel.image_label.is_default_state():
                self._gt_panel.image_label.reset_view(emit=False)
            if not self._pred_panel.image_label.is_default_state():
                self._pred_panel.image_label.reset_view(emit=False)
        else:
            self._sync_btn.setText("🔓 锁定同步")

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
        self._no_data_label.setVisible(False)
        self._gt_panel.setVisible(True)
        self._sep.setVisible(True)
        self._pred_panel.setVisible(True)
        self._sync_btn.setVisible(True)

        gt_img = load_image(pair.gt_path) if pair.gt_path else None
        if gt_img is not None:
            self._gt_panel.show_image(gt_img, pair.filename)
        else:
            self._gt_panel.clear()
            self._gt_panel._title.setText(pair.filename)
            self._gt_panel._notice.setText("Load Error")

        if pair.pred_path and not pair.pred_missing:
            pred_img = load_image(pair.pred_path)
            if pred_img is not None:
                self._pred_panel.show_image(pred_img, pair.filename)
            else:
                self._pred_panel.clear()
                self._pred_panel._title.setText(pair.filename)
                self._pred_panel._notice.setText("Load Error")
        else:
            gt_img_fallback = load_image(pair.gt_path) if pair.gt_path else None
            if gt_img_fallback is not None:
                self._pred_panel.show_image(
                    gt_img_fallback,
                    pair.filename,
                    notice="Prediction Missing\nShowing Ground Truth Only",
                )
            else:
                self._pred_panel.clear()
                self._pred_panel._title.setText(pair.filename)
                self._pred_panel._notice.setText("Prediction Missing")

    def show_fallback(self, pair: ImagePair) -> None:
        self._no_data_label.setVisible(False)
        self._gt_panel.setVisible(True)
        self._sep.setVisible(True)
        self._pred_panel.setVisible(True)
        self._sync_btn.setVisible(True)

        gt_img = load_image(pair.gt_path) if pair.gt_path else None
        if gt_img is not None:
            self._gt_panel.show_image(gt_img, pair.filename)
            self._pred_panel.show_image(
                gt_img,
                pair.filename,
                notice="No Training Result Available\nShowing Ground Truth Only",
            )
        else:
            self._gt_panel.clear()
            self._pred_panel.clear()
            self._gt_panel._title.setText(pair.filename)
            self._pred_panel._title.setText(pair.filename)

    def show_no_data(self) -> None:
        self._gt_panel.setVisible(False)
        self._sep.setVisible(False)
        self._pred_panel.setVisible(False)
        self._sync_btn.setVisible(False)
        self._no_data_label.setVisible(True)
        self._no_data_label.setText("No Ground Truth Dataset Found")
