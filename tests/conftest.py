from __future__ import annotations

import contextlib
import json
import threading
import time
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import TYPE_CHECKING, Any

import pytest

if TYPE_CHECKING:
    from collections.abc import Iterator
    from pathlib import Path


SAMPLE_HTML = """\
<!DOCTYPE html>
<html>
<head><meta charset="utf-8"></head>
<body>
<div class="name">@ExampleUser</div>
<div class="date">于 2026-3-4 导出 3 条 MEMO</div>

<div class="memo">
  <div class="time">2026-03-01 10:00:00</div>
  <div class="content"><p>First memo with <strong>bold</strong> text</p></div>
</div>

<div class="memo">
  <div class="time">2026-03-02 14:30:00</div>
  <div class="content"><p>Second memo with an image</p></div>
  <div class="files">
    <img src="file/2026-03-02/abc123/photo.png">
  </div>
</div>

<div class="memo">
  <div class="time">2026-03-03 09:15:00</div>
  <div class="content"><p>Third memo #tag1 #tag2</p></div>
  <div class="files">
    <img src="file/2026-03-03/def456/missing.jpg">
    <img src="file/2026-03-03/ghi789/audio_cover.png">
  </div>
</div>
</body>
</html>
"""


def build_sample_raw(raw_root: Path) -> Path:
    batch_dir = raw_root / "2026" / "flomo@ExampleUser-20260304"
    batch_dir.mkdir(parents=True, exist_ok=True)
    (batch_dir / "ExampleUser的笔记.html").write_text(SAMPLE_HTML, encoding="utf-8")

    file_dir = batch_dir / "file" / "2026-03-02" / "abc123"
    file_dir.mkdir(parents=True, exist_ok=True)
    (file_dir / "photo.png").write_bytes(b"\x89PNG\r\n\x1a\n")

    file_dir_2 = batch_dir / "file" / "2026-03-03" / "ghi789"
    file_dir_2.mkdir(parents=True, exist_ok=True)
    (file_dir_2 / "audio_cover.png").write_bytes(b"\x89PNG\r\n\x1a\n")

    return raw_root


def write_jsonl(path: Path, records: list[dict]) -> None:
    with open(path, "w", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")


@dataclass
class FakeHTTPResponse:
    status: int
    body: dict[str, Any] | str
    delay_seconds: float = 0


@dataclass
class FakeLMStudioServer:
    url: str
    requests: list[dict[str, Any]]


def lmstudio_chat_response(content: str) -> dict[str, Any]:
    return {"choices": [{"message": {"content": content}}]}


@contextlib.contextmanager
def run_fake_lmstudio_server(responses: list[FakeHTTPResponse]) -> Iterator[FakeLMStudioServer]:
    requests: list[dict[str, Any]] = []
    pending_responses = list(responses)

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self) -> None:
            content_length = int(self.headers.get("Content-Length", "0"))
            raw_body = self.rfile.read(content_length)
            requests.append(json.loads(raw_body.decode("utf-8")))

            if pending_responses:
                response = pending_responses.pop(0)
            else:
                response = FakeHTTPResponse(
                    status=500,
                    body={"error": "No fake response configured"},
                )

            if response.delay_seconds:
                time.sleep(response.delay_seconds)

            self.send_response(response.status)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            body = (
                response.body
                if isinstance(response.body, str)
                else json.dumps(response.body, ensure_ascii=False)
            )
            with contextlib.suppress(BrokenPipeError):
                self.wfile.write(body.encode("utf-8"))

        def log_message(self, format: str, *args: object) -> None:
            return

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    try:
        port = int(server.server_address[1])
        yield FakeLMStudioServer(url=f"http://127.0.0.1:{port}/v1", requests=requests)
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


@pytest.fixture
def sample_raw_root(tmp_path: Path) -> Path:
    return build_sample_raw(tmp_path / "raw")
