from __future__ import annotations

import importlib.util
from pathlib import Path

import numpy as np


def load_curve_types(source_root: Path):
    path = source_root / "comfy_api/latest/_input/curve_types.py"
    spec = importlib.util.spec_from_file_location("nodes_wizard_curve_types", path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def histogram_like_source(image: np.ndarray) -> tuple[list[int], ...]:
    first = image[0]
    img_uint8 = np.clip(first * 255, 0, 255).astype(np.uint8)
    red = np.bincount(img_uint8[..., 0].ravel(), minlength=256)
    green = np.bincount(img_uint8[..., 1].ravel(), minlength=256)
    blue = np.bincount(img_uint8[..., 2].ravel(), minlength=256)
    rgb = (red + green + blue) // 3
    luminance = (
        0.2126 * first[..., 0]
        + 0.7152 * first[..., 1]
        + 0.0722 * first[..., 2]
    )
    luminance = np.clip(luminance * 255, 0, 255).astype(np.uint8)
    lum = np.bincount(luminance.ravel(), minlength=256)
    return tuple(x.tolist() for x in (rgb, lum, red, green, blue))


def run(source_root: Path) -> dict[str, object]:
    curves = load_curve_types(source_root)
    linear = curves.CurveInput.from_raw(
        {"points": [[1, 1], [0, 0], [0.5, 0.25]], "interpolation": "linear"}
    )
    cubic = curves.CurveInput.from_raw({"points": [[0, 0], [0.5, 0.25], [1, 1]]})
    assert linear.points == [(0.0, 0.0), (0.5, 0.25), (1.0, 1.0)]
    assert linear.interp(0.25) == 0.125
    assert cubic.interp(-1) == 0.0 and cubic.interp(2) == 1.0

    image = np.array(
        [
            [[[0.0, 0.5, 1.0], [1.2, -0.1, 0.25]]],
            [[[1.0, 1.0, 1.0], [1.0, 1.0, 1.0]]],
        ],
        dtype=np.float32,
    )
    rgb, lum, red, green, blue = histogram_like_source(image)
    assert red[0] == 1 and red[255] == 1
    assert green[0] == 1 and green[127] == 1
    assert blue[63] == 1 and blue[255] == 1
    assert sum(lum) == 2
    assert sum(rgb) == 0  # each occupied composite bin has fewer than three counts
    return {"linearQuarter": linear.interp(0.25), "rgbCount": sum(rgb), "luminanceCount": sum(lum)}


if __name__ == "__main__":
    import sys

    print(run(Path(sys.argv[1])))
