from __future__ import annotations

from typing import Any, Protocol

from flomo_pipeline.report.models import ReportProviderResult


class ReportProvider(Protocol):
    name: str
    model_name: str
    prompt_version: str

    def summarize_chunk(self, chunk: dict[str, Any]) -> ReportProviderResult:
        ...
