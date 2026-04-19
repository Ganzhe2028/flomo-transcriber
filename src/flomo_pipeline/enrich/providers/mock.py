from __future__ import annotations

from pathlib import Path

from flomo_pipeline.enrich.models import ProviderResult


class MockEnrichmentProvider:
    name = "mock"
    model_name = "mock-vlm"
    prompt_version = "mock-v1"

    def enrich(self, image_path: Path, *, image_id: str, memo_id: str) -> ProviderResult:
        return ProviderResult(
            ocr_text=f"Mock OCR extracted from {image_path.name}",
            visual_description=(
                f"Mock visual description for {image_id} linked to {memo_id}."
            ),
            status="success",
            error_message=None,
        )
