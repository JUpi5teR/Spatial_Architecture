# coding: utf-8
"""Statistics 页面 —— 展示每个样本的聚类评价指标柱状图。

指标: ARI, NMI, HS, CS
展示: 每个样本一组柱子 + 全局 Mean / Median
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
from matplotlib.figure import Figure

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QSizePolicy, QVBoxLayout, QWidget, QComboBox,
)

from model.data_path import DataPathManager, TRAIN_LOG_METRICS
from utils.logger import logger


class StatisticsViewWidget(QWidget):
    """Bar-chart view of clustering metrics per sample.

    Reads from train_log/ CSV files; displays one metric at a time.
    """

    def __init__(self, path_mgr: DataPathManager, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self._mgr = path_mgr
        self._canvas: Optional[FigureCanvasQTAgg] = None
        self._figure: Optional[Figure] = None
        self._metric_combo: Optional[QComboBox] = None
        self._metric = "ari"
        self._loaded = False
        self._dark = False

        self._build_ui()

    def set_dark(self, dark: bool) -> None:
        self._dark = dark
        bg = "#1e1e21" if dark else "#fafafa"
        fg = "#d0d0d5" if dark else "#1a1a1a"
        combo_bg = "#2a2a2e" if dark else "#fff"
        combo_fg = "#e8e8ec" if dark else "#333"
        combo_border = "#3a3a3e" if dark else "#ddd"
        self.setStyleSheet(f"StatisticsViewWidget {{ background-color: {bg}; }}")
        for lbl in self.findChildren(QLabel):
            if lbl.text().startswith("≡"):
                lbl.setStyleSheet(f"font-size: 24px; font-weight: 800; color: {fg};")
            elif lbl.text() == "选择指标:":
                lbl.setStyleSheet(f"font-size: 12px; color: {fg};")
        if self._metric_combo:
            self._metric_combo.setStyleSheet(
                f"QComboBox {{ background: {combo_bg}; color: {combo_fg}; border: 1px solid {combo_border}; border-radius: 4px; padding: 4px 8px; }}"
                f"QComboBox:hover {{ border-color: #5a6a7a; }}"
                f"QComboBox QAbstractItemView {{ background: {combo_bg}; color: {combo_fg}; selection-background-color: #3a3a50; }}"
            )
        if self._figure:
            self._figure.patch.set_facecolor(bg)
            for ax in self._figure.axes:
                ax.set_facecolor("#2a2a2e" if dark else "#ffffff")
                ax.tick_params(colors=fg)
                ax.xaxis.label.set_color(fg)
                ax.yaxis.label.set_color(fg)
                ax.title.set_color(fg)

    def _build_ui(self) -> None:
        root_ly = QVBoxLayout(self)
        root_ly.setContentsMargins(40, 34, 40, 34)
        root_ly.setSpacing(12)

        title = QLabel("\u2261  Statistics")
        title.setStyleSheet("font-size: 24px; font-weight: 800; color: #1a1a1a;")
        root_ly.addWidget(title)

        # metric selector
        sel_row = QHBoxLayout()
        sel_row.addWidget(QLabel("选择指标: "))
        self._metric_combo = QComboBox()
        self._metric_combo.setFixedWidth(140)
        self._metric_combo.setStyleSheet(
            "QComboBox { background: #fff; border: 1px solid #ddd; border-radius: 4px; padding: 4px 8px; }"
        )
        self._metric_combo.currentTextChanged.connect(self._on_metric_changed)
        sel_row.addWidget(self._metric_combo)
        sel_row.addStretch()
        root_ly.addLayout(sel_row)

        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet("background: #ececec; max-height: 1px; min-height: 1px;")
        root_ly.addWidget(sep)

        # canvas
        self._figure = Figure(figsize=(9, 5), dpi=100)
        self._canvas = FigureCanvasQTAgg(self._figure)
        self._canvas.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        root_ly.addWidget(self._canvas, 1)

    def load_data(self) -> None:
        """Scan train_log, populate metric selector, draw first metric."""
        if not self._mgr.has_valid_data():
            self._draw_placeholder("\u26A0  请先上传数据文件夹 (Upload Data)")
            self._loaded = False
            return

        structure = self._mgr.structure()
        if structure is None or not structure.has_train_log or not structure.train_log_metrics:
            self._draw_placeholder("\u2139  train_log 未找到，暂无统计数据显示")
            self._loaded = False
            return

        metrics = structure.train_log_metrics
        # Populate combo
        self._metric_combo.blockSignals(True)
        self._metric_combo.clear()
        for m in metrics:
            self._metric_combo.addItem(m.upper())
        self._metric_combo.blockSignals(False)

        self._loaded = True
        self._metric = metrics[0].lower()
        if self._metric_combo.count() > 0:
            self._metric_combo.setCurrentIndex(0)
        self._draw()

    def _on_metric_changed(self, text: str) -> None:
        if not self._loaded:
            return
        self._metric = text.strip().lower()
        self._draw()

    # ----------------------------------------------------------------
    # Chart drawing
    # ----------------------------------------------------------------
    def _draw(self) -> None:
        structure = self._mgr.structure()
        if structure is None or not structure.has_train_log:
            self._draw_placeholder("No train_log data")
            return

        csv_path = structure.train_log_dir / f"{self._metric}.csv"
        if not csv_path.is_file():
            self._draw_placeholder(f"File not found: {csv_path}")
            return

        try:
            df = pd.read_csv(csv_path)
        except Exception as exc:
            logger.error("Failed to read %s: %s", csv_path, exc)
            self._draw_placeholder(f"Read error: {exc}")
            return

        if df.empty:
            self._draw_placeholder("CSV is empty")
            return

        # Strip whitespace from column names
        df.columns = [str(c).strip() for c in df.columns]

        # Detect long format (epoch, sample, metric_value) and pivot to wide
        sample_col_key = None
        for c in df.columns:
            if c.lower() == "sample":
                sample_col_key = c
                break
        if sample_col_key is not None:
            value_cols = [c for c in df.columns if c.lower() not in ("epoch", "sample")]
            if not value_cols:
                self._draw_placeholder("No numeric column in CSV")
                return
            # Use the LAST value column (skips extra columns like "seed")
            # The metric column is typically the last one in long format
            value_col = value_cols[-1]
            try:
                # ``aggfunc="last"`` picks the most recently recorded
                # seed at each (epoch, sample) cell, which is the
                # value we want for the final-epoch bar chart (and
                # especially for ``loss`` where the LAST epoch's loss
                # is the metric's representative value).
                df = df.pivot_table(index="epoch", columns=sample_col_key, values=value_col, aggfunc="last")
                df = df.reset_index()
            except Exception as exc:
                logger.warning("Pivot failed for %s: %s", csv_path, exc)
                self._draw_placeholder(f"Data format error: {exc}")
                return

        if df.empty:
            self._draw_placeholder("No data after processing")
            return

        # Get last epoch row for final values
        last_row = df.iloc[-1]
        sample_cols = [c for c in df.columns if str(c).lower() not in ("epoch", "")]
        if not sample_cols:
            self._draw_placeholder("No sample columns")
            return

        values = []
        labels = []
        for col in sample_cols:
            try:
                v = float(last_row[col])
            except (ValueError, TypeError):
                v = np.nan
            values.append(v)
            labels.append(str(col))

        values_arr = np.array(values, dtype=float)
        valid = ~np.isnan(values_arr)
        valid_vals = values_arr[valid]

        # Compute statistics
        if valid.any():
            mean_val = float(np.mean(valid_vals))
            median_val = float(np.median(valid_vals))
            max_val = float(np.max(valid_vals))
            min_val = float(np.min(valid_vals))
            std_val = float(np.std(valid_vals))
            q1 = float(np.percentile(valid_vals, 25))
            q3 = float(np.percentile(valid_vals, 75))
        else:
            mean_val = median_val = max_val = min_val = std_val = q1 = q3 = 0.0

        self._figure.clear()
        # Create figure with bar chart + stats table
        gs = self._figure.add_gridspec(1, 2, width_ratios=[3, 1], wspace=0.3)

        # Left: bar chart
        ax = self._figure.add_subplot(gs[0, 0])
        x = np.arange(len(labels))
        width = 0.6
        colors = ["#5b8fd9", "#3cba9a", "#4caf6e", "#d4b030", "#d48840",
                  "#d47068", "#9b6ab8", "#5ba0d0", "#e67e22", "#1abc9c",
                  "#3498db", "#e74c3c"][:len(labels)]
        bars = ax.bar(x, values_arr, width, color=colors, edgecolor="#3a6fb5", linewidth=0.5)

        ax.axhline(y=mean_val, color="#e74c3c", linestyle="--", linewidth=1.5, label=f"Mean = {mean_val:.4f}")
        ax.axhline(y=median_val, color="#f39c12", linestyle=":", linewidth=1.5, label=f"Median = {median_val:.4f}")

        ax.set_xticks(x)
        ax.set_xticklabels(labels, rotation=45, ha="right", fontsize=9)
        ax.set_ylabel(self._metric.upper(), fontsize=12)
        ax.set_title(f"{self._metric.upper()} - Final Epoch", fontsize=14, fontweight="bold")
        ax.legend(fontsize=10)
        ax.grid(axis="y", alpha=0.3)

        # Right: statistics table
        ax_table = self._figure.add_subplot(gs[0, 1])
        ax_table.axis("off")
        stats_data = [
            ["Mean", f"{mean_val:.4f}"],
            ["Median", f"{median_val:.4f}"],
            ["Max", f"{max_val:.4f}"],
            ["Min", f"{min_val:.4f}"],
            ["Std", f"{std_val:.4f}"],
            ["Q1", f"{q1:.4f}"],
            ["Q3", f"{q3:.4f}"],
        ]
        table = ax_table.table(
            cellText=stats_data,
            colLabels=["Statistic", "Value"],
            cellLoc="center",
            loc="center",
        )
        table.auto_set_font_size(False)
        table.set_fontsize(9)
        table.scale(1.0, 1.5)
        for key, cell in table.get_celld().items():
            cell.set_edgecolor("#ddd")
            if key[0] == 0:
                cell.set_facecolor("#e8e8e8")
                cell.set_fontsize(10)
        ax_table.set_title("Statistics", fontsize=12, fontweight="bold", pad=12)

        # tight_layout() can't handle axes containing a matplotlib table,
        # so use subplots_adjust() to avoid the UserWarning. The values below
        # mirror the padding tight_layout would otherwise pick.
        self._figure.subplots_adjust(left=0.08, right=0.98, top=0.92, bottom=0.18,
                                       wspace=0.25)
        self._canvas.draw()

    def _draw_placeholder(self, message: str) -> None:
        self._figure.clear()
        ax = self._figure.add_subplot(111)
        ax.text(0.5, 0.5, message, transform=ax.transAxes, ha="center", va="center",
                fontsize=16, color="#888")
        ax.set_xticks([])
        ax.set_yticks([])
        self._figure.tight_layout()
        self._canvas.draw()

