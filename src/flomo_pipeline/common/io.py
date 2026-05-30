from __future__ import annotations

import dataclasses
import json
import time
from typing import TYPE_CHECKING, Any, Protocol, TypeGuard

if TYPE_CHECKING:
    from collections.abc import Iterable
    from pathlib import Path


_ATOMIC_REPLACE_RETRY_DELAYS_SECONDS = (0.05, 0.1, 0.2, 0.5, 1.0)


class SupportsToDict(Protocol):
    def to_dict(self) -> dict[str, object]: ...


def _has_to_dict(value: object) -> TypeGuard[SupportsToDict]:
    return hasattr(value, "to_dict")


def to_plain_dict(value: object) -> dict[str, object]:
    if _has_to_dict(value):
        return value.to_dict()
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        data = dataclasses.asdict(value)
        return {str(key): item for key, item in data.items()}
    if isinstance(value, dict):
        return {str(key): item for key, item in value.items()}
    raise TypeError(f"Cannot convert {type(value).__name__} to dict")


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []

    records: list[dict[str, Any]] = []
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        if raw_line.strip():
            payload = json.loads(raw_line)
            if not isinstance(payload, dict):
                raise ValueError(f"JSONL row is not an object: {path}")
            records.append(payload)
    return records


def read_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"JSON file is not an object: {path}")
    return payload


def _replace_with_retries(source_path: Path, destination_path: Path) -> None:
    last_error: PermissionError | None = None
    for attempt in range(len(_ATOMIC_REPLACE_RETRY_DELAYS_SECONDS) + 1):
        try:
            source_path.replace(destination_path)
            return
        except PermissionError as exc:
            last_error = exc
            if attempt == len(_ATOMIC_REPLACE_RETRY_DELAYS_SECONDS):
                break
            time.sleep(_ATOMIC_REPLACE_RETRY_DELAYS_SECONDS[attempt])

    if last_error is None:  # pragma: no cover - defensive guard
        raise PermissionError(f"Could not replace {destination_path} with {source_path}")

    raise PermissionError(
        "Could not update "
        f"{destination_path}. Close any app or script that is using this file and rerun. "
        f"The latest attempted output was kept at {source_path}."
    ) from last_error


def write_jsonl(path: Path, records: Iterable[object], *, atomic: bool = False) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    target_path = path.with_name(f"{path.name}.tmp") if atomic else path
    with open(target_path, "w", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(to_plain_dict(record), ensure_ascii=False) + "\n")
    if atomic:
        _replace_with_retries(target_path, path)


def write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text.rstrip() + "\n", encoding="utf-8")
