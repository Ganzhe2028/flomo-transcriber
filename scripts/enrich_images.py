#!/usr/bin/env python3

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from flomo_pipeline.enrich import ImageEnrichmentRunner
from flomo_pipeline.enrich.providers import build_provider


def main() -> None:
    parser = argparse.ArgumentParser(description="Build image.enriched.jsonl from image.raw.jsonl")
    parser.add_argument("--store-root", type=Path, default=Path("store"), help="Path to the store root")
    parser.add_argument("--provider", default="mock", help="Enrichment provider name")
    parser.add_argument("--month", default=None, help="Process only one month, e.g. 2026-01")
    parser.add_argument("--overwrite", action="store_true", help="Reprocess existing successful image_id records")
    args = parser.parse_args()

    store_root = args.store_root.resolve()

    try:
        provider = build_provider(args.provider)
    except ValueError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)

    _, stats = ImageEnrichmentRunner(
        store_root=store_root,
        provider=provider,
        month=args.month,
        overwrite=args.overwrite,
    ).run()

    print(stats.format_summary())
    print(f"Output: {store_root / 'image.enriched.jsonl'}")


if __name__ == "__main__":
    main()
