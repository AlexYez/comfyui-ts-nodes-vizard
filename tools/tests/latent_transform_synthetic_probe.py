from __future__ import annotations

import ast
import json
import sys
import types
from pathlib import Path


def compile_named(path: Path, names: set[str]):
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    body = [
        node
        for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
        and node.name in names
    ]
    return compile(ast.Module(body=body, type_ignores=[]), str(path), "exec")


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit(
            "usage: latent_transform_synthetic_probe.py <pinned-comfyui-source>"
        )

    source = Path(sys.argv[1]).resolve()
    import torch

    utils_namespace = {"torch": torch}
    exec(
        compile_named(source / "comfy" / "utils.py", {"common_upscale"}),
        utils_namespace,
    )
    comfy = types.SimpleNamespace(
        utils=types.SimpleNamespace(common_upscale=utils_namespace["common_upscale"])
    )
    namespace = {"torch": torch, "comfy": comfy}
    exec(
        compile_named(
            source / "nodes.py",
            {"LatentBlend", "LatentRotate", "LatentFlip", "LatentCrop"},
        ),
        namespace,
    )

    marker = {"source": "first"}
    noise_mask = torch.arange(6, dtype=torch.float32).reshape(1, 2, 3)
    matrix = torch.tensor(
        [[[[1.0, 2.0, 3.0], [4.0, 5.0, 6.0]]]], dtype=torch.float32
    )
    latent = {"samples": matrix, "noise_mask": noise_mask, "custom": marker}

    rotate = namespace["LatentRotate"]()
    rotated = {
        setting: rotate.rotate(latent, setting)[0]
        for setting in ("none", "90 degrees", "180 degrees", "270 degrees")
    }
    expected_rotations = {
        "none": [[1.0, 2.0, 3.0], [4.0, 5.0, 6.0]],
        "90 degrees": [[4.0, 1.0], [5.0, 2.0], [6.0, 3.0]],
        "180 degrees": [[6.0, 5.0, 4.0], [3.0, 2.0, 1.0]],
        "270 degrees": [[3.0, 6.0], [2.0, 5.0], [1.0, 4.0]],
    }
    for setting, expected in expected_rotations.items():
        assert rotated[setting]["samples"][0, 0].tolist() == expected
        assert rotated[setting]["noise_mask"] is noise_mask
        assert rotated[setting]["custom"] is marker

    flip = namespace["LatentFlip"]()
    vertical = flip.flip(latent, "x-axis: vertically")[0]
    horizontal = flip.flip(latent, "y-axis: horizontally")[0]
    assert vertical["samples"][0, 0].tolist() == [
        [4.0, 5.0, 6.0],
        [1.0, 2.0, 3.0],
    ]
    assert horizontal["samples"][0, 0].tolist() == [
        [3.0, 2.0, 1.0],
        [6.0, 5.0, 4.0],
    ]
    for output in (vertical, horizontal):
        assert output["samples"].shape == matrix.shape
        assert output["noise_mask"] is noise_mask
        assert output["custom"] is marker

    blend = namespace["LatentBlend"]()
    first_samples = torch.full((2, 4, 4, 6), 2.0)
    second_samples = torch.full((2, 4, 4, 6), 10.0)
    first = {
        "samples": first_samples,
        "noise_mask": noise_mask,
        "custom": marker,
    }
    second = {
        "samples": second_samples,
        "noise_mask": torch.ones((2, 4, 6)),
        "second_only": True,
    }
    blended = {
        factor: blend.blend(first, second, factor)[0]
        for factor in (0.0, 0.25, 0.5, 1.0)
    }
    expected_values = {0.0: 10.0, 0.25: 8.0, 0.5: 6.0, 1.0: 2.0}
    for factor, expected in expected_values.items():
        assert torch.all(blended[factor]["samples"] == expected)
        assert blended[factor]["noise_mask"] is noise_mask
        assert blended[factor]["custom"] is marker
        assert "second_only" not in blended[factor]

    spatial_second = {"samples": torch.full((2, 4, 2, 2), 7.0)}
    spatial_resize = blend.blend(first, spatial_second, 0.0)[0]
    assert spatial_resize["samples"].shape == first_samples.shape
    assert torch.allclose(spatial_resize["samples"], torch.full_like(first_samples, 7.0))

    batch_broadcast = blend.blend(
        first,
        {"samples": torch.full((1, 4, 4, 6), 4.0)},
        0.5,
    )[0]
    assert batch_broadcast["samples"].shape == first_samples.shape
    assert torch.all(batch_broadcast["samples"] == 3.0)

    incompatible_batch_error = ""
    try:
        blend.blend(
            first,
            {"samples": torch.ones((3, 4, 4, 6))},
            0.5,
        )
    except RuntimeError as exc:
        incompatible_batch_error = str(exc)
    assert incompatible_batch_error

    crop = namespace["LatentCrop"]()
    crop_samples = torch.arange(12 * 16, dtype=torch.float32).reshape(1, 1, 12, 16)
    crop_mask = torch.ones((1, 96, 128), dtype=torch.float32)
    crop_marker = {"source": "crop"}
    crop_input = {
        "samples": crop_samples,
        "noise_mask": crop_mask,
        "custom": crop_marker,
    }
    cropped = crop.crop(
        crop_input, width=64, height=64, x=16, y=8
    )[0]
    expected_crop = crop_samples[:, :, 1:9, 2:10]
    assert cropped["samples"].shape == (1, 1, 8, 8)
    assert torch.equal(cropped["samples"], expected_crop)
    assert cropped["noise_mask"] is crop_mask
    assert cropped["custom"] is crop_marker
    shares_storage = (
        cropped["samples"].untyped_storage().data_ptr()
        == crop_samples.untyped_storage().data_ptr()
    )
    assert shares_storage

    edge_crop = crop.crop(
        crop_input, width=512, height=512, x=120, y=88
    )[0]
    assert edge_crop["samples"].shape == (1, 1, 8, 8)
    assert torch.equal(edge_crop["samples"], crop_samples[:, :, 4:12, 8:16])

    small_samples = torch.arange(36, dtype=torch.float32).reshape(1, 1, 6, 6)
    small_crop = crop.crop(
        {"samples": small_samples}, width=64, height=64, x=0, y=0
    )[0]
    assert small_crop["samples"].shape == (1, 1, 2, 2)
    assert torch.equal(small_crop["samples"], small_samples[:, :, 4:6, 4:6])

    print(
        json.dumps(
            {
                "rotate": {
                    setting: {
                        "matrix": output["samples"][0, 0].tolist(),
                        "shape": list(output["samples"].shape),
                        "metadataUnchanged": output["noise_mask"] is noise_mask,
                    }
                    for setting, output in rotated.items()
                },
                "flip": {
                    "vertical": vertical["samples"][0, 0].tolist(),
                    "horizontal": horizontal["samples"][0, 0].tolist(),
                    "shape": list(horizontal["samples"].shape),
                    "metadataUnchanged": horizontal["noise_mask"] is noise_mask,
                },
                "blend": {
                    "values": {
                        str(factor): float(output["samples"][0, 0, 0, 0])
                        for factor, output in blended.items()
                    },
                    "spatialResizeShape": list(spatial_resize["samples"].shape),
                    "batchBroadcastShape": list(batch_broadcast["samples"].shape),
                    "incompatibleBatchRejected": True,
                    "metadataFromFirst": blended[0.0]["custom"] is marker,
                },
                "crop": {
                    "shape": list(cropped["samples"].shape),
                    "originValue": float(cropped["samples"][0, 0, 0, 0]),
                    "edgeShape": list(edge_crop["samples"].shape),
                    "edgeOriginValue": float(edge_crop["samples"][0, 0, 0, 0]),
                    "smallInputShape": list(small_crop["samples"].shape),
                    "smallInputOriginValue": float(
                        small_crop["samples"][0, 0, 0, 0]
                    ),
                    "sharesStorage": shares_storage,
                    "metadataUnchanged": cropped["noise_mask"] is crop_mask,
                },
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
