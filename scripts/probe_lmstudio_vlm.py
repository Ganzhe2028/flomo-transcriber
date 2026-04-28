#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from flomo_pipeline.enrich.providers.lmstudio_openai import LMStudioEnrichmentProvider


def main() -> None:
    parser = argparse.ArgumentParser(description="Probe LM Studio VLM enrichment for one image")
    parser.add_argument("--image", type=Path, required=True, help="Path to one local image")
    parser.add_argument("--image-id", default="probe-image", help="Probe image_id")
    parser.add_argument("--memo-id", default="probe-memo", help="Probe memo_id")
    parser.add_argument(
        "--slice-long-images",
        action="store_true",
        default=None,
        help="Retry a failed long image as vertical clips",
    )
    parser.add_argument(
        "--force-slice-long-images",
        action="store_true",
        default=None,
        help="Skip whole-image recognition for images taller than slice height",
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

    provider = LMStudioEnrichmentProvider(
        slice_long_images=args.slice_long_images,
        force_slice_long_images=args.force_slice_long_images,
        slice_height=args.slice_height,
        slice_overlap=args.slice_overlap,
        slice_upscale=args.slice_upscale,
    )
    call = provider.enrich_with_response(
        args.image.resolve(),
        image_id=args.image_id,
        memo_id=args.memo_id,
    )

    print(f"Status: {call.result.status}")
    print(f"Base URL: {provider.base_url or '(unset)'}")
    print(f"Model: {provider.model_name}")
    print(f"Prompt version: {provider.prompt_version}")
    print(f"Slice long images: {provider.slice_long_images}")
    print(f"Force slice long images: {provider.force_slice_long_images}")
    print(f"Slice height: {provider.slice_height}")
    print(f"Slice overlap: {provider.slice_overlap}")
    print(f"Slice upscale: {provider.slice_upscale}")
    print(f"OCR text: {call.result.ocr_text}")
    print(f"Visual description: {call.result.visual_description}")
    print(f"Error: {call.result.error_message or ''}")

    if call.raw_response is not None:
        print("Raw response:")
        print(json.dumps(call.raw_response, ensure_ascii=False, indent=2))

    if call.result.status != "success":
        sys.exit(1)


if __name__ == "__main__":
    main()
