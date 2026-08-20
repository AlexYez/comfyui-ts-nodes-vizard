from __future__ import annotations

import ast
import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import torch


ROOT = Path(__file__).resolve().parents[2]
NODE_SOURCE = ROOT / ".comfyui-source-0.32.0" / "comfy_extras" / "nodes_hunyuan3d.py"
MMDIT_SOURCE = ROOT / ".comfyui-source-0.32.0" / "comfy" / "ldm" / "modules" / "diffusionmodules" / "mmdit.py"
VAE_SOURCE = ROOT / ".comfyui-source-0.32.0" / "comfy" / "ldm" / "hunyuan3d" / "vae.py"


class DummyNodeOutput:
    def __init__(self, *values: object) -> None:
        self.values = values


class DummyComfyNode:
    pass


class DummyVoxel:
    def __init__(self, data: torch.Tensor) -> None:
        self.data = data


def extract_named_function(path: Path, name: str, namespace: dict[str, object]) -> Any:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    selected = [
        node
        for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name
    ]
    if len(selected) != 1:
        raise AssertionError(f"exact function {name} was not found in {path}")
    exec(compile(ast.Module(body=selected, type_ignores=[]), str(path), "exec"), namespace)
    return namespace[name]


def extract_volume_decoder() -> type:
    tree = ast.parse(VAE_SOURCE.read_text(encoding="utf-8"))
    selected = [node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == "VanillaVolumeDecoder"]
    if len(selected) != 1:
        raise AssertionError("exact VanillaVolumeDecoder class was not found")
    namespace: dict[str, object] = {
        "torch": torch,
        "tqdm": lambda iterable, **_kwargs: iterable,
    }
    exec(compile(ast.Module(body=selected, type_ignores=[]), str(VAE_SOURCE), "exec"), namespace)
    return namespace["VanillaVolumeDecoder"]  # type: ignore[return-value]


def extract_node_classes() -> dict[str, type]:
    positional = extract_named_function(
        MMDIT_SOURCE,
        "get_1d_sincos_pos_embed_from_grid_torch",
        {"torch": torch},
    )
    tree = ast.parse(NODE_SOURCE.read_text(encoding="utf-8"))
    wanted = {
        "EmptyLatentHunyuan3Dv2",
        "Hunyuan3Dv2Conditioning",
        "Hunyuan3Dv2ConditioningMultiView",
        "VAEDecodeHunyuan3D",
    }
    selected = [node for node in tree.body if isinstance(node, ast.ClassDef) and node.name in wanted]
    found = {node.name for node in selected}
    if found != wanted:
        raise AssertionError(f"missing exact classes: {sorted(wanted - found)}")

    io = SimpleNamespace(ComfyNode=DummyComfyNode, NodeOutput=DummyNodeOutput)
    namespace: dict[str, object] = {
        "torch": torch,
        "IO": io,
        "Types": SimpleNamespace(VOXEL=DummyVoxel),
        "comfy": SimpleNamespace(
            model_management=SimpleNamespace(intermediate_device=lambda: torch.device("cpu"))
        ),
        "get_1d_sincos_pos_embed_from_grid_torch": positional,
    }
    exec(compile(ast.Module(body=selected, type_ignores=[]), str(NODE_SOURCE), "exec"), namespace)
    return {name: namespace[name] for name in wanted}  # type: ignore[return-value]


def probe_empty(classes: dict[str, type]) -> dict[str, object]:
    result = classes["EmptyLatentHunyuan3Dv2"].execute(7, 2).values[0]
    samples = result["samples"]
    return {
        "shape": list(samples.shape),
        "dtype": str(samples.dtype),
        "device": str(samples.device),
        "allZero": bool(torch.count_nonzero(samples) == 0),
        "keys": sorted(result),
        "typeMarker": result["type"],
        "bytesAtDefault": 1 * 64 * 3072 * 4,
        "bytesAtSchemaMaximum": 4096 * 64 * 8192 * 4,
    }


def probe_single_view(classes: dict[str, type]) -> dict[str, object]:
    hidden = torch.arange(2 * 3 * 8, dtype=torch.float32).reshape(2, 3, 8)
    ignored = torch.full((2, 8), 999.0)
    source = SimpleNamespace(last_hidden_state=hidden, image_embeds=ignored)
    positive, negative = classes["Hunyuan3Dv2Conditioning"].execute(source).values
    return {
        "positiveIsOriginal": positive[0][0] is hidden,
        "positiveMetadata": positive[0][1],
        "negativeShape": list(negative[0][0].shape),
        "negativeAllZero": bool(torch.count_nonzero(negative[0][0]) == 0),
        "negativeDtype": str(negative[0][0].dtype),
        "ignoredImageEmbeds": bool(torch.count_nonzero(positive[0][0] == 999.0) == 0),
    }


def probe_multi_view(classes: dict[str, type]) -> dict[str, object]:
    front_tensor = torch.zeros((1, 2, 8), dtype=torch.float16)
    back_tensor = torch.ones((1, 3, 8), dtype=torch.float16)
    front = SimpleNamespace(last_hidden_state=front_tensor)
    back = SimpleNamespace(last_hidden_state=back_tensor)
    positive, negative = classes["Hunyuan3Dv2ConditioningMultiView"].execute(front=front, back=back).values
    result = positive[0][0]

    positional = extract_named_function(
        MMDIT_SOURCE,
        "get_1d_sincos_pos_embed_from_grid_torch",
        {"torch": torch},
    )(8, torch.arange(4))
    expected = torch.cat(
        [
            front_tensor + positional[0].reshape(1, 1, -1),
            back_tensor + positional[2].reshape(1, 1, -1),
        ],
        dim=1,
    )

    empty_raises = False
    try:
        classes["Hunyuan3Dv2ConditioningMultiView"].execute()
    except (RuntimeError, ValueError):
        empty_raises = True

    odd_width_raises = False
    try:
        classes["Hunyuan3Dv2ConditioningMultiView"].execute(
            front=SimpleNamespace(last_hidden_state=torch.zeros((1, 1, 7)))
        )
    except (RuntimeError, ValueError):
        odd_width_raises = True

    mismatched_batch_raises = False
    try:
        classes["Hunyuan3Dv2ConditioningMultiView"].execute(
            front=front,
            left=SimpleNamespace(last_hidden_state=torch.zeros((2, 1, 8))),
        )
    except (RuntimeError, ValueError):
        mismatched_batch_raises = True

    return {
        "shape": list(result.shape),
        "dtype": str(result.dtype),
        "frontThenBackExact": bool(torch.equal(result, expected)),
        "frontPositionIndex": 0,
        "backPositionIndex": 2,
        "negativeAllZero": bool(torch.count_nonzero(negative[0][0]) == 0),
        "emptyRaises": empty_raises,
        "oddWidthRaises": odd_width_raises,
        "mismatchedBatchRaises": mismatched_batch_raises,
    }


class FakeVAE:
    def __init__(self) -> None:
        self.samples: torch.Tensor | None = None
        self.options: dict[str, int] | None = None
        self.result = torch.arange(2 * 3 * 4 * 5, dtype=torch.float32).reshape(2, 3, 4, 5)

    def decode(self, samples: torch.Tensor, vae_options: dict[str, int]) -> torch.Tensor:
        self.samples = samples
        self.options = dict(vae_options)
        return self.result


def probe_decode_wrapper(classes: dict[str, type]) -> dict[str, object]:
    latent = torch.randn((2, 64, 9), generator=torch.Generator().manual_seed(17))
    samples = {"samples": latent, "type": "hunyuan3dv2", "batch_index": [4, 5]}
    vae = FakeVAE()
    voxel = classes["VAEDecodeHunyuan3D"].execute(vae, samples, 1234, 48).values[0]
    missing_samples_raises = False
    try:
        classes["VAEDecodeHunyuan3D"].execute(vae, {}, 1234, 48)
    except KeyError:
        missing_samples_raises = True
    return {
        "samplesIdentity": vae.samples is latent,
        "options": vae.options,
        "voxelType": type(voxel).__name__,
        "voxelDataIdentity": voxel.data is vae.result,
        "voxelShape": list(voxel.data.shape),
        "nonSamplesMetadataIgnored": "batch_index" not in (vae.options or {}),
        "missingSamplesRaises": missing_samples_raises,
    }


def probe_volume_decoder() -> dict[str, object]:
    decoder = extract_volume_decoder()()
    calls: list[torch.Tensor] = []

    def geo_decoder(*, queries: torch.Tensor, latents: torch.Tensor) -> torch.Tensor:
        calls.append(queries.clone())
        if queries.shape[0] != latents.shape[0]:
            raise AssertionError("query batch was not repeated to latent batch")
        return queries.sum(dim=-1)

    latents = torch.zeros((2, 64, 5), dtype=torch.float32)
    result = decoder(
        latents,
        geo_decoder,
        octree_resolution=2,
        num_chunks=4,
        enable_pbar=False,
    )
    flattened = torch.cat(calls, dim=1)
    return {
        "shape": list(result.shape),
        "callCount": len(calls),
        "chunkSizes": [call.shape[1] for call in calls],
        "queryCount": flattened.shape[1],
        "queryBatch": flattened.shape[0],
        "boundsMinimum": float(flattened.min()),
        "boundsMaximum": float(flattened.max()),
        "defaultResolutionQueryCount": (256 + 1) ** 3,
        "defaultChunkIterations": ((256 + 1) ** 3 + 8000 - 1) // 8000,
        "maximumResolutionQueryCount": (512 + 1) ** 3,
    }


def run() -> dict[str, object]:
    classes = extract_node_classes()
    return {
        "empty": probe_empty(classes),
        "singleView": probe_single_view(classes),
        "multiView": probe_multi_view(classes),
        "decodeWrapper": probe_decode_wrapper(classes),
        "volumeDecoder": probe_volume_decoder(),
    }


if __name__ == "__main__":
    print(json.dumps(run(), ensure_ascii=False, sort_keys=True))
