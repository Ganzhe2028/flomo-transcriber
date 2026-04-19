#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_ROOT"

PYTHON_BIN="${PYTHON:-python3}"
STORE_ROOT="${STORE_ROOT:-store}"
MONTHLY_ROOT="${MONTHLY_ROOT:-monthly}"
CHUNKS_ROOT="${CHUNKS_ROOT:-llm_chunks}"
MONTH="${1:-${MONTH:-2025-12}}"
OVERWRITE_CHUNKS="${OVERWRITE_CHUNKS:-1}"

echo "Stage 3-4: build merged monthly context and LLM chunks"
echo "month=$MONTH"
echo "store_root=$STORE_ROOT"
echo "monthly_root=$MONTHLY_ROOT"
echo "chunks_root=$CHUNKS_ROOT"

"$PYTHON_BIN" scripts/validate_enriched_images.py \
  --store-root "$STORE_ROOT" \
  --summary

"$PYTHON_BIN" scripts/merge_monthly.py \
  --store-root "$STORE_ROOT" \
  --monthly-root "$MONTHLY_ROOT" \
  --month "$MONTH"

"$PYTHON_BIN" scripts/validate_monthly.py \
  --store-root "$STORE_ROOT" \
  --monthly-root "$MONTHLY_ROOT" \
  --month "$MONTH" \
  --summary

build_chunks_command=(
  "$PYTHON_BIN" scripts/build_chunks.py
  --monthly-root "$MONTHLY_ROOT"
  --chunks-root "$CHUNKS_ROOT"
  --month "$MONTH"
)

if [[ "$OVERWRITE_CHUNKS" == "1" ]]; then
  build_chunks_command+=(--overwrite)
fi

"${build_chunks_command[@]}"

"$PYTHON_BIN" scripts/validate_chunks.py \
  --monthly-root "$MONTHLY_ROOT" \
  --chunks-root "$CHUNKS_ROOT" \
  --month "$MONTH" \
  --summary

echo "Ready for external LLM input: $CHUNKS_ROOT/$MONTH/*.json"
