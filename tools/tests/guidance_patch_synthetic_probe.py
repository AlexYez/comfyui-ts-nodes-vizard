from __future__ import annotations

import ast
import json
import math
from pathlib import Path
from types import SimpleNamespace

import torch
import torch.nn.functional as F
from einops import rearrange, repeat
from torch import einsum


ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / ".comfyui-source-0.32.0" / "comfy_extras"
PAG_SOURCE = SOURCE / "nodes_pag.py"
SAG_SOURCE = SOURCE / "nodes_sag.py"
NAG_SOURCE = SOURCE / "nodes_nag.py"
EPS_SOURCE = SOURCE / "nodes_eps.py"


class DummyNodeOutput:
    def __init__(self, *values: object) -> None:
        self.values = values


class DummyComfyNode:
    pass


class DummyModelType:
    Type = object

    @staticmethod
    def Input(name: str, **kwargs: object) -> tuple[str, str, dict[str, object]]:
        return ("input", name, kwargs)

    @staticmethod
    def Output(name: str | None = None, **kwargs: object) -> tuple[str, str | None, dict[str, object]]:
        return ("output", name, kwargs)


IO = SimpleNamespace(
    ComfyNode=DummyComfyNode,
    NodeOutput=DummyNodeOutput,
    Model=DummyModelType,
    Float=DummyModelType,
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


class DummyPostCfgModel:
    def __init__(self, marker: str = "original") -> None:
        self.marker = marker
        self.post_cfg: object | None = None
        self.disable_cfg1_optimization = False
        self.attn1_replace: object | None = None

    def clone(self) -> "DummyPostCfgModel":
        return DummyPostCfgModel("clone")

    def set_model_sampler_post_cfg_function(
        self, function: object, disable_cfg1_optimization: bool = False
    ) -> None:
        self.post_cfg = function
        self.disable_cfg1_optimization = disable_cfg1_optimization

    def set_model_attn1_replace(
        self, function: object, block: str, block_id: int, transformer_index: int
    ) -> None:
        self.attn1_replace = (function, block, block_id, transformer_index)


class DummyNAGModel:
    def __init__(self, marker: str = "original") -> None:
        self.marker = marker
        self.attn1_output_patch: object | None = None
        self.cfg1_disabled = False

    def clone(self) -> "DummyNAGModel":
        return DummyNAGModel("clone")

    def set_model_attn1_output_patch(self, function: object) -> None:
        self.attn1_output_patch = function

    def disable_model_cfg1_optimization(self) -> None:
        self.cfg1_disabled = True


def run_pag_probe() -> dict[str, object]:
    calls: list[dict[str, object]] = []

    def set_patch(
        options: dict[str, object],
        patch: object,
        attention: str,
        block: str,
        block_id: int,
    ) -> dict[str, object]:
        copied = dict(options)
        copied["captured_patch"] = patch
        copied["patch_key"] = [attention, block, block_id]
        return copied

    def calc_cond_batch(
        model: object,
        conds: list[object],
        x: torch.Tensor,
        sigma: torch.Tensor,
        options: dict[str, object],
    ) -> tuple[torch.Tensor]:
        calls.append({"model": model, "conds": conds, "options": options, "sigma": sigma})
        return (torch.full_like(x, 1.25),)

    comfy = SimpleNamespace(
        model_patcher=SimpleNamespace(set_model_options_patch_replace=set_patch),
        samplers=SimpleNamespace(calc_cond_batch=calc_cond_batch),
    )
    definitions = extract(
        PAG_SOURCE,
        classes={"PerturbedAttentionGuidance"},
        namespace={"io": IO, "comfy": comfy},
    )
    model = DummyPostCfgModel()
    patched = definitions["PerturbedAttentionGuidance"].execute(model, 3.0).values[0]
    assert patched is not model and patched.post_cfg is not None
    x = torch.full((1, 1, 2, 2), 4.0)
    cfg = torch.full_like(x, 2.0)
    cond_pred = torch.full_like(x, 3.0)
    result = patched.post_cfg(
        {
            "model": object(),
            "cond_denoised": cond_pred,
            "cond": {"marker": "positive"},
            "denoised": cfg,
            "sigma": torch.tensor([0.5]),
            "model_options": {"kept": "yes"},
            "input": x,
        }
    )
    expected = cfg + (cond_pred - 1.25) * 3.0
    assert torch.equal(result, expected)
    assert len(calls) == 1
    options = calls[0]["options"]
    assert options["kept"] == "yes" and options["patch_key"] == ["attn1", "middle", 0]
    q = torch.randn(1, 3, 2)
    k = torch.randn_like(q)
    v = torch.randn_like(q)
    assert options["captured_patch"](q, k, v, {}) is v

    zero_patched = definitions["PerturbedAttentionGuidance"].execute(model, 0.0).values[0]
    zero = zero_patched.post_cfg(
        {
            "model": object(),
            "cond_denoised": cond_pred,
            "cond": {},
            "denoised": cfg,
            "sigma": torch.tensor([0.5]),
            "model_options": {},
            "input": x,
        }
    )
    assert zero is cfg and len(calls) == 1
    return {
        "result": result.tolist(),
        "expected": expected.tolist(),
        "extraConditionalCalls": len(calls),
        "patchKey": options["patch_key"],
        "returnsProjectedVByIdentity": options["captured_patch"](q, k, v, {}) is v,
        "scaleZeroBypassesExtraCall": zero is cfg and len(calls) == 1,
    }


def run_sag_probe() -> dict[str, object]:
    calls: list[dict[str, object]] = []

    def calc_cond_batch(
        model: object,
        conds: list[object],
        x: torch.Tensor,
        sigma: torch.Tensor,
        options: dict[str, object],
    ) -> tuple[torch.Tensor]:
        calls.append({"model": model, "conds": conds, "x": x.clone(), "options": options})
        return (torch.full_like(x, 0.25),)

    comfy = SimpleNamespace(samplers=SimpleNamespace(calc_cond_batch=calc_cond_batch))
    definitions = extract(
        SAG_SOURCE,
        functions={"attention_basic_with_sim", "create_blur_map", "gaussian_blur_2d"},
        classes={"SelfAttentionGuidance"},
        namespace={
            "torch": torch,
            "einsum": einsum,
            "F": F,
            "math": math,
            "rearrange": rearrange,
            "repeat": repeat,
            "optimized_attention": lambda q, k, v, heads, attn_precision=None: v,
            "comfy": comfy,
            "io": IO,
        },
    )
    blur = definitions["gaussian_blur_2d"]
    image = torch.arange(64, dtype=torch.float32).reshape(1, 1, 8, 8)
    finite_blur = blur(image, 9, 2.0)
    zero_blur = blur(image, 9, 0.0)
    assert torch.isfinite(finite_blur).all()
    assert not torch.isfinite(zero_blur).all()

    attention = torch.zeros(1, 4, 4)
    attention[:, :, 0] = 1.0
    degraded = definitions["create_blur_map"](image, attention, 2.0, 1.0)
    assert not torch.equal(degraded, image)
    assert torch.equal(degraded[:, :, 4:, 4:], image[:, :, 4:, 4:])

    model = DummyPostCfgModel()
    patched = definitions["SelfAttentionGuidance"].execute(model, 0.0, 2.0).values[0]
    assert patched is not model and patched.post_cfg is not None
    assert patched.disable_cfg1_optimization
    attn_function, block, block_id, transformer_index = patched.attn1_replace
    q = torch.zeros(2, 4, 2)
    k = torch.zeros_like(q)
    v = torch.arange(16, dtype=torch.float32).reshape(2, 4, 2)
    attn_function(
        q,
        k,
        v,
        {"n_heads": 1, "cond_or_uncond": [1, 0], "attn_precision": torch.float32},
    )
    cfg = torch.full((1, 1, 8, 8), 2.0)
    uncond_pred = torch.full_like(cfg, 1.0)
    result = patched.post_cfg(
        {
            "model": object(),
            "uncond_denoised": uncond_pred,
            "uncond": {"marker": "negative"},
            "denoised": cfg,
            "sigma": torch.tensor([0.5]),
            "model_options": {"kept": "yes"},
            "input": torch.full_like(cfg, 3.0),
        }
    )
    assert torch.equal(result, cfg)
    assert len(calls) == 1

    small = torch.ones(1, 1, 4, 8)
    skipped = patched.post_cfg(
        {
            "model": object(),
            "uncond_denoised": small,
            "uncond": {},
            "denoised": small,
            "sigma": torch.tensor([0.5]),
            "model_options": {},
            "input": small,
        }
    )
    assert skipped is small and len(calls) == 1
    return {
        "patchKey": [block, block_id, transformer_index],
        "cfg1OptimizationDisabled": patched.disable_cfg1_optimization,
        "scaleZeroStillRunsExtraUnconditionalCall": len(calls) == 1,
        "smallSpatialDimensionSkips": skipped is small,
        "sigmaTwoFinite": bool(torch.isfinite(finite_blur).all()),
        "sigmaZeroFinite": bool(torch.isfinite(zero_blur).all()),
        "attentionMaskChangesSelectedRegion": not torch.equal(degraded, image),
        "unselectedCornerPreserved": torch.equal(degraded[:, :, 4:, 4:], image[:, :, 4:, 4:]),
    }


def run_nag_probe() -> dict[str, object]:
    definitions = extract(
        NAG_SOURCE,
        classes={"NAGuidance"},
        namespace={"torch": torch, "io": IO},
    )
    model = DummyNAGModel()
    patched = definitions["NAGuidance"].execute(model, 5.0, 1.0, 1.5).values[0]
    assert patched is not model and patched.attn1_output_patch is not None and patched.cfg1_disabled
    patch = patched.attn1_output_patch
    source = torch.tensor(
        [
            [[1.0, -1.0], [2.0, 0.0]],
            [[2.0, 2.0], [1.0, 3.0]],
        ]
    )
    result = patch(source.clone(), {"cond_or_uncond": [1, 0]})
    assert torch.equal(result[0], source[0])
    pos = source[1:2]
    neg = source[0:1]
    guided = pos * 5.0 - neg * 4.0
    norm_pos = torch.norm(pos, p=1, dim=-1, keepdim=True).clamp_min(1e-6)
    norm_guided = torch.norm(guided, p=1, dim=-1, keepdim=True).clamp_min(1e-6)
    ratio = norm_guided / norm_pos
    expected = guided * (torch.minimum(ratio, torch.full_like(ratio, 1.5)) / ratio)
    assert torch.allclose(result[1:2], expected)
    assert bool((ratio > 1.5).any())

    alpha_zero_model = definitions["NAGuidance"].execute(model, 5.0, 0.0, 1.5).values[0]
    alpha_zero = alpha_zero_model.attn1_output_patch(source.clone(), {"cond_or_uncond": [1, 0]})
    assert torch.equal(alpha_zero, source)

    image_tokens = torch.tensor(
        [
            [[9.0, 9.0], [1.0, -1.0], [2.0, 0.0]],
            [[8.0, 8.0], [2.0, 2.0], [1.0, 3.0]],
        ]
    )
    sliced = alpha_zero_model.attn1_output_patch(
        image_tokens.clone(), {"cond_or_uncond": [1, 0], "img_slice": (1, 3)}
    )
    assert torch.equal(sliced[:, 0], image_tokens[:, 0])
    assert torch.equal(sliced[0, 1:3], image_tokens[1, 1:3])
    assert torch.equal(sliced[1, 1:3], image_tokens[1, 1:3])
    return {
        "cfg1OptimizationDisabled": patched.cfg1_disabled,
        "negativeBranchPreservedWithoutImageSlice": torch.equal(result[0], source[0]),
        "ratioWasCapped": bool((ratio > 1.5).any()),
        "normalizedPositive": result[1].tolist(),
        "alphaZeroNoSliceIsIdentity": torch.equal(alpha_zero, source),
        "alphaZeroImageSliceCopiesPositiveIntoNegative": torch.equal(
            sliced[0, 1:3], image_tokens[1, 1:3]
        ),
        "nonImageTokensPreserved": torch.equal(sliced[:, 0], image_tokens[:, 0]),
    }


def run_epsilon_probe() -> dict[str, object]:
    definitions = extract(
        EPS_SOURCE,
        classes={"EpsilonScaling"},
        namespace={"torch": torch, "io": IO},
    )
    model = DummyPostCfgModel()
    x = torch.tensor([[[[4.0, -2.0]]]])
    denoised = torch.tensor([[[[1.0, 2.0]]]])

    results: dict[str, object] = {}
    for factor in (1.0, 1.25, 0.5, 0.0):
        patched = definitions["EpsilonScaling"].execute(model, factor).values[0]
        assert patched is not model and patched.post_cfg is not None
        value = patched.post_cfg({"input": x, "denoised": denoised})
        effective = 1e-9 if factor == 0 else factor
        expected = x - (x - denoised) / effective
        assert torch.allclose(value, expected)
        results[str(factor)] = value.tolist()
    return {
        "factorOneIsIdentity": results["1.0"] == denoised.tolist(),
        "factorAboveOne": results["1.25"],
        "factorBelowOne": results["0.5"],
        "directZeroGuardFinite": bool(torch.isfinite(torch.tensor(results["0.0"])).all()),
        "allStepsUniformFormulaHasNoSigmaInput": True,
    }


def run() -> dict[str, object]:
    return {
        "perturbedAttentionGuidance": run_pag_probe(),
        "selfAttentionGuidance": run_sag_probe(),
        "normalizedAttentionGuidance": run_nag_probe(),
        "epsilonScaling": run_epsilon_probe(),
    }


if __name__ == "__main__":
    print(json.dumps(run(), ensure_ascii=False, sort_keys=True))
