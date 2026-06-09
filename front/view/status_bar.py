from PySide6.QtCore import Qt
from PySide6.QtWidgets import QHBoxLayout, QLabel, QWidget, QVBoxLayout


class StatusWidget(QWidget):
    """A single status indicator (label + status)."""

    STATUS_COLORS = {
        "Loaded": "#27ae60",
        "Missing": "#e67e22",
        "Error": "#e74c3c",
    }

    def __init__(self, title: str, parent: QWidget | None = None):
        super().__init__(parent)
        self._title = title
        self._value_label = QLabel("Missing")
        self._value_label.setStyleSheet(
            f"color: {self.STATUS_COLORS['Missing']}; font-weight: bold;"
        )

        layout = QHBoxLayout(self)
        layout.setContentsMargins(4, 2, 4, 2)
        layout.addWidget(QLabel(f"{title}:"))
        layout.addWidget(self._value_label)
        layout.addStretch()

    def set_status(self, status: str) -> None:
        color = self.STATUS_COLORS.get(status, "#95a5a6")
        self._value_label.setText(status)
        self._value_label.setStyleSheet(f"color: {color}; font-weight: bold;")


class StatusBarWidget(QWidget):
    """Top status bar showing three status indicators."""

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)

        self.training_status = StatusWidget("Training Log")
        self.result_status = StatusWidget("Result")
        self.gt_status = StatusWidget("Ground Truth")

        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 4, 8, 4)
        layout.addWidget(self.training_status)
        layout.addWidget(self.result_status)
        layout.addWidget(self.gt_status)
        layout.addStretch()

    def update_theme(self, dark: bool) -> None:
        """Theme hook — status colors stay semantic; no changes needed."""
        pass


class ParamsWidget(QWidget):
    """Training parameters display (last row of the training log)."""

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(8, 4, 8, 4)
        self._params_container = QWidget()
        self._params_layout = QHBoxLayout(self._params_container)
        self._params_layout.setContentsMargins(0, 0, 0, 0)
        self._params_layout.setSpacing(12)
        self._layout.addWidget(self._params_container)

        self._no_data_label = QLabel("No Training Log Found")
        self._no_data_label.setStyleSheet("color: #e67e22; font-size: 14px;")
        self._no_data_label.setVisible(False)
        self._layout.addWidget(self._no_data_label)

    def update_theme(self, dark: bool) -> None:
        """Theme hook — orange warning color works in both themes."""
        pass

    def set_params(self, params: dict[str, float]) -> None:
        self._clear_params()
        if not params:
            self._no_data_label.setVisible(True)
            self._params_container.setVisible(False)
            return

        self._no_data_label.setVisible(False)
        self._params_container.setVisible(True)
        for key, value in params.items():
            lbl = QLabel(f"<b>{key}</b>: {value:.6g}")
            lbl.setStyleSheet("font-size: 13px;")
            self._params_layout.addWidget(lbl)
            self._params_layout.addSpacing(8)

    def clear(self) -> None:
        self._clear_params()
        self._no_data_label.setVisible(True)
        self._params_container.setVisible(False)

    def _clear_params(self) -> None:
        while self._params_layout.count():
            item = self._params_layout.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()
