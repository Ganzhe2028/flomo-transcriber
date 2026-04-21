from __future__ import annotations

import base64
import errno
import json
import mimetypes
import os
import socket
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from flomo_pipeline.enrich.models import ProviderResult


PROMPT = """\
Extract two fields from this image and return only a JSON object.

Required JSON shape:
{"ocr_text":"...", "visual_description":"..."}

Rules:
- ocr_text: visible readable text only. Use an empty string if there is no readable text.
- visual_description: visible non-text content, including photos, objects, scenes, charts, UI layout, diagrams, and screenshots.
- At least one field must be non-empty. If the image has no readable text and no meaningful non-text content, set visual_description to "No meaningful visible content."
- Do not summarize meaning, infer emotions, add context, or combine the two fields.
- For dense screenshots or photographed notes, keep only the most important visible text in reading order.
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
    prompt_version = "lmstudio-openai-v2"

    def __init__(
        self,
        *,
        base_url: str | None = None,
        model_name: str | None = None,
        api_key: str | None = None,
        timeout_seconds: float | None = None,
        max_tokens: int | None = None,
    ) -> None:
        raw_base_url = base_url if base_url is not None else os.getenv("FLOMO_VLM_BASE_URL", "")
        self.base_url = raw_base_url.strip()
        self.model_name = (
            model_name if model_name is not None else os.getenv("FLOMO_VLM_MODEL", "")
        ).strip()
        self.api_key = api_key if api_key is not None else os.getenv("FLOMO_VLM_API_KEY")
        self.timeout_seconds, self._timeout_error = self._resolve_timeout(timeout_seconds)
        self.max_tokens, self._max_tokens_error = self._resolve_max_tokens(max_tokens)

    def enrich(self, image_path: Path, *, image_id: str, memo_id: str) -> ProviderResult:
        return self.enrich_with_response(image_path, image_id=image_id, memo_id=memo_id).result

    def enrich_with_response(
        self,
        image_path: Path,
        *,
        image_id: str,
        memo_id: str,
    ) -> LMStudioCallResult:
        raw_response: dict[str, Any] | None = None
        try:
            self._validate_config()
            payload = self._build_payload(image_path, image_id=image_id, memo_id=memo_id)
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

        parsed = urllib.parse.urlparse(self.base_url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise LMStudioProviderError(
                "FLOMO_VLM_BASE_URL must be an http(s) base URL, "
                "for example http://127.0.0.1:1234/v1"
            )

    def _build_payload(self, image_path: Path, *, image_id: str, memo_id: str) -> dict[str, Any]:
        if not image_path.exists():
            raise LMStudioProviderError(f"Image file not found: {image_path}")

        try:
            image_bytes = image_path.read_bytes()
        except OSError as exc:
            raise LMStudioProviderError(f"Could not read image file: {exc}") from exc

        mime_type = mimetypes.guess_type(image_path.name)[0] or "application/octet-stream"
        image_b64 = base64.b64encode(image_bytes).decode("ascii")
        data_url = f"data:{mime_type};base64,{image_b64}"

        return {
            "model": self.model_name,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": f"{PROMPT}\nimage_id: {image_id}\nmemo_id: {memo_id}",
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
        except (TimeoutError, socket.timeout) as exc:
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
