from __future__ import annotations

import dataclasses
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path


class ImageSliceError(Exception):
    pass


@dataclasses.dataclass(frozen=True)
class ImageSlice:
    index: int
    total: int
    top: int
    bottom: int
    path: Path


def get_image_size(image_path: Path) -> tuple[int, int]:
    try:
        from PIL import Image, ImageOps
    except ImportError as exc:  # pragma: no cover - depends on installation state
        raise ImageSliceError("Pillow is required for long-image slicing") from exc

    try:
        with Image.open(image_path) as image:
            transposed = ImageOps.exif_transpose(image)
            if transposed is None:
                transposed = image
            return transposed.size
    except OSError as exc:
        raise ImageSliceError(f"Could not inspect image dimensions: {exc}") from exc


def create_image_slices(
    *,
    image_path: Path,
    output_dir: Path,
    slice_height: int,
    overlap: int,
    upscale: float,
) -> list[ImageSlice]:
    if slice_height <= 0:
        raise ImageSliceError("slice_height must be greater than 0")
    if overlap < 0:
        raise ImageSliceError("slice_overlap must be greater than or equal to 0")
    if overlap >= slice_height:
        raise ImageSliceError("slice_overlap must be smaller than slice_height")
    if upscale <= 0:
        raise ImageSliceError("slice_upscale must be greater than 0")

    try:
        from PIL import Image, ImageOps
    except ImportError as exc:  # pragma: no cover - depends on installation state
        raise ImageSliceError("Pillow is required for long-image slicing") from exc

    try:
        with Image.open(image_path) as opened_image:
            image = ImageOps.exif_transpose(opened_image)
            if image is None:
                image = opened_image
            width, height = image.size
            if width <= 0 or height <= 0:
                raise ImageSliceError(f"Invalid image dimensions: {width}x{height}")

            windows = _slice_windows(height=height, slice_height=slice_height, overlap=overlap)
            output_dir.mkdir(parents=True, exist_ok=True)

            slices: list[ImageSlice] = []
            total = len(windows)
            resampling_filter = Image.Resampling.LANCZOS
            for index, (top, bottom) in enumerate(windows, start=1):
                clip = image.crop((0, top, width, bottom))
                if upscale != 1:
                    clip_width = max(1, round(clip.width * upscale))
                    clip_height = max(1, round(clip.height * upscale))
                    clip = clip.resize((clip_width, clip_height), resampling_filter)

                slice_path = output_dir / f"{image_path.stem}.slice-{index:04d}.png"
                clip.save(slice_path, format="PNG")
                slices.append(
                    ImageSlice(
                        index=index,
                        total=total,
                        top=top,
                        bottom=bottom,
                        path=slice_path,
                    )
                )
            return slices
    except ImageSliceError:
        raise
    except OSError as exc:
        raise ImageSliceError(f"Could not slice image: {exc}") from exc


def _slice_windows(*, height: int, slice_height: int, overlap: int) -> list[tuple[int, int]]:
    windows: list[tuple[int, int]] = []
    step = slice_height - overlap
    top = 0
    while top < height:
        bottom = min(top + slice_height, height)
        windows.append((top, bottom))
        if bottom >= height:
            break
        top += step
    return windows
