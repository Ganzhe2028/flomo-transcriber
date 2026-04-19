#!/usr/bin/env python3

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from flomo_pipeline.extract import StoreValidator


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate the Stage 1 raw truth layer")
    parser.add_argument("--store-root", type=Path, default=Path("store"), help="Path to the store root")
    parser.add_argument("--raw-root", type=Path, default=None, help="Optional raw root override")
    parser.add_argument("--project-root", type=Path, default=None, help="Optional project root override")
    parser.add_argument("--strict", action="store_true", help="Treat warnings as errors")
    parser.add_argument("--summary", action="store_true", help="Print only the summary line")
    args = parser.parse_args()

    store_root = args.store_root.resolve()
    raw_root = args.raw_root.resolve() if args.raw_root else None
    project_root = args.project_root.resolve() if args.project_root else None

    report = StoreValidator(
        store_root=store_root,
        project_root=project_root,
        raw_root=raw_root,
    ).validate()

    if args.summary:
        print(report.format_summary())
    else:
        print(report.format_detail())

    if not report.ok:
        sys.exit(1)
    if args.strict and report.warnings:
        sys.exit(1)


if __name__ == "__main__":
    main()
