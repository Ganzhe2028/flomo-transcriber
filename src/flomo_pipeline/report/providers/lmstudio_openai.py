from __future__ import annotations

import json
import os
import socket
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

from flomo_pipeline.report.models import ReportProviderResult


PROMPT = """\
你是一个严格的个人知识库整理助手。
只根据给定 chunk 内容写一段中文 Markdown 小结。
要求：
- 不要编造 chunk 中没有的信息
- 保留重要 memo_id 或线索
- 明确列出可行动事项、主题、疑问
- 如果图片 OCR 或描述有用，纳入小结
- 输出 Markdown，不要输出 JSON，不要加寒暄
"""


class LMStudioReportProvider:
    name = "lmstudio"
    prompt_version = "lmstudio-report-v1"

    def __init__(
        self,
        *,
        base_url: str | None = None,
        model_name: str | None = None,
        api_key: str | None = None,
        timeout_seconds: float | None = None,
    ) -> None:
        raw_base_url = base_url if base_url is not None else os.getenv("FLOMO_LLM_BASE_URL", "")
        self.base_url = raw_base_url.rstrip("/")
        self.model_name = (
            model_name if model_name is not None else os.getenv("FLOMO_LLM_MODEL", "")
        ).strip()
        self.api_key = api_key if api_key is not None else os.getenv("FLOMO_LLM_API_KEY")
        self.timeout_seconds = timeout_seconds

    def summarize_chunk(self, chunk: dict[str, Any]) -> ReportProviderResult:
        config_error = self._validate_config()
        if config_error is not None:
            return self._failed(config_error)

        payload = {
            "model": self.model_name,
            "messages": [
                {"role": "system", "content": PROMPT},
                {"role": "user", "content": self._render_user_content(chunk)},
            ],
            "temperature": 0,
            "stream": False,
        }
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        request = urllib.request.Request(
            f"{self.base_url}/chat/completions",
            data=body,
            headers=headers,
            method="POST",
        )

        try:
            with urllib.request.urlopen(request, timeout=self._timeout()) as response:
                response_body = response.read().decode("utf-8")
                response_payload = json.loads(response_body)
        except TimeoutError:
            return self._failed("Model request timed out")
        except socket.timeout:
            return self._failed("Model request timed out")
        except urllib.error.HTTPError as exc:
            error_body = exc.read().decode("utf-8", errors="replace")
            return self._failed(f"HTTP {exc.code}: {exc.reason} - {error_body}")
        except urllib.error.URLError as exc:
            return self._failed(f"Request error: {exc.reason}")
        except json.JSONDecodeError as exc:
            return self._failed(f"Response JSON parse error: {exc}")

        try:
            content = response_payload["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError):
            return self._failed("Response missing choices[0].message.content")

        if not isinstance(content, str) or not content.strip():
            return self._failed("Response content is empty")

        return ReportProviderResult(
            summary_md=content.strip(),
            status="success",
            error_message=None,
        )

    def _validate_config(self) -> str | None:
        missing: list[str] = []
        if not self.base_url:
            missing.append("FLOMO_LLM_BASE_URL")
        if not self.model_name:
            missing.append("FLOMO_LLM_MODEL")
        if missing:
            return f"Missing environment variable(s): {', '.join(missing)}"

        parsed = urllib.parse.urlparse(self.base_url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            return (
                "FLOMO_LLM_BASE_URL must be an http(s) base URL, "
                f"got: {self.base_url}"
            )

        try:
            timeout = self._timeout()
        except ValueError as exc:
            return str(exc)
        if timeout <= 0:
            return "FLOMO_LLM_TIMEOUT_SECONDS must be greater than 0"

        return None

    def _timeout(self) -> float:
        if self.timeout_seconds is not None:
            return float(self.timeout_seconds)
        raw_timeout = os.getenv("FLOMO_LLM_TIMEOUT_SECONDS", "120")
        try:
            return float(raw_timeout)
        except ValueError as exc:
            raise ValueError(f"Invalid FLOMO_LLM_TIMEOUT_SECONDS: {raw_timeout}") from exc

    @staticmethod
    def _render_user_content(chunk: dict[str, Any]) -> str:
        chunk_id = str(chunk.get("chunk_id", ""))
        month = str(chunk.get("month", ""))
        text = str(chunk.get("text", ""))
        return f"month: {month}\nchunk_id: {chunk_id}\n\n{text}"

    @staticmethod
    def _failed(message: str) -> ReportProviderResult:
        return ReportProviderResult(summary_md="", status="failed", error_message=message)
