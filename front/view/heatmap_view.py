# coding: utf-8
"""Heatmap page - confusion matrix heatmap grid.

3 x 4 grid layout showing GT x Pred confusion matrices per sample.
Top-left corner: sample ID + ARI value (e.g. "151507 (ARI=0.540)").
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
from matplotlib.figure import Figure

from PySide6.QtWidgets import (
    QFrame, QHBoxLayout, QLabel,
    QSizePolicy, QVBoxLayout, QWidget,
)

from utils.logger import logger


class HeatmapViewWidget(QWidget):
    """Confusion matrix heatmap grid (3 x 4) for all samples."""

    def __init__(self, path_mgr, parent=None):
        super().__init__(parent)
        self._mgr = path_mgr
        self._canvas = None
        self._figure = None
        self._overlay_datasets = []
        self._ari_map = {}
        self._build_ui()

    def _build_ui(self):
        ly = QVBoxLayout(self)
        ly.setContentsMargins(20, 20, 20, 20)
        ly.setSpacing(10)

        title = QLabel("Confusion Matrix Heatmaps")
        title.setStyleSheet("font-size: 22px; font-weight: 800; color: #1a1a1a;")
        ly.addWidget(title)

        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet("background: #ececec; max-height: 1px; min-height: 1px;")
        ly.addWidget(sep)

        self._figure = Figure(figsize=(16, 12), dpi=100)
        self._canvas = FigureCanvasQTAgg(self._figure)
        self._canvas.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        ly.addWidget(self._canvas, 1)

    def load_data(self):
        structure = self._mgr.structure()
        if structure is None or not structure.is_valid:
            self._draw_placeholder("No data loaded")
            return
        self._draw()

    def set_overlay_datasets(self, datasets):
        self._overlay_datasets = datasets

    def set_ari_map(self, ari_map):
        self._ari_map = ari_map

    def _draw(self):
        datasets = self._overlay_datasets
        if not datasets:
            self._draw_placeholder("No overlay data available")
            return

        self._figure.clear()

        n = len(datasets)
        ncols = 4
        nrows = (n + ncols - 1) // ncols

        for idx, ds in enumerate(datasets):
            ax = self._figure.add_subplot(nrows, ncols, idx + 1)
            self._draw_single_confusion(ax, ds)

        self._figure.tight_layout(pad=3.0, h_pad=2.5, w_pad=2.5)
        self._canvas.draw()

    def _draw_single_confusion(self, ax, ds):
        sid = ds.section_id
        gt = ds.gt_clusters
        pr = ds.pred_clusters

        # Build confusion matrix
        if not gt or not pr or not ds.confusion:
            ax.text(0.5, 0.5, sid + "\nNo data", ha="center", va="center",
                   transform=ax.transAxes, fontsize=10, color="#888")
            ax.set_xticks([])
            ax.set_yticks([])
            return

        mat = np.zeros((len(gt), len(pr)), dtype=int)
        for (g, p), n in ds.confusion.items():
            if g in gt and p in pr:
                mat[gt.index(g), pr.index(p)] = n

        # Draw heatmap
        im = ax.imshow(mat, cmap="Blues", aspect="auto")

        # Shorten labels for display
        def _short(s):
            s = str(s)
            if s.startswith("Layer"):
                return "L" + s[5:]
            if s.startswith("Cluster"):
                return "C" + s[7:]
            return s[:6]

        gt_short = [_short(g) for g in gt]
        pr_short = [_short(p) for p in pr]

        ax.set_xticks(range(len(pr)))
        ax.set_xticklabels(pr_short, fontsize=7, rotation=0)
        ax.set_yticks(range(len(gt)))
        ax.set_yticklabels(gt_short, fontsize=7)

        # Cell values
        max_val = mat.max()
        for i in range(len(gt)):
            for j in range(len(pr)):
                v = mat[i, j]
                if v == 0:
                    continue
                color = "#fff" if max_val > 0 and v > max_val * 0.55 else "#333"
                ax.text(j, i, str(v), ha="center", va="center",
                        color=color, fontsize=6)

        # Top-left corner label: sample ID + ARI
        ari_val = self._ari_map.get(sid, None)
        if ari_val is not None:
            label = "%s (ARI=%.3f)" % (sid, ari_val)
        else:
            label = sid

        ax.set_title(label, fontsize=8, fontweight="bold", loc="left",
                    color="#1a1a1a", pad=2)

        # Axis labels
        ax.set_xlabel("Pred", fontsize=7, color="#666", labelpad=1)
        ax.set_ylabel("True", fontsize=7, color="#666", labelpad=1)

        # Remove spines
        for spine in ax.spines.values():
            spine.set_visible(False)

    def _draw_placeholder(self, message):
        self._figure.clear()
        ax = self._figure.add_subplot(111)
        ax.text(0.5, 0.5, message, transform=ax.transAxes, ha="center", va="center",
                fontsize=16, color="#888")
        ax.set_xticks([])
        ax.set_yticks([])
        self._figure.tight_layout()
        self._canvas.draw()