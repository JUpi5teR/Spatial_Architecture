# coding: utf-8
"""Bottom panel displaying the DLPFC cortical histology reference table."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QSizePolicy, QVBoxLayout, QWidget,
)

from model.layer_info import get_layer_table


class LayerBiologyPanel(QFrame):
    """Compact reference panel showing the DLPFC cortical layer table.

    Height roughly 240 px. Columns: Layer | Name | Neuron Type | Thickness.
    Theme-aware via set_dark(bool).
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self._dark = False
        self._rows = []
        self.setObjectName("layerBiologyPanel")
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setFixedHeight(240)
        self._build_ui()
        self._apply_theme()

    def set_dark(self, dark):
        self._dark = dark
        self._apply_theme()

    def _apply_theme(self):
        if self._dark:
            bg, border, pri, sec, acc = "#2c2c2e", "#3a3a3c", "#f5f5f7", "#98989d", "#64d2ff"
        else:
            bg, border, pri, sec, acc = "#ffffff", "#e3e3e8", "#1d1d1f", "#6e6e73", "#0071e3"
        self.setStyleSheet(
            f"QFrame#layerBiologyPanel {{ background: {bg}; border: 1px solid {border}; border-radius: 10px; }}"
        )
        self._title.setStyleSheet(f"font-size: 13px; font-weight: 700; color: {pri};")
        self._header.setStyleSheet(
            f"font-size: 10px; font-weight: 600; color: {sec}; border-bottom: 1px solid {border};"
        )
        for row in self._rows:
            row["id"].setStyleSheet(f"font-weight: 700; font-size: 11px; color: {pri};")
            row["name"].setStyleSheet(f"font-size: 10px; color: {pri};")
            row["neuron"].setStyleSheet(f"font-size: 10px; color: {sec};")
            row["thick"].setStyleSheet(f"font-size: 10px; color: {sec};")

    def _build_ui(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(14, 10, 14, 10)
        outer.setSpacing(2)

        self._title = QLabel("Cortical Layer Reference  (DLPFC)")
        outer.addWidget(self._title)

        self._header = QLabel("Layer  Name                    Neuron Type                          Thickness")
        self._header.setFixedHeight(22)
        outer.addWidget(self._header)

        for li in get_layer_table():
            row_w = QWidget()
            row_w.setFixedHeight(24)
            row_lay = QHBoxLayout(row_w)
            row_lay.setContentsMargins(0, 0, 0, 0)
            row_lay.setSpacing(4)

            lid = QLabel(li.layer_id)
            lid.setFixedWidth(42)

            disp_name = li.name_cn + "  " + li.name_en
            name = QLabel(disp_name)
            name.setFixedWidth(185)

            neuron = QLabel(li.neuron_type)

            thick = QLabel(li.thickness)
            thick.setFixedWidth(56)
            thick.setAlignment(Qt.AlignmentFlag.AlignCenter)

            row_lay.addWidget(lid)
            row_lay.addWidget(name)
            row_lay.addWidget(neuron, 1)
            row_lay.addWidget(thick)
            outer.addWidget(row_w)

            self._rows.append({"id": lid, "name": name, "neuron": neuron, "thick": thick})

        outer.addStretch()