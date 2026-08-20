from __future__ import annotations

import ast
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import torch
import torch.nn.functional as F


class NodeOutput(tuple):
    def __new__(cls, *values):
        return tuple.__new__(cls, values)


class _Port:
    class Input:
        def __init__(self, *args, **kwargs):
            pass

    class Output:
        def __init__(self, *args, **kwargs):
            pass


class _IO:
    ComfyNode = object
    Schema = object
    NodeOutput = NodeOutput
    Model = _Port
    Float = _Port
    Boolean = _Port


class MockModel:
    def __init__(self):
        self.cfg_function = None
        self.pre_functions = []
        self.post_functions = []

    def clone(self):
        return MockModel()

    def set_model_sampler_cfg_function(self, function):
        self.cfg_function = function

    def set_model_sampler_pre_cfg_function(self, function):
        self.pre_functions.append(function)

    def set_model_sampler_post_cfg_function(self, function):
        self.post_functions.append(function)


def load_symbols(path: Path, names: set[str], extra: dict[str, object]) -> dict[str, object]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    selected = [
        node
        for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.ClassDef)) and node.name in names
    ]
    module = ast.Module(body=selected, type_ignores=[])
    ast.fix_missing_locations(module)
    namespace: dict[str, object] = {
        "torch": torch,
        "F": F,
        "io": _IO,
        "override": lambda value: value,
    }
    namespace.update(extra)
    exec(compile(module, str(path), "exec"), namespace)
    return namespace


def tensor_list(value: torch.Tensor) -> list:
    return value.detach().cpu().tolist()


def main() -> None:
    source_root = Path(sys.argv[1]).resolve()
    cfg = load_symbols(
        source_root / "comfy_extras" / "nodes_cfg.py",
        {"optimized_scale", "CFGZeroStar", "CFGNorm"},
        {},
    )
    tcfg = load_symbols(
        source_root / "comfy_extras" / "nodes_tcfg.py",
        {"score_tangential_damping", "TCFG"},
        {},
    )
    mahiro = load_symbols(
        source_root / "comfy_extras" / "nodes_mahiro.py",
        {"Mahiro"},
        {},
    )

    cond = torch.tensor([[[[3.0]], [[4.0]]]])
    combined = torch.tensor([[[[6.0]], [[8.0]]]])
    post_results = {}
    for strength in (0.0, 1.0, 2.0):
        patched = cfg["CFGNorm"].execute(MockModel(), strength, False)[0]
        post_results[str(strength)] = tensor_list(
            patched.post_functions[0](
                {"cond_denoised": cond, "denoised": combined}
            )
        )

    pre_results = {}
    for strength in (0.0, 1.0, 2.0):
        patched = cfg["CFGNorm"].execute(MockModel(), strength, True)[0]
        pre_results[str(strength)] = tensor_list(
            patched.cfg_function(
                {
                    "cond": cond,
                    "uncond": torch.zeros_like(cond),
                    "cond_scale": 2.0,
                }
            )
        )
    zero_pre = cfg["CFGNorm"].execute(MockModel(), 1.0, True)[0]
    zero_pre_result = zero_pre.cfg_function(
        {
            "cond": torch.zeros_like(cond),
            "uncond": torch.zeros_like(cond),
            "cond_scale": 8.0,
        }
    )

    positive = torch.tensor([[2.0, 0.0], [0.0, 3.0]])
    negative = torch.tensor([[1.0, 0.0], [0.0, 1.0]])
    alphas = cfg["optimized_scale"](positive, negative)
    zero_alpha = cfg["optimized_scale"](
        torch.ones((1, 2)), torch.zeros((1, 2))
    )
    zero_star_model = cfg["CFGZeroStar"].execute(MockModel())[0]
    zero_star = zero_star_model.post_functions[0]
    zs_args = {
        "cond_scale": 3.0,
        "input": torch.zeros((1, 2)),
        "cond_denoised": torch.tensor([[-2.0, 0.0]]),
        "uncond_denoised": torch.tensor([[-1.0, 0.0]]),
        "denoised": torch.tensor([[5.0, 5.0]]),
    }
    zs_result = zero_star(zs_args)
    zs_cfg_one = zero_star({**zs_args, "cond_scale": 1.0})

    cond_score = torch.tensor([[2.0, 0.0]], dtype=torch.float16)
    uncond_score = torch.tensor([[0.0, 1.0]], dtype=torch.float16)
    projected = tcfg["score_tangential_damping"](cond_score, uncond_score)
    tcfg_model = tcfg["TCFG"].execute(MockModel())[0]
    tcfg_hook = tcfg_model.pre_functions[0]
    x = torch.zeros((1, 2), dtype=torch.float16)
    transformed = tcfg_hook(
        {
            "input": x,
            "conds": [["positive"], ["negative"]],
            "conds_out": [-cond_score, -uncond_score],
        }
    )
    skipped = tcfg_hook(
        {
            "input": x,
            "conds": [["positive"], None],
            "conds_out": [-cond_score, -uncond_score],
        }
    )

    mahiro_model = mahiro["Mahiro"].execute(MockModel())[0]
    mahiro_hook = mahiro_model.post_functions[0]

    def run_mahiro(scale, cond_p, uncond_p, denoised):
        return mahiro_hook(
            {
                "cond_scale": scale,
                "cond_denoised": torch.tensor(cond_p, dtype=torch.float32),
                "uncond_denoised": torch.tensor(uncond_p, dtype=torch.float32),
                "denoised": torch.tensor(denoised, dtype=torch.float32),
            }
        )

    mahiro_same = run_mahiro(2.0, [[1.0, 0.0]], [[1.0, 0.0]], [[1.0, 0.0]])
    mahiro_opposite = run_mahiro(1.0, [[-4.0, 0.0]], [[1.0, 0.0]], [[0.0, 0.0]])
    mahiro_orthogonal = run_mahiro(1.0, [[0.0, 0.0]], [[1.0, 0.0]], [[0.0, 2.0]])
    mahiro_batch = run_mahiro(
        1.0,
        [[2.0, 0.0], [-2.0, 0.0]],
        [[1.0, 0.0], [1.0, 0.0]],
        [[0.0, 0.0], [0.0, 0.0]],
    )
    mahiro_cfg_one = run_mahiro(1.0, [[2.0, -1.0]], [[0.0, 0.0]], [[2.0, -1.0]])

    result = {
        "cfgNorm": {
            "post": post_results,
            "pre": pre_results,
            "zeroPre": tensor_list(zero_pre_result),
            "postHookCount": len(cfg["CFGNorm"].execute(MockModel(), 1.0, False)[0].post_functions),
            "preCfgFunction": cfg["CFGNorm"].execute(MockModel(), 1.0, True)[0].cfg_function is not None,
        },
        "cfgZeroStar": {
            "alphas": tensor_list(alphas),
            "zeroAlpha": tensor_list(zero_alpha),
            "zeroAlphaFinite": bool(torch.isfinite(zero_alpha).all()),
            "result": tensor_list(zs_result),
            "cfgOne": tensor_list(zs_cfg_one),
            "postHookCount": len(zero_star_model.post_functions),
        },
        "tcfg": {
            "projected": tensor_list(projected),
            "projectedDtype": str(projected.dtype),
            "transformedCond": tensor_list(transformed[0]),
            "transformedUncond": tensor_list(transformed[1]),
            "skipIdentity": bool(skipped[0] is not None and torch.equal(skipped[1], -uncond_score)),
            "preHookCount": len(tcfg_model.pre_functions),
        },
        "mahiro": {
            "sameDirection": tensor_list(mahiro_same),
            "oppositeDirection": tensor_list(mahiro_opposite),
            "orthogonal": tensor_list(mahiro_orthogonal),
            "batchCoupled": tensor_list(mahiro_batch),
            "cfgOne": tensor_list(mahiro_cfg_one),
            "postHookCount": len(mahiro_model.post_functions),
        },
    }
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
