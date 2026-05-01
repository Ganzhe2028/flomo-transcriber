#!/usr/bin/env python3

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import TYPE_CHECKING

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from flomo_pipeline.enrich import ImageEnrichmentRunner
from flomo_pipeline.enrich.providers import build_provider
from flomo_pipeline.enrich.retry_config import resolve_lmstudio_retry_model_name
from flomo_pipeline.enrich.runner import MAX_FAILED_RETRIES

if TYPE_CHECKING:
    from flomo_pipeline.enrich.provider import EnrichmentProvider


def _build_retry_provider(
    provider_name: str,
    provider: EnrichmentProvider,
    args: argparse.Namespace,
) -> EnrichmentProvider | None:
    if provider_name != "lmstudio":
        return None
    if args.max_failed_retries <= 0 and not args.failed_only:
        return None

    resolution = resolve_lmstudio_retry_model_name(base_model_name=provider.model_name)
    if resolution.warning is not None:
        print(f"Warning: {resolution.warning}", file=sys.stderr)
        return provider

    retry_provider = build_provider(
        provider_name,
        model_name=resolution.model_name,
        slice_long_images=args.slice_long_images,
        force_slice_long_images=args.force_slice_long_images,
        slice_height=args.slice_height,
        slice_overlap=args.slice_overlap,
        slice_upscale=args.slice_upscale,
    )
    print(f"retry_vlm_model={retry_provider.model_name}")
    return retry_provider


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
        retry_provider = _build_retry_provider(args.provider, provider, args)
    except ValueError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)

    if args.provider == "lmstudio":
        print(f"vlm_model={provider.model_name}")

    runner_provider = (
        retry_provider if args.failed_only and retry_provider is not None else provider
    )
    _, stats = ImageEnrichmentRunner(
        store_root=store_root,
        provider=runner_provider,
        retry_provider=retry_provider,
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
