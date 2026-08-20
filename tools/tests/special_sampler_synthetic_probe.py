from __future__ import annotations

import ast
import json
import sys
import types
from pathlib import Path
from typing import Callable, Union

import torch


class _IO:
    ComfyNode = object

    @staticmethod
    def NodeOutput(*values):
        return values


def selected_definitions(path: Path, names: set[str]) -> list[ast.stmt]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    return [
        node
        for node in tree.body
        if isinstance(node, (ast.ClassDef, ast.FunctionDef)) and node.name in names
    ]


def execute_definitions(path: Path, names: set[str], namespace: dict) -> dict:
    module = ast.Module(body=selected_definitions(path, names), type_ignores=[])
    ast.fix_missing_locations(module)
    exec(compile(module, str(path), "exec"), namespace)
    return namespace


class RecordingSamplers:
    def __init__(self):
        self.calls: list[tuple[str, dict]] = []

    def ksampler(self, name, options):
        result = {"name": name, "options": dict(options)}
        self.calls.append((name, dict(options)))
        return result


class ModelSampling:
    def __init__(self):
        self.calls: list[float] = []

    def percent_to_sigma(self, value):
        value = float(value)
        self.calls.append(value)
        return 10.0 - 10.0 * value


class Model:
    def __init__(self, sampling):
        self.sampling = sampling

    def get_model_object(self, name):
        assert name == "model_sampling"
        return self.sampling


def main() -> None:
    source_root = Path(sys.argv[1]).resolve()
    tau_ns = {"torch": torch, "Callable": Callable, "Union": Union}
    execute_definitions(
        source_root / "comfy" / "k_diffusion" / "sa_solver.py",
        {"get_tau_interval_func"},
        tau_ns,
    )
    sa_solver = types.SimpleNamespace(get_tau_interval_func=tau_ns["get_tau_interval_func"])
    factory = RecordingSamplers()
    namespace = {
        "torch": torch,
        "io": _IO,
        "comfy": types.SimpleNamespace(samplers=factory),
        "sa_solver": sa_solver,
    }
    execute_definitions(
        source_root / "comfy_extras" / "nodes_custom_sampler.py",
        {"SamplerDPMAdaptative", "SamplerER_SDE", "SamplerSASolver", "SamplerSEEDS2"},
        namespace,
    )

    dpm = namespace["SamplerDPMAdaptative"].execute(
        3, 0.05, 0.0078, 0.05, 0.0, 1.0, 0.0, 0.81, 0.0, 1.0
    )[0]
    assert dpm["name"] == "dpm_adaptive"
    assert dpm["options"] == {
        "order": 3,
        "rtol": 0.05,
        "atol": 0.0078,
        "h_init": 0.05,
        "pcoeff": 0.0,
        "icoeff": 1.0,
        "dcoeff": 0.0,
        "accept_safety": 0.81,
        "eta": 0.0,
        "s_noise": 1.0,
    }

    er = namespace["SamplerER_SDE"]
    er_sde = er.execute("ER-SDE", 3, 0.5, 1.25)[0]
    reverse = er.execute("Reverse-time SDE", 2, 0.5, 2.0)[0]
    ode = er.execute("ODE", 1, 7.0, 9.0)[0]
    zero_eta = er.execute("ER-SDE", 3, 0.0, 4.0)[0]
    x = torch.tensor(2.0)
    expected_er = x * ((x ** 0.3).exp() + 10.0) ** 0.5
    assert torch.allclose(er_sde["options"]["noise_scaler"](x), expected_er)
    assert torch.allclose(reverse["options"]["noise_scaler"](x), x ** 1.5)
    assert ode["options"]["noise_scaler"](x).item() == 2.0
    assert zero_eta["options"]["noise_scaler"](x).item() == 2.0
    assert er_sde["options"]["s_noise"] == 1.25 and er_sde["options"]["max_stage"] == 3
    assert reverse["options"]["s_noise"] == 2.0 and reverse["options"]["max_stage"] == 2
    assert ode["options"]["s_noise"] == 0.0 and zero_eta["options"]["s_noise"] == 0.0

    model_sampling = ModelSampling()
    sa = namespace["SamplerSASolver"].execute(
        Model(model_sampling), 1.5, 0.2, 0.8, 1.25, 3, 4, False, False
    )[0]
    assert model_sampling.calls == [0.2, 0.8]
    tau = sa["options"]["tau_func"]
    assert [tau(value) for value in (9.0, 8.0, 5.0, 2.0, 1.0)] == [0.0, 1.5, 1.5, 1.5, 0.0]
    assert sa["options"]["s_noise"] == 1.25
    assert sa["options"]["predictor_order"] == 3
    assert sa["options"]["corrector_order"] == 4
    assert sa["options"]["use_pece"] is False
    assert sa["options"]["simple_order_2"] is False
    zero_tau = sa_solver.get_tau_interval_func(8.0, 2.0, eta=0.0)
    assert [zero_tau(value) for value in (8.0, 5.0, 2.0)] == [0.0, 0.0, 0.0]

    seeds = namespace["SamplerSEEDS2"].execute("phi_2", 0.0, 1.0, 1.0)[0]
    assert seeds == {
        "name": "seeds_2",
        "options": {"eta": 0.0, "s_noise": 1.0, "r": 1.0, "solver_type": "phi_2"},
    }

    sampling_source = (source_root / "comfy" / "k_diffusion" / "sampling.py").read_text(encoding="utf-8")
    assert "inject_noise = eta > 0 and s_noise > 0" in sampling_source
    assert "stage_used = min(max_stage, i + 1)" in sampling_source
    assert "predictor_order_used = min(predictor_order, len(pred_list))" in sampling_source
    assert "corrector_order_used = min(corrector_order, len(pred_list))" in sampling_source

    print(
        json.dumps(
            {
                "dpm": {"name": dpm["name"], "options": dpm["options"]},
                "erSde": {
                    "erScalerAt2": float(er_sde["options"]["noise_scaler"](x)),
                    "reverseScalerAt2": float(reverse["options"]["noise_scaler"](x)),
                    "odeNoise": ode["options"]["s_noise"],
                    "etaZeroNoise": zero_eta["options"]["s_noise"],
                },
                "saSolver": {
                    "percentCalls": model_sampling.calls,
                    "tauSamples": [tau(value) for value in (9.0, 8.0, 5.0, 2.0, 1.0)],
                    "options": {key: value for key, value in sa["options"].items() if key != "tau_func"},
                },
                "seeds2": seeds,
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
