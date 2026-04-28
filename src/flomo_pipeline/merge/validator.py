from __future__ import annotations

import re
from enum import StrEnum
from typing import TYPE_CHECKING, Any

from flomo_pipeline.common.validation import (
    Severity,
    ValidationReport,
    Violation,
    load_jsonl_for_validation,
)

if TYPE_CHECKING:
    from pathlib import Path

MONTHLY_FILE_SUFFIX = ".enriched.jsonl"
MONTHLY_FILE_PATTERN = re.compile(r"^(\d{4}-\d{2})\.enriched\.jsonl$")
ISO8601_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}$")


class Rule(StrEnum):
    M1_MEMO_ID_UNIQUE = "M1"
    M2_FILE_MONTH_MATCH = "M2"
    M3_MEMO_EXISTS_IN_RAW = "M3"
    M4_NESTED_IMAGE_EXISTS_IN_ENRICHED = "M4"
    M5_IMAGES_ARRAY_REQUIRED = "M5"
    M6_MONTH_COVERAGE_COMPLETE = "M6"
    M7_PATH_RELATIVE = "M7"
    M8_CREATED_AT_AND_ORDERING = "M8"
    R1_MEMO_RAW_JSONL_PARSEABLE = "R1"
    R2_IMAGE_ENRICHED_JSONL_PARSEABLE = "R2"
    R3_MONTHLY_JSONL_PARSEABLE = "R3"
    R4_MISSING_REQUIRED_FIELD = "R4"


REQUIRED_TOP_LEVEL_FIELDS = {
    "memo_id",
    "created_at",
    "month",
    "memo_text",
    "source_relpath",
    "batch_label",
    "ordinal",
    "image_count_raw",
    "images",
}
REQUIRED_IMAGE_FIELDS = {
    "image_id",
    "memo_id",
    "relative_path",
    "source_relpath",
    "media_type",
    "ocr_text",
    "visual_description",
    "model_name",
    "prompt_version",
    "run_id",
    "status",
    "error_message",
}


class MonthlyValidator:
    def __init__(
        self,
        *,
        store_root: Path,
        monthly_root: Path,
        month: str | None = None,
    ) -> None:
        self.store_root = store_root
        self.monthly_root = monthly_root
        self.month = month
        self.memo_path = store_root / "memo.raw.jsonl"
        self.image_enriched_path = store_root / "image.enriched.jsonl"

    def validate(self) -> ValidationReport:
        report = ValidationReport()
        memos = load_jsonl_for_validation(
            self.memo_path,
            table="memo.raw",
            report=report,
            rule=Rule.R1_MEMO_RAW_JSONL_PARSEABLE,
        )
        enriched_images = load_jsonl_for_validation(
            self.image_enriched_path,
            table="image.enriched",
            report=report,
            rule=Rule.R2_IMAGE_ENRICHED_JSONL_PARSEABLE,
        )
        raw_memos_by_month = self._group_raw_memos_by_month(memos)
        enriched_by_id = {str(record.get("image_id", "")): record for record in enriched_images}

        if self.month is not None:
            target_months = [self.month]
        else:
            discovered_months = {
                match.group(1)
                for path in self.monthly_root.glob(f"*{MONTHLY_FILE_SUFFIX}")
                if (match := MONTHLY_FILE_PATTERN.match(path.name))
            }
            target_months = sorted(set(raw_memos_by_month) | discovered_months)
        for month in target_months:
            table_name = f"monthly/{month}.enriched.jsonl"
            file_path = self.monthly_root / f"{month}.enriched.jsonl"
            month_records = load_jsonl_for_validation(
                file_path,
                table=table_name,
                report=report,
                rule=Rule.R3_MONTHLY_JSONL_PARSEABLE,
            )

            if not month_records:
                expected_raw = raw_memos_by_month.get(month, [])
                if expected_raw:
                    report.add(
                        Violation(
                            rule=Rule.M6_MONTH_COVERAGE_COMPLETE,
                            severity=Severity.ERROR,
                            message=f"Missing monthly records for month {month}",
                            table=table_name,
                            line=0,
                            record_id="",
                        )
                    )
                continue

            self._validate_month_file(
                month=month,
                table_name=table_name,
                month_records=month_records,
                raw_memos=raw_memos_by_month.get(month, []),
                enriched_by_id=enriched_by_id,
                report=report,
            )

        return report

    @staticmethod
    def _group_raw_memos_by_month(memos: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
        grouped: dict[str, list[dict[str, Any]]] = {}
        for memo in memos:
            month = str(memo.get("created_at", ""))[:7]
            grouped.setdefault(month, []).append(memo)
        for month_records in grouped.values():
            month_records.sort(
                key=lambda record: (
                    str(record.get("created_at", "")),
                    str(record.get("memo_id", "")),
                )
            )
        return grouped

    def _validate_month_file(
        self,
        *,
        month: str,
        table_name: str,
        month_records: list[dict[str, Any]],
        raw_memos: list[dict[str, Any]],
        enriched_by_id: dict[str, dict[str, Any]],
        report: ValidationReport,
    ) -> None:
        seen_ids: set[str] = set()
        raw_by_id = {str(record.get("memo_id", "")): record for record in raw_memos}
        observed_memo_ids: list[str] = []
        observed_sort_keys: list[tuple[str, str]] = []

        for line_number, record in enumerate(month_records, start=1):
            memo_id = str(record.get("memo_id", ""))
            missing_fields = REQUIRED_TOP_LEVEL_FIELDS - record.keys()
            if missing_fields:
                report.add(
                    Violation(
                        rule=Rule.R4_MISSING_REQUIRED_FIELD,
                        severity=Severity.ERROR,
                        message=f"Missing required field(s): {', '.join(sorted(missing_fields))}",
                        table=table_name,
                        line=line_number,
                        record_id=memo_id,
                    )
                )
                continue

            if memo_id in seen_ids:
                report.add(
                    Violation(
                        rule=Rule.M1_MEMO_ID_UNIQUE,
                        severity=Severity.ERROR,
                        message="Duplicate memo_id",
                        table=table_name,
                        line=line_number,
                        record_id=memo_id,
                    )
                )
            seen_ids.add(memo_id)
            observed_memo_ids.append(memo_id)

            record_month = str(record.get("month", ""))
            if record_month != month:
                report.add(
                    Violation(
                        rule=Rule.M2_FILE_MONTH_MATCH,
                        severity=Severity.ERROR,
                        message=(
                            f"Record month '{record_month}' does not match "
                            f"file month '{month}'"
                        ),
                        table=table_name,
                        line=line_number,
                        record_id=memo_id,
                    )
                )

            created_at = str(record.get("created_at", ""))
            observed_sort_keys.append((created_at, memo_id))
            if not ISO8601_RE.match(created_at):
                report.add(
                    Violation(
                        rule=Rule.M8_CREATED_AT_AND_ORDERING,
                        severity=Severity.ERROR,
                        message=f"Invalid created_at: {created_at}",
                        table=table_name,
                        line=line_number,
                        record_id=memo_id,
                    )
                )

            raw_memo = raw_by_id.get(memo_id)
            self._validate_paths(
                table_name=table_name,
                line_number=line_number,
                record_id=memo_id,
                values=[str(record.get("source_relpath", ""))],
                report=report,
            )
            if raw_memo is None:
                report.add(
                    Violation(
                        rule=Rule.M3_MEMO_EXISTS_IN_RAW,
                        severity=Severity.ERROR,
                        message="memo_id not found in memo.raw.jsonl",
                        table=table_name,
                        line=line_number,
                        record_id=memo_id,
                    )
                )
            images = record.get("images")
            if not isinstance(images, list):
                report.add(
                    Violation(
                        rule=Rule.M5_IMAGES_ARRAY_REQUIRED,
                        severity=Severity.ERROR,
                        message="images must be present and must be an array",
                        table=table_name,
                        line=line_number,
                        record_id=memo_id,
                    )
                )
                continue

            for nested_image in images:
                self._validate_nested_image(
                    table_name=table_name,
                    line_number=line_number,
                    memo_id=memo_id,
                    nested_image=nested_image,
                    enriched_by_id=enriched_by_id,
                    report=report,
                )

        expected_memo_ids = [str(record.get("memo_id", "")) for record in raw_memos]
        if observed_memo_ids != expected_memo_ids:
            report.add(
                Violation(
                    rule=Rule.M6_MONTH_COVERAGE_COMPLETE,
                    severity=Severity.ERROR,
                    message="Monthly memo set does not match memo.raw.jsonl for this month",
                    table=table_name,
                    line=0,
                    record_id="",
                )
            )

        if observed_sort_keys != sorted(observed_sort_keys):
            report.add(
                Violation(
                    rule=Rule.M8_CREATED_AT_AND_ORDERING,
                    severity=Severity.ERROR,
                    message="Monthly records are not sorted by created_at, memo_id",
                    table=table_name,
                    line=0,
                    record_id="",
                )
            )

    def _validate_nested_image(
        self,
        *,
        table_name: str,
        line_number: int,
        memo_id: str,
        nested_image: Any,
        enriched_by_id: dict[str, dict[str, Any]],
        report: ValidationReport,
    ) -> None:
        if not isinstance(nested_image, dict):
            report.add(
                Violation(
                    rule=Rule.M4_NESTED_IMAGE_EXISTS_IN_ENRICHED,
                    severity=Severity.ERROR,
                    message="Nested image entry must be an object",
                    table=table_name,
                    line=line_number,
                    record_id=memo_id,
                )
            )
            return

        image_id = str(nested_image.get("image_id", ""))
        missing_fields = REQUIRED_IMAGE_FIELDS - nested_image.keys()
        if missing_fields:
            report.add(
                Violation(
                    rule=Rule.R4_MISSING_REQUIRED_FIELD,
                    severity=Severity.ERROR,
                    message=(
                        "Nested image missing required field(s): "
                        f"{', '.join(sorted(missing_fields))}"
                    ),
                    table=table_name,
                    line=line_number,
                    record_id=image_id or memo_id,
                )
            )
            return

        self._validate_paths(
            table_name=table_name,
            line_number=line_number,
            record_id=image_id,
            values=[
                str(nested_image.get("relative_path", "")),
                str(nested_image.get("source_relpath", "")),
            ],
            report=report,
        )

        enriched_image = enriched_by_id.get(image_id)
        if enriched_image is None:
            report.add(
                Violation(
                    rule=Rule.M4_NESTED_IMAGE_EXISTS_IN_ENRICHED,
                    severity=Severity.ERROR,
                    message="Nested image_id not found in image.enriched.jsonl",
                    table=table_name,
                    line=line_number,
                    record_id=image_id,
                )
            )
            return

        expected_pairs = {
            "memo_id": str(enriched_image.get("memo_id", "")),
            "relative_path": str(enriched_image.get("relative_path", "")),
            "source_relpath": str(enriched_image.get("source_relpath", "")),
            "media_type": str(enriched_image.get("media_type", "")),
            "ocr_text": str(enriched_image.get("ocr_text", "")),
            "visual_description": str(enriched_image.get("visual_description", "")),
            "model_name": str(enriched_image.get("model_name", "")),
            "prompt_version": str(enriched_image.get("prompt_version", "")),
            "run_id": str(enriched_image.get("run_id", "")),
            "status": str(enriched_image.get("status", "")),
            "error_message": enriched_image.get("error_message"),
        }
        for field_name, expected_value in expected_pairs.items():
            if nested_image.get(field_name) != expected_value:
                report.add(
                    Violation(
                        rule=Rule.M4_NESTED_IMAGE_EXISTS_IN_ENRICHED,
                        severity=Severity.ERROR,
                        message=(
                            f"Nested image field '{field_name}' does not match "
                            "image.enriched.jsonl"
                        ),
                        table=table_name,
                        line=line_number,
                        record_id=image_id,
                    )
                )

    @staticmethod
    def _validate_paths(
        *,
        table_name: str,
        line_number: int,
        record_id: str,
        values: list[str],
        report: ValidationReport,
    ) -> None:
        for value in values:
            if value.startswith("/") or value.startswith("\\"):
                report.add(
                    Violation(
                        rule=Rule.M7_PATH_RELATIVE,
                        severity=Severity.ERROR,
                        message=f"Absolute path found: {value}",
                        table=table_name,
                        line=line_number,
                        record_id=record_id,
                    )
                )
