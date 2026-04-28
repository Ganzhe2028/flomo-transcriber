from __future__ import annotations

from typing import TYPE_CHECKING, Any

from flomo_pipeline.common.io import read_json, write_json, write_text
from flomo_pipeline.report.models import (
    REPORT_BUILD_VERSION,
    REPORT_STATUS,
    ReportBuildStats,
    ReportRecord,
    ReportSection,
)

if TYPE_CHECKING:
    from pathlib import Path

    from flomo_pipeline.report.provider import ReportProvider

CHUNK_FILE_SUFFIX = ".json"
REPORT_JSON_SUFFIX = ".report.json"
REPORT_MD_SUFFIX = ".report.md"


class ReportBuildRunner:
    def __init__(
        self,
        *,
        chunks_root: Path,
        reports_root: Path,
        provider: ReportProvider,
        month: str | None = None,
        overwrite: bool = False,
    ) -> None:
        self.chunks_root = chunks_root
        self.reports_root = reports_root
        self.provider = provider
        self.month = month
        self.overwrite = overwrite

    def run(self) -> tuple[dict[str, ReportRecord], ReportBuildStats]:
        reports: dict[str, ReportRecord] = {}
        stats = ReportBuildStats()

        for month, chunk_paths in self._discover_chunk_inputs():
            json_path = self.reports_root / f"{month}{REPORT_JSON_SUFFIX}"
            md_path = self.reports_root / f"{month}{REPORT_MD_SUFFIX}"
            if (json_path.exists() or md_path.exists()) and not self.overwrite:
                stats.months_skipped += 1
                print(f"[{month}] skipped (existing report)")
                continue

            chunks = [read_json(path) for path in chunk_paths]
            report = self._build_month_report(month=month, chunks=chunks)
            reports[month] = report
            stats.months_built += 1
            stats.reports_written += 1
            stats.chunks_processed += len(chunks)
            stats.sections_failed += sum(
                1 for section in report.sections if section.status == "failed"
            )

            write_json(json_path, report.to_dict())
            write_text(md_path, report.report_md)
            print(f"[{month}] built report from {len(chunks)} chunks")

        return reports, stats

    def _discover_chunk_inputs(self) -> list[tuple[str, list[Path]]]:
        if self.month is not None:
            chunk_dir = self.chunks_root / self.month
            if not chunk_dir.exists():
                return []
            return [(self.month, sorted(chunk_dir.glob(f"*{CHUNK_FILE_SUFFIX}")))]

        pairs: list[tuple[str, list[Path]]] = []
        if not self.chunks_root.exists():
            return pairs
        for chunk_dir in sorted(path for path in self.chunks_root.iterdir() if path.is_dir()):
            pairs.append((chunk_dir.name, sorted(chunk_dir.glob(f"*{CHUNK_FILE_SUFFIX}"))))
        return pairs

    def _build_month_report(self, *, month: str, chunks: list[dict[str, Any]]) -> ReportRecord:
        sections: list[ReportSection] = []
        for chunk in chunks:
            result = self.provider.summarize_chunk(chunk)
            sections.append(
                ReportSection(
                    chunk_id=str(chunk["chunk_id"]),
                    chunk_index=int(chunk["chunk_index"]),
                    source_memo_ids=[str(memo_id) for memo_id in chunk["source_memo_ids"]],
                    source_count=int(chunk["source_count"]),
                    token_estimate=int(chunk["token_estimate"]),
                    status=result.status,
                    summary_md=result.summary_md,
                    error_message=result.error_message,
                )
            )

        failed_sections = [section for section in sections if section.status == "failed"]
        status: REPORT_STATUS = "failed" if failed_sections else "success"
        error_message = (
            f"{len(failed_sections)} chunk summary section(s) failed"
            if failed_sections
            else None
        )
        report_md = self._render_report_md(month=month, sections=sections, status=status)

        return ReportRecord(
            report_id=f"{month}-report",
            month=month,
            source_chunk_ids=[section.chunk_id for section in sections],
            source_count=len(sections),
            provider_name=self.provider.name,
            model_name=self.provider.model_name,
            prompt_version=self.provider.prompt_version,
            build_version=REPORT_BUILD_VERSION,
            status=status,
            error_message=error_message,
            report_md=report_md,
            sections=sections,
        )

    @staticmethod
    def _render_report_md(
        *,
        month: str,
        sections: list[ReportSection],
        status: str,
    ) -> str:
        lines = [
            f"# Flomo 月度报告：{month}",
            "",
            f"- status: {status}",
            f"- source_chunks: {len(sections)}",
            "",
            "## Chunk Summaries",
        ]
        for section in sections:
            lines.extend(["", f"## {section.chunk_id}"])
            if section.status == "failed":
                lines.extend(
                    [
                        "",
                        "- status: failed",
                        f"- error: {section.error_message or 'unknown error'}",
                    ]
                )
            else:
                lines.extend(["", section.summary_md.strip()])
        return "\n".join(lines).strip()
