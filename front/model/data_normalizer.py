# coding: utf-8
"""Data normalizer - ensures Results / train_log CSVs are well-formed.

Goals
-----
1. **Results** CSVs (per-sample `spatial/tissue_positions_list.csv`):
   * Always have a header row with standard column names.
   * Required columns: ``barcode, in_tissue, row, col, pxl_row, pxl_col, domain``.
   * Common aliases (e.g. ``pxl_row_in_fullres``) are mapped to canonical names.
   * Missing core columns are appended as empty.

2. **train_log** CSVs:
   * Format detection: ``wide`` (epoch x sample) vs ``long`` (epoch, sample, metric).
   * Unified reader (``read_metric_csv``) handles both transparently via
     **column-name matching** (the recommended approach in the task spec).
   * Optionally write back normalized wide format when ``--apply`` is used.

This module is intentionally side-effect free for read functions; the
``normalize_*`` functions only write when ``dry_run=False``.
"""
from __future__ import annotations

import csv
import io
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Optional

import pandas as pd

from utils.logger import logger


# ====================================================================
# Standard column definitions
# ====================================================================
RESULTS_REQUIRED_COLS: list[str] = [
    "barcode", "in_tissue", "row", "col", "pxl_row", "pxl_col", "domain",
]

# Lowercased alias -> canonical name
RESULTS_COL_ALIASES: dict[str, str] = {
    "barcode": "barcode",
    "cell_id": "barcode",
    "cell": "barcode",
    "spot": "barcode",
    "spot_id": "barcode",
    "in_tissue": "in_tissue",
    "intissue": "in_tissue",
    "row": "row",
    "array_row": "row",
    "col": "col",
    "array_col": "col",
    "pxl_row": "pxl_row",
    "pxl_row_in_fullres": "pxl_row",
    "imagerow": "pxl_row",
    "image_row": "pxl_row",
    "pxl_col": "pxl_col",
    "pxl_col_in_fullres": "pxl_col",
    "imagecol": "pxl_col",
    "image_col": "pxl_col",
    "domain": "domain",
    "prediction": "domain",
    "label": "domain",
    "cluster": "domain",
    "graphbased": "domain",
    "pred": "domain",
    "pred_label": "domain",
    "predict": "domain",
}

TRAIN_LOG_METRIC_COL_ALIASES: dict[str, str] = {
    "loss": "loss",
    "train_loss": "loss",
    "training_loss": "loss",
    "ari": "ari",
    "nmi": "nmi",
    "hs": "hs",
    "cs": "cs",
}


# ====================================================================
# Report data classes
# ====================================================================
@dataclass
class FileAction:
    path: Path
    detected_format: str = "unknown"        # "ok" | "missing_header" | "wide" | "long" | "unknown"
    added_columns: list[str] = field(default_factory=list)
    renamed_columns: dict[str, str] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)
    error: Optional[str] = None

    @property
    def modified(self) -> bool:
        return bool(self.added_columns or self.renamed_columns)


@dataclass
class NormalizeReport:
    target: Path
    file_actions: list[FileAction] = field(default_factory=list)

    @property
    def total(self) -> int:
        return len(self.file_actions)

    @property
    def modified_count(self) -> int:
        return sum(1 for a in self.file_actions if a.modified)

    @property
    def error_count(self) -> int:
        return sum(1 for a in self.file_actions if a.error)

    def summary(self) -> str:
        lines = [
            f"Target: {self.target}",
            f"Total files scanned: {self.total}",
            f"Modified: {self.modified_count}",
            f"Errors: {self.error_count}",
        ]
        for a in self.file_actions:
            status = "OK" if not a.error and not a.modified else (
                "ERR" if a.error else "MOD"
            )
            desc = f"  [{status}] {a.path.name}"
            if a.detected_format and a.detected_format != "unknown":
                desc += f"  format={a.detected_format}"
            if a.added_columns:
                desc += f"  added={a.added_columns}"
            if a.renamed_columns:
                desc += f"  renamed={a.renamed_columns}"
            if a.notes:
                desc += f"  notes={a.notes}"
            if a.error:
                desc += f"  error={a.error}"
            lines.append(desc)
        return "\n".join(lines)


# ====================================================================
# Helpers
# ====================================================================
def _sniff_delimiter(sample: str) -> str:
    """Return the most likely delimiter for a sample string."""
    try:
        sniffer = csv.Sniffer()
        dialect = sniffer.sniff(sample, delimiters=",\t;|")
        return dialect.delimiter
    except csv.Error:
        # Fallback: count occurrences
        counts = {d: sample.count(d) for d in (",", "\t", ";", "|")}
        return max(counts, key=counts.get) if any(counts.values()) else ","


def _read_first_lines(path: Path, n: int = 3) -> list[str]:
    """Read up to ``n`` lines from ``path``. Returns fewer lines if EOF."""
    out: list[str] = []
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            for _ in range(n):
                line = f.readline()
                if not line:
                    break
                out.append(line.rstrip("\r\n"))
    except OSError:
        return []
    return out


def _looks_like_header(line: str) -> bool:
    """Heuristic: a line that is non-empty, non-numeric, has multiple words,
    and contains at least one known alias looks like a header."""
    if not line:
        return False
    parts = [p.strip().lower() for p in line.replace(";", ",").split(",")]
    if not parts or all(p == "" for p in parts):
        return False
    if all(p.lstrip("-").isdigit() for p in parts if p):
        return False
    if not any(p in RESULTS_COL_ALIASES for p in parts):
        return False
    return True


def _map_columns(cols: list[str]) -> tuple[list[str], dict[str, str], list[str]]:
    """Map columns to canonical names.

    Returns ``(mapped_cols, rename_map, warnings)`` where ``warnings`` lists
    any columns that were kept under their original name to avoid data loss
    (e.g., when two source columns both alias to the same canonical name,
    only the first is renamed; the second is kept as-is so its data is
    preserved).
    """
    mapped: list[str] = []
    rename_map: dict[str, str] = {}
    warnings: list[str] = []
    used_canonicals: set[str] = set()
    for col in cols:
        key = col.strip().lower()
        canonical = RESULTS_COL_ALIASES.get(key)
        if canonical and canonical not in used_canonicals:
            mapped.append(canonical)
            used_canonicals.add(canonical)
            if canonical != col:
                rename_map[col] = canonical
        else:
            # Keep the original column name to preserve its data.
            mapped.append(col)
            if canonical:
                warnings.append(
                    f"column '{col}' (alias of '{canonical}') kept as-is "
                    f"to avoid collision with earlier column"
                )
    return mapped, rename_map, warnings


# ====================================================================
# Results normalization
# ====================================================================
def _process_results_file(
    path: Path, *, dry_run: bool
) -> FileAction:
    """Normalize a single Results CSV/TSV file in place (unless dry_run)."""
    action = FileAction(path=path, detected_format="unknown")
    if not path.exists():
        action.error = "file not found"
        return action

    first_lines = _read_first_lines(path, n=2)
    if not first_lines:
        action.error = "empty file"
        return action

    delimiter = _sniff_delimiter("\n".join(first_lines))
    first_line = first_lines[0]

    # ---- Detect / fix header ----
    if _looks_like_header(first_line):
        # Read existing header
        try:
            df = pd.read_csv(path, sep=delimiter, dtype=str, keep_default_na=False)
        except Exception as exc:
            action.error = f"read failed: {exc}"
            return action

        original_cols = list(df.columns)
        mapped_cols, rename_map, warnings = _map_columns(original_cols)
        action.renamed_columns = rename_map
        if warnings:
            action.notes.extend(warnings)
        action.detected_format = "ok"

        # Append missing required columns
        for col in RESULTS_REQUIRED_COLS:
            if col not in mapped_cols:
                df[col] = ""
                mapped_cols.append(col)
                action.added_columns.append(col)

        if not action.modified:
            return action

        # Rename columns in-place (preserves duplicates that we kept)
        if rename_map:
            df = df.rename(columns=rename_map)
            # Rebuild mapped_cols to match the renamed DataFrame
            mapped_cols = list(df.columns)

        # Reorder columns: required first, then extras. Use ``reindex(columns=...)``
        # with deduplicated order; duplicated original-name columns are preserved
        # by leaving them out of the reindex and concatenating at the end.
        seen: set[str] = set()
        new_order: list[str] = []
        for c in list(RESULTS_REQUIRED_COLS) + mapped_cols:
            if c in seen:
                continue
            seen.add(c)
            new_order.append(c)
        # Identify columns that would be dropped by reindex due to duplicates
        duplicated = [c for c in mapped_cols if mapped_cols.count(c) > 1]
        for c in duplicated:
            action.notes.append(f"duplicate column kept: '{c}'")
        df = df.reindex(columns=new_order)

        if not dry_run:
            try:
                df.to_csv(
                    path, sep=delimiter, index=False, encoding="utf-8",
                )
            except Exception as exc:
                action.error = f"write failed: {exc}"
        return action

    # ---- Missing header: synthesize one ----
    action.detected_format = "missing_header"
    try:
        df = pd.read_csv(path, sep=delimiter, header=None, dtype=str,
                         keep_default_na=False)
    except Exception as exc:
        action.error = f"read failed: {exc}"
        return action

    n_cols = df.shape[1]
    # Synthesize header: first len(RESULTS_REQUIRED_COLS) columns get the
    # canonical names; any extra columns are named ``extra_col_<i>`` so
    # their data is preserved rather than silently dropped.
    new_cols: list[str] = []
    for i in range(n_cols):
        if i < len(RESULTS_REQUIRED_COLS):
            new_cols.append(RESULTS_REQUIRED_COLS[i])
        else:
            new_cols.append(f"extra_col_{i - len(RESULTS_REQUIRED_COLS)}")
    df.columns = new_cols

    extra_cols = [c for c in df.columns if c.startswith("extra_col_")]
    if extra_cols:
        action.notes.append(
            f"synthesized header with {len(extra_cols)} extra columns"
        )

    # Make sure all REQUIRED cols are present (already true for n_cols >= 7).
    for col in RESULTS_REQUIRED_COLS:
        if col not in df.columns:
            df[col] = ""
            action.added_columns.append(col)
    action.notes.append("synthesized header")

    if not dry_run:
        try:
            df.to_csv(path, sep=delimiter, index=False, encoding="utf-8")
        except Exception as exc:
            action.error = f"write failed: {exc}"
    return action


def normalize_results_dir(
    results_dir: Path, *, dry_run: bool = False
) -> NormalizeReport:
    """Normalize every Results/<sample>/spatial/*.csv under ``results_dir``.

    If ``results_dir`` itself is a section folder, processes it directly.
    """
    report = NormalizeReport(target=results_dir)
    if not results_dir.exists():
        return report

    candidate_dirs: list[Path] = []
    # Case 1: results_dir == Results/ root
    if any(p.is_dir() and (p / "spatial").is_dir() for p in results_dir.iterdir()
           if not p.name.startswith(".")):
        for sid_dir in sorted(results_dir.iterdir()):
            spatial = sid_dir / "spatial"
            if sid_dir.is_dir() and spatial.is_dir():
                candidate_dirs.append(spatial)
    # Case 2: results_dir == a single section (e.g. Results/151507)
    elif (results_dir / "spatial").is_dir():
        candidate_dirs.append(results_dir / "spatial")
    # Case 3: results_dir is itself the spatial folder
    elif any(results_dir.glob("*.csv")) or any(results_dir.glob("*.tsv")):
        candidate_dirs.append(results_dir)

    for spatial_dir in candidate_dirs:
        for csv_path in sorted(list(spatial_dir.glob("*.csv")) +
                               list(spatial_dir.glob("*.tsv"))):
            action = _process_results_file(csv_path, dry_run=dry_run)
            report.file_actions.append(action)
    return report


# ====================================================================
# train_log normalization
# ====================================================================
def detect_csv_format(path: Path) -> str:
    """Return ``"wide"`` (epoch x sample) or ``"long"`` (epoch, sample, metric)."""
    if not path.exists():
        return "unknown"
    try:
        df = pd.read_csv(path, nrows=2)
    except Exception:
        return "unknown"
    cols = [str(c).strip().lower() for c in df.columns]
    if "sample" in cols and "epoch" in cols:
        return "long"
    if "epoch" in cols:
        return "wide"
    return "unknown"


def _pivot_long_to_wide(df: pd.DataFrame, metric_col: str) -> pd.DataFrame:
    """Convert long-format (epoch, sample, metric) to wide (epoch x sample)."""
    if "epoch" not in df.columns or "sample" not in df.columns:
        return df
    if metric_col not in df.columns:
        # Fallback: take the first non-epoch/sample column
        candidates = [c for c in df.columns
                      if str(c).lower() not in ("epoch", "sample")]
        if not candidates:
            return df
        metric_col = candidates[0]
    wide = df.pivot_table(
        index="epoch", columns="sample", values=metric_col,
        aggfunc="first",
    )
    wide = wide.reset_index()
    return wide


def read_metric_csv(path: Path, metric_name: str) -> pd.DataFrame:
    """Unified reader for train_log CSV.

    Returns a wide-format DataFrame with ``epoch`` as the first column and one
    column per sample. Supports both:

    * wide format: ``epoch, sample1, sample2, ...``
    * long format: ``epoch, sample, <metric>``

    The ``metric_name`` argument is only used to disambiguate when the file
    uses long format and the value column is named generically (e.g. ``value``).
    The function is robust to **column name matching**: extra columns or
    reordered columns are handled automatically.
    """
    if not path.exists():
        raise FileNotFoundError(f"CSV not found: {path}")

    first_lines = _read_first_lines(path, n=2)
    if not first_lines:
        raise ValueError(f"Empty CSV: {path}")

    delimiter = _sniff_delimiter("\n".join(first_lines))

    try:
        df = pd.read_csv(path, sep=delimiter)
    except Exception as exc:
        raise ValueError(f"Failed to parse {path}: {exc}")

    if df.empty:
        return df

    cols = [str(c).strip() for c in df.columns]
    df.columns = cols

    # Normalize known aliases
    rename: dict[str, str] = {}
    lower_cols = [c.lower() for c in cols]
    if "epoch" in lower_cols:
        idx = lower_cols.index("epoch")
        if cols[idx] != "epoch":
            rename[cols[idx]] = "epoch"
    if "sample" in lower_cols:
        idx = lower_cols.index("sample")
        if cols[idx] != "sample":
            rename[cols[idx]] = "sample"
    target_metric = metric_name.strip().lower()
    alias_canonical = TRAIN_LOG_METRIC_COL_ALIASES.get(target_metric, target_metric)
    if alias_canonical in lower_cols:
        idx = lower_cols.index(alias_canonical)
        if cols[idx] != alias_canonical:
            rename[cols[idx]] = alias_canonical
    if rename:
        df = df.rename(columns=rename)
        cols = list(df.columns)
        lower_cols = [c.lower() for c in cols]

    has_sample = "sample" in lower_cols
    has_epoch = "epoch" in lower_cols

    if not has_epoch:
        # Cannot pivot without epoch - return as-is
        logger.warning("read_metric_csv: no 'epoch' column in %s", path)
        return df

    if has_sample:
        # Long format
        metric_col = None
        if alias_canonical in lower_cols:
            metric_col = alias_canonical
        else:
            # First non-epoch, non-sample column
            for c in cols:
                if c.lower() not in ("epoch", "sample"):
                    metric_col = c
                    break
        if metric_col is None:
            return df
        wide = _pivot_long_to_wide(df, metric_col)
        # Coerce sample column names to strings (pivot may produce ints)
        new_cols = []
        for c in wide.columns:
            if str(c).lower() == "epoch":
                new_cols.append("epoch")
            else:
                new_cols.append(str(c))
        wide.columns = new_cols
        return wide

    # Wide format - return as-is (epoch is already first column)
    # Coerce sample column names to strings to ensure consistent lookup
    new_cols = []
    for c in df.columns:
        if str(c).lower() == "epoch":
            new_cols.append("epoch")
        else:
            new_cols.append(str(c))
    df.columns = new_cols
    return df


def _process_train_log_file(
    path: Path, *, dry_run: bool
) -> FileAction:
    """Normalize a single train_log CSV. Currently ensures the file is parseable
    and has either wide or long header. Writes a normalized wide version when
    ``--apply`` is used and the file is currently in long format.
    """
    action = FileAction(path=path, detected_format="unknown")
    if not path.exists():
        action.error = "file not found"
        return action

    fmt = detect_csv_format(path)
    action.detected_format = fmt if fmt != "unknown" else "unknown"

    if fmt == "unknown":
        action.notes.append("format not recognized; skipping")
        return action

    if fmt == "long" and not dry_run:
        # Convert long -> wide and write back (overwrite)
        try:
            df = pd.read_csv(path)
            # Drop the metric column header to use the file's metric name
            metric_cols = [c for c in df.columns
                           if c.lower() not in ("epoch", "sample")]
            metric_col = metric_cols[0] if metric_cols else path.stem
            wide = _pivot_long_to_wide(df, metric_col)
            # Backup
            backup = path.with_suffix(path.suffix + ".bak")
            if not backup.exists():
                shutil.copy2(path, backup)
                action.notes.append(f"backup -> {backup.name}")
            wide.to_csv(path, index=False)
            action.notes.append("converted long -> wide")
        except Exception as exc:
            action.error = f"long->wide conversion failed: {exc}"
    return action


def normalize_train_log_dir(
    train_log_dir: Path, *, dry_run: bool = False
) -> NormalizeReport:
    """Normalize every train_log CSV in the directory.

    By default (dry_run=True) this only reports detected formats.
    With dry_run=False, long-format files are converted to wide format
    (after a ``.bak`` backup is created).
    """
    report = NormalizeReport(target=train_log_dir)
    if not train_log_dir.exists():
        return report

    for csv_path in sorted(list(train_log_dir.glob("*.csv")) +
                           list(train_log_dir.glob("*.tsv"))):
        action = _process_train_log_file(csv_path, dry_run=dry_run)
        report.file_actions.append(action)
    return report


# ====================================================================
# ARI map (per-sample last-epoch ARI)
# ====================================================================
def load_ari_map(train_log_dir: Path) -> dict[str, float]:
    """Return ``{sample_id: ari_at_last_epoch}`` for the ari.csv in the dir.

    Works for both long and wide format CSVs via :func:`read_metric_csv`.
    """
    ari_path = train_log_dir / "ari.csv"
    if not ari_path.exists():
        return {}
    try:
        df = read_metric_csv(ari_path, "ari")
    except Exception as exc:
        logger.warning("load_ari_map: failed to read %s: %s", ari_path, exc)
        return {}
    if df.empty or "epoch" not in df.columns:
        return {}
    df = df.sort_values("epoch")
    last_row = df.iloc[-1]
    out: dict[str, float] = {}
    for col in df.columns:
        if col == "epoch":
            continue
        try:
            v = float(last_row[col])
        except (TypeError, ValueError):
            continue
        if pd.isna(v):
            continue
        out[str(col).strip()] = v
    return out


__all__ = [
    "RESULTS_REQUIRED_COLS",
    "RESULTS_COL_ALIASES",
    "TRAIN_LOG_METRIC_COL_ALIASES",
    "FileAction",
    "NormalizeReport",
    "normalize_results_dir",
    "normalize_train_log_dir",
    "detect_csv_format",
    "read_metric_csv",
    "load_ari_map",
]
