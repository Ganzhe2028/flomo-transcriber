from __future__ import annotations

import urllib.error
import urllib.request
from typing import TYPE_CHECKING

from flomo_pipeline.enrich import ImageEnrichmentRunner
from flomo_pipeline.enrich.providers import LMStudioEnrichmentProvider, build_provider
from tests.conftest import (
    FakeHTTPResponse,
    lmstudio_chat_response,
    run_fake_lmstudio_server,
)

if TYPE_CHECKING:
    from pathlib import Path
from tests.test_enrich_images import _setup_enrich_store


def _write_probe_image(tmp_path: Path) -> Path:
    image_path = tmp_path / "probe.png"
    image_path.write_bytes(b"\x89PNG\r\n\x1a\n")
    return image_path


def _write_real_png(tmp_path: Path, *, size: tuple[int, int] = (24, 1100)) -> Path:
    from PIL import Image

    image_path = tmp_path / "long.png"
    Image.new("RGB", size, color="white").save(image_path, format="PNG")
    return image_path


def test_lmstudio_provider_success_parses_fields_and_sends_image(tmp_path: Path) -> None:
    image_path = _write_probe_image(tmp_path)
    content = """```json
{"ocr_text":"hello world","visual_description":"A screenshot with a chart."}
```"""

    with run_fake_lmstudio_server(
        [FakeHTTPResponse(status=200, body=lmstudio_chat_response(content))]
    ) as server:
        provider = LMStudioEnrichmentProvider(
            base_url=server.url,
            model_name="local-vlm",
            timeout_seconds=2,
        )

        call = provider.enrich_with_response(image_path, image_id="image-1", memo_id="memo-1")

    assert call.result.status == "success"
    assert call.result.ocr_text == "hello world"
    assert call.result.visual_description == "A screenshot with a chart."
    assert call.raw_response is not None

    request_payload = server.requests[0]
    assert request_payload["model"] == "local-vlm"
    assert request_payload["temperature"] == 0
    assert request_payload["max_tokens"] == 4096
    assert request_payload["response_format"]["type"] == "json_schema"
    assert request_payload["stream"] is False
    message_content = request_payload["messages"][0]["content"]
    assert message_content[0]["type"] == "text"
    assert message_content[1]["type"] == "image_url"
    assert message_content[1]["image_url"]["url"].startswith("data:image/png;base64,")


def test_build_provider_accepts_explicit_lmstudio_model_name() -> None:
    provider = build_provider("lmstudio", model_name="retry-vlm")

    assert provider.model_name == "retry-vlm"


def test_lmstudio_provider_accepts_custom_max_tokens_and_reasoning_prefix(
    tmp_path: Path,
) -> None:
    image_path = _write_probe_image(tmp_path)
    content = (
        "<|channel>thought\nThinking Process with {\"ocr_text\":\"bad\"}<channel|>"
        '{"ocr_text":"hello world","visual_description":"A screenshot."}'
    )

    with run_fake_lmstudio_server(
        [FakeHTTPResponse(status=200, body=lmstudio_chat_response(content))]
    ) as server:
        provider = LMStudioEnrichmentProvider(
            base_url=server.url,
            model_name="local-vlm",
            timeout_seconds=2,
            max_tokens=256,
        )

        result = provider.enrich(image_path, image_id="image-1", memo_id="memo-1")

    assert result.status == "success"
    assert result.ocr_text == "hello world"
    assert result.visual_description == "A screenshot."
    assert server.requests[0]["max_tokens"] == 256


def test_lmstudio_provider_http_failure_returns_failed(tmp_path: Path) -> None:
    image_path = _write_probe_image(tmp_path)

    with run_fake_lmstudio_server(
        [FakeHTTPResponse(status=500, body={"error": "model failed"})]
    ) as server:
        provider = LMStudioEnrichmentProvider(
            base_url=server.url,
            model_name="local-vlm",
            timeout_seconds=2,
        )

        result = provider.enrich(image_path, image_id="image-1", memo_id="memo-1")

    assert result.status == "failed"
    assert result.error_message is not None
    assert "HTTP 500" in result.error_message


def test_lmstudio_provider_connection_refused_returns_actionable_error(
    tmp_path: Path,
    monkeypatch,
) -> None:
    image_path = _write_probe_image(tmp_path)

    def raise_connection_refused(*args, **kwargs):
        raise urllib.error.URLError(ConnectionRefusedError(10061, "connection refused"))

    monkeypatch.setattr(urllib.request, "urlopen", raise_connection_refused)

    provider = LMStudioEnrichmentProvider(
        base_url="http://127.0.0.1:1234/v1",
        model_name="local-vlm",
        timeout_seconds=1,
    )

    result = provider.enrich(image_path, image_id="image-1", memo_id="memo-1")

    assert result.status == "failed"
    assert result.error_message is not None
    assert "Could not connect to LM Studio" in result.error_message
    assert "/chat/completions" in result.error_message
    assert "FLOMO_VLM_BASE_URL" in result.error_message


def test_lmstudio_provider_timeout_returns_failed(tmp_path: Path) -> None:
    image_path = _write_probe_image(tmp_path)

    with run_fake_lmstudio_server(
        [
            FakeHTTPResponse(
                status=200,
                body=lmstudio_chat_response('{"ocr_text":"late","visual_description":""}'),
                delay_seconds=0.25,
            )
        ]
    ) as server:
        provider = LMStudioEnrichmentProvider(
            base_url=server.url,
            model_name="local-vlm",
            timeout_seconds=0.01,
        )

        result = provider.enrich(image_path, image_id="image-1", memo_id="memo-1")

    assert result.status == "failed"
    assert result.error_message == "Model request timed out"


def test_lmstudio_provider_rejects_malformed_response_shape(tmp_path: Path) -> None:
    image_path = _write_probe_image(tmp_path)

    with run_fake_lmstudio_server([FakeHTTPResponse(status=200, body={"choices": []})]) as server:
        provider = LMStudioEnrichmentProvider(
            base_url=server.url,
            model_name="local-vlm",
            timeout_seconds=2,
        )

        result = provider.enrich(image_path, image_id="image-1", memo_id="memo-1")

    assert result.status == "failed"
    assert result.error_message is not None
    assert "choices[0].message.content" in result.error_message


def test_lmstudio_provider_rejects_non_json_content(tmp_path: Path) -> None:
    image_path = _write_probe_image(tmp_path)

    with run_fake_lmstudio_server(
        [FakeHTTPResponse(status=200, body=lmstudio_chat_response("not json"))]
    ) as server:
        provider = LMStudioEnrichmentProvider(
            base_url=server.url,
            model_name="local-vlm",
            timeout_seconds=2,
        )

        call = provider.enrich_with_response(image_path, image_id="image-1", memo_id="memo-1")

    assert call.result.status == "failed"
    assert call.result.error_message is not None
    assert "Content JSON parse error" in call.result.error_message
    assert call.raw_response is not None


def test_lmstudio_provider_json_parse_error_hints_when_response_is_truncated(
    tmp_path: Path,
) -> None:
    image_path = _write_probe_image(tmp_path)

    with run_fake_lmstudio_server(
        [FakeHTTPResponse(status=200, body=lmstudio_chat_response('{"ocr_text":"long text'))]
    ) as server:
        provider = LMStudioEnrichmentProvider(
            base_url=server.url,
            model_name="local-vlm",
            timeout_seconds=2,
        )

        result = provider.enrich(image_path, image_id="image-1", memo_id="memo-1")

    assert result.status == "failed"
    assert result.error_message is not None
    assert "Content JSON parse error" in result.error_message
    assert "FLOMO_VLM_MAX_TOKENS" in result.error_message


def test_lmstudio_provider_rejects_empty_fields(tmp_path: Path) -> None:
    image_path = _write_probe_image(tmp_path)

    with run_fake_lmstudio_server(
        [
            FakeHTTPResponse(
                status=200,
                body=lmstudio_chat_response('{"ocr_text":"","visual_description":""}'),
            )
        ]
    ) as server:
        provider = LMStudioEnrichmentProvider(
            base_url=server.url,
            model_name="local-vlm",
            timeout_seconds=2,
        )

        result = provider.enrich(image_path, image_id="image-1", memo_id="memo-1")

    assert result.status == "failed"
    assert result.error_message is not None
    assert "empty ocr_text and visual_description" in result.error_message


def test_lmstudio_provider_slices_long_image_after_whole_image_failure(
    tmp_path: Path,
) -> None:
    image_path = _write_real_png(tmp_path)

    with run_fake_lmstudio_server(
        [
            FakeHTTPResponse(status=400, body={"error": "Invalid image detected"}),
            FakeHTTPResponse(
                status=200,
                body=lmstudio_chat_response(
                    '{"ocr_text":"line one\\nshared line","visual_description":"Top clip."}'
                ),
            ),
            FakeHTTPResponse(
                status=200,
                body=lmstudio_chat_response(
                    '{"ocr_text":"shared line\\nline two","visual_description":"Middle clip."}'
                ),
            ),
            FakeHTTPResponse(
                status=200,
                body=lmstudio_chat_response(
                    '{"ocr_text":"line three","visual_description":"Bottom clip."}'
                ),
            ),
        ]
    ) as server:
        provider = LMStudioEnrichmentProvider(
            base_url=server.url,
            model_name="local-vlm",
            timeout_seconds=2,
            slice_long_images=True,
            slice_height=500,
            slice_overlap=0,
            slice_upscale=1,
        )

        call = provider.enrich_with_response(image_path, image_id="image-1", memo_id="memo-1")

    assert call.result.status == "success"
    assert call.result.ocr_text == "line one\nshared line\nline two\nline three"
    assert "Clip 1: Top clip." in call.result.visual_description
    assert "Clip 2: Middle clip." in call.result.visual_description
    assert "Clip 3: Bottom clip." in call.result.visual_description
    assert call.result.error_message is None
    assert len(server.requests) == 4

    first_slice_prompt = server.requests[1]["messages"][0]["content"][0]["text"]
    assert "vertical clip 1 of 3" in first_slice_prompt
    assert "#clip-0001-of-0003" in first_slice_prompt
    assert server.requests[1]["messages"][0]["content"][1]["image_url"]["url"].startswith(
        "data:image/png;base64,"
    )


def test_lmstudio_provider_force_slices_long_image_without_whole_image_call(
    tmp_path: Path,
) -> None:
    image_path = _write_real_png(tmp_path)

    with run_fake_lmstudio_server(
        [
            FakeHTTPResponse(
                status=200,
                body=lmstudio_chat_response('{"ocr_text":"top","visual_description":""}'),
            ),
            FakeHTTPResponse(
                status=200,
                body=lmstudio_chat_response('{"ocr_text":"middle","visual_description":""}'),
            ),
            FakeHTTPResponse(
                status=200,
                body=lmstudio_chat_response('{"ocr_text":"bottom","visual_description":""}'),
            ),
        ]
    ) as server:
        provider = LMStudioEnrichmentProvider(
            base_url=server.url,
            model_name="local-vlm",
            timeout_seconds=2,
            force_slice_long_images=True,
            slice_height=500,
            slice_overlap=0,
            slice_upscale=1,
        )

        result = provider.enrich(image_path, image_id="image-1", memo_id="memo-1")

    assert result.status == "success"
    assert result.ocr_text == "top\nmiddle\nbottom"
    assert len(server.requests) == 3
    assert "#clip-0001-of-0003" in server.requests[0]["messages"][0]["content"][0]["text"]


def test_lmstudio_provider_returns_failed_when_all_long_image_slices_fail(
    tmp_path: Path,
) -> None:
    image_path = _write_real_png(tmp_path)

    with run_fake_lmstudio_server(
        [
            FakeHTTPResponse(status=400, body={"error": "whole failed"}),
            FakeHTTPResponse(status=500, body={"error": "slice 1 failed"}),
            FakeHTTPResponse(status=500, body={"error": "slice 2 failed"}),
            FakeHTTPResponse(status=500, body={"error": "slice 3 failed"}),
        ]
    ) as server:
        provider = LMStudioEnrichmentProvider(
            base_url=server.url,
            model_name="local-vlm",
            timeout_seconds=2,
            slice_long_images=True,
            slice_height=500,
            slice_overlap=0,
            slice_upscale=1,
        )

        result = provider.enrich(image_path, image_id="image-1", memo_id="memo-1")

    assert result.status == "failed"
    assert result.error_message is not None
    assert "Whole-image failed" in result.error_message
    assert "Slice fallback failed for 3/3 clip(s)" in result.error_message
    assert len(server.requests) == 4


def test_lmstudio_runner_happy_path_and_default_rerun_skip(tmp_path: Path) -> None:
    store_root = _setup_enrich_store(tmp_path)

    with run_fake_lmstudio_server(
        [
            FakeHTTPResponse(
                status=200,
                body=lmstudio_chat_response(
                    '{"ocr_text":"visible words","visual_description":"A saved image."}'
                ),
            )
        ]
    ) as server:
        provider = LMStudioEnrichmentProvider(
            base_url=server.url,
            model_name="local-vlm",
            timeout_seconds=2,
        )

        records, stats = ImageEnrichmentRunner(
            store_root=store_root,
            provider=provider,
            project_root=tmp_path,
            run_id="run-1",
        ).run()
        second_records, second_stats = ImageEnrichmentRunner(
            store_root=store_root,
            provider=provider,
            project_root=tmp_path,
            run_id="run-2",
        ).run()

    by_id = {record.image_id: record for record in records}
    success = by_id["flomo-example-20260304--0001--01"]
    assert success.status == "success"
    assert success.model_name == "local-vlm"
    assert success.prompt_version == "lmstudio-openai-v2"
    assert success.ocr_text == "visible words"
    assert success.visual_description == "A saved image."
    assert stats.success == 1
    assert stats.skipped == 1
    assert stats.failed == 1

    second_success = {
        record.image_id: record for record in second_records
    }["flomo-example-20260304--0001--01"]
    assert second_success.run_id == "run-1"
    assert second_stats.success == 0
    assert second_stats.skipped == 2
    assert second_stats.failed == 1
    assert len(server.requests) == 1
