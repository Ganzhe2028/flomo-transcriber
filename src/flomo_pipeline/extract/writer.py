from __future__ import annotations

import shutil
from typing import TYPE_CHECKING

from flomo_pipeline.common.io import write_jsonl

if TYPE_CHECKING:
    from pathlib import Path

    from flomo_pipeline.common.models import ImageRecord, ParseResult


class StoreWriter:
    def __init__(self, store_root: Path) -> None:
        self.store_root = store_root
        self.memo_path = store_root / "memo.raw.jsonl"
        self.image_path = store_root / "image.raw.jsonl"
        self.missing_image_path = store_root / "missing_image.raw.jsonl"
        self.images_dir = store_root / "images"

    def write(self, result: ParseResult, raw_root: Path) -> None:
        self.store_root.mkdir(parents=True, exist_ok=True)
        self.images_dir.mkdir(parents=True, exist_ok=True)

        write_jsonl(self.memo_path, result.memos)
        write_jsonl(self.image_path, result.images)
        write_jsonl(self.missing_image_path, result.missing_images)
        self._copy_images(result.images, raw_root)

    def _copy_images(self, images: list[ImageRecord], raw_root: Path) -> None:
        for image in images:
            source = raw_root / image.source_relpath
            dest = self.store_root.parent / image.image_relpath
            dest.parent.mkdir(parents=True, exist_ok=True)
            if source.exists():
                shutil.copy2(source, dest)
