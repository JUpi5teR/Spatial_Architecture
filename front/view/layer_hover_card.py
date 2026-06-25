# coding: utf-8
"""In-panel hover card showing cortical layer info for a clicked scatter point.

Child of an ImagePanel (or similar container), positioned absolutely.
Stays within parent bounds. Draggable. Auto-hides after 8 seconds.
"""
from __future__ import annotations

from PySide6.QtCore import Qt, QPoint, QTimer
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen, QBrush
from PySide6.QtWidgets import (
    QFrame, QLabel, QSizePolicy, QVBoxLayout,
)

from model.layer_info import lookup_layer


class LayerHoverCard(QFrame):
    """Floating card inside a parent panel, showing layer histology info.

    Usage per panel:
        card = LayerHoverCard(panel)
        card.show_for_label("Layer3")
        card.hide()   # or auto-hides after 8s
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self._dark = False
        self._dragging = False
        self._drag_start = QPoint()

        self.setObjectName("layerHoverCard")
        self.setFixedWidth(240)
        self.setVisible(False)
        self.setCursor(Qt.CursorShape.OpenHandCursor)

        self._build_ui()
        self._apply_theme()
        self.setVisible(False)

        self._hide_timer = QTimer(self)
        self._hide_timer.setSingleShot(True)
        self._hide_timer.setInterval(8000)
        self._hide_timer.timeout.connect(self._hide)

    def set_dark(self, dark):
        self._dark = dark
        self._apply_theme()

    def show_for_label(self, label, source=""):
        info = lookup_layer(label)
        if info is None:
            self._hide()
            return

        self._title.setText(info.name_cn + "  (" + info.layer_id + ")")
        self._en_name.setText(info.name_en)
        self._neuron.setText("Neuron: " + info.neuron_type)
        self._thickness.setText("Thickness: " + info.thickness)
        self._source.setText("Source: " + source if source else "")

        self.adjustSize()
        self._position_default()
        self.setVisible(True)
        self.raise_()
        self._hide_timer.start()

    def _hide(self):
        self._hide_timer.stop()
        self.setVisible(False)

    def _position_default(self):
        pw = self.parent().width() if self.parent() else 400
        self.move(max(0, pw - self.width() - 6), 6)

    def _clamp(self):
        if not self.parent():
            return
        pw, ph = self.parent().width(), self.parent().height()
        x = max(0, min(self.x(), pw - self.width()))
        y = max(0, min(self.y(), ph - self.height()))
        self.move(x, y)

    def _apply_theme(self):
        if self._dark:
            bg, border, pri, sec = "#2c2c2e", "#3a3a3c", "#f5f5f7", "#98989d"
            shadow = QColor(0, 0, 0, 80)
        else:
            bg, border, pri, sec = "#ffffff", "#d1d1d6", "#1d1d1f", "#6e6e73"
            shadow = QColor(0, 0, 0, 30)

        self._bg = bg
        self._border = border
        self._shadow = shadow

        # Make background transparent so paintEvent draws it
        self.setStyleSheet(
            "QFrame#layerHoverCard { background: transparent; border: none; }"
        )
        self._title.setStyleSheet(
            f"font-size: 13px; font-weight: 700; color: {pri}; background: transparent;"
        )
        self._en_name.setStyleSheet(
            f"font-size: 11px; color: {sec}; font-style: italic; background: transparent;"
        )
        self._neuron.setStyleSheet(
            f"font-size: 12px; color: {pri}; background: transparent;"
        )
        self._thickness.setStyleSheet(
            f"font-size: 12px; color: {pri}; background: transparent;"
        )
        self._source.setStyleSheet(
            f"font-size: 10px; color: {sec}; background: transparent;"
        )
        self.update()

    def _build_ui(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(14, 10, 14, 10)
        outer.setSpacing(3)

        self._title = QLabel("")
        self._title.setWordWrap(True)
        outer.addWidget(self._title)

        self._en_name = QLabel("")
        outer.addWidget(self._en_name)

        sep = QFrame()
        sep.setFixedHeight(1)
        sep.setFrameShape(QFrame.Shape.HLine)
        outer.addWidget(sep)

        self._neuron = QLabel("")
        self._neuron.setWordWrap(True)
        outer.addWidget(self._neuron)

        self._thickness = QLabel("")
        outer.addWidget(self._thickness)

        self._source = QLabel("")
        outer.addWidget(self._source)

    # ---- drag ----

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._dragging = True
            self._drag_start = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._dragging:
            new_global = event.globalPosition().toPoint() - self._drag_start
            if self.parent():
                local = self.parent().mapFromGlobal(new_global)
                self.move(local)
            else:
                self.move(new_global)
            self._clamp()
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and self._dragging:
            self._dragging = False
            self.setCursor(Qt.CursorShape.OpenHandCursor)
            self._hide_timer.start()
            event.accept()
            return
        super().mouseReleaseEvent(event)

    # ---- paint ----

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)

        r = self.rect().adjusted(2, 2, -2, -2)

        # Shadow
        sh = QPainterPath()
        sh.addRoundedRect(r.translated(1, 2), 10, 10)
        p.fillPath(sh, self._shadow)

        # Card
        bg_path = QPainterPath()
        bg_path.addRoundedRect(r, 10, 10)
        p.fillPath(bg_path, QColor(self._bg))

        # Border
        p.setPen(QPen(QColor(self._border), 1))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRoundedRect(r, 10, 10)

        p.end()