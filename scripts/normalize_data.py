# coding: utf-8
"""CLI: normalize Results and train_log CSVs in a dataset folder.

Usage
-----
    python scripts/normalize_data.py <path> [--apply] [--results-only] [--train-log-only]

* Without ``--apply``: only prints a dry-run report (no files are modified).
* With ``--apply``: writes back changes; ``.bak`` backups are created for any
  train_log CSV that is converted long -> wide.

The path can be:

* a ``main_file`` root (containing ``Results/`` and ``train_log/``)
* a single ``Results`` directory
* a single ``train_log`` directory
* a single CSV/TSV file

Examples
--------
    # Inspect only
    python scripts/normalize_data.py "E:/data/main_file"

    # Apply normalization
    python scripts/normalize_data.py "E:/data/main_file" --apply
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path


def _bootstrap_path() -> None:
    """Ensure the project's `front` package is importable when run as a script."""
    project_root = Path(__file__).resolve().parent.parent
    front_dir = project_root / "front"
    if str(front_dir) not in sys.path:
        sys.path.insert(0, str(front_dir))


_bootstrap_path()

from model.data_normalizer import (  # noqa: E402
    NormalizeReport,
    normalize_results_dir,
    normalize_train_log_dir,
)


_GT_NAMES = {"ground_truth", "groundtruth", "gt", "ground-truth"}
_RESULT_NAMES = {"results", "result", "predictions", "prediction", "pred", "preds"}
_TRAIN_LOG_NAMES = {
    "train_log", "trainlog", "train-log", "training_log", "traininglog", "logs", "log",
}


def _norm(s: str) -> str:
    return s.lower().replace("-", "_").replace(" ", "_")


def _resolve_targets(
    path: Path,
) -> tuple[list[Path], list[Path]]:
    """Return (results_dirs, train_log_dirs) discovered under ``path``."""
    results_dirs: list[Path] = []
    train_log_dirs: list[Path] = []

    if path.is_file():
        # Single file: nothing to infer - caller should use the per-file path
        return [], []

    if not path.exists() or not path.is_dir():
        return [], []

    # Direct children: detect by name
    for child in path.iterdir():
        if not child.is_dir():
            continue
        n = _norm(child.name)
        if n in _RESULT_NAMES:
            results_dirs.append(child)
        elif n in _TRAIN_LOG_NAMES:
            train_log_dirs.append(child)

    # If the path itself is a Results/ or train_log/ directory
    if _norm(path.name) in _RESULT_NAMES:
        results_dirs.append(path)
    if _norm(path.name) in _TRAIN_LOG_NAMES:
        train_log_dirs.append(path)

    # Deduplicate while preserving order
    seen: set[Path] = set()
    deduped_results: list[Path] = []
    for d in results_dirs:
        if d in seen:
            continue
        seen.add(d)
        deduped_results.append(d)

    seen.clear()
    deduped_logs: list[Path] = []
    for d in train_log_dirs:
        if d in seen:
            continue
        seen.add(d)
        deduped_logs.append(d)

    return deduped_results, deduped_logs


def _merge_reports(reports: list[NormalizeReport]) -> NormalizeReport:
    """Combine several reports into one for unified display."""
    if len(reports) == 1:
        return reports[0]
    root = reports[0].target
    merged = NormalizeReport(target=root)
    for r in reports:
        merged.file_actions.extend(r.file_actions)
    return merged


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Normalize Results and train_log CSVs in a dataset folder.",
    )
    parser.add_argument(
        "path",
        help="Path to a main_file root, Results dir, train_log dir, or a single CSV/TSV file.",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Actually write changes. Without this flag, only a dry-run report is printed.",
    )
    parser.add_argument(
        "--results-only", action="store_true",
        help="Only process Results directories.",
    )
    parser.add_argument(
        "--train-log-only", action="store_true",
        help="Only process train_log directories.",
    )
    args = parser.parse_args()

    target = Path(args.path).resolve()
    if not target.exists():
        print(f"Error: path not found: {target}", file=sys.stderr)
        return 1

    dry_run = not args.apply

    # ---- Single CSV/TSV file ----
    if target.is_file():
        print(f"Single file mode: {target}")
        print("(File-level normalization is performed by normalize_results_dir "
              "when the parent is a spatial/ folder. For one-off inspection, "
              "use --results-only/--train-log-only on the parent directory.)")
        return 0

    results_dirs, train_log_dirs = _resolve_targets(target)

    if not results_dirs and not train_log_dirs:
        print(f"No Results/ or train_log/ directories found under: {target}")
        return 0

    if args.results_only and args.train_log_only:
        print("Cannot specify both --results-only and --train-log-only.")
        return 2

    all_reports: list[NormalizeReport] = []

    if not args.train_log_only:
        for d in results_dirs:
            print(f"\n[Results] Scanning: {d}")
            r = normalize_results_dir(d, dry_run=dry_run)
            all_reports.append(r)

    if not args.results_only:
        for d in train_log_dirs:
            print(f"\n[train_log] Scanning: {d}")
            r = normalize_train_log_dir(d, dry_run=dry_run)
            all_reports.append(r)

    # ---- Print unified report ----
    if all_reports:
        print("\n" + "=" * 60)
        print(f"Mode: {'DRY-RUN' if dry_run else 'APPLY'}")
        if len(all_reports) == 1:
            print(all_reports[0].summary())
        else:
            for r in all_reports:
                print()
                print(r.summary())
        print("=" * 60)

    return 0


if __name__ == "__main__":
    sys.exit(main())
