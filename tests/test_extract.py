from __future__ import annotations

import json
from pathlib import Path

from flomo_pipeline.extract import FlomoParser, StoreWriter


def test_parse_all_returns_stage1_records(sample_raw_root: Path, tmp_path: Path) -> None:
    store_root = tmp_path / "store"
    result = FlomoParser(raw_root=sample_raw_root, store_root=store_root).parse_all()

    assert len(result.memos) == 3
    assert len(result.images) == 2
    assert len(result.missing_images) == 1

    first_memo = result.memos[0]
    assert first_memo.memo_id == "flomo-exampleuser-20260304--0001"
    assert first_memo.source_relpath == "2026/flomo@ExampleUser-20260304/ExampleUser的笔记.html"
    assert first_memo.batch_label == "20260304"
    assert first_memo.ordinal == 1

    second_image = result.images[1]
    assert second_image.memo_id == "flomo-exampleuser-20260304--0003"
    assert second_image.ordinal == 2
    assert second_image.image_relpath.startswith("store/images/2026/2026-03/")

    missing_image = result.missing_images[0]
    assert missing_image.image_id == "flomo-exampleuser-20260304--0003--01"
    assert missing_image.reason == "source_file_missing"


def test_writer_writes_stage1_filenames_and_copies_images(sample_raw_root: Path, tmp_path: Path) -> None:
    store_root = tmp_path / "store"
    result = FlomoParser(raw_root=sample_raw_root, store_root=store_root).parse_all()
    StoreWriter(store_root=store_root).write(result, raw_root=sample_raw_root)

    assert (store_root / "memo.raw.jsonl").exists()
    assert (store_root / "image.raw.jsonl").exists()
    assert (store_root / "missing_image.raw.jsonl").exists()

    memo_lines = (store_root / "memo.raw.jsonl").read_text(encoding="utf-8").strip().splitlines()
    image_lines = (store_root / "image.raw.jsonl").read_text(encoding="utf-8").strip().splitlines()
    missing_lines = (
        store_root / "missing_image.raw.jsonl"
    ).read_text(encoding="utf-8").strip().splitlines()

    assert len(memo_lines) == 3
    assert len(image_lines) == 2
    assert len(missing_lines) == 1

    image_record = json.loads(image_lines[0])
    copied_image_path = tmp_path / image_record["image_relpath"]
    assert copied_image_path.exists()
