from __future__ import annotations

import json
import sys
from pathlib import Path
from types import SimpleNamespace


def values(output):
    return output.args


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit("usage: ltxv_legacy_i2v_synthetic_probe.py <pinned-comfyui-source>")
    source = Path(sys.argv[1]).resolve()
    sys.path.insert(0, str(source))

    import torch
    import comfy_extras.nodes_lt as nodes_lt

    class FakeVAE:
        downscale_index_formula = (8, 32, 32)

        def __init__(self) -> None:
            self.inputs: list[torch.Tensor] = []

        def encode(self, pixels):
            self.inputs.append(pixels.clone())
            batch, height, width, channels = pixels.shape
            assert channels == 3
            return torch.full((batch, 128, 1, height // 32, width // 32), 5.0)

    old_device = nodes_lt.comfy.model_management.intermediate_device
    nodes_lt.comfy.model_management.intermediate_device = lambda: torch.device("cpu")
    try:
        empty, = values(nodes_lt.EmptyLTXVLatentVideo.execute(768, 512, 97, 1))
        assert list(empty["samples"].shape) == [1, 128, 13, 16, 24]
        assert empty["downscale_ratio_spacial"] == 32
        assert not bool(empty["samples"].any())

        vae = FakeVAE()
        positive_tensor = torch.tensor([[1.0]])
        negative_tensor = torch.tensor([[0.0]])
        positive = [[positive_tensor, {"branch": "positive"}]]
        negative = [[negative_tensor, {"branch": "negative"}]]
        rgba = torch.rand((1, 40, 50, 4), generator=torch.Generator().manual_seed(7))
        positive_out, negative_out, legacy = values(
            nodes_lt.LTXVImgToVideo.execute(
                positive, negative, rgba, vae, 64, 64, 9, 2, 0.25
            )
        )
        assert positive_out is positive and negative_out is negative
        legacy_conditioning_identity = positive_out is positive and negative_out is negative
        assert list(legacy["samples"].shape) == [2, 128, 2, 2, 2]
        assert bool((legacy["samples"][:, :, 0] == 5.0).all())
        assert not bool(legacy["samples"][:, :, 1].any())
        assert list(legacy["noise_mask"].shape) == [2, 1, 2, 1, 1]
        assert bool((legacy["noise_mask"][:, :, 0] == 0.75).all())
        assert bool((legacy["noise_mask"][:, :, 1] == 1.0).all())
        assert vae.inputs[0].shape == (1, 64, 64, 3)

        _, _, strength_one = values(
            nodes_lt.LTXVImgToVideo.execute(positive, negative, rgba, vae, 64, 64, 9, 1, 1.0)
        )
        _, _, strength_zero = values(
            nodes_lt.LTXVImgToVideo.execute(positive, negative, rgba, vae, 64, 64, 9, 1, 0.0)
        )
        assert bool((strength_one["noise_mask"][:, :, 0] == 0).all())
        assert bool((strength_zero["noise_mask"][:, :, 0] == 1).all())
    finally:
        nodes_lt.comfy.model_management.intermediate_device = old_device

    input_samples = torch.ones((1, 128, 2, 2, 3))
    input_mask = torch.full((1, 1, 2, 1, 1), 0.4)
    inplace_input = {
        "samples": input_samples,
        "noise_mask": input_mask,
        "downscale_ratio_spacial": 32,
        "custom": {"shared": True},
    }
    small_rgba = torch.rand((1, 32, 40, 4), generator=torch.Generator().manual_seed(9))
    (inplace,) = values(
        nodes_lt.LTXVImgToVideoInplace.execute(vae, small_rgba, inplace_input, 0.5, False)
    )
    assert inplace["samples"] is not input_samples
    assert bool((inplace["samples"][:, :, 0] == 5.0).all())
    assert bool((inplace["samples"][:, :, 1] == 1.0).all())
    assert bool((input_samples == 1.0).all())
    assert bool((inplace["noise_mask"][:, :, 0] == 0.5).all())
    assert bool((inplace["noise_mask"][:, :, 1] == 0.4).all())
    assert input_mask is not inplace["noise_mask"]
    assert set(inplace) == {"samples", "noise_mask"}
    assert vae.inputs[-1].shape == (1, 64, 96, 3)

    (bypassed,) = nodes_lt.LTXVImgToVideoInplace.execute(vae, small_rgba, inplace_input, 1.0, True)
    assert bypassed is inplace_input

    nested_meta = {"items": [1, 2]}
    positive = [[positive_tensor, {"frame_rate": 12.0, "nested": nested_meta}]]
    negative = [[negative_tensor, {"other": 3, "nested": nested_meta}]]
    conditioned_positive, conditioned_negative = values(
        nodes_lt.LTXVConditioning.execute(positive, negative, 24.0)
    )
    assert conditioned_positive is not positive and conditioned_negative is not negative
    assert conditioned_positive[0][0] is positive_tensor
    assert conditioned_negative[0][0] is negative_tensor
    assert conditioned_positive[0][1] is not positive[0][1]
    assert conditioned_positive[0][1]["frame_rate"] == 24.0
    assert conditioned_negative[0][1]["frame_rate"] == 24.0
    assert positive[0][1]["frame_rate"] == 12.0
    assert "frame_rate" not in negative[0][1]
    assert conditioned_positive[0][1]["nested"] is nested_meta
    assert conditioned_negative[0][1]["nested"] is nested_meta

    print(
        json.dumps(
            {
                "empty": {"shape": list(empty["samples"].shape), "ratio": empty["downscale_ratio_spacial"]},
                "legacy": {
                    "shape": list(legacy["samples"].shape),
                    "vaeInputShape": list(vae.inputs[0].shape),
                    "conditioningIdentity": legacy_conditioning_identity,
                    "maskFirst": float(legacy["noise_mask"][0, 0, 0, 0, 0]),
                    "maskRest": float(legacy["noise_mask"][0, 0, 1, 0, 0]),
                    "strengthOneMask": float(strength_one["noise_mask"][0, 0, 0, 0, 0]),
                    "strengthZeroMask": float(strength_zero["noise_mask"][0, 0, 0, 0, 0]),
                },
                "inplace": {
                    "vaeInputShape": list(vae.inputs[-1].shape),
                    "inputUnchanged": bool((input_samples == 1.0).all()),
                    "metadataDiscarded": set(inplace) == {"samples", "noise_mask"},
                    "maskFirst": float(inplace["noise_mask"][0, 0, 0, 0, 0]),
                    "maskRest": float(inplace["noise_mask"][0, 0, 1, 0, 0]),
                    "bypassIdentity": bypassed is inplace_input,
                },
                "conditioning": {
                    "tensorIdentity": conditioned_positive[0][0] is positive_tensor,
                    "metadataCopied": conditioned_positive[0][1] is not positive[0][1],
                    "nestedShared": conditioned_positive[0][1]["nested"] is nested_meta,
                    "positiveRate": conditioned_positive[0][1]["frame_rate"],
                    "negativeRate": conditioned_negative[0][1]["frame_rate"],
                },
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
