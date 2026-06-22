# coding: utf-8
"""Global data path manager.

单例式数据源，保存用户上传的主文件夹路径并扫描出：
- Ground_Truth / Results 子目录
- 所有 sample_id（section）
- train_log 目录及指标文件列表
- 校验状态

上传完成后通过 Qt signal 通知 Controller 重载数据。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from PySide6.QtCore import QObject, Signal

from utils.logger import logger


# -------------------------------------------------------------------
# Train log metric file names
# -------------------------------------------------------------------
TRAIN_LOG_METRICS = ["loss", "ari", "nmi", "hs", "cs"]


# -------------------------------------------------------------------
# Expected folder names (case-insensitive match helpers) -----------
# -------------------------------------------------------------------
_GT_NAMES = {"ground_truth", "groundtruth", "gt", "ground-truth"}
_RESULT_NAMES = {"results", "result", "predictions", "prediction", "pred", "preds"}
_TRAIN_LOG_NAMES = {"train_log", "trainlog", "train-log", "training_log", "traininglog", "logs", "log"}


def _norm(s: str) -> str:
    """Normalise string for case-insensitive / punctuation-robust matching."""
    return s.lower().replace("-", "_").replace(" ", "_")


# -------------------------------------------------------------------
# Data structure
# -------------------------------------------------------------------
@dataclass
class DataStructure:
    """Scan result of the user-selected root folder."""

    root: Path
    gt_root: Optional[Path] = None          # main_file / Ground_Truth
    results_root: Optional[Path] = None     # main_file / Results
    train_log_dir: Optional[Path] = None    # main_file / train_log
    section_ids: list[str] = field(default_factory=list)
    train_log_metrics: list[str] = field(default_factory=list)  # available metrics
    warnings: list[str] = field(default_factory=list)
    is_valid: bool = False                  # passes core validation

    @property
    def has_gt(self) -> bool:
        return self.gt_root is not None

    @property
    def has_results(self) -> bool:
        return self.results_root is not None

    @property
    def has_train_log(self) -> bool:
        return self.train_log_dir is not None


# -------------------------------------------------------------------
# Manager
# -------------------------------------------------------------------
class DataPathManager(QObject):
    """Application-wide singleton holder for uploaded data path.

    Signals
    -------
    path_changed: emitted when root_path changes (None = cleared).
    structure_changed: emitted when a new DataStructure is ready.

    Usage
    -----
        mgr = DataPathManager()
        mgr.path_changed.connect(controller.reload)
        mgr.set_root(Path(r"C:\\my_data"))   # scans & emits
        mgr.has_path()                        # bool
    """

    path_changed = Signal(object)          # Optional[Path]
    structure_changed = Signal(object)     # Optional[DataStructure]

    def __init__(self) -> None:
        super().__init__()
        self._root: Optional[Path] = None
        self._structure: Optional[DataStructure] = None

    # ---- queries ----
    def has_path(self) -> bool:
        return self._root is not None

    def has_valid_data(self) -> bool:
        return self._structure is not None and self._structure.is_valid

    def root_path(self) -> Optional[Path]:
        return self._root

    def structure(self) -> Optional[DataStructure]:
        return self._structure

    def gt_root(self) -> Optional[Path]:
        return self._structure.gt_root if self._structure else None

    def results_root(self) -> Optional[Path]:
        return self._structure.results_root if self._structure else None

    def section_ids(self) -> list[str]:
        return list(self._structure.section_ids) if self._structure else []

    def train_log_metrics(self) -> list[str]:
        return list(self._structure.train_log_metrics) if self._structure else []

    # ---- setters ----
    def set_root(self, root: Optional[Path]) -> DataStructure:
        """Assign a new root path, scan it, and emit signals.

        Returns the resulting DataStructure for immediate inspection.
        """
        if root is None:
            self._root = None
            self._structure = None
            self.path_changed.emit(None)
            self.structure_changed.emit(None)
            logger.info("DataPathManager: cleared")
            return None

        root = Path(root)
        self._root = root
        self._structure = _scan_structure(root)
        logger.info(
            "DataPathManager: root=%s  gt=%s  results=%s  sections=%s  valid=%s",
            root,
            self._structure.gt_root,
            self._structure.results_root,
            self._structure.section_ids,
            self._structure.is_valid,
        )
        self.path_changed.emit(root)
        self.structure_changed.emit(self._structure)
        return self._structure

    def clear(self) -> None:
        self.set_root(None)


# -------------------------------------------------------------------
# Scanning
# -------------------------------------------------------------------
def _scan_structure(root: Path) -> DataStructure:
    """Walk the root folder and build a DataStructure.

    Expected layout
    ---------------
    root/
      Ground_Truth/          (or gt / groundtruth)
        <sample_id>/
          metadata.tsv
          spatial/
            tissue_positions_list.csv
            tissue_hires_image.png
            tissue_lowres_image.png
      Results/               (or result / predictions ...)
        <sample_id>/
          metadata.tsv
          spatial/ ...
      train_log/             (optional)
        loss.csv
        ari.csv
        nmi.csv
        hs.csv
        cs.csv

    Single-folder fallback
    ----------------------
    If neither Ground_Truth nor Results subfolder is detected, each direct
    subfolder of `root` is treated as a section and used for BOTH roles.
    """
    warnings: list[str] = []
    gt_root: Optional[Path] = None
    results_root: Optional[Path] = None
    train_log_dir: Optional[Path] = None
    gt_sids: list[str] = []
    res_sids: list[str] = []
    train_metrics: list[str] = []

    if not root.exists() or not root.is_dir():
        return DataStructure(
            root=root,
            warnings=[f"路径不存在或不是文件夹: {root}"],
        )

    direct_dirs = [p for p in root.iterdir() if p.is_dir()]

    # Locate the three special subfolders
    for sub in direct_dirs:
        n = _norm(sub.name)
        if gt_root is None and n in _GT_NAMES:
            gt_root = sub
        elif results_root is None and n in _RESULT_NAMES:
            results_root = sub
        elif train_log_dir is None and n in _TRAIN_LOG_NAMES:
            train_log_dir = sub

    # Single-section mode
    if gt_root is None and results_root is None:
        if direct_dirs:
            # everything else is a section
            sids = sorted([p.name for p in direct_dirs])
            gt_sids = sids
            res_sids = sids
            gt_root = root
            results_root = root
            if len(sids) > 1:
                warnings.append(
                    "未找到 Ground_Truth / Results 子文件夹，"
                    "根目录下所有直接子文件夹将被视为 section。"
                    "建议将数据组织为 Ground_Truth/<sample>/ 和 Results/<sample>/。"
                )
        else:
            warnings.append("所选文件夹为空，请确认路径。")
    else:
        # Standard mode: gather section ids from each side
        if gt_root:
            gt_sids = sorted([p.name for p in gt_root.iterdir() if p.is_dir()])
        if results_root:
            res_sids = sorted([p.name for p in results_root.iterdir() if p.is_dir()])

        if not gt_root:
            warnings.append("未找到 Ground_Truth 子文件夹。")
        if not results_root:
            warnings.append("未找到 Results 子文件夹。")

    # Scan train_log
    if train_log_dir:
        for metric in TRAIN_LOG_METRICS:
            cand = train_log_dir / f"{metric}.csv"
            if cand.is_file():
                train_metrics.append(metric)
        if not train_metrics:
            warnings.append(f"train_log 目录下未找到任何 {TRAIN_LOG_METRICS} 系列 .csv 文件。")

    # Core validation: require at least one GT or Results root with metadata
    is_valid = False
    if gt_root or results_root:
        check_root = gt_root or results_root
        valid_sids = [
            s for s in (gt_sids or res_sids)
            if (check_root / s / "metadata.tsv").exists()
        ]
        if valid_sids:
            is_valid = True
        else:
            warnings.append("未找到任何包含 metadata.tsv 的 sample 子文件夹。")

    section_ids = sorted(set(gt_sids) & set(res_sids)) if (gt_sids and res_sids) else sorted(set(gt_sids) | set(res_sids))

    return DataStructure(
        root=root,
        gt_root=gt_root,
        results_root=results_root,
        train_log_dir=train_log_dir,
        section_ids=section_ids,
        train_log_metrics=train_metrics,
        warnings=warnings,
        is_valid=is_valid,
    )
