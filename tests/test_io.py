from __future__ import annotations

import json
from pathlib import Path

import pytest

from flomo_pipeline.common import io


def test_write_jsonl_atomic_retries_transient_replace_permission_error(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    output_path = tmp_path / "image.enriched.jsonl"
    original_replace = Path.replace
    calls = 0

    def flaky_replace(self: Path, target: str | Path) -> Path:
        nonlocal calls
        calls += 1
        if calls == 1:
            raise PermissionError("locked")
        return original_replace(self, target)

    monkeypatch.setattr(Path, "replace", flaky_replace)
    monkeypatch.setattr(io.time, "sleep", lambda delay: None)

    io.write_jsonl(output_path, [{"image_id": "image-1", "status": "success"}], atomic=True)

    records = [
        json.loads(line)
        for line in output_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    assert calls == 2
    assert records == [{"image_id": "image-1", "status": "success"}]
    assert not output_path.with_name("image.enriched.jsonl.tmp").exists()


def test_write_jsonl_atomic_keeps_tmp_file_when_replace_stays_locked(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    output_path = tmp_path / "image.enriched.jsonl"

    def locked_replace(self: Path, target: str | Path) -> Path:
        raise PermissionError("locked")

    monkeypatch.setattr(Path, "replace", locked_replace)
    monkeypatch.setattr(io.time, "sleep", lambda delay: None)

    with pytest.raises(PermissionError, match="Close any app or script"):
        io.write_jsonl(output_path, [{"image_id": "image-1", "status": "success"}], atomic=True)

    tmp_output_path = output_path.with_name("image.enriched.jsonl.tmp")
    records = [
        json.loads(line)
        for line in tmp_output_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    assert records == [{"image_id": "image-1", "status": "success"}]
