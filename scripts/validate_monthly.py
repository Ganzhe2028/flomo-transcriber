#!/usr/bin/env python3

from __future__ import annotations

import argparse
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from flomo_pipeline.merge import MonthlyValidator


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate monthly/YYYY-MM.enriched.jsonl outputs")
    parser.add_argument("--store-root", type=Path, default=Path("store"), help="Path to the store root")
    parser.add_argument(
        "--monthly-root",
        type=Path,
        default=Path("monthly"),
        help="Path to the monthly output root",
    )
    parser.add_argument("--month", default=None, help="Validate only one month, e.g. 2025-12")
    parser.add_argument("--summary", action="store_true", help="Print only the summary line")
    args = parser.parse_args()

    report = MonthlyValidator(
        store_root=args.store_root.resolve(),
        monthly_root=args.monthly_root.resolve(),
        month=args.month,
    ).validate()

    if args.summary:
        print(report.format_summary())
    else:
        print(report.format_detail())

    if not report.ok:
        sys.exit(1)


if __name__ == "__main__":
    main()
