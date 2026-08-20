from __future__ import annotations

import ast
import json
import math
import sys
import types
from pathlib import Path
from typing import Any


TARGET_CLASSES = {
    "SamplerDPMPP_3M_SDE",
    "SamplerDPMPP_2M_SDE",
    "SamplerDPMPP_SDE",
    "SamplerDPMPP_2S_Ancestral",
}


def compile_named(path: Path, names: set[str], node_types: tuple[type[ast.AST], ...]):
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    body = [node for node in tree.body if isinstance(node, node_types) and getattr(node, "name", None) in names]
    found = {getattr(node, "name") for node in body}
    if found != names:
        raise AssertionError(f"missing exact-source definitions: {sorted(names - found)}")
    return compile(ast.Module(body=body, type_ignores=[]), str(path), "exec")


def has_two_r_divisor(path: Path) -> bool:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    function = next(
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name == "sample_dpmpp_sde"
    )
    for node in ast.walk(function):
        if not isinstance(node, ast.BinOp) or not isinstance(node.op, ast.Div):
            continue
        denominator = node.right
        if (
            isinstance(denominator, ast.BinOp)
            and isinstance(denominator.op, ast.Mult)
            and isinstance(denominator.left, ast.Constant)
            and denominator.left.value == 2
            and isinstance(denominator.right, ast.Name)
            and denominator.right.id == "r"
        ):
            return True
    return False


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit("usage: dpmpp_sampler_synthetic_probe.py <pinned-comfyui-source>")

    source = Path(sys.argv[1]).resolve()
    node_path = source / "comfy_extras" / "nodes_custom_sampler.py"
    sampling_path = source / "comfy" / "k_diffusion" / "sampling.py"
    calls: list[dict[str, Any]] = []

    def ksampler(name: str, options: dict[str, Any]):
        result = {"name": name, "options": dict(options)}
        calls.append(result)
        return result

    namespace: dict[str, Any] = {
        "io": types.SimpleNamespace(ComfyNode=object, NodeOutput=lambda *items: tuple(items)),
        "comfy": types.SimpleNamespace(samplers=types.SimpleNamespace(ksampler=ksampler)),
    }
    exec(compile_named(node_path, TARGET_CLASSES, (ast.ClassDef,)), namespace)

    outputs: dict[str, Any] = {}
    outputs["3mCpu"] = namespace["SamplerDPMPP_3M_SDE"].execute(0.7, 0.8, "cpu")[0]
    outputs["3mGpu"] = namespace["SamplerDPMPP_3M_SDE"].execute(0.7, 0.8, "gpu")[0]
    outputs["2mMidpointCpu"] = namespace["SamplerDPMPP_2M_SDE"].execute("midpoint", 0.6, 0.9, "cpu")[0]
    outputs["2mHeunGpu"] = namespace["SamplerDPMPP_2M_SDE"].execute("heun", 0.6, 0.9, "gpu")[0]
    outputs["sdeCpu"] = namespace["SamplerDPMPP_SDE"].execute(0.5, 0.75, 0.4, "cpu")[0]
    outputs["sdeGpu"] = namespace["SamplerDPMPP_SDE"].execute(0.5, 0.75, 0.4, "gpu")[0]
    outputs["twoS"] = namespace["SamplerDPMPP_2S_Ancestral"].execute(0.25, 0.5)[0]

    step_namespace: dict[str, Any] = {}
    exec(compile_named(sampling_path, {"get_ancestral_step"}, (ast.FunctionDef,)), step_namespace)
    get_ancestral_step = step_namespace["get_ancestral_step"]
    eta_zero = get_ancestral_step(10.0, 5.0, eta=0.0)
    eta_one = get_ancestral_step(10.0, 5.0, eta=1.0)
    assert eta_zero == (5.0, 0.0)
    assert math.isclose(eta_one[0], 2.5)
    assert math.isclose(eta_one[1], math.sqrt(18.75))

    assert outputs["3mCpu"] == {"name": "dpmpp_3m_sde", "options": {"eta": 0.7, "s_noise": 0.8}}
    assert outputs["3mGpu"] == {"name": "dpmpp_3m_sde_gpu", "options": {"eta": 0.7, "s_noise": 0.8}}
    assert outputs["2mMidpointCpu"]["name"] == "dpmpp_2m_sde"
    assert outputs["2mMidpointCpu"]["options"]["solver_type"] == "midpoint"
    assert outputs["2mHeunGpu"]["name"] == "dpmpp_2m_sde_gpu"
    assert outputs["2mHeunGpu"]["options"]["solver_type"] == "heun"
    assert outputs["sdeCpu"] == {"name": "dpmpp_sde", "options": {"eta": 0.5, "s_noise": 0.75, "r": 0.4}}
    assert outputs["sdeGpu"] == {"name": "dpmpp_sde_gpu", "options": {"eta": 0.5, "s_noise": 0.75, "r": 0.4}}
    assert outputs["twoS"] == {"name": "dpmpp_2s_ancestral", "options": {"eta": 0.25, "s_noise": 0.5}}
    assert has_two_r_divisor(sampling_path)

    print(
        json.dumps(
            {
                "constructors": outputs,
                "callCount": len(calls),
                "ancestralStep": {"eta0": eta_zero, "eta1": eta_one},
                "dpmppSdeDividesByTwoR": True,
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
