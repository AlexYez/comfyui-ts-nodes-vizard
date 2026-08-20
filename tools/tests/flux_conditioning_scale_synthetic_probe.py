from __future__ import annotations

import json
import sys
from pathlib import Path


def output_args(output):
    return output.args


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit("usage: flux_conditioning_scale_synthetic_probe.py <pinned-comfyui-source>")
    source = Path(sys.argv[1]).resolve()
    sys.path.insert(0, str(source))

    import torch
    import nodes
    import comfy_extras.nodes_flux as nodes_flux

    class FakeClip:
        def __init__(self) -> None:
            self.tokenize_calls: list[str] = []
            self.encoded = None

        def tokenize(self, text):
            self.tokenize_calls.append(text)
            return {"clip_l": [f"clip:{text}"], "t5xxl": [f"t5:{text}"], "shared": [f"shared:{text}"]}

        def encode_from_tokens_scheduled(self, tokens, add_dict):
            self.encoded = (tokens, add_dict)
            return [[torch.tensor([[3.0]]), {**add_dict, "tokens": tokens}]]

    clip = FakeClip()
    (encoded,) = output_args(nodes_flux.CLIPTextEncodeFlux.execute(clip, "short", "long description", 3.5))
    tokens, add_dict = clip.encoded
    assert clip.tokenize_calls == ["short", "long description"]
    assert tokens["clip_l"] == ["clip:short"]
    assert tokens["shared"] == ["shared:short"]
    assert tokens["t5xxl"] == ["t5:long description"]
    assert add_dict == {"guidance": 3.5}
    assert encoded[0][1]["guidance"] == 3.5

    tensor = torch.tensor([[1.0]])
    nested = {"shared": [1, 2]}
    conditioning = [[tensor, {"guidance": 1.0, "nested": nested}], [tensor, {"other": 4}]]
    (guided,) = output_args(nodes_flux.FluxGuidance.execute(conditioning, 4.0))
    assert guided is not conditioning
    assert all(entry[0] is tensor for entry in guided)
    assert guided[0][1] is not conditioning[0][1]
    assert guided[0][1]["guidance"] == 4.0 and guided[1][1]["guidance"] == 4.0
    assert guided[0][1]["nested"] is nested
    assert conditioning[0][1]["guidance"] == 1.0 and "guidance" not in conditioning[1][1]

    (disabled,) = output_args(nodes_flux.FluxDisableGuidance.execute(guided))
    assert all(entry[0] is tensor for entry in disabled)
    assert all(entry[1]["guidance"] is None for entry in disabled)
    assert guided[0][1]["guidance"] == 4.0
    assert disabled[0][1]["nested"] is nested

    pooled = torch.tensor([[2.0]])
    lyrics = torch.tensor([[3.0]])
    (zeroed,) = nodes.ConditioningZeroOut().zero_out([[tensor, {"pooled_output": pooled, "conditioning_lyrics": lyrics, "guidance": 3.5, "marker": "kept"}]])
    assert torch.equal(zeroed[0][0], torch.zeros_like(tensor))
    assert torch.equal(zeroed[0][1]["pooled_output"], torch.zeros_like(pooled))
    assert torch.equal(zeroed[0][1]["conditioning_lyrics"], torch.zeros_like(lyrics))
    assert zeroed[0][1]["guidance"] == 3.5 and zeroed[0][1]["marker"] == "kept"

    calls: list[dict[str, object]] = []
    original_upscale = nodes_flux.comfy.utils.common_upscale

    def fake_upscale(image, width, height, method, crop):
        calls.append({"input": list(image.shape), "width": width, "height": height, "method": method, "crop": crop})
        return torch.zeros((image.shape[0], image.shape[1], height, width), dtype=image.dtype)

    nodes_flux.comfy.utils.common_upscale = fake_upscale
    try:
        (square,) = output_args(nodes_flux.FluxKontextImageScale.execute(torch.zeros((2, 500, 500, 4))))
        (landscape,) = output_args(nodes_flux.FluxKontextImageScale.execute(torch.zeros((1, 400, 600, 3))))
        (portrait,) = output_args(nodes_flux.FluxKontextImageScale.execute(torch.zeros((1, 600, 400, 3))))
    finally:
        nodes_flux.comfy.utils.common_upscale = original_upscale

    crop_input = torch.tensor([[[[0.0, 0.25, 0.75, 1.0], [0.0, 0.25, 0.75, 1.0]]]])
    crop_then_resize = nodes_flux.comfy.utils.common_upscale(crop_input, 2, 2, "lanczos", "center")
    resize_without_crop = nodes_flux.comfy.utils.common_upscale(crop_input, 2, 2, "lanczos", "disabled")
    assert torch.allclose(crop_then_resize[0, 0], torch.tensor([0.2471, 0.7490]), atol=0.002)
    assert torch.allclose(resize_without_crop[0, 0], torch.tensor([0.1490, 0.8471]), atol=0.002)

    quantization_input = torch.tensor([[[[-0.25, 0.5, 1.25], [1 / 255, 64 / 255, 254 / 255]]]]).repeat(1, 3, 1, 1)
    quantized = nodes_flux.comfy.utils.common_upscale(quantization_input, 3, 2, "lanczos", "disabled")
    quantization_expected = torch.tensor([[[[0.0, 127 / 255, 1.0], [1 / 255, 64 / 255, 254 / 255]]]]).repeat(1, 3, 1, 1)
    assert torch.allclose(quantized, quantization_expected, atol=1e-7)

    (mono,) = output_args(nodes_flux.FluxKontextImageScale.execute(torch.full((1, 2, 3, 1), 64 / 255)))
    assert list(mono.shape) == [1, 1248, 832]
    assert torch.allclose(mono, torch.full_like(mono, 64 / 255), atol=1e-7)

    assert list(square.shape) == [2, 1024, 1024, 4]
    assert list(landscape.shape) == [1, 832, 1248, 3]
    assert list(portrait.shape) == [1, 1248, 832, 3]
    assert calls[0] == {"input": [2, 4, 500, 500], "width": 1024, "height": 1024, "method": "lanczos", "crop": "center"}
    assert calls[1]["width"] == 1248 and calls[1]["height"] == 832
    assert calls[2]["width"] == 832 and calls[2]["height"] == 1248

    print(json.dumps({
        "encode": {"calls": clip.tokenize_calls, "clip": tokens["clip_l"], "t5": tokens["t5xxl"], "guidance": add_dict["guidance"]},
        "metadata": {"guided": guided[0][1]["guidance"], "disabled": disabled[0][1]["guidance"], "tensorIdentity": disabled[0][0] is tensor, "nestedShared": disabled[0][1]["nested"] is nested, "zeroOutGuidance": zeroed[0][1]["guidance"], "zeroOutMarker": zeroed[0][1]["marker"]},
        "scale": {"square": list(square.shape), "landscape": list(landscape.shape), "portrait": list(portrait.shape), "calls": calls, "cropThenResize": crop_then_resize[0, 0].tolist(), "resizeWithoutCrop": resize_without_crop[0, 0].tolist(), "quantized": quantized[0, 0].tolist(), "mono": list(mono.shape), "monoLevel": mono[0, 0, 0].item()},
    }, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
