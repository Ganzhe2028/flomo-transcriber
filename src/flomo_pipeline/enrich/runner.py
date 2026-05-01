from __future__ import annotations

import uuid
from concurrent.futures import Future, ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

from flomo_pipeline.common.io import read_jsonl, write_jsonl
from flomo_pipeline.enrich.models import EnrichedImageRecord, EnrichStats, EnrichStatus

if TYPE_CHECKING:
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
        status=cast("EnrichStatus", str(payload["status"])),
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
        retry_provider: EnrichmentProvider | None = None,
        month: str | None = None,
        overwrite: bool = False,
        run_id: str | None = None,
        project_root: Path | None = None,
        max_failed_retries: int = MAX_FAILED_RETRIES,
        workers: int = 1,
        failed_only: bool = False,
    ) -> None:
        if workers <= 0:
            raise ValueError("workers must be positive")
        self.store_root = store_root
        self.provider = provider
        self.retry_provider = retry_provider or provider
        self.month = month
        self.overwrite = overwrite
        self.run_id = run_id or uuid.uuid4().hex
        self.project_root = project_root or store_root.parent
        self.max_failed_retries = max_failed_retries
        self.workers = workers
        self.failed_only = failed_only
        self.memo_path = store_root / "memo.raw.jsonl"
        self.image_path = store_root / "image.raw.jsonl"
        self.enriched_path = store_root / "image.enriched.jsonl"

    def run(self) -> tuple[list[EnrichedImageRecord], EnrichStats]:
        memo_records = read_jsonl(self.memo_path)
        image_records = read_jsonl(self.image_path)
        existing_records = {
            record.image_id: record
            for record in (
                _record_from_dict(payload) for payload in read_jsonl(self.enriched_path)
            )
        }
        memos_by_id = {str(record["memo_id"]): record for record in memo_records}

        stats = EnrichStats()
        processed_records: list[EnrichedImageRecord] = []

        target_images = self._select_target_images(
            image_records=image_records,
            existing_records=existing_records,
            memos_by_id=memos_by_id,
        )
        target_image_ids = {str(record["image_id"]) for record in target_images}
        preserve_non_target_existing = self.month is not None or self.failed_only
        stats.total = len(target_images)

        processed_records = self._process_initial_records(
            target_images=target_images,
            existing_records=existing_records,
            memos_by_id=memos_by_id,
            stats=stats,
            target_image_ids=target_image_ids,
            preserve_non_target_existing=preserve_non_target_existing,
        )

        self._retry_failed_records(
            processed_records,
            target_images,
            memos_by_id,
            stats,
            existing_records=existing_records,
            target_image_ids=target_image_ids,
            preserve_non_target_existing=preserve_non_target_existing,
        )

        final_records = self._build_output_records(
            processed_records=processed_records,
            existing_records=existing_records,
            target_image_ids=target_image_ids,
            preserve_non_target_existing=preserve_non_target_existing,
        )
        write_jsonl(self.enriched_path, final_records, atomic=True)
        return final_records, stats

    def _select_target_images(
        self,
        *,
        image_records: list[dict[str, Any]],
        existing_records: dict[str, EnrichedImageRecord],
        memos_by_id: dict[str, dict[str, Any]],
    ) -> list[dict[str, Any]]:
        target_images = [
            record
            for record in image_records
            if self.month is None
            or self._get_month(memos_by_id.get(str(record["memo_id"]))) == self.month
        ]
        if not self.failed_only:
            return target_images

        failed_image_ids = {
            image_id
            for image_id, record in existing_records.items()
            if record.status == "failed"
        }
        return [record for record in target_images if str(record["image_id"]) in failed_image_ids]

    def _build_output_records(
        self,
        *,
        processed_records: list[EnrichedImageRecord],
        existing_records: dict[str, EnrichedImageRecord],
        target_image_ids: set[str],
        preserve_non_target_existing: bool,
    ) -> list[EnrichedImageRecord]:
        by_id: dict[str, EnrichedImageRecord] = {}
        if preserve_non_target_existing:
            by_id.update(existing_records)
        else:
            for image_id in target_image_ids:
                existing = existing_records.get(image_id)
                if existing is not None:
                    by_id[image_id] = existing

        for record in processed_records:
            by_id[record.image_id] = record

        return sorted(by_id.values(), key=lambda record: record.image_id)

    def _persist_progress(
        self,
        *,
        processed_records: list[EnrichedImageRecord],
        existing_records: dict[str, EnrichedImageRecord],
        target_image_ids: set[str],
        preserve_non_target_existing: bool,
    ) -> None:
        write_jsonl(
            self.enriched_path,
            self._build_output_records(
                processed_records=processed_records,
                existing_records=existing_records,
                target_image_ids=target_image_ids,
                preserve_non_target_existing=preserve_non_target_existing,
            ),
            atomic=True,
        )

    def _process_initial_records(
        self,
        *,
        target_images: list[dict[str, Any]],
        existing_records: dict[str, EnrichedImageRecord],
        memos_by_id: dict[str, dict[str, Any]],
        stats: EnrichStats,
        target_image_ids: set[str],
        preserve_non_target_existing: bool,
    ) -> list[EnrichedImageRecord]:
        if self.workers == 1:
            return self._process_initial_records_sequential(
                target_images=target_images,
                existing_records=existing_records,
                memos_by_id=memos_by_id,
                stats=stats,
                target_image_ids=target_image_ids,
                preserve_non_target_existing=preserve_non_target_existing,
            )
        return self._process_initial_records_parallel(
            target_images=target_images,
            existing_records=existing_records,
            memos_by_id=memos_by_id,
            stats=stats,
            target_image_ids=target_image_ids,
            preserve_non_target_existing=preserve_non_target_existing,
        )

    def _process_initial_records_sequential(
        self,
        *,
        target_images: list[dict[str, Any]],
        existing_records: dict[str, EnrichedImageRecord],
        memos_by_id: dict[str, dict[str, Any]],
        stats: EnrichStats,
        target_image_ids: set[str],
        preserve_non_target_existing: bool,
    ) -> list[EnrichedImageRecord]:
        processed_records: list[EnrichedImageRecord] = []
        for index, image_record in enumerate(target_images, start=1):
            image_id = str(image_record["image_id"])
            existing = existing_records.get(image_id)
            if existing is not None and existing.status == "success" and not self.overwrite:
                processed_records.append(existing)
                stats.skipped += 1
                self._persist_progress(
                    processed_records=processed_records,
                    existing_records=existing_records,
                    target_image_ids=target_image_ids,
                    preserve_non_target_existing=preserve_non_target_existing,
                )
                print(f"[{index}/{stats.total}] {image_id} skipped (existing success)", flush=True)
                continue

            memo_record = memos_by_id.get(str(image_record["memo_id"]))
            enriched_record = self._enrich_one(image_record, memo_record)
            processed_records.append(enriched_record)
            self._update_stats(stats, enriched_record)
            self._persist_progress(
                processed_records=processed_records,
                existing_records=existing_records,
                target_image_ids=target_image_ids,
                preserve_non_target_existing=preserve_non_target_existing,
            )

            print(f"[{index}/{stats.total}] {image_id} {enriched_record.status}", flush=True)
        return processed_records

    def _process_initial_records_parallel(
        self,
        *,
        target_images: list[dict[str, Any]],
        existing_records: dict[str, EnrichedImageRecord],
        memos_by_id: dict[str, dict[str, Any]],
        stats: EnrichStats,
        target_image_ids: set[str],
        preserve_non_target_existing: bool,
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
                    self._persist_progress(
                        processed_records=[
                            record for record in processed_records if record is not None
                        ],
                        existing_records=existing_records,
                        target_image_ids=target_image_ids,
                        preserve_non_target_existing=preserve_non_target_existing,
                    )
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
                self._persist_progress(
                    processed_records=[
                        record for record in processed_records if record is not None
                    ],
                    existing_records=existing_records,
                    target_image_ids=target_image_ids,
                    preserve_non_target_existing=preserve_non_target_existing,
                )
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
        *,
        existing_records: dict[str, EnrichedImageRecord],
        target_image_ids: set[str],
        preserve_non_target_existing: bool,
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
                retried_record = self._enrich_one(
                    image_record,
                    memo_record,
                    provider=self.retry_provider,
                )
                processed_records[position] = retried_record
                stats.retry_attempts += 1
                self._persist_progress(
                    processed_records=processed_records,
                    existing_records=existing_records,
                    target_image_ids=target_image_ids,
                    preserve_non_target_existing=preserve_non_target_existing,
                )

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
        *,
        provider: EnrichmentProvider | None = None,
    ) -> EnrichedImageRecord:
        active_provider = provider or self.provider
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
            "model_name": active_provider.model_name,
            "prompt_version": active_provider.prompt_version,
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
            provider_result = active_provider.enrich(
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
