"""Side-by-side image comparison view with zoom, pan, and sync."""
from __future__ import annotations
from typing import List, Optional

import numpy as np
from PySide6.QtCore import Qt, QPoint, QPointF, Signal
from PySide6.QtGui import QImage, QPixmap, QPainter, QColor, QPen, QBrush
from PySide6.QtWidgets import (
    QComboBox,
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
    """A QLabel that supports zoom, pan, double-click reset, and scatter overlay."""

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
        self._dark: bool = False
        # Scatter overlay data (in image pixel coordinates)
        self._scatter_x: Optional[np.ndarray] = None
        self._scatter_y: Optional[np.ndarray] = None
        self._scatter_colors: Optional[list] = None
        self._scatter_sizes: Optional[np.ndarray] = None
        self._scatter_labels: Optional[list] = None
        # Click-highlight state (indices into self._scatter_* arrays)
        self._highlight_indices: Optional[set] = None
        # Track press position to distinguish click from drag
        self._press_pos: Optional[QPoint] = None
        self._press_active: bool = False

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
        self._scatter_x = None
        self._scatter_y = None
        self._scatter_colors = None
        self._scatter_sizes = None
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

    def set_scatter_data(
        self,
        x: np.ndarray,
        y: np.ndarray,
        colors: list,
        sizes: np.ndarray | None = None,
        labels: Optional[list] = None,
    ) -> None:
        """Store scatter overlay data in image pixel coordinates.

        `labels` is an optional list of per-point label names. When
        provided, click-to-highlight groups points by label value.
        """
        self._scatter_x = np.asarray(x, dtype=np.float64)
        self._scatter_y = np.asarray(y, dtype=np.float64)
        self._scatter_colors = colors
        self._scatter_sizes = sizes
        self._scatter_labels = labels
        self._highlight_indices = None
        self._update_display()

    def clear_scatter(self) -> None:
        """Remove scatter overlay."""
        self._scatter_x = None
        self._scatter_y = None
        self._scatter_colors = None
        self._scatter_sizes = None
        self._scatter_labels = None
        self._highlight_indices = None
        self._update_display()

    def clear_highlight(self) -> None:
        """Drop click-highlight state and repaint."""
        if self._highlight_indices is None:
            return
        self._highlight_indices = None
        self._update_display()

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
        ow = self._original_pixmap.width()
        oh = self._original_pixmap.height()
        scaled = self._original_pixmap.scaled(
            int(ow * self._zoom_factor),
            int(oh * self._zoom_factor),
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        pm = QPixmap(scaled.size())
        pm.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pm)
        painter.drawPixmap(self._pan_offset, scaled)

        # Draw scatter points on top of the image
        if self._scatter_x is not None and len(self._scatter_x) > 0:
            scale_x = scaled.width() / ow
            scale_y = scaled.height() / oh
            base_radius = max(2.5, min(ow, oh) * 0.0045)
            has_highlight = (
                self._highlight_indices is not None
                and len(self._highlight_indices) > 0
            )

            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            for i in range(len(self._scatter_x)):
                sx = self._scatter_x[i] * scale_x + self._pan_offset.x()
                sy = self._scatter_y[i] * scale_y + self._pan_offset.y()
                radius = base_radius * self._zoom_factor
                radius = max(1.8, min(radius, 12.0))
                color = self._scatter_colors[i]
                qc = QColor(*color)
                if has_highlight:
                    if i in self._highlight_indices:
                        # Highlighted: same size, full alpha, dark outline
                        qc.setAlpha(255)
                        painter.setPen(QPen(QColor(20, 20, 20, 220), 1.0))
                        painter.setBrush(QBrush(qc))
                        painter.drawEllipse(QPointF(sx, sy), radius, radius)
                    else:
                        # Dimmed: same size, half-transparent
                        qc.setAlpha(110)
                        painter.setPen(Qt.PenStyle.NoPen)
                        painter.setBrush(QBrush(qc))
                        painter.drawEllipse(QPointF(sx, sy), radius, radius)
                else:
                    qc.setAlpha(220)
                    painter.setPen(Qt.PenStyle.NoPen)
                    painter.setBrush(QBrush(qc))
                    painter.drawEllipse(QPointF(sx, sy), radius, radius)

        painter.end()
        self.setPixmap(pm)

    # ---- Events ----

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_active = True
            self._press_active = True
            self._pan_start = event.position().toPoint()
            self._press_pos = event.position().toPoint()
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
            was_pressed = self._press_active
            press_pos = self._press_pos
            release_pos = event.position().toPoint()
            self._drag_active = False
            self._press_active = False
            self._pan_start = None
            self._press_pos = None
            self.setCursor(Qt.CursorShape.ArrowCursor)
            if was_pressed and press_pos is not None:
                if (release_pos - press_pos).manhattanLength() < 4:
                    self._handle_click(release_pos)

    def mouseDoubleClickEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self.reset_view()

    def wheelEvent(self, event) -> None:
        delta = event.angleDelta().y()
        factor = 1.15 if delta > 0 else 1.0 / 1.15
        self._apply_zoom(self._zoom_factor * factor)

    # ---- Click highlight ----

    def _find_scatter_at(self, pos):
        # Return index of the nearest scatter point to pos within tolerance.
        if (
            self._scatter_x is None
            or self._scatter_y is None
            or len(self._scatter_x) == 0
        ):
            return None
        pm = self.pixmap()
        if pm is None or pm.isNull():
            return None
        if self._original_pixmap is None:
            return None
        ow = self._original_pixmap.width()
        oh = self._original_pixmap.height()
        if ow == 0 or oh == 0:
            return None

        label_w = self.width()
        label_h = self.height()
        pm_w = pm.width()
        pm_h = pm.height()
        offset_x = (label_w - pm_w) / 2.0
        offset_y = (label_h - pm_h) / 2.0
        cx_pm = pos.x() - offset_x
        cy_pm = pos.y() - offset_y
        if cx_pm < 0 or cy_pm < 0 or cx_pm >= pm_w or cy_pm >= pm_h:
            return None

        inv_z = 1.0 / self._zoom_factor if self._zoom_factor else 0.0
        sx_target = (cx_pm - self._pan_offset.x()) * inv_z
        sy_target = (cy_pm - self._pan_offset.y()) * inv_z

        dx = self._scatter_x - sx_target
        dy = self._scatter_y - sy_target
        dist = np.hypot(dx, dy)
        nearest = int(np.argmin(dist))
        if dist[nearest] <= 10.0:
            return nearest
        return None

    def _handle_click(self, pos):
        # Toggle highlight for the label group containing pos. Empty = clear.
        hit = self._find_scatter_at(pos)
        if hit is None:
            self.clear_highlight()
            return

        labels = self._scatter_labels
        if labels is not None and hit < len(labels):
            target = labels[hit]
            self._highlight_indices = {
                i for i, lbl in enumerate(labels) if lbl == target
            }
        else:
            target_color = self._scatter_colors[hit]
            self._highlight_indices = {
                i
                for i, c in enumerate(self._scatter_colors)
                if tuple(c) == tuple(target_color)
            }
        self._update_display()



class ImagePanel(QWidget):
    """Single image panel with title, image, and optional label."""

    def __init__(self, title: str, parent: QWidget | None = None):
        super().__init__(parent)
        self._dark: bool = False

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

    def show_overlay(
        self,
        image: np.ndarray,
        scatter_x: np.ndarray,
        scatter_y: np.ndarray,
        scatter_colors: list,
        filename: str,
        label: str = "",
        scatter_labels: list | None = None,
    ) -> None:
        """Show image with scatter points overlaid."""
        self.image_label.set_image(image)
        self.image_label.set_scatter_data(
            scatter_x, scatter_y, scatter_colors, labels=scatter_labels
        )
        self._title.setText(f"{self._title.text().split(':')[0]}: {filename}")
        self._label.setText(label)

    def clear(self) -> None:
        self.image_label.clear_image()
        self.image_label.clear_highlight()
        self._label.setText("")



# ---- Helper: load scatter data from spatial datasets ----

# Qualitative palette with strong light/dark contrast: warm layers
# use the light (Flat-UI) variants, cool layers use the dark variants
# so adjacent cool layers (green / blue / purple) are clearly distinct.
_CLUSTER_COLORS = {
    "Layer1":    (231,  76,  60),   # #E74C3C  light red
    "Layer2":    (230, 126,  34),   # #E67E22  light orange
    "Layer3":    (241, 196,  15),   # #F1C40F  light yellow
    "Layer4":    ( 39, 174,  96),   # #27AE60  DARK green
    "Layer5":    ( 41, 128, 185),   # #2980B9  DARK blue
    "Layer6":    (142,  68, 173),   # #8E44AD  DARK purple
    "WM":        (127, 140, 141),   # #7F8C8D  medium gray
    "Unlabeled": ( 44,  62,  80),   # #2C3E50  dark slate
}
_FALLBACK_RGB = [
    # Light warm
    (231,  76,  60), (230, 126,  34), (241, 196,  15),
    # Dark cool
    ( 39, 174,  96), ( 41, 128, 185), (142,  68, 173),
    # Mixed extras
    (192,  57,  43), (211,  84,   0), (243, 156,  18),
    ( 22, 160, 133), ( 31,  97, 141), (108,  52, 131),
]

def _normalize_label(label):
    """Normalize label: 'Layer1' -> 1, '1' -> 1, 'WM' -> 0, '' -> None."""
    if not label or str(label).upper() == "NA":
        return None
    s = str(label).strip()
    if s.startswith("Layer"):
        try:
            return int(s[5:])
        except ValueError:
            pass
    if s == "WM":
        return 0
    try:
        return int(s)
    except ValueError:
        return None

def _get_color(name):
    """Get RGB tuple for a cluster name."""
    c = _CLUSTER_COLORS.get(name)
    if c is None:
        c = _FALLBACK_RGB[sum(ord(ch) for ch in str(name)) % len(_FALLBACK_RGB)]
    return c


# ---------------------------------------------------------------------------
# Comparison View
# ---------------------------------------------------------------------------

class ComparisonViewWidget(QWidget):
    """Side-by-side GT vs Prediction image comparison with scatter overlay."""

    section_changed = Signal(str)

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self._dark: bool = False
        self._syncing: bool = False
        self._sync_locked: bool = False

        # Data roots for loading spatial data
        self._data_root: str = ""
        self._res_root: str = ""
        self._section_ids: list = []

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        # Sync controls
        ctrl_layout = QHBoxLayout()
        ctrl_layout.setContentsMargins(0, 0, 0, 0)

        self._sync_btn = QPushButton("Lock Sync")
        self._sync_btn.setCheckable(True)
        self._sync_btn.setChecked(False)
        self._sync_btn.setStyleSheet(_BTN_DARK)
        self._sync_btn.clicked.connect(self._on_sync_toggled)
        ctrl_layout.addWidget(self._sync_btn)

        self._reset_btn = QPushButton("Reset Highlight")
        self._reset_btn.setToolTip(
            "Clear click-highlight on both panels"
        )
        self._reset_btn.setStyleSheet(_BTN_DARK)
        self._reset_btn.clicked.connect(self._on_reset_highlight)
        ctrl_layout.addWidget(self._reset_btn)

        # Section selector
        section_label = QLabel("Section:")
        section_label.setStyleSheet(_LABEL_DARK)
        ctrl_layout.addWidget(section_label)
        self._section_combo = QComboBox()
        self._section_combo.setFixedWidth(140)
        self._section_combo.setStyleSheet(
            "QComboBox { background: #fff; color: #333; border: 1px solid #e0e0e0; border-radius: 6px; padding: 4px 10px; font-size: 12px; }"
            " QComboBox:hover { border-color: #b9d2f1; }"
        )
        self._section_combo.currentTextChanged.connect(self._on_section_changed)
        ctrl_layout.addWidget(self._section_combo)
        ctrl_layout.addStretch()

        layout.addLayout(ctrl_layout)

        # Image panels side by side
        panels_layout = QHBoxLayout()
        panels_layout.setContentsMargins(0, 0, 0, 0)
        panels_layout.setSpacing(6)

        # Wrap each panel in a QFrame for the border
        self._gt_frame = QFrame()
        self._gt_frame.setFrameStyle(QFrame.Shape.Box | QFrame.Shadow.Plain)
        self._gt_frame.setStyleSheet("QFrame { border: 2px solid #ddd; border-radius: 4px; }")
        gt_frame_layout = QVBoxLayout(self._gt_frame)
        gt_frame_layout.setContentsMargins(2, 2, 2, 2)

        self._gt_panel = ImagePanel("Ground Truth")
        gt_frame_layout.addWidget(self._gt_panel)

        self._pred_frame = QFrame()
        self._pred_frame.setFrameStyle(QFrame.Shape.Box | QFrame.Shadow.Plain)
        self._pred_frame.setStyleSheet("QFrame { border: 2px solid #ddd; border-radius: 4px; }")
        pred_frame_layout = QVBoxLayout(self._pred_frame)
        pred_frame_layout.setContentsMargins(2, 2, 2, 2)

        self._pred_panel = ImagePanel("Results")
        pred_frame_layout.addWidget(self._pred_panel)

        panels_layout.addWidget(self._gt_frame, 1)
        panels_layout.addWidget(self._pred_frame, 1)

        layout.addLayout(panels_layout)

        # No-data overlay
        self._no_data_label = QLabel("No Ground Truth Dataset Found", self)
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
        self._reset_btn.setStyleSheet(_BTN_DARK if dark else _BTN_LIGHT)
        self._no_data_label.setStyleSheet(
            _NO_DATA_DARK if dark else _NO_DATA_LIGHT
        )
        border_color = "#3a3a3e" if dark else "#ddd"
        self._gt_frame.setStyleSheet(f"QFrame {{ border: 2px solid {border_color}; border-radius: 4px; }}")
        self._pred_frame.setStyleSheet(f"QFrame {{ border: 2px solid {border_color}; border-radius: 4px; }}")
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
            self._sync_btn.setText("Sync Locked")
            if not self._gt_panel.image_label.is_default_state():
                self._gt_panel.image_label.reset_view(emit=False)
            if not self._pred_panel.image_label.is_default_state():
                self._pred_panel.image_label.reset_view(emit=False)
        else:
            self._sync_btn.setText("Lock Sync")

    def _on_reset_highlight(self) -> None:
        # Clear click-highlight on both panels (GT and Results stay independent).
        self._gt_panel.image_label.clear_highlight()
        self._pred_panel.image_label.clear_highlight()

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

    # ---- Data roots ----

    def set_sections(self, section_ids):
        """Populate the section selector combo box."""
        self._section_ids = list(section_ids)
        if self._section_combo is None:
            return
        self._section_combo.blockSignals(True)
        self._section_combo.clear()
        self._section_combo.addItems(section_ids)
        self._section_combo.blockSignals(False)

    def set_current_section(self, section_id):
        """Select a section in the combo without emitting signal."""
        if self._section_combo is None:
            return
        self._section_combo.blockSignals(True)
        idx = self._section_combo.findText(section_id)
        if idx >= 0:
            self._section_combo.setCurrentIndex(idx)
        self._section_combo.blockSignals(False)

    def _on_section_changed(self, text):
        """Emit when user selects a different section."""
        if text and self._section_ids:
            self.section_changed.emit(text)

    def set_data_roots(self, data_root: str, res_root: str) -> None:
        """Set paths for loading GT and Results spatial data."""
        self._data_root = data_root
        self._res_root = res_root

    # ---- Public API ----

    def show_pair(self, pair: ImagePair) -> None:
        """Show a GT/Prediction image pair (fallback: images only, no scatter)."""
        self._no_data_label.setVisible(False)
        self._gt_frame.setVisible(True)
        self._pred_frame.setVisible(True)
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
            elif gt_img is not None:
                self._pred_panel.show_image(gt_img, pair.filename, label="(GT fallback)")
            else:
                self._pred_panel.clear()
        else:
            if gt_img is not None:
                self._pred_panel.show_image(gt_img, pair.filename, label="(GT fallback)")
            else:
                self._pred_panel.clear()

    def show_fallback(self, pair: ImagePair) -> None:
        """Fallback mode: show GT on both sides."""
        self._no_data_label.setVisible(False)
        self._gt_frame.setVisible(True)
        self._pred_frame.setVisible(True)
        self._sync_btn.setVisible(True)

        gt_img = load_image(pair.gt_path) if pair.gt_path else None
        if gt_img is not None:
            self._gt_panel.show_image(gt_img, pair.filename, label="Ground Truth")
            self._pred_panel.show_image(gt_img, pair.filename, label="(GT fallback)")
        else:
            self._gt_panel.clear()
            self._pred_panel.clear()

    def show_no_data(self) -> None:
        self._gt_frame.setVisible(False)
        self._pred_frame.setVisible(False)
        self._sync_btn.setVisible(False)
        self._no_data_label.setVisible(True)
        self._no_data_label.setText("No Ground Truth Dataset Found")

    # ---- Overlay (scatter on image) rendering ----

    def show_overlay_pair(self, section_id: str) -> None:
        """Show GT vs Results as tissue image + scatter points overlay.

        Loads tissue_hires_image.png as background and draws scatter points
        from the corresponding CSV files.
        """
        from pathlib import Path
        import json, csv, os

        self._no_data_label.setVisible(False)
        self._gt_frame.setVisible(True)
        self._pred_frame.setVisible(True)
        self._sync_btn.setVisible(True)

        # ---- Load GT side ----
        gt_dir = Path(self._data_root) / section_id
        gt_img_path = gt_dir / "spatial" / "tissue_hires_image.png"
        gt_csv_path = gt_dir / "spatial" / "tissue_positions_list.csv"
        gt_meta_path = gt_dir / "metadata.tsv"
        gt_scale_path = gt_dir / "spatial" / "scalefactors_json.json"

        gt_image = None
        if gt_img_path.exists():
            gt_image = load_image(gt_img_path)

        # Read scale factor
        scale = 0.15
        if gt_scale_path.exists():
            try:
                with open(gt_scale_path) as f:
                    scale = float(json.load(f).get("tissue_hires_scalef", 0.15))
            except Exception:
                pass

        # Read GT positions (filter in_tissue=1)
        gt_positions = {}
        if gt_csv_path.exists():
            with open(gt_csv_path) as f:
                for line in f:
                    parts = line.strip().split(",")
                    if len(parts) >= 6 and parts[1] == "1":
                        barcode = parts[0]
                        px_row, px_col = float(parts[4]), float(parts[5])
                        gt_positions[barcode] = (px_row * scale, px_col * scale)

        # Read GT metadata for labels
        gt_labels = {}
        if gt_meta_path.exists():
            with open(gt_meta_path, encoding="utf-8") as f:
                reader = csv.DictReader(f, delimiter="	")
                for row in reader:
                    barcode = row.get("barcode", "").strip()
                    label = row.get("layer_guess_reordered", "").strip()
                    if barcode and label and label.upper() != "NA":
                        gt_labels[barcode] = label

        # Build GT scatter data (parallel label list enables click-highlight)
        gt_sx, gt_sy, gt_colors, gt_label_list = [], [], [], []
        for barcode, (hx, hy) in gt_positions.items():
            label = gt_labels.get(barcode, "")
            if not label:
                continue
            gt_sx.append(hy)  # px_col * scale -> image x
            gt_sy.append(hx)  # px_row * scale -> image y
            gt_colors.append(_get_color(label))
            gt_label_list.append(label)

        gt_sx = np.array(gt_sx, dtype=np.float64)
        gt_sy = np.array(gt_sy, dtype=np.float64)

        # Show GT side
        if gt_image is not None and len(gt_sx) > 0:
            self._gt_panel.show_overlay(
                gt_image, gt_sx, gt_sy, gt_colors,
                filename=section_id,
                label=f"Ground Truth ({len(gt_sx)} cells)",
                scatter_labels=gt_label_list,
            )
        elif gt_image is not None:
            self._gt_panel.show_image(gt_image, section_id, label="Ground Truth (no data)")
        else:
            self._gt_panel.clear()

        # ---- Load Results side ----
        res_dir = Path(self._res_root) / section_id if self._res_root else None
        res_csv_path = res_dir / "spatial" / "tissue_positions_list.csv" if res_dir else None

        res_sx, res_sy, res_colors, res_label_list = [], [], [], []
        res_has_data = False

        if res_csv_path and res_csv_path.exists():
            with open(res_csv_path) as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    parts = line.split(",")
                    # Accept 6 or 7 column format
                    if len(parts) < 6:
                        continue
                    barcode = parts[0].strip()
                    in_tissue = parts[1].strip()
                    if in_tissue != "1" or not barcode:
                        continue
                    px_row = float(parts[4])
                    px_col = float(parts[5])
                    # Domain: 7th column if non-empty, otherwise use "Unlabeled"
                    if len(parts) >= 7 and parts[6].strip():
                        domain = parts[6].strip()
                    else:
                        domain = ""
                    hx = px_row * scale  # image y
                    hy = px_col * scale  # image x

                    if domain:
                        # Map domain to layer color + canonical label
                        norm = _normalize_label(domain)
                        if norm is not None:
                            if norm == 0:
                                color = _get_color("WM")
                                can_label = "WM"
                            else:
                                color = _get_color(f"Layer{norm}")
                                can_label = f"Layer{norm}"
                        else:
                            color = _get_color(domain)
                            can_label = domain
                    else:
                        color = _get_color("Unlabeled")
                        can_label = "Unlabeled"

                    res_sx.append(hy)  # px_col * scale -> image x
                    res_sy.append(hx)  # px_row * scale -> image y
                    res_colors.append(color)
                    res_label_list.append(can_label)

            res_sx = np.array(res_sx, dtype=np.float64)
            res_sy = np.array(res_sy, dtype=np.float64)
            res_has_data = len(res_sx) > 0

        # Show Results side
        if res_has_data:
            # Use GT image as background for results side too
            bg_img = gt_image if gt_image is not None else (
                load_image(gt_img_path) if gt_img_path.exists() else None
            )
            if bg_img is not None:
                self._pred_panel.show_overlay(
                    bg_img, res_sx, res_sy, res_colors,
                    filename=section_id,
                    label=f"Results ({len(res_sx)} cells)",
                    scatter_labels=res_label_list,
                )
            else:
                self._pred_panel.clear()
        else:
            # No results data: show GT image without scatter
            if gt_image is not None:
                self._pred_panel.show_image(gt_image, section_id, label="(no Results data)")
            else:
                self._pred_panel.clear()

