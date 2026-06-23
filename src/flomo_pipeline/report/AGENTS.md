# report/ — Stage 5: Optional LLM Monthly Report

## OVERVIEW
Reads `llm_chunks/YYYY-MM/*.json`, calls an LLM to generate a monthly summary, writes `reports/YYYY-MM.report.md` + `.report.json`. **Optional stage** — not part of the default `guide.py --action first` flow.

## STRUCTURE
```
report/
├── runner.py       # ReportBuildRunner: per-month LLM report generation
├── validator.py    # ReportValidator: validates report files
├── models.py       # ReportRecord, ReportBuildStats, ReportSection
├── provider.py     # ReportProvider Protocol (build_report signature)
└── providers/
    ├── __init__.py          # build_report_provider() factory
    ├── lmstudio_openai.py   # LMStudioReportProvider: OpenAI-compatible API → local text LLM
    └── mock.py              # MockReportProvider: placeholder report, no API calls
```

## WHERE TO LOOK
| Task | File | Notes |
|------|------|-------|
| Add a new report provider | `providers/` | Implement `ReportProvider` Protocol, register in `build_report_provider()` |
| Change report prompt | `providers/lmstudio_openai.py` | LLM prompt has hard constraints: no fabrication, Markdown only, no greetings |
| Change report output schema | `models.py:ReportRecord` | `report_md` is the rendered report; `sections[]` for structured access |
| Add Stage 5 validation | `validator.py` | Cross-references reports against chunk files |

## CONVENTIONS
- ALLOWED statuses: `success`, `failed`
- LLM prompt constraints (hardcoded): 不要编造、输出Markdown、不要加寒暄
- Reports are optional and regenerable — delete and re-run to get fresh output

## ANTI-PATTERNS
- **NEVER call LLM for reports from Stage 4** — report LLM calls belong here
- **NEVER hardcode provider credentials** — use env vars (`FLOMO_LLM_*`) or `.env`
