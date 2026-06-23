# enrich/ — Stage 2: Image Enrichment via VLM

## OVERVIEW
Reads `store/image.raw.jsonl`, calls a local VLM (LM Studio) to OCR and describe each image, writes `store/image.enriched.jsonl`. Most complex stage — has provider pattern, long-image slicing, retry logic, and parallel workers.

## STRUCTURE
```
enrich/
├── runner.py                 # ImageEnrichmentRunner: batch process, atomic per-image save,
│                             #   skip-success, failed-only retry, retry-provider switching
├── validator.py              # EnrichedImageValidator: validates enriched JSONL
├── models.py                 # EnrichedImageRecord, EnrichStats, ProviderResult
├── provider.py               # EnrichmentProvider Protocol (enrich signature)
├── retry_config.py           # resolve_lmstudio_retry_model_name()
├── image_slicer.py           # create_image_slices(), get_image_size() — long-image fallback
└── providers/
    ├── __init__.py            # build_provider() factory
    ├── lmstudio_openai.py     # LMStudioEnrichmentProvider: OpenAI-compatible API → local VLM
    └── mock.py                # MockEnrichmentProvider: no API calls, test-only
```

## WHERE TO LOOK
| Task | File | Notes |
|------|------|-------|
| Add a new VLM provider | `providers/` | Implement `EnrichmentProvider` Protocol, register in `build_provider()` |
| Change enrichment workflow | `runner.py` | Key classes: `ImageEnrichmentRunner` (workers, retry, atomic saves) |
| Fix VLM API issues | `providers/lmstudio_openai.py` | `enrich_with_response()` → whole-image → slice fallback chain |
| Tune long-image slicing | `image_slicer.py` | Config: `--slice-height`, `--slice-overlap`, `--slice-upscale` |
| Change enrich output schema | `models.py:EnrichedImageRecord` | Fields: ocr_text, visual_description, model_name, status, error_message |

## CONVENTIONS
- ALLOWED statuses: `success`, `skipped`, `failed` (enforced in validator)
- MAX_FAILED_RETRIES = 3 per image
- Only static images processed: `.png`, `.jpg`, `.jpeg`; `.mov/.mp4/.m4a` explicitly skipped
- Per-image atomic save: each image flushes to `image.enriched.jsonl.tmp` immediately
- Long-image slicing: whole-image fail → auto-slice (if `slice_long_images`); or force-slice via `force_slice_long_images`

## ANTI-PATTERNS
- **NEVER silently drop `failed` / `skipped` images** — they stay in enriched JSONL with `error_message`
- **NEVER process video/audio** in Stage 2 unless a new stage design is explicitly approved
- **NEVER call LLM** from Stage 4 — VLM calls belong here (Stage 2) or in Stage 5 (report)
