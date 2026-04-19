from __future__ import annotations

from pathlib import Path
from typing import Protocol

from .models import ProviderResult


class EnrichmentProvider(Protocol):
    name: str
    model_name: str
    prompt_version: str

    def enrich(self, image_path: Path, *, image_id: str, memo_id: str) -> ProviderResult:
        ...
