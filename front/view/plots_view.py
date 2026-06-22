# coding: utf-8
"""Plots 页面 —— 训练过程曲线 (Loss, ARI, NMI, HS, CS)。

读取 train_log 中每个指标的 .csv，按 epoch 绘制折线图。
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional

import pandas as pd
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
from matplotlib.figure import Figure

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QFrame, QHBoxLayout, QLabel,
    QSizePolicy, QVBoxLayout, QWidget, QListWidget, QAbstractItemView,
)

from model.data_path import DataPathManager, TRAIN_LOG_METRICS
from utils.logger import logger


class PlotsViewWidget(QWidget):
    """Line-chart view of training curves.

    Select one metric at a time; all sample columns are plotted.
    """

    def __init__(self, path_mgr: DataPathManager, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self._mgr = path_mgr
        self._canvas: Optional[FigureCanvasQTAgg] = None
        self._figure: Optional[Figure] = None
        self._metric_combo: Optional[QComboBox] = None
        self._metric = "loss"
        self._smooth = False
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
        self.setStyleSheet(f"PlotsViewWidget {{ background-color: {bg}; }}")
        for lbl in self.findChildren(QLabel):
            if lbl.text().startswith("↗"):
                lbl.setStyleSheet(f"font-size: 24px; font-weight: 800; color: {fg};")
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

    def _build_ui(self) -> None:
        root_ly = QVBoxLayout(self)
        root_ly.setContentsMargins(40, 34, 40, 34)
        root_ly.setSpacing(12)

        title = QLabel("\u2197  Plots")
        title.setStyleSheet("font-size: 24px; font-weight: 800; color: #1a1a1a;")
        root_ly.addWidget(title)

        ctrl_row = QHBoxLayout()
        ctrl_row.setSpacing(12)

        # All 5 metrics shown together per sample
        # Metric combo removed - all metrics displayed in grid

        self._smooth_check = QCheckBox("平滑 (窗口=5)")
        self._smooth_check.toggled.connect(self._on_smooth_toggled)
        ctrl_row.addWidget(self._smooth_check)

        ctrl_row.addStretch()
        root_ly.addLayout(ctrl_row)

        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet("background: #ececec; max-height: 1px; min-height: 1px;")
        root_ly.addWidget(sep)

        self._figure = Figure(figsize=(10, 5), dpi=100)
        self._canvas = FigureCanvasQTAgg(self._figure)
        self._canvas.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        root_ly.addWidget(self._canvas, 1)

    def load_data(self) -> None:
        if not self._mgr.has_valid_data():
            self._draw_placeholder("\u26A0  请先上传数据文件夹 (Upload Data)")
            self._loaded = False
            return

        structure = self._mgr.structure()
        if structure is None or not structure.has_train_log or not structure.train_log_metrics:
            self._draw_placeholder("\u2139  train_log 未找到，暂无训练曲线")
            self._loaded = False
            return

        self._loaded = True
        self._draw()

    def _on_smooth_toggled(self, checked: bool) -> None:
        self._smooth = checked
        self._draw()

    # ----------------------------------------------------------------
    # Chart drawing
    # ----------------------------------------------------------------
    def _draw(self) -> None:
        structure = self._mgr.structure()
        if structure is None or not structure.has_train_log:
            self._draw_placeholder("No train_log data")
            return

        metrics = structure.train_log_metrics
        if not metrics:
            self._draw_placeholder("No metrics available")
            return

        # Load all metrics data, pivoted to wide (epoch x sample)
        all_data = {}
        all_samples = set()
        for metric in metrics:
            csv_path = structure.train_log_dir / f"{metric}.csv"
            if not csv_path.is_file():
                continue
            try:
                df = pd.read_csv(csv_path)
            except Exception as exc:
                logger.error("Failed to read %s: %s", csv_path, exc)
                continue
            if df.empty:
                continue
            # Pivot if long format. Column names may be str or int after
            # pd.read_csv() / pivot_table(), so always cast before .lower().
            sample_col_key = None
            for c in df.columns:
                if str(c).lower().strip() == "sample":
                    sample_col_key = c
                    break
            if sample_col_key is not None:
                value_cols = [c for c in df.columns if str(c).lower().strip() not in ("epoch", "sample")]
                if not value_cols:
                    continue
                value_col = value_cols[0]
                df = df.pivot_table(index="epoch", columns=sample_col_key, values=value_col, aggfunc="first")
                df = df.reset_index()
            # Collect sample names (column names from pivot are typically ints like 151507)
            sample_cols = [c for c in df.columns if str(c).lower().strip() not in ("epoch",)]
            for sc in sample_cols:
                all_samples.add(str(sc))
            all_data[metric] = df

        if not all_data:
            self._draw_placeholder("No data to plot")
            return

        samples = sorted(all_samples, key=lambda s: (len(s), s))

        self._figure.clear()

        # Grid layout: 4 cols, as many rows as needed
        ncols = 4
        nrows = max(1, (len(samples) + ncols - 1) // ncols)
        metric_colors = {"ari": "#e74c3c", "cs": "#3498db", "hs": "#2ecc71",
                         "loss": "#e67e22", "nmi": "#9b59b6"}
        legend_colors = {}

        for idx, sample in enumerate(samples):
            ax = self._figure.add_subplot(nrows, ncols, idx + 1)

            for metric in metrics:
                df = all_data.get(metric)
                if df is None or sample not in df.columns:
                    continue
                if "epoch" in df.columns:
                    x = df["epoch"].values
                else:
                    x = range(len(df))

                y = pd.to_numeric(df[sample], errors="coerce").values
                if self._smooth and len(y) > 5:
                    y = pd.Series(y).rolling(window=5, min_periods=1).mean().values

                color = metric_colors.get(metric, "#888")
                ax.plot(x, y, linewidth=1.2, alpha=0.8, color=color, label=metric.upper())
                legend_colors[metric.upper()] = color

            ax.set_title(sample, fontsize=9, fontweight="bold")
            ax.set_xlabel("Epoch", fontsize=6)
            ax.set_ylabel("Value", fontsize=6)
            ax.tick_params(labelsize=6)
            ax.grid(alpha=0.2)
            ax.set_xlim(left=0)

        # Add single legend above all subplots
        handles = []
        for label, color in legend_colors.items():
            from matplotlib.lines import Line2D
            handles.append(Line2D([0], [0], color=color, linewidth=2, label=label))
        if handles:
            self._figure.legend(handles=handles, loc="upper center",
                              ncol=len(handles), fontsize=8,
                              bbox_to_anchor=(0.5, 1.01))

        self._figure.suptitle("Training Curves - All Samples",
                             fontsize=14, fontweight="bold", y=1.03)
        self._figure.tight_layout(rect=[0, 0, 1, 0.97])
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

