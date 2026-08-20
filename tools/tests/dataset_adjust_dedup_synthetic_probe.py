from __future__ import annotations

import json
import sys
from pathlib import Path


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit(
            "usage: dataset_adjust_dedup_synthetic_probe.py <pinned-comfyui-source>"
        )

    source = Path(sys.argv[1]).resolve()
    sys.path.insert(0, str(source))

    import torch

    from comfy_extras.nodes_dataset import (
        AdjustBrightnessNode,
        AdjustContrastNode,
        ImageDeduplicationNode,
        NormalizeImagesNode,
    )

    values = torch.tensor(
        [
            -0.25,
            0.0,
            0.25,
            0.5,
            0.75,
            1.0,
            1.25,
            0.1,
            0.2,
            0.3,
            0.4,
            0.6,
            0.8,
            0.9,
            1.1,
            -0.1,
            0.05,
            0.95,
            0.35,
            0.65,
            0.15,
            0.85,
            0.45,
            0.55,
        ],
        dtype=torch.float32,
    ).reshape(2, 2, 2, 3)

    bright = AdjustBrightnessNode.execute(images=values, factor=[2.0]).args[0]
    assert bright.shape == values.shape
    assert bright.dtype == values.dtype
    assert torch.equal(bright, (values * 2.0).clamp(0.0, 1.0))
    dark = AdjustBrightnessNode.execute(images=values, factor=0.0).args[0]
    assert torch.count_nonzero(dark) == 0

    contrast_zero = AdjustContrastNode.execute(images=values, factor=[0.0]).args[0]
    assert torch.equal(contrast_zero, torch.full_like(values, 0.5))
    contrast_two = AdjustContrastNode.execute(images=values, factor=2.0).args[0]
    expected_contrast = ((values - 0.5) * 2.0 + 0.5).clamp(0.0, 1.0)
    assert torch.equal(contrast_two, expected_contrast)

    normalized = NormalizeImagesNode.execute(
        images=values, mean=[0.5], std=[0.5]
    ).args[0]
    assert normalized.shape == values.shape
    assert normalized.dtype == values.dtype
    assert torch.equal(normalized, (values - 0.5) / 0.5)
    assert float(normalized.min()) == -1.5
    assert float(normalized.max()) == 1.5

    pattern_a = torch.zeros((1, 8, 8, 3), dtype=torch.float32)
    pattern_a.reshape(1, 64, 3)[:, :32, :] = 1.0
    pattern_b = torch.zeros((1, 8, 8, 3), dtype=torch.float32)
    pattern_b.reshape(1, 64, 3)[:, :31, :] = 1.0
    pattern_inverse = 1.0 - pattern_a

    exact_only = ImageDeduplicationNode.execute(
        images=[pattern_a, pattern_a.clone(), pattern_b, pattern_inverse],
        similarity_threshold=[1.0],
    ).args[0]
    assert len(exact_only) == 3
    assert torch.equal(exact_only[0], pattern_a)
    assert torch.equal(exact_only[1], pattern_b)
    assert torch.equal(exact_only[2], pattern_inverse)

    boundary = 1.0 - (1.0 / 64.0)
    inclusive_boundary = ImageDeduplicationNode.execute(
        images=[pattern_a, pattern_b],
        similarity_threshold=[boundary],
    ).args[0]
    assert len(inclusive_boundary) == 1
    above_boundary = ImageDeduplicationNode.execute(
        images=[pattern_a, pattern_b],
        similarity_threshold=[boundary + 0.0001],
    ).args[0]
    assert len(above_boundary) == 2

    default_threshold = ImageDeduplicationNode.execute(
        images=[pattern_a, pattern_b, pattern_inverse],
        similarity_threshold=[0.95],
    ).args[0]
    assert len(default_threshold) == 2
    assert torch.equal(default_threshold[0], pattern_a)
    assert torch.equal(default_threshold[1], pattern_inverse)

    black = torch.zeros((1, 8, 8, 3), dtype=torch.float32)
    white = torch.ones((1, 10, 6, 3), dtype=torch.float32)
    solids = ImageDeduplicationNode.execute(
        images=[black, white], similarity_threshold=[1.0]
    ).args[0]
    assert len(solids) == 1
    assert torch.equal(solids[0], black)

    zero_threshold = ImageDeduplicationNode.execute(
        images=[pattern_a, pattern_inverse, white], similarity_threshold=[0.0]
    ).args[0]
    assert len(zero_threshold) == 1
    assert torch.equal(zero_threshold[0], pattern_a)

    empty = ImageDeduplicationNode.execute(
        images=[], similarity_threshold=[0.95]
    ).args[0]
    assert empty == []

    batched = torch.cat([pattern_a, pattern_b], dim=0)
    flattened = ImageDeduplicationNode._ensure_image_list([batched, pattern_inverse])
    assert len(flattened) == 3
    assert all(item.shape[0] == 1 for item in flattened)

    invalid_shape_error = None
    try:
        ImageDeduplicationNode.execute(
            images=torch.zeros((8, 8, 3)), similarity_threshold=[0.95]
        )
    except ValueError as exc:
        invalid_shape_error = str(exc)
    assert invalid_shape_error == "Expected 4D image tensor, got shape (8, 8, 3)"

    print(
        json.dumps(
            {
                "brightness": {
                    "shape": list(bright.shape),
                    "min": float(bright.min()),
                    "max": float(bright.max()),
                    "factorZeroIsBlack": True,
                },
                "contrast": {
                    "factorZeroValue": float(contrast_zero[0, 0, 0, 0]),
                    "shape": list(contrast_two.shape),
                },
                "normalize": {
                    "shape": list(normalized.shape),
                    "min": float(normalized.min()),
                    "max": float(normalized.max()),
                    "notClamped": True,
                },
                "deduplication": {
                    "exactThresholdKept": len(exact_only),
                    "inclusiveOneBitBoundaryKept": len(inclusive_boundary),
                    "aboveOneBitBoundaryKept": len(above_boundary),
                    "defaultThresholdKept": len(default_threshold),
                    "solidColorsKept": len(solids),
                    "zeroThresholdKept": len(zero_threshold),
                    "emptyKept": len(empty),
                    "flattenedItems": len(flattened),
                    "invalid3dRejected": True,
                    "oneBitSimilarity": boundary,
                },
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
