from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from flomo_pipeline.chunk.models import (
    ChunkBuildStats,
    ChunkCreatedAtRange,
    ChunkRecord,
    ChunkSourceImage,
    ChunkSourceItem,
)
from flomo_pipeline.chunk.token_estimator import estimate_tokens


MONTHLY_FILE_SUFFIX = ".enriched.jsonl"
CHUNK_FILE_SUFFIX = ".json"
BUILD_VERSION = "chunk-v1"
STRATEGY = "sequential-size-pack:v1"


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    records: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            records.append(json.loads(line))
    return records


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _chunk_file_path(chunks_root: Path, month: str, chunk_id: str) -> Path:
    return chunks_root / month / f"{chunk_id}{CHUNK_FILE_SUFFIX}"


class ChunkBuildRunner:
    def __init__(
        self,
        *,
        monthly_root: Path,
        chunks_root: Path,
        month: str | None = None,
        target_tokens: int = 1200,
        hard_max_tokens: int = 1600,
        overwrite: bool = False,
    ) -> None:
        if target_tokens <= 0:
            raise ValueError("target_tokens must be positive")
        if hard_max_tokens <= 0:
            raise ValueError("hard_max_tokens must be positive")
        if target_tokens > hard_max_tokens:
            raise ValueError("target_tokens must not exceed hard_max_tokens")

        self.monthly_root = monthly_root
        self.chunks_root = chunks_root
        self.month = month
        self.target_tokens = target_tokens
        self.hard_max_tokens = hard_max_tokens
        self.overwrite = overwrite

    def run(self) -> tuple[dict[str, list[ChunkRecord]], ChunkBuildStats]:
        grouped_chunks: dict[str, list[ChunkRecord]] = {}
        stats = ChunkBuildStats()

        for month, monthly_path in self._discover_monthly_inputs():
            month_output_dir = self.chunks_root / month
            existing_chunk_files = sorted(month_output_dir.glob(f"*{CHUNK_FILE_SUFFIX}"))
            if existing_chunk_files and not self.overwrite:
                stats.months_skipped += 1
                print(f"[{month}] skipped (existing output)")
                continue

            monthly_records = _load_jsonl(monthly_path)
            if self.overwrite and month_output_dir.exists():
                for path in existing_chunk_files:
                    path.unlink()

            chunks = self._build_month_chunks(month=month, monthly_records=monthly_records)
            grouped_chunks[month] = chunks
            stats.months_built += 1
            stats.chunk_count += len(chunks)
            stats.memo_count += sum(chunk.source_count for chunk in chunks)

            month_output_dir.mkdir(parents=True, exist_ok=True)
            for chunk in chunks:
                _write_json(_chunk_file_path(self.chunks_root, month, chunk.chunk_id), chunk.to_dict())
            print(f"[{month}] built {len(chunks)} chunks from {len(monthly_records)} memos")

        return grouped_chunks, stats

    def _discover_monthly_inputs(self) -> list[tuple[str, Path]]:
        if self.month is not None:
            path = self.monthly_root / f"{self.month}{MONTHLY_FILE_SUFFIX}"
            if not path.exists():
                return []
            return [(self.month, path)]

        pairs: list[tuple[str, Path]] = []
        for path in sorted(self.monthly_root.glob(f"*{MONTHLY_FILE_SUFFIX}")):
            month = path.name[:7]
            pairs.append((month, path))
        return pairs

    def _build_month_chunks(self, *, month: str, monthly_records: list[dict[str, Any]]) -> list[ChunkRecord]:
        normalized_items = [self._normalize_monthly_record(record) for record in monthly_records]
        chunks: list[list[ChunkSourceItem]] = []
        current_chunk: list[ChunkSourceItem] = []
        current_estimate = 0

        for item in normalized_items:
            item_text = self._render_memo_block(item)
            item_tokens = estimate_tokens(item_text)

            if not current_chunk:
                current_chunk = [item]
                current_estimate = item_tokens
                continue

            if current_estimate + item_tokens <= self.target_tokens:
                current_chunk.append(item)
                current_estimate += item_tokens
                continue

            chunks.append(current_chunk)
            current_chunk = [item]
            current_estimate = item_tokens

        if current_chunk:
            chunks.append(current_chunk)

        built_chunks: list[ChunkRecord] = []
        for chunk_index, items in enumerate(chunks, start=1):
            chunk_id = f"{month}-{chunk_index:04d}"
            text = self._render_chunk_text(month=month, chunk_id=chunk_id, items=items)
            source_memo_ids = [item.memo_id for item in items]
            created_at_values = [item.created_at for item in items]
            built_chunks.append(
                ChunkRecord(
                    chunk_id=chunk_id,
                    month=month,
                    chunk_index=chunk_index,
                    source_memo_ids=source_memo_ids,
                    source_count=len(source_memo_ids),
                    created_at_range=ChunkCreatedAtRange(
                        start=min(created_at_values),
                        end=max(created_at_values),
                    ),
                    token_estimate=estimate_tokens(text),
                    text=text,
                    source_items=items,
                    build_version=BUILD_VERSION,
                    strategy=STRATEGY,
                    status="success",
                )
            )
        return built_chunks

    @staticmethod
    def _normalize_monthly_record(record: dict[str, Any]) -> ChunkSourceItem:
        images: list[ChunkSourceImage] = []
        for image in record.get("images", []):
            images.append(
                ChunkSourceImage(
                    image_id=str(image["image_id"]),
                    status=str(image["status"]),
                    media_type=str(image["media_type"]),
                    relative_path=str(image["relative_path"]),
                    source_relpath=str(image["source_relpath"]),
                    ocr_text=str(image.get("ocr_text", "") or ""),
                    visual_description=str(image.get("visual_description", "") or ""),
                    error_message=image.get("error_message"),
                )
            )

        return ChunkSourceItem(
            memo_id=str(record["memo_id"]),
            created_at=str(record["created_at"]),
            memo_text=str(record["memo_text"]),
            source_relpath=str(record["source_relpath"]),
            image_count_raw=int(record["image_count_raw"]),
            images=images,
        )

    def _render_chunk_text(self, *, month: str, chunk_id: str, items: list[ChunkSourceItem]) -> str:
        lines = [
            "[META]",
            f"month: {month}",
            f"chunk_id: {chunk_id}",
            f"source_count: {len(items)}",
            "",
        ]
        for index, item in enumerate(items):
            if index > 0:
                lines.append("")
            lines.extend(self._render_memo_block(item).splitlines())
        return "\n".join(lines).strip()

    @staticmethod
    def _render_memo_block(item: ChunkSourceItem) -> str:
        success_images = [image for image in item.images if image.status == "success"]
        skipped_images = [image for image in item.images if image.status == "skipped"]
        failed_images = [image for image in item.images if image.status == "failed"]

        lines = [
            "[MEMO]",
            f"memo_id: {item.memo_id}",
            f"created_at: {item.created_at}",
            "memo_text:",
            item.memo_text,
            "",
            "[IMAGES]",
            f"image_count_raw: {item.image_count_raw}",
            f"image_count_success: {len(success_images)}",
            f"image_count_skipped: {len(skipped_images)}",
            f"image_count_failed: {len(failed_images)}",
        ]

        for image in success_images:
            lines.extend(
                [
                    "",
                    "[IMAGE]",
                    f"image_id: {image.image_id}",
                ]
            )
            if image.ocr_text.strip():
                lines.extend(["ocr_text:", image.ocr_text])
            if image.visual_description.strip():
                lines.extend(["visual_description:", image.visual_description])

        return "\n".join(lines).strip()
