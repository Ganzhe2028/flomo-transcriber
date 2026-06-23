# merge/ — Stage 3: Monthly Memo-Image Merge

## OVERVIEW
Joins `store/memo.raw.jsonl` with `store/image.enriched.jsonl` by `memo_id`, groups by month, and writes `monthly/YYYY-MM.enriched.jsonl`.

## STRUCTURE
```
merge/
├── runner.py       # MonthlyMergeRunner: _load_and_index(), _merge_month()
├── validator.py    # MonthlyValidator: validates monthly JSONL against store sources
└── models.py       # MonthlyMemoRecord, MonthlyImageRecord, MergeStats
```

## WHERE TO LOOK
| Task | File | Notes |
|------|------|-------|
| Change merge logic | `runner.py` | `run()` iterates months, merges per month |
| Change monthly output schema | `models.py:MonthlyMemoRecord` | `images` list carries per-image enriched fields |
| Add Stage 3 validation | `validator.py` | Cross-references memo.raw + image.enriched |

## CONVENTIONS
- Memos with zero images are preserved (not dropped)
- Failed/skipped images remain in `images[]` with `status` and `error_message`
- Month extracted from `created_at` field (ISO 8601 → `YYYY-MM`)
- Output is regenerable: delete monthly dir and re-run to get identical output

## ANTI-PATTERNS
- **NEVER treat `monthly/` as a truth layer** — it's derived output, re-run to regenerate
- **NEVER silently drop memos** that have zero images or failed enrichments
