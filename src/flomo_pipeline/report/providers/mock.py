from __future__ import annotations

from typing import Any

from flomo_pipeline.report.models import ReportProviderResult


class MockReportProvider:
    name = "mock"
    model_name = "mock-llm"
    prompt_version = "mock-report-v1"

    def summarize_chunk(self, chunk: dict[str, Any]) -> ReportProviderResult:
        chunk_id = str(chunk["chunk_id"])
        source_count = int(chunk["source_count"])
        memo_ids = ", ".join(str(memo_id) for memo_id in chunk["source_memo_ids"])
        summary = (
            f"### {chunk_id}\n\n"
            f"- Source memos: {source_count}\n"
            f"- Memo ids: {memo_ids}\n"
            "- Summary: mock report section generated from chunk metadata."
        )
        return ReportProviderResult(summary_md=summary, status="success", error_message=None)
