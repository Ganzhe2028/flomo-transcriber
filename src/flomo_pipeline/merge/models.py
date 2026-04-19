from __future__ import annotations

import dataclasses


@dataclasses.dataclass(frozen=True)
class MonthlyImageRecord:
    image_id: str
    memo_id: str
    relative_path: str
    source_relpath: str
    media_type: str
    ocr_text: str
    visual_description: str
    model_name: str
    prompt_version: str
    run_id: str
    status: str
    error_message: str | None

    def to_dict(self) -> dict[str, object]:
        return dataclasses.asdict(self)


@dataclasses.dataclass(frozen=True)
class MonthlyMemoRecord:
    memo_id: str
    created_at: str
    month: str
    memo_text: str
    source_relpath: str
    batch_label: str
    ordinal: int
    image_count_raw: int
    images: list[MonthlyImageRecord]

    def to_dict(self) -> dict[str, object]:
        payload = dataclasses.asdict(self)
        payload["images"] = [image.to_dict() for image in self.images]
        return payload


@dataclasses.dataclass
class MergeStats:
    memo_count: int = 0
    monthly_file_count: int = 0

    def format_summary(self) -> str:
        return (
            f"Memos written: {self.memo_count}\n"
            f"Monthly files written: {self.monthly_file_count}"
        )
