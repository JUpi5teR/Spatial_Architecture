# coding: utf-8
"""Notebook workspace - scoped container for all analysis modules."""
from __future__ import annotations

from pathlib import Path
from typing import Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QComboBox, QFrame, QHBoxLayout, QLabel,
    QPushButton, QStackedWidget, QStatusBar,
    QVBoxLayout, QWidget,
)

from backend.models import DatasetManager, NotebookManager
from model.data_path import DataPathManager
from model.image_manager import scan_images
from model.overlay_data import load_all_overlay_datasets
from utils.logger import logger

from view.sidebar import Sidebar
from view.upload_view import UploadViewWidget
from view.comparison_view import ComparisonViewWidget
from view.clustering_page import ClusteringPage
from view.statistics_view import StatisticsViewWidget
from view.plots_view import PlotsViewWidget
from view.heatmap_view import HeatmapViewWidget
from view.datasets_view import DatasetsViewWidget

SECTION_IDS = [
    "151507", "151508", "151509", "151510",
    "151669", "151670", "151671", "151672",
    "151673", "151674", "151675", "151676",
]

def _check_results_has_csv(res_root):
    if not res_root.exists():
        return False
    for sid in SECTION_IDS:
        sec_dir = res_root / sid
        if sec_dir.is_dir():
            if list(sec_dir.glob("*.csv")) or list(sec_dir.glob("*.tsv")):
                return True
    return False


_BACK_BTN = '''
QPushButton {
    background: transparent; color: #1a6bc0; border: 1px solid #1a6bc0;
    border-radius: 6px; font-size: 12px; padding: 6px 14px; font-weight: 600;
}
QPushButton:hover { background: #e3eefb; }
'''

_TOPBAR = 'background: #fafafa; border-bottom: 1px solid #ececec;'
_NOTEBOOK_NAME = 'font-size: 16px; font-weight: 700; color: #1a1a1a;'
_DATASET_LABEL = 'font-size: 12px; color: #888;'
_EMPTY_STATE = 'font-size: 15px; color: #aaa; padding: 40px;'

class NotebookWorkspace(QWidget):
    back_to_homepage = Signal()
    notebook_updated = Signal()
    theme_toggled = Signal(bool)
    def __init__(self, notebook, path_mgr, parent=None, dark=False):
        super().__init__(parent)
        self._notebook = notebook
        self._path_mgr = path_mgr
        self._ds_mgr = DatasetManager()
        self._nb_mgr = NotebookManager()
        self._current_dataset = None
        self._dark = dark
        self._collection = None
        self._overlay_datasets = []
        self._build_ui()
        self._refresh_datasets()
        self._datasets_view.refresh()
    @property
    def notebook(self):
        return self._notebook
    @property
    def current_dataset(self):
        return self._current_dataset
    def set_controller(self, controller):
        pass

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        # ---- Top bar ----
        top = QFrame()
        top.setStyleSheet(_TOPBAR)
        top.setFixedHeight(52)
        top_ly = QHBoxLayout(top)
        top_ly.setContentsMargins(12, 8, 16, 8)
        back_btn = QPushButton('\u2190  Homepage')
        back_btn.setStyleSheet(_BACK_BTN)
        back_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        back_btn.clicked.connect(self.back_to_homepage.emit)
        top_ly.addWidget(back_btn)
        self._title_label = QLabel(self._notebook.name)
        self._title_label.setStyleSheet(_NOTEBOOK_NAME)
        top_ly.addWidget(self._title_label)
        top_ly.addStretch()
        ds_label = QLabel('Dataset:')
        ds_label.setStyleSheet(_DATASET_LABEL)
        top_ly.addWidget(ds_label)
        self._dataset_combo = QComboBox()
        self._dataset_combo.setMinimumWidth(220)
        self._dataset_combo.setStyleSheet(
            'QComboBox {'
                'background: #ffffff; color: #1a1a1a;'
                'border: 1px solid #e0e0e0; border-radius: 6px;'
                'padding: 4px 10px; font-size: 12px; min-height: 22px;'
            '}'
            'QComboBox:hover { border-color: #b9d2f1; }'
        )
        self._dataset_combo.currentIndexChanged.connect(self._on_dataset_changed)
        top_ly.addWidget(self._dataset_combo)
        root.addWidget(top)
        # ---- Body ----
        body = QHBoxLayout()
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(0)
        self._sidebar = Sidebar(
            active_key='upload',
            on_theme_toggle=self._toggle_theme,
            parent=self,
        )
        self._sidebar.module_selected.connect(self._on_module_selected)
        body.addWidget(self._sidebar)
        self._stack = QStackedWidget()
        self._stack.setStyleSheet('background: #ffffff;')
        self._upload_view = UploadViewWidget(self._path_mgr)
        self._upload_view.folder_registered.connect(self._on_folder_registered)
        self._clustering_page = ClusteringPage()
        self._comparison_view = self._clustering_page.comparison_view
        self._statistics_view = StatisticsViewWidget(self._path_mgr)
        self._plots_view = PlotsViewWidget(self._path_mgr)
        self._heatmap_view = HeatmapViewWidget(self._path_mgr)
        # REAL datasets page (replaces placeholder)
        self._datasets_view = DatasetsViewWidget(self._ds_mgr, self._notebook)
        self._datasets_view.dataset_activated.connect(self._on_dataset_loaded)
        self._empty_widget = self._make_empty('No dataset loaded.\nPlease upload data first.')
        self._page_placeholder = self._make_placeholder('Coming soon')
        # Stack: 0=upload  1=clustering  2=statistics  3=plots
        #        4=heatmaps  5=empty  6=overview  7=datasets
        #        8=preprocessing  9=marker_genes  10=dimensionality
        #        11=trajectory  12=comparison
        self._stack.addWidget(self._upload_view)         # 0
        self._stack.addWidget(self._clustering_page)       # 1
        self._stack.addWidget(self._statistics_view)     # 2
        self._stack.addWidget(self._plots_view)          # 3
        self._stack.addWidget(self._heatmap_view)        # 4
        self._stack.addWidget(self._empty_widget)        # 5
        self._stack.addWidget(self._page_placeholder)    # 6
        self._stack.addWidget(self._datasets_view)       # 7  DATASETS
        self._stack.addWidget(self._page_placeholder)    # 8
        self._stack.addWidget(self._page_placeholder)    # 9
        self._stack.addWidget(self._page_placeholder)    # 10
        self._stack.addWidget(self._page_placeholder)    # 11
        self._stack.addWidget(self._page_placeholder)    # 12
        self._module_map = {
            'upload': 0, 'clustering': 1, 'statistics': 2,
            'plots': 3, 'heatmaps': 4,
            'overview': 7, 'datasets': 7, 'preprocessing': 8,
            'marker_genes': 9, 'dimensionality': 10,
            'trajectory': 11, 'comparison': 12,
        }
        body.addWidget(self._stack)
        root.addLayout(body)
        self._status = QStatusBar()
        self._status.setStyleSheet(
            'QStatusBar { background: #fafafa; border-top: 1px solid #ececec;'
            ' font-size: 11px; color: #888; }'
        )
        self._status.setFixedHeight(26)
        root.addWidget(self._status)
        self._stack.setCurrentIndex(0)
    def _make_empty(self, text):
        w = QWidget()
        ly = QVBoxLayout(w)
        ly.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lbl = QLabel(text)
        lbl.setStyleSheet(_EMPTY_STATE)
        lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        ly.addWidget(lbl)
        return w
    def _make_placeholder(self, text):
        w = QWidget()
        ly = QVBoxLayout(w)
        ly.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lbl = QLabel(text)
        lbl.setStyleSheet('font-size: 18px; color: #bbb; padding: 40px;')
        lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        ly.addWidget(lbl)
        return w
    # ----------------------------------------------------------------
    # Sidebar navigation
    # ----------------------------------------------------------------
    def _on_module_selected(self, key):
        if key == 'homepage':
            self.back_to_homepage.emit()
            return
        # Datasets page is always accessible (no data required)
        if key in ('upload', 'datasets'):
            idx = self._module_map.get(key, 0)
            if key == 'datasets':
                logger.info('_on_module_selected: datasets clicked, refreshing')
                self._datasets_view.refresh()
                logger.info('_on_module_selected: table rows=%s', self._datasets_view._table.rowCount())
            self._stack.setCurrentIndex(idx)
            return
        # Analysis modules need data
        if key in ('clustering', 'statistics', 'plots', 'heatmaps',
                    'preprocessing', 'comparison',
                    'overview', 'marker_genes', 'dimensionality', 'trajectory'):
            if self._current_dataset is None:
                self.show_status_message('No dataset loaded. Please upload data first.')
                self._stack.setCurrentWidget(self._empty_widget)
                return
        idx = self._module_map.get(key, 0)
        if idx < self._stack.count():
            self._stack.setCurrentIndex(idx)

        # Refresh views that depend on DataPathManager data
        if key == 'plots':
            self._plots_view.load_data()
        elif key == 'statistics':
            self._statistics_view.load_data()
        elif key == 'heatmaps':
            self._heatmap_view.set_overlay_datasets(self._overlay_datasets)
            self._heatmap_view.set_ari_map(self._ari_map)
            self._heatmap_view.load_data()

    # ----------------------------------------------------------------
    # Dataset management
    # ----------------------------------------------------------------
    def _refresh_datasets(self):
        self._dataset_combo.blockSignals(True)
        self._dataset_combo.clear()
        datasets = self._ds_mgr.list_by_notebook(self._notebook.id)
        if datasets:
            self._dataset_combo.addItem('-- Select dataset --', None)
            for ds in datasets:
                ts = ds.upload_time[:16] if ds.upload_time else ''
                self._dataset_combo.addItem(ds.name + '  (' + ts + ')', ds.id)
        else:
            self._dataset_combo.addItem('-- No datasets yet --', None)
        self._dataset_combo.blockSignals(False)
    def _on_dataset_changed(self, idx):
        if idx < 0:
            return
        try:
            ds_id = self._dataset_combo.itemData(idx)
            if ds_id is None:
                self._current_dataset = None
                return
            self._select_dataset(ds_id)
        except Exception as e:
            logger.error('_on_dataset_changed failed: %s', e, exc_info=True)

    def _on_dataset_loaded(self, dataset_id):
        self._select_dataset(dataset_id)
        for i in range(self._dataset_combo.count()):
            if self._dataset_combo.itemData(i) == dataset_id:
                self._dataset_combo.blockSignals(True)
                self._dataset_combo.setCurrentIndex(i)
                self._dataset_combo.blockSignals(False)
                break

    def _select_dataset(self, dataset_id):
        try:
            ds = self._ds_mgr.get_by_id(dataset_id)
            if ds is None:
                return
            self._current_dataset = ds
            self._load_data(ds)
            self.show_status_message('Loaded: ' + ds.name)
        except Exception as e:
            logger.error('_select_dataset failed: %s', e, exc_info=True)
            self.show_status_message('Failed to load dataset: ' + str(e))
    # ----------------------------------------------------------------
    # Upload handler
    # ----------------------------------------------------------------
    def _on_folder_registered(self, root):
        if root is None:
                return
        try:
            structure = self._path_mgr.structure()
            if structure is None:
                return
            import datetime
            ts = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
            ds_name = 'upload_' + ts
            ds = self._ds_mgr.create(
                notebook_id=self._notebook.id,
                name=ds_name,
                file_path=str(root),
                ground_truth_path=str(structure.gt_root) if structure.gt_root else None,
                results_path=str(structure.results_root) if structure.results_root else None,
                train_log_path=str(structure.train_log_dir) if structure.train_log_dir else None,
            )
            self._refresh_datasets()
            self._datasets_view.refresh()
            for i in range(self._dataset_combo.count()):
                if self._dataset_combo.itemData(i) == ds.id:
                    self._dataset_combo.setCurrentIndex(i)
                    break
            self._nb_mgr.touch(self._notebook.id)
            self.notebook_updated.emit()
        except Exception as e:
            logger.error('Upload failed: %s', e, exc_info=True)
            self.show_status_message('Upload error: ' + str(e))

    def _load_data(self, ds):
        self.show_status_message('Loading data...')
        data_root = Path(ds.file_path)
        gt_dir = Path(ds.ground_truth_path) if ds.ground_truth_path else data_root
        res_dir = Path(ds.results_path) if ds.results_path else data_root
        section_ids = self._scan_ids(data_root, gt_dir, res_dir)
        # Sync DataPathManager so analysis pages (plots, statistics, heatmaps)
        # can access train_log and other data via the path manager.
        self._path_mgr.set_root(data_root)
        try:
            # Try standard scan first
            self._collection = scan_images(gt_dir, res_dir, section_ids)
            # If no pairs found, try flexible scanning
            if not self._collection or not self._collection.pairs:
                logger.info('Standard scan found nothing, trying flexible scan...')
                self._collection = self._flexible_scan(gt_dir, res_dir, section_ids)
            n = len(self._collection.pairs) if self._collection else 0
            logger.info('Final image count: %d', n)
            # Always push GT and Results roots into the clustering page so the
            # 3D view can render the predictions too, even if the side-by-side
            # PNG scan came up empty.
            if self._collection is None:
                self._collection = self._flexible_scan(gt_dir, res_dir, section_ids)
            self._clustering_page.load_data(
                self._collection,
                gt_root=str(gt_dir),
                results_root=str(res_dir),
                section_ids=section_ids,
            )
            # Load overlay for 3D / cell-level display (CSV-driven).
            try:
                has_pred = _check_results_has_csv(res_dir)
                gt_col = 'layer_guess_reordered'
                pred_col = 'GraphBased' if has_pred else '__no_results__'
                self._overlay_datasets = load_all_overlay_datasets(
                    gt_dir, section_ids,
                    gt_column=gt_col, pred_column=pred_col,
                    result_root=res_dir if has_pred else None,
                )
            except Exception:
                self._overlay_datasets = []
                logger.debug('Overlay loading skipped (no CSV metadata)')
            self._ari_map = self._load_ari_map()
            self.show_status_message(
                'Ready - %d image pairs, %d sections with overlay data'
                % (n, len(self._overlay_datasets))
            )
        except Exception as exc:
            logger.warning('Data load error: %s', exc)
            self.show_status_message('Data load error: ' + str(exc))
            self._clustering_page.show_no_data()
    def _flexible_scan(self, gt_dir, res_dir, section_ids):
        from model.image_manager import ImagePair, ImageCollection
        pairs = []
        has_pred = False
        for sid in section_ids:
            gt_path = self._find_image(gt_dir / sid)
            pred_path = self._find_image(res_dir / sid)
            if gt_path:
                pairs.append(ImagePair(
                    section_id=sid,
                    gt_path=gt_path,
                    pred_path=pred_path,
                    filename=sid,
                    pred_missing=not bool(pred_path),
                ))
                if pred_path:
                    has_pred = True
        return ImageCollection(
            pairs=pairs,
            gt_dir_status='loaded' if pairs else 'missing',
            pred_dir_status='loaded' if has_pred else 'missing',
            has_pred=has_pred,
            fallback_mode=not has_pred,
        )
    def _load_ari_map(self):
        ari_map = {}
        structure = self._path_mgr.structure()
        if structure is None or not structure.has_train_log:
            return ari_map
        ari_path = structure.train_log_dir / "ari.csv"
        if not ari_path.is_file():
            return ari_map
        try:
            import pandas as pd
            df = pd.read_csv(ari_path)
            if "sample" in df.columns and "ari" in df.columns:
                last_epoch = df["epoch"].max()
                last_rows = df[df["epoch"] == last_epoch]
                for _, row in last_rows.iterrows():
                    ari_map[str(row["sample"]).strip()] = float(row["ari"])
        except Exception as exc:
            logger.warning("Failed to load ARI map: %s", exc)
        return ari_map

    @staticmethod
    def _find_image(folder):
        if not folder.exists():
            return None
        for ext in ('*.png', '*.jpg', '*.jpeg', '*.tif', '*.tiff'):
            for p in sorted(folder.rglob(ext)):
                return p
        return None
    @staticmethod
    def _scan_ids(data_root, gt_dir, res_dir):
        ids = set()
        for d in (gt_dir, res_dir):
            if d.exists():
                for p in d.iterdir():
                    if p.is_dir():
                        ids.add(p.name)
        return sorted(ids) if ids else list(SECTION_IDS)
    # ----------------------------------------------------------------
    # Public
    # ----------------------------------------------------------------
    def show_status_message(self, msg, timeout=5000):
        self._status.showMessage(msg, timeout)
    def update_notebook_name(self, new_name):
        self._notebook.name = new_name
        self._title_label.setText(new_name)
    def _toggle_theme(self):
        from view.main_window import apply_theme
        self._dark = not self._dark
        self._sidebar.set_dark(self._dark)
        apply_theme(self._dark)
        # Propagate theme to the active views.
        if self._clustering_page is not None:
            try:
                self._clustering_page.set_dark(self._dark)
            except Exception:
                pass
        for view in (
            self._statistics_view,
            self._plots_view,
            self._heatmap_view,
        ):
            if view is not None and hasattr(view, "set_dark"):
                try:
                    view.set_dark(self._dark)
                except Exception:
                    pass
        self.theme_toggled.emit(self._dark)
