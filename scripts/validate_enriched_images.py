#!/usr/bin/env python3

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from flomo_pipeline.enrich import EnrichedImageValidator


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate image.enriched.jsonl against image.raw.jsonl")
    parser.add_argument("--store-root", type=Path, default=Path("store"), help="Path to the store root")
    parser.add_argument("--summary", action="store_true", help="Print only the summary line")
    args = parser.parse_args()

    report = EnrichedImageValidator(store_root=args.store_root.resolve()).validate()

    if args.summary:
        print(report.format_summary())
    else:
        print(report.format_detail())

    if not report.ok:
        sys.exit(1)


if __name__ == "__main__":
    main()
