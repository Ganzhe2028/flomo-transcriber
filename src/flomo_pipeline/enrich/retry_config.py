from __future__ import annotations

import os
from dataclasses import dataclass

RETRY_MODEL_ENV = "FLOMO_VLM_RETRY_MODEL"
BASE_MODEL_ENV = "FLOMO_VLM_MODEL"
RETRY_MODEL_PLACEHOLDERS = {
    "",
    "<your-retry-vision-model-name>",
    "<你的重试视觉模型名>",
    "your-local-retry-vision-model",
}


@dataclass(frozen=True)
class RetryModelResolution:
    model_name: str | None
    warning: str | None


def resolve_lmstudio_retry_model_name(
    *,
    base_model_name: str | None = None,
) -> RetryModelResolution:
    base_model = (base_model_name if base_model_name is not None else os.getenv(BASE_MODEL_ENV, ""))
    base_model = base_model.strip()
    retry_model = os.getenv(RETRY_MODEL_ENV, "").strip()

    if retry_model in RETRY_MODEL_PLACEHOLDERS:
        return RetryModelResolution(
            model_name=None,
            warning=f"{RETRY_MODEL_ENV} is not set; retry will use {BASE_MODEL_ENV}.",
        )

    if base_model and retry_model == base_model:
        raise ValueError(f"{RETRY_MODEL_ENV} must be different from {BASE_MODEL_ENV}.")

    return RetryModelResolution(model_name=retry_model, warning=None)
