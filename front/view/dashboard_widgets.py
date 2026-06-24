# coding: utf-8
"""Dashboard widgets for the overview page.

All charts are painted with QPainter so the dashboard has no hard
dependency on matplotlib (whose numpy ABI currently conflicts with the
shipped environment). Each widget is theme-aware via set_dark().
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import List, Optional, Sequence

from PySide6.QtCore import Qt, QRectF, QPointF, QSize, Signal
from PySide6.QtGui import (
    QColor, QFont, QPainter, QPainterPath, QPen, QBrush,
    QLinearGradient,
)
from PySide6.QtWidgets import (
    QComboBox, QFrame, QGridLayout, QHBoxLayout, QLabel,
    QSizePolicy, QVBoxLayout, QWidget,
)

from front.model.dashboard_data import (
    CurvePoint, DashboardSnapshot, METRICS, MetricSummary,
)

# ---- Theme tokens (light + dark) ----
_FONT_STACK = (
    '-apple-system, BlinkMacSystemFont, "SF Pro Display", '
    '"SF Pro Text", "Segoe UI Variable", "Segoe UI", '
    'Helvetica, Arial, sans-serif'
)

BG_LIGHT = "#f5f5f7"
SURFACE_LIGHT = "#ffffff"
SURFACE_ALT_LIGHT = "#fbfbfd"
DIVIDER_LIGHT = "#e3e3e8"
TXT_PRI_LIGHT = "#1d1d1f"
TXT_SEC_LIGHT = "#6e6e73"
TXT_TER_LIGHT = "#86868b"

BG_DARK = "#1c1c1e"
SURFACE_DARK = "#2c2c2e"
SURFACE_ALT_DARK = "#242426"
DIVIDER_DARK = "#3a3a3c"
TXT_PRI_DARK = "#f5f5f7"
TXT_SEC_DARK = "#98989d"
TXT_TER_DARK = "#6e6e73"

# Brand palette (consistent across metrics).
PRIMARY_COLOR = "#0a84ff"
PRIMARY_COLOR_DARK = "#0a84ff"
ACCENT_GRADIENT_LIGHT = ("#0071e3", "#5e5ce6")
ACCENT_GRADIENT_DARK = ("#0a84ff", "#bf5af2")


def _is_higher_better(metric: str) -> bool:
    return metric in {"ari", "nmi", "hs", "cs"}


def _fmt(value, digits: int = 4) -> str:
    if value is None:
        return "-"
    return f"{value:.{digits}f}"


def _shadow_layers(dark: bool, hover: bool = False):
    """Reuse the Apple-style layered shadow recipe from the homepage."""
    if hover:
        layers = ((16, 10), (10, 22), (4, 38))
    else:
        layers = ((12, 6), (7, 14), (3, 26))
    if dark:
        layers = tuple((dy, a + 10) for dy, a in layers)
    return layers


def _paint_card_surface(p: QPainter, rect: QRectF, radius: float, color: QColor,
                        dark: bool, hover: bool = False) -> None:
    for dy, alpha in _shadow_layers(dark, hover):
        sr = QRectF(rect)
        sr.translate(0, dy)
        path = QPainterPath()
        path.addRoundedRect(sr, radius, radius)
        p.fillPath(path, QColor(0, 0, 0, alpha))
    sp = QPainterPath()
    sp.addRoundedRect(rect, radius, radius)
    p.fillPath(sp, color)


# ============================================================================
# KPI card
# ============================================================================
class KpiCard(QFrame):
    """Compact stat card. Shows label, value, optional sub-text."""

    def __init__(self, label: str, accent: str = PRIMARY_COLOR,
                 parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._label = label
        self._value = "-"
        self._sub = ""
        self._accent = accent
        self._dark = False
        self.setObjectName("kpiCard")
        self.setMinimumHeight(110)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 14, 18, 14)
        layout.setSpacing(6)

        self._label_lbl = QLabel(label)
        self._label_lbl.setObjectName("kpiLabel")
        layout.addWidget(self._label_lbl)

        self._value_lbl = QLabel("-")
        self._value_lbl.setObjectName("kpiValue")
        layout.addWidget(self._value_lbl)

        self._sub_lbl = QLabel("")
        self._sub_lbl.setObjectName("kpiSub")
        self._sub_lbl.setWordWrap(True)
        layout.addWidget(self._sub_lbl)
        layout.addStretch(1)

        self._apply_text()

    def set_value(self, value: str, sub: str = "") -> None:
        self._value_lbl.setText(value)
        self._sub_lbl.setText(sub)
        self._sub_lbl.setVisible(bool(sub))

    def set_dark(self, dark: bool) -> None:
        self._dark = dark
        self._apply_text()

    def paintEvent(self, event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        rect = QRectF(8, 6, self.width() - 16, self.height() - 16)
        surface = QColor(SURFACE_DARK if self._dark else SURFACE_LIGHT)
        _paint_card_surface(p, rect, 14.0, surface, self._dark)
        accent_rect = QRectF(rect.left() + 2, rect.top() + 14, 3, rect.height() - 28)
        accent_path = QPainterPath()
        accent_path.addRoundedRect(accent_rect, 1.5, 1.5)
        p.fillPath(accent_path, QColor(self._accent))
        p.end()

    def _apply_text(self) -> None:
        dark = self._dark
        pri = TXT_PRI_DARK if dark else TXT_PRI_LIGHT
        sec = TXT_SEC_DARK if dark else TXT_SEC_LIGHT
        ter = TXT_TER_DARK if dark else TXT_TER_LIGHT
        self._label_lbl.setStyleSheet(
            f"font-family: {_FONT_STACK}; font-size: 11px; font-weight: 700;"
            f" letter-spacing: 0.6px; text-transform: uppercase;"
            f" color: {ter}; background: transparent;"
        )
        self._value_lbl.setStyleSheet(
            f"font-family: {_FONT_STACK}; font-size: 26px; font-weight: 700;"
            f" color: {pri}; background: transparent;"
        )
        self._sub_lbl.setStyleSheet(
            f"font-family: {_FONT_STACK}; font-size: 11px;"
            f" color: {sec}; background: transparent;"
        )


# ============================================================================
# Dual-axis bar chart
# ============================================================================
@dataclass
class _Bar:
    label: str
    mean: float
    variance: float


class DualAxisBarChart(QFrame):
    """Paints a grouped bar chart with two y-axes (mean + variance)."""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._dark = False
        self._bars: List[_Bar] = []
        self._metric = ""
        self._higher_better = True
        self.setObjectName("dualAxisChart")
        self.setMinimumHeight(360)

    def set_data(self, metric: str, series_rows: Sequence) -> None:
        self._metric = metric
        self._higher_better = _is_higher_better(metric)
        bars: List[_Bar] = []
        for row in series_rows:
            bars.append(_Bar(
                label=str(row.sample_id),
                mean=float(row.mean),
                variance=float(row.variance),
            ))
        bars.sort(key=lambda b: (-b.mean if self._higher_better else b.mean))
        self._bars = bars
        self.update()

    def clear(self) -> None:
        self._bars = []
        self._metric = ""
        self.update()

    def set_dark(self, dark: bool) -> None:
        self._dark = dark
        self.update()

    def paintEvent(self, event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        p.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)

        rect = QRectF(8, 6, self.width() - 16, self.height() - 16)
        surface = QColor(SURFACE_DARK if self._dark else SURFACE_LIGHT)
        _paint_card_surface(p, rect, 16.0, surface, self._dark)

        if not self._bars:
            self._draw_empty(p, rect)
            p.end()
            return

        left_pad = 60
        right_pad = 60
        top_pad = 84
        bottom_pad = 92
        plot = QRectF(
            rect.left() + left_pad,
            rect.top() + top_pad,
            rect.width() - left_pad - right_pad,
            rect.height() - top_pad - bottom_pad,
        )

        means = [b.mean for b in self._bars]
        variances = [b.variance for b in self._bars]
        left_max = max(means) * 1.18 if means else 1.0
        right_max = max(variances) * 1.25 if variances else 1.0
        if left_max <= 0:
            left_max = 1.0
        if right_max <= 0:
            right_max = 1.0

        self._draw_title(p, rect)
        self._draw_axes(p, plot, left_max, right_max)
        self._draw_bars(p, plot, left_max, right_max)
        self._draw_legend(p, rect)
        p.end()

    def _draw_empty(self, p: QPainter, rect: QRectF) -> None:
        pri = TXT_SEC_DARK if self._dark else TXT_SEC_LIGHT
        p.setPen(QColor(pri))
        f = QFont(_FONT_STACK, 13)
        f.setWeight(QFont.Weight.Medium)
        p.setFont(f)
        msg = "No training data yet. Upload datasets and run training to see metrics here."
        p.drawText(rect, Qt.AlignmentFlag.AlignCenter, msg)

    def _draw_title(self, p: QPainter, rect: QRectF) -> None:
        if not self._metric:
            return
        ter = TXT_TER_DARK if self._dark else TXT_TER_LIGHT
        pri = TXT_PRI_DARK if self._dark else TXT_PRI_LIGHT
        metric_label = self._metric.upper()
        badge_rect = QRectF(rect.left() + 20, rect.top() + 16, 88, 26)
        badge_path = QPainterPath()
        badge_path.addRoundedRect(badge_rect, 13, 13)
        p.fillPath(badge_path, QColor(PRIMARY_COLOR if not self._dark else PRIMARY_COLOR_DARK))
        p.setPen(QColor("#ffffff"))
        f = QFont(_FONT_STACK, 11)
        f.setWeight(QFont.Weight.Bold)
        f.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, 0.6)
        p.setFont(f)
        p.drawText(badge_rect, Qt.AlignmentFlag.AlignCenter, metric_label)
        p.setPen(QColor(ter))
        sub = QFont(_FONT_STACK, 11)
        sub.setWeight(QFont.Weight.Normal)
        p.setFont(sub)
        sub_text = "Left axis: mean over epochs. Right axis: variance across epochs."
        p.drawText(QRectF(rect.left() + 116, rect.top() + 16,
                          rect.width() - 136, 26),
                   Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, sub_text)
        p.setPen(QColor(pri))
        title = QFont(_FONT_STACK, 14)
        title.setWeight(QFont.Weight.DemiBold)
        p.setFont(title)
        p.drawText(QRectF(rect.left(), rect.top() + 44, rect.width(), 24),
                   Qt.AlignmentFlag.AlignCenter,
                   f"{metric_label} mean & variance per dataset")

    def _draw_axes(self, p: QPainter, plot: QRectF,
                   left_max: float, right_max: float) -> None:
        pri = TXT_PRI_DARK if self._dark else TXT_PRI_LIGHT
        sec = TXT_SEC_DARK if self._dark else TXT_SEC_LIGHT
        ter = TXT_TER_DARK if self._dark else TXT_TER_LIGHT
        div = DIVIDER_DARK if self._dark else DIVIDER_LIGHT

        axis_font = QFont(_FONT_STACK, 9)
        axis_font.setWeight(QFont.Weight.Medium)
        p.setFont(axis_font)
        for i in range(0, 5):
            frac = i / 4.0
            y = plot.bottom() - frac * plot.height()
            p.setPen(QPen(QColor(div), 1, Qt.PenStyle.DashLine))
            p.drawLine(QPointF(plot.left(), y), QPointF(plot.right(), y))
            val = left_max * frac
            p.setPen(QColor(ter))
            p.drawText(QRectF(plot.left() - 54, y - 9, 48, 18),
                       Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
                       f"{val:.3f}")

        for i in range(0, 5):
            frac = i / 4.0
            y = plot.bottom() - frac * plot.height()
            val = right_max * frac
            p.setPen(QColor(ter))
            p.drawText(QRectF(plot.right() + 6, y - 9, 48, 18),
                       Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                       f"{val:.3f}")

        p.setPen(QPen(QColor(sec), 1))
        p.drawLine(QPointF(plot.left(), plot.top()), QPointF(plot.left(), plot.bottom()))
        p.drawLine(QPointF(plot.right(), plot.top()), QPointF(plot.right(), plot.bottom()))
        p.drawLine(QPointF(plot.left(), plot.bottom()), QPointF(plot.right(), plot.bottom()))

        title_font = QFont(_FONT_STACK, 10)
        title_font.setWeight(QFont.Weight.DemiBold)
        p.setFont(title_font)
        p.setPen(QColor(pri))
        p.save()
        p.translate(plot.left() - 42, plot.center().y())
        p.rotate(-90)
        p.drawText(QRectF(-60, -10, 120, 20),
                   Qt.AlignmentFlag.AlignCenter, "Mean")
        p.restore()
        p.save()
        p.translate(plot.right() + 42, plot.center().y())
        p.rotate(-90)
        p.drawText(QRectF(-60, -10, 120, 20),
                   Qt.AlignmentFlag.AlignCenter, "Variance")
        p.restore()

    def _draw_bars(self, p: QPainter, plot: QRectF,
                   left_max: float, right_max: float) -> None:
        if not self._bars:
            return
        n = len(self._bars)
        slot_w = plot.width() / n
        bar_w = max(2.0, slot_w * 0.32)
        gap = max(1.0, slot_w * 0.06)
        ter = TXT_TER_DARK if self._dark else TXT_TER_LIGHT

        palette = ACCENT_GRADIENT_DARK if self._dark else ACCENT_GRADIENT_LIGHT
        gradient_top = QColor(palette[0])
        gradient_bot = QColor(palette[1])

        for i, bar in enumerate(self._bars):
            cx = plot.left() + slot_w * (i + 0.5)
            mean_h = (bar.mean / left_max) * plot.height() if left_max else 0
            mean_x = cx - bar_w - gap / 2
            mean_y = plot.bottom() - mean_h
            grad = QLinearGradient(QPointF(mean_x, mean_y), QPointF(mean_x, plot.bottom()))
            grad.setColorAt(0, gradient_top)
            grad.setColorAt(1, gradient_bot)
            mean_rect = QRectF(mean_x, mean_y, bar_w, mean_h)
            mean_path = QPainterPath()
            mean_path.addRoundedRect(mean_rect, 3, 3)
            p.fillPath(mean_path, QBrush(grad))

            var_h = (bar.variance / right_max) * plot.height() if right_max else 0
            var_x = cx + gap / 2
            var_y = plot.bottom() - var_h
            var_color = QColor("#ff9f0a" if self._dark else "#ff9500")
            var_rect = QRectF(var_x, var_y, bar_w, var_h)
            var_path = QPainterPath()
            var_path.addRoundedRect(var_rect, 3, 3)
            p.fillPath(var_path, var_color)

            p.setPen(QColor(ter))
            label_font = QFont(_FONT_STACK, 8)
            label_font.setWeight(QFont.Weight.Medium)
            p.setFont(label_font)
            # Rotate labels to avoid overlap with long dataset names
            p.save()
            p.translate(cx, plot.bottom() + 12)
            p.rotate(-40)
            # Truncate label if too long
            label_text = bar.label
            if len(label_text) > 16:
                label_text = label_text[:14] + "..."
            p.drawText(0, 0, label_text)
            p.restore()

    def _draw_legend(self, p: QPainter, rect: QRectF) -> None:
        ter = TXT_TER_DARK if self._dark else TXT_TER_LIGHT
        sw_w = 14
        sw_h = 10
        sw_y = rect.bottom() - 18
        sw1 = QRectF(rect.right() - 160, sw_y, sw_w, sw_h)
        legend_palette = ACCENT_GRADIENT_DARK if self._dark else ACCENT_GRADIENT_LIGHT
        p.setBrush(QBrush(QColor(legend_palette[0])))
        p.setPen(Qt.PenStyle.NoPen)
        p.drawRoundedRect(sw1, 2, 2)
        sw2 = QRectF(rect.right() - 80, sw_y, sw_w, sw_h)
        p.setBrush(QBrush(QColor("#ff9500")))
        p.drawRoundedRect(sw2, 2, 2)
        p.setPen(QColor(ter))
        legend_font = QFont(_FONT_STACK, 9)
        legend_font.setWeight(QFont.Weight.Medium)
        p.setFont(legend_font)
        p.drawText(QRectF(sw1.right() + 6, sw_y - 3, 60, 16),
                   Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, "Mean")
        p.drawText(QRectF(sw2.right() + 6, sw_y - 3, 80, 16),
                   Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, "Variance")


# ============================================================================
# Training-curve thumbnail
# ============================================================================
class _CurveHost(QWidget):
    """Inner widget that paints the actual curve inside TrainingCurveThumb."""

    def __init__(self, dark_ref, points_ref, color_ref, parent=None) -> None:
        super().__init__(parent)
        self._dark_ref = dark_ref
        self._points_ref = points_ref
        self._color_ref = color_ref
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, False)
        self.setMinimumHeight(60)

    def paintEvent(self, event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        p.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)
        dark = self._dark_ref()
        points = self._points_ref()
        color = self._color_ref()
        if dark:
            bg = SURFACE_DARK
            div = DIVIDER_DARK
            ter = TXT_TER_DARK
        else:
            bg = SURFACE_LIGHT
            div = DIVIDER_LIGHT
            ter = TXT_TER_LIGHT
        plot = QRectF(2, 4, self.width() - 4, self.height() - 16)
        if not points:
            p.setPen(QColor(ter))
            f = QFont(_FONT_STACK, 10)
            p.setFont(f)
            p.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, "no data")
            return
        # Baseline
        p.setPen(QPen(QColor(div), 1, Qt.PenStyle.DashLine))
        p.drawLine(QPointF(plot.left(), plot.bottom()),
                   QPointF(plot.right(), plot.bottom()))
        values = [pt.value for pt in points]
        vmin = min(values)
        vmax = max(values)
        if math.isclose(vmin, vmax):
            vmax = vmin + 1e-6
        # Filled area under the line.
        path = QPainterPath()
        path.moveTo(plot.left(), plot.bottom())
        for i, pt in enumerate(points):
            x = plot.left() + (i / max(1, len(points) - 1)) * plot.width()
            y = plot.bottom() - ((pt.value - vmin) / (vmax - vmin)) * plot.height()
            if i == 0:
                path.lineTo(x, y)
            else:
                path.lineTo(x, y)
        path.lineTo(plot.right(), plot.bottom())
        path.closeSubpath()
        area_color = QColor(color)
        area_color.setAlpha(48)
        p.fillPath(path, area_color)
        # Line.
        line_path = QPainterPath()
        for i, pt in enumerate(points):
            x = plot.left() + (i / max(1, len(points) - 1)) * plot.width()
            y = plot.bottom() - ((pt.value - vmin) / (vmax - vmin)) * plot.height()
            if i == 0:
                line_path.moveTo(x, y)
            else:
                line_path.lineTo(x, y)
        p.setPen(QPen(QColor(color), 2.0))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawPath(line_path)
        # Endpoint dot.
        last_x = plot.right()
        last_y = plot.bottom() - ((points[-1].value - vmin) / (vmax - vmin)) * plot.height()
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(color))
        p.drawEllipse(QPointF(last_x, last_y), 3.0, 3.0)
        # Min/max labels.
        p.setPen(QColor(ter))
        f = QFont(_FONT_STACK, 8)
        f.setWeight(QFont.Weight.Medium)
        p.setFont(f)
        p.drawText(QRectF(plot.left(), plot.top() - 2, 60, 14),
                   Qt.AlignmentFlag.AlignLeft, _fmt(vmax, 3))
        p.drawText(QRectF(plot.right() - 60, plot.bottom() + 2, 60, 14),
                   Qt.AlignmentFlag.AlignRight, _fmt(vmin, 3))


class TrainingCurveThumb(QFrame):
    """Mini line chart of a downsampled training curve."""

    def __init__(self, metric: str, color: str = PRIMARY_COLOR,
                 parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._metric = metric
        self._color = color
        self._points: List[CurvePoint] = []
        self._dark = False
        self.setMinimumHeight(120)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(4)

        header = QHBoxLayout()
        header.setSpacing(8)
        self._title_lbl = QLabel(metric.upper())
        self._title_lbl.setObjectName("curveTitle")
        header.addWidget(self._title_lbl)
        header.addStretch()
        self._value_lbl = QLabel("-")
        self._value_lbl.setObjectName("curveValue")
        header.addWidget(self._value_lbl)
        layout.addLayout(header)

        self._host = _CurveHost(
            dark_ref=lambda: self._dark,
            points_ref=lambda: self._points,
            color_ref=lambda: self._color,
        )
        layout.addWidget(self._host, 1)
        self._apply_text()

    def set_data(self, points: Sequence[CurvePoint]) -> None:
        self._points = list(points)
        if points:
            self._value_lbl.setText(_fmt(points[-1].value, 4))
        else:
            self._value_lbl.setText("-")
        self._host.update()

    def clear(self) -> None:
        self._points = []
        self._value_lbl.setText("-")
        self._host.update()

    def set_dark(self, dark: bool) -> None:
        self._dark = dark
        self._apply_text()
        self._host.update()

    def paintEvent(self, event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        rect = QRectF(8, 6, self.width() - 16, self.height() - 16)
        surface = QColor(SURFACE_DARK if self._dark else SURFACE_LIGHT)
        _paint_card_surface(p, rect, 14.0, surface, self._dark)
        p.end()

    def _apply_text(self) -> None:
        dark = self._dark
        pri = TXT_PRI_DARK if dark else TXT_PRI_LIGHT
        ter = TXT_TER_DARK if dark else TXT_TER_LIGHT
        self._title_lbl.setStyleSheet(
            f"font-family: {_FONT_STACK}; font-size: 11px; font-weight: 700;"
            f" letter-spacing: 0.6px; color: {ter}; background: transparent;"
        )
        self._value_lbl.setStyleSheet(
            f"font-family: {_FONT_STACK}; font-size: 13px; font-weight: 600;"
            f" color: {pri}; background: transparent;"
        )


# ============================================================================
# Metric overview card
# ============================================================================
class MetricOverviewCard(QFrame):
    """Small card showing summary statistics for a single metric."""

    def __init__(self, metric: str, color: str = PRIMARY_COLOR,
                 parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._metric = metric
        self._color = color
        self._dark = False
        self.setMinimumHeight(110)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setSpacing(4)

        header = QHBoxLayout()
        header.setSpacing(8)
        self._dot = QLabel()
        self._dot.setFixedSize(10, 10)
        self._dot.setStyleSheet(
            f"background: {color}; border-radius: 5px; border: none;"
        )
        header.addWidget(self._dot)
        self._title_lbl = QLabel(metric.upper())
        self._title_lbl.setObjectName("overviewTitle")
        header.addWidget(self._title_lbl)
        header.addStretch()
        layout.addLayout(header)

        self._value_lbl = QLabel("-")
        self._value_lbl.setObjectName("overviewValue")
        layout.addWidget(self._value_lbl)

        self._extra_lbl = QLabel("")
        self._extra_lbl.setObjectName("overviewExtra")
        self._extra_lbl.setWordWrap(True)
        layout.addWidget(self._extra_lbl)
        layout.addStretch(1)

        self._apply_text()

    def set_summary(self, summary: MetricSummary) -> None:
        self._value_lbl.setText(_fmt(summary.grand_mean, 4))
        higher = _is_higher_better(summary.metric)
        arrow = "\u2191" if higher else "\u2193"
        verb = "higher is better" if higher else "lower is better"
        self._extra_lbl.setText(
            f"{arrow} {verb} - best: {summary.best_sample_id} ({_fmt(summary.best_value, 4)})"
            f" - worst: {summary.worst_sample_id} ({_fmt(summary.worst_value, 4)})"
        )

    def clear(self) -> None:
        self._value_lbl.setText("-")
        self._extra_lbl.setText("")

    def set_dark(self, dark: bool) -> None:
        self._dark = dark
        self._apply_text()

    def paintEvent(self, event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        rect = QRectF(8, 6, self.width() - 16, self.height() - 16)
        surface = QColor(SURFACE_DARK if self._dark else SURFACE_LIGHT)
        _paint_card_surface(p, rect, 14.0, surface, self._dark)
        p.end()

    def _apply_text(self) -> None:
        dark = self._dark
        pri = TXT_PRI_DARK if dark else TXT_PRI_LIGHT
        ter = TXT_TER_DARK if dark else TXT_TER_LIGHT
        sec = TXT_SEC_DARK if dark else TXT_SEC_LIGHT
        self._title_lbl.setStyleSheet(
            f"font-family: {_FONT_STACK}; font-size: 11px; font-weight: 700;"
            f" letter-spacing: 0.6px; color: {ter}; background: transparent;"
        )
        self._value_lbl.setStyleSheet(
            f"font-family: {_FONT_STACK}; font-size: 22px; font-weight: 700;"
            f" color: {pri}; background: transparent;"
        )
        self._extra_lbl.setStyleSheet(
            f"font-family: {_FONT_STACK}; font-size: 10px;"
            f" color: {sec}; background: transparent;"
        )


# ============================================================================
# Chart container panel (wraps DualAxisBarChart with title + selector)
# ============================================================================
class BarChartPanel(QFrame):
    """Holds the dual-axis bar chart plus a metric selector and KPI strip."""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._dark = False
        self._metric_changed_cb = None
        self.setObjectName("barChartPanel")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self._chart = DualAxisBarChart()
        layout.addWidget(self._chart)

        self._selector_row = QFrame()
        self._selector_row.setObjectName("selectorRow")
        s_ly = QHBoxLayout(self._selector_row)
        s_ly.setContentsMargins(18, 12, 18, 12)
        s_ly.setSpacing(10)
        label = QLabel("Metric")
        label.setObjectName("selectorLabel")
        s_ly.addWidget(label)
        self._combo = QComboBox()
        for m in METRICS:
            self._combo.addItem(m.upper())
        self._combo.currentTextChanged.connect(self._on_metric_changed)
        s_ly.addWidget(self._combo)
        s_ly.addStretch()
        self._hint = QLabel("Mean over epochs  -  Variance across epochs")
        self._hint.setObjectName("selectorHint")
        s_ly.addWidget(self._hint)
        layout.addWidget(self._selector_row)
        self._apply_text()

    def set_metric_provider(self, cb) -> None:
        self._metric_changed_cb = cb

    def set_data(self, metric: str, series_rows: Sequence) -> None:
        self._combo.blockSignals(True)
        idx = max(0, self._combo.findText(metric.upper()))
        self._combo.setCurrentIndex(idx)
        self._combo.blockSignals(False)
        self._chart.set_data(metric, series_rows)

    def clear(self) -> None:
        self._chart.clear()

    def set_dark(self, dark: bool) -> None:
        self._dark = dark
        self._chart.set_dark(dark)
        self._apply_text()

    def _on_metric_changed(self, text: str) -> None:
        if not self._metric_changed_cb:
            return
        self._metric_changed_cb(text.lower())

    def _apply_text(self) -> None:
        dark = self._dark
        pri = TXT_PRI_DARK if dark else TXT_PRI_LIGHT
        sec = TXT_SEC_DARK if dark else TXT_SEC_LIGHT
        div = DIVIDER_DARK if dark else DIVIDER_LIGHT
        self._selector_row.setStyleSheet(
            f"QFrame#selectorRow {{ background: transparent;"
            f" border-top: 1px solid {div}; }}"
        )
        label = self._selector_row.findChild(QLabel, "selectorLabel")
        hint = self._selector_row.findChild(QLabel, "selectorHint")
        if label is not None:
            label.setStyleSheet(
                f"font-family: {_FONT_STACK}; font-size: 11px; font-weight: 700;"
                f" letter-spacing: 0.6px; color: {sec}; background: transparent;"
            )
        if hint is not None:
            hint.setStyleSheet(
                f"font-family: {_FONT_STACK}; font-size: 10px;"
                f" color: {sec}; background: transparent;"
            )
        combo_bg = SURFACE_ALT_DARK if dark else SURFACE_ALT_LIGHT
        combo_border = DIVIDER_DARK if dark else DIVIDER_LIGHT
        combo_fg = pri
        self._combo.setStyleSheet(
            f"QComboBox {{ background: {combo_bg}; color: {combo_fg};"
            f" border: 1px solid {combo_border}; border-radius: 6px;"
            f" padding: 4px 10px; font-family: {_FONT_STACK};"
            f" font-size: 12px; font-weight: 600;"
            f" min-width: 80px; }}"
            f"QComboBox:hover {{ border-color: {PRIMARY_COLOR}; }}"
            f"QComboBox::drop-down {{ border: none; width: 18px; }}"
            f"QComboBox QAbstractItemView {{"
            f" background: {SURFACE_DARK if dark else SURFACE_LIGHT};"
            f" color: {combo_fg}; selection-background-color: rgba(10,132,255,0.18);"
            f" border: 1px solid {combo_border}; }}"
        )
