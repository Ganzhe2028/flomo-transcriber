#!/usr/bin/env python3

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path


def _run(command: list[str]) -> None:
    print("$ " + " ".join(command))
    result = subprocess.run(command, check=False)
    if result.returncode != 0:
        raise SystemExit(result.returncode)


def _add_month(command: list[str], month: str | None) -> list[str]:
    if month is None:
        return command
    return [*command, "--month", month]


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the local flomo-pipeline stages")
    parser.add_argument("--store-root", type=Path, default=Path("store"))
    parser.add_argument("--monthly-root", type=Path, default=Path("monthly"))
    parser.add_argument("--chunks-root", type=Path, default=Path("llm_chunks"))
    parser.add_argument("--reports-root", type=Path, default=Path("reports"))
    parser.add_argument("--month", default=None, help="Run only one month, e.g. 2025-12")
    parser.add_argument(
        "--enrich-provider",
        choices=["none", "mock", "lmstudio"],
        default="none",
        help="Run Stage 2 before derived stages",
    )
    parser.add_argument(
        "--report-provider",
        choices=["mock", "lmstudio"],
        default="mock",
        help="Provider for Stage 5 report generation",
    )
    parser.add_argument("--overwrite-enrich", action="store_true")
    parser.add_argument(
        "--no-overwrite-chunks",
        dest="overwrite_chunks",
        action="store_false",
        help="Do not overwrite existing Stage 4 chunk files",
    )
    parser.add_argument(
        "--no-overwrite-reports",
        dest="overwrite_reports",
        action="store_false",
        help="Do not overwrite existing Stage 5 reports",
    )
    parser.set_defaults(overwrite_chunks=True, overwrite_reports=True)
    args = parser.parse_args()

    python = sys.executable
    store_root = str(args.store_root)
    monthly_root = str(args.monthly_root)
    chunks_root = str(args.chunks_root)
    reports_root = str(args.reports_root)

    if args.enrich_provider != "none":
        command = [
            python,
            "scripts/enrich_images.py",
            "--store-root",
            store_root,
            "--provider",
            args.enrich_provider,
        ]
        command = _add_month(command, args.month)
        if args.overwrite_enrich:
            command.append("--overwrite")
        _run(command)

    _run([python, "scripts/validate_enriched_images.py", "--store-root", store_root, "--summary"])
    _run(
        _add_month(
            [
                python,
                "scripts/merge_monthly.py",
                "--store-root",
                store_root,
                "--monthly-root",
                monthly_root,
            ],
            args.month,
        )
    )
    _run(
        _add_month(
            [
                python,
                "scripts/validate_monthly.py",
                "--store-root",
                store_root,
                "--monthly-root",
                monthly_root,
                "--summary",
            ],
            args.month,
        )
    )

    build_chunks_command = [
        python,
        "scripts/build_chunks.py",
        "--monthly-root",
        monthly_root,
        "--chunks-root",
        chunks_root,
    ]
    build_chunks_command = _add_month(build_chunks_command, args.month)
    if args.overwrite_chunks:
        build_chunks_command.append("--overwrite")
    _run(build_chunks_command)

    _run(
        _add_month(
            [
                python,
                "scripts/validate_chunks.py",
                "--monthly-root",
                monthly_root,
                "--chunks-root",
                chunks_root,
                "--summary",
            ],
            args.month,
        )
    )

    build_reports_command = [
        python,
        "scripts/build_reports.py",
        "--chunks-root",
        chunks_root,
        "--reports-root",
        reports_root,
        "--provider",
        args.report_provider,
    ]
    build_reports_command = _add_month(build_reports_command, args.month)
    if args.overwrite_reports:
        build_reports_command.append("--overwrite")
    _run(build_reports_command)

    _run(
        _add_month(
            [
                python,
                "scripts/validate_reports.py",
                "--chunks-root",
                chunks_root,
                "--reports-root",
                reports_root,
                "--summary",
            ],
            args.month,
        )
    )


if __name__ == "__main__":
    main()
