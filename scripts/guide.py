#!/usr/bin/env python3

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Sequence


PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

PLACEHOLDER_VALUES = {
    "",
    "<your-vision-model-name>",
    "<你的视觉模型名>",
    "your-local-vision-model",
}


def _project_path(path: Path) -> Path:
    if path.is_absolute():
        return path
    return (PROJECT_ROOT / path).resolve()


def _display_path(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(PROJECT_ROOT))
    except ValueError:
        return str(path)


def _python_executable() -> str:
    venv = os.getenv("VIRTUAL_ENV", "").strip()
    if not venv:
        return sys.executable

    venv_root = Path(venv)
    if os.name == "nt":
        candidate = venv_root / "Scripts" / "python.exe"
    else:
        candidate = venv_root / "bin" / "python"
    if candidate.exists():
        return str(candidate)
    return sys.executable


def _load_env_file(path: Path) -> list[str]:
    if not path.exists():
        return []

    loaded: list[str] = []
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line.removeprefix("export ").strip()
        if "=" not in line:
            continue

        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()
        if not key:
            continue
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
            value = value[1:-1]

        if key not in os.environ:
            os.environ[key] = value
            loaded.append(key)

    return loaded


def _run(command: Sequence[str]) -> None:
    print("$ " + " ".join(command))
    result = subprocess.run(command, cwd=PROJECT_ROOT, check=False)
    if result.returncode != 0:
        raise SystemExit(result.returncode)


def _with_month(command: list[str], month: str | None) -> list[str]:
    if not month:
        return command
    return [*command, "--month", month]


def _require_vlm_config(*, include_retry: bool = False) -> None:
    missing: list[str] = []
    if not os.getenv("FLOMO_VLM_BASE_URL", "").strip():
        missing.append("FLOMO_VLM_BASE_URL")

    model = os.getenv("FLOMO_VLM_MODEL", "").strip()
    if model in PLACEHOLDER_VALUES:
        missing.append("FLOMO_VLM_MODEL")

    if missing:
        print(
            "Missing LM Studio configuration: "
            + ", ".join(missing)
            + ". Copy .env.example to .env and set your real vision model name.",
            file=sys.stderr,
        )
        raise SystemExit(2)

    print(f"vlm_model={model}")
    if include_retry:
        from flomo_pipeline.enrich.retry_config import resolve_lmstudio_retry_model_name

        try:
            resolution = resolve_lmstudio_retry_model_name(base_model_name=model)
        except ValueError as exc:
            print(f"Error: {exc}", file=sys.stderr)
            raise SystemExit(2) from exc
        if resolution.warning is not None:
            print(f"Warning: {resolution.warning}", file=sys.stderr)
        print(f"retry_vlm_model={resolution.model_name or model}")


def _prompt_action() -> str | None:
    print("flomo-transcriber guide")
    print("1. First run: build LLM chunks from raw/")
    print("2. Daily update: refresh LLM chunks after raw/ changes")
    print("3. Probe one image with LM Studio")
    print("4. Retry failed image records")
    print("q. Quit")
    choice = input("Choose: ").strip().lower()
    actions = {
        "1": "first",
        "2": "daily",
        "3": "probe",
        "4": "retry",
        "q": None,
        "quit": None,
        "exit": None,
    }
    if choice not in actions:
        print("Unknown choice.", file=sys.stderr)
        raise SystemExit(2)
    return actions[choice]


def _prompt_month() -> str | None:
    month = input("Month YYYY-MM, or empty for all months: ").strip()
    return month or None


def _prompt_provider() -> str:
    provider = input("Image provider [lmstudio/mock] (default lmstudio): ").strip().lower()
    if not provider:
        return "lmstudio"
    if provider not in {"lmstudio", "mock"}:
        print("Provider must be lmstudio or mock.", file=sys.stderr)
        raise SystemExit(2)
    return provider


def _prompt_image() -> Path:
    image = input("Image path: ").strip()
    if not image:
        print("Image path is required.", file=sys.stderr)
        raise SystemExit(2)
    return Path(image)


def _build_chunks_from_raw(
    *,
    raw_root: Path,
    store_root: Path,
    monthly_root: Path,
    chunks_root: Path,
    provider: str,
    month: str | None,
    workers: int,
) -> None:
    if provider == "lmstudio":
        _require_vlm_config(include_retry=True)

    python = _python_executable()
    raw = str(raw_root)
    store = str(store_root)
    monthly = str(monthly_root)
    chunks = str(chunks_root)

    _run([python, "scripts/extract_raw.py", "--raw-root", raw, "--store-root", store])
    _run(
        [
            python,
            "scripts/validate_store.py",
            "--raw-root",
            raw,
            "--store-root",
            store,
            "--summary",
        ]
    )

    enrich_command = [
        python,
        "scripts/enrich_images.py",
        "--store-root",
        store,
        "--provider",
        provider,
    ]
    enrich_command = _with_month(enrich_command, month)
    if workers > 1:
        enrich_command.extend(["--workers", str(workers)])
    _run(enrich_command)

    _run([python, "scripts/validate_enriched_images.py", "--store-root", store, "--summary"])

    _run(
        _with_month(
            [
                python,
                "scripts/merge_monthly.py",
                "--store-root",
                store,
                "--monthly-root",
                monthly,
            ],
            month,
        )
    )
    _run(
        _with_month(
            [
                python,
                "scripts/validate_monthly.py",
                "--store-root",
                store,
                "--monthly-root",
                monthly,
                "--summary",
            ],
            month,
        )
    )

    _run(
        _with_month(
            [
                python,
                "scripts/build_chunks.py",
                "--monthly-root",
                monthly,
                "--chunks-root",
                chunks,
                "--overwrite",
            ],
            month,
        )
    )
    _run(
        _with_month(
            [
                python,
                "scripts/validate_chunks.py",
                "--monthly-root",
                monthly,
                "--chunks-root",
                chunks,
                "--summary",
            ],
            month,
        )
    )

    if month:
        print(f"Ready for external LLM input: {_display_path(chunks_root / month)}")
    else:
        print(f"Ready for external LLM input: {_display_path(chunks_root / 'YYYY-MM')}")


def _probe_image(image: Path) -> None:
    _require_vlm_config()
    image_path = _project_path(image)
    _run([_python_executable(), "scripts/probe_lmstudio_vlm.py", "--image", str(image_path)])


def _retry_failed_images(
    *,
    store_root: Path,
    provider: str,
    month: str | None,
    rounds: int,
    workers: int,
) -> None:
    if provider == "lmstudio":
        _require_vlm_config(include_retry=True)

    command = [
        _python_executable(),
        "scripts/retry_failed_images.py",
        "--store-root",
        str(store_root),
        "--provider",
        provider,
        "--rounds",
        str(rounds),
    ]
    command = _with_month(command, month)
    if workers > 1:
        command.extend(["--workers", str(workers)])
    _run(command)


def main() -> None:
    parser = argparse.ArgumentParser(description="Guided flomo-transcriber workflow")
    parser.add_argument(
        "--action",
        choices=["first", "daily", "probe", "retry"],
        default=None,
        help="Skip the menu and run one guide action",
    )
    parser.add_argument("--env-file", type=Path, default=Path(".env"))
    parser.add_argument("--raw-root", type=Path, default=Path("raw"))
    parser.add_argument("--store-root", type=Path, default=Path("store"))
    parser.add_argument("--monthly-root", type=Path, default=Path("monthly"))
    parser.add_argument("--chunks-root", type=Path, default=Path("llm_chunks"))
    parser.add_argument("--month", default=None, help="Run one month, e.g. 2025-12")
    parser.add_argument("--provider", choices=["lmstudio", "mock"], default=None)
    parser.add_argument("--image", type=Path, default=None)
    parser.add_argument("--rounds", type=int, default=3)
    parser.add_argument("--workers", type=int, default=1)
    args = parser.parse_args()

    if args.rounds <= 0:
        print("--rounds must be greater than 0.", file=sys.stderr)
        raise SystemExit(2)
    if args.workers <= 0:
        print("--workers must be greater than 0.", file=sys.stderr)
        raise SystemExit(2)

    env_file = _project_path(args.env_file)
    loaded = _load_env_file(env_file)
    if loaded:
        print(f"Loaded configuration: {_display_path(env_file)}")

    interactive = args.action is None
    action = args.action or _prompt_action()
    if action is None:
        return

    month = _prompt_month() if interactive and action in {"first", "daily", "retry"} else args.month
    provider = args.provider
    if action in {"first", "daily", "retry"}:
        provider = provider or (_prompt_provider() if interactive else "lmstudio")

    raw_root = _project_path(args.raw_root)
    store_root = _project_path(args.store_root)
    monthly_root = _project_path(args.monthly_root)
    chunks_root = _project_path(args.chunks_root)

    if action in {"first", "daily"}:
        _build_chunks_from_raw(
            raw_root=raw_root,
            store_root=store_root,
            monthly_root=monthly_root,
            chunks_root=chunks_root,
            provider=provider or "lmstudio",
            month=month,
            workers=args.workers,
        )
        return

    if action == "probe":
        image = args.image or (_prompt_image() if interactive else None)
        if image is None:
            print("--image is required for probe.", file=sys.stderr)
            raise SystemExit(2)
        _probe_image(image)
        return

    if action == "retry":
        _retry_failed_images(
            store_root=store_root,
            provider=provider or "lmstudio",
            month=month,
            rounds=args.rounds,
            workers=args.workers,
        )
        return

    raise AssertionError(f"Unhandled action: {action}")


if __name__ == "__main__":
    main()
