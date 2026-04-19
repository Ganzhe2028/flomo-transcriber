from __future__ import annotations

import json
from pathlib import Path

from flomo_pipeline.merge import MonthlyMergeRunner, MonthlyValidator
from tests.conftest import write_jsonl


def _setup_merge_store(tmp_path: Path) -> tuple[Path, Path]:
    store_root = tmp_path / "store"
    monthly_root = tmp_path / "monthly"
    store_root.mkdir(parents=True, exist_ok=True)
    monthly_root.mkdir(parents=True, exist_ok=True)

    write_jsonl(
        store_root / "memo.raw.jsonl",
        [
            {
                "memo_id": "flomo-example-20251231--0002",
                "created_at": "2025-12-31T09:00:00",
                "body_md": "December memo with images",
                "image_count": 2,
                "source_relpath": "2025/flomo@Example-20251231/2512.html",
                "batch_label": "20251231",
                "ordinal": 2,
            },
            {
                "memo_id": "flomo-example-20251231--0001",
                "created_at": "2025-12-31T08:00:00",
                "body_md": "December memo with zero images",
                "image_count": 0,
                "source_relpath": "2025/flomo@Example-20251231/2512.html",
                "batch_label": "20251231",
                "ordinal": 1,
            },
            {
                "memo_id": "flomo-example-20260102--0001",
                "created_at": "2026-01-02T10:00:00",
                "body_md": "January memo with failed image",
                "image_count": 1,
                "source_relpath": "2026/flomo@Example-20260102/2601.html",
                "batch_label": "20260102",
                "ordinal": 1,
            },
        ],
    )

    write_jsonl(
        store_root / "image.enriched.jsonl",
        [
            {
                "image_id": "flomo-example-20251231--0002--02",
                "memo_id": "flomo-example-20251231--0002",
                "created_at": "2025-12-31T09:00:00",
                "month": "2025-12",
                "relative_path": "store/images/2025/2025-12/second.jpg",
                "source_relpath": "2025/flomo@Example-20251231/file/2025-12-31/a/second.jpg",
                "media_type": "video/quicktime",
                "ocr_text": "",
                "visual_description": "",
                "model_name": "mock-vlm",
                "prompt_version": "mock-v1",
                "run_id": "run-1",
                "status": "skipped",
                "error_message": None,
            },
            {
                "image_id": "flomo-example-20251231--0002--01",
                "memo_id": "flomo-example-20251231--0002",
                "created_at": "2025-12-31T09:00:00",
                "month": "2025-12",
                "relative_path": "store/images/2025/2025-12/first.jpg",
                "source_relpath": "2025/flomo@Example-20251231/file/2025-12-31/a/first.jpg",
                "media_type": "image/jpeg",
                "ocr_text": "text one",
                "visual_description": "desc one",
                "model_name": "mock-vlm",
                "prompt_version": "mock-v1",
                "run_id": "run-1",
                "status": "success",
                "error_message": None,
            },
            {
                "image_id": "flomo-example-20260102--0001--01",
                "memo_id": "flomo-example-20260102--0001",
                "created_at": "2026-01-02T10:00:00",
                "month": "2026-01",
                "relative_path": "store/images/2026/2026-01/missing.jpg",
                "source_relpath": "2026/flomo@Example-20260102/file/2026-01-02/a/missing.jpg",
                "media_type": "image/jpeg",
                "ocr_text": "",
                "visual_description": "",
                "model_name": "mock-vlm",
                "prompt_version": "mock-v1",
                "run_id": "run-1",
                "status": "failed",
                "error_message": "Image file not found",
            },
        ],
    )
    return store_root, monthly_root


def test_merge_runner_writes_correct_month_split_and_keeps_zero_image_memos(tmp_path: Path) -> None:
    store_root, monthly_root = _setup_merge_store(tmp_path)

    grouped_records, stats = MonthlyMergeRunner(
        store_root=store_root,
        monthly_root=monthly_root,
    ).run()

    assert sorted(grouped_records) == ["2025-12", "2026-01"]
    assert stats.memo_count == 3
    assert stats.monthly_file_count == 2
    assert (monthly_root / "2025-12.enriched.jsonl").exists()
    assert (monthly_root / "2026-01.enriched.jsonl").exists()

    december_records = grouped_records["2025-12"]
    assert [record.memo_id for record in december_records] == [
        "flomo-example-20251231--0001",
        "flomo-example-20251231--0002",
    ]
    assert december_records[0].images == []
    assert december_records[0].memo_text == "December memo with zero images"


def test_merge_runner_preserves_failed_and_skipped_images(tmp_path: Path) -> None:
    store_root, monthly_root = _setup_merge_store(tmp_path)

    grouped_records, _ = MonthlyMergeRunner(store_root=store_root, monthly_root=monthly_root).run()

    december_images = grouped_records["2025-12"][1].images
    assert [image.image_id for image in december_images] == [
        "flomo-example-20251231--0002--01",
        "flomo-example-20251231--0002--02",
    ]
    assert [image.status for image in december_images] == ["success", "skipped"]

    january_images = grouped_records["2026-01"][0].images
    assert len(january_images) == 1
    assert january_images[0].status == "failed"
    assert january_images[0].error_message == "Image file not found"


def test_monthly_validator_passes_generated_output(tmp_path: Path) -> None:
    store_root, monthly_root = _setup_merge_store(tmp_path)
    MonthlyMergeRunner(store_root=store_root, monthly_root=monthly_root).run()

    report = MonthlyValidator(store_root=store_root, monthly_root=monthly_root).validate()
    assert report.ok, report.format_detail()


def test_monthly_validator_catches_month_mismatch(tmp_path: Path) -> None:
    store_root, monthly_root = _setup_merge_store(tmp_path)
    MonthlyMergeRunner(store_root=store_root, monthly_root=monthly_root).run()

    december_path = monthly_root / "2025-12.enriched.jsonl"
    records = [json.loads(line) for line in december_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    records[0]["month"] = "2026-01"
    write_jsonl(december_path, records)

    report = MonthlyValidator(store_root=store_root, monthly_root=monthly_root).validate()
    assert not report.ok
    assert "does not match file month" in report.format_detail()
