"""Data area below the 3D visualization.

Five tabs (per ideal front-end image):
  1. Data Summary      - aggregate metrics (Total Cells / Clusters / Agreement)
  2. Cluster Summary   - per-cluster table with Download button
  3. Confusion Matrix  - GT x Pred heatmap
  4. Mismatched Points - sortable list of misclassified spots
  5. Cluster Details   - selected cluster info (placeholder)
"""
from __future__ import annotations

from typing import Optional

import numpy as np
import pandas as pd
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QAbstractItemView, QComboBox, QFileDialog, QFrame, QGridLayout,
    QHBoxLayout, QHeaderView, QLabel, QLineEdit, QMenu, QPushButton,
    QSizePolicy, QTableWidget, QTableWidgetItem, QTabWidget, QVBoxLayout,
    QWidget,
)

from model.overlay_data import ClusterStat, ErrorType, OverlayDataset
from utils.logger import logger


# ====================================================================
#  Styles
# ====================================================================
_SUMMARY_LIGHT = """
QFrame#summaryCard {
    background: #ffffff;
    border: 1px solid #ececec;
    border-radius: 10px;
}
QLabel#summaryTitle { color: #888; font-size: 10px; font-weight: 600; }
QLabel#summaryValue {
    color: #1a1a1a; font-size: 22px; font-weight: 700;
}
QLabel#summarySub { color: #888; font-size: 10px; }
"""

_SUMMARY_DARK = """
QFrame#summaryCard {
    background: #1e1e21;
    border: 1px solid #2a2a2e;
    border-radius: 10px;
}
QLabel#summaryTitle { color: #8a8a90; font-size: 10px; font-weight: 600; }
QLabel#summaryValue {
    color: #f5f5f7; font-size: 22px; font-weight: 700;
}
QLabel#summarySub { color: #8a8a90; font-size: 10px; }
"""

_TAB_LIGHT = """
QTabWidget::pane {
    border: 1px solid #ececec;
    border-radius: 10px;
    background: #ffffff;
    top: -1px;
}
QTabBar::tab {
    background: transparent;
    color: #888;
    padding: 8px 14px;
    margin-right: 2px;
    font-size: 12px;
    font-weight: 600;
    border: none;
    border-bottom: 2px solid transparent;
}
QTabBar::tab:hover { color: #1a1a1a; }
QTabBar::tab:selected {
    color: #1a6bc0;
    border-bottom: 2px solid #1a6bc0;
}
"""

_TAB_DARK = """
QTabWidget::pane {
    border: 1px solid #2a2a2e;
    border-radius: 10px;
    background: #1e1e21;
    top: -1px;
}
QTabBar::tab {
    background: transparent;
    color: #8a8a90;
    padding: 8px 14px;
    margin-right: 2px;
    font-size: 12px;
    font-weight: 600;
    border: none;
    border-bottom: 2px solid transparent;
}
QTabBar::tab:hover { color: #f5f5f7; }
QTabBar::tab:selected {
    color: #64b4ff;
    border-bottom: 2px solid #64b4ff;
}
"""


# ====================================================================
#  Helpers
# ====================================================================
def _agreement_color(v: float) -> QColor:
    """Map agreement 0..1 to a traffic-light color."""
    if v >= 0.90:
        return QColor("#2ecc71")
    if v >= 0.70:
        return QColor("#f39c12")
    return QColor("#e74c3c")


def _fmt_pct(v: float) -> str:
    return f"{100.0 * v:.2f}%"


def _cluster_color(name: str) -> QColor:
    """Stable color per cluster name."""
    palette = {
        "Layer1": "#5ba0d0", "Layer2": "#3cba9a", "Layer3": "#4caf6e",
        "Layer4": "#d4b030", "Layer5": "#d48840", "Layer6": "#d47068",
        "WM": "#9b6ab8",
    }
    return QColor(palette.get(name, "#a0a8b0"))


# ====================================================================
#  Tab 1: Data Summary
# ====================================================================
class _DataSummaryCard(QFrame):
    def __init__(self, dark: bool = False):
        super().__init__()
        self.setObjectName("summaryCard")
        self._dark = dark
        self.setStyleSheet(_SUMMARY_DARK if dark else _SUMMARY_LIGHT)
        self.setFixedWidth(220)

        ly = QVBoxLayout(self)
        ly.setContentsMargins(16, 16, 16, 16)
        ly.setSpacing(14)

        rows = [
            ("Total Cells",   "cell_count",   "summaryValue"),
            ("Clusters (True)", "n_gt",       "summaryValue"),
            ("Clusters (Pred)", "n_pred",     "summaryValue"),
            ("Agreement",     "agreement",    "summaryValue"),
        ]
        self._value_labels: dict[str, QLabel] = {}
        for title, key, _ in rows:
            row = QVBoxLayout()
            row.setContentsMargins(0, 0, 0, 0)
            row.setSpacing(2)
            t = QLabel(title)
            t.setObjectName("summaryTitle")
            v = QLabel("--")
            v.setObjectName("summaryValue")
            row.addWidget(t)
            row.addWidget(v)
            ly.addLayout(row)
            self._value_labels[key] = v

        ly.addStretch()

    def update_dataset(self, ds: Optional[OverlayDataset]) -> None:
        v = self._value_labels
        if ds is None:
            for k in v:
                v[k].setText("--")
            v["agreement"].setStyleSheet(
                "color: #64b4ff; font-size: 22px; font-weight: 700;"
                if self._dark else
                "color: #1a6bc0; font-size: 22px; font-weight: 700;"
            )
            return
        v["cell_count"].setText(f"{ds.cell_count:,}")
        v["n_gt"].setText(str(len(ds.gt_clusters)))
        v["n_pred"].setText(str(len(ds.pred_clusters)))
        v["agreement"].setText(_fmt_pct(1.0 - ds.error_rate))
        v["agreement"].setStyleSheet(
            f"color: {_agreement_color(1.0 - ds.error_rate).name()};"
            " font-size: 22px; font-weight: 700;"
        )

    def set_dark(self, dark: bool) -> None:
        self._dark = dark
        self.setStyleSheet(_SUMMARY_DARK if dark else _SUMMARY_LIGHT)


# ====================================================================
#  Tab 2: Cluster Summary
# ====================================================================
class _ClusterSummaryTab(QWidget):
    HEADERS = [
        "Cluster ID (True)", "Cluster Name", "# Cells",
        "Cluster ID (Pred)", "# Cells", "Agreement", "Mismatched",
    ]

    def __init__(self, dark: bool = False):
        super().__init__()
        self._dark = dark
        self._stats: list[ClusterStat] = []

        ly = QVBoxLayout(self)
        ly.setContentsMargins(0, 0, 0, 0)
        ly.setSpacing(0)

        # Toolbar
        toolbar = QHBoxLayout()
        toolbar.setContentsMargins(12, 8, 12, 8)
        spacer = QLabel("")
        self._dl_btn = QPushButton("\u2B07  Download")
        self._dl_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._dl_btn.setStyleSheet(
            "QPushButton { font-size: 11px; padding: 4px 10px; border: 1px solid #ddd;"
            " border-radius: 5px; background: #fafafa; color: #333; }"
            "QPushButton:hover { background: #eef3fb; }"
        )
        self._dl_btn.clicked.connect(self._download)
        self._more_btn = QPushButton("\u2026")
        self._more_btn.setFixedWidth(28)
        self._more_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._more_btn.setStyleSheet(self._dl_btn.styleSheet())
        self._more_btn.clicked.connect(self._show_more_menu)
        toolbar.addStretch()
        toolbar.addWidget(self._dl_btn)
        toolbar.addWidget(self._more_btn)
        ly.addLayout(toolbar)

        # Table
        self._table = QTableWidget(0, len(self.HEADERS))
        self._table.setHorizontalHeaderLabels(self.HEADERS)
        self._table.verticalHeader().setVisible(False)
        self._table.setSelectionBehavior(
            QAbstractItemView.SelectionBehavior.SelectRows
        )
        self._table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._table.setAlternatingRowColors(True)
        self._table.setShowGrid(False)
        self._table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.Stretch
        )
        self._table.horizontalHeader().setSectionResizeMode(
            0, QHeaderView.ResizeMode.ResizeToContents
        )
        self._table.horizontalHeader().setSectionResizeMode(
            3, QHeaderView.ResizeMode.ResizeToContents
        )
        self._table.setStyleSheet(self._table_style())
        ly.addWidget(self._table, 1)

    def _table_style(self) -> str:
        if self._dark:
            return """
                QTableWidget {
                    background: #1e1e21; alternate-background-color: #232327;
                    gridline-color: #2a2a2e; color: #f5f5f7;
                    font-size: 12px; border: none;
                }
                QHeaderView::section {
                    background: #1a1a1d; color: #8a8a90;
                    padding: 6px 8px; border: none;
                    border-bottom: 1px solid #2a2a2e;
                    font-weight: 600; font-size: 11px;
                }
                QTableWidget::item { padding: 6px 8px; }
                QTableWidget::item:selected { background: rgba(100,180,255,0.20); }
            """
        return """
            QTableWidget {
                background: #ffffff; alternate-background-color: #fafbfc;
                gridline-color: #ececec; color: #1a1a1a;
                font-size: 12px; border: none;
            }
            QHeaderView::section {
                background: #fafafa; color: #666;
                padding: 6px 8px; border: none;
                border-bottom: 1px solid #ececec;
                font-weight: 600; font-size: 11px;
            }
            QTableWidget::item { padding: 6px 8px; }
            QTableWidget::item:selected { background: #e3eefb; color: #1a6bc0; }
        """

    def update_dataset(self, ds: Optional[OverlayDataset]) -> None:
        self._stats = ds.cluster_stats if ds else []
        self._table.setRowCount(len(self._stats))
        for r, st in enumerate(self._stats):
            values = [
                (str(st.gt_id) if st.gt_id is not None else "-", "c"),
                (st.gt_name, "c"),
                (f"{st.n_true:,}", "n"),
                (str(st.pred_id) if st.pred_id is not None else "-", "c"),
                (f"{st.n_pred:,}", "n"),
                (_fmt_pct(st.agreement), "a"),
                (str(st.n_misclass), "n"),
            ]
            for c, (val, kind) in enumerate(values):
                item = QTableWidgetItem(val)
                if kind == "n":
                    item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                if c == 1:  # Cluster Name
                    item.setForeground(_cluster_color(st.gt_name))
                if c == 5:  # Agreement
                    item.setForeground(_agreement_color(st.agreement))
                if c == 6:  # Mismatched
                    item.setForeground(QColor("#e74c3c" if st.n_misclass else "#888"))
                self._table.setItem(r, c, item)

    def set_dark(self, dark: bool) -> None:
        self._dark = dark
        self._table.setStyleSheet(self._table_style())

    def _download(self) -> None:
        if not self._stats:
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "Export cluster summary", "cluster_summary.csv",
            "CSV (*.csv);;Excel (*.xlsx)",
        )
        if not path:
            return
        try:
            rows = [
                {
                    "Cluster ID (True)": s.gt_id,
                    "Cluster Name": s.gt_name,
                    "# Cells (True)": s.n_true,
                    "Cluster ID (Pred)": s.pred_id,
                    "# Cells (Pred)": s.n_pred,
                    "Agreement": s.agreement,
                    "Mismatched": s.n_misclass,
                }
                for s in self._stats
            ]
            df = pd.DataFrame(rows)
            if path.lower().endswith(".xlsx"):
                df.to_excel(path, index=False)
            else:
                df.to_csv(path, index=False)
            logger.info("Exported cluster summary to %s", path)
        except Exception as exc:
            logger.error("Export failed: %s", exc)

    def _show_more_menu(self) -> None:
        menu = QMenu(self)
        menu.addAction("Export as CSV", self._download)
        menu.addAction("Reset table view", lambda: self._table.resizeColumnsToContents())
        menu.exec(self._more_btn.mapToGlobal(self._more_btn.rect().bottomLeft()))


# ====================================================================
#  Tab 3: Confusion Matrix
# ====================================================================
class _ConfusionMatrixTab(QWidget):
    def __init__(self, dark: bool = False):
        super().__init__()
        self._dark = dark
        self._ds: Optional[OverlayDataset] = None

        ly = QVBoxLayout(self)
        ly.setContentsMargins(0, 0, 0, 0)
        ly.setSpacing(0)

        self._figure = Figure(figsize=(6, 4), dpi=100)
        self._canvas = FigureCanvas(self._figure)
        self._canvas.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        ly.addWidget(self._canvas, 1)
        self._render_empty()

    def _render_empty(self) -> None:
        self._figure.clear()
        ax = self._figure.add_subplot(111)
        bg = "#1e1e21" if self._dark else "#ffffff"
        self._figure.patch.set_facecolor(bg)
        ax.set_facecolor(bg)
        ax.text(
            0.5, 0.5, "No confusion matrix available",
            ha="center", va="center",
            color="#888" if self._dark else "#888",
            transform=ax.transAxes,
        )
        ax.set_xticks([]); ax.set_yticks([])
        self._canvas.draw()

    def update_dataset(self, ds: Optional[OverlayDataset]) -> None:
        self._ds = ds
        if ds is None or not ds.confusion or not ds.gt_clusters or not ds.pred_clusters:
            self._render_empty()
            return
        gt = ds.gt_clusters
        pr = ds.pred_clusters
        mat = np.zeros((len(gt), len(pr)), dtype=int)
        for (g, p), n in ds.confusion.items():
            if g in gt and p in pr:
                mat[gt.index(g), pr.index(p)] = n
        self._figure.clear()
        ax = self._figure.add_subplot(111)
        bg = "#1e1e21" if self._dark else "#ffffff"
        self._figure.patch.set_facecolor(bg)
        ax.set_facecolor(bg)
        im = ax.imshow(mat, cmap="Blues", aspect="auto")
        ax.set_xticks(range(len(pr)))
        ax.set_xticklabels(pr, rotation=30, ha="right",
                           color="#ddd" if self._dark else "#333", fontsize=9)
        ax.set_yticks(range(len(gt)))
        ax.set_yticklabels(gt,
                           color="#ddd" if self._dark else "#333", fontsize=9)
        ax.set_xlabel("Prediction", color="#888", fontsize=10)
        ax.set_ylabel("Ground Truth", color="#888", fontsize=10)
        for i in range(len(gt)):
            for j in range(len(pr)):
                v = mat[i, j]
                if v == 0:
                    continue
                color = "#fff" if v > mat.max() * 0.55 else "#1a1a1a"
                if self._dark:
                    color = "#fff" if v > mat.max() * 0.55 else "#ddd"
                ax.text(j, i, str(v), ha="center", va="center",
                        color=color, fontsize=8)
        for spine in ax.spines.values():
            spine.set_visible(False)
        self._figure.tight_layout(pad=1.5)
        self._canvas.draw()

    def set_dark(self, dark: bool) -> None:
        self._dark = dark
        self.update_dataset(self._ds)


# ====================================================================
#  Tab 4: Mismatched Points
# ====================================================================
class _MismatchedPointsTab(QWidget):
    HEADERS = ["Cell ID", "Ground Truth", "Prediction", "Error Type"]

    def __init__(self, dark: bool = False):
        super().__init__()
        self._dark = dark
        self._ds: Optional[OverlayDataset] = None

        ly = QVBoxLayout(self)
        ly.setContentsMargins(0, 0, 0, 0)
        ly.setSpacing(0)

        # Filter row
        toolbar = QHBoxLayout()
        toolbar.setContentsMargins(12, 8, 12, 8)
        toolbar.setSpacing(8)

        fl = QLabel("Filter:")
        fl.setStyleSheet("color: #888; font-size: 11px;")
        toolbar.addWidget(fl)

        self._filter_combo = QComboBox()
        self._filter_combo.addItem("All", "All")
        self._filter_combo.addItem("Misclassified", ErrorType.MISCLASSIFIED.value)
        self._filter_combo.addItem("New", ErrorType.NEW.value)
        self._filter_combo.addItem("Missing", ErrorType.MISSING.value)
        self._filter_combo.currentIndexChanged.connect(self._refresh_rows)
        self._filter_combo.setFixedWidth(160)
        self._filter_combo.setStyleSheet(self._combo_style())
        toolbar.addWidget(self._filter_combo)

        toolbar.addStretch()
        self._count_lbl = QLabel("0 mismatched")
        self._count_lbl.setStyleSheet("color: #888; font-size: 11px;")
        toolbar.addWidget(self._count_lbl)
        ly.addLayout(toolbar)

        # Table
        self._table = QTableWidget(0, len(self.HEADERS))
        self._table.setHorizontalHeaderLabels(self.HEADERS)
        self._table.verticalHeader().setVisible(False)
        self._table.setSelectionBehavior(
            QAbstractItemView.SelectionBehavior.SelectRows
        )
        self._table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._table.setAlternatingRowColors(True)
        self._table.setShowGrid(False)
        self._table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.Stretch
        )
        self._table.setStyleSheet(self._table_style())
        ly.addWidget(self._table, 1)

    def _combo_style(self) -> str:
        if self._dark:
            return """
                QComboBox { background: #232327; color: #f5f5f7; border: 1px solid #2a2a2e;
                            border-radius: 4px; padding: 4px 8px; font-size: 11px; }
                QComboBox::drop-down { border: none; }
            """
        return """
            QComboBox { background: #fafafa; color: #1a1a1a; border: 1px solid #ddd;
                        border-radius: 4px; padding: 4px 8px; font-size: 11px; }
            QComboBox::drop-down { border: none; }
        """

    def _table_style(self) -> str:
        if self._dark:
            return """
                QTableWidget { background: #1e1e21; alternate-background-color: #232327;
                               gridline-color: #2a2a2e; color: #f5f5f7;
                               font-size: 12px; border: none; }
                QHeaderView::section { background: #1a1a1d; color: #8a8a90;
                                       padding: 6px 8px; border: none;
                                       border-bottom: 1px solid #2a2a2e;
                                       font-weight: 600; font-size: 11px; }
                QTableWidget::item { padding: 6px 8px; }
                QTableWidget::item:selected { background: rgba(100,180,255,0.20); }
            """
        return """
            QTableWidget { background: #ffffff; alternate-background-color: #fafbfc;
                           gridline-color: #ececec; color: #1a1a1a;
                           font-size: 12px; border: none; }
            QHeaderView::section { background: #fafafa; color: #666;
                                   padding: 6px 8px; border: none;
                                   border-bottom: 1px solid #ececec;
                                   font-weight: 600; font-size: 11px; }
            QTableWidget::item { padding: 6px 8px; }
            QTableWidget::item:selected { background: #e3eefb; color: #1a6bc0; }
        """

    def update_dataset(self, ds: Optional[OverlayDataset]) -> None:
        self._ds = ds
        self._refresh_rows()

    def _refresh_rows(self) -> None:
        if self._ds is None:
            self._table.setRowCount(0)
            self._count_lbl.setText("0 mismatched")
            return
        sel = self._filter_combo.currentData()
        rows = []
        for c in self._ds.cells:
            if c.error_type == ErrorType.CORRECT:
                continue
            if sel != "All" and c.error_type.value != sel:
                continue
            rows.append(c)
        self._table.setRowCount(len(rows))
        for r, c in enumerate(rows):
            vals = [c.cell_id, c.ground_truth, c.prediction, c.error_type.value]
            for col_i, v in enumerate(vals):
                item = QTableWidgetItem(v)
                if col_i == 1:
                    item.setForeground(_cluster_color(c.ground_truth))
                if col_i == 3:
                    if c.error_type == ErrorType.MISCLASSIFIED:
                        item.setForeground(QColor("#e74c3c"))
                    elif c.error_type == ErrorType.NEW:
                        item.setForeground(QColor("#d48800"))
                    elif c.error_type == ErrorType.MISSING:
                        item.setForeground(QColor("#ff7a45"))
                self._table.setItem(r, col_i, item)
        self._count_lbl.setText(f"{len(rows):,} mismatched")

    def set_dark(self, dark: bool) -> None:
        self._dark = dark
        self._table.setStyleSheet(self._table_style())
        self._filter_combo.setStyleSheet(self._combo_style())


# ====================================================================
#  Tab 5: Cluster Details
# ====================================================================
class _ClusterDetailsTab(QWidget):
    def __init__(self, dark: bool = False):
        super().__init__()
        self._dark = dark
        self._ds: Optional[OverlayDataset] = None

        ly = QVBoxLayout(self)
        ly.setContentsMargins(16, 16, 16, 16)
        ly.setSpacing(10)

        self._header = QLabel("Select a cluster to inspect")
        self._header.setStyleSheet(
            "color: #1a1a1a; font-size: 16px; font-weight: 700;"
        )
        ly.addWidget(self._header)

        self._sub = QLabel(
            "Cluster Details provides per-cluster deep dive (marker genes, "
            "expression distributions, top spots). It is reserved for the "
            "Marker Genes module and shown here as a placeholder."
        )
        self._sub.setWordWrap(True)
        self._sub.setStyleSheet("color: #888; font-size: 12px;")
        ly.addWidget(self._sub)
        ly.addStretch()

    def update_dataset(self, ds: Optional[OverlayDataset]) -> None:
        self._ds = ds
        if ds is None:
            return

    def set_dark(self, dark: bool) -> None:
        self._dark = dark
        self._header.setStyleSheet(
            "color: #f5f5f7; font-size: 16px; font-weight: 700;"
            if dark else
            "color: #1a1a1a; font-size: 16px; font-weight: 700;"
        )


# ====================================================================
#  Data area container
# ====================================================================
class DataAreaWidget(QFrame):
    """Container that hosts the 5-tab data section beneath the visualization."""

    def __init__(self, dark: bool = False, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self._dark = dark

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        outer.setContentsMargins(0, 8, 0, 0)

        # Top row: Data Summary card (always visible at the top of data area)
        top_row = QHBoxLayout()
        top_row.setContentsMargins(0, 0, 0, 8)
        self._summary_card = _DataSummaryCard(dark)
        top_row.addWidget(self._summary_card)
        top_row.addStretch()

        # The summary card itself sits beside the tab widget:
        # build a row that contains [summary card] [tab widget]
        outer.addLayout(top_row)
        # Tabs
        self._tabs = QTabWidget()
        self._tabs.setStyleSheet(_TAB_DARK if dark else _TAB_LIGHT)

        self._cluster_tab = _ClusterSummaryTab(dark)
        self._confusion_tab = _ConfusionMatrixTab(dark)
        self._mismatch_tab = _MismatchedPointsTab(dark)
        self._details_tab = _ClusterDetailsTab(dark)

        self._tabs.addTab(self._cluster_tab, "Cluster Summary")
        self._tabs.addTab(self._confusion_tab, "Confusion Matrix")
        self._tabs.addTab(self._mismatch_tab, "Mismatched Points")
        self._tabs.addTab(self._details_tab, "Cluster Details")
        # The first tab is "Data Summary" (left card), default to Cluster Summary
        # (matches the ideal image default selection).
        outer.addWidget(self._tabs, 1)

    def update_dataset(self, ds: Optional[OverlayDataset]) -> None:
        self._summary_card.update_dataset(ds)
        self._cluster_tab.update_dataset(ds)
        self._confusion_tab.update_dataset(ds)
        self._mismatch_tab.update_dataset(ds)
        self._details_tab.update_dataset(ds)

    def set_dark(self, dark: bool) -> None:
        self._dark = dark
        self._tabs.setStyleSheet(_TAB_DARK if dark else _TAB_LIGHT)
        self._summary_card.set_dark(dark)
        self._cluster_tab.set_dark(dark)
        self._confusion_tab.set_dark(dark)
        self._mismatch_tab.set_dark(dark)
        self._details_tab.set_dark(dark)

    def show_mismatched_points(self) -> None:
        idx = self._tabs.indexOf(self._mismatch_tab)
        if idx >= 0:
            self._tabs.setCurrentIndex(idx)
