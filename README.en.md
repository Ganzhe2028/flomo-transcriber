# flomo-transcriber

[中文](README.md)

Turn your Flomo memory archive into files that LLMs can actually read.

Many people use Flomo as a long-term memory system. After years of notes, the export can contain thousands of memos and many images, but it is not easy to hand that export to an LLM: text is scattered, images are unread, months are not split cleanly, and source tracking is fragile. `flomo-transcriber` turns that local export into clean, inspectable, reproducible files.

It keeps your original memo text, can convert readable image content into text through a local vision model, merges everything by month, and produces chunk files that external LLMs can read directly.

What it does:

1. Extract memos and images from a local Flomo HTML export.
2. Save stable JSONL files.
3. Optionally use LM Studio to read text and visual information from static images.
4. Merge memo text and image descriptions by month.
5. Build `llm_chunks/YYYY-MM/*.json` for OpenRouter, ChatGPT, Claude, or other external models.
6. Optionally build local monthly reports.

This is not a web app and does not require a database. Everything is local files.

## Start Here

Choose the section that matches your role:

- If you only want to prepare Flomo data for an LLM, read [User: Shortest Path](#user-shortest-path).
- If you want to change code or maintain the project, read [Developer: Structure and Tests](#developer-structure-and-tests).
- If you are an AI agent taking over the repo, read [Agent: Boundaries and Contracts](#agent-boundaries-and-contracts).

## User: Shortest Path

### 1. Install

```bash
pip install -e .[dev]
```

### 2. Put Your Flomo Export Into `raw/`

Place your Flomo HTML export under:

```text
raw/
```

Both the regular layout `raw/YYYY/flomo@User-YYYYMMDD/*.html` and the duplicate wrapper layout `raw/YYYY/flomo@User-YYYYMMDD/flomo@User-YYYYMMDD/*.html` are supported.

This repository does not include real Flomo data. `raw/`, `store/`, `monthly/`, `llm_chunks/`, and `reports/` are ignored by Git by default so private data is not accidentally committed.

### 3. Build the Raw Data Layer

```bash
python scripts/extract_raw.py --raw-root raw --store-root store
python scripts/validate_store.py --store-root store
```

After this step, you should have:

```text
store/memo.raw.jsonl
store/image.raw.jsonl
store/missing_image.raw.jsonl
store/images/
```

### 4. Convert Images Into Text

If you only want to test the pipeline without calling a real model:

```bash
python scripts/enrich_images.py --store-root store --provider mock
python scripts/validate_enriched_images.py --store-root store
```

If you want to read real image content with LM Studio, start LM Studio's OpenAI-compatible server, then set:

```bash
export FLOMO_VLM_BASE_URL="http://127.0.0.1:1234/v1"
export FLOMO_VLM_MODEL="<your-vision-model-name>"
export FLOMO_VLM_TIMEOUT_SECONDS="180"
export FLOMO_VLM_MAX_TOKENS="1024"
```

Probe one image first:

```bash
python scripts/probe_lmstudio_vlm.py --image store/images/2025/2025-12/example.png
```

Then process one month:

```bash
python scripts/enrich_images.py --store-root store --provider lmstudio --month 2025-12
python scripts/validate_enriched_images.py --store-root store
```

`--month 2025-12` is optional. If you omit `--month`, all months are processed:

```bash
python scripts/enrich_images.py --store-root store --provider lmstudio
```

If your local model server allows concurrent predictions, add `--workers` to process images in parallel:

```bash
python scripts/enrich_images.py --store-root store --provider lmstudio --workers 4
```

### 5. Build LLM-Ready Chunks

```bash
python scripts/merge_monthly.py --store-root store --monthly-root monthly
python scripts/validate_monthly.py --store-root store --monthly-root monthly
python scripts/build_chunks.py --monthly-root monthly --chunks-root llm_chunks --overwrite
python scripts/validate_chunks.py --monthly-root monthly --chunks-root llm_chunks
```

The final files for external LLMs are:

```text
llm_chunks/YYYY-MM/*.json
```

To process only one month:

```bash
python scripts/merge_monthly.py --store-root store --monthly-root monthly --month 2025-12
python scripts/validate_monthly.py --store-root store --monthly-root monthly --month 2025-12
python scripts/build_chunks.py --monthly-root monthly --chunks-root llm_chunks --month 2025-12 --overwrite
python scripts/validate_chunks.py --monthly-root monthly --chunks-root llm_chunks --month 2025-12 --summary
```

## Convenience Scripts

### macOS / Linux

Stage 2 uses the vision model:

```bash
export FLOMO_VLM_BASE_URL="http://127.0.0.1:1234/v1"
export FLOMO_VLM_MODEL="<your-vision-model-name>"
export FLOMO_VLM_TIMEOUT_SECONDS="180"
export FLOMO_VLM_MAX_TOKENS="1024"

scripts/00_probe_lmstudio_image.sh store/images/2025/2025-12/example.png
scripts/10_stage2_enrich_lmstudio.sh 2025-12
```

Stage 3-4 are local file operations:

```bash
scripts/20_stage3_4_build_context.sh 2025-12
```

Omit the month to process all months:

```bash
scripts/10_stage2_enrich_lmstudio.sh
scripts/20_stage3_4_build_context.sh
```

### Windows

Set the LM Studio environment variables in CMD or PowerShell:

```bat
set FLOMO_VLM_BASE_URL=http://127.0.0.1:1234/v1
set FLOMO_VLM_MODEL=<your-vision-model-name>
set FLOMO_VLM_TIMEOUT_SECONDS=180
set FLOMO_VLM_MAX_TOKENS=1024
```

Probe one image:

```bat
scripts\00_probe_lmstudio_image.bat store\images\2025\2025-12\example.png
```

Run Stage 2 with the model:

```bat
scripts\10_stage2_enrich_lmstudio.bat 2025-12
```

Run local Stage 3-4:

```bat
scripts\20_stage3_4_build_context.bat 2025-12
```

Run Stage 2-4 together:

```bat
scripts\30_stage2_4_prepare_context.bat 2025-12
```

If you omit `2025-12`, all months are processed.

## Folders and Outputs

```text
raw/          Your original Flomo export
store/        Stage 1-2 outputs: raw JSONL, copied images, image enrichment
monthly/      Stage 3 output: monthly merged memo records
llm_chunks/   Stage 4 output: chunk JSON files for external LLMs
reports/      Stage 5 output: optional local monthly reports
preview/      Reserved directory
scripts/      CLI entry points
src/          Python source code
tests/        Tests
```

The most important output is:

```text
llm_chunks/YYYY-MM/*.json
```

If you plan to use OpenRouter for final summarization, this is usually the only directory your external model needs to read.

## What Each Stage Does

| Stage | Input | Output | Purpose |
| --- | --- | --- | --- |
| Stage 1 extract | `raw/` | `store/memo.raw.jsonl`, `store/image.raw.jsonl`, `store/images/` | Extract memos and image references |
| Stage 2 enrich | `store/image.raw.jsonl` | `store/image.enriched.jsonl` | Read static images and write OCR / visual descriptions |
| Stage 3 merge monthly | `memo.raw.jsonl`, `image.enriched.jsonl` | `monthly/YYYY-MM.enriched.jsonl` | Merge memo text and image enrichment by month |
| Stage 4 chunk | `monthly/YYYY-MM.enriched.jsonl` | `llm_chunks/YYYY-MM/*.json` | Build LLM-readable context chunks |
| Stage 5 report | `llm_chunks/YYYY-MM/*.json` | `reports/YYYY-MM.report.md`, `reports/YYYY-MM.report.json` | Optional local monthly report generation |

Stage 1-4 are the recommended main path. Stage 5 is optional. If you use OpenRouter or another external model for the final report, you can stop after Stage 4.

## Stage 2 Image Enrichment

Currently supported static image types:

- `.png`
- `.jpg`
- `.jpeg`

Explicitly skipped:

- `.mov`
- `.mp4`
- `.m4a`
- other non-static image types

Providers:

- `mock`: test provider, no model call.
- `lmstudio`: calls LM Studio's OpenAI-compatible `/chat/completions` endpoint.

`lmstudio` reads:

- `FLOMO_VLM_BASE_URL`: for example `http://127.0.0.1:1234/v1`
- `FLOMO_VLM_MODEL`: local vision model name
- `FLOMO_VLM_API_KEY`: optional
- `FLOMO_VLM_TIMEOUT_SECONDS`: optional, default `60`
- `FLOMO_VLM_MAX_TOKENS`: optional, default `1024`, limits model output length for each image

Image enrichment failures do not stop the whole run. The command finishes the first pass, then retries failed records only, up to 3 retry rounds. Records that still fail keep `status=failed` and the final error message.

Existing successful records are skipped by default. To rerun successful records:

```bash
python scripts/enrich_images.py --store-root store --provider lmstudio --overwrite
```

## Stage 4 Chunks

Chunks are the final context files for LLMs.

Each chunk includes at least:

- `chunk_id`
- `month`
- `source_memo_ids`
- `created_at_range`
- `token_estimate`
- `text`
- `source_items`

Notes:

- `text` is the text field for the model to read directly.
- `source_items` keeps source memos and image enrichment records for traceability.
- A memo is the atomic unit; v1 does not split one memo across multiple chunks.
- `failed` and `skipped` images are not fabricated into text, but they remain traceable in structured fields.

The current strategy packs memos sequentially by time. The default target size is about `1200` estimated tokens. Token estimation is deterministic and heuristic; it is not meant to exactly match a specific model tokenizer.

## Optional: Build Local Reports

Mock report:

```bash
python scripts/build_reports.py --chunks-root llm_chunks --reports-root reports --provider mock
python scripts/validate_reports.py --chunks-root llm_chunks --reports-root reports
```

LM Studio text model report:

```bash
export FLOMO_LLM_BASE_URL="http://127.0.0.1:1234/v1"
export FLOMO_LLM_MODEL="<your-text-model-name>"
export FLOMO_LLM_TIMEOUT_SECONDS="120"

python scripts/build_reports.py --chunks-root llm_chunks --reports-root reports --provider lmstudio --month 2025-12 --overwrite
python scripts/validate_reports.py --chunks-root llm_chunks --reports-root reports --month 2025-12 --summary
```

If you use OpenRouter or another external model for final reporting, you can skip this section.

## Developer: Structure and Tests

Source layout:

```text
src/flomo_pipeline/
├── extract/
├── enrich/
├── merge/
├── chunk/
├── report/
├── preview/
└── common/
```

The public project name is `flomo-transcriber`. The internal Python import package remains `flomo_pipeline` for compatibility with existing scripts and tests.

Common commands:

```bash
python -m pytest
python scripts/check_open_source_readiness.py
```

Makefile shortcuts:

```bash
make extract
make validate
make enrich
make enrich-lmstudio
make validate-enrich
make merge-monthly
make validate-monthly
make build-chunks
make validate-chunks
make build-reports
make validate-reports
make test
```

Code principles:

- Each stage reads upstream files and writes its own derived artifact.
- Stage 1 raw JSONL is the truth layer and must not be rewritten by downstream stages.
- Derived outputs must be regenerable.
- Path fields must stay relative.
- Important outputs must have validators.

## Agent: Boundaries and Contracts

If you are an AI agent taking over this repo, read these first:

1. `README.md` or `README.en.md`
2. `pyproject.toml`
3. `tests/`

Do not default to refactoring existing stages. Current boundaries:

- Stage 1: `raw -> store/*.raw.jsonl`
- Stage 2: `store/image.raw.jsonl -> store/image.enriched.jsonl`
- Stage 3: `store/*.jsonl -> monthly/YYYY-MM.enriched.jsonl`
- Stage 4: `monthly/YYYY-MM.enriched.jsonl -> llm_chunks/YYYY-MM/*.json`
- Stage 5: `llm_chunks/YYYY-MM/*.json -> reports/YYYY-MM.report.*`

When adding features:

- Do not commit real user data.
- Do not treat `monthly`, `chunk`, or `report` as a new truth layer.
- Do not silently drop `failed` or `skipped` images.
- Do not call LLMs from Stage 4.
- Do not add video or audio understanding to Stage 2 unless a new stage design is explicitly approved.
- Update docs when user-visible behavior changes.

Minimum delivery checks:

```bash
python -m pytest
python scripts/check_open_source_readiness.py
```

## Schema Quick Reference

### `store/memo.raw.jsonl`

- `memo_id`
- `created_at`
- `body_md`
- `image_count`
- `source_relpath`
- `batch_label`
- `ordinal`

### `store/image.raw.jsonl`

- `image_id`
- `memo_id`
- `image_relpath`
- `source_relpath`
- `ordinal`

### `store/image.enriched.jsonl`

- `image_id`
- `memo_id`
- `created_at`
- `month`
- `relative_path`
- `source_relpath`
- `media_type`
- `ocr_text`
- `visual_description`
- `model_name`
- `prompt_version`
- `run_id`
- `status`
- `error_message`

### `monthly/YYYY-MM.enriched.jsonl`

- `memo_id`
- `created_at`
- `month`
- `memo_text`
- `source_relpath`
- `batch_label`
- `ordinal`
- `image_count_raw`
- `images`

`images` preserves the key Stage 2 fields, including `image_id`, paths, OCR, visual description, model metadata, `status`, and `error_message`.

### `llm_chunks/YYYY-MM/<chunk-id>.json`

- `chunk_id`
- `month`
- `chunk_index`
- `source_memo_ids`
- `source_count`
- `created_at_range`
- `token_estimate`
- `text`
- `source_items`
- `build_version`
- `strategy`
- `status`

### `reports/YYYY-MM.report.json`

- `report_id`
- `month`
- `source_chunk_ids`
- `source_count`
- `provider_name`
- `model_name`
- `prompt_version`
- `build_version`
- `status`
- `error_message`
- `report_md`
- `sections`

## Open Source Safety

Real Flomo exports and derived outputs should not be committed to a public repository. Before publishing, run:

```bash
python scripts/check_open_source_readiness.py
```

The check confirms that real data from these directories is not tracked by Git:

- `raw/`
- `store/`
- `monthly/`
- `llm_chunks/`
- `reports/`
- `preview/`

The old Git history of the private working repository is not suitable for direct public release. Publish from a clean orphan branch or a new public repository.
