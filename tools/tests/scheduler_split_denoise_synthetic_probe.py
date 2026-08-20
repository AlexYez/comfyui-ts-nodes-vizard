from __future__ import annotations

import ast
import json
from pathlib import Path
from types import SimpleNamespace

import numpy
import scipy
import torch


ROOT = Path(__file__).resolve().parents[2]
CUSTOM_SOURCE = ROOT / ".comfyui-source-0.32.0" / "comfy_extras" / "nodes_custom_sampler.py"
SAMPLERS_SOURCE = ROOT / ".comfyui-source-0.32.0" / "comfy" / "samplers.py"
K_DIFFUSION_SOURCE = ROOT / ".comfyui-source-0.32.0" / "comfy" / "k_diffusion" / "sampling.py"


class DummyNodeOutput:
    def __init__(self, *values: object) -> None:
        self.values = values


def extract_functions(path: Path, names: set[str], namespace: dict[str, object]) -> dict[str, object]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    selected = [
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name in names
    ]
    if {node.name for node in selected} != names:
        raise AssertionError(f"missing exact functions in {path}")
    exec(compile(ast.Module(body=selected, type_ignores=[]), str(path), "exec"), namespace)
    return {name: namespace[name] for name in names}


def load_exact_classes() -> dict[str, type]:
    k_functions = extract_functions(
        K_DIFFUSION_SOURCE,
        {"append_zero", "get_sigmas_vp", "get_sigmas_laplace"},
        {"torch": torch},
    )
    beta_function = extract_functions(
        SAMPLERS_SOURCE,
        {"beta_scheduler"},
        {"torch": torch, "numpy": numpy, "scipy": scipy},
    )["beta_scheduler"]

    tree = ast.parse(CUSTOM_SOURCE.read_text(encoding="utf-8"))
    names = {"SplitSigmasDenoise", "VPScheduler", "BetaSamplingScheduler", "LaplaceScheduler"}
    selected = [
        node
        for node in tree.body
        if isinstance(node, ast.ClassDef) and node.name in names
    ]
    if {node.name for node in selected} != names:
        raise AssertionError("pinned scheduler classes were not found")
    namespace: dict[str, object] = {
        "io": SimpleNamespace(ComfyNode=object, NodeOutput=DummyNodeOutput),
        "torch": torch,
        "k_diffusion_sampling": SimpleNamespace(**k_functions),
        "comfy": SimpleNamespace(
            samplers=SimpleNamespace(beta_scheduler=beta_function),
        ),
    }
    exec(
        compile(ast.Module(body=selected, type_ignores=[]), str(CUSTOM_SOURCE), "exec"),
        namespace,
    )
    return {name: namespace[name] for name in names}  # type: ignore[return-value]


class DummyModel:
    def __init__(self, sigmas: torch.Tensor) -> None:
        self.sampling = SimpleNamespace(sigmas=sigmas)

    def get_model_object(self, name: str) -> object:
        assert name == "model_sampling"
        return self.sampling


def run() -> dict[str, object]:
    classes = load_exact_classes()

    split = classes["SplitSigmasDenoise"]
    schedule = torch.tensor([5.0, 4.0, 3.0, 2.0, 0.0])
    half_high, half_low = split.execute(schedule, 0.5).values
    zero_high, zero_low = split.execute(schedule, 0.0).values
    full_high, full_low = split.execute(schedule, 1.0).values
    empty = split.execute(torch.empty(0), 0.5).values
    singleton = split.execute(torch.tensor([6.0]), 0.5).values
    bank_schedule = torch.tensor([6.0, 5.0, 4.0, 3.0, 2.0, 0.0])
    bank_high, bank_low = split.execute(bank_schedule, 0.5).values
    assert torch.equal(half_high, torch.tensor([5.0, 4.0, 3.0]))
    assert torch.equal(half_low, torch.tensor([3.0, 2.0, 0.0]))
    assert [tensor.numel() for tensor in (zero_high, zero_low)] == [0, 1]
    assert [tensor.numel() for tensor in (full_high, full_low)] == [1, 5]
    assert [tensor.numel() for tensor in empty] == [0, 0]
    assert [tensor.numel() for tensor in singleton] == [0, 1]
    assert torch.equal(bank_high, torch.tensor([6.0, 5.0, 4.0, 3.0]))
    assert torch.equal(bank_low, torch.tensor([3.0, 2.0, 0.0]))
    assert half_high.untyped_storage().data_ptr() == schedule.untyped_storage().data_ptr()
    assert half_low.untyped_storage().data_ptr() == schedule.untyped_storage().data_ptr()

    vp = classes["VPScheduler"]
    vp_default = vp.execute(4, 19.9, 0.1, 0.001).values[0]
    vp_one = vp.execute(1, 19.9, 0.1, 0.001).values[0]
    vp_eps_zero = vp.execute(4, 19.9, 0.1, 0.0).values[0]
    vp_eps_one = vp.execute(4, 19.9, 0.1, 1.0).values[0]
    vp_zero_beta = vp.execute(4, 0.0, 0.0, 0.001).values[0]
    vp_overflow = vp.execute(4, 5000.0, 5000.0, 0.001).values[0]
    assert vp_default.shape == (5,) and vp_default[-1] == 0
    assert torch.all(vp_default[:-1] > vp_default[1:])
    assert vp_one.shape == (2,) and vp_one[-1] == 0
    assert vp_eps_zero[-2:].tolist() == [0.0, 0.0]
    assert torch.all(vp_eps_one[:-1] == vp_eps_one[0])
    assert torch.count_nonzero(vp_zero_beta) == 0
    assert torch.isinf(vp_overflow[:3]).all()
    assert torch.isfinite(vp_overflow[-2:]).all()

    beta = classes["BetaSamplingScheduler"]
    model = DummyModel(torch.tensor([0.0, 1.0, 2.0, 3.0, 4.0, 5.0]))
    beta_default = beta.execute(model, 4, 0.6, 0.6).values[0]
    beta_many = beta.execute(model, 20, 0.6, 0.6).values[0]
    beta_one = beta.execute(model, 1, 0.6, 0.6).values[0]
    alpha_zero_error = None
    beta_zero_error = None
    try:
        beta.execute(model, 4, 0.0, 0.6)
    except ValueError as exc:
        alpha_zero_error = type(exc).__name__
    try:
        beta.execute(model, 4, 0.6, 0.0)
    except ValueError as exc:
        beta_zero_error = type(exc).__name__
    assert torch.equal(beta_default, torch.tensor([5.0, 4.0, 3.0, 1.0, 0.0]))
    assert torch.equal(beta_many, torch.tensor([5.0, 4.0, 3.0, 2.0, 1.0, 0.0, 0.0]))
    assert torch.equal(beta_one, torch.tensor([5.0, 0.0]))
    assert alpha_zero_error == "ValueError"
    assert beta_zero_error == "ValueError"

    laplace = classes["LaplaceScheduler"]
    laplace_default = laplace.execute(5, 14.614642, 0.0291675, 0.0, 0.5).values[0]
    laplace_one = laplace.execute(1, 14.614642, 0.0291675, 0.0, 0.5).values[0]
    laplace_two = laplace.execute(2, 14.614642, 0.0291675, 0.0, 0.5).values[0]
    laplace_beta_zero = laplace.execute(5, 14.614642, 0.0291675, 0.0, 0.0).values[0]
    laplace_bad_bounds = laplace.execute(5, 2.0, 3.0, 0.0, 0.5).values[0]
    assert laplace_default.shape == (5,)
    assert torch.all(laplace_default[:-1] >= laplace_default[1:])
    assert torch.isclose(laplace_default[0], torch.tensor(14.614642))
    assert torch.isclose(laplace_default[-1], torch.tensor(0.0291675))
    assert laplace_default[-1] != 0
    assert laplace_one.shape == (1,) and torch.isclose(laplace_one[0], torch.tensor(14.614642))
    assert torch.allclose(laplace_two, torch.tensor([14.614642, 0.0291675]))
    assert torch.all(laplace_beta_zero == 1.0)
    assert torch.all(laplace_bad_bounds == 2.0)

    return {
        "splitDenoise": {
            "halfHigh": half_high.tolist(),
            "halfLow": half_low.tolist(),
            "zeroLengths": [int(tensor.numel()) for tensor in (zero_high, zero_low)],
            "fullLengths": [int(tensor.numel()) for tensor in (full_high, full_low)],
            "emptyLengths": [int(tensor.numel()) for tensor in empty],
            "singletonLengths": [int(tensor.numel()) for tensor in singleton],
            "bankersHalfHigh": bank_high.tolist(),
            "bankersHalfLow": bank_low.tolist(),
            "sharedStorage": (
                half_high.untyped_storage().data_ptr() == schedule.untyped_storage().data_ptr()
                and half_low.untyped_storage().data_ptr() == schedule.untyped_storage().data_ptr()
            ),
        },
        "vp": {
            "default": vp_default.tolist(),
            "oneStep": vp_one.tolist(),
            "epsZero": vp_eps_zero.tolist(),
            "epsOne": vp_eps_one.tolist(),
            "zeroBeta": vp_zero_beta.tolist(),
            "overflowIsInf": torch.isinf(vp_overflow).tolist(),
        },
        "beta": {
            "fourSteps": beta_default.tolist(),
            "twentyRequested": beta_many.tolist(),
            "oneStep": beta_one.tolist(),
            "alphaZeroError": alpha_zero_error,
            "betaZeroError": beta_zero_error,
        },
        "laplace": {
            "default": laplace_default.tolist(),
            "oneStep": laplace_one.tolist(),
            "twoSteps": laplace_two.tolist(),
            "betaZero": laplace_beta_zero.tolist(),
            "reversedBounds": laplace_bad_bounds.tolist(),
        },
    }


if __name__ == "__main__":
    print(json.dumps(run(), ensure_ascii=False, sort_keys=True))
