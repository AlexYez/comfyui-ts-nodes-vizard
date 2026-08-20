from __future__ import annotations

import ast
import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import torch


ROOT = Path(__file__).resolve().parents[2]
NODE_SOURCE = ROOT / ".comfyui-source-0.32.0" / "comfy_extras" / "nodes_stable_cascade.py"
UTILS_SOURCE = ROOT / ".comfyui-source-0.32.0" / "comfy" / "utils.py"


class DummyNodeOutput:
    def __init__(self, *values: object) -> None:
        self.values = values


class DummyComfyNode:
    pass


def extract_common_upscale() -> Any:
    tree = ast.parse(UTILS_SOURCE.read_text(encoding="utf-8"))
    selected = [
        node
        for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and node.name == "common_upscale"
    ]
    if len(selected) != 1:
        raise AssertionError("exact common_upscale definition was not found")
    namespace: dict[str, object] = {
        "torch": torch,
        "bislerp": lambda *_args, **_kwargs: None,
        "lanczos": lambda *_args, **_kwargs: None,
    }
    exec(compile(ast.Module(body=selected, type_ignores=[]), str(UTILS_SOURCE), "exec"), namespace)
    return namespace["common_upscale"]


def extract_classes(common_upscale: Any) -> dict[str, type]:
    tree = ast.parse(NODE_SOURCE.read_text(encoding="utf-8"))
    wanted = {
        "StableCascade_EmptyLatentImage",
        "StableCascade_StageB_Conditioning",
        "StableCascade_StageC_VAEEncode",
        "StableCascade_SuperResolutionControlnet",
    }
    selected = [
        node
        for node in tree.body
        if isinstance(node, ast.ClassDef) and node.name in wanted
    ]
    found = {node.name for node in selected}
    if found != wanted:
        raise AssertionError(f"missing exact classes: {sorted(wanted - found)}")

    io = SimpleNamespace(ComfyNode=DummyComfyNode, NodeOutput=DummyNodeOutput)
    namespace: dict[str, object] = {
        "io": io,
        "torch": torch,
        "comfy": SimpleNamespace(utils=SimpleNamespace(common_upscale=common_upscale)),
    }
    exec(compile(ast.Module(body=selected, type_ignores=[]), str(NODE_SOURCE), "exec"), namespace)
    return {name: namespace[name] for name in wanted}  # type: ignore[return-value]


class FakeCascadeVAE:
    downscale_ratio = 32

    def __init__(self) -> None:
        self.inputs: list[torch.Tensor] = []

    def encode(self, image: torch.Tensor) -> torch.Tensor:
        self.inputs.append(image.clone())
        nchw = image.movedim(-1, 1)
        pooled = torch.nn.functional.avg_pool2d(nchw, kernel_size=32, stride=32)
        repeats = (16 + pooled.shape[1] - 1) // pooled.shape[1]
        return pooled.repeat(1, repeats, 1, 1)[:, :16]


def unpack_latent(output: DummyNodeOutput, index: int) -> dict[str, Any]:
    payload = output.values[index]
    if not isinstance(payload, dict):
        raise AssertionError(payload)
    return payload


def probe_empty(classes: dict[str, type]) -> dict[str, object]:
    output = classes["StableCascade_EmptyLatentImage"].execute(1000, 770, 42, 2)
    stage_c = unpack_latent(output, 0)["samples"]
    stage_b = unpack_latent(output, 1)["samples"]
    return {
        "stageCShape": list(stage_c.shape),
        "stageBShape": list(stage_b.shape),
        "stageCDtype": str(stage_c.dtype),
        "stageCDevice": str(stage_c.device),
        "bothZero": bool(torch.count_nonzero(stage_c) == 0 and torch.count_nonzero(stage_b) == 0),
        "onlySamplesKeys": [sorted(unpack_latent(output, i)) for i in (0, 1)],
    }


def probe_stage_b(classes: dict[str, type]) -> dict[str, object]:
    embedding_a = object()
    embedding_b = object()
    nested = {"shared": True}
    conditioning = [
        [embedding_a, {"pooled_output": "a", "nested": nested}],
        [embedding_b, {"pooled_output": "b", "nested": nested}],
    ]
    prior = torch.arange(2 * 16 * 3 * 4, dtype=torch.float32).reshape(2, 16, 3, 4)
    stage_c = {"samples": prior, "batch_index": [9, 10]}
    output = classes["StableCascade_StageB_Conditioning"].execute(conditioning, stage_c)
    result = output.values[0]
    missing_samples_raises = False
    try:
        classes["StableCascade_StageB_Conditioning"].execute(conditioning, {})
    except KeyError:
        missing_samples_raises = True
    return {
        "entryCount": len(result),
        "embeddingsPreserved": [result[0][0] is embedding_a, result[1][0] is embedding_b],
        "metadataCopied": [result[i][1] is not conditioning[i][1] for i in range(2)],
        "nestedMetadataIsShallow": [result[i][1]["nested"] is nested for i in range(2)],
        "sourceMetadataUnchanged": all("stable_cascade_prior" not in item[1] for item in conditioning),
        "priorIdentityPreserved": all(item[1]["stable_cascade_prior"] is prior for item in result),
        "nonSamplesStageCMetadataIgnored": "batch_index" not in result[0][1],
        "missingSamplesRaises": missing_samples_raises,
    }


def probe_stage_c(classes: dict[str, type], common_upscale: Any) -> dict[str, object]:
    image = torch.linspace(0, 1, 2 * 101 * 155 * 4, dtype=torch.float32).reshape(2, 101, 155, 4)
    vae = FakeCascadeVAE()
    output = classes["StableCascade_StageC_VAEEncode"].execute(image, vae, 32)
    stage_c = unpack_latent(output, 0)["samples"]
    stage_b = unpack_latent(output, 1)["samples"]
    expected = common_upscale(image.movedim(-1, 1), 128, 96, "bicubic", "center").movedim(1, -1)[..., :3]
    return {
        "vaeInputShape": list(vae.inputs[0].shape),
        "centerCropAndBicubicMatch": bool(torch.equal(vae.inputs[0], expected)),
        "alphaDropped": vae.inputs[0].shape[-1] == 3,
        "stageCShape": list(stage_c.shape),
        "stageBShape": list(stage_b.shape),
        "stageBZero": bool(torch.count_nonzero(stage_b) == 0),
        "onlySamplesKeys": [sorted(unpack_latent(output, i)) for i in (0, 1)],
    }


def probe_super_resolution(classes: dict[str, type]) -> dict[str, object]:
    image = torch.linspace(0, 1, 2 * 33 * 65 * 4, dtype=torch.float32).reshape(2, 33, 65, 4)
    vae = FakeCascadeVAE()
    output = classes["StableCascade_SuperResolutionControlnet"].execute(image, vae)
    controlnet_input = output.values[0]
    stage_c = unpack_latent(output, 1)["samples"]
    stage_b = unpack_latent(output, 2)["samples"]
    expected_control = vae.encode(image[..., :3]).movedim(1, -1)
    return {
        "vaeInputShape": list(vae.inputs[0].shape),
        "alphaDropped": vae.inputs[0].shape[-1] == 3,
        "controlShape": list(controlnet_input.shape),
        "controlMatchesEncodedNHWC": bool(torch.equal(controlnet_input, expected_control)),
        "stageCShape": list(stage_c.shape),
        "stageBShape": list(stage_b.shape),
        "latentsZero": bool(torch.count_nonzero(stage_c) == 0 and torch.count_nonzero(stage_b) == 0),
        "latentDtype": str(stage_c.dtype),
        "latentDevice": str(stage_c.device),
    }


def run() -> dict[str, object]:
    common_upscale = extract_common_upscale()
    classes = extract_classes(common_upscale)
    return {
        "empty": probe_empty(classes),
        "stageB": probe_stage_b(classes),
        "stageC": probe_stage_c(classes, common_upscale),
        "superResolution": probe_super_resolution(classes),
    }


if __name__ == "__main__":
    print(json.dumps(run(), ensure_ascii=False, sort_keys=True))
