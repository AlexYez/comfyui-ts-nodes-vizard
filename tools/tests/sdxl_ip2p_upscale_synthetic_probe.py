from __future__ import annotations

import ast
import json
import sys
import types
from pathlib import Path


def _compile_execute_classes(path: Path, names: set[str], namespace: dict) -> None:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    classes: list[ast.ClassDef] = []
    for node in tree.body:
        if not isinstance(node, ast.ClassDef) or node.name not in names:
            continue
        execute = next(
            item
            for item in node.body
            if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef))
            and item.name == "execute"
        )
        classes.append(
            ast.ClassDef(
                name=node.name,
                bases=[],
                keywords=[],
                body=[execute],
                decorator_list=[],
            )
        )
    if {item.name for item in classes} != names:
        raise AssertionError(f"missing execute classes in {path}")
    module = ast.fix_missing_locations(ast.Module(body=classes, type_ignores=[]))
    exec(compile(module, str(path), "exec"), namespace)


def _compile_function(path: Path, name: str, namespace: dict) -> None:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    function = next(
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name == name
    )
    module = ast.fix_missing_locations(ast.Module(body=[function], type_ignores=[]))
    exec(compile(module, str(path), "exec"), namespace)


class FakeClip:
    def __init__(self, token_map: dict[str, dict[str, list[str]]]):
        self.token_map = token_map
        self.calls: list[str] = []
        self.encoded: list[tuple[dict, dict]] = []

    def tokenize(self, text: str):
        self.calls.append(text)
        value = self.token_map[text]
        return {key: list(items) for key, items in value.items()}

    def encode_from_tokens_scheduled(self, tokens, add_dict):
        snapshot = ({key: list(items) for key, items in tokens.items()}, dict(add_dict))
        self.encoded.append(snapshot)
        return snapshot


class FakeVAE:
    def __init__(self, torch_module):
        self.torch = torch_module
        self.inputs = []
        self.result = None

    def encode(self, pixels):
        self.inputs.append(pixels)
        self.result = self.torch.arange(
            pixels.shape[0] * 4 * max(1, pixels.shape[1] // 8) * max(1, pixels.shape[2] // 8),
            dtype=self.torch.float32,
        ).reshape(
            pixels.shape[0],
            4,
            max(1, pixels.shape[1] // 8),
            max(1, pixels.shape[2] // 8),
        )
        return self.result


def run_probe(source: Path) -> dict:
    import torch

    io = types.SimpleNamespace(NodeOutput=lambda *values: values)
    namespace = {"torch": torch, "io": io}
    _compile_execute_classes(
        source / "comfy_extras" / "nodes_clip_sdxl.py",
        {"CLIPTextEncodeSDXL", "CLIPTextEncodeSDXLRefiner"},
        namespace,
    )
    _compile_execute_classes(
        source / "comfy_extras" / "nodes_ip2p.py",
        {"InstructPixToPixConditioning"},
        namespace,
    )

    upscale_calls: list[dict] = []

    def fake_upscale(samples, width, height, method, crop):
        upscale_calls.append(
            {
                "input": samples.clone(),
                "width": width,
                "height": height,
                "method": method,
                "crop": crop,
            }
        )
        return torch.full(
            (samples.shape[0], samples.shape[1], height, width),
            0.25,
            dtype=samples.dtype,
            device=samples.device,
        )

    comfy = types.SimpleNamespace(
        utils=types.SimpleNamespace(common_upscale=fake_upscale)
    )
    namespace["comfy"] = comfy
    _compile_execute_classes(
        source / "comfy_extras" / "nodes_sdupscale.py",
        {"SD_4XUpscale_Conditioning"},
        namespace,
    )

    clip = FakeClip(
        {
            "g-long": {"g": ["g0", "g1", "g2"], "l": ["unused"]},
            "l-short": {"g": ["unused"], "l": ["l0"]},
            "": {"g": ["empty-g"], "l": ["empty-l"]},
        }
    )
    sdxl_output = namespace["CLIPTextEncodeSDXL"].execute(
        clip,
        width=1280,
        height=768,
        crop_w=16,
        crop_h=8,
        target_width=1024,
        target_height=1024,
        text_g="g-long",
        text_l="l-short",
    )[0]
    sdxl_tokens, sdxl_metadata = sdxl_output
    assert sdxl_tokens["g"] == ["g0", "g1", "g2"]
    assert sdxl_tokens["l"] == ["l0", "empty-l", "empty-l"]
    assert sdxl_metadata == {
        "width": 1280,
        "height": 768,
        "crop_w": 16,
        "crop_h": 8,
        "target_width": 1024,
        "target_height": 1024,
    }

    clip_reverse = FakeClip(
        {
            "g-short": {"g": ["g0"], "l": ["unused"]},
            "l-long": {"g": ["unused"], "l": ["l0", "l1", "l2"]},
            "": {"g": ["empty-g"], "l": ["empty-l"]},
        }
    )
    reverse_tokens = namespace["CLIPTextEncodeSDXL"].execute(
        clip_reverse, 1024, 1024, 0, 0, 1024, 1024, "g-short", "l-long"
    )[0][0]
    assert reverse_tokens["g"] == ["g0", "empty-g", "empty-g"]
    assert reverse_tokens["l"] == ["l0", "l1", "l2"]

    refiner_clip = FakeClip(
        {"refine": {"g": ["unused"], "l": ["ref-token"]}}
    )
    refiner_output = namespace["CLIPTextEncodeSDXLRefiner"].execute(
        refiner_clip,
        ascore=6.5,
        width=1216,
        height=832,
        text="refine",
    )[0]
    assert refiner_output[1] == {
        "aesthetic_score": 6.5,
        "width": 1216,
        "height": 832,
    }

    pixels = torch.linspace(0.0, 1.0, 2 * 11 * 14 * 3).reshape(2, 11, 14, 3)
    vae = FakeVAE(torch)
    positive_tensor = torch.tensor([[1.0, 2.0]])
    negative_tensor = torch.tensor([[3.0, 4.0]])
    positive_nested = {"name": "positive"}
    negative_nested = {"name": "negative"}
    positive_meta = {"strength": 0.8, "nested": positive_nested}
    negative_meta = {"strength": 0.2, "nested": negative_nested}
    positive = [[positive_tensor, positive_meta]]
    negative = [[negative_tensor, negative_meta]]
    ip2p_positive, ip2p_negative, ip2p_latent = namespace[
        "InstructPixToPixConditioning"
    ].execute(positive, negative, pixels, vae)
    expected_crop = pixels[:, 1:9, 3:11, :]
    assert torch.equal(vae.inputs[0], expected_crop)
    assert ip2p_positive[0][0] is positive_tensor
    assert ip2p_negative[0][0] is negative_tensor
    assert ip2p_positive[0][1] is not positive_meta
    assert ip2p_negative[0][1] is not negative_meta
    assert ip2p_positive[0][1]["nested"] is positive_nested
    assert ip2p_negative[0][1]["nested"] is negative_nested
    assert ip2p_positive[0][1]["concat_latent_image"] is vae.result
    assert ip2p_negative[0][1]["concat_latent_image"] is vae.result
    assert "concat_latent_image" not in positive_meta
    assert "concat_latent_image" not in negative_meta
    assert torch.equal(ip2p_latent["samples"], torch.zeros_like(vae.result))

    images = torch.linspace(0.0, 1.0, 2 * 5 * 7 * 3).reshape(2, 5, 7, 3)
    upscale_positive_meta = {"tag": "p"}
    upscale_negative_meta = {"tag": "n"}
    upscale_positive = [[positive_tensor, upscale_positive_meta]]
    upscale_negative = [[negative_tensor, upscale_negative_meta]]
    up_positive, up_negative, up_latent = namespace[
        "SD_4XUpscale_Conditioning"
    ].execute(images, upscale_positive, upscale_negative, 4.0, 0.125)
    call = upscale_calls[0]
    assert (call["width"], call["height"], call["method"], call["crop"]) == (
        7,
        5,
        "bilinear",
        "center",
    )
    assert torch.allclose(call["input"], images.movedim(-1, 1) * 2.0 - 1.0)
    assert up_positive[0][1] is not upscale_positive_meta
    assert up_negative[0][1] is not upscale_negative_meta
    assert up_positive[0][1]["concat_image"] is up_negative[0][1]["concat_image"]
    assert up_positive[0][1]["noise_augmentation"] == 0.125
    assert up_negative[0][1]["noise_augmentation"] == 0.125
    assert "concat_image" not in upscale_positive_meta
    assert "concat_image" not in upscale_negative_meta
    assert up_latent["samples"].shape == (2, 4, 5, 7)
    assert up_latent["samples"].device.type == "cpu"
    assert up_latent["samples"].dtype == torch.float32

    exact_utils_namespace = {"torch": torch}
    _compile_function(
        source / "comfy" / "utils.py", "common_upscale", exact_utils_namespace
    )
    namespace["comfy"] = types.SimpleNamespace(
        utils=types.SimpleNamespace(
            common_upscale=exact_utils_namespace["common_upscale"]
        )
    )
    zero_ratio_error = ""
    try:
        namespace["SD_4XUpscale_Conditioning"].execute(
            images, upscale_positive, upscale_negative, 0.0, 0.0
        )
    except Exception as exc:  # exact pinned source exposes an invalid zero target
        zero_ratio_error = type(exc).__name__
    assert zero_ratio_error == "ZeroDivisionError"

    return {
        "sdxl": {
            "calls": clip.calls,
            "gLength": len(sdxl_tokens["g"]),
            "lLength": len(sdxl_tokens["l"]),
            "lPadding": sdxl_tokens["l"][1:],
            "reverseGPadding": reverse_tokens["g"][1:],
            "metadata": sdxl_metadata,
        },
        "refiner": {
            "calls": refiner_clip.calls,
            "metadata": refiner_output[1],
        },
        "ip2p": {
            "inputShape": list(pixels.shape),
            "croppedShape": list(vae.inputs[0].shape),
            "cropMatchesCenter": torch.equal(vae.inputs[0], expected_crop),
            "metadataCopied": ip2p_positive[0][1] is not positive_meta,
            "encodedLatentShared": ip2p_positive[0][1]["concat_latent_image"]
            is ip2p_negative[0][1]["concat_latent_image"],
            "zeroLatentShape": list(ip2p_latent["samples"].shape),
        },
        "sd4x": {
            "requestedConditionalSize": [call["height"], call["width"]],
            "latentShape": list(up_latent["samples"].shape),
            "latentDevice": up_latent["samples"].device.type,
            "noiseMetadata": up_positive[0][1]["noise_augmentation"],
            "zeroRatioError": zero_ratio_error,
        },
        "weightsLoaded": False,
        "workflowExampleExecuted": False,
    }


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit(
            "usage: sdxl_ip2p_upscale_synthetic_probe.py <pinned-comfyui-source>"
        )
    print(
        json.dumps(
            run_probe(Path(sys.argv[1]).resolve()),
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
