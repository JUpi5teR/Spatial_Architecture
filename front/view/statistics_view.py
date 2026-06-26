# coding: utf-8
"""Statistics page -- bar chart + _stats.json matrix table.

指标: ARI, NMI, HS, CS
展示: 每个样本一组柱子 + 全局 Mean / Median

下方为 train_log/_stats.json 矩阵表格，以行=指标、列=样本的 CSV 矩阵形式展示。
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

import numpy as np
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
from matplotlib.figure import Figure

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QFrame, QHBoxLayout, QHeaderView, QLabel, QScrollArea,
    QSizePolicy, QTableWidget, QTableWidgetItem, QVBoxLayout,
    QWidget, QComboBox,
)

from model.data_path import DataPathManager, TRAIN_LOG_METRICS
from front.model.train_log_stats import compute_per_sample_best, read_metric_csv
from utils.logger import logger


class StatisticsViewWidget(QWidget):
    """Bar-chart view of clustering metrics per sample + _stats.json matrix."""

    def __init__(self, path_mgr: DataPathManager, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self._mgr = path_mgr
        self._canvas: Optional[FigureCanvasQTAgg] = None
        self._figure: Optional[Figure] = None
        self._metric_combo: Optional[QComboBox] = None
        self._metric = "ari"
        self._loaded = False
        self._dark = False
        self._stats_table: Optional[QTableWidget] = None

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
            txt = lbl.text()
            if txt.startswith("\u2261"):
                lbl.setStyleSheet(f"font-size: 24px; font-weight: 800; color: {fg};")
            elif "\u6307\u6807" in txt:
                lbl.setStyleSheet(f"font-size: 12px; color: {fg};")
            elif hasattr(lbl, "objectName") and lbl.objectName() == "statsTableTitle":
                lbl.setStyleSheet(f"font-size: 16px; font-weight: 700; color: {fg}; padding-top: 8px;")
            elif hasattr(lbl, "objectName") and lbl.objectName() == "statsTableHint":
                lbl.setStyleSheet(f"font-size: 11px; color: {'#8a8a90' if dark else '#888'}; padding-bottom: 4px;")
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
        self._apply_table_theme()


    def _build_ui(self) -> None:
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setStyleSheet(
            "QScrollArea { background: transparent; border: none; }"
            "QScrollBar:vertical { background: transparent; width: 8px; }"
            "QScrollBar::handle:vertical { background: rgba(128,128,128,0.3); border-radius: 4px; min-height: 30px; }"
            "QScrollBar::handle:vertical:hover { background: rgba(128,128,128,0.5); }"
            "QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }"
        )

        inner = QWidget()
        inner.setObjectName("statisticsInner")

        root_ly = QVBoxLayout(inner)
        root_ly.setContentsMargins(40, 34, 40, 34)
        root_ly.setSpacing(12)

        title = QLabel("\u2261  Statistics")
        title.setStyleSheet("font-size: 24px; font-weight: 800; color: #1a1a1a;")
        root_ly.addWidget(title)

        sel_row = QHBoxLayout()
        sel_row.addWidget(QLabel("\u9009\u62e9\u6307\u6807:"))
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

        self._figure = Figure(figsize=(9, 5), dpi=100)
        self._canvas = FigureCanvasQTAgg(self._figure)
        self._canvas.setFixedHeight(500)
        self._canvas.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        root_ly.addWidget(self._canvas)

        sep2 = QFrame()
        sep2.setFrameShape(QFrame.Shape.HLine)
        sep2.setStyleSheet("background: #ececec; max-height: 1px; min-height: 1px;")
        root_ly.addWidget(sep2)

        table_title = QLabel("train_log / _stats.json")
        table_title.setObjectName("statsTableTitle")
        table_title.setStyleSheet("font-size: 16px; font-weight: 700; color: #1a1a1a; padding-top: 8px;")
        root_ly.addWidget(table_title)

        table_hint = QLabel("Matrix: rows = metrics, columns = samples, cells = best_value")
        table_hint.setObjectName("statsTableHint")
        table_hint.setStyleSheet("font-size: 11px; color: #888; padding-bottom: 4px;")
        root_ly.addWidget(table_hint)

        self._stats_table = QTableWidget()
        self._stats_table.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)
        self._stats_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self._stats_table.verticalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Fixed)
        self._stats_table.verticalHeader().setDefaultSectionSize(36)
        self._stats_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._stats_table.setSelectionMode(QTableWidget.SelectionMode.NoSelection)
        self._stats_table.setAlternatingRowColors(False)
        self._stats_table.setShowGrid(True)
        root_ly.addWidget(self._stats_table)

        root_ly.addStretch()

        scroll.setWidget(inner)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(scroll)


    def load_data(self) -> None:
        if not self._mgr.has_valid_data():
            self._draw_placeholder("\u26a0  \u8bf7\u5148\u4e0a\u4f20\u6570\u636e\u6587\u4ef6\u5939 (Upload Data)")
            self._loaded = False
            return

        structure = self._mgr.structure()
        if structure is None or not structure.has_train_log or not structure.train_log_metrics:
            self._draw_placeholder("\u2139  train_log \u672a\u627e\u5230\uff0c\u6682\u65e0\u7edf\u8ba1\u6570\u636e\u663e\u793a")
            self._loaded = False
            return

        metrics = structure.train_log_metrics
        self._metric_combo.blockSignals(True)
        self._metric_combo.clear()
        for m in TRAIN_LOG_METRICS:
            if m in metrics:
                self._metric_combo.addItem(m.upper())
        self._metric_combo.blockSignals(False)
        self._loaded = True

        idx = max(0, self._metric_combo.findText(self._metric.upper()))
        if self._metric_combo.count() > 0:
            self._metric_combo.setCurrentIndex(idx)
        self._draw()
        self._load_stats_json_table(structure.train_log_dir)

    def _on_metric_changed(self, text: str) -> None:
        if not self._loaded:
            return
        self._metric = text.strip().lower()
        self._draw()


    def _draw(self) -> None:
        structure = self._mgr.structure()
        if structure is None or not structure.has_train_log:
            self._draw_placeholder("No train_log data")
            return

        csv_path = structure.train_log_dir / f"{self._metric}.csv"
        if not csv_path.is_file():
            self._draw_placeholder(f"File not found: {csv_path}")
            return

        per_sample_rows, _raw, _dedup = read_metric_csv(csv_path)
        if not per_sample_rows:
            self._draw_placeholder("No data in CSV")
            return

        sample_best = compute_per_sample_best(per_sample_rows, self._metric)
        labels = sorted(sample_best.keys())
        values_arr = np.array([sample_best[k] for k in labels], dtype=float)

        valid = ~np.isnan(values_arr)
        valid_vals = values_arr[valid]

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
        gs = self._figure.add_gridspec(1, 2, width_ratios=[3, 1], wspace=0.3)

        ax = self._figure.add_subplot(gs[0, 0])
        x = np.arange(len(labels))
        width = 0.6
        colors = ["#5b8fd9", "#3cba9a", "#4caf6e", "#d4b030", "#d48840",
                  "#d47068", "#9b6ab8", "#5ba0d0", "#e67e22", "#1abc9c",
                  "#3498db", "#e74c3c"][:len(labels)]
        ax.bar(x, values_arr, width, color=colors, edgecolor="#3a6fb5", linewidth=0.5)

        ax.axhline(y=mean_val, color="#e74c3c", linestyle="--", linewidth=1.5, label=f"Mean = {mean_val:.4f}")
        ax.axhline(y=median_val, color="#f39c12", linestyle=":", linewidth=1.5, label=f"Median = {median_val:.4f}")

        ax.set_xticks(x)
        ax.set_xticklabels(labels, rotation=45, ha="right", fontsize=9)
        ax.set_ylabel(self._metric.upper(), fontsize=12)
        ax.set_title(f"{self._metric.upper()} - Best per Sample", fontsize=14, fontweight="bold")
        ax.legend(fontsize=10)
        ax.grid(axis="y", alpha=0.3)

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

        self._figure.subplots_adjust(left=0.08, right=0.98, top=0.92, bottom=0.18, wspace=0.25)
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


    def _load_stats_json_table(self, train_log_dir: Path) -> None:
        """Load _stats.json and populate the QTableWidget as a matrix."""
        stats_path = train_log_dir / "_stats.json"
        if not stats_path.is_file():
            self._stats_table.setRowCount(0)
            self._stats_table.setColumnCount(1)
            self._stats_table.setHorizontalHeaderLabels(["No _stats.json"])
            return

        try:
            with open(stats_path, "r", encoding="utf-8") as fh:
                raw = json.load(fh)
        except (OSError, json.JSONDecodeError) as exc:
            logger.warning("Failed to read _stats.json: %s", exc)
            self._stats_table.setRowCount(0)
            self._stats_table.setColumnCount(1)
            self._stats_table.setHorizontalHeaderLabels(["Read error"])
            return

        metrics_data = raw.get("metrics", {})
        if not metrics_data:
            self._stats_table.setRowCount(0)
            self._stats_table.setColumnCount(1)
            self._stats_table.setHorizontalHeaderLabels(["No metrics"])
            return

        all_images: set = set()
        for mdata in metrics_data.values():
            if isinstance(mdata, dict):
                per_img = mdata.get("per_image", {})
                if isinstance(per_img, dict):
                    all_images.update(per_img.keys())
        images_sorted = sorted(all_images)

        metric_names = sorted(metrics_data.keys())

        columns = images_sorted + ["Grand Mean", "Best Image", "Best Value"]

        self._stats_table.setRowCount(len(metric_names))
        self._stats_table.setColumnCount(len(columns))
        self._stats_table.setHorizontalHeaderLabels(columns)
        self._stats_table.setVerticalHeaderLabels([m.upper() for m in metric_names])

        for row_idx, metric in enumerate(metric_names):
            mdata = metrics_data.get(metric, {})
            if not isinstance(mdata, dict):
                continue
            per_img = mdata.get("per_image", {}) if isinstance(mdata.get("per_image"), dict) else {}
            grand_mean = mdata.get("grand_mean", 0.0)
            best_image = str(mdata.get("best_image", "-"))
            best_val = mdata.get("best_image_value", 0.0)

            for col_idx, image_id in enumerate(images_sorted):
                img_data = per_img.get(image_id, {})
                val = img_data.get("best_value", float("nan")) if isinstance(img_data, dict) else float("nan")
                cell_text = f"{val:.4f}" if not np.isnan(val) else "-"
                item = QTableWidgetItem(cell_text)
                item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                self._stats_table.setItem(row_idx, col_idx, item)

            gm_col = len(images_sorted)
            item = QTableWidgetItem(f"{grand_mean:.4f}" if grand_mean else "-")
            item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self._stats_table.setItem(row_idx, gm_col, item)

            bi_col = len(images_sorted) + 1
            item = QTableWidgetItem(best_image)
            item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self._stats_table.setItem(row_idx, bi_col, item)

            bv_col = len(images_sorted) + 2
            item = QTableWidgetItem(f"{best_val:.4f}" if best_val else "-")
            item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self._stats_table.setItem(row_idx, bv_col, item)

        self._apply_table_theme()

    def _apply_table_theme(self) -> None:
        if self._stats_table is None:
            return
        dark = self._dark

        header_bg = "#2a2a2e" if dark else "#e8e8ec"
        header_fg = "#e8e8ec" if dark else "#1a1a1a"
        cell_bg = "#1e1e21" if dark else "#ffffff"
        cell_fg = "#d0d0d5" if dark else "#1a1a1a"
        grid_color = "#3a3a3e" if dark else "#e0e0e0"

        header_style = (
            f"QHeaderView::section {{"
            f" background-color: {header_bg}; color: {header_fg};"
            f" border: 1px solid {grid_color}; padding: 6px 8px;"
            f" font-weight: 700; font-size: 11px; }}"
        )
        self._stats_table.horizontalHeader().setStyleSheet(header_style)
        self._stats_table.verticalHeader().setStyleSheet(header_style)

        self._stats_table.setStyleSheet(
            f"QTableWidget {{"
            f" background-color: {cell_bg}; color: {cell_fg};"
            f" gridline-color: {grid_color}; border: 1px solid {grid_color};"
            f" font-size: 12px; }}"
            f"QTableWidget::item {{ padding: 4px 6px; }}"
        )

        data_col_count = self._stats_table.columnCount() - 3
        for row in range(self._stats_table.rowCount()):
            for col in range(max(0, data_col_count)):
                item = self._stats_table.item(row, col)
                if item is None:
                    continue
                try:
                    v = float(item.text())
                except ValueError:
                    continue
                t = min(max((v - 0.2) / 0.6, 0.0), 1.0)
                r = int(220 * (1 - t) + 40 * t)
                g = int(80 * (1 - t) + 180 * t)
                b = int(80 * (1 - t) + 100 * t)
                item.setBackground(QColor(r, g, b, 40 if dark else 30))

