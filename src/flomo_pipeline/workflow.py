from __future__ import annotations

import json
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

from flomo_pipeline.chunk import ChunkBuildRunner, ChunkValidator
from flomo_pipeline.enrich import EnrichedImageValidator, ImageEnrichmentRunner
from flomo_pipeline.enrich.providers import build_provider
from flomo_pipeline.enrich.providers.lmstudio_openai import LMStudioEnrichmentProvider
from flomo_pipeline.enrich.retry_config import resolve_lmstudio_retry_model_name
from flomo_pipeline.extract import FlomoParser, StoreValidator, StoreWriter
from flomo_pipeline.merge import MonthlyMergeRunner, MonthlyValidator

if TYPE_CHECKING:
    from flomo_pipeline.enrich.provider import EnrichmentProvider

PLACEHOLDER_VALUES = {
    "",
    "<your-vision-model-name>",
    "<你的视觉模型名>",
    "your-local-vision-model",
}


@dataclass(frozen=True)
class WorkflowPaths:
    project_root: Path
    raw_root: Path
    store_root: Path
    monthly_root: Path
    chunks_root: Path


@dataclass(frozen=True)
class WorkflowOptions:
    provider: str = "lmstudio"
    month: str | None = None
    image: Path | None = None
    rounds: int = 3
    workers: int = 1


def project_path(project_root: Path, path: Path) -> Path:
    if path.is_absolute():
        return path
    return (project_root / path).resolve()


def display_path(project_root: Path, path: Path) -> str:
    try:
        return str(path.resolve().relative_to(project_root))
    except ValueError:
        return str(path)


def python_executable() -> str:
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


def load_env_file(path: Path) -> list[str]:
    if not path.exists():
        return []

    loaded: list[str] = []
    for raw_line in path.read_text(encoding="utf-8").split("\n"):
        line = raw_line.rstrip("\r")
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


def require_vlm_config(*, include_retry: bool = False) -> None:
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
        try:
            resolution = resolve_lmstudio_retry_model_name(base_model_name=model)
        except ValueError as exc:
            print(f"Error: {exc}", file=sys.stderr)
            raise SystemExit(2) from exc
        if resolution.warning is not None:
            print(f"Warning: {resolution.warning}", file=sys.stderr)
        print(f"retry_vlm_model={resolution.model_name or model}")


def run_action(action: str, paths: WorkflowPaths, options: WorkflowOptions) -> None:
    if options.rounds <= 0:
        print("--rounds must be greater than 0.", file=sys.stderr)
        raise SystemExit(2)
    if options.workers <= 0:
        print("--workers must be greater than 0.", file=sys.stderr)
        raise SystemExit(2)

    if action in {"first", "daily"}:
        build_chunks_from_raw(paths=paths, options=options)
        return

    if action == "probe":
        if options.image is None:
            print("--image is required for probe.", file=sys.stderr)
            raise SystemExit(2)
        probe_image(paths=paths, image=options.image)
        return

    if action == "retry":
        retry_failed_images(paths=paths, options=options)
        return

    raise AssertionError(f"Unhandled action: {action}")


def build_chunks_from_raw(*, paths: WorkflowPaths, options: WorkflowOptions) -> None:
    if options.provider == "lmstudio":
        require_vlm_config(include_retry=True)

    raw_root = paths.raw_root.resolve()
    store_root = paths.store_root.resolve()
    monthly_root = paths.monthly_root.resolve()
    chunks_root = paths.chunks_root.resolve()

    if not raw_root.is_dir():
        print(f"Error: raw directory not found: {raw_root}", file=sys.stderr)
        raise SystemExit(1)

    parse_result = FlomoParser(raw_root=raw_root, store_root=store_root).parse_all()
    StoreWriter(store_root=store_root).write(parse_result, raw_root=raw_root)
    print(f"Memos:          {len(parse_result.memos)}")
    print(f"Images:         {len(parse_result.images)}")
    print(f"Missing images: {len(parse_result.missing_images)}")
    print(f"Memo JSONL:     {store_root / 'memo.raw.jsonl'}")
    print(f"Image JSONL:    {store_root / 'image.raw.jsonl'}")
    print(f"Missing JSONL:  {store_root / 'missing_image.raw.jsonl'}")

    store_report = StoreValidator(
        store_root=store_root,
        raw_root=raw_root,
    ).validate()
    print(store_report.format_summary())
    if not store_report.ok:
        raise SystemExit(1)

    provider = _build_enrichment_provider(options.provider)
    retry_provider = _build_retry_provider(options.provider, provider, failed_only=False)
    _, enrich_stats = ImageEnrichmentRunner(
        store_root=store_root,
        provider=provider,
        retry_provider=retry_provider,
        month=options.month,
        workers=options.workers,
    ).run()
    print(enrich_stats.format_summary())
    print(f"Output: {store_root / 'image.enriched.jsonl'}")

    enriched_report = EnrichedImageValidator(store_root=store_root).validate()
    print(enriched_report.format_summary())
    if not enriched_report.ok:
        raise SystemExit(1)

    _, merge_stats = MonthlyMergeRunner(
        store_root=store_root,
        monthly_root=monthly_root,
        month=options.month,
    ).run()
    print(merge_stats.format_summary())
    print(f"Output dir: {monthly_root}")

    monthly_report = MonthlyValidator(
        store_root=store_root,
        monthly_root=monthly_root,
        month=options.month,
    ).validate()
    print(monthly_report.format_summary())
    if not monthly_report.ok:
        raise SystemExit(1)

    _, chunk_stats = ChunkBuildRunner(
        monthly_root=monthly_root,
        chunks_root=chunks_root,
        month=options.month,
        overwrite=True,
    ).run()
    print(chunk_stats.format_summary())
    print(f"Output dir: {chunks_root}")

    chunk_report = ChunkValidator(
        monthly_root=monthly_root,
        chunks_root=chunks_root,
        month=options.month,
    ).validate()
    print(chunk_report.format_summary())
    if not chunk_report.ok:
        raise SystemExit(1)

    if options.month:
        print(f"Ready for external LLM input: {display_path(paths.project_root, chunks_root / options.month)}")
    else:
        print(f"Ready for external LLM input: {display_path(paths.project_root, chunks_root / 'YYYY-MM')}")


def probe_image(*, paths: WorkflowPaths, image: Path) -> None:
    require_vlm_config()
    image_path = project_path(paths.project_root, image)
    provider = LMStudioEnrichmentProvider()
    call = provider.enrich_with_response(
        image_path.resolve(),
        image_id="probe-image",
        memo_id="probe-memo",
    )

    print(f"Status: {call.result.status}")
    print(f"Base URL: {provider.base_url or '(unset)'}")
    print(f"Model: {provider.model_name}")
    print(f"Prompt version: {provider.prompt_version}")
    print(f"Slice long images: {provider.slice_long_images}")
    print(f"Force slice long images: {provider.force_slice_long_images}")
    print(f"Slice height: {provider.slice_height}")
    print(f"Slice overlap: {provider.slice_overlap}")
    print(f"Slice upscale: {provider.slice_upscale}")
    print(f"OCR text: {call.result.ocr_text}")
    print(f"Visual description: {call.result.visual_description}")
    print(f"Error: {call.result.error_message or ''}")

    if call.raw_response is not None:
        print("Raw response:")
        print(json.dumps(call.raw_response, ensure_ascii=False, indent=2))

    if call.result.status != "success":
        raise SystemExit(1)


def retry_failed_images(*, paths: WorkflowPaths, options: WorkflowOptions) -> None:
    if options.provider == "lmstudio":
        require_vlm_config(include_retry=True)

    store_root = paths.store_root.resolve()
    enriched_path = store_root / "image.enriched.jsonl"
    base_provider = _build_enrichment_provider(options.provider)
    provider = base_provider
    if options.provider == "lmstudio":
        resolution = resolve_lmstudio_retry_model_name(base_model_name=base_provider.model_name)
        if resolution.warning is not None:
            print(f"Warning: {resolution.warning}", file=sys.stderr)
        else:
            provider = build_provider(options.provider, model_name=resolution.model_name)
        print(f"retry_vlm_model={provider.model_name}")

    for round_index in range(1, options.rounds + 1):
        before = _count_failed(enriched_path, options.month)
        print(f"Retry round {round_index}/{options.rounds}")
        print(f"Failed before: {before}")
        if before == 0:
            break

        _, stats = ImageEnrichmentRunner(
            store_root=store_root,
            provider=provider,
            month=options.month,
            workers=options.workers,
            failed_only=True,
            max_failed_retries=0,
        ).run()

        print(stats.format_summary())

        report = EnrichedImageValidator(store_root=store_root).validate()
        print(report.format_summary())
        if not report.ok:
            raise SystemExit(1)

        after = _count_failed(enriched_path, options.month)
        print(f"Failed after: {after}")
        if after == 0:
            break

    print(f"Remaining failed: {_count_failed(enriched_path, options.month)}")


def _build_enrichment_provider(provider_name: str) -> EnrichmentProvider:
    try:
        provider = build_provider(provider_name)
    except ValueError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
    if provider_name == "lmstudio":
        print(f"vlm_model={provider.model_name}")
    return provider


def _build_retry_provider(
    provider_name: str,
    provider: EnrichmentProvider,
    *,
    failed_only: bool,
) -> EnrichmentProvider | None:
    if provider_name != "lmstudio":
        return None
    if failed_only:
        return provider

    resolution = resolve_lmstudio_retry_model_name(base_model_name=provider.model_name)
    if resolution.warning is not None:
        print(f"Warning: {resolution.warning}", file=sys.stderr)
        return provider

    retry_provider = build_provider(provider_name, model_name=resolution.model_name)
    print(f"retry_vlm_model={retry_provider.model_name}")
    return retry_provider


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    records: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").split("\n"):
        line = line.rstrip("\r")
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
