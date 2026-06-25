# coding: utf-8
"""Dashboard data aggregator.

Loads training metrics from `train_log_path` CSVs across datasets and
produces aggregated statistics that the overview dashboard can render.

The service supports two scopes:
    - Global (notebook_id=None): aggregate across every active dataset
      in the database. Used by the homepage-level dashboard.
    - Notebook-scoped (notebook_id=N): only the datasets belonging to
      that notebook. Used by the per-notebook Overview dashboard.

Privacy contract:
    Only summary statistics (mean, variance, min, max, std, epoch count,
    best epoch, best value) are exposed to the UI layer. Raw per-epoch
    values are kept inside this module and never returned.
"""
from __future__ import annotations

import sys as _sys
from pathlib import Path as _Path
# Make ``utils`` and ``front.model.train_log_stats`` resolvable when
# this module is imported via ``front.model.dashboard_data`` (mirrors
# the front-path setup used in train_log_stats.py and
# overview_dashboard.py).
_front = _Path(__file__).resolve().parent.parent
if str(_front) not in _sys.path:
    _sys.path.insert(0, str(_front))
del _sys, _Path

import csv
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Sequence

from backend.models import DatasetManager, NotebookManager
from utils.logger import logger

from front.model.train_log_stats import (
    HIGHER_IS_BETTER as _TL_HIGHER_IS_BETTER,
    ImageStat as _ImageStat,
    MetricStat as _MetricStat,
    compute_dataset_stats as _compute_dataset_stats,
    ensure_dataset_stats as _ensure_dataset_stats,
    load_dataset_stats as _load_dataset_stats,
    aggregate_epoch_means as _aggregate_epoch_means,
    compute_per_sample_best as _compute_per_sample_best,
    read_metric_csv as _read_metric_csv_v2,
    save_dataset_stats as _save_dataset_stats,
)

# Same metric set used by the plots module. Order matters - it drives
# the default order in metric selectors / overview cards.
METRICS: Sequence[str] = ("ari", "nmi", "hs", "cs", "loss")


# ---------------------------------------------------------------------------
# Data classes (return shapes)
# ---------------------------------------------------------------------------
@dataclass
class DatasetSeries:
    """Per-dataset aggregated metrics for a single metric column."""

    name: str                   # dataset name shown to user
    sample_id: str              # tissue section id (e.g. "151507")
    notebook_id: int
    final_value: float          # value at the last epoch seen
    mean: float                 # mean across all epochs for this dataset
    variance: float             # always 0 (one max-seed representative value per image)
    min_value: float
    max_value: float
    epochs_seen: int
    final_epoch: int = 0        # last epoch recorded for this sample
    final_epoch_mean: float = 0.0  # cross-seed mean at final epoch
    final_epoch_variance: float = 0.0  # cross-seed variance at final epoch

    def as_display(self) -> Dict[str, float]:
        """Return only the fields safe to render in the UI."""
        return {
            "name": self.name,
            "sample_id": self.sample_id,
            "final": self.final_value,
            "mean": self.mean,
            "variance": self.variance,
            "min": self.min_value,
            "max": self.max_value,
            "epochs": self.epochs_seen,
            "final_epoch": self.final_epoch,
            "final_epoch_mean": self.final_epoch_mean,
            "final_epoch_variance": self.final_epoch_variance,
        }


@dataclass
class DatasetGroupSummary:
    """Per-dataset-name aggregated metrics for a single metric column."""

    name: str
    combined_mean: float
    combined_variance: float
    sample_count: int
    epochs_total: int


@dataclass
class MetricSummary:
    """Cross-dataset summary for one metric column."""

    metric: str
    dataset_count: int
    grand_mean: float           # mean of per-dataset final values
    grand_variance: float       # variance of per-dataset final values
    best_sample_id: str
    best_value: float
    worst_sample_id: str
    worst_value: float
    series: List[DatasetSeries] = field(default_factory=list)
    dataset_groups: Dict[str, DatasetGroupSummary] = field(default_factory=dict)

    # ---- Best / worst aggregated at the dataset-name level ----
    # Populated by the data service from `dataset_groups`. Surfaced by
    # KPI and Metric Overview cards so they show the strongest dataset's
    # pooled mean rather than the mean across every sample in every
    # dataset.
    best_dataset_name: str = ""
    best_dataset_value: float = 0.0
    worst_dataset_name: str = ""
    worst_dataset_value: float = 0.0

    @property
    def best_sample_mean(self) -> Optional[float]:
        """Mean-across-epochs for the best sample, used by KPI / overview
        cards so they surface the best dataset's parameter mean instead
        of the grand mean across all datasets."""
        if not self.best_sample_id:
            return None
        for row in self.series:
            if row.sample_id == self.best_sample_id:
                return row.mean
        return None

    @property
    def best_sample_dataset(self) -> str:
        """Name of the dataset that contains ``best_sample_id``. Empty
        when the best sample cannot be located. The overview UI joins
        this with the sample id to surface "which dataset's which
        sample" for the metric's top performer."""
        if not self.best_sample_id:
            return ""
        for row in self.series:
            if row.sample_id == self.best_sample_id:
                return row.name
        return ""

    @property
    def worst_sample_dataset(self) -> str:
        """Same as :pyattr:`best_sample_dataset` but for
        ``worst_sample_id``."""
        if not self.worst_sample_id:
            return ""
        for row in self.series:
            if row.sample_id == self.worst_sample_id:
                return row.name
        return ""

    @property
    def best_dataset_mean(self) -> Optional[float]:
        """Combined-mean across all data within the best-performing
        dataset (grouped by dataset.name). Mirrors what the top
        per-dataset bar chart shows for the strongest bar."""
        if not self.best_dataset_name:
            return None
        return self.best_dataset_value

    def as_display(self) -> Dict[str, object]:
        return {
            "metric": self.metric,
            "dataset_count": self.dataset_count,
            "grand_mean": self.grand_mean,
            "grand_variance": self.grand_variance,
            "best_sample_id": self.best_sample_id,
            "best_value": self.best_value,
            "worst_sample_id": self.worst_sample_id,
            "worst_value": self.worst_value,
            "series": [s.as_display() for s in self.series],
            "best_dataset_name": self.best_dataset_name,
            "best_dataset_value": self.best_dataset_value,
            "worst_dataset_name": self.worst_dataset_name,
            "worst_dataset_value": self.worst_dataset_value,
        }


@dataclass
class DashboardSnapshot:
    """Top-level snapshot used by the overview dashboard."""

    notebook_count: int
    dataset_count: int
    metrics_with_data: int
    scope_notebook_id: Optional[int]
    metrics: Dict[str, MetricSummary] = field(default_factory=dict)
    train_curves: Dict[str, List["CurvePoint"]] = field(default_factory=dict)

    def kpi(self) -> Dict[str, str]:
        """High-level KPI strings rendered in the dashboard header row."""
        return {
            "datasets": str(self.dataset_count),
            "metrics": f"{self.metrics_with_data}/{len(METRICS)}",
            "ari_mean": _fmt(self._safe_mean("ari"), 4),
            "loss_mean": _fmt(self._safe_mean("loss"), 4),
        }

    def _safe_mean(self, metric: str) -> Optional[float]:
        s = self.metrics.get(metric)
        return s.grand_mean if s is not None else None


@dataclass
class CurvePoint:
    """One point on a downsampled training curve (epoch, mean_across_samples)."""

    epoch: int
    value: float


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _fmt(value: Optional[float], digits: int) -> str:
    if value is None:
        return "-"
    return f"{value:.{digits}f}"


def _variance(values: Sequence[float]) -> float:
    """Population variance (divisor n). Avoids leaking sample std semantics."""
    n = len(values)
    if n == 0:
        return 0.0
    mean = sum(values) / n
    return sum((v - mean) ** 2 for v in values) / n


def _safe_float(s: str) -> Optional[float]:
    try:
        return float(s)
    except (TypeError, ValueError):
        return None


def _is_higher_better(metric: str) -> bool:
    return metric in {"ari", "nmi", "hs", "cs"}


# ---------------------------------------------------------------------------
# CSV reader
# ---------------------------------------------------------------------------
def _read_metric_csv(csv_path: Path) -> Dict[str, List[float]]:
    """Return {sample_id: [value_per_epoch, ...]} from a train_log CSV.
    Handles both long format (epoch, sample, value) and wide format
    (epoch, sample1, sample2, ...) with column name variations.
    """
    out: Dict[str, List[float]] = {}
    try:
        with open(csv_path, "r", encoding="utf-8", newline="") as fh:
            reader = csv.reader(fh)
            header = [h.strip().lower() for h in next(reader, [])]
            if not header or len(header) < 2:
                return out

            # Detect format: long format has a "sample" column; wide format doesn"t
            is_long = "sample" in header
            if is_long and len(header) >= 3:
                sample_idx = header.index("sample")
                # For long format (epoch, sample [, seed], metric),
                # use the LAST column as the metric value to skip extra columns like "seed"
                value_idx = len(header) - 1
                if value_idx <= sample_idx:
                    return out
                for row in reader:
                    if len(row) < 3:
                        continue
                    sample = row[sample_idx].strip()
                    val = _safe_float(row[value_idx])
                    if val is None or not sample:
                        continue
                    out.setdefault(sample, []).append(val)
            else:
                # Wide format: all non-epoch columns are sample IDs
                sample_indices = [(i, h) for i, h in enumerate(header)
                                  if h != "epoch" and h.strip()]
                for row in reader:
                    if len(row) < len(header):
                        continue
                    for idx, sample in sample_indices:
                        val = _safe_float(row[idx])
                        if val is None or not sample:
                            continue
                        out.setdefault(sample, []).append(val)
    except OSError as exc:
        logger.warning("Cannot read train log csv %s: %s", csv_path, exc)
    return out


def _downsample_curve(
    per_sample_rows: Dict[str, List[tuple]],
    max_points: int = 80,
) -> List[CurvePoint]:
    """Build a downsampled aggregate curve for the overview thumbnail.

    Uses ``aggregate_epoch_means`` to collapse seeds into per-epoch
    means, then averages across samples, and finally downsamples to
    at most ``max_points``. Only aggregate trends are exposed (no
    per-sample trajectories) for privacy.
    """
    if not per_sample_rows:
        return []
    epoch_means = _aggregate_epoch_means(per_sample_rows)
    # Collect all per-epoch per-sample means into epoch-aligned lists
    all_epochs = sorted(set(
        e for sample_data in epoch_means.values() for e in sample_data
    ))
    if not all_epochs:
        return []
    means: List[float] = []
    for epoch in all_epochs:
        vals = [
            sample_data[epoch]
            for sample_data in epoch_means.values()
            if epoch in sample_data
        ]
        if vals:
            means.append(sum(vals) / len(vals))
    if len(means) <= max_points:
        return [CurvePoint(epoch=i + 1, value=v) for i, v in enumerate(means)]
    bucket_size = max(1, len(means) // max_points)
    pts: List[CurvePoint] = []
    for start in range(0, len(means), bucket_size):
        chunk = means[start : start + bucket_size]
        if not chunk:
            continue
        pts.append(CurvePoint(epoch=start + 1, value=sum(chunk) / len(chunk)))
    return pts


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------
class DashboardDataService:
    """Builds DashboardSnapshot objects from the database + train_log files."""

    CACHE_VERSION = 2

    def __init__(self) -> None:
        self._ds_mgr = DatasetManager()
        self._nb_mgr = NotebookManager()
        self._cache: Optional[DashboardSnapshot] = None
        self._cache_signature: Optional[tuple] = None

    # ----- public -----
    def build_snapshot(
        self,
        notebook_id: Optional[int] = None,
        use_cache: bool = True,
    ) -> DashboardSnapshot:
        """Build a snapshot.

        notebook_id: if given, only include datasets belonging to that
            notebook. Otherwise aggregate across every active dataset.
        """
        ds_filter_fn = (
            (lambda d: d.notebook_id == notebook_id) if notebook_id is not None
            else (lambda d: True)
        )
        datasets_all = self._ds_mgr.list_all_active()
        datasets = [d for d in datasets_all if ds_filter_fn(d)]
        notebooks = self._nb_mgr.list_active()

        # Pre-compute per-dataset train_log stats caches so the rest of
        # the pipeline can read the precomputed _stats.json. The upload
        # flow in notebook_workspace calls ``ensure_dataset_stats``
        # eagerly; this block is the lazy fallback for datasets whose
        # cache hasn't been written yet (e.g. legacy uploads).
        for _ds in datasets:
            if not _ds.train_log_path:
                continue
            try:
                _ensure_dataset_stats(Path(_ds.train_log_path))
            except Exception as _exc:
                logger.warning(
                    "Failed to ensure train_log stats for %s: %s",
                    _ds.train_log_path, _exc,
                )

        sig = (
            self.CACHE_VERSION,
            notebook_id,
            tuple(sorted((d.id, d.train_log_path or "") for d in datasets)),
        )
        if use_cache and self._cache is not None and sig == self._cache_signature:
            return self._cache

        metrics: Dict[str, MetricSummary] = {}
        curves: Dict[str, List[CurvePoint]] = {}
        metrics_with_data = 0

        for metric in METRICS:
            summary = self._aggregate_metric(metric, datasets)
            if summary is None:
                continue
            metrics[metric] = summary
            metrics_with_data += 1
            for ds in datasets:
                log_dir = ds.train_log_path
                if not log_dir:
                    continue
                csv_path = Path(log_dir) / f"{metric}.csv"
                if csv_path.exists():
                    curves[metric] = _downsample_curve(per_sample_rows=_read_metric_csv_v2(csv_path)[0])
                    break

        snapshot = DashboardSnapshot(
            notebook_count=len(notebooks),
            dataset_count=len(datasets),
            metrics_with_data=metrics_with_data,
            scope_notebook_id=notebook_id,
            metrics=metrics,
            train_curves=curves,
        )
        self._cache = snapshot
        self._cache_signature = sig
        return snapshot

    def invalidate(self) -> None:
        self._cache = None
        self._cache_signature = None

    # ----- internal -----
    def _aggregate_metric(
        self, metric: str, datasets: Sequence
    ) -> Optional[MetricSummary]:
        """Build a MetricSummary for one metric column.

        Behaviour matches the ``train_log_stats`` module:

        * The CSV reader dedupes on ``(sample, seed, epoch)``.
        * Each sample's representative point is the strongest value
          across *all* epochs and seeds (``max(values)`` for
          higher-better metrics, last value for lower-better).
        * ``grand_mean`` / ``grand_variance`` are taken across
          the per-sample representative values, and the
          dataset-level panel uses the same per-sample values as
          its representative unit.
        """
        series: List[DatasetSeries] = []
        per_sample: Dict[str, DatasetSeries] = {}
        # Per-dataset: collect one entry per sample, equal to that
        # sample's strongest value across all epochs/seeds. So
        # ``_build_dataset_groups`` aggregates across samples within
        # a dataset using those per-sample best values, giving the
        # dataset its combined_mean / combined_variance.
        per_dataset_image_final: Dict[str, Dict[str, float]] = {}
        for ds in datasets:
            log_dir = ds.train_log_path
            if not log_dir:
                continue
            csv_path = Path(log_dir) / f"{metric}.csv"
            if not csv_path.exists():
                continue
            per_sample_id, _raw, _dedup = _read_metric_csv_v2(csv_path)
            for sample_id, entries in per_sample_id.items():
                if not entries:
                    continue
                values = [v for _, _, v in entries]
                mean_v = sum(values) / len(values)
                epochs_for_sample = {e for e, _, _ in entries}
                final_epoch = max(epochs_for_sample) if epochs_for_sample else 0
                # Delegate to the shared helper so every consumer
                # (dashboard, statistics, train_log_stats) uses the
                # same per-sample best-value selection.
                per_sample_best = _compute_per_sample_best(
                    {sample_id: entries}, metric,
                )
                rep_v = per_sample_best[sample_id]
                rep_var = 0.0
                series_row = DatasetSeries(
                    name=ds.name,
                    sample_id=sample_id,
                    notebook_id=ds.notebook_id,
                    final_value=rep_v,
                    mean=mean_v,
                    variance=0.0,
                    min_value=min(values),
                    max_value=max(values),
                    epochs_seen=len(values),
                    final_epoch=final_epoch,
                    final_epoch_mean=rep_v,
                    final_epoch_variance=rep_var,
                )
                # Last writer wins; mirrors a user re-uploading the same sample.
                per_sample[sample_id] = series_row
                per_dataset_image_final.setdefault(
                    ds.name, {}
                )[sample_id] = rep_v

        if not per_sample:
            return None

        series = list(per_sample.values())
        # Per-sample representative point is now the cross-seed mean
        # at the sample's final epoch; mean and variance are taken
        # across those per-image final-epoch means.
        finals = [s.final_epoch_mean for s in series]
        grand_mean = sum(finals) / len(finals)
        grand_var = _variance(finals)
        higher_better = _is_higher_better(metric)
        if higher_better:
            best = max(series, key=lambda s: s.final_epoch_mean)
            worst = min(series, key=lambda s: s.final_epoch_mean)
        else:
            best = min(series, key=lambda s: s.final_epoch_mean)
            worst = max(series, key=lambda s: s.final_epoch_mean)

        summary = MetricSummary(
            metric=metric,
            dataset_count=len(series),
            grand_mean=grand_mean,
            grand_variance=grand_var,
            best_sample_id=best.sample_id,
            best_value=best.final_epoch_mean,
            worst_sample_id=worst.sample_id,
            worst_value=worst.final_epoch_mean,
            series=series,
        )
        # Build dataset-level aggregation and pick the strongest / weakest
        # dataset by combined_mean. Populated from per-image final-epoch
        # means (one value per sample) so combined_mean = mean of
        # per-image final-epoch means and combined_variance = variance
        # of those means across samples within the dataset.
        per_dataset_values = {
            name: list(image_finals.values())
            for name, image_finals in per_dataset_image_final.items()
        }
        per_dataset_samples = {
            name: len(image_finals)
            for name, image_finals in per_dataset_image_final.items()
        }
        groups = _build_dataset_groups(per_dataset_values, per_dataset_samples)
        bd_name, bd_val, wd_name, wd_val = _pick_best_worst_dataset(
            groups, _is_higher_better(metric)
        )
        summary.dataset_groups = groups
        summary.best_dataset_name = bd_name
        summary.best_dataset_value = bd_val
        summary.worst_dataset_name = wd_name
        summary.worst_dataset_value = wd_val
        return summary


def _pick_best_worst_dataset(
    groups: Dict[str, DatasetGroupSummary],
    higher_better: bool,
) -> tuple[str, float, str, float]:
    """Pick best/worst dataset by combined_mean across dataset groups."""
    if not groups:
        return "", 0.0, "", 0.0
    items = list(groups.values())
    if higher_better:
        best = max(items, key=lambda g: g.combined_mean)
        worst = min(items, key=lambda g: g.combined_mean)
    else:
        best = min(items, key=lambda g: g.combined_mean)
        worst = max(items, key=lambda g: g.combined_mean)
    return best.name, best.combined_mean, worst.name, worst.combined_mean


def _build_dataset_groups(
    per_dataset_values: Dict[str, List[float]],
    per_dataset_samples: Dict[str, int],
) -> Dict[str, DatasetGroupSummary]:
    """Pool all per-sample per-epoch values by dataset.name and emit
    one DatasetGroupSummary per dataset name."""
    out: Dict[str, DatasetGroupSummary] = {}
    for name, values in per_dataset_values.items():
        if not values:
            continue
        n = len(values)
        mean_v = sum(values) / n
        var_v = _variance(values)
        out[name] = DatasetGroupSummary(
            name=name,
            combined_mean=mean_v,
            combined_variance=var_v,
            sample_count=per_dataset_samples.get(name, 0),
            epochs_total=n,
        )
    return out
