from __future__ import annotations

import dataclasses
from typing import Literal


EnrichStatus = Literal["success", "skipped", "failed"]


@dataclasses.dataclass(frozen=True)
class EnrichedImageRecord:
    image_id: str
    memo_id: str
    created_at: str
    month: str
    relative_path: str
    source_relpath: str
    media_type: str
    ocr_text: str
    visual_description: str
    model_name: str
    prompt_version: str
    run_id: str
    status: EnrichStatus
    error_message: str | None

    def to_dict(self) -> dict[str, object]:
        return dataclasses.asdict(self)


@dataclasses.dataclass(frozen=True)
class ProviderResult:
    ocr_text: str
    visual_description: str
    status: Literal["success", "failed"]
    error_message: str | None


@dataclasses.dataclass
class EnrichStats:
    total: int = 0
    success: int = 0
    skipped: int = 0
    failed: int = 0
    retry_rounds: int = 0
    retry_attempts: int = 0
    retry_success: int = 0
    retry_failed: int = 0

    def format_summary(self) -> str:
        lines = [
            f"Total: {self.total}",
            f"Success: {self.success}",
            f"Skipped: {self.skipped}",
            f"Failed: {self.failed}",
        ]
        if self.retry_attempts or self.retry_failed:
            lines.extend(
                [
                    f"Retry rounds: {self.retry_rounds}",
                    f"Retry attempts: {self.retry_attempts}",
                    f"Retry success: {self.retry_success}",
                    f"Retry still failed: {self.retry_failed}",
                ]
            )
        return "\n".join(lines)
