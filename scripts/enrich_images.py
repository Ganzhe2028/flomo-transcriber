#!/usr/bin/env python3

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from flomo_pipeline.enrich import ImageEnrichmentRunner
from flomo_pipeline.enrich.providers import build_provider
from flomo_pipeline.enrich.runner import MAX_FAILED_RETRIES


def main() -> None:
    parser = argparse.ArgumentParser(description="Build image.enriched.jsonl from image.raw.jsonl")
    parser.add_argument(
        "--store-root",
        type=Path,
        default=Path("store"),
        help="Path to the store root",
    )
    parser.add_argument("--provider", default="mock", help="Enrichment provider name")
    parser.add_argument("--month", default=None, help="Process only one month, e.g. 2026-01")
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Reprocess existing successful image_id records",
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=1,
        help="Number of images to process concurrently",
    )
    parser.add_argument(
        "--failed-only",
        action="store_true",
        help="Process only existing failed image records",
    )
    parser.add_argument(
        "--max-failed-retries",
        type=int,
        default=MAX_FAILED_RETRIES,
        help="Retry failed records inside this run",
    )
    parser.add_argument(
        "--slice-long-images",
        action="store_true",
        default=None,
        help="For LM Studio, retry failed long images as vertical clips",
    )
    parser.add_argument(
        "--force-slice-long-images",
        action="store_true",
        default=None,
        help="For LM Studio, skip whole-image recognition for images taller than slice height",
    )
    parser.add_argument(
        "--slice-height",
        type=int,
        default=None,
        help="Clip height in pixels for long-image slicing; default is 500",
    )
    parser.add_argument(
        "--slice-overlap",
        type=int,
        default=None,
        help="Vertical overlap in pixels between clips; default is 60",
    )
    parser.add_argument(
        "--slice-upscale",
        type=float,
        default=None,
        help="Upscale factor applied to each clip before recognition; default is 2",
    )
    args = parser.parse_args()

    store_root = args.store_root.resolve()

    try:
        provider = build_provider(
            args.provider,
            slice_long_images=args.slice_long_images,
            force_slice_long_images=args.force_slice_long_images,
            slice_height=args.slice_height,
            slice_overlap=args.slice_overlap,
            slice_upscale=args.slice_upscale,
        )
    except ValueError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)

    _, stats = ImageEnrichmentRunner(
        store_root=store_root,
        provider=provider,
        month=args.month,
        overwrite=args.overwrite,
        workers=args.workers,
        max_failed_retries=args.max_failed_retries,
        failed_only=args.failed_only,
    ).run()

    print(stats.format_summary())
    print(f"Output: {store_root / 'image.enriched.jsonl'}")


if __name__ == "__main__":
    main()
