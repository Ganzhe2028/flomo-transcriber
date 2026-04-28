from __future__ import annotations

from enum import StrEnum
from typing import TYPE_CHECKING

from flomo_pipeline.common.validation import (
    Severity,
    ValidationReport,
    Violation,
    load_jsonl_for_validation,
)

if TYPE_CHECKING:
    from pathlib import Path


class Rule(StrEnum):
    E1_IMAGE_ID_UNIQUE = "E1"
    E2_IMAGE_ID_EXISTS_IN_RAW = "E2"
    E3_MEMO_ID_MATCHES_RAW = "E3"
    E4_PATH_RELATIVE = "E4"
    E5_STATUS_ALLOWED = "E5"
    E6_SUCCESS_HAS_CONTENT = "E6"
    E7_FAILED_HAS_ERROR = "E7"
    R1_IMAGE_RAW_JSONL_PARSEABLE = "R1"
    R2_IMAGE_ENRICHED_JSONL_PARSEABLE = "R2"
    R3_MISSING_REQUIRED_FIELD = "R3"


ALLOWED_STATUSES = {"success", "skipped", "failed"}
REQUIRED_FIELDS = {
    "image_id",
    "memo_id",
    "created_at",
    "month",
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
PATH_FIELDS = {"relative_path", "source_relpath"}


class EnrichedImageValidator:
    def __init__(self, *, store_root: Path) -> None:
        self.store_root = store_root
        self.image_raw_path = store_root / "image.raw.jsonl"
        self.image_enriched_path = store_root / "image.enriched.jsonl"

    def validate(self) -> ValidationReport:
        report = ValidationReport(
            default_table="image.enriched",
            table_order=("image.raw", "image.enriched"),
        )
        raw_images = load_jsonl_for_validation(
            self.image_raw_path,
            report=report,
            table="image.raw",
            rule=Rule.R1_IMAGE_RAW_JSONL_PARSEABLE,
        )
        enriched_images = load_jsonl_for_validation(
            self.image_enriched_path,
            report=report,
            table="image.enriched",
            rule=Rule.R2_IMAGE_ENRICHED_JSONL_PARSEABLE,
        )

        raw_by_id = {str(record.get("image_id", "")): record for record in raw_images}
        seen_ids: set[str] = set()

        for line_number, record in enumerate(enriched_images, start=1):
            image_id = str(record.get("image_id", ""))
            memo_id = str(record.get("memo_id", ""))

            missing_fields = REQUIRED_FIELDS - record.keys()
            if missing_fields:
                report.add(
                    Violation(
                        rule=Rule.R3_MISSING_REQUIRED_FIELD,
                        severity=Severity.ERROR,
                        message=f"Missing required field(s): {', '.join(sorted(missing_fields))}",
                        line=line_number,
                        record_id=image_id,
                    )
                )
                continue

            if image_id in seen_ids:
                report.add(
                    Violation(
                        rule=Rule.E1_IMAGE_ID_UNIQUE,
                        severity=Severity.ERROR,
                        message="Duplicate image_id",
                        line=line_number,
                        record_id=image_id,
                    )
                )
            seen_ids.add(image_id)

            raw_record = raw_by_id.get(image_id)
            if raw_record is None:
                report.add(
                    Violation(
                        rule=Rule.E2_IMAGE_ID_EXISTS_IN_RAW,
                        severity=Severity.ERROR,
                        message="image_id not found in image.raw.jsonl",
                        line=line_number,
                        record_id=image_id,
                    )
                )
            elif str(raw_record.get("memo_id", "")) != memo_id:
                report.add(
                    Violation(
                        rule=Rule.E3_MEMO_ID_MATCHES_RAW,
                        severity=Severity.ERROR,
                        message="memo_id does not match image.raw.jsonl",
                        line=line_number,
                        record_id=image_id,
                    )
                )

            for field_name in sorted(PATH_FIELDS):
                value = record.get(field_name)
                if isinstance(value, str) and (value.startswith("/") or value.startswith("\\")):
                    report.add(
                        Violation(
                            rule=Rule.E4_PATH_RELATIVE,
                            severity=Severity.ERROR,
                            message=f"Absolute path in '{field_name}': {value}",
                            line=line_number,
                            record_id=image_id,
                        )
                    )

            status = record.get("status")
            if status not in ALLOWED_STATUSES:
                report.add(
                    Violation(
                        rule=Rule.E5_STATUS_ALLOWED,
                        severity=Severity.ERROR,
                        message=f"Unsupported status: {status}",
                        line=line_number,
                        record_id=image_id,
                    )
                )
                continue

            ocr_text = str(record.get("ocr_text", "") or "")
            visual_description = str(record.get("visual_description", "") or "")
            error_message = record.get("error_message")

            if status == "success" and not (ocr_text.strip() or visual_description.strip()):
                report.add(
                    Violation(
                        rule=Rule.E6_SUCCESS_HAS_CONTENT,
                        severity=Severity.ERROR,
                        message="success record must include ocr_text or visual_description",
                        line=line_number,
                        record_id=image_id,
                    )
                )

            if status == "failed" and not (
                isinstance(error_message, str) and error_message.strip()
            ):
                report.add(
                    Violation(
                        rule=Rule.E7_FAILED_HAS_ERROR,
                        severity=Severity.ERROR,
                        message="failed record must include error_message",
                        line=line_number,
                        record_id=image_id,
                    )
                )

        return report
