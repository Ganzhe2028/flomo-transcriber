#!/usr/bin/env python3

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from flomo_pipeline.report import ReportValidator


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate reports/YYYY-MM.report.* outputs")
    parser.add_argument(
        "--chunks-root",
        type=Path,
        default=Path("llm_chunks"),
        help="Path to the chunk input root",
    )
    parser.add_argument(
        "--reports-root",
        type=Path,
        default=Path("reports"),
        help="Path to the report output root",
    )
    parser.add_argument("--month", default=None, help="Validate only one month, e.g. 2025-12")
    parser.add_argument("--summary", action="store_true", help="Print summary only")
    args = parser.parse_args()

    report = ReportValidator(
        chunks_root=args.chunks_root.resolve(),
        reports_root=args.reports_root.resolve(),
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
