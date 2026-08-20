from __future__ import annotations

import ast
import json
import logging
import math
from pathlib import Path
from types import SimpleNamespace

import torch
from einops import rearrange
from torch import einsum, randint


ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / ".comfyui-source-0.32.0"
FREEU_SOURCE = SOURCE / "comfy_extras" / "nodes_freelunch.py"
FRESCA_SOURCE = SOURCE / "comfy_extras" / "nodes_fresca.py"
HYPERTILE_SOURCE = SOURCE / "comfy_extras" / "nodes_hypertile.py"
ATTENTION_SOURCE = SOURCE / "comfy" / "ldm" / "modules" / "attention.py"


class DummyNodeOutput:
    def __init__(self, *values: object) -> None:
        self.values = values


class DummyComfyNode:
    pass


class DummyType:
    @staticmethod
    def Input(name: str, **kwargs: object) -> tuple[str, str, dict[str, object]]:
        return ("input", name, kwargs)

    @staticmethod
    def Output(name: str | None = None, **kwargs: object) -> tuple[str, str | None, dict[str, object]]:
        return ("output", name, kwargs)


IO = SimpleNamespace(
    ComfyNode=DummyComfyNode,
    NodeOutput=DummyNodeOutput,
    Model=DummyType,
    Float=DummyType,
    Int=DummyType,
    Boolean=DummyType,
    Schema=dict,
)


def extract(
    path: Path,
    *,
    functions: set[str] = frozenset(),
    classes: set[str] = frozenset(),
    namespace: dict[str, object],
) -> dict[str, object]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    selected: list[ast.stmt] = []
    found_functions: set[str] = set()
    found_classes: set[str] = set()
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name in functions:
            selected.append(node)
            found_functions.add(node.name)
        elif isinstance(node, ast.ClassDef) and node.name in classes:
            selected.append(node)
            found_classes.add(node.name)
    if found_functions != functions or found_classes != classes:
        raise AssertionError(
            f"missing exact definitions in {path}: "
            f"functions={functions - found_functions}, classes={classes - found_classes}"
        )
    exec(compile(ast.Module(body=selected, type_ignores=[]), str(path), "exec"), namespace)
    return {name: namespace[name] for name in functions | classes}


class DummyPatchModel:
    def __init__(
        self,
        *,
        model_channels: int = 4,
        output_patches: list[object] | None = None,
        pre_cfg_patches: list[object] | None = None,
        attn1_patches: list[object] | None = None,
        attn1_output_patches: list[object] | None = None,
    ) -> None:
        self.model = SimpleNamespace(
            model_config=SimpleNamespace(unet_config={"model_channels": model_channels})
        )
        self.output_patches = list(output_patches or [])
        self.pre_cfg_patches = list(pre_cfg_patches or [])
        self.attn1_patches = list(attn1_patches or [])
        self.attn1_output_patches = list(attn1_output_patches or [])

    def clone(self) -> "DummyPatchModel":
        return DummyPatchModel(
            model_channels=self.model.model_config.unet_config["model_channels"],
            output_patches=self.output_patches,
            pre_cfg_patches=self.pre_cfg_patches,
            attn1_patches=self.attn1_patches,
            attn1_output_patches=self.attn1_output_patches,
        )

    def set_model_output_block_patch(self, patch: object) -> None:
        self.output_patches.append(patch)

    def set_model_sampler_pre_cfg_function(self, patch: object) -> None:
        self.pre_cfg_patches.append(patch)

    def set_model_attn1_patch(self, patch: object) -> None:
        self.attn1_patches.append(patch)

    def set_model_attn1_output_patch(self, patch: object) -> None:
        self.attn1_output_patches.append(patch)


def run_freeu_probe() -> dict[str, object]:
    definitions = extract(
        FREEU_SOURCE,
        functions={"Fourier_filter"},
        classes={"FreeU", "FreeU_V2"},
        namespace={"torch": torch, "logging": logging, "IO": IO},
    )
    fourier = definitions["Fourier_filter"]
    base = DummyPatchModel(model_channels=4)

    freeu = definitions["FreeU"].execute(base, 1.1, 1.2, 0.9, 0.2).values[0]
    assert len(freeu.output_patches) == 1
    patch = freeu.output_patches[0]
    h = torch.arange(2 * 16 * 4 * 4, dtype=torch.float32).reshape(2, 16, 4, 4)
    h_original = h.clone()
    hsp = torch.ones(2, 3, 4, 4, dtype=torch.float16)
    returned_h, returned_hsp = patch(h, hsp, {})
    assert returned_h is h
    assert torch.allclose(h[:, :8], h_original[:, :8] * 1.1)
    assert torch.equal(h[:, 8:], h_original[:, 8:])
    assert returned_hsp.dtype == hsp.dtype
    assert torch.allclose(returned_hsp.float(), torch.full_like(returned_hsp.float(), 0.9), atol=1e-3)

    unmatched_h = torch.randn(1, 12, 4, 4)
    unmatched_hsp = torch.randn(1, 3, 4, 4)
    unmatched_h_copy = unmatched_h.clone()
    unmatched_hsp_copy = unmatched_hsp.clone()
    unmatched_result = patch(unmatched_h, unmatched_hsp, {})
    assert torch.equal(unmatched_result[0], unmatched_h_copy)
    assert torch.equal(unmatched_result[1], unmatched_hsp_copy)

    v2 = definitions["FreeU_V2"].execute(base, 1.3, 1.4, 0.9, 0.2).values[0]
    v2_patch = v2.output_patches[0]
    v2_h = torch.arange(1 * 16 * 4 * 4, dtype=torch.float32).reshape(1, 16, 4, 4)
    v2_original = v2_h.clone()
    v2_hsp = torch.ones(1, 3, 4, 4)
    v2_result, _ = v2_patch(v2_h, v2_hsp, {})
    hidden_mean = v2_original.mean(1, keepdim=True)
    normalized = (hidden_mean - hidden_mean.amin((2, 3), keepdim=True)) / (
        hidden_mean.amax((2, 3), keepdim=True) - hidden_mean.amin((2, 3), keepdim=True)
    )
    expected_first = v2_original[:, :8] * ((1.3 - 1.0) * normalized + 1.0)
    assert torch.allclose(v2_result[:, :8], expected_first)
    assert torch.equal(v2_result[:, 8:], v2_original[:, 8:])

    constant_h = torch.ones(1, 16, 4, 4)
    constant_v2, _ = v2_patch(constant_h, torch.ones(1, 3, 4, 4), {})
    assert not torch.isfinite(constant_v2[:, :8]).all()

    video_failed = False
    try:
        patch(torch.ones(1, 16, 2, 4, 4), torch.ones(1, 3, 2, 4, 4), {})
    except ValueError:
        video_failed = True
    assert video_failed

    stacked = definitions["FreeU_V2"].execute(freeu, 1.3, 1.4, 0.9, 0.2).values[0]
    assert len(stacked.output_patches) == 2
    torch.manual_seed(91)
    stacking_input_h = torch.randn(1, 16, 4, 4)
    stacking_input_hsp = torch.randn(1, 3, 4, 4)
    first_order_h = stacking_input_h.clone()
    first_order_hsp = stacking_input_hsp.clone()
    for stacked_patch in stacked.output_patches:
        first_order_h, first_order_hsp = stacked_patch(first_order_h, first_order_hsp, {})
    reverse_h = stacking_input_h.clone()
    reverse_hsp = stacking_input_hsp.clone()
    for stacked_patch in reversed(stacked.output_patches):
        reverse_h, reverse_hsp = stacked_patch(reverse_h, reverse_hsp, {})
    assert not torch.allclose(first_order_h, reverse_h)

    identity_source = torch.randn(1, 2, 8, 8)
    identity_filtered = fourier(identity_source, threshold=1, scale=1.0)
    return {
        "freeuFirstHalfScaled": torch.allclose(h[:, :8], h_original[:, :8] * 1.1),
        "freeuSecondHalfPreserved": torch.equal(h[:, 8:], h_original[:, 8:]),
        "constantSkipScaledByS1": float(returned_hsp.flatten()[0]),
        "skipDtypePreserved": str(returned_hsp.dtype),
        "unmatchedChannelsBypass": torch.equal(unmatched_result[0], unmatched_h_copy),
        "v2SpatialGainMinMax": [
            float((((1.3 - 1.0) * normalized + 1.0).amin())),
            float((((1.3 - 1.0) * normalized + 1.0).amax())),
        ],
        "v2ConstantHiddenFinite": bool(torch.isfinite(constant_v2[:, :8]).all()),
        "fiveDimensionalSkipFails": video_failed,
        "stackedPatchCount": len(stacked.output_patches),
        "freeuThenV2DiffersFromReverse": not torch.allclose(first_order_h, reverse_h),
        "fourierIdentity": bool(torch.allclose(identity_filtered, identity_source, atol=1e-5)),
    }


def run_fresca_probe() -> dict[str, object]:
    definitions = extract(
        FRESCA_SOURCE,
        functions={"Fourier_filter"},
        classes={"FreSca"},
        namespace={"torch": torch, "fft": torch.fft, "io": IO},
    )
    fourier = definitions["Fourier_filter"]
    base = DummyPatchModel()
    patched = definitions["FreSca"].execute(base, 1.0, 1.25, 20).values[0]
    assert len(patched.pre_cfg_patches) == 1
    hook = patched.pre_cfg_patches[0]

    cond = torch.arange(2 * 3 * 8 * 8, dtype=torch.float32).reshape(2, 3, 8, 8) / 100
    uncond = torch.full_like(cond, 0.25)
    extra = torch.full_like(cond, -1.0)
    result = hook({"conds_out": [cond, uncond, extra], "conds": [object(), object(), object()]})
    assert len(result) == 3 and result[1] is uncond and result[2] is extra
    assert torch.allclose(result[0], cond, atol=1e-5)

    one = [cond]
    assert hook({"conds_out": one, "conds": [object()]}) is one
    missing = [cond, uncond]
    assert hook({"conds_out": missing, "conds": [object(), None]}) is missing

    identity_input = torch.randn(2, 3, 16, 16, dtype=torch.float16)
    identity = fourier(identity_input, scale_low=1.0, scale_high=1.0, freq_cutoff=3)
    assert identity.dtype == identity_input.dtype
    assert torch.allclose(identity.float(), identity_input.float(), atol=2e-3)

    video = torch.randn(2, 4, 3, 8, 10, dtype=torch.float16)
    video_result = fourier(video, scale_low=0.8, scale_high=1.2, freq_cutoff=2)
    assert video_result.shape == video.shape and video_result.dtype == video.dtype

    odd = torch.randn(1, 1, 5, 5)
    odd_result = fourier(odd, scale_low=1.0, scale_high=2.0, freq_cutoff=10000)
    assert not torch.allclose(odd_result, odd)

    stacked = definitions["FreSca"].execute(patched, 0.8, 1.1, 4).values[0]
    assert len(stacked.pre_cfg_patches) == 2
    stacked_outputs = [cond, uncond]
    for stacked_hook in stacked.pre_cfg_patches:
        stacked_outputs = stacked_hook(
            {"conds_out": stacked_outputs, "conds": [object(), object()]}
        )
    assert len(stacked_outputs) == 2

    return {
        "defaultCutoffSaturatesEightByEight": torch.allclose(result[0], cond, atol=1e-5),
        "extraConditionPreserved": result[2] is extra,
        "singleConditionBypassIdentity": hook({"conds_out": one, "conds": [object()]}) is one,
        "missingConditionBypassIdentity": hook({"conds_out": missing, "conds": [object(), None]}) is missing,
        "identityFilterDtype": str(identity.dtype),
        "identityFilterClose": bool(torch.allclose(identity.float(), identity_input.float(), atol=2e-3)),
        "fiveDimensionalShape": list(video_result.shape),
        "fiveDimensionalDtype": str(video_result.dtype),
        "oversizedCutoffOddShapeLeavesHighFrequencyRim": not torch.allclose(odd_result, odd),
        "stackedPreCfgPatchCount": len(stacked.pre_cfg_patches),
    }


def load_attention_basic() -> object:
    comfy = SimpleNamespace(ops=SimpleNamespace(repeat_kv_for_gqa=lambda *args, **kwargs: args[0]))
    functions = {
        "exists",
        "_heads_from_dim",
        "_reshape_qkv_to_heads",
        "get_attn_precision",
        "attention_basic",
    }
    definitions = extract(
        ATTENTION_SOURCE,
        functions=functions,
        namespace={
            "torch": torch,
            "einsum": einsum,
            "rearrange": rearrange,
            "repeat": lambda *args, **kwargs: None,
            "args": SimpleNamespace(dont_upcast_attention=True),
            "FORCE_UPCAST_ATTENTION_DTYPE": None,
            "comfy": comfy,
            "wrap_attn": lambda function: function,
        },
    )
    return definitions["attention_basic"]


def run_hypertile_probe() -> dict[str, object]:
    definitions = extract(
        HYPERTILE_SOURCE,
        functions={"random_divisor"},
        classes={"HyperTile"},
        namespace={
            "math": math,
            "rearrange": rearrange,
            "randint": randint,
            "io": IO,
        },
    )
    random_divisor = definitions["random_divisor"]
    base = DummyPatchModel()
    patched = definitions["HyperTile"].execute(base, 256, 2, 0, False)[0]
    assert len(patched.attn1_patches) == 1 and len(patched.attn1_output_patches) == 1
    patch_in = patched.attn1_patches[0]
    patch_out = patched.attn1_output_patches[0]

    q = torch.arange(2 * 4096 * 4, dtype=torch.float32).reshape(2, 4096, 4) / 1000
    k = q.clone()
    v = q.clone()
    torch.manual_seed(123)
    tiled_q, tiled_k, tiled_v = patch_in(
        q, k, v, {"original_shape": [2, 4, 64, 64]}
    )
    assert tiled_q.shape == (8, 1024, 4)
    assert tiled_k is k and tiled_v is v

    attention_basic = load_attention_basic()
    attended = attention_basic(tiled_q, tiled_k, tiled_v, heads=1)
    assert attended.shape == tiled_q.shape
    restored = patch_out(attended, {"original_shape": [2, 4, 64, 64]})
    assert restored.shape == q.shape

    choices: set[int] = set()
    for seed in range(64):
        torch.manual_seed(seed)
        choices.add(random_divisor(120, 4, 4))
    assert choices.issubset({30, 24, 20}) and 15 not in choices and len(choices) > 1

    default_choices: set[int] = set()
    for seed in range(16):
        torch.manual_seed(seed)
        default_choices.add(random_divisor(64, 32, 2))
    assert default_choices == {2}

    tile_floor = []
    for tile_size in (1, 39, 40):
        current = definitions["HyperTile"].execute(base, tile_size, 1, 0, False)[0]
        current_in = current.attn1_patches[0]
        current_q, _, _ = current_in(
            torch.zeros(1, 1024, 2),
            torch.zeros(1, 1024, 2),
            torch.zeros(1, 1024, 2),
            {"original_shape": [1, 4, 32, 32]},
        )
        tile_floor.append([tile_size, current_q.shape[0], current_q.shape[1]])
    assert tile_floor == [[1, 64, 16], [39, 64, 16], [40, 16, 64]]

    depth_no_scale = definitions["HyperTile"].execute(base, 64, 1, 1, False)[0]
    depth_scaled = definitions["HyperTile"].execute(base, 64, 1, 1, True)[0]
    depth_q = torch.zeros(1, 1024, 2)
    depth_options = {"original_shape": [1, 4, 64, 64]}
    depth_plain, _, _ = depth_no_scale.attn1_patches[0](depth_q, depth_q, depth_q, depth_options)
    depth_scale, _, _ = depth_scaled.attn1_patches[0](depth_q, depth_q, depth_q, depth_options)
    assert depth_plain.shape == (16, 64, 2)
    assert depth_scale.shape == (4, 256, 2)

    video_spatial = definitions["HyperTile"].execute(base, 256, 2, 0, False)[0]
    video_q = torch.zeros(3, 4096, 2)
    tiled_video, _, _ = video_spatial.attn1_patches[0](
        video_q, video_q, video_q, {"original_shape": [1, 4, 3, 64, 64]}
    )
    assert tiled_video.shape == (12, 1024, 2)
    video_joint = torch.zeros(1, 3 * 64 * 64, 2)
    skipped_video, _, _ = video_spatial.attn1_patches[0](
        video_joint,
        video_joint,
        video_joint,
        {"original_shape": [1, 4, 3, 64, 64]},
    )
    assert skipped_video is video_joint

    stacked = definitions["HyperTile"].execute(patched, 64, 1, 1, False)[0]
    assert len(stacked.attn1_patches) == 2 and len(stacked.attn1_output_patches) == 2

    return {
        "batchTwoInputShape": list(q.shape),
        "batchTwoTiledQueryShape": list(tiled_q.shape),
        "keysAndValuesAreReinterpretedByAttention": list(attended.shape),
        "restoredShape": list(restored.shape),
        "swapFourObservedTileCounts": sorted(choices),
        "lastCandidateExcluded": 15 not in choices,
        "defaultSwapTwoIsDeterministicForSixtyFour": sorted(default_choices),
        "tileSizeFloorCases": tile_floor,
        "depthWithoutScaleShape": list(depth_plain.shape),
        "depthWithScaleShape": list(depth_scale.shape),
        "videoPerFrameSpatialAttentionShape": list(tiled_video.shape),
        "jointSpatiotemporalAttentionSkipped": skipped_video is video_joint,
        "stackedInputPatchCount": len(stacked.attn1_patches),
        "stackedOutputPatchCount": len(stacked.attn1_output_patches),
        "hasRandomSpatialOffset": False,
    }


def run() -> dict[str, object]:
    return {
        "freeU": run_freeu_probe(),
        "freSca": run_fresca_probe(),
        "hyperTile": run_hypertile_probe(),
    }


if __name__ == "__main__":
    print(json.dumps(run(), ensure_ascii=False, sort_keys=True))
