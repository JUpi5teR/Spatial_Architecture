# coding: utf-8
"""Loading overlay widget - blocks interaction during async operations."""
from __future__ import annotations

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QPainter, QColor, QPen, QFont
from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel


class LoadingOverlay(QWidget):
    """A semi-transparent overlay with spinning indicator.

    Usage:
        overlay = LoadingOverlay(parent_widget)
        overlay.show()          # Blocks interaction, shows spinner
        # ... do work ...
        overlay.hide()          # Restores interaction
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, False)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet("background: rgba(0, 0, 0, 0.35);")

        # Spin animation
        self._angle = 0
        self._timer = QTimer(self)
        self._timer.setInterval(30)
        self._timer.timeout.connect(self._on_tick)
        self._visible = False

        # Label
        self._label = QLabel("Loading...", self)
        self._label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._label.setStyleSheet(
            "background: transparent; color: #fff; font-size: 16px; font-weight: 600;"
        )

        self.hide()

    def show(self):
        """Show overlay and start animation."""
        self._visible = True
        self._angle = 0
        self._timer.start()
        if self.parent():
            self.setGeometry(self.parent().rect())
        super().show()
        self.raise_()
        # Force immediate paint so overlay appears before blocking work
        QApplication.processEvents()
        self.repaint()

    def hide(self):
        """Hide overlay and stop animation."""
        self._visible = False
        self._timer.stop()
        super().hide()

    def resizeEvent(self, event):
        """Track parent size changes."""
        super().resizeEvent(event)
        if self.parent():
            self.setGeometry(self.parent().rect())
        # Center the label
        self._label.setGeometry(0, 0, self.width(), self.height())

    def paintEvent(self, event):
        """Draw semi-transparent background + spinning arc."""
        super().paintEvent(event)
        if not self._visible:
            return

        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # Center position
        cx = self.width() / 2
        cy = self.height() / 2 - 20
        radius = 32

        # Draw arc
        pen = QPen(QColor("#ffffff"), 5)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(pen)

        span = 270 * 16  # 270 degrees in 1/16th degree units
        painter.drawArc(
            int(cx - radius), int(cy - radius),
            int(radius * 2), int(radius * 2),
            self._angle * 16, span,
        )

        painter.end()

    def _on_tick(self):
        """Update rotation angle."""
        self._angle = (self._angle + 12) % 360
        self.update()
