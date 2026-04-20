#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_ROOT"

PYTHON_BIN="${PYTHON:-python3}"
STORE_ROOT="${STORE_ROOT:-store}"
MONTH="${1:-${MONTH:-}}"
OVERWRITE_ENRICH="${OVERWRITE_ENRICH:-0}"

if [[ -z "${FLOMO_VLM_BASE_URL:-}" ]]; then
  echo "Missing FLOMO_VLM_BASE_URL, for example: http://127.0.0.1:1234/v1"
  exit 2
fi

if [[ -z "${FLOMO_VLM_MODEL:-}" ]]; then
  echo "Missing FLOMO_VLM_MODEL, for example: google/gemma-4-e4b"
  exit 2
fi

export FLOMO_VLM_TIMEOUT_SECONDS="${FLOMO_VLM_TIMEOUT_SECONDS:-180}"
export FLOMO_VLM_MAX_TOKENS="${FLOMO_VLM_MAX_TOKENS:-1024}"

command=(
  "$PYTHON_BIN" scripts/enrich_images.py
  --store-root "$STORE_ROOT"
  --provider lmstudio
)

if [[ -n "$MONTH" ]]; then
  command+=(--month "$MONTH")
fi

if [[ "$OVERWRITE_ENRICH" == "1" ]]; then
  command+=(--overwrite)
fi

echo "Stage 2: image enrich via LM Studio"
echo "month=${MONTH:-all}"
echo "store_root=$STORE_ROOT"
"${command[@]}"

"$PYTHON_BIN" scripts/validate_enriched_images.py \
  --store-root "$STORE_ROOT" \
  --summary
