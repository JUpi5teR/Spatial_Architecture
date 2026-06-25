from typing import Optional

from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel, QSizePolicy, QVBoxLayout, QWidget

from utils.logger import logger

_NO_CURVE_DARK = "color: #95a5a6; font-size: 16px;"
_NO_CURVE_LIGHT = "color: #7f8c8d; font-size: 16px;"


class TrainingCurveWidget(QWidget):
    """Matplotlib embedded training curve widget."""

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self._dark: bool = True

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self._figure = Figure(figsize=(6, 3), dpi=100)
        self._canvas = FigureCanvas(self._figure)
        self._canvas.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self._no_data_label = QLabel("No Training Curve Available")
        self._no_data_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._no_data_label.setStyleSheet(_NO_CURVE_DARK)

        layout.addWidget(self._no_data_label)
        layout.addWidget(self._canvas)
        self._canvas.setVisible(False)
        self._has_curve = False

    def update_theme(self, dark: bool) -> None:
        self._dark = dark
        self._no_data_label.setStyleSheet(_NO_CURVE_DARK if dark else _NO_CURVE_LIGHT)

    def plot(
        self,
        epochs: list[int],
        y1_name: str,
        y1_values: list[float],
        y2_name: Optional[str] = None,
        y2_values: Optional[list[float]] = None,
    ) -> None:
        try:
            self._figure.clear()
            ax = self._figure.add_subplot(111)

            if self._dark:
                self._figure.patch.set_facecolor("#2d2d2d")
                ax.set_facecolor("#1e1e1e")
                ax.tick_params(colors="#ddd")
                ax.spines["bottom"].set_color("#555")
                ax.spines["top"].set_color("#555")
                ax.spines["left"].set_color("#555")
                ax.spines["right"].set_color("#555")
                ax.yaxis.label.set_color("#ddd")
                ax.xaxis.label.set_color("#ddd")
                ax.title.set_color("#ddd")
            else:
                self._figure.patch.set_facecolor("#f0f0f0")
                ax.set_facecolor("#ffffff")
                ax.tick_params(colors="#333")
                ax.spines["bottom"].set_color("#ccc")
                ax.spines["top"].set_color("#ccc")
                ax.spines["left"].set_color("#ccc")
                ax.spines["right"].set_color("#ccc")
                ax.yaxis.label.set_color("#333")
                ax.xaxis.label.set_color("#333")
                ax.title.set_color("#333")

            x = epochs
            ax.plot(x, y1_values, "b-o", label=y1_name, markersize=3, linewidth=1)
            if y2_name and y2_values:
                ax.plot(x, y2_values, "r-s", label=y2_name, markersize=3, linewidth=1)

            ax.set_xlabel("Epoch")
            ax.set_ylabel("Value")
            ax.set_title("Training Progress")
            ax.legend()
            ax.set_ylim(top=1)\n            ax.grid(True, alpha=0.3)

            self._figure.tight_layout()
            self._canvas.draw()

            self._no_data_label.setVisible(False)
            self._canvas.setVisible(True)
            self._has_curve = True
        except Exception as exc:
            logger.error("Failed to plot training curve: %s", exc)

    def show_no_data(self) -> None:
        self._figure.clear()
        self._canvas.draw()
        self._canvas.setVisible(False)
        self._no_data_label.setVisible(True)
        self._has_curve = False
