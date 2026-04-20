#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_ROOT"

PYTHON_BIN="${PYTHON:-python3}"
STORE_ROOT="${STORE_ROOT:-store}"
MONTHLY_ROOT="${MONTHLY_ROOT:-monthly}"
CHUNKS_ROOT="${CHUNKS_ROOT:-llm_chunks}"
MONTH="${1:-${MONTH:-}}"
OVERWRITE_CHUNKS="${OVERWRITE_CHUNKS:-1}"

echo "Stage 3-4: build merged monthly context and LLM chunks"
echo "month=${MONTH:-all}"
echo "store_root=$STORE_ROOT"
echo "monthly_root=$MONTHLY_ROOT"
echo "chunks_root=$CHUNKS_ROOT"

"$PYTHON_BIN" scripts/validate_enriched_images.py \
  --store-root "$STORE_ROOT" \
  --summary

merge_command=(
  "$PYTHON_BIN" scripts/merge_monthly.py
  --store-root "$STORE_ROOT"
  --monthly-root "$MONTHLY_ROOT"
)
if [[ -n "$MONTH" ]]; then
  merge_command+=(--month "$MONTH")
fi
"${merge_command[@]}"

validate_monthly_command=(
  "$PYTHON_BIN" scripts/validate_monthly.py
  --store-root "$STORE_ROOT"
  --monthly-root "$MONTHLY_ROOT"
  --summary
)
if [[ -n "$MONTH" ]]; then
  validate_monthly_command+=(--month "$MONTH")
fi
"${validate_monthly_command[@]}"

build_chunks_command=(
  "$PYTHON_BIN" scripts/build_chunks.py
  --monthly-root "$MONTHLY_ROOT"
  --chunks-root "$CHUNKS_ROOT"
)

if [[ -n "$MONTH" ]]; then
  build_chunks_command+=(--month "$MONTH")
fi

if [[ "$OVERWRITE_CHUNKS" == "1" ]]; then
  build_chunks_command+=(--overwrite)
fi

"${build_chunks_command[@]}"

validate_chunks_command=(
  "$PYTHON_BIN" scripts/validate_chunks.py
  --monthly-root "$MONTHLY_ROOT"
  --chunks-root "$CHUNKS_ROOT"
  --summary
)
if [[ -n "$MONTH" ]]; then
  validate_chunks_command+=(--month "$MONTH")
fi
"${validate_chunks_command[@]}"

if [[ -n "$MONTH" ]]; then
  echo "Ready for external LLM input: $CHUNKS_ROOT/$MONTH/*.json"
else
  echo "Ready for external LLM input: $CHUNKS_ROOT/YYYY-MM/*.json"
fi
