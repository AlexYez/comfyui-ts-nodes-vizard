from __future__ import annotations

import ast
import json
import logging
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Callable

import torch


class _ComfyNode:
    pass


class _NodeOutput:
    def __init__(self, *args: Any) -> None:
        self.args = args


class _FakeModel:
    def __init__(self, in_channels: int = 2, origin: "_FakeModel | None" = None) -> None:
        self.origin = origin
        self.model = SimpleNamespace(diffusion_model=SimpleNamespace(in_channels=in_channels))
        self.cfg_function: Callable[[dict[str, Any]], torch.Tensor] | None = None
        self.compute_dtype: torch.dtype | None | str = "unset"
        self.attention_function: Callable[..., Any] | None = None

    def clone(self) -> "_FakeModel":
        return _FakeModel(self.model.diffusion_model.in_channels, origin=self)

    def set_model_sampler_cfg_function(self, function: Callable[[dict[str, Any]], torch.Tensor]) -> None:
        self.cfg_function = function

    def set_model_compute_dtype(self, dtype: torch.dtype | None) -> None:
        self.compute_dtype = dtype

    def set_model_optimized_attention(self, function: Callable[..., Any]) -> None:
        self.attention_function = function


def _extract_function(path: Path, name: str) -> Callable[..., Any]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    node = next(item for item in tree.body if isinstance(item, ast.FunctionDef) and item.name == name)
    namespace = {"torch": torch}
    exec(compile(ast.Module(body=[node], type_ignores=[]), str(path), "exec"), namespace)
    return namespace[name]


def _extract_legacy_nodes(
    source_root: Path,
    *,
    kitchen_available: bool,
    attention_registry: dict[str, Callable[..., Any]],
) -> dict[str, type]:
    path = source_root / "comfy_extras" / "nodes_model_advanced.py"
    tree = ast.parse(path.read_text(encoding="utf-8"))
    wanted = {"RescaleCFG", "ModelComputeDtype", "ModelAttentionBackend"}
    body = [node for node in tree.body if isinstance(node, ast.ClassDef) and node.name in wanted]

    def get_attention_function(name: str | None, default: Any = ...) -> Any:
        if name in attention_registry:
            return attention_registry[name]
        if default is ...:
            raise KeyError(name)
        return default

    dtype_mapper = _extract_function(source_root / "node_helpers.py", "string_to_torch_dtype")
    attention = SimpleNamespace(
        COMFY_KITCHEN_INT8_ATTENTION_IS_AVAILABLE=kitchen_available,
        get_attention_function=get_attention_function,
    )
    namespace: dict[str, Any] = {
        "torch": torch,
        "logging": logging,
        "node_helpers": SimpleNamespace(string_to_torch_dtype=dtype_mapper),
        "comfy": SimpleNamespace(
            ldm=SimpleNamespace(modules=SimpleNamespace(attention=attention))
        ),
    }
    exec(compile(ast.Module(body=body, type_ignores=[]), str(path), "exec"), namespace)
    return {name: namespace[name] for name in wanted}


def _extract_renorm(source_root: Path) -> type:
    path = source_root / "comfy_extras" / "nodes_lumina2.py"
    tree = ast.parse(path.read_text(encoding="utf-8"))
    class_node = next(node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == "RenormCFG")
    io = SimpleNamespace(ComfyNode=_ComfyNode, NodeOutput=_NodeOutput)
    namespace: dict[str, Any] = {"io": io, "torch": torch}
    exec(compile(ast.Module(body=[class_node], type_ignores=[]), str(path), "exec"), namespace)
    return namespace["RenormCFG"]


def run_probe(source_root: Path) -> dict[str, Any]:
    def pytorch_attention(*args: Any, **kwargs: Any) -> tuple[str, tuple[Any, ...], dict[str, Any]]:
        return "pytorch", args, kwargs

    def kitchen_attention(*args: Any, **kwargs: Any) -> tuple[str, tuple[Any, ...], dict[str, Any]]:
        return "kitchen", args, kwargs

    nodes = _extract_legacy_nodes(
        source_root,
        kitchen_available=True,
        attention_registry={"pytorch": pytorch_attention, "comfy_kitchen_int8": kitchen_attention},
    )
    original = _FakeModel()

    rescale_hooks: dict[float, Callable[[dict[str, Any]], torch.Tensor]] = {}
    for multiplier in (0.0, 0.3, 1.0):
        patched = nodes["RescaleCFG"]().patch(original, multiplier)[0]
        assert patched is not original and patched.origin is original
        assert patched.cfg_function is not None
        rescale_hooks[multiplier] = patched.cfg_function

    torch.manual_seed(7)
    args = {
        "cond": torch.randn(1, 2, 3, 4),
        "uncond": torch.randn(1, 2, 3, 4),
        "cond_scale": 5.0,
        "sigma": torch.tensor([2.0]),
        "input": torch.randn(1, 2, 3, 4),
    }
    rescale_zero = rescale_hooks[0.0](args)
    rescale_mid = rescale_hooks[0.3](args)
    rescale_one = rescale_hooks[1.0](args)
    torch.testing.assert_close(rescale_mid, rescale_zero * 0.7 + rescale_one * 0.3)
    assert not torch.equal(rescale_zero, rescale_one)
    sigma_zero_args = dict(args)
    sigma_zero_args["sigma"] = torch.tensor([0.0])
    assert not bool(torch.isfinite(rescale_hooks[0.0](sigma_zero_args)).all())
    constant_args = {
        "cond": torch.zeros(1, 2, 2, 2),
        "uncond": torch.zeros(1, 2, 2, 2),
        "cond_scale": 1.0,
        "sigma": torch.tensor([1.0]),
        "input": torch.zeros(1, 2, 2, 2),
    }
    assert not bool(torch.isfinite(rescale_hooks[0.0](constant_args)).all())

    dtype_results: dict[str, str] = {}
    for choice, expected in {
        "default": None,
        "fp32": torch.float32,
        "fp16": torch.float16,
        "bf16": torch.bfloat16,
    }.items():
        patched = nodes["ModelComputeDtype"]().patch(original, choice)[0]
        assert patched.compute_dtype is expected
        dtype_results[choice] = str(patched.compute_dtype)

    pytorch_patched = nodes["ModelAttentionBackend"]().patch(original, "pytorch attention")[0]
    kitchen_patched = nodes["ModelAttentionBackend"]().patch(original, "comfy kitchen attention")[0]
    unknown_patched = nodes["ModelAttentionBackend"]().patch(original, "unregistered backend")[0]
    assert pytorch_patched.attention_function is pytorch_attention
    assert kitchen_patched.attention_function is kitchen_attention
    assert unknown_patched.attention_function is pytorch_attention
    assert nodes["ModelAttentionBackend"].VALIDATE_INPUTS("anything") is True

    unavailable_nodes = _extract_legacy_nodes(
        source_root,
        kitchen_available=False,
        attention_registry={"pytorch": pytorch_attention},
    )
    options = unavailable_nodes["ModelAttentionBackend"].INPUT_TYPES()["required"]["attention"][0]
    assert options == ["pytorch attention"]
    fallback = unavailable_nodes["ModelAttentionBackend"]().patch(
        original, "comfy kitchen attention"
    )[0]
    assert fallback.attention_function is pytorch_attention

    renorm = _extract_renorm(source_root)
    patched_renorm = renorm.execute(original, 100.0, 0.0).args[0]
    assert patched_renorm.cfg_function is not None
    cond = torch.tensor(
        [[[[1.0, 2.0], [3.0, 4.0]], [[2.0, 1.0], [0.0, -1.0]], [[9.0, 8.0], [7.0, 6.0]], [[5.0, 4.0], [3.0, 2.0]]]]
    )
    uncond = torch.zeros_like(cond)
    x_orig = torch.full_like(cond, 10.0)
    renorm_args = {
        "cond_denoised": cond,
        "uncond_denoised": uncond,
        "cond_scale": 2.0,
        "timestep": torch.tensor([50.0]),
        "input": x_orig,
    }
    cfg_result = patched_renorm.cfg_function(renorm_args)
    expected_eps = 2.0 * cond[:, :2]
    expected_cfg = x_orig - torch.cat([expected_eps, cond[:, 2:]], dim=1)
    torch.testing.assert_close(cfg_result, expected_cfg)

    truncated = renorm.execute(original, 100.0, 1.0).args[0]
    trunc_args = dict(renorm_args)
    trunc_args["timestep"] = torch.tensor([100.0])
    torch.testing.assert_close(truncated.cfg_function(trunc_args), x_orig - cond)

    renormalized = renorm.execute(original, 100.0, 1.0).args[0]
    renorm_out = renormalized.cfg_function(renorm_args)
    renorm_eps = (x_orig - renorm_out)[:, :2]
    assert torch.linalg.vector_norm(renorm_eps) <= torch.linalg.vector_norm(cond[:, :2]) + 1e-6

    batch_args = {key: value.repeat(2, 1, 1, 1) if isinstance(value, torch.Tensor) and value.ndim == 4 else value for key, value in renorm_args.items()}
    try:
        renormalized.cfg_function(batch_args)
    except RuntimeError as error:
        batch_error = "ambiguous" in str(error).lower()
    else:
        raise AssertionError("RenormCFG batch>1 must expose the scalar-if ambiguity in v0.32.0")
    assert batch_error

    zero_args = dict(renorm_args)
    zero_args["cond_denoised"] = torch.zeros_like(cond)
    zero_args["uncond_denoised"] = torch.zeros_like(cond)
    assert not bool(torch.isfinite(renormalized.cfg_function(zero_args)).all())

    return {
        "rescaleCFG": {
            "affineMultiplier": True,
            "sigmaZeroFinite": bool(torch.isfinite(rescale_hooks[0.0](sigma_zero_args)).all()),
            "constantFinite": bool(torch.isfinite(rescale_hooks[0.0](constant_args)).all()),
        },
        "computeDtype": dtype_results,
        "attention": {
            "registered": ["pytorch", "comfy_kitchen_int8"],
            "unknownFallsBack": True,
            "unavailableOptions": options,
        },
        "renormCFG": {
            "cfgBranchVerified": True,
            "truncationBoundaryUsesConditional": True,
            "batchTwoRejected": batch_error,
            "zeroNormFinite": bool(torch.isfinite(renormalized.cfg_function(zero_args)).all()),
        },
    }


if __name__ == "__main__":
    root = Path(sys.argv[1] if len(sys.argv) > 1 else ".comfyui-source-0.32.0")
    print(json.dumps(run_probe(root), ensure_ascii=False, sort_keys=True))
