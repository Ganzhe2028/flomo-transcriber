from __future__ import annotations

from typing import TYPE_CHECKING

from .lmstudio_openai import LMStudioEnrichmentProvider
from .mock import MockEnrichmentProvider

if TYPE_CHECKING:
    from flomo_pipeline.enrich.provider import EnrichmentProvider


def build_provider(
    name: str,
    *,
    model_name: str | None = None,
    slice_long_images: bool | None = None,
    force_slice_long_images: bool | None = None,
    slice_height: int | None = None,
    slice_overlap: int | None = None,
    slice_upscale: float | None = None,
) -> EnrichmentProvider:
    if name == "mock":
        return MockEnrichmentProvider()
    if name == "lmstudio":
        return LMStudioEnrichmentProvider(
            model_name=model_name,
            slice_long_images=slice_long_images,
            force_slice_long_images=force_slice_long_images,
            slice_height=slice_height,
            slice_overlap=slice_overlap,
            slice_upscale=slice_upscale,
        )
    raise ValueError(f"Unsupported provider: {name}")


__all__ = ["LMStudioEnrichmentProvider", "MockEnrichmentProvider", "build_provider"]
