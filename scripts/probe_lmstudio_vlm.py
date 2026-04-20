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
    args = parser.parse_args()

    provider = LMStudioEnrichmentProvider()
    call = provider.enrich_with_response(
        args.image.resolve(),
        image_id=args.image_id,
        memo_id=args.memo_id,
    )

    print(f"Status: {call.result.status}")
    print(f"Base URL: {provider.base_url or '(unset)'}")
    print(f"Model: {provider.model_name}")
    print(f"Prompt version: {provider.prompt_version}")
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
