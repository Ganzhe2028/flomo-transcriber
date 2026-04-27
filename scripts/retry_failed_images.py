#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from flomo_pipeline.enrich import EnrichedImageValidator, ImageEnrichmentRunner
from flomo_pipeline.enrich.providers import build_provider


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    records: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            records.append(json.loads(line))
    return records


def _count_failed(enriched_path: Path, month: str | None) -> int:
    failed = 0
    for record in _load_jsonl(enriched_path):
        if record.get("status") != "failed":
            continue
        if month is not None and record.get("month") != month:
            continue
        failed += 1
    return failed


def main() -> None:
    parser = argparse.ArgumentParser(description="Retry existing failed image enrichment records")
    parser.add_argument(
        "--store-root",
        type=Path,
        default=Path("store"),
        help="Path to the store root",
    )
    parser.add_argument("--provider", default="lmstudio", help="Enrichment provider name")
    parser.add_argument("--month", default=None, help="Retry only one month, e.g. 2026-01")
    parser.add_argument("--rounds", type=int, default=3, help="Maximum retry rounds")
    parser.add_argument(
        "--workers",
        type=int,
        default=1,
        help="Number of images to process concurrently",
    )
    args = parser.parse_args()

    if args.rounds <= 0:
        print("Error: --rounds must be positive", file=sys.stderr)
        sys.exit(1)

    store_root = args.store_root.resolve()
    enriched_path = store_root / "image.enriched.jsonl"

    try:
        provider = build_provider(args.provider)
    except ValueError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)

    for round_index in range(1, args.rounds + 1):
        before = _count_failed(enriched_path, args.month)
        print(f"Retry round {round_index}/{args.rounds}")
        print(f"Failed before: {before}")
        if before == 0:
            break

        _, stats = ImageEnrichmentRunner(
            store_root=store_root,
            provider=provider,
            month=args.month,
            workers=args.workers,
            failed_only=True,
            max_failed_retries=0,
        ).run()

        print(stats.format_summary())

        report = EnrichedImageValidator(store_root=store_root).validate()
        print(report.format_summary())
        if not report.ok:
            sys.exit(1)

        after = _count_failed(enriched_path, args.month)
        print(f"Failed after: {after}")
        if after == 0:
            break

    print(f"Remaining failed: {_count_failed(enriched_path, args.month)}")


if __name__ == "__main__":
    main()
