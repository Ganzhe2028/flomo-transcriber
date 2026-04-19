#!/usr/bin/env python3

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from flomo_pipeline.extract import FlomoParser, StoreWriter


def main() -> None:
    parser = argparse.ArgumentParser(description="Build the Stage 1 raw truth layer from flomo exports")
    parser.add_argument("--raw-root", type=Path, default=Path("raw"), help="Path to the raw export root")
    parser.add_argument("--store-root", type=Path, default=Path("store"), help="Path to the store root")
    args = parser.parse_args()

    raw_root = args.raw_root.resolve()
    store_root = args.store_root.resolve()

    if not raw_root.is_dir():
        print(f"Error: raw directory not found: {raw_root}", file=sys.stderr)
        sys.exit(1)

    result = FlomoParser(raw_root=raw_root, store_root=store_root).parse_all()
    StoreWriter(store_root=store_root).write(result, raw_root=raw_root)

    print(f"Memos:          {len(result.memos)}")
    print(f"Images:         {len(result.images)}")
    print(f"Missing images: {len(result.missing_images)}")
    print(f"Memo JSONL:     {store_root / 'memo.raw.jsonl'}")
    print(f"Image JSONL:    {store_root / 'image.raw.jsonl'}")
    print(f"Missing JSONL:  {store_root / 'missing_image.raw.jsonl'}")


if __name__ == "__main__":
    main()
