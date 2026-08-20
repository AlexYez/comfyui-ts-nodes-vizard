from __future__ import annotations

import json
import sys
from pathlib import Path


def output_args(node_output):
    return node_output.args


def raises(expected: type[BaseException], callback) -> str:
    try:
        callback()
    except expected as exc:
        return str(exc)
    raise AssertionError(f"expected {expected.__name__}")


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit("usage: ltxv_guide_preprocess_synthetic_probe.py <pinned-comfyui-source>")
    source = Path(sys.argv[1]).resolve()
    sys.path.insert(0, str(source))

    import torch
    import comfy_extras.nodes_lt as nodes_lt

    class FakeModel:
        def __init__(self, metadata):
            self.metadata = metadata

        def get_attachment(self, name):
            assert name == "lora_metadata"
            return self.metadata

    (fallback,) = output_args(nodes_lt.GetICLoRAParameters.execute(FakeModel(None)))
    (rounded_even,) = output_args(
        nodes_lt.GetICLoRAParameters.execute(FakeModel({"vendor.reference_downscale_factor": "2.5"}))
    )
    (rounded_up,) = output_args(
        nodes_lt.GetICLoRAParameters.execute(FakeModel({"x.reference_downscale_factor": "2.6"}))
    )
    (bad_value,) = output_args(
        nodes_lt.GetICLoRAParameters.execute(FakeModel({"reference_downscale_factor": "bad"}))
    )
    overflow = raises(
        OverflowError,
        lambda: nodes_lt.GetICLoRAParameters.execute(
            FakeModel({"reference_downscale_factor": "inf"})
        ),
    )
    assert fallback == {"reference_downscale_factor": 1}
    assert rounded_even == {"reference_downscale_factor": 2}
    assert rounded_up == {"reference_downscale_factor": 3}
    assert bad_value == {"reference_downscale_factor": 1}

    class FakeVAE:
        downscale_index_formula = (8, 32, 32)

        def __init__(self) -> None:
            self.inputs: list[torch.Tensor] = []

        def encode(self, pixels):
            self.inputs.append(pixels.clone())
            batch, _, _, channels = pixels.shape
            assert channels == 3
            latent_frames = ((batch - 1) // 8) + 1
            return torch.full((1, 128, latent_frames, 2, 2), 4.0)

    positive_tensor = torch.tensor([[1.0]])
    negative_tensor = torch.tensor([[0.0]])
    positive = [[positive_tensor, {"branch": "positive"}]]
    negative = [[negative_tensor, {"branch": "negative"}]]
    samples = torch.zeros((1, 128, 3, 2, 2))
    mask = torch.ones((1, 1, 3, 1, 1))
    latent = {"samples": samples, "noise_mask": mask, "custom": 9}
    attention = torch.ones((1, 64, 64))
    vae = FakeVAE()
    positive_out, negative_out, guided = output_args(
        nodes_lt.LTXVAddGuide.execute(
            positive,
            negative,
            vae,
            latent,
            torch.rand((1, 64, 64, 4), generator=torch.Generator().manual_seed(4)),
            0,
            0.75,
            attention,
            None,
        )
    )
    assert list(guided["samples"].shape) == [1, 128, 4, 2, 2]
    assert bool((guided["samples"][:, :, -1] == 4.0).all())
    assert list(guided["noise_mask"].shape) == [1, 1, 4, 1, 1]
    assert float(guided["noise_mask"][0, 0, -1, 0, 0]) == 0.25
    assert set(guided) == {"samples", "noise_mask"}
    assert "custom" in latent
    positive_meta = positive_out[0][1]
    negative_meta = negative_out[0][1]
    assert positive_out[0][0] is positive_tensor and negative_out[0][0] is negative_tensor
    assert list(positive_meta["keyframe_idxs"].shape) == [1, 3, 4, 2]
    assert len(positive_meta["guide_attention_entries"]) == 1
    assert positive_meta["guide_attention_entries"] is not negative_meta["guide_attention_entries"]
    pixel_mask = positive_meta["guide_attention_entries"][0]["pixel_mask"]
    assert list(pixel_mask.shape) == [1, 1, 1, 64, 64]

    aligned = nodes_lt.LTXVAddGuide.get_latent_index([], 20, 9, 10, (8, 32, 32))
    negative_index = nodes_lt.LTXVAddGuide.get_latent_index([], 20, 1, -1, (8, 32, 32))
    assert aligned == (9, 2)
    assert negative_index == (152, 19)
    assert nodes_lt.LTXVAddGuide.get_reference_downscale_factor({"reference_downscale_factor": "2.6"}) == 3
    assert nodes_lt.LTXVAddGuide.get_reference_downscale_factor({"reference_downscale_factor": "bad"}) == 1

    numbered_frames = torch.stack(
        [torch.full((64, 64, 3), float(index) / 10.0) for index in range(9)]
    )
    _, _, noncausal = output_args(
        nodes_lt.LTXVAddGuide.execute(
            positive,
            negative,
            vae,
            {"samples": torch.zeros((1, 128, 5, 2, 2))},
            numbered_frames,
            9,
            1.0,
        )
    )
    noncausal_pixels = vae.inputs[-1]
    assert list(noncausal_pixels.shape) == [9, 64, 64, 3]
    assert bool((noncausal_pixels[0] == numbered_frames[0]).all())
    assert bool((noncausal_pixels[1] == numbered_frames[0]).all())
    assert bool((noncausal_pixels[-1] == numbered_frames[7]).all())
    assert not bool((noncausal_pixels == numbered_frames[8]).all(dim=-1).all(dim=-1).all(dim=-1).any())
    assert list(noncausal["samples"].shape) == [1, 128, 6, 2, 2]

    sparse = torch.arange(256, dtype=torch.float32).reshape(1, 128, 1, 1, 2)
    dilated, dilated_mask = nodes_lt.LTXVAddGuide.dilate_latent(sparse, 2)
    assert list(dilated.shape) == [1, 128, 1, 2, 4]
    assert bool((dilated[..., ::2, ::2] == sparse).all())
    assert bool((dilated_mask[..., ::2, ::2] == 1).all())
    assert bool((dilated_mask[..., 1::2, :] == -1).all())
    channel_error = raises(
        ValueError,
        lambda: nodes_lt.LTXVAddGuide.append_keyframe(
            positive,
            negative,
            0,
            torch.zeros((1, 132, 2, 1, 1)),
            torch.ones((1, 1, 2, 1, 1)),
            torch.zeros((1, 128, 1, 1, 1)),
            1.0,
            (8, 32, 32),
        ),
    )

    cropped_positive, cropped_negative, cropped = output_args(
        nodes_lt.LTXVCropGuides.execute(positive_out, negative_out, guided)
    )
    assert list(cropped["samples"].shape) == [1, 128, 3, 2, 2]
    assert list(cropped["noise_mask"].shape) == [1, 1, 3, 1, 1]
    assert cropped_positive[0][1]["keyframe_idxs"] is None
    assert cropped_positive[0][1]["guide_attention_entries"] is None
    assert cropped_negative[0][1]["keyframe_idxs"] is None

    plain_positive = [[positive_tensor, {"plain": True}]]
    plain_negative = [[negative_tensor, {"plain": True}]]
    plain_latent = {"samples": torch.ones((1, 128, 2, 1, 1)), "custom": 7}
    plain_positive_out, plain_negative_out, plain = output_args(
        nodes_lt.LTXVCropGuides.execute(plain_positive, plain_negative, plain_latent)
    )
    assert plain_positive_out is plain_positive and plain_negative_out is plain_negative
    assert set(plain) == {"samples", "noise_mask"}
    assert list(plain["noise_mask"].shape) == [1, 1, 2, 1, 1]

    zero_input = torch.rand((2, 5, 7, 3), generator=torch.Generator().manual_seed(8))
    frame_zero = zero_input[0]
    zero_frame = nodes_lt.preprocess(frame_zero, 0)
    (zero_batch,) = output_args(nodes_lt.LTXVPreprocess.execute(zero_input, 0))
    assert zero_frame is frame_zero
    assert torch.equal(zero_batch, zero_input)
    assert zero_batch is not zero_input
    rgb = torch.rand((8, 10, 3), generator=torch.Generator().manual_seed(12))
    compressed_rgb = nodes_lt.preprocess(rgb, 18)
    assert list(compressed_rgb.shape) == [8, 10, 3]
    rgba_error = raises(
        ValueError,
        lambda: nodes_lt.preprocess(torch.rand((8, 10, 4)), 18),
    )
    assert "Unexpected numpy array shape" in rgba_error

    print(
        json.dumps(
            {
                "metadata": {
                    "fallback": fallback["reference_downscale_factor"],
                    "roundEven": rounded_even["reference_downscale_factor"],
                    "roundUp": rounded_up["reference_downscale_factor"],
                    "overflow": bool(overflow),
                },
                "guide": {
                    "shape": list(guided["samples"].shape),
                    "maskTail": float(guided["noise_mask"][0, 0, -1, 0, 0]),
                    "aligned": list(aligned),
                    "negativeIndex": list(negative_index),
                    "pixelMask": list(pixel_mask.shape),
                    "channelError": "combined AV" in channel_error,
                    "noncausalVaeInput": list(noncausal_pixels.shape),
                    "noncausalLastOriginal": float(noncausal_pixels[-1, 0, 0, 0]),
                },
                "crop": {"shape": list(cropped["samples"].shape), "plainMetadataDropped": set(plain) == {"samples", "noise_mask"}},
                "preprocess": {"zeroEqual": bool(torch.equal(zero_batch, zero_input)), "newBatch": zero_batch is not zero_input, "rgbShape": list(compressed_rgb.shape), "rgbaError": "Unexpected numpy array shape" in rgba_error},
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
