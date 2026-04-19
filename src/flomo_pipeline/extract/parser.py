from __future__ import annotations

import re
from pathlib import Path, PurePosixPath
from typing import Optional

from bs4 import BeautifulSoup, Tag

from flomo_pipeline.common.models import ImageRecord, MemoRecord, MissingImageRecord, ParseResult


def _discover_html_files(batch_dir: Path) -> list[Path]:
    html_files = [
        candidate
        for candidate in batch_dir.iterdir()
        if candidate.is_file() and candidate.suffix.lower() == ".html" and candidate.name != ".DS_Store"
    ]
    return sorted(html_files)


def _extract_user_name(soup: BeautifulSoup) -> str:
    name_div = soup.find("div", class_="name")
    if name_div is None:
        raise ValueError("Cannot find <div class='name'> in HTML; not a valid flomo export")
    text = name_div.get_text(strip=True)
    if text.startswith("@"):
        text = text[1:]
    return text


def _slugify_user(name: str) -> str:
    return name.strip().replace(" ", "").lower()


def _extract_batch_label(batch_dir_name: str) -> str:
    pattern = r"flomo@(.+?)-(\d{8})"
    match = re.search(pattern, batch_dir_name)
    if not match:
        raise ValueError(f"Cannot parse batch label from directory: {batch_dir_name}")
    return match.group(2)


def _html_to_markdown(content_div: Tag) -> str:
    parts: list[str] = []

    for element in content_div.children:
        if isinstance(element, str):
            text = element.strip()
            if text:
                parts.append(text)
            continue

        if not isinstance(element, Tag):
            continue

        tag = element.name

        if tag == "p":
            inner = _process_inline(element)
            if inner:
                parts.append(inner)
        elif tag == "br":
            parts.append("")
        elif tag in ("strong", "b"):
            parts.append(f"**{_get_inner_text(element)}**")
        elif tag in ("em", "i"):
            parts.append(f"*{_get_inner_text(element)}*")
        elif tag == "a":
            href = element.get("href", "")
            link_text = _get_inner_text(element)
            if href:
                parts.append(f"[{link_text}]({href})")
            else:
                parts.append(link_text)
        elif tag in ("ul", "ol"):
            parts.append(_html_list_to_markdown(element))
        elif tag == "img":
            continue
        elif tag == "div":
            class_list = element.get("class")
            if isinstance(class_list, list) and ("files" in class_list or "audio-player" in class_list):
                continue
            parts.append(_html_to_markdown(element))

    while parts and parts[-1] == "":
        parts.pop()
    while parts and parts[0] == "":
        parts.pop(0)

    return "\n\n".join(parts)


def _process_inline(element: Tag) -> str:
    parts: list[str] = []
    for child in element.children:
        if isinstance(child, str):
            parts.append(child)
            continue
        if not isinstance(child, Tag):
            continue
        tag = child.name
        if tag in ("strong", "b"):
            parts.append(f"**{_get_inner_text(child)}**")
        elif tag in ("em", "i"):
            parts.append(f"*{_get_inner_text(child)}*")
        elif tag == "a":
            href = child.get("href", "")
            link_text = _get_inner_text(child)
            if href:
                parts.append(f"[{link_text}]({href})")
            else:
                parts.append(link_text)
        elif tag == "code":
            parts.append(f"`{_get_inner_text(child)}`")
        elif tag == "img":
            continue
        else:
            parts.append(_get_inner_text(child))
    return "".join(parts).strip()


def _get_inner_text(tag: Tag) -> str:
    return tag.get_text(strip=True)


def _html_list_to_markdown(element: Tag) -> str:
    ordered = element.name == "ol"
    items: list[str] = []
    for idx, li in enumerate(element.find_all("li", recursive=False), start=1):
        inner = _html_to_markdown(li).replace("\n", " ").strip()
        if ordered:
            items.append(f"{idx}. {inner}")
        else:
            items.append(f"- {inner}")
    return "\n".join(items)


def _parse_time(time_div: Tag) -> Optional[str]:
    raw = time_div.get_text(strip=True)
    pattern = r"(\d{4})-(\d{1,2})-(\d{1,2})\s+(\d{1,2}):(\d{2}):?(\d{2})?"
    match = re.match(pattern, raw)
    if not match:
        return None
    year, month, day, hour, minute, second = match.groups()
    second = second or "00"
    return f"{int(year):04d}-{int(month):02d}-{int(day):02d}T{int(hour):02d}:{minute}:{int(second):02d}"


def _format_ordinal(value: int, *, width: int = 4) -> str:
    return f"{value:0{width}d}"


def _to_posix(path: Path | PurePosixPath) -> str:
    return PurePosixPath(str(path)).as_posix()


class FlomoParser:
    def __init__(self, raw_root: Path, store_root: Path) -> None:
        self.raw_root = raw_root
        self.store_root = store_root

    def parse_all(self) -> ParseResult:
        all_memos: list[MemoRecord] = []
        all_images: list[ImageRecord] = []
        all_missing: list[MissingImageRecord] = []

        for batch_dir in self._discover_batches():
            result = self.parse_batch(batch_dir)
            all_memos.extend(result.memos)
            all_images.extend(result.images)
            all_missing.extend(result.missing_images)

        all_memos.sort(key=lambda record: record.memo_id)
        all_images.sort(key=lambda record: record.image_id)
        all_missing.sort(key=lambda record: record.image_id)

        return ParseResult(memos=all_memos, images=all_images, missing_images=all_missing)

    def parse_batch(self, batch_dir: Path) -> ParseResult:
        html_files = _discover_html_files(batch_dir)
        if not html_files:
            raise ValueError(f"No HTML files found in {batch_dir}")

        batch_label = _extract_batch_label(batch_dir.name)
        first_html = html_files[0]
        source_html_rel = _to_posix(first_html.relative_to(self.raw_root))

        with open(first_html, encoding="utf-8") as handle:
            soup = BeautifulSoup(handle.read(), "html.parser")

        user_slug = _slugify_user(_extract_user_name(soup))
        memo_divs = soup.find_all("div", class_="memo")

        memos: list[MemoRecord] = []
        images: list[ImageRecord] = []
        missing: list[MissingImageRecord] = []

        source_batch_rel = batch_dir.relative_to(self.raw_root)
        store_images_root = PurePosixPath(self.store_root.name) / "images"

        for memo_ordinal, memo_div in enumerate(memo_divs, start=1):
            time_div = memo_div.find("div", class_="time")
            content_div = memo_div.find("div", class_="content")

            created_at = _parse_time(time_div) if isinstance(time_div, Tag) else None
            body_md = _html_to_markdown(content_div) if isinstance(content_div, Tag) else ""
            memo_id = f"flomo-{user_slug}-{batch_label}--{_format_ordinal(memo_ordinal)}"

            image_records: list[ImageRecord] = []
            missing_records: list[MissingImageRecord] = []

            for image_ordinal, image_tag in enumerate(memo_div.find_all("img"), start=1):
                src_raw = image_tag.get("src")
                if not src_raw or not isinstance(src_raw, str):
                    continue

                source_relpath = _to_posix(source_batch_rel / PurePosixPath(src_raw))
                source_abs = batch_dir / str(PurePosixPath(src_raw))
                image_id = f"{memo_id}--{_format_ordinal(image_ordinal, width=2)}"

                year_month_match = re.search(r"(\d{4})-(\d{2})", source_relpath)
                if year_month_match:
                    year = year_month_match.group(1)
                    year_month = f"{year}-{year_month_match.group(2)}"
                else:
                    year = "1970"
                    year_month = "1970-01"

                ext = PurePosixPath(source_relpath).suffix or ".png"
                image_relpath = _to_posix(
                    store_images_root / year / year_month / f"{image_id}{ext}"
                )

                if source_abs.exists():
                    image_records.append(
                        ImageRecord(
                            image_id=image_id,
                            memo_id=memo_id,
                            image_relpath=image_relpath,
                            source_relpath=source_relpath,
                            ordinal=image_ordinal,
                        )
                    )
                else:
                    missing_records.append(
                        MissingImageRecord(
                            image_id=image_id,
                            memo_id=memo_id,
                            source_relpath=source_relpath,
                            ordinal=image_ordinal,
                            reason="source_file_missing",
                        )
                    )

            memos.append(
                MemoRecord(
                    memo_id=memo_id,
                    created_at=created_at or "1970-01-01T00:00:00",
                    body_md=body_md,
                    image_count=len(image_records) + len(missing_records),
                    source_relpath=source_html_rel,
                    batch_label=batch_label,
                    ordinal=memo_ordinal,
                )
            )
            images.extend(image_records)
            missing.extend(missing_records)

        return ParseResult(memos=memos, images=images, missing_images=missing)

    def _discover_batches(self) -> list[Path]:
        batch_dirs: list[Path] = []
        for year_dir in sorted(self.raw_root.iterdir()):
            if not year_dir.is_dir() or year_dir.name.startswith("."):
                continue
            for candidate in sorted(year_dir.iterdir()):
                if not candidate.is_dir() or candidate.name.startswith("."):
                    continue
                if candidate.name.startswith("flomo@"):
                    batch_dirs.append(candidate)
                else:
                    for nested in sorted(candidate.iterdir()):
                        if nested.is_dir() and nested.name.startswith("flomo@"):
                            batch_dirs.append(nested)
        return batch_dirs
