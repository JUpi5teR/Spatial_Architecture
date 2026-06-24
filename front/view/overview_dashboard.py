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


class _HighlightChip(QFrame):
    """Pill-shaped card highlighting the best dataset for a single metric.

    Used by the Highlights strip on the overview page to fill the gap
    between the KPI row and the main chart row, while also giving the
    user a quick read of which dataset wins on every metric.
    """

    def __init__(self, metric: str, color: str,
                 parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._metric = metric
        self._color = color
        self._dark = False
        self._dataset_name = "-"
        self._dataset_value: Optional[float] = None
        self.setMinimumHeight(64)
        self.setSizePolicy(QSizePolicy.Policy.Expanding,
                           QSizePolicy.Policy.Fixed)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(14, 10, 14, 10)
        layout.setSpacing(10)

        self._dot = QLabel()
        self._dot.setFixedSize(10, 10)
        self._dot.setStyleSheet(
            f"background: {color}; border-radius: 5px; border: none;"
        )
        layout.addWidget(self._dot)

        text_col = QVBoxLayout()
        text_col.setSpacing(0)
        self._metric_lbl = QLabel(metric.upper())
        self._metric_lbl.setObjectName("highlightMetric")
        text_col.addWidget(self._metric_lbl)
        self._name_lbl = QLabel("-")
        self._name_lbl.setObjectName("highlightName")
        text_col.addWidget(self._name_lbl)
        layout.addLayout(text_col, 1)

        self._value_lbl = QLabel("-")
        self._value_lbl.setObjectName("highlightValue")
        self._value_lbl.setAlignment(
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        )
        layout.addWidget(self._value_lbl)

        self._apply_text()

    def set_data(self, dataset_name: str, value: Optional[float]) -> None:
        self._dataset_name = dataset_name or "-"
        self._dataset_value = value
        self._name_lbl.setText(self._dataset_name)
        self._value_lbl.setText(
            f"{value:.4f}" if value is not None else "-"
        )

    def set_dark(self, dark: bool) -> None:
        self._dark = dark
        self._apply_text()

    def paintEvent(self, event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        rect = QRectF(4, 2, self.width() - 8, self.height() - 6)
        surface = QColor(SURFACE_DARK if self._dark else SURFACE_LIGHT)
        _paint_card_surface(p, rect, 12.0, surface, self._dark)
        # Subtle accent bar on the left so the chip reads as a tag.
        accent_rect = QRectF(rect.left() + 2, rect.top() + 12,
                             2.5, rect.height() - 24)
        accent_path = QPainterPath()
        accent_path.addRoundedRect(accent_rect, 1.2, 1.2)
        p.fillPath(accent_path, QColor(self._color))
        p.end()

    def _apply_text(self) -> None:
        dark = self._dark
        pri = TXT_PRI_DARK if dark else TXT_PRI_LIGHT
        ter = TXT_TER_DARK if dark else TXT_TER_LIGHT
        sec = TXT_SEC_DARK if dark else TXT_SEC_LIGHT
        self._metric_lbl.setStyleSheet(
            f"font-family: {_FONT_STACK}; font-size: 10px; font-weight: 700;"
            f" letter-spacing: 0.6px; color: {ter}; background: transparent;"
        )
        self._name_lbl.setStyleSheet(
            f"font-family: {_FONT_STACK}; font-size: 13px; font-weight: 600;"
            f" color: {pri}; background: transparent;"
        )
        self._value_lbl.setStyleSheet(
            f"font-family: {_FONT_STACK}; font-size: 13px; font-weight: 600;"
            f" color: {sec}; background: transparent;"
        )


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
        self._highlight_chips = {}

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
        self._dataset_bar_panel.set_dark(dark)
        self._sample_bar_panel.set_dark(dark)
        for w in (self._kpi_datasets, self._kpi_metrics, self._kpi_ari,
                  self._kpi_loss):
            w.set_dark(dark)
        for thumb in self._thumbs.values():
            thumb.set_dark(dark)
        for card in self._overview_cards.values():
            card.set_dark(dark)
        for chip in self._highlight_chips.values():
            chip.set_dark(dark)
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
        self._kpi_ari = KpiCard(
            "Best ARI Sample",
            accent=_METRIC_COLORS["ari"],
        )
        self._kpi_loss = KpiCard(
            "Best Loss Sample",
            accent=_METRIC_COLORS["loss"],
        )
        for w in (self._kpi_datasets, self._kpi_metrics, self._kpi_ari, self._kpi_loss):
            kpi_row.addWidget(w, 1)
        root.addLayout(kpi_row)

        # ---- Highlights strip ----
        # One chip per metric, showing the best dataset name and its
        # combined-mean value. Sits between the KPI strip and the main
        # chart row to fill the gap and give a quick at-a-glance read.
        highlights_panel = _PanelSurface()
        highlights_ly = QVBoxLayout(highlights_panel)
        highlights_ly.setContentsMargins(18, 14, 18, 14)
        highlights_ly.setSpacing(10)
        highlights_header = QHBoxLayout()
        highlights_header.setSpacing(8)
        h_title = QLabel("Best Dataset by Metric")
        h_title.setObjectName("highlightsTitle")
        highlights_header.addWidget(h_title)
        highlights_header.addStretch()
        h_sub = QLabel("Highest pooled-mean dataset per metric.")
        h_sub.setObjectName("highlightsSubtitle")
        highlights_header.addWidget(h_sub)
        highlights_ly.addLayout(highlights_header)
        chips_row = QHBoxLayout()
        chips_row.setSpacing(12)
        for metric in METRICS:
            color = _METRIC_COLORS.get(metric, PRIMARY_COLOR)
            chip = _HighlightChip(metric, color=color)
            chip.setMinimumWidth(170)
            self._highlight_chips[metric] = chip
            chips_row.addWidget(chip, 1)
        highlights_ly.addLayout(chips_row)
        root.addWidget(highlights_panel)

        # ---- Main: bar chart + metric overview ----
        main_row = QHBoxLayout()
        main_row.setSpacing(18)
        # Top-level bar chart panel: aggregates by dataset name
        # (sts/all/none) using combined mean & variance pooled across
        # every sample+epoch that belongs to a dataset with that name.
        self._sample_bar_panel = BarChartPanel()
        self._sample_bar_panel.set_metric_provider(self._on_sample_metric_changed)
        self._sample_bar_panel.setMinimumHeight(360)
        self._dataset_bar_panel = BarChartPanel()
        self._dataset_bar_panel.set_metric_provider(self._on_dataset_metric_changed)
        self._dataset_bar_panel.setMinimumHeight(440)
        main_row.addWidget(self._dataset_bar_panel, 3)

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
        ov_subtitle = QLabel(
            "Strongest single sample across every dataset in this "
            "notebook. Tagged with ``dataset/sample`` so you can see "
            "which run produced the top result."
        )
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

        # ---- Per-sample bar chart (moved down from its original
        # position above the metric overview; replaced there by the
        # per-dataset-aggregated panel).
        self._sample_bar_panel.setObjectName("sampleBarPanel")
        sample_panel = _PanelSurface()
        sample_ly = QVBoxLayout(sample_panel)
        sample_ly.setContentsMargins(16, 14, 16, 14)
        sample_ly.setSpacing(10)
        sample_title = QLabel("Per-sample Mean & Variance")
        sample_title.setObjectName("sampleBarTitle")
        sample_ly.addWidget(sample_title)
        sample_subtitle = QLabel(
            "Each bar is one tissue sample; mean and variance are taken "
            "across training epochs for that sample."
        )
        sample_subtitle.setObjectName("sampleBarSubtitle")
        sample_subtitle.setWordWrap(True)
        sample_ly.addWidget(sample_subtitle)
        sample_ly.addWidget(self._sample_bar_panel)
        root.addWidget(sample_panel)

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
            ari_best_value = ari_summary.best_value
            self._kpi_ari.set_value(
                f"{ari_best_value:.4f}",
                f"best sample: {ari_summary.best_sample_dataset or '-'}"
                f"/{ari_summary.best_sample_id or '-'} "
                f"({ari_best_value:.4f})"
                if ari_summary.best_sample_id
                else "no best sample"
            )
        else:
            self._kpi_ari.set_value("-", "no data")
        if loss_summary is not None:
            loss_best_value = loss_summary.best_value
            self._kpi_loss.set_value(
                f"{loss_best_value:.4f}",
                f"best sample: {loss_summary.best_sample_dataset or '-'}"
                f"/{loss_summary.best_sample_id or '-'} "
                f"({loss_best_value:.4f})"
                if loss_summary.best_sample_id
                else "no best sample"
            )
        else:
            self._kpi_loss.set_value("-", "no data")

        # Empty-state handling
        has_data = bool(snap.metrics)
        self._empty_lbl.setVisible(not has_data)
        if not has_data:
            self._dataset_bar_panel.clear()
            self._sample_bar_panel.clear()
            for thumb in self._thumbs.values():
                thumb.clear()
            for chip in self._highlight_chips.values():
                chip.set_data("-", None)
            self._clear_overview_cards()
            return

        # Bar chart
        if self._current_metric not in snap.metrics:
            self._current_metric = next(iter(snap.metrics))
        summary = snap.metrics[self._current_metric]
        self._dataset_bar_panel.set_data(
            self._current_metric,
            list(summary.dataset_groups.values()),
            label_attr="name",
            mean_attr="combined_mean",
            variance_attr="combined_variance",
        )
        self._sample_bar_panel.set_data(self._current_metric, summary.series)

        # Training curves
        for metric, thumb in self._thumbs.items():
            points = snap.train_curves.get(metric, [])
            if points:
                thumb.set_data(points)
            else:
                thumb.clear()

        # Highlight chips: best dataset per metric.
        for metric, chip in self._highlight_chips.items():
            m_summary = snap.metrics.get(metric)
            if m_summary is None or not m_summary.best_dataset_name:
                chip.set_data("-", None)
            else:
                chip.set_data(
                    m_summary.best_dataset_name,
                    m_summary.best_dataset_value,
                )

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
    def _on_dataset_metric_changed(self, metric: str) -> None:
        if not metric or self._snapshot is None:
            return
        summary = self._snapshot.metrics.get(metric)
        if summary is None:
            self._dataset_bar_panel.clear()
            return
        self._current_metric = metric
        self._dataset_bar_panel.set_data(
            metric,
            list(summary.dataset_groups.values()),
            label_attr="name",
            mean_attr="combined_mean",
            variance_attr="combined_variance",
        )
        # Keep the sample-level panel in sync with the same metric.
        self._sample_bar_panel.set_data(metric, summary.series)

    def _on_sample_metric_changed(self, metric: str) -> None:
        if not metric or self._snapshot is None:
            return
        summary = self._snapshot.metrics.get(metric)
        if summary is None:
            self._sample_bar_panel.clear()
            return
        self._current_metric = metric
        self._sample_bar_panel.set_data(metric, summary.series)
        # Keep the dataset-level panel in sync with the same metric.
        self._dataset_bar_panel.set_data(
            metric,
            list(summary.dataset_groups.values()),
            label_attr="name",
            mean_attr="combined_mean",
            variance_attr="combined_variance",
        )

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
            ("sampleBarTitle", 14, 700),
            ("sampleBarSubtitle", 11, 500),
            ("highlightsTitle", 14, 700),
            ("highlightsSubtitle", 11, 500),
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
