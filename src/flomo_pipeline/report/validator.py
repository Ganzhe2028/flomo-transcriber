from __future__ import annotations

import json
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any


CHUNK_FILE_SUFFIX = ".json"
REPORT_JSON_SUFFIX = ".report.json"
REPORT_MD_SUFFIX = ".report.md"
ALLOWED_STATUS = {"success", "failed"}
REQUIRED_REPORT_FIELDS = {
    "report_id",
    "month",
    "source_chunk_ids",
    "source_count",
    "provider_name",
    "model_name",
    "prompt_version",
    "build_version",
    "status",
    "error_message",
    "report_md",
    "sections",
}
REQUIRED_SECTION_FIELDS = {
    "chunk_id",
    "chunk_index",
    "source_memo_ids",
    "source_count",
    "token_estimate",
    "status",
    "summary_md",
    "error_message",
}


class Severity(str, Enum):
    ERROR = "error"


class Rule(str, Enum):
    R1_CHUNK_JSON_PARSEABLE = "R1"
    R2_REPORT_JSON_PARSEABLE = "R2"
    R3_REQUIRED_FIELD_MISSING = "R3"
    C1_MONTH_MATCH = "C1"
    C2_SOURCE_CHUNKS_MATCH = "C2"
    C3_SOURCE_COUNT_MATCH = "C3"
    C4_STATUS_ALLOWED = "C4"
    C5_REPORT_MD_MATCH = "C5"
    C6_SUCCESS_CONTENT_NON_EMPTY = "C6"
    C7_FAILED_ERROR_PRESENT = "C7"


@dataclass(frozen=True)
class Violation:
    rule: Rule
    severity: Severity
    message: str
    table: str
    record_id: str


@dataclass
class ValidationReport:
    violations: list[Violation] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return len(self.violations) == 0

    def add(self, violation: Violation) -> None:
        self.violations.append(violation)

    def format_summary(self) -> str:
        if self.ok:
            return "Validation passed (0 error(s))"
        return f"Validation failed: {len(self.violations)} error(s)"

    def format_detail(self) -> str:
        lines: list[str] = []
        by_table: dict[str, list[Violation]] = {}
        for violation in self.violations:
            by_table.setdefault(violation.table, []).append(violation)

        for table in sorted(by_table):
            lines.append(f"\n-- {table} --")
            for violation in by_table[table]:
                record_suffix = f" [{violation.record_id}]" if violation.record_id else ""
                lines.append(
                    f"  {violation.severity.value.upper():7} "
                    f"{violation.rule.value:3}{record_suffix}  {violation.message}"
                )

        lines.append("")
        lines.append(self.format_summary())
        return "\n".join(lines)


def _load_json(
    path: Path,
    report: ValidationReport,
    table: str,
    rule: Rule,
) -> dict[str, Any] | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        report.add(
            Violation(
                rule=rule,
                severity=Severity.ERROR,
                message=f"JSON parse error: {exc}",
                table=table,
                record_id=path.name,
            )
        )
        return None


class ReportValidator:
    def __init__(self, *, chunks_root: Path, reports_root: Path, month: str | None = None) -> None:
        self.chunks_root = chunks_root
        self.reports_root = reports_root
        self.month = month

    def validate(self) -> ValidationReport:
        report = ValidationReport()
        for month in self._discover_months():
            chunk_paths = sorted((self.chunks_root / month).glob(f"*{CHUNK_FILE_SUFFIX}"))
            chunk_ids = [
                str(chunk["chunk_id"])
                for chunk in (
                    _load_json(path, report, f"llm_chunks/{month}", Rule.R1_CHUNK_JSON_PARSEABLE)
                    for path in chunk_paths
                )
                if chunk is not None
            ]

            report_path = self.reports_root / f"{month}{REPORT_JSON_SUFFIX}"
            md_path = self.reports_root / f"{month}{REPORT_MD_SUFFIX}"
            if not report_path.exists():
                report.add(
                    Violation(
                        rule=Rule.R2_REPORT_JSON_PARSEABLE,
                        severity=Severity.ERROR,
                        message=f"File not found: {report_path}",
                        table="reports",
                        record_id=month,
                    )
                )
                continue

            record = _load_json(report_path, report, "reports", Rule.R2_REPORT_JSON_PARSEABLE)
            if record is None:
                continue

            self._validate_report_record(
                record=record,
                month=month,
                chunk_ids=chunk_ids,
                md_path=md_path,
                report=report,
            )

        return report

    def _discover_months(self) -> list[str]:
        if self.month is not None:
            return [self.month]
        if not self.chunks_root.exists():
            return []
        return sorted(path.name for path in self.chunks_root.iterdir() if path.is_dir())

    @staticmethod
    def _validate_report_record(
        *,
        record: dict[str, Any],
        month: str,
        chunk_ids: list[str],
        md_path: Path,
        report: ValidationReport,
    ) -> None:
        report_id = str(record.get("report_id", ""))
        missing_fields = REQUIRED_REPORT_FIELDS - record.keys()
        if missing_fields:
            report.add(
                Violation(
                    rule=Rule.R3_REQUIRED_FIELD_MISSING,
                    severity=Severity.ERROR,
                    message=f"Missing required field(s): {', '.join(sorted(missing_fields))}",
                    table="reports",
                    record_id=report_id or month,
                )
            )
            return

        if record.get("month") != month:
            report.add(
                Violation(
                    rule=Rule.C1_MONTH_MATCH,
                    severity=Severity.ERROR,
                    message="Report month does not match source chunk directory",
                    table="reports",
                    record_id=report_id,
                )
            )

        source_chunk_ids = record.get("source_chunk_ids")
        if source_chunk_ids != chunk_ids:
            report.add(
                Violation(
                    rule=Rule.C2_SOURCE_CHUNKS_MATCH,
                    severity=Severity.ERROR,
                    message="Report source_chunk_ids do not match chunk files",
                    table="reports",
                    record_id=report_id,
                )
            )

        if record.get("source_count") != len(chunk_ids):
            report.add(
                Violation(
                    rule=Rule.C3_SOURCE_COUNT_MATCH,
                    severity=Severity.ERROR,
                    message="source_count must equal number of source_chunk_ids",
                    table="reports",
                    record_id=report_id,
                )
            )

        status = record.get("status")
        if status not in ALLOWED_STATUS:
            report.add(
                Violation(
                    rule=Rule.C4_STATUS_ALLOWED,
                    severity=Severity.ERROR,
                    message=f"Invalid report status: {status}",
                    table="reports",
                    record_id=report_id,
                )
            )
        elif status == "success" and not str(record.get("report_md") or "").strip():
            report.add(
                Violation(
                    rule=Rule.C6_SUCCESS_CONTENT_NON_EMPTY,
                    severity=Severity.ERROR,
                    message="successful report must include non-empty report_md",
                    table="reports",
                    record_id=report_id,
                )
            )
        elif status == "failed" and not str(record.get("error_message") or "").strip():
            report.add(
                Violation(
                    rule=Rule.C7_FAILED_ERROR_PRESENT,
                    severity=Severity.ERROR,
                    message="failed report must include error_message",
                    table="reports",
                    record_id=report_id,
                )
            )

        if not md_path.exists():
            report.add(
                Violation(
                    rule=Rule.C5_REPORT_MD_MATCH,
                    severity=Severity.ERROR,
                    message=f"Markdown report not found: {md_path}",
                    table="reports",
                    record_id=report_id,
                )
            )
        elif md_path.read_text(encoding="utf-8").strip() != str(record["report_md"]).strip():
            report.add(
                Violation(
                    rule=Rule.C5_REPORT_MD_MATCH,
                    severity=Severity.ERROR,
                    message="Markdown report content does not match report_md",
                    table="reports",
                    record_id=report_id,
                )
            )

        sections = record.get("sections")
        if not isinstance(sections, list):
            report.add(
                Violation(
                    rule=Rule.R3_REQUIRED_FIELD_MISSING,
                    severity=Severity.ERROR,
                    message="sections must be an array",
                    table="reports",
                    record_id=report_id,
                )
            )
            return

        section_chunk_ids: list[str] = []
        for section in sections:
            if not isinstance(section, dict):
                continue
            section_chunk_id = str(section.get("chunk_id", ""))
            section_chunk_ids.append(section_chunk_id)
            missing_section_fields = REQUIRED_SECTION_FIELDS - section.keys()
            if missing_section_fields:
                report.add(
                    Violation(
                        rule=Rule.R3_REQUIRED_FIELD_MISSING,
                        severity=Severity.ERROR,
                        message=(
                            "Missing section field(s): "
                            f"{', '.join(sorted(missing_section_fields))}"
                        ),
                        table="reports",
                        record_id=section_chunk_id or report_id,
                    )
                )
                continue

            section_status = section.get("status")
            if section_status not in ALLOWED_STATUS:
                report.add(
                    Violation(
                        rule=Rule.C4_STATUS_ALLOWED,
                        severity=Severity.ERROR,
                        message=f"Invalid section status: {section_status}",
                        table="reports",
                        record_id=section_chunk_id,
                    )
                )
            elif section_status == "success" and not str(section.get("summary_md") or "").strip():
                report.add(
                    Violation(
                        rule=Rule.C6_SUCCESS_CONTENT_NON_EMPTY,
                        severity=Severity.ERROR,
                        message="successful section must include non-empty summary_md",
                        table="reports",
                        record_id=section_chunk_id,
                    )
                )
            elif section_status == "failed" and not str(section.get("error_message") or "").strip():
                report.add(
                    Violation(
                        rule=Rule.C7_FAILED_ERROR_PRESENT,
                        severity=Severity.ERROR,
                        message="failed section must include error_message",
                        table="reports",
                        record_id=section_chunk_id,
                    )
                )

        if section_chunk_ids != chunk_ids:
            report.add(
                Violation(
                    rule=Rule.C2_SOURCE_CHUNKS_MATCH,
                    severity=Severity.ERROR,
                    message="Section chunk ids do not match source chunk files",
                    table="reports",
                    record_id=report_id,
                )
            )
