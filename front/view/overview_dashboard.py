# coding: utf-8
"""Overview dashboard widget (notebook workspace > Overview).

Replaces the placeholder at stack index 6 of NotebookWorkspace. It is
a pure read-only dashboard: KPI strip, dual-axis bar chart with metric
selector, training-curve thumbnails, and metric overview cards. All
charting is done with QPainter in `dashboard_widgets.py`, so the page
has no matplotlib dependency.

Scope: only the datasets that belong to the currently-open notebook
are aggregated - this keeps the comparison meaningful and avoids
leaking cross-notebook data on a shared workstation.
"""
from __future__ import annotations

import sys as _sys
from pathlib import Path as _Path

# Ensure front/ is on sys.path so this widget can be imported both
# via `from view.overview_dashboard import ...` (package style) and
# `import overview_dashboard` (script style) without surprises.
_front = _Path(__file__).resolve().parent.parent
if str(_front) not in _sys.path:
    _sys.path.insert(0, str(_front))
del _sys, _Path

from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtCore import QRectF
from PySide6.QtGui import QColor, QPainter, QPainterPath
from PySide6.QtWidgets import (
    QFrame, QGridLayout, QHBoxLayout, QLabel, QScrollArea,
    QSizePolicy, QVBoxLayout, QWidget,
)

from backend.models import Notebook
from utils.logger import logger

from front.model.dashboard_data import (
    DashboardDataService, DashboardSnapshot, METRICS,
)
from front.view.dashboard_widgets import (
    BarChartPanel, KpiCard, MetricOverviewCard, TrainingCurveThumb,
    _FONT_STACK, _paint_card_surface,
    BG_LIGHT, BG_DARK, SURFACE_LIGHT, SURFACE_DARK,
    TXT_PRI_LIGHT, TXT_PRI_DARK, TXT_SEC_LIGHT, TXT_SEC_DARK,
    TXT_TER_LIGHT, TXT_TER_DARK, DIVIDER_LIGHT, DIVIDER_DARK,
    PRIMARY_COLOR,
)


# Accent palette used by the metric overview cards. Mirrors Apple HIG
# system colours so the cards read like an OS dashboard.
_METRIC_COLORS = {
    "ari":  "#0a84ff",
    "nmi":  "#5e5ce6",
    "hs":   "#bf5af2",
    "cs":   "#ff9f0a",
    "loss": "#ff453a",
}


class _Background(QWidget):
    """Paints the dashboard background and a soft hero gradient."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._dark = False

    def set_dark(self, dark: bool) -> None:
        self._dark = dark
        self.update()

    def paintEvent(self, event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
        if self._dark:
            base = QColor(BG_DARK)
            accent = QColor("#1c2940")
        else:
            base = QColor(BG_LIGHT)
            accent = QColor("#dde8ff")
        p.fillRect(self.rect(), base)
        # Soft hero blob in the top-right corner.
        blob = QRectF(self.width() - 420, -180, 540, 380)
        path = QPainterPath()
        path.addEllipse(blob)
        p.fillPath(path, QColor(accent.red(), accent.green(), accent.blue(), 70))
        p.end()


class _PanelSurface(QFrame):
    """Wraps a card-style container with consistent rounded shadow."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._dark = False
        self.setObjectName("panelSurface")

    def set_dark(self, dark: bool) -> None:
        self._dark = dark
        self.update()

    def paintEvent(self, event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        rect = QRectF(6, 4, self.width() - 12, self.height() - 12)
        surface = QColor(SURFACE_DARK if self._dark else SURFACE_LIGHT)
        _paint_card_surface(p, rect, 16.0, surface, self._dark)
        p.end()


class OverviewDashboardWidget(QWidget):
    """The Overview page rendered inside NotebookWorkspace."""

    def __init__(self, notebook: Optional[Notebook] = None,
                 parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._notebook = notebook
        self._dark = False
        self._service = DashboardDataService()
        self._snapshot: Optional[DashboardSnapshot] = None
        self._current_metric = "ari"
        # Map metric -> thumb widget so we can refresh on data change.
        self._thumbs = {}
        self._overview_cards = {}

        self._build_ui()
        self.refresh()

    # ----------------------------------------------------------------
    # Public API
    # ----------------------------------------------------------------
    def set_notebook(self, notebook: Notebook) -> None:
        self._notebook = notebook
        self.refresh()

    def set_dark(self, dark: bool) -> None:
        self._dark = dark
        # Propagate to direct children that paint their own backgrounds.
        self._bg.set_dark(dark)
        self._bar_panel.set_dark(dark)
        for w in (self._kpi_datasets, self._kpi_metrics, self._kpi_ari,
                  self._kpi_loss):
            w.set_dark(dark)
        for thumb in self._thumbs.values():
            thumb.set_dark(dark)
        for card in self._overview_cards.values():
            card.set_dark(dark)
        self._apply_header_text()
        self._apply_empty_text()

    def refresh(self) -> None:
        nb_id = self._notebook.id if self._notebook is not None else None
        # Always rebuild for the current notebook so dataset uploads
        # show up immediately when the user returns to this page.
        self._service.invalidate()
        try:
            snap = self._service.build_snapshot(notebook_id=nb_id, use_cache=False)
        except Exception as exc:
            logger.error("Overview dashboard refresh failed: %s", exc, exc_info=True)
            return
        self._snapshot = snap
        self._populate(snap)

    # ----------------------------------------------------------------
    # Layout
    # ----------------------------------------------------------------
    def _build_ui(self) -> None:
        # Outer wrapper so we can paint a themed background and host a
        # scroll area inside it. We override paintEvent via _Background.
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        self._bg = _Background(self)
        self._bg.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, False)
        outer.addWidget(self._bg)

        bg_layout = QVBoxLayout(self._bg)
        bg_layout.setContentsMargins(0, 0, 0, 0)
        bg_layout.setSpacing(0)

        scroll = QScrollArea(self._bg)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setStyleSheet(
            "QScrollArea { background: transparent; border: none; }"
            "QScrollArea > QWidget > QWidget { background: transparent; }"
        )
        scroll.verticalScrollBar().setStyleSheet(self._scrollbar_qss())
        bg_layout.addWidget(scroll)

        container = QWidget()
        container.setStyleSheet("background: transparent;")
        container.setSizePolicy(QSizePolicy.Policy.Expanding,
                                QSizePolicy.Policy.Expanding)
        scroll.setWidget(container)

        root = QVBoxLayout(container)
        root.setContentsMargins(28, 24, 28, 28)
        root.setSpacing(18)

        # ---- Header ----
        self._header_panel = _PanelSurface()
        self._header_panel.setMinimumHeight(78)
        header_ly = QHBoxLayout(self._header_panel)
        header_ly.setContentsMargins(20, 14, 20, 14)
        header_ly.setSpacing(16)
        title_block = QVBoxLayout()
        title_block.setSpacing(2)
        self._eyebrow = QLabel("OVERVIEW")
        self._eyebrow.setObjectName("overviewEyebrow")
        title_block.addWidget(self._eyebrow)
        self._title_lbl = QLabel("")
        self._title_lbl.setObjectName("overviewTitle")
        title_block.addWidget(self._title_lbl)
        self._subtitle_lbl = QLabel("")
        self._subtitle_lbl.setObjectName("overviewSubtitle")
        self._subtitle_lbl.setWordWrap(True)
        title_block.addWidget(self._subtitle_lbl)
        header_ly.addLayout(title_block)
        header_ly.addStretch()
        root.addWidget(self._header_panel)

        # ---- KPI strip ----
        kpi_row = QHBoxLayout()
        kpi_row.setSpacing(14)
        self._kpi_datasets = KpiCard("Datasets", accent=_METRIC_COLORS["ari"])
        self._kpi_metrics = KpiCard("Metrics Loaded", accent=_METRIC_COLORS["nmi"])
        self._kpi_ari = KpiCard("ARI Mean", accent=_METRIC_COLORS["ari"])
        self._kpi_loss = KpiCard("Loss Mean", accent=_METRIC_COLORS["loss"])
        for w in (self._kpi_datasets, self._kpi_metrics, self._kpi_ari, self._kpi_loss):
            kpi_row.addWidget(w, 1)
        root.addLayout(kpi_row)

        # ---- Main: bar chart + metric overview ----
        main_row = QHBoxLayout()
        main_row.setSpacing(18)
        # Bar chart panel (large)
        self._bar_panel = BarChartPanel()
        self._bar_panel.set_metric_provider(self._on_metric_changed)
        self._bar_panel.setMinimumHeight(440)
        main_row.addWidget(self._bar_panel, 3)

        # Right column: metric overview cards stacked vertically.
        right_col = QVBoxLayout()
        right_col.setSpacing(12)
        self._overview_panel = _PanelSurface()
        ov_ly = QVBoxLayout(self._overview_panel)
        ov_ly.setContentsMargins(16, 14, 16, 14)
        ov_ly.setSpacing(10)
        ov_title = QLabel("Metric Overview")
        ov_title.setObjectName("overviewSideTitle")
        ov_ly.addWidget(ov_title)
        ov_subtitle = QLabel("Per-metric grand mean across datasets.")
        ov_subtitle.setObjectName("overviewSideSubtitle")
        ov_subtitle.setWordWrap(True)
        ov_ly.addWidget(ov_subtitle)
        self._overview_holder = QVBoxLayout()
        self._overview_holder.setSpacing(10)
        ov_ly.addLayout(self._overview_holder)
        ov_ly.addStretch(1)
        right_col.addWidget(self._overview_panel, 1)
        main_row.addLayout(right_col, 1)
        root.addLayout(main_row)

        # ---- Training curves row ----
        curves_panel = _PanelSurface()
        curves_ly = QVBoxLayout(curves_panel)
        curves_ly.setContentsMargins(16, 14, 16, 14)
        curves_ly.setSpacing(10)
        curves_title = QLabel("Training Curves")
        curves_title.setObjectName("curvesTitle")
        curves_ly.addWidget(curves_title)
        curves_subtitle = QLabel(
            "Downsampled average of the metric across this notebook'\''s datasets. "
            "Raw per-epoch rows are not exposed."
        )
        curves_subtitle.setObjectName("curvesSubtitle")
        curves_subtitle.setWordWrap(True)
        curves_ly.addWidget(curves_subtitle)
        curves_grid = QGridLayout()
        curves_grid.setSpacing(12)
        curves_grid.setContentsMargins(0, 0, 0, 0)
        for i, metric in enumerate(METRICS):
            color = _METRIC_COLORS.get(metric, PRIMARY_COLOR)
            thumb = TrainingCurveThumb(metric, color=color)
            thumb.setMinimumHeight(150)
            self._thumbs[metric] = thumb
            curves_grid.addWidget(thumb, i // 3, i % 3)
        curves_grid.setColumnStretch(0, 1)
        curves_grid.setColumnStretch(1, 1)
        curves_grid.setColumnStretch(2, 1)
        curves_ly.addLayout(curves_grid)
        root.addWidget(curves_panel)

        # ---- Empty / fallback state (hidden when data is present) ----
        self._empty_lbl = QLabel("")
        self._empty_lbl.setObjectName("overviewEmpty")
        self._empty_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._empty_lbl.setWordWrap(True)
        self._empty_lbl.hide()
        root.addWidget(self._empty_lbl)

        # Initial text styles (theme applied later via set_dark).
        self._apply_header_text()
        self._apply_empty_text()

    # ----------------------------------------------------------------
    # Data binding
    # ----------------------------------------------------------------
    def _populate(self, snap: DashboardSnapshot) -> None:
        nb = self._notebook
        nb_name = nb.name if nb is not None else "(no notebook)"
        scope = "this notebook" if nb is not None else "all datasets"
        self._title_lbl.setText(f"{nb_name} - Overview")
        if snap.dataset_count == 0 or not snap.metrics:
            self._subtitle_lbl.setText(
                f"No training data in {scope}. Upload a dataset and run training to populate this dashboard."
            )
        else:
            self._subtitle_lbl.setText(
                f"Aggregated training metrics for {snap.dataset_count} dataset(s) in {scope}. "
                "Charts only expose summary statistics; raw per-epoch values stay in the data layer."
            )

        # KPI strip
        self._kpi_datasets.set_value(str(snap.dataset_count),
                                     f"in {scope}")
        self._kpi_metrics.set_value(
            f"{snap.metrics_with_data}/{len(METRICS)}",
            "metrics with data"
        )
        ari_summary = snap.metrics.get("ari")
        loss_summary = snap.metrics.get("loss")
        if ari_summary is not None:
            self._kpi_ari.set_value(
                f"{ari_summary.grand_mean:.4f}",
                f"best: {ari_summary.best_sample_id} ({ari_summary.best_value:.4f})"
            )
        else:
            self._kpi_ari.set_value("-", "no data")
        if loss_summary is not None:
            self._kpi_loss.set_value(
                f"{loss_summary.grand_mean:.4f}",
                f"best: {loss_summary.best_sample_id} ({loss_summary.best_value:.4f})"
            )
        else:
            self._kpi_loss.set_value("-", "no data")

        # Empty-state handling
        has_data = bool(snap.metrics)
        self._empty_lbl.setVisible(not has_data)
        if not has_data:
            self._bar_panel.clear()
            for thumb in self._thumbs.values():
                thumb.clear()
            self._clear_overview_cards()
            return

        # Bar chart
        if self._current_metric not in snap.metrics:
            self._current_metric = next(iter(snap.metrics))
        self._bar_panel.set_data(self._current_metric,
                                 snap.metrics[self._current_metric].series)

        # Training curves
        for metric, thumb in self._thumbs.items():
            points = snap.train_curves.get(metric, [])
            if points:
                thumb.set_data(points)
            else:
                thumb.clear()

        # Metric overview cards
        self._refresh_overview_cards(snap)

    def _refresh_overview_cards(self, snap: DashboardSnapshot) -> None:
        # Clear existing cards
        self._clear_overview_cards()
        for metric in METRICS:
            summary = snap.metrics.get(metric)
            if summary is None:
                continue
            color = _METRIC_COLORS.get(metric, PRIMARY_COLOR)
            card = MetricOverviewCard(metric, color=color)
            card.set_summary(summary)
            card.set_dark(self._dark)
            self._overview_cards[metric] = card
            self._overview_holder.addWidget(card)
        self._overview_holder.addStretch(1)

    def _clear_overview_cards(self) -> None:
        while self._overview_holder.count():
            item = self._overview_holder.takeAt(0)
            w = item.widget()
            if w is not None:
                w.setParent(None)
                w.deleteLater()
        self._overview_cards.clear()

    # ----------------------------------------------------------------
    # Metric selector
    # ----------------------------------------------------------------
    def _on_metric_changed(self, metric: str) -> None:
        if not metric or metric == self._current_metric:
            return
        self._current_metric = metric
        if self._snapshot is None:
            return
        summary = self._snapshot.metrics.get(metric)
        if summary is None:
            self._bar_panel.clear()
            return
        self._bar_panel.set_data(metric, summary.series)

    # ----------------------------------------------------------------
    # Theme / styling
    # ----------------------------------------------------------------
    def _apply_header_text(self) -> None:
        dark = self._dark
        pri = TXT_PRI_DARK if dark else TXT_PRI_LIGHT
        sec = TXT_SEC_DARK if dark else TXT_SEC_LIGHT
        ter = TXT_TER_DARK if dark else TXT_TER_LIGHT
        eyebrow_font_size = 11
        self._eyebrow.setStyleSheet(
            f"font-family: {_FONT_STACK}; font-size: {eyebrow_font_size}px;"
            f" font-weight: 800; letter-spacing: 1.2px; color: {ter};"
            f" background: transparent;"
        )
        self._title_lbl.setStyleSheet(
            f"font-family: {_FONT_STACK}; font-size: 22px; font-weight: 700;"
            f" color: {pri}; background: transparent;"
        )
        self._subtitle_lbl.setStyleSheet(
            f"font-family: {_FONT_STACK}; font-size: 12px;"
            f" color: {sec}; background: transparent;"
        )
        # Apply text style to side panel titles
        for obj_name, size, weight in (
            ("overviewSideTitle", 14, 700),
            ("overviewSideSubtitle", 11, 500),
            ("curvesTitle", 14, 700),
            ("curvesSubtitle", 11, 500),
        ):
            lbl = self.findChild(QLabel, obj_name)
            if lbl is None:
                continue
            color = pri if weight >= 700 else sec
            lbl.setStyleSheet(
                f"font-family: {_FONT_STACK}; font-size: {size}px;"
                f" font-weight: {weight}; color: {color};"
                f" background: transparent;"
            )

    def _apply_empty_text(self) -> None:
        dark = self._dark
        ter = TXT_TER_DARK if dark else TXT_TER_LIGHT
        self._empty_lbl.setStyleSheet(
            f"font-family: {_FONT_STACK}; font-size: 13px;"
            f" color: {ter}; background: transparent;"
            f" padding: 24px;"
        )

    def _scrollbar_qss(self) -> str:
        if self._dark:
            handle = "rgba(255,255,255,0.18)"
            handle_h = "rgba(255,255,255,0.28)"
        else:
            handle = "rgba(0,0,0,0.15)"
            handle_h = "rgba(0,0,0,0.25)"
        return (
            "QScrollBar { background: transparent; width: 8px; }"
            f"QScrollBar::handle {{ background: {handle}; border-radius: 4px; min-height: 30px; }}"
            f"QScrollBar::handle:hover {{ background: {handle_h}; }}"
            "QScrollBar::add-line, QScrollBar::sub-line { height: 0; }"
        )
