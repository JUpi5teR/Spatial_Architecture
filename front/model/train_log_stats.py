# coding: utf-8
"""Pre-computed statistics for a dataset's train_log directory.

train_log/*.csv uses a long format with columns
``sample, seed, epoch, <metric>`` (the original training script writes
this layout; the screenshot in the design notes shows the same data
re-ordered as ``epoch, image_name, seed, ari``). The CSV reader in this
module is order-agnostic and dedupes rows that share the same
``(sample, seed, epoch)`` triple, so re-running training or accidental
duplicate appends do not skew the per-image statistics.

Per-image contract (one image == one tissue section == one CSV row
group):

* ``best_value``     -- max value across that image's deduped rows.
                        ``best_epoch`` / ``best_seed`` are the
                        ``(epoch, seed)`` triple that produced it.
* ``mean`` / ``variance`` -- mean and population variance over the
                              image's deduped values.
* ``epochs_seen`` / ``seeds_seen`` -- unique epoch / seed counts.
* ``raw_count`` / ``dedup_count`` -- total rows vs. deduped rows
                                       (raw > dedup means duplicates
                                       were found).

Per-metric contract:

* ``grand_mean`` / ``grand_variance`` -- mean and variance of the
                                          per-image ``best_value``
                                          across all images. This is
                                          what the Overview dashboard
                                          surfaces as the metric's
                                          representative value.
* ``best_image`` / ``worst_image`` -- image name with highest /
                                       lowest ``best_value``
                                       (``higher_is_better`` aware).
"""
from __future__ import annotations

import sys as _sys
from pathlib import Path as _Path
# Allow ``from utils.logger import logger`` to resolve to
# ``front/utils/logger.py`` when this module is imported via the
# ``front.model.train_log_stats`` package path. Mirrors the setup used
# in dashboard_data.py and overview_dashboard.py.
_front = _Path(__file__).resolve().parent.parent
if str(_front) not in _sys.path:
    _sys.path.insert(0, str(_front))
del _sys, _Path

import csv
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Set, Tuple

from utils.logger import logger


STATS_FILENAME = "_stats.json"
STATS_VERSION = 4

# Metric families that should be treated as "higher is better" when
# picking the best / worst image. Loss / error-style metrics invert
# this. The default policy matches the dashboard's metric palette.
HIGHER_IS_BETTER: Set[str] = {"ari", "nmi", "hs", "cs", "acc", "accuracy"}

FINAL_EPOCH = 900


def _get_final_epoch(entries):
    """Find the maximum epoch across all entries."""
    max_e = 0
    for e, _, _ in entries:
        if e > max_e:
            max_e = e
    return max_e
  # final training epoch for all evaluation stats


# ---------------------------------------------------------------------------
# Data shapes (returned by the loaders, also used by the dashboard)
# ---------------------------------------------------------------------------
@dataclass
class ImageStat:
    """Per-image aggregate row for a single metric."""

    best_value: float = 0.0
    best_epoch: int = 0
    best_seed: int = 0
    mean: float = 0.0
    variance: float = 0.0           # always 0 (one max-seed representative value per image)
    min_value: float = 0.0
    max_value: float = 0.0
    epochs_seen: int = 0
    seeds_seen: int = 0
    raw_count: int = 0
    dedup_count: int = 0
    final_epoch: int = 0
    final_epoch_mean: float = 0.0
    final_epoch_variance: float = 0.0

    def as_dict(self) -> Dict[str, float]:
        return {
            "best_value": self.best_value,
            "best_epoch": self.best_epoch,
            "best_seed": self.best_seed,
            "mean": self.mean,
            "variance": self.variance,
            "min": self.min_value,
            "max": self.max_value,
            "epochs_seen": self.epochs_seen,
            "seeds_seen": self.seeds_seen,
            "raw_count": self.raw_count,
            "dedup_count": self.dedup_count,
            "final_epoch": self.final_epoch,
            "final_epoch_mean": self.final_epoch_mean,
            "final_epoch_variance": self.final_epoch_variance,
        }


@dataclass
class MetricStat:
    """Aggregate of all per-image stats for a single metric."""

    metric: str
    grand_mean: float = 0.0
    grand_variance: float = 0.0
    best_image: str = ""
    best_image_value: float = 0.0
    worst_image: str = ""
    worst_image_value: float = 0.0
    image_count: int = 0
    per_image: Dict[str, ImageStat] = field(default_factory=dict)

    def as_dict(self) -> Dict[str, object]:
        return {
            "metric": self.metric,
            "grand_mean": self.grand_mean,
            "grand_variance": self.grand_variance,
            "best_image": self.best_image,
            "best_image_value": self.best_image_value,
            "worst_image": self.worst_image,
            "worst_image_value": self.worst_image_value,
            "image_count": self.image_count,
            "per_image": {k: v.as_dict() for k, v in self.per_image.items()},
        }


@dataclass
class DatasetStats:
    """All metrics for one train_log directory."""

    train_log_dir: Path
    metrics: Dict[str, MetricStat] = field(default_factory=dict)
    computed_at: str = ""

    def as_dict(self) -> Dict[str, object]:
        return {
            "version": STATS_VERSION,
            "computed_at": self.computed_at,
            "metrics": {k: v.as_dict() for k, v in self.metrics.items()},
        }


# ---------------------------------------------------------------------------
# Math helpers
# ---------------------------------------------------------------------------
def _variance(values: Sequence[float]) -> float:
    """Population variance (divisor n)."""
    n = len(values)
    if n == 0:
        return 0.0
    mean = sum(values) / n
    return sum((v - mean) ** 2 for v in values) / n


def aggregate_epoch_means(
    per_sample_rows: Dict[str, List[Tuple[int, int, float]]],
) -> Dict[str, Dict[int, float]]:
    """Aggregate per-sample per-epoch values by computing the mean across seeds.

    Each CSV row is ``(epoch, seed, value)``. When the same sample was
    trained with multiple seeds, this collapses them into a single
    mean per (sample, epoch). The result is ready for plotting
    training curves.

    Returns ``{sample_id: {epoch: mean_value}}``.
    """
    result: Dict[str, Dict[int, float]] = {}
    for sample_id, entries in per_sample_rows.items():
        epoch_groups: Dict[int, List[float]] = {}
        for epoch, _seed, value in entries:
            epoch_groups.setdefault(epoch, []).append(value)
        result[sample_id] = {
            epoch: sum(vals) / len(vals)
            for epoch, vals in epoch_groups.items()
        }
    return result


def compute_per_sample_best(
    per_sample_rows: Dict[str, List[Tuple[int, int, float]]],
    metric: str = "",
) -> Dict[str, float]:
    """For each sample, pick the strongest value at final epoch only.

    Filters to rows at final epoch (max epoch in data),
    then takes max across seeds for higher-better metrics,
    or mean across seeds for lower-better metrics.
    """
    metric_lower = metric.lower() if metric else ""
    higher_better = (metric_lower in HIGHER_IS_BETTER) if metric_lower else True
    result: Dict[str, float] = {}
    for sample_id, entries in per_sample_rows.items():
        if not entries:
            continue
        fe = _get_final_epoch(entries)
        final_entries = [v for e, _, v in entries if e == fe]
        if not final_entries:
            continue
        if higher_better:
            result[sample_id] = max(final_entries)
        else:
            result[sample_id] = sum(final_entries) / len(final_entries)
    return result


def _safe_float(s: object) -> Optional[float]:
    try:
        return float(s)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None


def _safe_int(s: object, default: int = 0) -> int:
    try:
        return int(float(s))  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return default


def _count_raw_rows(
    csv_path: Path,
    known_samples: Iterable[str],
) -> Dict[str, int]:
    """Count input rows per sample id, before dedup. Samples absent
    from ``known_samples`` are ignored."""
    keep = {s for s in known_samples}
    out: Dict[str, int] = {s: 0 for s in keep}
    try:
        with open(csv_path, "r", encoding="utf-8", newline="") as fh:
            reader = csv.reader(fh)
            header = [h.strip().lower() for h in next(reader, [])]
            sample_idx = 0
            for cand in ("sample", "image", "image_name", "barcode", "cell_id"):
                if cand in header:
                    sample_idx = header.index(cand)
                    break
            for row in reader:
                if len(row) <= sample_idx:
                    continue
                s = row[sample_idx].strip()
                if s in keep:
                    out[s] = out.get(s, 0) + 1
    except OSError as exc:
        logger.warning("Cannot count raw rows in %s: %s", csv_path, exc)
    return out


# ---------------------------------------------------------------------------
# CSV reader (long-format, order-agnostic, deduped)
# ---------------------------------------------------------------------------
def read_metric_csv(
    csv_path: Path,
) -> Tuple[Dict[str, List[Tuple[int, int, float]]], int, int]:
    """Read a metric CSV.

    Returns ``(per_sample, raw_count, dedup_count)`` where
    ``per_sample`` is ``{sample_id: [(epoch, seed, value), ...]}``
    with duplicates removed (see contract below).

    * Detects the long-format layout regardless of column order:
      we pick the column literally named ``sample`` (or ``image`` /
      ``image_name`` / ``barcode``) and treat the LAST column as the
      metric value. The remaining recognised columns (``seed``,
      ``epoch``) are picked by name.
    * Dedupes on ``(sample, seed, epoch)`` -- first occurrence wins.
      ``raw_count`` is the number of *input* rows seen, ``dedup_count``
      is the number of unique rows kept.
    """
    out: Dict[str, List[Tuple[int, int, float]]] = {}
    seen: Dict[Tuple[str, int, int], bool] = {}
    raw_count = 0
    dedup_count = 0
    try:
        with open(csv_path, "r", encoding="utf-8", newline="") as fh:
            reader = csv.reader(fh)
            header = [h.strip().lower() for h in next(reader, [])]
            if not header or len(header) < 2:
                return out, raw_count, dedup_count
            sample_idx = None
            for cand in ("sample", "image", "image_name", "barcode", "cell_id"):
                if cand in header:
                    sample_idx = header.index(cand)
                    break
            if sample_idx is None:
                sample_idx = 0
            epoch_idx = header.index("epoch") if "epoch" in header else None
            seed_idx = header.index("seed") if "seed" in header else None
            # Value column: use the LAST column that is not one of the
            # known metadata columns. This keeps the reader robust to
            # re-ordered layouts like epoch | image_name | seed | ari.
            skip_indices = {sample_idx}
            if epoch_idx is not None:
                skip_indices.add(epoch_idx)
            if seed_idx is not None:
                skip_indices.add(seed_idx)
            value_idx = max(
                (i for i in range(len(header)) if i not in skip_indices),
                default=len(header) - 1,
            )
            for row in reader:
                if len(row) <= value_idx:
                    continue
                sample = row[sample_idx].strip()
                if not sample:
                    continue
                val = _safe_float(row[value_idx])
                if val is None:
                    continue
                epoch = (
                    _safe_int(row[epoch_idx], default=0) if epoch_idx is not None
                    else 0
                )
                seed = (
                    _safe_int(row[seed_idx], default=0) if seed_idx is not None
                    else 0
                )
                key = (sample, seed, epoch)
                raw_count += 1
                if key in seen:
                    continue
                seen[key] = True
                dedup_count += 1
                out.setdefault(sample, []).append((epoch, seed, val))
    except OSError as exc:
        logger.warning("Cannot read train log csv %s: %s", csv_path, exc)
    return out, raw_count, dedup_count


# ---------------------------------------------------------------------------
# Stat computation
# ---------------------------------------------------------------------------
def compute_image_stat(
    entries: List[Tuple[int, int, float]],
    raw_count: int = 0,
    metric: str = "",
) -> ImageStat:

    """Reduce an image rows to one ImageStat, using only FINAL_EPOCH.

    Filters rows to FINAL_EPOCH, then:
    - Higher-better metrics: best_value = max across seeds.
    - Lower-better metrics: best_value = mean across seeds.
    """
    if not entries:
        return ImageStat()
    if raw_count <= 0:
        raw_count = len(entries)
    fe = _get_final_epoch(entries)
    final_entries = [(e, s, v) for (e, s, v) in entries if e == fe]
    if not final_entries:
        return ImageStat()
    dedup_count = len(entries)
    values = [v for _, _, v in final_entries]
    metric_lower = metric.lower() if isinstance(metric, str) else ""
    if metric_lower and metric_lower not in HIGHER_IS_BETTER:
        best_value = sum(values) / len(values)
        best_epoch = fe
        best_seed = 0
    else:
        best_value = max(values)
        best_idx = values.index(best_value)
        best_epoch, best_seed = final_entries[best_idx][0], final_entries[best_idx][1]
    seeds = {s for _, s, _ in final_entries}
    mean_v = sum(values) / len(values)
    return ImageStat(
        best_value=float(best_value),
        best_epoch=int(best_epoch),
        best_seed=int(best_seed),
        mean=float(mean_v),
        variance=0.0,
        min_value=float(min(values)),
        max_value=float(max(values)),
        epochs_seen=1,
        seeds_seen=len(seeds),
        raw_count=raw_count,
        dedup_count=dedup_count,
        final_epoch=int(fe),
        final_epoch_mean=float(best_value),
        final_epoch_variance=0.0,
    )
def compute_metric_stat(
    metric: str,
    per_sample_rows: Dict[str, List[Tuple[int, int, float]]],
    per_sample_raw: Optional[Dict[str, int]] = None,
) -> MetricStat:
    """Aggregate ``per_sample_rows`` (output of ``read_metric_csv``)
    into a ``MetricStat``."""
    per_image: Dict[str, ImageStat] = {}
    for sample, entries in per_sample_rows.items():
        raw = (per_sample_raw or {}).get(sample, 0)
        per_image[sample] = compute_image_stat(
            entries, raw_count=raw, metric=metric,
        )

    if not per_image:
        return MetricStat(metric=metric)

    # Grand aggregate uses each image's final-epoch cross-seed mean,
    # not its best run across all epochs. This keeps the cache
    # ``_stats.json`` consistent with what the overview dashboard
    # renders on top of these CSV files.
    final_means = [s.final_epoch_mean for s in per_image.values()]
    grand_mean = sum(final_means) / len(final_means)
    grand_var = _variance(final_means)

    higher_better = metric.lower() in HIGHER_IS_BETTER
    if higher_better:
        best_image_name = max(
            per_image, key=lambda k: per_image[k].final_epoch_mean
        )
        worst_image_name = min(
            per_image, key=lambda k: per_image[k].final_epoch_mean
        )
    else:
        best_image_name = min(
            per_image, key=lambda k: per_image[k].final_epoch_mean
        )
        worst_image_name = max(
            per_image, key=lambda k: per_image[k].final_epoch_mean
        )

    return MetricStat(
        metric=metric,
        grand_mean=float(grand_mean),
        grand_variance=float(grand_var),
        best_image=best_image_name,
        best_image_value=float(per_image[best_image_name].final_epoch_mean),
        worst_image=worst_image_name,
        worst_image_value=float(per_image[worst_image_name].final_epoch_mean),
        image_count=len(per_image),
        per_image=per_image,
    )


def _metric_filename(metric: str, log_dir: Path) -> Path:
    """Locate the CSV for ``metric`` inside ``log_dir``. Tries the
    lowercased name first, then preserves the original casing."""
    for cand in (f"{metric.lower()}.csv", f"{metric}.csv"):
        p = log_dir / cand
        if p.exists():
            return p
    return log_dir / f"{metric.lower()}.csv"


def compute_dataset_stats(
    train_log_dir: Path,
    metrics: Optional[Iterable[str]] = None,
) -> DatasetStats:
    """Build a ``DatasetStats`` for every metric CSV found in
    ``train_log_dir``. If ``metrics`` is given, restrict to those names
    (case-insensitive); otherwise discover ``*.csv`` files but skip the
    stats cache (``_stats.json``)."""
    metrics_list: Optional[List[str]] = (
        [m.lower() for m in metrics] if metrics is not None else None
    )
    result = DatasetStats(
        train_log_dir=train_log_dir,
        computed_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
    )
    if not train_log_dir.is_dir():
        logger.info("train_log dir missing: %s", train_log_dir)
        return result
    if metrics_list is None:
        files = sorted(p for p in train_log_dir.glob("*.csv"))
    else:
        files = [_metric_filename(m, train_log_dir) for m in metrics_list]
        files = [p for p in files if p.exists()]
    for path in files:
        metric = path.stem.lower()
        rows, _raw, _dedup = read_metric_csv(path)
        if not rows:
            continue
        per_sample_raw = _count_raw_rows(path, rows)
        result.metrics[metric] = compute_metric_stat(
            metric, rows, per_sample_raw=per_sample_raw,
        )
    return result


# ---------------------------------------------------------------------------
# Cache I/O
# ---------------------------------------------------------------------------
def save_dataset_stats(
    train_log_dir: Path, stats: DatasetStats
) -> Optional[Path]:
    """Write stats JSON next to the train_log CSVs. Returns the output
    path on success or ``None`` on failure."""
    try:
        train_log_dir.mkdir(parents=True, exist_ok=True)
        out = train_log_dir / STATS_FILENAME
        with open(out, "w", encoding="utf-8") as fh:
            json.dump(stats.as_dict(), fh, indent=2, sort_keys=True)
        logger.info("Wrote train_log stats cache: %s", out)
        return out
    except OSError as exc:
        logger.warning("Failed to write train_log stats cache: %s", exc)
        return None


def load_dataset_stats(train_log_dir: Path) -> Optional[DatasetStats]:
    """Load and validate a cached stats JSON. Returns ``None`` when the
    file is missing or unreadable so callers can fall back to a
    live recompute."""
    path = train_log_dir / STATS_FILENAME
    if not path.is_file():
        return None
    try:
        with open(path, "r", encoding="utf-8") as fh:
            raw = json.load(fh)
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning("Cannot read stats cache %s: %s", path, exc)
        return None
    if not isinstance(raw, dict):
        return None
    version = raw.get("version", 0)
    if version != STATS_VERSION:
        logger.info(
            "Stats cache %s has version %s (expected %s); ignoring",
            path, version, STATS_VERSION,
        )
        return None
    metrics_raw = raw.get("metrics", {})
    if not isinstance(metrics_raw, dict):
        return None
    stats = DatasetStats(
        train_log_dir=train_log_dir,
        computed_at=str(raw.get("computed_at", "")),
    )
    for metric_name, mraw in metrics_raw.items():
        if not isinstance(mraw, dict):
            continue
        per_image_raw = mraw.get("per_image", {})
        per_image: Dict[str, ImageStat] = {}
        if isinstance(per_image_raw, dict):
            for img, irst in per_image_raw.items():
                if not isinstance(irst, dict):
                    continue
                per_image[str(img)] = ImageStat(
                    best_value=float(irst.get("best_value", 0.0)),
                    best_epoch=int(irst.get("best_epoch", 0)),
                    best_seed=int(irst.get("best_seed", 0)),
                    mean=float(irst.get("mean", 0.0)),
                    variance=float(irst.get("variance", 0.0)),
                    min_value=float(irst.get("min", irst.get("min_value", 0.0))),
                    max_value=float(irst.get("max", irst.get("max_value", 0.0))),
                    epochs_seen=int(irst.get("epochs_seen", 0)),
                    seeds_seen=int(irst.get("seeds_seen", 0)),
                    raw_count=int(irst.get("raw_count", 0)),
                    dedup_count=int(irst.get("dedup_count", 0)),
                    final_epoch=int(irst.get("final_epoch", 0)),
                    final_epoch_mean=float(irst.get("final_epoch_mean", 0.0)),
                    final_epoch_variance=float(irst.get("final_epoch_variance", 0.0)),
                )
        stats.metrics[str(metric_name)] = MetricStat(
            metric=str(metric_name),
            grand_mean=float(mraw.get("grand_mean", 0.0)),
            grand_variance=float(mraw.get("grand_variance", 0.0)),
            best_image=str(mraw.get("best_image", "")),
            best_image_value=float(mraw.get("best_image_value", 0.0)),
            worst_image=str(mraw.get("worst_image", "")),
            worst_image_value=float(mraw.get("worst_image_value", 0.0)),
            image_count=int(mraw.get("image_count", 0)),
            per_image=per_image,
        )
    return stats


def ensure_dataset_stats(
    train_log_dir: Path,
    metrics: Optional[Iterable[str]] = None,
    use_cache: bool = True,
) -> DatasetStats:
    """Return the cached stats for ``train_log_dir`` if present and
    ``use_cache`` is True, otherwise compute and persist a fresh copy."""
    if use_cache:
        cached = load_dataset_stats(train_log_dir)
        if cached is not None:
            return cached
    stats = compute_dataset_stats(train_log_dir, metrics=metrics)
    if stats.metrics:
        save_dataset_stats(train_log_dir, stats)
    return stats
