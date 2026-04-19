#!/usr/bin/env python3

from __future__ import annotations

import argparse
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from flomo_pipeline.merge import MonthlyMergeRunner


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Build monthly/YYYY-MM.enriched.jsonl from memo.raw.jsonl and image.enriched.jsonl"
    )
    parser.add_argument("--store-root", type=Path, default=Path("store"), help="Path to the store root")
    parser.add_argument(
        "--monthly-root",
        type=Path,
        default=Path("monthly"),
        help="Path to the monthly output root",
    )
    parser.add_argument("--month", default=None, help="Regenerate only one month, e.g. 2025-12")
    args = parser.parse_args()

    _, stats = MonthlyMergeRunner(
        store_root=args.store_root.resolve(),
        monthly_root=args.monthly_root.resolve(),
        month=args.month,
    ).run()

    print(stats.format_summary())
    print(f"Output dir: {args.monthly_root.resolve()}")


if __name__ == "__main__":
    main()
