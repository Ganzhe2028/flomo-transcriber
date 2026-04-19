#!/usr/bin/env python3

from __future__ import annotations

import argparse
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from flomo_pipeline.chunk import ChunkValidator


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate llm_chunks/YYYY-MM/*.json outputs")
    parser.add_argument(
        "--monthly-root",
        type=Path,
        default=Path("monthly"),
        help="Path to the monthly input root",
    )
    parser.add_argument(
        "--chunks-root",
        type=Path,
        default=Path("llm_chunks"),
        help="Path to the chunk output root",
    )
    parser.add_argument("--month", default=None, help="Validate only one month, e.g. 2025-12")
    parser.add_argument("--summary", action="store_true", help="Print only the summary line")
    args = parser.parse_args()

    report = ChunkValidator(
        monthly_root=args.monthly_root.resolve(),
        chunks_root=args.chunks_root.resolve(),
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
