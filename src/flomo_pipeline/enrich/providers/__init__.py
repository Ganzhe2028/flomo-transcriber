from __future__ import annotations

from flomo_pipeline.enrich.provider import EnrichmentProvider

from .lmstudio_openai import LMStudioEnrichmentProvider
from .mock import MockEnrichmentProvider


def build_provider(name: str) -> EnrichmentProvider:
    if name == "mock":
        return MockEnrichmentProvider()
    if name == "lmstudio":
        return LMStudioEnrichmentProvider()
    raise ValueError(f"Unsupported provider: {name}")


__all__ = ["LMStudioEnrichmentProvider", "MockEnrichmentProvider", "build_provider"]
