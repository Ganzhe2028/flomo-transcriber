from __future__ import annotations

from typing import TYPE_CHECKING, Any

from flomo_pipeline.common.io import read_jsonl, write_jsonl
from flomo_pipeline.merge.models import MergeStats, MonthlyImageRecord, MonthlyMemoRecord

if TYPE_CHECKING:
    from pathlib import Path

MONTHLY_FILE_SUFFIX = ".enriched.jsonl"


def _build_nested_image(record: dict[str, Any]) -> MonthlyImageRecord:
    return MonthlyImageRecord(
        image_id=str(record["image_id"]),
        memo_id=str(record["memo_id"]),
        relative_path=str(record["relative_path"]),
        source_relpath=str(record["source_relpath"]),
        media_type=str(record["media_type"]),
        ocr_text=str(record["ocr_text"]),
        visual_description=str(record["visual_description"]),
        model_name=str(record["model_name"]),
        prompt_version=str(record["prompt_version"]),
        run_id=str(record["run_id"]),
        status=str(record["status"]),
        error_message=record.get("error_message"),
    )


class MonthlyMergeRunner:
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

    def run(self) -> tuple[dict[str, list[MonthlyMemoRecord]], MergeStats]:
        memos = read_jsonl(self.memo_path)
        enriched_images = read_jsonl(self.image_enriched_path)

        images_by_memo: dict[str, list[MonthlyImageRecord]] = {}
        for image_record in enriched_images:
            memo_id = str(image_record["memo_id"])
            images_by_memo.setdefault(memo_id, []).append(_build_nested_image(image_record))

        for memo_images in images_by_memo.values():
            memo_images.sort(key=lambda image: image.image_id)

        grouped_records: dict[str, list[MonthlyMemoRecord]] = {}
        for memo_record in memos:
            month = str(memo_record["created_at"])[:7]
            if self.month is not None and month != self.month:
                continue

            merged_record = MonthlyMemoRecord(
                memo_id=str(memo_record["memo_id"]),
                created_at=str(memo_record["created_at"]),
                month=month,
                memo_text=str(memo_record["body_md"]),
                source_relpath=str(memo_record["source_relpath"]),
                batch_label=str(memo_record["batch_label"]),
                ordinal=int(memo_record["ordinal"]),
                image_count_raw=int(memo_record["image_count"]),
                images=list(images_by_memo.get(str(memo_record["memo_id"]), [])),
            )
            grouped_records.setdefault(month, []).append(merged_record)

        for month_records in grouped_records.values():
            month_records.sort(key=lambda record: (record.created_at, record.memo_id))

        self._prepare_output_dir(grouped_records)

        for month, month_records in grouped_records.items():
            write_jsonl(self.monthly_root / f"{month}{MONTHLY_FILE_SUFFIX}", month_records)

        stats = MergeStats(
            memo_count=sum(len(month_records) for month_records in grouped_records.values()),
            monthly_file_count=len(grouped_records),
        )
        return grouped_records, stats

    def _prepare_output_dir(self, grouped_records: dict[str, list[MonthlyMemoRecord]]) -> None:
        self.monthly_root.mkdir(parents=True, exist_ok=True)
        target_files = {f"{month}{MONTHLY_FILE_SUFFIX}" for month in grouped_records}

        if self.month is None:
            for path in self.monthly_root.glob(f"*{MONTHLY_FILE_SUFFIX}"):
                path.unlink()
            return

        target_path = self.monthly_root / f"{self.month}{MONTHLY_FILE_SUFFIX}"
        if not target_files and target_path.exists():
            target_path.unlink()
