# Security Policy

## Supported Versions

This project is pre-1.0. Security fixes are made on the default branch.

## Reporting a Vulnerability

Do not open a public issue for secrets, private data exposure, or other
sensitive reports.

If you find a vulnerability, contact the repository owner privately through
GitHub.

## Data Safety Notes

This project is designed to process personal Flomo exports locally. Do not
commit real exports or generated private outputs.

The following directories are intentionally ignored except for `.gitkeep`:

- `raw/`
- `store/`
- `monthly/`
- `llm_chunks/`
- `reports/`
- `preview/`

Before publishing or sharing a fork, run:

```bash
python scripts/check_open_source_readiness.py
```
