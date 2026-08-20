from __future__ import annotations

import ast
import json
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import torch


class DummyNodeOutput:
    def __init__(self, *values: object) -> None:
        self.values = values


class DummyComfyNode:
    pass


def extract_nodes(source_root: Path) -> tuple[dict[str, type], str]:
    path = source_root / "comfy_extras" / "nodes_hunyuan.py"
    tree = ast.parse(path.read_text(encoding="utf-8"))
    wanted = {
        "CLIPTextEncodeHunyuanDiT",
        "TextEncodeHunyuanVideo_ImageToVideo",
        "EmptyHunyuanLatentVideo",
        "EmptyHunyuanVideo15Latent",
    }
    selected: list[ast.stmt] = []
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(
            isinstance(target, ast.Name) and target.id == "PROMPT_TEMPLATE_ENCODE_VIDEO_I2V"
            for target in node.targets
        ):
            selected.append(node)
        elif isinstance(node, ast.ClassDef) and node.name in wanted:
            selected.append(node)

    found = {node.name for node in selected if isinstance(node, ast.ClassDef)}
    if found != wanted:
        raise AssertionError(f"missing exact classes: {sorted(wanted - found)}")

    namespace: dict[str, Any] = {
        "torch": torch,
        "io": SimpleNamespace(ComfyNode=DummyComfyNode, NodeOutput=DummyNodeOutput),
        "comfy": SimpleNamespace(
            model_management=SimpleNamespace(intermediate_device=lambda: torch.device("cpu"))
        ),
    }
    exec(compile(ast.Module(body=selected, type_ignores=[]), str(path), "exec"), namespace)
    classes = {name: namespace[name] for name in wanted}
    return classes, namespace["PROMPT_TEMPLATE_ENCODE_VIDEO_I2V"]


class FakeDualClip:
    def __init__(self) -> None:
        self.tokenize_calls: list[str] = []
        self.encoded: dict[str, str] | None = None

    def tokenize(self, text: str) -> dict[str, str]:
        self.tokenize_calls.append(text)
        return {
            "hydit_clip": f"hydit:{text}",
            "mt5xl": f"mt5xl:{text}",
        }

    def encode_from_tokens_scheduled(self, tokens: dict[str, str]) -> dict[str, str]:
        self.encoded = dict(tokens)
        return self.encoded


class FakeVideoClip:
    def __init__(self) -> None:
        self.call: dict[str, object] | None = None
        self.tokens = {"llama": "tokens"}

    def tokenize(self, prompt: str, **kwargs: object) -> dict[str, str]:
        self.call = {"prompt": prompt, **kwargs}
        return self.tokens

    def encode_from_tokens_scheduled(self, tokens: dict[str, str]) -> dict[str, object]:
        return {"encodedTokensIdentity": tokens is self.tokens}


def probe_hydit(classes: dict[str, type]) -> dict[str, object]:
    clip = FakeDualClip()
    output = classes["CLIPTextEncodeHunyuanDiT"].execute(
        clip,
        "BERT description",
        "mT5 description",
    ).values[0]
    expected = {
        "hydit_clip": "hydit:BERT description",
        "mt5xl": "mt5xl:mT5 description",
    }
    assert clip.tokenize_calls == ["BERT description", "mT5 description"]
    assert clip.encoded == expected
    assert output == expected
    return {
        "tokenizeCalls": clip.tokenize_calls,
        "hyditStream": output["hydit_clip"],
        "mt5xlStream": output["mt5xl"],
    }


def probe_video_text(
    classes: dict[str, type], prompt_template: str
) -> dict[str, object]:
    clip = FakeVideoClip()
    projected = torch.arange(24, dtype=torch.float32).reshape(1, 3, 8)
    clip_vision_output = SimpleNamespace(mm_projected=projected)
    output = classes["TextEncodeHunyuanVideo_ImageToVideo"].execute(
        clip,
        clip_vision_output,
        "A fox turns toward the camera",
        3,
    ).values[0]
    assert clip.call is not None
    assert clip.call["prompt"] == "A fox turns toward the camera"
    assert clip.call["llama_template"] == prompt_template
    assert clip.call["image_embeds"] is projected
    assert clip.call["image_interleave"] == 3
    assert output["encodedTokensIdentity"] is True

    sequence = torch.arange(7)
    retained = {stride: sequence[::stride].tolist() for stride in (1, 2, 3, 512)}
    assert retained == {
        1: [0, 1, 2, 3, 4, 5, 6],
        2: [0, 2, 4, 6],
        3: [0, 3, 6],
        512: [0],
    }
    return {
        "templateHasImagePlaceholder": "<image>" in prompt_template,
        "projectedIdentityForwarded": clip.call["image_embeds"] is projected,
        "imageInterleave": clip.call["image_interleave"],
        "retainedImageTokenIndices": retained,
    }


def latent_record(value: dict[str, object]) -> dict[str, object]:
    samples = value["samples"]
    assert isinstance(samples, torch.Tensor)
    return {
        "shape": list(samples.shape),
        "dtype": str(samples.dtype),
        "device": str(samples.device),
        "allZero": bool(torch.count_nonzero(samples) == 0),
        "keys": sorted(value),
        "downscaleRatioSpacial": value["downscale_ratio_spacial"],
        "bytes": samples.numel() * samples.element_size(),
    }


def probe_latents(classes: dict[str, type]) -> dict[str, object]:
    old = classes["EmptyHunyuanLatentVideo"]
    video15 = classes["EmptyHunyuanVideo15Latent"]

    old_default = latent_record(old.execute(848, 480, 25, 1).values[0])
    video15_default = latent_record(video15.execute(848, 480, 25, 1).values[0])
    assert old_default["shape"] == [1, 16, 7, 60, 106]
    assert video15_default["shape"] == [1, 32, 7, 30, 53]
    assert old_default["downscaleRatioSpacial"] == 8
    assert video15_default["downscaleRatioSpacial"] == 16
    assert old_default["keys"] == ["downscale_ratio_spacial", "samples"]
    assert video15_default["keys"] == ["downscale_ratio_spacial", "samples"]

    temporal_shapes: dict[int, list[int]] = {}
    for length in (1, 2, 4, 5, 8, 9):
        value = old.execute(32, 32, length, 1).values[0]
        shape = list(value["samples"].shape)
        temporal_shapes[length] = shape
        assert shape[2] == ((length - 1) // 4) + 1
    assert {length: shape[2] for length, shape in temporal_shapes.items()} == {
        1: 1,
        2: 1,
        4: 1,
        5: 2,
        8: 2,
        9: 3,
    }

    direct_old = latent_record(old.execute(31, 47, 5, 2).values[0])
    direct_video15 = latent_record(video15.execute(31, 47, 5, 2).values[0])
    assert direct_old["shape"] == [2, 16, 2, 5, 3]
    assert direct_video15["shape"] == [2, 32, 2, 2, 1]
    return {
        "hunyuanVideo10Default": old_default,
        "hunyuanVideo15Default": video15_default,
        "maximumFloat32Bytes": {
            "hunyuanVideo10": 4096 * 16 * (((16384 - 1) // 4) + 1) * (16384 // 8) * (16384 // 8) * 4,
            "hunyuanVideo15": 4096 * 32 * (((16384 - 1) // 4) + 1) * (16384 // 16) * (16384 // 16) * 4,
        },
        "directNonWidgetMultiple": {
            "hunyuanVideo10": direct_old,
            "hunyuanVideo15": direct_video15,
        },
        "temporalShapes": temporal_shapes,
    }


def run_probe(source_root: Path) -> dict[str, object]:
    classes, prompt_template = extract_nodes(source_root)
    return {
        "hydit": probe_hydit(classes),
        "videoImageToVideoText": probe_video_text(classes, prompt_template),
        "latents": probe_latents(classes),
    }


if __name__ == "__main__":
    root = Path(sys.argv[1] if len(sys.argv) > 1 else ".comfyui-source-0.32.0")
    print(json.dumps(run_probe(root), ensure_ascii=False, sort_keys=True))
