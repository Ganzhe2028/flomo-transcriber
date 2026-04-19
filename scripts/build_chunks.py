#!/usr/bin/env python3

from __future__ import annotations

import argparse
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from flomo_pipeline.chunk import ChunkBuildRunner


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Build llm chunk files from monthly/YYYY-MM.enriched.jsonl"
    )
    parser.add_argument(
        "--monthly-root",
        type=Path,
        default=Path("monthly"),
        help="Path to the monthly input root",
    )
    parser.add_argument(
        "--chunks-root",
        type=Path,
        default=Path("llm_chunks"),
        help="Path to the chunk output root",
    )
    parser.add_argument("--month", default=None, help="Build only one month, e.g. 2025-12")
    parser.add_argument("--target-tokens", type=int, default=1200, help="Soft target tokens per chunk")
    parser.add_argument("--hard-max-tokens", type=int, default=1600, help="Reserved hard ceiling for future use")
    parser.add_argument("--overwrite", action="store_true", help="Overwrite existing chunk files for target months")
    args = parser.parse_args()

    _, stats = ChunkBuildRunner(
        monthly_root=args.monthly_root.resolve(),
        chunks_root=args.chunks_root.resolve(),
        month=args.month,
        target_tokens=args.target_tokens,
        hard_max_tokens=args.hard_max_tokens,
        overwrite=args.overwrite,
    ).run()

    print(stats.format_summary())
    print(f"Output dir: {args.chunks_root.resolve()}")


if __name__ == "__main__":
    main()
