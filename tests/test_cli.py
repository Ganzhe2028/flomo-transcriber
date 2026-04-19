from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

from tests.conftest import (
    FakeHTTPResponse,
    build_sample_raw,
    lmstudio_chat_response,
    run_fake_lmstudio_server,
)


def test_extract_and_validate_scripts(tmp_path: Path) -> None:
    repo_root = Path(__file__).resolve().parent.parent
    raw_root = build_sample_raw(tmp_path / "raw")
    store_root = tmp_path / "store"

    extract = subprocess.run(
        [
            sys.executable,
            str(repo_root / "scripts" / "extract_raw.py"),
            "--raw-root",
            str(raw_root),
            "--store-root",
            str(store_root),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert extract.returncode == 0, extract.stderr
    assert "Memos:" in extract.stdout
    assert (store_root / "memo.raw.jsonl").exists()

    validate = subprocess.run(
        [
            sys.executable,
            str(repo_root / "scripts" / "validate_store.py"),
            "--raw-root",
            str(raw_root),
            "--store-root",
            str(store_root),
            "--summary",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert validate.returncode == 0, validate.stdout + validate.stderr
    assert "Validation passed" in validate.stdout


def test_enrich_and_validate_enriched_scripts(tmp_path: Path) -> None:
    repo_root = Path(__file__).resolve().parent.parent
    raw_root = build_sample_raw(tmp_path / "raw")
    store_root = tmp_path / "store"

    extract = subprocess.run(
        [
            sys.executable,
            str(repo_root / "scripts" / "extract_raw.py"),
            "--raw-root",
            str(raw_root),
            "--store-root",
            str(store_root),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert extract.returncode == 0, extract.stderr

    enrich = subprocess.run(
        [
            sys.executable,
            str(repo_root / "scripts" / "enrich_images.py"),
            "--store-root",
            str(store_root),
            "--provider",
            "mock",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert enrich.returncode == 0, enrich.stdout + enrich.stderr
    assert "Success:" in enrich.stdout
    assert (store_root / "image.enriched.jsonl").exists()

    validate = subprocess.run(
        [
            sys.executable,
            str(repo_root / "scripts" / "validate_enriched_images.py"),
            "--store-root",
            str(store_root),
            "--summary",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert validate.returncode == 0, validate.stdout + validate.stderr
    assert "Validation passed" in validate.stdout


def test_enrich_lmstudio_script_happy_path(tmp_path: Path) -> None:
    repo_root = Path(__file__).resolve().parent.parent
    raw_root = build_sample_raw(tmp_path / "raw")
    store_root = tmp_path / "store"

    extract = subprocess.run(
        [
            sys.executable,
            str(repo_root / "scripts" / "extract_raw.py"),
            "--raw-root",
            str(raw_root),
            "--store-root",
            str(store_root),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert extract.returncode == 0, extract.stderr

    with run_fake_lmstudio_server(
        [
            FakeHTTPResponse(
                status=200,
                body=lmstudio_chat_response(
                    '{"ocr_text":"photo text","visual_description":"First fixture image."}'
                ),
            ),
            FakeHTTPResponse(
                status=200,
                body=lmstudio_chat_response(
                    '{"ocr_text":"","visual_description":"Second fixture image."}'
                ),
            ),
        ]
    ) as server:
        env = os.environ.copy()
        env["FLOMO_VLM_BASE_URL"] = server.url
        env["FLOMO_VLM_MODEL"] = "local-vlm"
        env["FLOMO_VLM_TIMEOUT_SECONDS"] = "2"

        enrich = subprocess.run(
            [
                sys.executable,
                str(repo_root / "scripts" / "enrich_images.py"),
                "--store-root",
                str(store_root),
                "--provider",
                "lmstudio",
            ],
            capture_output=True,
            text=True,
            check=False,
            env=env,
        )

    assert enrich.returncode == 0, enrich.stdout + enrich.stderr
    assert "Success:" in enrich.stdout
    assert (store_root / "image.enriched.jsonl").exists()
    assert len(server.requests) == 2

    validate = subprocess.run(
        [
            sys.executable,
            str(repo_root / "scripts" / "validate_enriched_images.py"),
            "--store-root",
            str(store_root),
            "--summary",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert validate.returncode == 0, validate.stdout + validate.stderr
    assert "Validation passed" in validate.stdout


def test_enrich_lmstudio_script_retries_failed_records(tmp_path: Path) -> None:
    repo_root = Path(__file__).resolve().parent.parent
    raw_root = build_sample_raw(tmp_path / "raw")
    store_root = tmp_path / "store"

    extract = subprocess.run(
        [
            sys.executable,
            str(repo_root / "scripts" / "extract_raw.py"),
            "--raw-root",
            str(raw_root),
            "--store-root",
            str(store_root),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert extract.returncode == 0, extract.stderr

    with run_fake_lmstudio_server(
        [
            FakeHTTPResponse(status=500, body={"error": "temporary failure"}),
            FakeHTTPResponse(
                status=200,
                body=lmstudio_chat_response(
                    '{"ocr_text":"","visual_description":"Second fixture image."}'
                ),
            ),
            FakeHTTPResponse(
                status=200,
                body=lmstudio_chat_response(
                    '{"ocr_text":"retried text","visual_description":""}'
                ),
            ),
        ]
    ) as server:
        env = os.environ.copy()
        env["FLOMO_VLM_BASE_URL"] = server.url
        env["FLOMO_VLM_MODEL"] = "local-vlm"
        env["FLOMO_VLM_TIMEOUT_SECONDS"] = "2"

        enrich = subprocess.run(
            [
                sys.executable,
                str(repo_root / "scripts" / "enrich_images.py"),
                "--store-root",
                str(store_root),
                "--provider",
                "lmstudio",
            ],
            capture_output=True,
            text=True,
            check=False,
            env=env,
        )

    assert enrich.returncode == 0, enrich.stdout + enrich.stderr
    assert "Retry attempts: 1" in enrich.stdout
    assert "Retry success: 1" in enrich.stdout
    assert len(server.requests) == 3

    records = [
        json.loads(line)
        for line in (store_root / "image.enriched.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    assert {record["status"] for record in records} == {"success"}


def test_probe_lmstudio_script_happy_path(tmp_path: Path) -> None:
    repo_root = Path(__file__).resolve().parent.parent
    image_path = tmp_path / "probe.png"
    image_path.write_bytes(b"\x89PNG\r\n\x1a\n")

    with run_fake_lmstudio_server(
        [
            FakeHTTPResponse(
                status=200,
                body=lmstudio_chat_response(
                    '{"ocr_text":"probe text","visual_description":"Probe image."}'
                ),
            )
        ]
    ) as server:
        env = os.environ.copy()
        env["FLOMO_VLM_BASE_URL"] = server.url
        env["FLOMO_VLM_MODEL"] = "local-vlm"
        env["FLOMO_VLM_TIMEOUT_SECONDS"] = "2"

        probe = subprocess.run(
            [
                sys.executable,
                str(repo_root / "scripts" / "probe_lmstudio_vlm.py"),
                "--image",
                str(image_path),
            ],
            capture_output=True,
            text=True,
            check=False,
            env=env,
        )

    assert probe.returncode == 0, probe.stdout + probe.stderr
    assert "Status: success" in probe.stdout
    assert "OCR text: probe text" in probe.stdout
    assert "Raw response:" in probe.stdout


def test_merge_and_validate_monthly_scripts(tmp_path: Path) -> None:
    repo_root = Path(__file__).resolve().parent.parent
    raw_root = build_sample_raw(tmp_path / "raw")
    store_root = tmp_path / "store"
    monthly_root = tmp_path / "monthly"

    extract = subprocess.run(
        [
            sys.executable,
            str(repo_root / "scripts" / "extract_raw.py"),
            "--raw-root",
            str(raw_root),
            "--store-root",
            str(store_root),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert extract.returncode == 0, extract.stderr

    enrich = subprocess.run(
        [
            sys.executable,
            str(repo_root / "scripts" / "enrich_images.py"),
            "--store-root",
            str(store_root),
            "--provider",
            "mock",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert enrich.returncode == 0, enrich.stdout + enrich.stderr

    merge = subprocess.run(
        [
            sys.executable,
            str(repo_root / "scripts" / "merge_monthly.py"),
            "--store-root",
            str(store_root),
            "--monthly-root",
            str(monthly_root),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert merge.returncode == 0, merge.stdout + merge.stderr
    assert "Monthly files written" in merge.stdout
    assert (monthly_root / "2026-03.enriched.jsonl").exists()

    validate = subprocess.run(
        [
            sys.executable,
            str(repo_root / "scripts" / "validate_monthly.py"),
            "--store-root",
            str(store_root),
            "--monthly-root",
            str(monthly_root),
            "--summary",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert validate.returncode == 0, validate.stdout + validate.stderr
    assert "Validation passed" in validate.stdout


def test_build_and_validate_chunks_scripts(tmp_path: Path) -> None:
    repo_root = Path(__file__).resolve().parent.parent
    raw_root = build_sample_raw(tmp_path / "raw")
    store_root = tmp_path / "store"
    monthly_root = tmp_path / "monthly"
    chunks_root = tmp_path / "llm_chunks"

    for command in [
        [
            sys.executable,
            str(repo_root / "scripts" / "extract_raw.py"),
            "--raw-root",
            str(raw_root),
            "--store-root",
            str(store_root),
        ],
        [
            sys.executable,
            str(repo_root / "scripts" / "enrich_images.py"),
            "--store-root",
            str(store_root),
            "--provider",
            "mock",
        ],
        [
            sys.executable,
            str(repo_root / "scripts" / "merge_monthly.py"),
            "--store-root",
            str(store_root),
            "--monthly-root",
            str(monthly_root),
        ],
    ]:
        result = subprocess.run(command, capture_output=True, text=True, check=False)
        assert result.returncode == 0, result.stdout + result.stderr

    build = subprocess.run(
        [
            sys.executable,
            str(repo_root / "scripts" / "build_chunks.py"),
            "--monthly-root",
            str(monthly_root),
            "--chunks-root",
            str(chunks_root),
            "--month",
            "2026-03",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert build.returncode == 0, build.stdout + build.stderr
    assert "Chunks written" in build.stdout
    assert (chunks_root / "2026-03" / "2026-03-0001.json").exists()

    validate = subprocess.run(
        [
            sys.executable,
            str(repo_root / "scripts" / "validate_chunks.py"),
            "--monthly-root",
            str(monthly_root),
            "--chunks-root",
            str(chunks_root),
            "--month",
            "2026-03",
            "--summary",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert validate.returncode == 0, validate.stdout + validate.stderr
    assert "Validation passed" in validate.stdout


def test_build_and_validate_reports_scripts(tmp_path: Path) -> None:
    repo_root = Path(__file__).resolve().parent.parent
    raw_root = build_sample_raw(tmp_path / "raw")
    store_root = tmp_path / "store"
    monthly_root = tmp_path / "monthly"
    chunks_root = tmp_path / "llm_chunks"
    reports_root = tmp_path / "reports"

    for command in [
        [
            sys.executable,
            str(repo_root / "scripts" / "extract_raw.py"),
            "--raw-root",
            str(raw_root),
            "--store-root",
            str(store_root),
        ],
        [
            sys.executable,
            str(repo_root / "scripts" / "enrich_images.py"),
            "--store-root",
            str(store_root),
            "--provider",
            "mock",
        ],
        [
            sys.executable,
            str(repo_root / "scripts" / "merge_monthly.py"),
            "--store-root",
            str(store_root),
            "--monthly-root",
            str(monthly_root),
        ],
        [
            sys.executable,
            str(repo_root / "scripts" / "build_chunks.py"),
            "--monthly-root",
            str(monthly_root),
            "--chunks-root",
            str(chunks_root),
        ],
    ]:
        result = subprocess.run(command, capture_output=True, text=True, check=False)
        assert result.returncode == 0, result.stdout + result.stderr

    build = subprocess.run(
        [
            sys.executable,
            str(repo_root / "scripts" / "build_reports.py"),
            "--chunks-root",
            str(chunks_root),
            "--reports-root",
            str(reports_root),
            "--provider",
            "mock",
            "--month",
            "2026-03",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert build.returncode == 0, build.stdout + build.stderr
    assert "Reports written: 1" in build.stdout
    assert (reports_root / "2026-03.report.md").exists()
    assert (reports_root / "2026-03.report.json").exists()

    validate = subprocess.run(
        [
            sys.executable,
            str(repo_root / "scripts" / "validate_reports.py"),
            "--chunks-root",
            str(chunks_root),
            "--reports-root",
            str(reports_root),
            "--month",
            "2026-03",
            "--summary",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert validate.returncode == 0, validate.stdout + validate.stderr
    assert "Validation passed" in validate.stdout


def test_run_pipeline_script_happy_path(tmp_path: Path) -> None:
    repo_root = Path(__file__).resolve().parent.parent
    raw_root = build_sample_raw(tmp_path / "raw")
    store_root = tmp_path / "store"
    monthly_root = tmp_path / "monthly"
    chunks_root = tmp_path / "llm_chunks"
    reports_root = tmp_path / "reports"

    extract = subprocess.run(
        [
            sys.executable,
            str(repo_root / "scripts" / "extract_raw.py"),
            "--raw-root",
            str(raw_root),
            "--store-root",
            str(store_root),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert extract.returncode == 0, extract.stderr

    enrich = subprocess.run(
        [
            sys.executable,
            str(repo_root / "scripts" / "enrich_images.py"),
            "--store-root",
            str(store_root),
            "--provider",
            "mock",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert enrich.returncode == 0, enrich.stdout + enrich.stderr

    pipeline = subprocess.run(
        [
            sys.executable,
            str(repo_root / "scripts" / "run_pipeline.py"),
            "--store-root",
            str(store_root),
            "--monthly-root",
            str(monthly_root),
            "--chunks-root",
            str(chunks_root),
            "--reports-root",
            str(reports_root),
            "--month",
            "2026-03",
            "--report-provider",
            "mock",
        ],
        capture_output=True,
        text=True,
        check=False,
        cwd=repo_root,
    )
    assert pipeline.returncode == 0, pipeline.stdout + pipeline.stderr
    assert (reports_root / "2026-03.report.md").exists()
