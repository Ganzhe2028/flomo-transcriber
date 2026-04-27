from __future__ import annotations

import json
from pathlib import Path

from flomo_pipeline.enrich import EnrichedImageValidator, ImageEnrichmentRunner
from flomo_pipeline.enrich.models import ProviderResult
from flomo_pipeline.enrich.providers import MockEnrichmentProvider
from tests.conftest import write_jsonl


def _setup_enrich_store(tmp_path: Path) -> Path:
    store_root = tmp_path / "store"
    store_root.mkdir(parents=True, exist_ok=True)

    write_jsonl(
        store_root / "memo.raw.jsonl",
        [
            {
                "memo_id": "flomo-example-20260304--0001",
                "created_at": "2026-03-04T10:00:00",
                "body_md": "memo",
                "image_count": 3,
                "source_relpath": "2026/flomo@Example-20260304/Example.html",
                "batch_label": "20260304",
                "ordinal": 1,
            }
        ],
    )
    write_jsonl(
        store_root / "image.raw.jsonl",
        [
            {
                "image_id": "flomo-example-20260304--0001--01",
                "memo_id": "flomo-example-20260304--0001",
                "image_relpath": "store/images/2026/2026-03/good-image.png",
                "source_relpath": "2026/flomo@Example-20260304/file/2026-03-04/a/good-image.png",
                "ordinal": 1,
            },
            {
                "image_id": "flomo-example-20260304--0001--02",
                "memo_id": "flomo-example-20260304--0001",
                "image_relpath": "store/media/2026/2026-03/clip.mov",
                "source_relpath": "2026/flomo@Example-20260304/file/2026-03-04/a/clip.mov",
                "ordinal": 2,
            },
            {
                "image_id": "flomo-example-20260304--0001--03",
                "memo_id": "flomo-example-20260304--0001",
                "image_relpath": "store/images/2026/2026-03/missing-image.jpg",
                "source_relpath": "2026/flomo@Example-20260304/file/2026-03-04/a/missing-image.jpg",
                "ordinal": 3,
            },
        ],
    )

    good_image = tmp_path / "store" / "images" / "2026" / "2026-03" / "good-image.png"
    good_image.parent.mkdir(parents=True, exist_ok=True)
    good_image.write_bytes(b"\x89PNG\r\n\x1a\n")

    skipped_media = tmp_path / "store" / "media" / "2026" / "2026-03" / "clip.mov"
    skipped_media.parent.mkdir(parents=True, exist_ok=True)
    skipped_media.write_bytes(b"mov")

    return store_root


def _setup_single_image_store(tmp_path: Path) -> Path:
    store_root = tmp_path / "store"
    store_root.mkdir(parents=True, exist_ok=True)

    write_jsonl(
        store_root / "memo.raw.jsonl",
        [
            {
                "memo_id": "flomo-example-20260304--0001",
                "created_at": "2026-03-04T10:00:00",
                "body_md": "memo",
                "image_count": 1,
                "source_relpath": "2026/flomo@Example-20260304/Example.html",
                "batch_label": "20260304",
                "ordinal": 1,
            }
        ],
    )
    write_jsonl(
        store_root / "image.raw.jsonl",
        [
            {
                "image_id": "flomo-example-20260304--0001--01",
                "memo_id": "flomo-example-20260304--0001",
                "image_relpath": "store/images/2026/2026-03/good-image.png",
                "source_relpath": "2026/flomo@Example-20260304/file/2026-03-04/a/good-image.png",
                "ordinal": 1,
            }
        ],
    )

    good_image = tmp_path / "store" / "images" / "2026" / "2026-03" / "good-image.png"
    good_image.parent.mkdir(parents=True, exist_ok=True)
    good_image.write_bytes(b"\x89PNG\r\n\x1a\n")

    return store_root


def _setup_two_image_store(tmp_path: Path) -> Path:
    store_root = tmp_path / "store"
    store_root.mkdir(parents=True, exist_ok=True)

    write_jsonl(
        store_root / "memo.raw.jsonl",
        [
            {
                "memo_id": "flomo-example-20260304--0001",
                "created_at": "2026-03-04T10:00:00",
                "body_md": "memo",
                "image_count": 2,
                "source_relpath": "2026/flomo@Example-20260304/Example.html",
                "batch_label": "20260304",
                "ordinal": 1,
            }
        ],
    )
    write_jsonl(
        store_root / "image.raw.jsonl",
        [
            {
                "image_id": "flomo-example-20260304--0001--01",
                "memo_id": "flomo-example-20260304--0001",
                "image_relpath": "store/images/2026/2026-03/good-image-1.png",
                "source_relpath": "2026/flomo@Example-20260304/file/2026-03-04/a/good-image-1.png",
                "ordinal": 1,
            },
            {
                "image_id": "flomo-example-20260304--0001--02",
                "memo_id": "flomo-example-20260304--0001",
                "image_relpath": "store/images/2026/2026-03/good-image-2.png",
                "source_relpath": "2026/flomo@Example-20260304/file/2026-03-04/a/good-image-2.png",
                "ordinal": 2,
            },
        ],
    )

    for name in ("good-image-1.png", "good-image-2.png"):
        image_path = tmp_path / "store" / "images" / "2026" / "2026-03" / name
        image_path.parent.mkdir(parents=True, exist_ok=True)
        image_path.write_bytes(b"\x89PNG\r\n\x1a\n")

    return store_root


class SequencedProvider:
    name = "sequenced"
    model_name = "sequenced-vlm"
    prompt_version = "sequenced-v1"

    def __init__(self, results: list[ProviderResult]) -> None:
        self.results = results
        self.calls = 0

    def enrich(self, image_path: Path, *, image_id: str, memo_id: str) -> ProviderResult:
        self.calls += 1
        if self.results:
            return self.results.pop(0)
        return ProviderResult(
            ocr_text="",
            visual_description="",
            status="failed",
            error_message="unexpected extra call",
        )


class InterruptingProvider:
    name = "interrupting"
    model_name = "interrupting-vlm"
    prompt_version = "interrupting-v1"

    def __init__(self) -> None:
        self.calls = 0

    def enrich(self, image_path: Path, *, image_id: str, memo_id: str) -> ProviderResult:
        self.calls += 1
        if self.calls == 1:
            return ProviderResult("saved text", "", "success", None)
        raise KeyboardInterrupt()


def test_enrich_runner_handles_success_skipped_failed_and_stats(tmp_path: Path) -> None:
    store_root = _setup_enrich_store(tmp_path)

    records, stats = ImageEnrichmentRunner(
        store_root=store_root,
        provider=MockEnrichmentProvider(),
        project_root=tmp_path,
        run_id="run-1",
    ).run()

    by_id = {record.image_id: record for record in records}

    success_record = by_id["flomo-example-20260304--0001--01"]
    assert success_record.status == "success"
    assert success_record.memo_id == "flomo-example-20260304--0001"
    assert success_record.relative_path == "store/images/2026/2026-03/good-image.png"
    assert success_record.ocr_text
    assert success_record.visual_description

    skipped_record = by_id["flomo-example-20260304--0001--02"]
    assert skipped_record.status == "skipped"
    assert skipped_record.media_type == "video/quicktime"

    failed_record = by_id["flomo-example-20260304--0001--03"]
    assert failed_record.status == "failed"
    assert failed_record.error_message == "Image file not found: store/images/2026/2026-03/missing-image.jpg"

    assert stats.total == 3
    assert stats.success == 1
    assert stats.skipped == 1
    assert stats.failed == 1


def test_enrich_runner_persists_progress_before_interruption(tmp_path: Path) -> None:
    store_root = _setup_two_image_store(tmp_path)
    provider = InterruptingProvider()

    try:
        ImageEnrichmentRunner(
            store_root=store_root,
            provider=provider,
            project_root=tmp_path,
            run_id="run-1",
            max_failed_retries=0,
        ).run()
    except KeyboardInterrupt:
        pass
    else:  # pragma: no cover - defensive guard
        raise AssertionError("expected interruption")

    records = [
        json.loads(line)
        for line in (store_root / "image.enriched.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]

    assert provider.calls == 2
    assert len(records) == 1
    assert records[0]["image_id"] == "flomo-example-20260304--0001--01"
    assert records[0]["status"] == "success"
    assert records[0]["ocr_text"] == "saved text"


def test_enrich_runner_parallel_workers_keep_records_and_stats(tmp_path: Path) -> None:
    store_root = _setup_enrich_store(tmp_path)

    records, stats = ImageEnrichmentRunner(
        store_root=store_root,
        provider=MockEnrichmentProvider(),
        project_root=tmp_path,
        run_id="run-1",
        workers=2,
    ).run()

    assert [record.image_id for record in records] == [
        "flomo-example-20260304--0001--01",
        "flomo-example-20260304--0001--02",
        "flomo-example-20260304--0001--03",
    ]
    assert stats.total == 3
    assert stats.success == 1
    assert stats.skipped == 1
    assert stats.failed == 1


def test_enrich_runner_skips_existing_success_by_default(tmp_path: Path) -> None:
    store_root = _setup_enrich_store(tmp_path)

    first_records, _ = ImageEnrichmentRunner(
        store_root=store_root,
        provider=MockEnrichmentProvider(),
        project_root=tmp_path,
        run_id="run-1",
    ).run()
    second_records, second_stats = ImageEnrichmentRunner(
        store_root=store_root,
        provider=MockEnrichmentProvider(),
        project_root=tmp_path,
        run_id="run-2",
    ).run()

    first_success = {
        record.image_id: record for record in first_records
    }["flomo-example-20260304--0001--01"]
    second_success = {
        record.image_id: record for record in second_records
    }["flomo-example-20260304--0001--01"]

    assert second_success.run_id == first_success.run_id
    assert second_stats.total == 3
    assert second_stats.success == 0
    assert second_stats.skipped == 2
    assert second_stats.failed == 1


def test_enrich_runner_failed_only_retries_failed_and_preserves_success(tmp_path: Path) -> None:
    store_root = _setup_two_image_store(tmp_path)
    write_jsonl(
        store_root / "image.enriched.jsonl",
        [
            {
                "image_id": "flomo-example-20260304--0001--01",
                "memo_id": "flomo-example-20260304--0001",
                "created_at": "2026-03-04T10:00:00",
                "month": "2026-03",
                "relative_path": "store/images/2026/2026-03/good-image-1.png",
                "source_relpath": "2026/flomo@Example-20260304/file/2026-03-04/a/good-image-1.png",
                "media_type": "image/png",
                "ocr_text": "existing text",
                "visual_description": "",
                "model_name": "old-vlm",
                "prompt_version": "old-v1",
                "run_id": "old-run",
                "status": "success",
                "error_message": None,
            },
            {
                "image_id": "flomo-example-20260304--0001--02",
                "memo_id": "flomo-example-20260304--0001",
                "created_at": "2026-03-04T10:00:00",
                "month": "2026-03",
                "relative_path": "store/images/2026/2026-03/good-image-2.png",
                "source_relpath": "2026/flomo@Example-20260304/file/2026-03-04/a/good-image-2.png",
                "media_type": "image/png",
                "ocr_text": "",
                "visual_description": "",
                "model_name": "old-vlm",
                "prompt_version": "old-v1",
                "run_id": "old-run",
                "status": "failed",
                "error_message": "temporary failure",
            },
        ],
    )
    provider = SequencedProvider([ProviderResult("retried text", "", "success", None)])

    records, stats = ImageEnrichmentRunner(
        store_root=store_root,
        provider=provider,
        project_root=tmp_path,
        run_id="retry-run",
        failed_only=True,
        max_failed_retries=0,
    ).run()

    by_id = {record.image_id: record for record in records}
    assert provider.calls == 1
    assert by_id["flomo-example-20260304--0001--01"].run_id == "old-run"
    assert by_id["flomo-example-20260304--0001--02"].run_id == "retry-run"
    assert by_id["flomo-example-20260304--0001--02"].status == "success"
    assert by_id["flomo-example-20260304--0001--02"].ocr_text == "retried text"
    assert stats.total == 1
    assert stats.success == 1
    assert stats.failed == 0


def test_enrich_runner_retries_failed_records_after_initial_pass(tmp_path: Path) -> None:
    store_root = _setup_single_image_store(tmp_path)
    provider = SequencedProvider(
        [
            ProviderResult("", "", "failed", "first failure"),
            ProviderResult("", "", "failed", "second failure"),
            ProviderResult("retried text", "", "success", None),
        ]
    )

    records, stats = ImageEnrichmentRunner(
        store_root=store_root,
        provider=provider,
        project_root=tmp_path,
        run_id="run-1",
    ).run()

    assert provider.calls == 3
    assert len(records) == 1
    assert records[0].status == "success"
    assert records[0].ocr_text == "retried text"
    assert stats.total == 1
    assert stats.success == 1
    assert stats.failed == 0
    assert stats.retry_rounds == 2
    assert stats.retry_attempts == 2
    assert stats.retry_success == 1
    assert stats.retry_failed == 0


def test_enrich_runner_stops_after_three_failed_retries(tmp_path: Path) -> None:
    store_root = _setup_single_image_store(tmp_path)
    provider = SequencedProvider(
        [
            ProviderResult("", "", "failed", "initial"),
            ProviderResult("", "", "failed", "retry-1"),
            ProviderResult("", "", "failed", "retry-2"),
            ProviderResult("", "", "failed", "retry-3"),
            ProviderResult("too late", "", "success", None),
        ]
    )

    records, stats = ImageEnrichmentRunner(
        store_root=store_root,
        provider=provider,
        project_root=tmp_path,
        run_id="run-1",
    ).run()

    assert provider.calls == 4
    assert len(records) == 1
    assert records[0].status == "failed"
    assert records[0].error_message == "retry-3"
    assert stats.total == 1
    assert stats.success == 0
    assert stats.failed == 1
    assert stats.retry_rounds == 3
    assert stats.retry_attempts == 3
    assert stats.retry_success == 0
    assert stats.retry_failed == 1
    assert "Retry still failed: 1" in stats.format_summary()


def test_enrich_validator_passes_generated_output(tmp_path: Path) -> None:
    store_root = _setup_enrich_store(tmp_path)
    ImageEnrichmentRunner(
        store_root=store_root,
        provider=MockEnrichmentProvider(),
        project_root=tmp_path,
        run_id="run-1",
    ).run()

    report = EnrichedImageValidator(store_root=store_root).validate()
    assert report.ok, report.format_detail()


def test_enrich_validator_catches_invalid_failed_record(tmp_path: Path) -> None:
    store_root = _setup_enrich_store(tmp_path)
    write_jsonl(
        store_root / "image.enriched.jsonl",
        [
            {
                "image_id": "flomo-example-20260304--0001--01",
                "memo_id": "flomo-example-20260304--0001",
                "created_at": "2026-03-04T10:00:00",
                "month": "2026-03",
                "relative_path": "store/images/2026/2026-03/good-image.png",
                "source_relpath": "2026/flomo@Example-20260304/file/2026-03-04/a/good-image.png",
                "media_type": "image/png",
                "ocr_text": "",
                "visual_description": "",
                "model_name": "mock-vlm",
                "prompt_version": "mock-v1",
                "run_id": "run-1",
                "status": "failed",
                "error_message": "",
            }
        ],
    )

    report = EnrichedImageValidator(store_root=store_root).validate()
    assert not report.ok
    assert "failed record must include error_message" in report.format_detail()
