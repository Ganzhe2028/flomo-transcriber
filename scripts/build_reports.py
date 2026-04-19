#!/usr/bin/env python3

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from flomo_pipeline.report import ReportBuildRunner
from flomo_pipeline.report.providers import build_report_provider


def main() -> None:
    parser = argparse.ArgumentParser(description="Build reports from llm_chunks/YYYY-MM/*.json")
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
    parser.add_argument("--provider", default="mock", help="Report provider name")
    parser.add_argument("--month", default=None, help="Build only one month, e.g. 2025-12")
    parser.add_argument("--overwrite", action="store_true", help="Overwrite existing reports")
    args = parser.parse_args()

    try:
        provider = build_report_provider(args.provider)
    except ValueError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)

    _, stats = ReportBuildRunner(
        chunks_root=args.chunks_root.resolve(),
        reports_root=args.reports_root.resolve(),
        provider=provider,
        month=args.month,
        overwrite=args.overwrite,
    ).run()

    print(stats.format_summary())
    print(f"Output dir: {args.reports_root.resolve()}")


if __name__ == "__main__":
    main()
