#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_ROOT"

PYTHON_BIN="${PYTHON:-python3}"
IMAGE_PATH="${1:-${IMAGE:-}}"

if [[ -z "$IMAGE_PATH" ]]; then
  echo "Usage: $0 <image-path>"
  echo "Or: IMAGE=<image-path> $0"
  exit 2
fi

if [[ -z "${FLOMO_VLM_BASE_URL:-}" ]]; then
  echo "Missing FLOMO_VLM_BASE_URL, for example: http://127.0.0.1:1234/v1"
  exit 2
fi

if [[ -z "${FLOMO_VLM_MODEL:-}" ]]; then
  echo "Missing FLOMO_VLM_MODEL, for example: google/gemma-4-e4b:2"
  exit 2
fi

export FLOMO_VLM_TIMEOUT_SECONDS="${FLOMO_VLM_TIMEOUT_SECONDS:-180}"

"$PYTHON_BIN" scripts/probe_lmstudio_vlm.py --image "$IMAGE_PATH"
