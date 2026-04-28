from __future__ import annotations

from typing import TYPE_CHECKING

from flomo_pipeline.enrich.image_slicer import create_image_slices, get_image_size

if TYPE_CHECKING:
    from pathlib import Path


def _write_png(path: Path, *, size: tuple[int, int]) -> Path:
    from PIL import Image

    Image.new("RGB", size, color="white").save(path, format="PNG")
    return path


def test_get_image_size_reads_dimensions(tmp_path: Path) -> None:
    image_path = _write_png(tmp_path / "sample.png", size=(32, 64))

    assert get_image_size(image_path) == (32, 64)


def test_create_image_slices_preserves_tail_and_overlap(tmp_path: Path) -> None:
    image_path = _write_png(tmp_path / "long.png", size=(20, 1100))
    slices = create_image_slices(
        image_path=image_path,
        output_dir=tmp_path / "slices",
        slice_height=500,
        overlap=50,
        upscale=1,
    )

    assert [(image_slice.top, image_slice.bottom) for image_slice in slices] == [
        (0, 500),
        (450, 950),
        (900, 1100),
    ]
    assert [image_slice.index for image_slice in slices] == [1, 2, 3]
    assert [image_slice.total for image_slice in slices] == [3, 3, 3]
    assert all(image_slice.path.exists() for image_slice in slices)
    assert get_image_size(slices[-1].path) == (20, 200)


def test_create_image_slices_upscales_each_clip(tmp_path: Path) -> None:
    image_path = _write_png(tmp_path / "long.png", size=(20, 600))
    slices = create_image_slices(
        image_path=image_path,
        output_dir=tmp_path / "slices",
        slice_height=500,
        overlap=0,
        upscale=2,
    )

    assert get_image_size(slices[0].path) == (40, 1000)
    assert get_image_size(slices[1].path) == (40, 200)
