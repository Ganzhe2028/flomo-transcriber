from __future__ import annotations

import dataclasses
from typing import Literal


REPORT_BUILD_VERSION = "report-v1"
REPORT_STATUS = Literal["success", "failed"]


@dataclasses.dataclass(frozen=True)
class ReportProviderResult:
    summary_md: str
    status: REPORT_STATUS
    error_message: str | None


@dataclasses.dataclass(frozen=True)
class ReportSection:
    chunk_id: str
    chunk_index: int
    source_memo_ids: list[str]
    source_count: int
    token_estimate: int
    status: REPORT_STATUS
    summary_md: str
    error_message: str | None

    def to_dict(self) -> dict[str, object]:
        return dataclasses.asdict(self)


@dataclasses.dataclass(frozen=True)
class ReportRecord:
    report_id: str
    month: str
    source_chunk_ids: list[str]
    source_count: int
    provider_name: str
    model_name: str
    prompt_version: str
    build_version: str
    status: REPORT_STATUS
    error_message: str | None
    report_md: str
    sections: list[ReportSection]

    def to_dict(self) -> dict[str, object]:
        return {
            "report_id": self.report_id,
            "month": self.month,
            "source_chunk_ids": self.source_chunk_ids,
            "source_count": self.source_count,
            "provider_name": self.provider_name,
            "model_name": self.model_name,
            "prompt_version": self.prompt_version,
            "build_version": self.build_version,
            "status": self.status,
            "error_message": self.error_message,
            "report_md": self.report_md,
            "sections": [section.to_dict() for section in self.sections],
        }


@dataclasses.dataclass
class ReportBuildStats:
    months_built: int = 0
    months_skipped: int = 0
    reports_written: int = 0
    chunks_processed: int = 0
    sections_failed: int = 0

    def format_summary(self) -> str:
        return (
            f"Months built: {self.months_built}\n"
            f"Months skipped: {self.months_skipped}\n"
            f"Reports written: {self.reports_written}\n"
            f"Chunks processed: {self.chunks_processed}\n"
            f"Sections failed: {self.sections_failed}"
        )
