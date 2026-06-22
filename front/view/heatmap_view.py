# coding: utf-8
"""Heatmap page - spatial heatmap viewer (interface placeholder).

Modes: Ground Truth / Prediction / Density.
Full rendering injected via set_renderer().
"""
from __future__ import annotations

from pathlib import Path
from typing import Callable, Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QComboBox, QFrame, QHBoxLayout, QLabel,
    QVBoxLayout, QWidget,
)

from model.data_path import DataPathManager


class HeatmapViewWidget(QWidget):
    """Spatial heatmap viewer with mode selector.

    Interface:
        load_data()    - refresh from DataPathManager
        clear()        - reset to placeholder
        set_renderer() - inject render callback

    Signals:
        mode_changed(str) - ground_truth / prediction / density
    """

    mode_changed = Signal(str)

    def __init__(self, path_mgr: DataPathManager, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self._mgr = path_mgr
        self._mode = "ground_truth"
        self._renderer: Optional[Callable] = None
        self._placeholder: Optional[QLabel] = None
        self._build_ui()

    # -------- public interface --------
    def load_data(self) -> None:
        if not self._mgr.has_valid_data():
            self._show_placeholder("⚠  请先上传数据文件夹 (Upload Data)")
            return
        if self._renderer is None:
            st = self._mgr.structure()
            n = len(st.section_ids) if st else 0
            self._show_placeholder(
                f"✅  数据已加载  |  样本: {n}\n\n"
                "Heatmap 渲染引擎待注入。"
            )
            return
        self._show_content()

    def clear(self) -> None:
        self._show_placeholder("ℹ  暂无数据")

    def set_renderer(self, renderer: Callable) -> None:
        self._renderer = renderer
        if self._mgr.has_valid_data():
            self.load_data()

    # -------- UI --------
    def _build_ui(self) -> None:
        ly = QVBoxLayout(self)
        ly.setContentsMargins(40, 34, 40, 34)
        ly.setSpacing(12)

        title = QLabel("▦  Heatmap")
        title.setStyleSheet("font-size: 24px; font-weight: 800; color: #1a1a1a;")
        ly.addWidget(title)

        ctrl = QHBoxLayout()
        ctrl.setSpacing(12)
        ctrl.addWidget(QLabel("模式:"))
        self._mode_combo = QComboBox()
        self._mode_combo.setFixedWidth(160)
        self._mode_combo.addItems(["Ground Truth", "Prediction", "Density"])
        self._mode_combo.setStyleSheet(
            "QComboBox { background: #fff; border: 1px solid #ddd; border-radius: 4px; padding: 4px 8px; }"
        )
        self._mode_combo.currentIndexChanged.connect(self._on_mode)
        ctrl.addWidget(self._mode_combo)
        ctrl.addStretch()
        ly.addLayout(ctrl)

        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet("background: #ececec; max-height: 1px; min-height: 1px;")
        ly.addWidget(sep)

        self._placeholder = QLabel("ℹ  暂无数据")
        self._placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._placeholder.setStyleSheet("color: #888; font-size: 14px;")
        self._placeholder.setWordWrap(True)
        ly.addWidget(self._placeholder, 1)

    def _on_mode(self, idx: int) -> None:
        modes = ["ground_truth", "prediction", "density"]
        if 0 <= idx < len(modes):
            self._mode = modes[idx]
            self.mode_changed.emit(self._mode)
            if self._renderer is not None and self._mgr.has_valid_data():
                self.load_data()

    def _show_placeholder(self, msg: str) -> None:
        if self._placeholder:
            self._placeholder.setText(msg)
            self._placeholder.setVisible(True)

    def _show_content(self) -> None:
        if self._placeholder:
            self._placeholder.setVisible(False)
