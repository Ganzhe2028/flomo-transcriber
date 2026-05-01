from __future__ import annotations

import json
from typing import TYPE_CHECKING

from flomo_pipeline.report import ReportBuildRunner, ReportValidator
from flomo_pipeline.report.models import ReportProviderResult
from flomo_pipeline.report.providers import MockReportProvider
from flomo_pipeline.report.providers.lmstudio_openai import LMStudioReportProvider
from tests.conftest import FakeHTTPResponse, lmstudio_chat_response, run_fake_lmstudio_server

if TYPE_CHECKING:
    from pathlib import Path


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _chunk(chunk_id: str, chunk_index: int) -> dict:
    return {
        "chunk_id": chunk_id,
        "month": "2026-03",
        "chunk_index": chunk_index,
        "source_memo_ids": [f"memo-{chunk_index}"],
        "source_count": 1,
        "created_at_range": {
            "start": "2026-03-04T10:00:00",
            "end": "2026-03-04T10:00:00",
        },
        "token_estimate": 100,
        "text": f"[MEMO]\nmemo_id: memo-{chunk_index}\nmemo_text:\nhello",
        "source_items": [],
        "build_version": "chunk-v1",
        "strategy": "sequential-size-pack:v1",
        "status": "success",
    }


def _setup_chunks(tmp_path: Path) -> tuple[Path, Path]:
    chunks_root = tmp_path / "llm_chunks"
    reports_root = tmp_path / "reports"
    _write_json(chunks_root / "2026-03" / "2026-03-0001.json", _chunk("2026-03-0001", 1))
    _write_json(chunks_root / "2026-03" / "2026-03-0002.json", _chunk("2026-03-0002", 2))
    return chunks_root, reports_root


class FailingReportProvider:
    name = "failing"
    model_name = "failing-llm"
    prompt_version = "failing-v1"

    def summarize_chunk(self, chunk: dict) -> ReportProviderResult:
        return ReportProviderResult(
            summary_md="",
            status="failed",
            error_message=f"failed {chunk['chunk_id']}",
        )


def test_report_runner_builds_markdown_and_json(tmp_path: Path) -> None:
    chunks_root, reports_root = _setup_chunks(tmp_path)

    reports, stats = ReportBuildRunner(
        chunks_root=chunks_root,
        reports_root=reports_root,
        provider=MockReportProvider(),
        month="2026-03",
        overwrite=True,
    ).run()

    report = reports["2026-03"]
    assert report.status == "success"
    assert report.source_chunk_ids == ["2026-03-0001", "2026-03-0002"]
    assert "2026-03-0001" in report.report_md
    assert (reports_root / "2026-03.report.json").exists()
    assert (reports_root / "2026-03.report.md").exists()
    assert stats.reports_written == 1
    assert stats.chunks_processed == 2


def test_report_runner_skips_existing_without_overwrite(tmp_path: Path) -> None:
    chunks_root, reports_root = _setup_chunks(tmp_path)
    existing = reports_root / "2026-03.report.md"
    existing.parent.mkdir(parents=True, exist_ok=True)
    existing.write_text("keep me\n", encoding="utf-8")

    _, stats = ReportBuildRunner(
        chunks_root=chunks_root,
        reports_root=reports_root,
        provider=MockReportProvider(),
        month="2026-03",
        overwrite=False,
    ).run()

    assert stats.months_skipped == 1
    assert existing.read_text(encoding="utf-8") == "keep me\n"


def test_report_validator_passes_generated_report(tmp_path: Path) -> None:
    chunks_root, reports_root = _setup_chunks(tmp_path)
    ReportBuildRunner(
        chunks_root=chunks_root,
        reports_root=reports_root,
        provider=MockReportProvider(),
        month="2026-03",
        overwrite=True,
    ).run()

    report = ReportValidator(
        chunks_root=chunks_root,
        reports_root=reports_root,
        month="2026-03",
    ).validate()

    assert report.ok, report.format_detail()


def test_report_validator_catches_missing_source_chunk(tmp_path: Path) -> None:
    chunks_root, reports_root = _setup_chunks(tmp_path)
    ReportBuildRunner(
        chunks_root=chunks_root,
        reports_root=reports_root,
        provider=MockReportProvider(),
        month="2026-03",
        overwrite=True,
    ).run()

    payload = json.loads((reports_root / "2026-03.report.json").read_text(encoding="utf-8"))
    payload["source_chunk_ids"] = ["missing"]
    _write_json(reports_root / "2026-03.report.json", payload)

    report = ReportValidator(
        chunks_root=chunks_root,
        reports_root=reports_root,
        month="2026-03",
    ).validate()

    assert not report.ok
    assert "source_chunk_ids do not match" in report.format_detail()


def test_lmstudio_report_provider_success(tmp_path: Path) -> None:
    chunk = _chunk("2026-03-0001", 1)

    with run_fake_lmstudio_server(
        [FakeHTTPResponse(status=200, body=lmstudio_chat_response("## Summary\n\n- item"))]
    ) as server:
        provider = LMStudioReportProvider(
            base_url=server.url,
            model_name="local-llm",
            timeout_seconds=2,
        )
        result = provider.summarize_chunk(chunk)

    assert result.status == "success"
    assert "Summary" in result.summary_md
    assert server.requests[0]["model"] == "local-llm"
    assert server.requests[0]["stream"] is False


def test_report_runner_preserves_failed_sections(tmp_path: Path) -> None:
    chunks_root, reports_root = _setup_chunks(tmp_path)

    reports, stats = ReportBuildRunner(
        chunks_root=chunks_root,
        reports_root=reports_root,
        provider=FailingReportProvider(),
        month="2026-03",
        overwrite=True,
    ).run()

    report = reports["2026-03"]
    assert report.status == "failed"
    assert stats.sections_failed == 2
    assert all(section.error_message for section in report.sections)
