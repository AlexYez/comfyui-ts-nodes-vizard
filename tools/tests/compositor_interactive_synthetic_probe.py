from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

import numpy as np
from PIL import Image


def main() -> int:
    if len(sys.argv) != 2:
        raise SystemExit("usage: compositor_interactive_synthetic_probe.py <ComfyUI source>")
    source = Path(sys.argv[1]).resolve()
    sys.path.insert(0, str(source))

    import torch
    import comfy_extras.nodes_image_compare as compare_module
    import comfy_extras.nodes_painter as painter_module
    from comfy_extras.nodes_compositor import (
        AddLayer,
        canvas_extent,
        composite_from_state,
        composite_outputs,
        document_items,
        expand_item_frames,
        frame_alpha,
        parse_layer_state,
        state_from_items,
    )

    image_batch = torch.zeros((2, 3, 4, 3), dtype=torch.float32)
    image_batch[0, :, :, 0] = 1.0
    image_batch[1, :, :, 1] = 1.0
    layer_mask = torch.zeros((1, 3, 4), dtype=torch.float32)
    layer_mask[:, 1:, 2:] = 1.0
    layer_doc = AddLayer.execute(
        image_batch,
        mask=layer_mask,
        name="pair",
        x=-1,
        y=2,
        opacity=0.5,
        blend_mode="screen",
        rotation=90.0,
        width=8,
        height=6,
        z_index=3,
        flip_h=True,
    ).result[0]
    item = layer_doc["layers"][0]
    frames = expand_item_frames(document_items(layer_doc))
    assert len(frames) == 2
    assert abs(item["rotation"] - np.pi / 2) < 1e-8
    assert all(frame["w"] == 8 and frame["h"] == 6 for frame in frames)
    repeated_alphas = [frame_alpha(frame["tensor"], frame["mask"]) for frame in frames]
    assert all(alpha is not None for alpha in repeated_alphas)
    assert all(float(alpha.min()) == 0.0 and float(alpha.max()) == 1.0 for alpha in repeated_alphas)

    red = torch.zeros((1, 2, 3, 3), dtype=torch.float32)
    red[..., 0] = 1.0
    opaque_doc = AddLayer.execute(red, name="red").result[0]
    opaque_frames = expand_item_frames(document_items(opaque_doc))
    opaque_alphas = [frame_alpha(frame["tensor"], frame["mask"]) for frame in opaque_frames]
    opaque_rgba = composite_from_state(
        [frame["tensor"] for frame in opaque_frames],
        state_from_items(opaque_frames, canvas_extent(opaque_frames)),
        opaque_alphas,
    )
    opaque_image, opaque_mask = composite_outputs(opaque_rgba)
    assert tuple(opaque_image.shape) == (1, 2, 3, 3)
    assert float(opaque_mask.max()) == 0.0

    opaque_doc["canvas"] = (5, 4)
    green = torch.zeros((1, 2, 2, 4), dtype=torch.float32)
    green[..., 1] = 1.0
    green[..., 3] = 0.5
    two_doc = AddLayer.execute(green, layers=opaque_doc, name="green", x=1, y=1, z_index=4).result[0]
    two_frames = expand_item_frames(document_items(two_doc))
    two_alphas = [frame_alpha(frame["tensor"], frame["mask"]) for frame in two_frames]
    two_rgba = composite_from_state(
        [frame["tensor"] for frame in two_frames],
        state_from_items(two_frames, two_doc["canvas"]),
        two_alphas,
    )
    transparent_image, transparent_mask = composite_outputs(two_rgba)
    assert tuple(transparent_image.shape) == (1, 4, 5, 4)
    assert float(transparent_mask[0, 3, 4]) == 1.0
    assert parse_layer_state("{}") is None
    assert parse_layer_state({"version": 2}) is None

    compare_calls: list[tuple[str, tuple[int, ...]]] = []

    class FakePreview:
        def save_images(self, images, prefix):
            compare_calls.append((prefix, tuple(images.shape)))
            return {
                "ui": {
                    "images": [
                        {"filename": f"{prefix}-{index}.png", "subfolder": "", "type": "temp"}
                        for index in range(len(images))
                    ]
                }
            }

    original_preview = compare_module.nodes.PreviewImage
    compare_module.nodes.PreviewImage = FakePreview
    try:
        compare_output = compare_module.ImageCompare.execute(
            torch.zeros((2, 3, 4, 3)), torch.ones((1, 5, 6, 3)), {}
        )
        empty_compare = compare_module.ImageCompare.execute(None, None, {})
    finally:
        compare_module.nodes.PreviewImage = original_preview
    assert len(compare_output.ui["a_images"]) == 2
    assert len(compare_output.ui["b_images"]) == 1
    assert empty_compare.ui == {"a_images": [], "b_images": []}

    with tempfile.TemporaryDirectory() as temporary:
        overlay_path = Path(temporary) / "paint.png"
        rgba = np.zeros((2, 3, 4), dtype=np.uint8)
        rgba[..., 0] = 255
        rgba[:, 1:, 3] = 128
        Image.fromarray(rgba, "RGBA").save(overlay_path)
        original_resolver = painter_module.folder_paths.get_annotated_filepath
        painter_module.folder_paths.get_annotated_filepath = lambda _: str(overlay_path)
        try:
            base = torch.zeros((2, 4, 6, 3), dtype=torch.float32)
            base[..., 2] = 1.0
            painted_image, painted_mask = painter_module.PainterNode.execute(
                "paint.png", 99, 88, "#00ff00", base
            ).result
            blank_image, blank_mask = painter_module.PainterNode.execute(
                "", 128, 64, "#336699", None
            ).result
        finally:
            painter_module.folder_paths.get_annotated_filepath = original_resolver
    assert tuple(painted_image.shape) == (1, 4, 6, 3)
    assert tuple(painted_mask.shape) == (1, 4, 6)
    assert float(painted_mask.max()) > 0.5
    assert tuple(blank_image.shape) == (1, 64, 128, 3)
    assert tuple(blank_mask.shape) == (1, 64, 128)
    assert np.allclose(blank_image[0, 0, 0].numpy(), [0.2, 0.4, 0.6])
    assert float(blank_mask.max()) == 0.0

    print(
        json.dumps(
            {
                "addLayer": {"frames": len(frames), "rotationRadians": item["rotation"]},
                "compositor": {
                    "opaqueShape": list(opaque_image.shape),
                    "transparentShape": list(transparent_image.shape),
                    "outsideMask": float(transparent_mask[0, 3, 4]),
                },
                "imageCompare": {
                    "aFiles": len(compare_output.ui["a_images"]),
                    "bFiles": len(compare_output.ui["b_images"]),
                    "calls": [[name, list(shape)] for name, shape in compare_calls],
                },
                "painter": {
                    "paintedShape": list(painted_image.shape),
                    "blankShape": list(blank_image.shape),
                    "blankColor": blank_image[0, 0, 0].tolist(),
                },
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
