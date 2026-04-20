from __future__ import annotations

import json
import uuid
from concurrent.futures import Future, ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

from flomo_pipeline.enrich.models import EnrichStats, EnrichedImageRecord
from flomo_pipeline.enrich.provider import EnrichmentProvider

SUPPORTED_IMAGE_EXTENSIONS = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
}
SKIPPED_MEDIA_EXTENSIONS = {
    ".mov": "video/quicktime",
    ".mp4": "video/mp4",
    ".m4a": "audio/m4a",
}
DEFAULT_MEDIA_TYPE = "application/octet-stream"
MAX_FAILED_RETRIES = 3


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    records: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            records.append(json.loads(line))
    return records


def _write_jsonl(path: Path, records: list[EnrichedImageRecord]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record.to_dict(), ensure_ascii=False) + "\n")


def _record_from_dict(payload: dict[str, Any]) -> EnrichedImageRecord:
    return EnrichedImageRecord(
        image_id=str(payload["image_id"]),
        memo_id=str(payload["memo_id"]),
        created_at=str(payload["created_at"]),
        month=str(payload["month"]),
        relative_path=str(payload["relative_path"]),
        source_relpath=str(payload["source_relpath"]),
        media_type=str(payload["media_type"]),
        ocr_text=str(payload["ocr_text"]),
        visual_description=str(payload["visual_description"]),
        model_name=str(payload["model_name"]),
        prompt_version=str(payload["prompt_version"]),
        run_id=str(payload["run_id"]),
        status=str(payload["status"]),
        error_message=payload.get("error_message"),
    )


def _detect_media_type(relative_path: str) -> str:
    ext = Path(relative_path).suffix.lower()
    if ext in SUPPORTED_IMAGE_EXTENSIONS:
        return SUPPORTED_IMAGE_EXTENSIONS[ext]
    if ext in SKIPPED_MEDIA_EXTENSIONS:
        return SKIPPED_MEDIA_EXTENSIONS[ext]
    return DEFAULT_MEDIA_TYPE


def _is_supported_static_image(relative_path: str) -> bool:
    return Path(relative_path).suffix.lower() in SUPPORTED_IMAGE_EXTENSIONS


class ImageEnrichmentRunner:
    def __init__(
        self,
        *,
        store_root: Path,
        provider: EnrichmentProvider,
        month: str | None = None,
        overwrite: bool = False,
        run_id: str | None = None,
        project_root: Path | None = None,
        max_failed_retries: int = MAX_FAILED_RETRIES,
        workers: int = 1,
    ) -> None:
        if workers <= 0:
            raise ValueError("workers must be positive")
        self.store_root = store_root
        self.provider = provider
        self.month = month
        self.overwrite = overwrite
        self.run_id = run_id or uuid.uuid4().hex
        self.project_root = project_root or store_root.parent
        self.max_failed_retries = max_failed_retries
        self.workers = workers
        self.memo_path = store_root / "memo.raw.jsonl"
        self.image_path = store_root / "image.raw.jsonl"
        self.enriched_path = store_root / "image.enriched.jsonl"

    def run(self) -> tuple[list[EnrichedImageRecord], EnrichStats]:
        memo_records = _load_jsonl(self.memo_path)
        image_records = _load_jsonl(self.image_path)
        existing_records = {
            record.image_id: record
            for record in (
                _record_from_dict(payload) for payload in _load_jsonl(self.enriched_path)
            )
        }
        memos_by_id = {str(record["memo_id"]): record for record in memo_records}

        stats = EnrichStats()
        processed_records: list[EnrichedImageRecord] = []

        target_images = [
            record
            for record in image_records
            if self.month is None
            or self._get_month(memos_by_id.get(str(record["memo_id"]))) == self.month
        ]
        stats.total = len(target_images)

        processed_records = self._process_initial_records(
            target_images=target_images,
            existing_records=existing_records,
            memos_by_id=memos_by_id,
            stats=stats,
        )

        self._retry_failed_records(processed_records, target_images, memos_by_id, stats)

        if self.month is None:
            final_records = processed_records
        else:
            untouched_existing = [
                record
                for image_id, record in existing_records.items()
                if image_id not in {str(raw["image_id"]) for raw in target_images}
            ]
            final_records = untouched_existing + processed_records

        final_records.sort(key=lambda record: record.image_id)
        _write_jsonl(self.enriched_path, final_records)
        return final_records, stats

    def _process_initial_records(
        self,
        *,
        target_images: list[dict[str, Any]],
        existing_records: dict[str, EnrichedImageRecord],
        memos_by_id: dict[str, dict[str, Any]],
        stats: EnrichStats,
    ) -> list[EnrichedImageRecord]:
        if self.workers == 1:
            return self._process_initial_records_sequential(
                target_images=target_images,
                existing_records=existing_records,
                memos_by_id=memos_by_id,
                stats=stats,
            )
        return self._process_initial_records_parallel(
            target_images=target_images,
            existing_records=existing_records,
            memos_by_id=memos_by_id,
            stats=stats,
        )

    def _process_initial_records_sequential(
        self,
        *,
        target_images: list[dict[str, Any]],
        existing_records: dict[str, EnrichedImageRecord],
        memos_by_id: dict[str, dict[str, Any]],
        stats: EnrichStats,
    ) -> list[EnrichedImageRecord]:
        processed_records: list[EnrichedImageRecord] = []
        for index, image_record in enumerate(target_images, start=1):
            image_id = str(image_record["image_id"])
            existing = existing_records.get(image_id)
            if existing is not None and existing.status == "success" and not self.overwrite:
                processed_records.append(existing)
                stats.skipped += 1
                print(f"[{index}/{stats.total}] {image_id} skipped (existing success)", flush=True)
                continue

            memo_record = memos_by_id.get(str(image_record["memo_id"]))
            enriched_record = self._enrich_one(image_record, memo_record)
            processed_records.append(enriched_record)
            self._update_stats(stats, enriched_record)

            print(f"[{index}/{stats.total}] {image_id} {enriched_record.status}", flush=True)
        return processed_records

    def _process_initial_records_parallel(
        self,
        *,
        target_images: list[dict[str, Any]],
        existing_records: dict[str, EnrichedImageRecord],
        memos_by_id: dict[str, dict[str, Any]],
        stats: EnrichStats,
    ) -> list[EnrichedImageRecord]:
        processed_records: list[EnrichedImageRecord | None] = [None] * len(target_images)
        futures: dict[Future[EnrichedImageRecord], tuple[int, str]] = {}

        with ThreadPoolExecutor(max_workers=self.workers) as executor:
            for index, image_record in enumerate(target_images, start=1):
                image_id = str(image_record["image_id"])
                existing = existing_records.get(image_id)
                if existing is not None and existing.status == "success" and not self.overwrite:
                    processed_records[index - 1] = existing
                    stats.skipped += 1
                    print(
                        f"[{index}/{stats.total}] {image_id} skipped (existing success)",
                        flush=True,
                    )
                    continue

                memo_record = memos_by_id.get(str(image_record["memo_id"]))
                future = executor.submit(self._enrich_one, image_record, memo_record)
                futures[future] = (index, image_id)

            for future in as_completed(futures):
                index, image_id = futures[future]
                enriched_record = future.result()
                processed_records[index - 1] = enriched_record
                self._update_stats(stats, enriched_record)
                print(f"[{index}/{stats.total}] {image_id} {enriched_record.status}", flush=True)

        return [record for record in processed_records if record is not None]

    @staticmethod
    def _update_stats(stats: EnrichStats, enriched_record: EnrichedImageRecord) -> None:
        if enriched_record.status == "success":
            stats.success += 1
        elif enriched_record.status == "skipped":
            stats.skipped += 1
        else:
            stats.failed += 1

    def _retry_failed_records(
        self,
        processed_records: list[EnrichedImageRecord],
        target_images: list[dict[str, Any]],
        memos_by_id: dict[str, dict[str, Any]],
        stats: EnrichStats,
    ) -> None:
        if self.max_failed_retries <= 0:
            stats.retry_failed = self._count_failed(processed_records, target_images)
            return

        target_images_by_id = {str(record["image_id"]): record for record in target_images}

        for retry_round in range(1, self.max_failed_retries + 1):
            failed_positions = [
                (position, record)
                for position, record in enumerate(processed_records)
                if record.status == "failed" and record.image_id in target_images_by_id
            ]
            if not failed_positions:
                return

            stats.retry_rounds = retry_round
            print(
                "Retry "
                f"{retry_round}/{self.max_failed_retries}: "
                f"{len(failed_positions)} failed image(s)",
                flush=True,
            )

            for retry_index, (position, failed_record) in enumerate(failed_positions, start=1):
                image_record = target_images_by_id[failed_record.image_id]
                memo_record = memos_by_id.get(str(image_record["memo_id"]))
                retried_record = self._enrich_one(image_record, memo_record)
                processed_records[position] = retried_record
                stats.retry_attempts += 1

                if retried_record.status == "success":
                    stats.failed -= 1
                    stats.success += 1
                    stats.retry_success += 1
                elif retried_record.status == "skipped":
                    stats.failed -= 1
                    stats.skipped += 1

                print(
                    f"[retry {retry_round}/{self.max_failed_retries} "
                    f"{retry_index}/{len(failed_positions)}] "
                    f"{retried_record.image_id} {retried_record.status}",
                    flush=True,
                )

        stats.retry_failed = self._count_failed(processed_records, target_images)

    @staticmethod
    def _count_failed(
        processed_records: list[EnrichedImageRecord],
        target_images: list[dict[str, Any]],
    ) -> int:
        target_image_ids = {str(record["image_id"]) for record in target_images}
        return sum(
            1
            for record in processed_records
            if record.status == "failed" and record.image_id in target_image_ids
        )

    def _enrich_one(
        self,
        image_record: dict[str, Any],
        memo_record: dict[str, Any] | None,
    ) -> EnrichedImageRecord:
        image_id = str(image_record["image_id"])
        memo_id = str(image_record["memo_id"])
        relative_path = str(image_record["image_relpath"])
        source_relpath = str(image_record["source_relpath"])
        created_at = str(memo_record["created_at"]) if memo_record else ""
        month = self._get_month(memo_record)
        media_type = _detect_media_type(relative_path)

        base_payload = {
            "image_id": image_id,
            "memo_id": memo_id,
            "created_at": created_at,
            "month": month,
            "relative_path": relative_path,
            "source_relpath": source_relpath,
            "media_type": media_type,
            "model_name": self.provider.model_name,
            "prompt_version": self.provider.prompt_version,
            "run_id": self.run_id,
        }

        if not _is_supported_static_image(relative_path):
            return EnrichedImageRecord(
                **base_payload,
                ocr_text="",
                visual_description="",
                status="skipped",
                error_message=None,
            )

        absolute_path = self.project_root / relative_path
        if not absolute_path.exists():
            return EnrichedImageRecord(
                **base_payload,
                ocr_text="",
                visual_description="",
                status="failed",
                error_message=f"Image file not found: {relative_path}",
            )

        try:
            provider_result = self.provider.enrich(
                absolute_path,
                image_id=image_id,
                memo_id=memo_id,
            )
        except Exception as exc:  # pragma: no cover - defensive guard for future providers
            return EnrichedImageRecord(
                **base_payload,
                ocr_text="",
                visual_description="",
                status="failed",
                error_message=str(exc),
            )

        if provider_result.status == "failed":
            return EnrichedImageRecord(
                **base_payload,
                ocr_text=provider_result.ocr_text,
                visual_description=provider_result.visual_description,
                status="failed",
                error_message=provider_result.error_message or "Provider returned failed status",
            )

        return EnrichedImageRecord(
            **base_payload,
            ocr_text=provider_result.ocr_text,
            visual_description=provider_result.visual_description,
            status="success",
            error_message=provider_result.error_message,
        )

    @staticmethod
    def _get_month(memo_record: dict[str, Any] | None) -> str:
        if memo_record is None:
            return ""
        created_at = str(memo_record.get("created_at", ""))
        return created_at[:7] if len(created_at) >= 7 else ""
