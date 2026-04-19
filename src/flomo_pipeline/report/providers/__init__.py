from __future__ import annotations

from flomo_pipeline.report.provider import ReportProvider

from .lmstudio_openai import LMStudioReportProvider
from .mock import MockReportProvider


def build_report_provider(name: str) -> ReportProvider:
    if name == "mock":
        return MockReportProvider()
    if name == "lmstudio":
        return LMStudioReportProvider()
    raise ValueError(f"Unsupported report provider: {name}")


__all__ = ["LMStudioReportProvider", "MockReportProvider", "build_report_provider"]
