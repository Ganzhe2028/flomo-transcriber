"""Validation for the Stage 1 raw truth layer."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path


class Severity(str, Enum):
    ERROR = "error"
    WARNING = "warning"


class Rule(str, Enum):
    C1_MEMO_ID_UNIQUE = "C1"
    C2_IMAGE_ID_UNIQUE = "C2"
    C3_IMAGE_COUNT_CONSISTENT = "C3"
    C4_IMAGE_MEMO_ID_EXISTS = "C4"
    C5_MISSING_IMAGE_MEMO_ID_EXISTS = "C5"
    C6_IMAGE_ID_NO_CROSS = "C6"
    C7_PATH_RELATIVE = "C7"
    C8_IMAGE_FILE_EXISTS = "C8"
    C9_SOURCE_FILE_EXPECTATION = "C9"
    C10_CREATED_AT_ISO = "C10"
    C11_NO_FRONTMATTER = "C11"
    R1_MEMO_JSONL_PARSEABLE = "R1"
    R2_IMAGE_JSONL_PARSEABLE = "R2"
    R3_MISSING_IMAGE_JSONL_PARSEABLE = "R3"
    R4_EMPTY_KEY_FIELD = "R4"
    R5_MISSING_REQUIRED_FIELD = "R5"


MEMO_FIELDS = {
    "memo_id",
    "created_at",
    "body_md",
    "image_count",
    "source_relpath",
    "batch_label",
    "ordinal",
}
IMAGE_FIELDS = {"image_id", "memo_id", "image_relpath", "source_relpath", "ordinal"}
MISSING_FIELDS = {"image_id", "memo_id", "source_relpath", "ordinal", "reason"}

MEMO_KEY_FIELDS = {"memo_id", "created_at", "body_md", "source_relpath", "batch_label"}
IMAGE_KEY_FIELDS = {"image_id", "memo_id", "image_relpath", "source_relpath"}
MISSING_KEY_FIELDS = {"image_id", "memo_id", "source_relpath", "reason"}

MEMO_PATH_FIELDS = {"source_relpath"}
IMAGE_PATH_FIELDS = {"image_relpath", "source_relpath"}
MISSING_PATH_FIELDS = {"source_relpath"}

ISO8601_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}$")


@dataclass(frozen=True)
class Violation:
    rule: Rule
    severity: Severity
    message: str
    table: str
    line: int
    record_id: str


@dataclass
class ValidationReport:
    violations: list[Violation] = field(default_factory=list)

    @property
    def errors(self) -> list[Violation]:
        return [violation for violation in self.violations if violation.severity == Severity.ERROR]

    @property
    def warnings(self) -> list[Violation]:
        return [violation for violation in self.violations if violation.severity == Severity.WARNING]

    @property
    def ok(self) -> bool:
        return not self.errors

    def add(self, violation: Violation) -> None:
        self.violations.append(violation)

    def format_summary(self) -> str:
        error_count = len(self.errors)
        warning_count = len(self.warnings)
        if self.ok:
            return f"Validation passed ({warning_count} warning(s))"
        return f"Validation failed: {error_count} error(s), {warning_count} warning(s)"

    def format_detail(self) -> str:
        lines: list[str] = []
        by_table: dict[str, list[Violation]] = {}
        for violation in self.violations:
            by_table.setdefault(violation.table, []).append(violation)

        for table in ("memo.raw", "image.raw", "missing_image.raw", "cross-table"):
            table_violations = by_table.get(table)
            if not table_violations:
                continue
            lines.append(f"\n-- {table} --")
            for violation in sorted(table_violations, key=lambda item: (item.line, item.rule.value)):
                location = f"line {violation.line}" if violation.line > 0 else "global"
                record_suffix = f" [{violation.record_id}]" if violation.record_id else ""
                lines.append(
                    f"  {violation.severity.value.upper():7} {violation.rule.value:3} "
                    f"{location:>10}{record_suffix}  {violation.message}"
                )

        lines.append("")
        lines.append(self.format_summary())
        return "\n".join(lines)


def _load_jsonl(path: Path, table_name: str, report: ValidationReport, rule: Rule) -> list[dict]:
    records: list[dict] = []
    if not path.exists():
        report.add(
            Violation(
                rule=rule,
                severity=Severity.ERROR,
                message=f"File not found: {path}",
                table=table_name,
                line=0,
                record_id="",
            )
        )
        return records

    for line_number, raw_line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        line = raw_line.strip()
        if not line:
            continue
        try:
            records.append(json.loads(line))
        except json.JSONDecodeError as exc:
            report.add(
                Violation(
                    rule=rule,
                    severity=Severity.ERROR,
                    message=f"JSON parse error: {exc}",
                    table=table_name,
                    line=line_number,
                    record_id="",
                )
            )
    return records


class StoreValidator:
    def __init__(
        self,
        store_root: Path,
        project_root: Path | None = None,
        raw_root: Path | None = None,
    ) -> None:
        self.store_root = store_root
        self.project_root = project_root or store_root.parent
        self.raw_root = raw_root or self.project_root / "raw"
        self.memo_path = store_root / "memo.raw.jsonl"
        self.image_path = store_root / "image.raw.jsonl"
        self.missing_image_path = store_root / "missing_image.raw.jsonl"

    def validate(self) -> ValidationReport:
        report = ValidationReport()

        memos = _load_jsonl(self.memo_path, "memo.raw", report, Rule.R1_MEMO_JSONL_PARSEABLE)
        images = _load_jsonl(self.image_path, "image.raw", report, Rule.R2_IMAGE_JSONL_PARSEABLE)
        missing_images = _load_jsonl(
            self.missing_image_path,
            "missing_image.raw",
            report,
            Rule.R3_MISSING_IMAGE_JSONL_PARSEABLE,
        )

        if not memos and not images and not missing_images:
            return report

        self._check_required_fields(memos, "memo.raw", MEMO_FIELDS, report)
        self._check_required_fields(images, "image.raw", IMAGE_FIELDS, report)
        self._check_required_fields(missing_images, "missing_image.raw", MISSING_FIELDS, report)

        self._check_empty_keys(memos, "memo.raw", MEMO_KEY_FIELDS, report)
        self._check_empty_keys(images, "image.raw", IMAGE_KEY_FIELDS, report)
        self._check_empty_keys(missing_images, "missing_image.raw", MISSING_KEY_FIELDS, report)

        self._check_id_unique(memos, "memo.raw", "memo_id", Rule.C1_MEMO_ID_UNIQUE, report)
        self._check_id_unique(images, "image.raw", "image_id", Rule.C2_IMAGE_ID_UNIQUE, report)

        memo_ids = {record.get("memo_id", "") for record in memos}
        self._check_fk_exists(images, "image.raw", "memo_id", memo_ids, Rule.C4_IMAGE_MEMO_ID_EXISTS, report)
        self._check_fk_exists(
            missing_images,
            "missing_image.raw",
            "memo_id",
            memo_ids,
            Rule.C5_MISSING_IMAGE_MEMO_ID_EXISTS,
            report,
        )

        image_ids = {record.get("image_id", "") for record in images}
        missing_ids = {record.get("image_id", "") for record in missing_images}
        for image_id in image_ids & missing_ids:
            if image_id:
                report.add(
                    Violation(
                        rule=Rule.C6_IMAGE_ID_NO_CROSS,
                        severity=Severity.ERROR,
                        message="image_id appears in both image.raw and missing_image.raw",
                        table="cross-table",
                        line=0,
                        record_id=image_id,
                    )
                )

        self._check_relative_paths(memos, "memo.raw", MEMO_PATH_FIELDS, report)
        self._check_relative_paths(images, "image.raw", IMAGE_PATH_FIELDS, report)
        self._check_relative_paths(missing_images, "missing_image.raw", MISSING_PATH_FIELDS, report)

        self._check_image_files_exist(images, report)
        self._check_source_files_exist(memos, images, missing_images, report)
        self._check_iso8601(memos, report)
        self._check_image_count(memos, images, missing_images, report)
        self._check_frontmatter(memos, report)

        return report

    @staticmethod
    def _record_id(record: dict) -> str:
        return str(record.get("memo_id") or record.get("image_id") or "")

    def _check_required_fields(
        self,
        records: list[dict],
        table: str,
        required: set[str],
        report: ValidationReport,
    ) -> None:
        for line_number, record in enumerate(records, start=1):
            missing_fields = required - record.keys()
            if missing_fields:
                report.add(
                    Violation(
                        rule=Rule.R5_MISSING_REQUIRED_FIELD,
                        severity=Severity.ERROR,
                        message=f"Missing required field(s): {', '.join(sorted(missing_fields))}",
                        table=table,
                        line=line_number,
                        record_id=self._record_id(record),
                    )
                )

    def _check_empty_keys(
        self,
        records: list[dict],
        table: str,
        key_fields: set[str],
        report: ValidationReport,
    ) -> None:
        for line_number, record in enumerate(records, start=1):
            for field_name in sorted(key_fields):
                if record.get(field_name) == "":
                    report.add(
                        Violation(
                            rule=Rule.R4_EMPTY_KEY_FIELD,
                            severity=Severity.ERROR,
                            message=f"Empty string in key field '{field_name}'",
                            table=table,
                            line=line_number,
                            record_id=self._record_id(record),
                        )
                    )

    def _check_id_unique(
        self,
        records: list[dict],
        table: str,
        id_field: str,
        rule: Rule,
        report: ValidationReport,
    ) -> None:
        seen: dict[str, int] = {}
        for line_number, record in enumerate(records, start=1):
            record_id = str(record.get(id_field, ""))
            if record_id in seen:
                report.add(
                    Violation(
                        rule=rule,
                        severity=Severity.ERROR,
                        message=f"Duplicate {id_field}",
                        table=table,
                        line=line_number,
                        record_id=record_id,
                    )
                )
            else:
                seen[record_id] = line_number

    def _check_fk_exists(
        self,
        records: list[dict],
        table: str,
        fk_field: str,
        parent_ids: set[str],
        rule: Rule,
        report: ValidationReport,
    ) -> None:
        for line_number, record in enumerate(records, start=1):
            fk_value = str(record.get(fk_field, ""))
            if fk_value and fk_value not in parent_ids:
                report.add(
                    Violation(
                        rule=rule,
                        severity=Severity.ERROR,
                        message=f"{fk_field} '{fk_value}' not found in memo.raw",
                        table=table,
                        line=line_number,
                        record_id=fk_value,
                    )
                )

    def _check_relative_paths(
        self,
        records: list[dict],
        table: str,
        path_fields: set[str],
        report: ValidationReport,
    ) -> None:
        for line_number, record in enumerate(records, start=1):
            for field_name in sorted(path_fields):
                value = record.get(field_name, "")
                if value and isinstance(value, str) and (value.startswith("/") or value.startswith("\\")):
                    report.add(
                        Violation(
                            rule=Rule.C7_PATH_RELATIVE,
                            severity=Severity.ERROR,
                            message=f"Absolute path in '{field_name}': {value}",
                            table=table,
                            line=line_number,
                            record_id=self._record_id(record),
                        )
                    )

    def _check_image_files_exist(self, images: list[dict], report: ValidationReport) -> None:
        for line_number, record in enumerate(images, start=1):
            image_relpath = record.get("image_relpath", "")
            if not image_relpath:
                continue
            full_path = self.project_root / str(image_relpath)
            if not full_path.exists():
                report.add(
                    Violation(
                        rule=Rule.C8_IMAGE_FILE_EXISTS,
                        severity=Severity.ERROR,
                        message=f"Image file not found: {image_relpath}",
                        table="image.raw",
                        line=line_number,
                        record_id=str(record.get("image_id", "")),
                    )
                )

    def _check_source_files_exist(
        self,
        memos: list[dict],
        images: list[dict],
        missing_images: list[dict],
        report: ValidationReport,
    ) -> None:
        for line_number, record in enumerate(memos, start=1):
            self._check_source_file(
                table="memo.raw",
                line_number=line_number,
                record=record,
                should_exist=True,
                report=report,
            )
        for line_number, record in enumerate(images, start=1):
            self._check_source_file(
                table="image.raw",
                line_number=line_number,
                record=record,
                should_exist=True,
                report=report,
            )
        for line_number, record in enumerate(missing_images, start=1):
            self._check_source_file(
                table="missing_image.raw",
                line_number=line_number,
                record=record,
                should_exist=False,
                report=report,
            )

    def _check_source_file(
        self,
        table: str,
        line_number: int,
        record: dict,
        should_exist: bool,
        report: ValidationReport,
    ) -> None:
        source_relpath = record.get("source_relpath", "")
        if not source_relpath:
            return
        full_path = self.raw_root / str(source_relpath)
        exists = full_path.exists()
        if should_exist and not exists:
            report.add(
                Violation(
                    rule=Rule.C9_SOURCE_FILE_EXPECTATION,
                    severity=Severity.ERROR,
                    message=f"Source file not found under raw root: {source_relpath}",
                    table=table,
                    line=line_number,
                    record_id=self._record_id(record),
                )
            )
        if not should_exist and exists:
            report.add(
                Violation(
                    rule=Rule.C9_SOURCE_FILE_EXPECTATION,
                    severity=Severity.ERROR,
                    message=f"Missing-image record points to an existing file: {source_relpath}",
                    table=table,
                    line=line_number,
                    record_id=self._record_id(record),
                )
            )

    def _check_iso8601(self, memos: list[dict], report: ValidationReport) -> None:
        for line_number, record in enumerate(memos, start=1):
            created_at = record.get("created_at", "")
            if created_at and not ISO8601_RE.match(str(created_at)):
                report.add(
                    Violation(
                        rule=Rule.C10_CREATED_AT_ISO,
                        severity=Severity.ERROR,
                        message=f"Invalid ISO 8601 format: '{created_at}'",
                        table="memo.raw",
                        line=line_number,
                        record_id=str(record.get("memo_id", "")),
                    )
                )

    def _check_image_count(
        self,
        memos: list[dict],
        images: list[dict],
        missing_images: list[dict],
        report: ValidationReport,
    ) -> None:
        image_count_by_memo: dict[str, int] = {}
        for record in images:
            memo_id = str(record.get("memo_id", ""))
            if memo_id:
                image_count_by_memo[memo_id] = image_count_by_memo.get(memo_id, 0) + 1
        for record in missing_images:
            memo_id = str(record.get("memo_id", ""))
            if memo_id:
                image_count_by_memo[memo_id] = image_count_by_memo.get(memo_id, 0) + 1

        for line_number, record in enumerate(memos, start=1):
            memo_id = str(record.get("memo_id", ""))
            declared = record.get("image_count")
            if memo_id and declared is not None:
                actual = image_count_by_memo.get(memo_id, 0)
                if declared != actual:
                    report.add(
                        Violation(
                            rule=Rule.C3_IMAGE_COUNT_CONSISTENT,
                            severity=Severity.ERROR,
                            message=f"image_count={declared} but found {actual} image records",
                            table="memo.raw",
                            line=line_number,
                            record_id=memo_id,
                        )
                    )

    def _check_frontmatter(self, memos: list[dict], report: ValidationReport) -> None:
        for line_number, record in enumerate(memos, start=1):
            body_md = record.get("body_md", "")
            if isinstance(body_md, str) and body_md.startswith("---\n"):
                report.add(
                    Violation(
                        rule=Rule.C11_NO_FRONTMATTER,
                        severity=Severity.WARNING,
                        message="body_md starts with frontmatter-like header",
                        table="memo.raw",
                        line=line_number,
                        record_id=str(record.get("memo_id", "")),
                    )
                )
