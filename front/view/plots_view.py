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

        self._build_ui()

    def _build_ui(self) -> None:
        root_ly = QVBoxLayout(self)
        root_ly.setContentsMargins(40, 34, 40, 34)
        root_ly.setSpacing(12)

        title = QLabel("\u2197  Plots")
        title.setStyleSheet("font-size: 24px; font-weight: 800; color: #1a1a1a;")
        root_ly.addWidget(title)

        ctrl_row = QHBoxLayout()
        ctrl_row.setSpacing(12)

        ctrl_row.addWidget(QLabel("指标: "))
        self._metric_combo = QComboBox()
        self._metric_combo.setFixedWidth(120)
        self._metric_combo.setStyleSheet(
            "QComboBox { background: #fff; border: 1px solid #ddd; border-radius: 4px; padding: 4px 8px; }"
        )
        self._metric_combo.currentTextChanged.connect(self._on_metric_changed)
        ctrl_row.addWidget(self._metric_combo)

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

        metrics = structure.train_log_metrics
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

    def _on_smooth_toggled(self, checked: bool) -> None:
        self._smooth = checked
        self._draw()

    # ----------------------------------------------------------------
    # Chart drawing
    # ----------------------------------------------------------------
    def _draw(self) -> None:
        structure = self._mgr.structure()
        if structure is None or not structure.has_train_log:
            self._draw_placeholder("\u2139  train_log 未找到")
            return

        csv_path = structure.train_log_dir / f"{self._metric}.csv"
        if not csv_path.is_file():
            self._draw_placeholder(f"\u26A0  文件不存在: {csv_path}")
            return

        try:
            df = pd.read_csv(csv_path)
        except Exception as exc:
            logger.error("Failed to read %s: %s", csv_path, exc)
            self._draw_placeholder(f"\u274C  读取失败: {exc}")
            return

        if df.empty:
            self._draw_placeholder("\u2139  CSV 文件为空")
            return

        sample_cols = [c for c in df.columns if c.lower().strip() not in ("epoch",)]
        if not sample_cols:
            self._draw_placeholder("\u26A0  CSV 中无样本列")
            return

        epoch_col = "epoch" if "epoch" in df.columns else None
        if epoch_col:
            x = df[epoch_col].values
        else:
            x = range(len(df))

        self._figure.clear()
        ax = self._figure.add_subplot(111)

        for col in sample_cols:
            y = pd.to_numeric(df[col], errors="coerce").values
            if self._smooth and len(y) > 5:
                y = pd.Series(y).rolling(window=5, min_periods=1).mean().values
            ax.plot(x, y, linewidth=1.2, alpha=0.75, label=str(col))

        ax.set_xlabel("Epoch" if epoch_col else "Step", fontsize=11)
        ax.set_ylabel(self._metric.upper(), fontsize=11)
        ax.set_title(f"训练曲线 — {self._metric.upper()}", fontsize=14, fontweight="bold")
        ax.grid(alpha=0.3)
        if len(sample_cols) <= 12:
            ax.legend(fontsize=8, ncol=2, loc="best")
        self._figure.tight_layout()
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
