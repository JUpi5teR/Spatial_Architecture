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

import csv
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Sequence

from backend.models import DatasetManager, NotebookManager
from utils.logger import logger


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
    variance: float             # population variance across all epochs
    min_value: float
    max_value: float
    epochs_seen: int

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
        }


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
    per_sample: Dict[str, List[float]],
    max_points: int = 80,
) -> List[CurvePoint]:
    """Average each epoch across samples and downsample to <= max_points.

    We average across samples rather than emitting per-sample curves so
    the thumbnail only exposes aggregate trends, not individual data
    points (privacy: no per-sample trajectories are surfaced).
    """
    if not per_sample:
        return []
    max_len = max((len(v) for v in per_sample.values()), default=0)
    if max_len == 0:
        return []
    means: List[float] = []
    for i in range(max_len):
        vals = [v[i] for v in per_sample.values() if i < len(v)]
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
                    curves[metric] = _downsample_curve(_read_metric_csv(csv_path))
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
        series: List[DatasetSeries] = []
        per_sample: Dict[str, DatasetSeries] = {}
        for ds in datasets:
            log_dir = ds.train_log_path
            if not log_dir:
                continue
            csv_path = Path(log_dir) / f"{metric}.csv"
            if not csv_path.exists():
                continue
            per_sample_id = _read_metric_csv(csv_path)
            for sample_id, values in per_sample_id.items():
                if not values:
                    continue
                final_v = values[-1]
                mean_v = sum(values) / len(values)
                var_v = _variance(values)
                series_row = DatasetSeries(
                    name=ds.name,
                    sample_id=sample_id,
                    notebook_id=ds.notebook_id,
                    final_value=final_v,
                    mean=mean_v,
                    variance=var_v,
                    min_value=min(values),
                    max_value=max(values),
                    epochs_seen=len(values),
                )
                # Last writer wins; mirrors a user re-uploading the same sample.
                per_sample[sample_id] = series_row

        if not per_sample:
            return None

        series = list(per_sample.values())
        finals = [s.final_value for s in series]
        grand_mean = sum(finals) / len(finals)
        grand_var = _variance(finals)
        higher_better = _is_higher_better(metric)
        if higher_better:
            best = max(series, key=lambda s: s.final_value)
            worst = min(series, key=lambda s: s.final_value)
        else:
            best = min(series, key=lambda s: s.final_value)
            worst = max(series, key=lambda s: s.final_value)

        return MetricSummary(
            metric=metric,
            dataset_count=len(series),
            grand_mean=grand_mean,
            grand_variance=grand_var,
            best_sample_id=best.sample_id,
            best_value=best.final_value,
            worst_sample_id=worst.sample_id,
            worst_value=worst.final_value,
            series=series,
        )
