"""Overlay scatter view ? GT vs Prediction error analysis."""
from typing import Optional

import numpy as np
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from model.overlay_data import (
    ERROR_ALPHA,
    ERROR_COLORS,
    ERROR_SHAPES,
    ERROR_SIZE,
    ErrorType,
    OverlayDataset,
)
from utils.logger import logger


_NO_DATA_DARK = "color: #95a5a6; font-size: 16px;"
_NO_DATA_LIGHT = "color: #7f8c8d; font-size: 16px;"


class OverlayViewWidget(QWidget):
    """Matplotlib scatter plot for overlay GT vs Prediction comparison.

    Shows cells as scatter points color-coded by error type:
    - Correct: muted, low-saturation, semi-transparent
    - Misclassification: orange diamonds
    - Embedding Shift: cyan triangles
    - Critical Error: red stars
    """

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self._dark: bool = True
        self._dataset: Optional[OverlayDataset] = None
        self._annot: Optional[object] = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        # Info bar
        info_layout = QHBoxLayout()
        info_layout.setContentsMargins(8, 4, 8, 4)

        self._info_label = QLabel("No overlay data loaded")
        self._info_label.setStyleSheet(
            "font-size: 13px; color: #95a5a6;" if self._dark
            else "font-size: 13px; color: #7f8c8d;"
        )
        info_layout.addWidget(self._info_label)
        info_layout.addStretch()

        # Legend
        legend_layout = QHBoxLayout()
        legend_layout.setSpacing(12)
        self._legend_labels: dict[ErrorType, QLabel] = {}
        legend_data = [
            (ErrorType.MISCLASSIFICATION, "Misclassification", "#e67e22", "◆"),
            (ErrorType.CRITICAL_ERROR, "Critical Error", "#ff3838", "✦"),
        ]
        for etype, name, color, shape in legend_data:
            lbl = QLabel(f'<span style="color:{color};">{shape}</span> {name}')
            lbl.setStyleSheet("font-size: 12px;")
            legend_layout.addWidget(lbl)
            self._legend_labels[etype] = lbl
        legend_layout.addStretch()
        info_layout.addLayout(legend_layout)
        layout.addLayout(info_layout)

        # Matplotlib canvas
        self._figure = Figure(figsize=(8, 6), dpi=100)
        self._canvas = FigureCanvas(self._figure)
        self._canvas.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )
        self._canvas.mpl_connect("motion_notify_event", self._on_hover)
        self._canvas.setVisible(True)

        self._figure.clear()
        self._ax = self._figure.add_subplot(111)
        self._ax.set_facecolor("#1e1e1e")
        self._ax.set_xticks([])
        self._ax.set_yticks([])
        self._figure.patch.set_facecolor("#2d2d2d")
        self._canvas.draw()

        self._no_data_label = QLabel("No Overlay Data Available")
        self._no_data_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._no_data_label.setStyleSheet(_NO_DATA_DARK)

        layout.addWidget(self._no_data_label)
        layout.addWidget(self._canvas)
        self._no_data_label.setVisible(False)

    def update_theme(self, dark: bool) -> None:
        self._dark = dark
        self._no_data_label.setStyleSheet(
            _NO_DATA_DARK if dark else _NO_DATA_LIGHT
        )
        if self._dataset is None:
            return
        if dark:
            self._figure.patch.set_facecolor("#2d2d2d")
            self._ax.set_facecolor("#1e1e1e")
        else:
            self._figure.patch.set_facecolor("#f0f0f0")
            self._ax.set_facecolor("#ffffff")
        self._canvas.draw()

    def set_dataset(self, dataset: Optional[OverlayDataset]) -> None:
        self._dataset = dataset
        if dataset is None or dataset.cell_count == 0:
            self._render_empty()
            return

        self._no_data_label.setVisible(False)
        self._canvas.setVisible(True)

        self._figure.clear()
        self._ax = self._figure.add_subplot(111)
        self._render_scatter()

        self._figure.tight_layout(pad=1.0)
        self._canvas.draw()

    def _render_empty(self) -> None:
        self._figure.clear()
        self._ax = self._figure.add_subplot(111)
        self._ax.set_facecolor(
            "#1e1e1e" if self._dark else "#ffffff"
        )
        self._ax.set_xticks([])
        self._ax.set_yticks([])
        self._canvas.draw()
        self._no_data_label.setVisible(True)
        self._canvas.setVisible(False)

    def _render_scatter(self) -> None:
        if self._dataset is None:
            return

        cells = self._dataset.cells
        if not cells:
            return

        bg = "#1e1e1e" if self._dark else "#ffffff"
        self._ax.set_facecolor(bg)

        # Group by error type
        groups: dict[ErrorType, list] = {}
        for c in cells:
            groups.setdefault(c.error_type, []).append(c)

        artists = []
        for etype in ErrorType:
            if etype not in groups:
                continue
            group_cells = groups[etype]
            xs = [c.x for c in group_cells]
            ys = [c.y for c in group_cells]
            color = ERROR_COLORS[etype]
            shape = ERROR_SHAPES[etype]
            alpha = ERROR_ALPHA[etype]
            size = ERROR_SIZE[etype]

            # Correct points first (zorder 0), errors on top (zorder 2)
            zorder = 0 if etype == ErrorType.CORRECT else 2
            edge = "none" if etype == ErrorType.CORRECT else color
            face = color if etype == ErrorType.CORRECT else "none"

            if etype == ErrorType.CORRECT:
                sc = self._ax.scatter(
                    xs, ys, s=size, c=color, marker=shape,
                    alpha=alpha, zorder=zorder, edgecolors="none",
                    label="Correct",
                )
            else:
                linewidth = 1.5
                sc = self._ax.scatter(
                    xs, ys, s=size * 8, c="none", marker=shape,
                    alpha=alpha, zorder=zorder,
                    edgecolors=color, linewidth=linewidth,
                    label=etype.name.capitalize().replace("_", " "),
                )
            artists.append(sc)

        self._ax.set_aspect("equal")
        self._ax.invert_yaxis()
        self._ax.set_xticks([])
        self._ax.set_yticks([])

        if self._dark:
            self._ax.tick_params(colors="#ddd")
            for spine in self._ax.spines.values():
                spine.set_color("#444")
        else:
            self._ax.tick_params(colors="#333")
            for spine in self._ax.spines.values():
                spine.set_color("#ccc")

        # Legend for errors only
        legend = self._ax.legend(
            loc="upper right", framealpha=0.7,
            fontsize=8, labelcolor="#ccc" if self._dark else "#333",
        )
        if self._dark:
            legend.get_frame().set_facecolor("#333")
        else:
            legend.get_frame().set_facecolor("#eee")

        # Info text
        total = self._dataset.cell_count
        errors = self._dataset.error_count
        err_pct = 100.0 * errors / max(total, 1)
        self._info_label.setText(
            f"Section {self._dataset.section_id}  |  "
            f"Cells: {total}  |  Errors: {errors} ({err_pct:.1f}%)  |  "
            f"GT: layer_guess  |  Pred: GraphBased"
        )
        self._info_label.setStyleSheet(
            "font-size: 13px; color: #ccc;" if self._dark
            else "font-size: 13px; color: #333;"
        )

    def _on_hover(self, event) -> None:
        if self._dataset is None or event.inaxes != self._ax:
            if self._annot is not None:
                self._annot.set_visible(False)
                self._canvas.draw_idle()
            return

        # Find nearest cell (simplified: just check if over any point)
        # For performance with 20k+ cells, we skip expensive nearest-neighbor search
        # Tooltip is shown in status bar via controller instead
        pass

    def show_no_data(self) -> None:
        self._dataset = None
        self._render_empty()
        self._info_label.setText("No overlay data loaded")
        self._info_label.setStyleSheet(
            "font-size: 13px; color: #95a5a6;" if self._dark
            else "font-size: 13px; color: #7f8c8d;"
        )

    def get_dataset(self) -> Optional[OverlayDataset]:
        return self._dataset
