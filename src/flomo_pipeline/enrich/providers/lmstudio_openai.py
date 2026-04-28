from __future__ import annotations

import base64
import errno
import json
import mimetypes
import os
import socket
import tempfile
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from flomo_pipeline.enrich.image_slicer import (
    ImageSlice,
    ImageSliceError,
    create_image_slices,
    get_image_size,
)
from flomo_pipeline.enrich.models import ProviderResult

PROMPT_VERSION = "lmstudio-openai-v2"
SLICE_PROMPT_VERSION = "lmstudio-openai-v2-slice-fallback-v1"
DEFAULT_SLICE_HEIGHT = 500
DEFAULT_SLICE_OVERLAP = 60
DEFAULT_SLICE_UPSCALE = 2.0
TRUE_VALUES = {"1", "true", "yes", "y", "on"}
FALSE_VALUES = {"0", "false", "no", "n", "off"}

PROMPT = """\
Extract two fields from this image and return only a JSON object.

Required JSON shape:
{"ocr_text":"...", "visual_description":"..."}

Rules:
- ocr_text: visible readable text only. Use an empty string if there is no readable text.
- visual_description: visible non-text content, including photos, objects, scenes,
  charts, UI layout, diagrams, and screenshots.
- At least one field must be non-empty. If the image has no readable text and no
  meaningful non-text content, set visual_description to "No meaningful visible content."
- Do not summarize meaning, infer emotions, add context, or combine the two fields.
- For dense screenshots or photographed notes, keep only the most important visible text
  in reading order.
- Keep ocr_text under 1200 characters and visual_description under 400 characters.
- Do not repeat duplicated blocks.
- Do not return Markdown, prose, or code fences.
"""

RESPONSE_FORMAT = {
    "type": "json_schema",
    "json_schema": {
        "name": "flomo_image_enrichment",
        "strict": True,
        "schema": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "ocr_text": {"type": "string"},
                "visual_description": {"type": "string"},
            },
            "required": ["ocr_text", "visual_description"],
        },
    },
}

DEFAULT_MAX_TOKENS = 4096


@dataclass(frozen=True)
class LMStudioCallResult:
    result: ProviderResult
    raw_response: dict[str, Any] | None


class LMStudioProviderError(Exception):
    pass


class LMStudioEnrichmentProvider:
    name = "lmstudio"
    prompt_version = PROMPT_VERSION

    def __init__(
        self,
        *,
        base_url: str | None = None,
        model_name: str | None = None,
        api_key: str | None = None,
        timeout_seconds: float | None = None,
        max_tokens: int | None = None,
        slice_long_images: bool | None = None,
        force_slice_long_images: bool | None = None,
        slice_height: int | None = None,
        slice_overlap: int | None = None,
        slice_upscale: float | None = None,
    ) -> None:
        raw_base_url = base_url if base_url is not None else os.getenv("FLOMO_VLM_BASE_URL", "")
        self.base_url = raw_base_url.strip()
        self.model_name = (
            model_name if model_name is not None else os.getenv("FLOMO_VLM_MODEL", "")
        ).strip()
        self.api_key = api_key if api_key is not None else os.getenv("FLOMO_VLM_API_KEY")
        self.timeout_seconds, self._timeout_error = self._resolve_timeout(timeout_seconds)
        self.max_tokens, self._max_tokens_error = self._resolve_max_tokens(max_tokens)
        self.slice_long_images, self._slice_long_images_error = self._resolve_bool(
            value=slice_long_images,
            env_name="FLOMO_VLM_SLICE_LONG_IMAGES",
            default=False,
        )
        self.force_slice_long_images, self._force_slice_long_images_error = self._resolve_bool(
            value=force_slice_long_images,
            env_name="FLOMO_VLM_FORCE_SLICE_LONG_IMAGES",
            default=False,
        )
        if self.force_slice_long_images:
            self.slice_long_images = True
        self.slice_height, self._slice_height_error = self._resolve_int(
            value=slice_height,
            env_name="FLOMO_VLM_SLICE_HEIGHT",
            default=DEFAULT_SLICE_HEIGHT,
        )
        self.slice_overlap, self._slice_overlap_error = self._resolve_int(
            value=slice_overlap,
            env_name="FLOMO_VLM_SLICE_OVERLAP",
            default=DEFAULT_SLICE_OVERLAP,
        )
        self.slice_upscale, self._slice_upscale_error = self._resolve_float(
            value=slice_upscale,
            env_name="FLOMO_VLM_SLICE_UPSCALE",
            default=DEFAULT_SLICE_UPSCALE,
        )
        self.prompt_version = SLICE_PROMPT_VERSION if self.slice_long_images else PROMPT_VERSION

    def enrich(self, image_path: Path, *, image_id: str, memo_id: str) -> ProviderResult:
        return self.enrich_with_response(image_path, image_id=image_id, memo_id=memo_id).result

    def enrich_with_response(
        self,
        image_path: Path,
        *,
        image_id: str,
        memo_id: str,
    ) -> LMStudioCallResult:
        try:
            self._validate_config()
        except LMStudioProviderError as exc:
            return LMStudioCallResult(
                result=ProviderResult(
                    ocr_text="",
                    visual_description="",
                    status="failed",
                    error_message=str(exc),
                ),
                raw_response=None,
            )

        if self.force_slice_long_images and self._is_taller_than_slice_height(image_path):
            return self._enrich_sliced_with_response(
                image_path,
                image_id=image_id,
                memo_id=memo_id,
                whole_error=None,
            )

        whole_call = self._enrich_single_with_response(
            image_path,
            image_id=image_id,
            memo_id=memo_id,
        )
        if whole_call.result.status == "success":
            return whole_call

        if self.slice_long_images and self._is_taller_than_slice_height(image_path):
            sliced_call = self._enrich_sliced_with_response(
                image_path,
                image_id=image_id,
                memo_id=memo_id,
                whole_error=whole_call.result.error_message,
            )
            if sliced_call.result.status == "success":
                return sliced_call
            return sliced_call

        return whole_call

    def _enrich_single_with_response(
        self,
        image_path: Path,
        *,
        image_id: str,
        memo_id: str,
        slice_context: str | None = None,
    ) -> LMStudioCallResult:
        raw_response: dict[str, Any] | None = None
        try:
            payload = self._build_payload(
                image_path,
                image_id=image_id,
                memo_id=memo_id,
                slice_context=slice_context,
            )
            raw_response = self._post_json(payload)
            result = self._parse_response(raw_response)
            return LMStudioCallResult(result=result, raw_response=raw_response)
        except LMStudioProviderError as exc:
            return LMStudioCallResult(
                result=ProviderResult(
                    ocr_text="",
                    visual_description="",
                    status="failed",
                    error_message=str(exc),
                ),
                raw_response=raw_response,
            )

    def _enrich_sliced_with_response(
        self,
        image_path: Path,
        *,
        image_id: str,
        memo_id: str,
        whole_error: str | None,
    ) -> LMStudioCallResult:
        with tempfile.TemporaryDirectory(prefix="flomo-image-slices-") as temp_dir:
            try:
                slices = create_image_slices(
                    image_path=image_path,
                    output_dir=Path(temp_dir),
                    slice_height=self.slice_height,
                    overlap=self.slice_overlap,
                    upscale=self.slice_upscale,
                )
            except ImageSliceError as exc:
                return LMStudioCallResult(
                    result=ProviderResult(
                        ocr_text="",
                        visual_description="",
                        status="failed",
                        error_message=_format_slice_unavailable_error(whole_error, str(exc)),
                    ),
                    raw_response=None,
                )

            successful_slices: list[tuple[ImageSlice, ProviderResult]] = []
            failures: list[str] = []
            first_raw_response: dict[str, Any] | None = None

            for image_slice in slices:
                call = self._enrich_single_with_response(
                    image_slice.path,
                    image_id=f"{image_id}#clip-{image_slice.index:04d}-of-{image_slice.total:04d}",
                    memo_id=memo_id,
                    slice_context=(
                        f"This image is vertical clip {image_slice.index} of "
                        f"{image_slice.total} from one long screenshot. "
                        "Read only this clip and keep the visible text in order."
                    ),
                )
                if first_raw_response is None and call.raw_response is not None:
                    first_raw_response = call.raw_response

                if call.result.status == "success":
                    successful_slices.append((image_slice, call.result))
                    continue

                error = call.result.error_message or "unknown error"
                failures.append(f"clip {image_slice.index}/{image_slice.total}: {error}")

            return LMStudioCallResult(
                result=_merge_slice_results(
                    successful_slices=successful_slices,
                    failure_messages=failures,
                    total=len(slices),
                    whole_error=whole_error,
                ),
                raw_response=first_raw_response,
            )

    @staticmethod
    def _resolve_timeout(timeout_seconds: float | None) -> tuple[float, str | None]:
        if timeout_seconds is not None:
            return timeout_seconds, None

        raw_timeout = os.getenv("FLOMO_VLM_TIMEOUT_SECONDS", "60")
        try:
            return float(raw_timeout), None
        except ValueError:
            return 60.0, f"Invalid FLOMO_VLM_TIMEOUT_SECONDS: {raw_timeout}"

    @staticmethod
    def _resolve_max_tokens(max_tokens: int | None) -> tuple[int, str | None]:
        if max_tokens is not None:
            return max_tokens, None

        raw_max_tokens = os.getenv("FLOMO_VLM_MAX_TOKENS", str(DEFAULT_MAX_TOKENS))
        try:
            return int(raw_max_tokens), None
        except ValueError:
            return DEFAULT_MAX_TOKENS, f"Invalid FLOMO_VLM_MAX_TOKENS: {raw_max_tokens}"

    @staticmethod
    def _resolve_bool(
        *,
        value: bool | None,
        env_name: str,
        default: bool,
    ) -> tuple[bool, str | None]:
        if value is not None:
            return value, None

        raw_value = os.getenv(env_name)
        if raw_value is None or not raw_value.strip():
            return default, None

        normalized = raw_value.strip().lower()
        if normalized in TRUE_VALUES:
            return True, None
        if normalized in FALSE_VALUES:
            return False, None
        return default, f"Invalid {env_name}: {raw_value}"

    @staticmethod
    def _resolve_int(
        *,
        value: int | None,
        env_name: str,
        default: int,
    ) -> tuple[int, str | None]:
        if value is not None:
            return value, None

        raw_value = os.getenv(env_name)
        if raw_value is None or not raw_value.strip():
            return default, None

        try:
            return int(raw_value), None
        except ValueError:
            return default, f"Invalid {env_name}: {raw_value}"

    @staticmethod
    def _resolve_float(
        *,
        value: float | None,
        env_name: str,
        default: float,
    ) -> tuple[float, str | None]:
        if value is not None:
            return value, None

        raw_value = os.getenv(env_name)
        if raw_value is None or not raw_value.strip():
            return default, None

        try:
            return float(raw_value), None
        except ValueError:
            return default, f"Invalid {env_name}: {raw_value}"

    def _validate_config(self) -> None:
        missing = []
        if not self.base_url:
            missing.append("FLOMO_VLM_BASE_URL")
        if not self.model_name:
            missing.append("FLOMO_VLM_MODEL")
        if missing:
            raise LMStudioProviderError(
                f"Missing required environment variable(s): {', '.join(missing)}"
            )

        if self._timeout_error is not None:
            raise LMStudioProviderError(self._timeout_error)
        if self._max_tokens_error is not None:
            raise LMStudioProviderError(self._max_tokens_error)
        if self.timeout_seconds <= 0:
            raise LMStudioProviderError("FLOMO_VLM_TIMEOUT_SECONDS must be greater than 0")
        if self.max_tokens <= 0:
            raise LMStudioProviderError("FLOMO_VLM_MAX_TOKENS must be greater than 0")
        bool_errors = [
            error
            for error in (
                self._slice_long_images_error,
                self._force_slice_long_images_error,
            )
            if error is not None
        ]
        if bool_errors:
            raise LMStudioProviderError("; ".join(bool_errors))

        if self.slice_long_images:
            slice_errors = [
                error
                for error in (
                    self._slice_height_error,
                    self._slice_overlap_error,
                    self._slice_upscale_error,
                )
                if error is not None
            ]
            if slice_errors:
                raise LMStudioProviderError("; ".join(slice_errors))
            if self.slice_height <= 0:
                raise LMStudioProviderError("FLOMO_VLM_SLICE_HEIGHT must be greater than 0")
            if self.slice_overlap < 0:
                raise LMStudioProviderError(
                    "FLOMO_VLM_SLICE_OVERLAP must be greater than or equal to 0"
                )
            if self.slice_overlap >= self.slice_height:
                raise LMStudioProviderError(
                    "FLOMO_VLM_SLICE_OVERLAP must be smaller than FLOMO_VLM_SLICE_HEIGHT"
                )
            if self.slice_upscale <= 0:
                raise LMStudioProviderError("FLOMO_VLM_SLICE_UPSCALE must be greater than 0")

        parsed = urllib.parse.urlparse(self.base_url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise LMStudioProviderError(
                "FLOMO_VLM_BASE_URL must be an http(s) base URL, "
                "for example http://127.0.0.1:1234/v1"
            )

    def _is_taller_than_slice_height(self, image_path: Path) -> bool:
        try:
            _, height = get_image_size(image_path)
        except ImageSliceError:
            return False
        return height > self.slice_height

    def _build_payload(
        self,
        image_path: Path,
        *,
        image_id: str,
        memo_id: str,
        slice_context: str | None = None,
    ) -> dict[str, Any]:
        if not image_path.exists():
            raise LMStudioProviderError(f"Image file not found: {image_path}")

        try:
            image_bytes = image_path.read_bytes()
        except OSError as exc:
            raise LMStudioProviderError(f"Could not read image file: {exc}") from exc

        mime_type = mimetypes.guess_type(image_path.name)[0] or "application/octet-stream"
        image_b64 = base64.b64encode(image_bytes).decode("ascii")
        data_url = f"data:{mime_type};base64,{image_b64}"
        prompt_text = f"{PROMPT}\nimage_id: {image_id}\nmemo_id: {memo_id}"
        if slice_context is not None:
            prompt_text = f"{PROMPT}\n{slice_context}\nimage_id: {image_id}\nmemo_id: {memo_id}"

        return {
            "model": self.model_name,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": prompt_text,
                        },
                        {"type": "image_url", "image_url": {"url": data_url}},
                    ],
                }
            ],
            "temperature": 0,
            "max_tokens": self.max_tokens,
            "response_format": RESPONSE_FORMAT,
            "stream": False,
        }

    def _post_json(self, payload: dict[str, Any]) -> dict[str, Any]:
        endpoint = f"{self.base_url.rstrip('/')}/chat/completions"
        request_body = json.dumps(payload).encode("utf-8")
        headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
        }
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        request = urllib.request.Request(
            endpoint,
            data=request_body,
            headers=headers,
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout_seconds) as response:
                response_text = response.read().decode("utf-8")
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace").strip()
            message = f"HTTP {exc.code}: {exc.reason}"
            if body:
                message = f"{message} - {body[:500]}"
            raise LMStudioProviderError(message) from exc
        except TimeoutError as exc:
            raise LMStudioProviderError("Model request timed out") from exc
        except urllib.error.URLError as exc:
            if _is_timeout_reason(exc.reason):
                raise LMStudioProviderError("Model request timed out") from exc
            raise LMStudioProviderError(_format_url_error(endpoint, exc.reason)) from exc

        try:
            parsed_response = json.loads(response_text)
        except json.JSONDecodeError as exc:
            raise LMStudioProviderError(f"Response JSON parse error: {exc}") from exc

        if not isinstance(parsed_response, dict):
            raise LMStudioProviderError("Response JSON must be an object")
        return parsed_response

    def _parse_response(self, raw_response: dict[str, Any]) -> ProviderResult:
        choices = raw_response.get("choices")
        if not isinstance(choices, list) or not choices:
            raise LMStudioProviderError("Response missing choices[0].message.content")

        first_choice = choices[0]
        if not isinstance(first_choice, dict):
            raise LMStudioProviderError("Response choices[0] must be an object")

        message = first_choice.get("message")
        if not isinstance(message, dict):
            raise LMStudioProviderError("Response choices[0].message must be an object")

        content = message.get("content")
        if not isinstance(content, str) or not content.strip():
            raise LMStudioProviderError("Response choices[0].message.content is empty")

        try:
            parsed_content = _parse_json_object(content)
        except json.JSONDecodeError as exc:
            raise LMStudioProviderError(_format_content_json_error(content, exc)) from exc

        if not isinstance(parsed_content, dict):
            raise LMStudioProviderError("Content JSON must be an object")

        ocr_text = str(parsed_content.get("ocr_text") or "").strip()
        visual_description = str(parsed_content.get("visual_description") or "").strip()

        if not (ocr_text or visual_description):
            raise LMStudioProviderError(
                "Model returned empty ocr_text and visual_description. "
                "If the image is not blank, retry with a stronger vision model."
            )

        return ProviderResult(
            ocr_text=ocr_text,
            visual_description=visual_description,
            status="success",
            error_message=None,
        )


def _strip_json_code_fence(content: str) -> str:
    lines = content.strip().splitlines()
    if lines and lines[0].strip().startswith("```"):
        lines = lines[1:]
    if lines and lines[-1].strip() == "```":
        lines = lines[:-1]
    return "\n".join(lines).strip()


def _parse_json_object(content: str) -> Any:
    cleaned_content = _strip_json_code_fence(content)
    try:
        return json.loads(cleaned_content)
    except json.JSONDecodeError as original_exc:
        decoder = json.JSONDecoder()
        for position, character in enumerate(cleaned_content):
            if character != "{":
                continue
            try:
                parsed, _ = decoder.raw_decode(cleaned_content[position:])
            except json.JSONDecodeError:
                continue
            if (
                isinstance(parsed, dict)
                and "ocr_text" in parsed
                and "visual_description" in parsed
            ):
                return parsed
        raise original_exc


def _format_url_error(endpoint: str, reason: Any) -> str:
    if _is_connection_refused(reason):
        return (
            f"Could not connect to LM Studio at {endpoint} (connection refused). "
            "Start LM Studio's OpenAI-compatible server and verify "
            "FLOMO_VLM_BASE_URL matches its host and port. "
            f"Underlying error: {reason}"
        )
    return f"HTTP request failed for {endpoint}: {reason}"


def _merge_slice_results(
    *,
    successful_slices: list[tuple[ImageSlice, ProviderResult]],
    failure_messages: list[str],
    total: int,
    whole_error: str | None,
) -> ProviderResult:
    if not successful_slices:
        detail = "; ".join(failure_messages[:3])
        if len(failure_messages) > 3:
            detail = f"{detail}; ..."
        message = f"Slice fallback failed for {total}/{total} clip(s)"
        if detail:
            message = f"{message}: {detail}"
        if whole_error:
            message = f"Whole-image failed: {whole_error}. {message}"
        return ProviderResult(
            ocr_text="",
            visual_description="",
            status="failed",
            error_message=message,
        )

    ocr_text = _merge_ocr_parts([result.ocr_text for _, result in successful_slices])
    visual_description = _merge_visual_parts(
        [
            (image_slice.index, result.visual_description)
            for image_slice, result in successful_slices
        ]
    )
    if not (ocr_text.strip() or visual_description.strip()):
        return ProviderResult(
            ocr_text="",
            visual_description="",
            status="failed",
            error_message="Slice fallback returned empty merged content",
        )

    error_message = None
    if failure_messages:
        failed_detail = "; ".join(failure_messages[:3])
        if len(failure_messages) > 3:
            failed_detail = f"{failed_detail}; ..."
        error_message = (
            f"Slice fallback succeeded for {len(successful_slices)}/{total} clip(s); "
            f"failed clips: {failed_detail}"
        )

    return ProviderResult(
        ocr_text=ocr_text,
        visual_description=visual_description,
        status="success",
        error_message=error_message,
    )


def _format_slice_unavailable_error(whole_error: str | None, slice_error: str) -> str:
    if whole_error:
        return f"Whole-image failed: {whole_error}. Slice fallback unavailable: {slice_error}"
    return f"Slice fallback unavailable: {slice_error}"


def _merge_ocr_parts(parts: list[str]) -> str:
    merged_lines: list[str] = []
    for part in parts:
        for raw_line in part.splitlines():
            line = raw_line.strip()
            if not line:
                continue
            normalized = _normalize_merge_line(line)
            recent_normalized = {_normalize_merge_line(item) for item in merged_lines[-8:]}
            if normalized in recent_normalized:
                continue
            merged_lines.append(line)
    return "\n".join(merged_lines)


def _merge_visual_parts(parts: list[tuple[int, str]]) -> str:
    merged: list[str] = []
    seen: set[str] = set()
    for clip_index, part in parts:
        cleaned = " ".join(part.split())
        if not cleaned:
            continue
        normalized = _normalize_merge_line(cleaned)
        if normalized in seen:
            continue
        seen.add(normalized)
        merged.append(f"Clip {clip_index}: {cleaned}")
    return "\n".join(merged)


def _normalize_merge_line(value: str) -> str:
    return " ".join(value.strip().casefold().split())


def _is_connection_refused(reason: Any) -> bool:
    if isinstance(reason, ConnectionRefusedError):
        return True
    if not isinstance(reason, OSError):
        return False
    return (
        getattr(reason, "errno", None) == errno.ECONNREFUSED
        or getattr(reason, "winerror", None) == 10061
    )


def _is_timeout_reason(reason: Any) -> bool:
    return isinstance(reason, (TimeoutError, socket.timeout)) or str(reason) == "timed out"


def _format_content_json_error(content: str, exc: json.JSONDecodeError) -> str:
    message = f"Content JSON parse error: {exc}"
    if _looks_truncated(content, exc):
        return (
            f"{message}. The model response may have been truncated; "
            "increase FLOMO_VLM_MAX_TOKENS, for example to 4096."
        )
    return message


def _looks_truncated(content: str, exc: json.JSONDecodeError) -> bool:
    stripped_content = _strip_json_code_fence(content)
    if not stripped_content:
        return False
    return "Unterminated string" in exc.msg or (
        stripped_content.startswith("{") and not stripped_content.endswith("}")
    )
