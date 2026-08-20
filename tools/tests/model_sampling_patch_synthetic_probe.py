from __future__ import annotations

import ast
import json
import math
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import torch


def _extract_model_sampling(source_root: Path) -> SimpleNamespace:
    path = source_root / "comfy" / "model_sampling.py"
    tree = ast.parse(path.read_text(encoding="utf-8"))
    wanted = {
        "rescale_zero_terminal_snr_sigmas",
        "reshape_sigma",
        "EPS",
        "V_PREDICTION",
        "EDM",
        "CONST",
        "X0",
        "IMG_TO_IMG",
        "IMG_TO_IMG_FLOW",
        "COSMOS_RFLOW",
        "ModelSamplingDiscrete",
        "ModelSamplingContinuousEDM",
        "ModelSamplingContinuousV",
        "StableCascadeSampling",
        "ModelSamplingCosmosRFlow",
    }
    body = [
        node
        for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.ClassDef)) and node.name in wanted
    ]

    def make_beta_schedule(
        _schedule: str,
        timesteps: int,
        linear_start: float,
        linear_end: float,
        cosine_s: float = 8e-3,
    ) -> torch.Tensor:
        del cosine_s
        return torch.linspace(linear_start**0.5, linear_end**0.5, timesteps) ** 2

    namespace: dict[str, Any] = {
        "math": math,
        "torch": torch,
        "make_beta_schedule": make_beta_schedule,
    }
    exec(compile(ast.Module(body=body, type_ignores=[]), str(path), "exec"), namespace)
    return SimpleNamespace(**{name: namespace[name] for name in wanted if name in namespace})


def _extract_patch_nodes(source_root: Path, model_sampling: SimpleNamespace) -> dict[str, type]:
    path = source_root / "comfy_extras" / "nodes_model_advanced.py"
    tree = ast.parse(path.read_text(encoding="utf-8"))
    wanted = {
        "LCM",
        "ModelSamplingDiscreteDistilled",
        "ModelSamplingDiscrete",
        "ModelSamplingStableCascade",
        "ModelSamplingContinuousEDM",
        "ModelSamplingContinuousV",
    }
    body = [node for node in tree.body if isinstance(node, ast.ClassDef) and node.name in wanted]

    class SDXLPlayground25:
        marker = "SDXL_Playground_2_5"

    namespace: dict[str, Any] = {
        "comfy": SimpleNamespace(model_sampling=model_sampling),
        "torch": torch,
    }
    namespace["comfy"].latent_formats = SimpleNamespace(SDXL_Playground_2_5=SDXLPlayground25)
    exec(compile(ast.Module(body=body, type_ignores=[]), str(path), "exec"), namespace)
    return {name: namespace[name] for name in wanted}


class _FakeModel:
    def __init__(self, model_config: Any, origin: "_FakeModel | None" = None) -> None:
        self.model = SimpleNamespace(model_config=model_config)
        self.origin = origin
        self.patches: dict[str, Any] = {}

    def clone(self) -> "_FakeModel":
        return _FakeModel(self.model.model_config, origin=self)

    def add_object_patch(self, name: str, value: Any) -> None:
        self.patches[name] = value


def run_probe(source_root: Path) -> dict[str, Any]:
    sampling = _extract_model_sampling(source_root)
    nodes = _extract_patch_nodes(source_root, sampling)
    config = SimpleNamespace(sampling_settings={})
    original = _FakeModel(config)

    discrete_results: dict[str, Any] = {}
    for choice, expected_type in {
        "eps": sampling.EPS,
        "v_prediction": sampling.V_PREDICTION,
        "lcm": nodes["LCM"],
        "x0": sampling.X0,
        "img_to_img": sampling.IMG_TO_IMG,
        "img_to_img_flow": sampling.IMG_TO_IMG_FLOW,
    }.items():
        patched = nodes["ModelSamplingDiscrete"]().patch(original, choice, False)[0]
        model_sampling = patched.patches["model_sampling"]
        assert patched is not original and patched.origin is original
        assert not original.patches
        assert isinstance(model_sampling, expected_type)
        assert model_sampling.zsnr is False
        if choice == "lcm":
            assert isinstance(model_sampling, nodes["ModelSamplingDiscreteDistilled"])
            assert len(model_sampling.sigmas) == 50
            assert model_sampling.skip_steps == 20
        else:
            assert isinstance(model_sampling, sampling.ModelSamplingDiscrete)
            assert len(model_sampling.sigmas) == 1000
        discrete_results[choice] = {
            "samplingClass": expected_type.__name__,
            "sigmaCount": len(model_sampling.sigmas),
        }

    zsnr_model = nodes["ModelSamplingDiscrete"]().patch(original, "eps", True)[0].patches[
        "model_sampling"
    ]
    plain_model = nodes["ModelSamplingDiscrete"]().patch(original, "eps", False)[0].patches[
        "model_sampling"
    ]
    assert zsnr_model.zsnr is True
    assert float(zsnr_model.sigma_max) > float(plain_model.sigma_max)

    edm_results: dict[str, Any] = {}
    for choice, sigma_data in {
        "v_prediction": 1.0,
        "edm": 0.5,
        "edm_playground_v2.5": 0.5,
        "eps": 1.0,
        "cosmos_rflow": 1.0,
    }.items():
        patched = nodes["ModelSamplingContinuousEDM"]().patch(original, choice, 120.0, 0.002)[0]
        model_sampling = patched.patches["model_sampling"]
        assert len(model_sampling.sigmas) == 1000
        assert math.isclose(float(model_sampling.sigma_min), 0.002, rel_tol=1e-5)
        assert math.isclose(float(model_sampling.sigma_max), 120.0, rel_tol=1e-5)
        assert model_sampling.sigma_data == sigma_data
        if choice == "cosmos_rflow":
            assert isinstance(model_sampling, sampling.ModelSamplingCosmosRFlow)
            assert isinstance(model_sampling, sampling.COSMOS_RFLOW)
        if choice == "edm_playground_v2.5":
            assert patched.patches["latent_format"].marker == "SDXL_Playground_2_5"
        else:
            assert "latent_format" not in patched.patches
        edm_results[choice] = {"sigmaData": sigma_data, "patches": sorted(patched.patches)}

    try:
        nodes["ModelSamplingContinuousEDM"]().patch(original, "eps", 120.0, 0.0)
    except ValueError:
        edm_zero_rejected = True
    else:
        raise AssertionError("sigma_min=0 must fail in math.log")

    reversed_edm = nodes["ModelSamplingContinuousEDM"]().patch(original, "eps", 1.0, 10.0)[0].patches[
        "model_sampling"
    ]
    assert math.isclose(float(reversed_edm.sigmas[0]), 10.0, rel_tol=1e-6)
    assert math.isclose(float(reversed_edm.sigmas[-1]), 1.0, rel_tol=1e-6)
    assert bool(torch.all(reversed_edm.sigmas[:-1] > reversed_edm.sigmas[1:]))

    continuous_v = nodes["ModelSamplingContinuousV"]().patch(
        original, "v_prediction", 500.0, 0.03
    )[0].patches["model_sampling"]
    assert isinstance(continuous_v, sampling.ModelSamplingContinuousV)
    assert isinstance(continuous_v, sampling.V_PREDICTION)
    assert math.isclose(float(continuous_v.sigma_min), 0.03, rel_tol=1e-5)
    assert math.isclose(float(continuous_v.sigma_max), 500.0, rel_tol=1e-5)
    sigma = torch.tensor([0.03, 1.0, 500.0])
    torch.testing.assert_close(
        continuous_v.sigma(continuous_v.timestep(sigma)), sigma, rtol=5e-5, atol=1e-5
    )

    stable = nodes["ModelSamplingStableCascade"]().patch(original, 2.0)[0].patches[
        "model_sampling"
    ]
    assert isinstance(stable, sampling.StableCascadeSampling)
    assert isinstance(stable, sampling.EPS)
    assert stable.shift == 2.0
    assert len(stable.sigmas) == 10000
    assert bool(torch.all(stable.sigmas[:-1] <= stable.sigmas[1:]))
    stable_zero = nodes["ModelSamplingStableCascade"]().patch(original, 0.0)[0].patches[
        "model_sampling"
    ]
    assert stable_zero.shift == 0.0
    assert bool(torch.isfinite(stable_zero.sigmas).all())
    assert torch.unique(stable_zero.sigmas).numel() == 1

    return {
        "discrete": {
            "choices": discrete_results,
            "plainSigmaMax": float(plain_model.sigma_max),
            "zsnrSigmaMax": float(zsnr_model.sigma_max),
        },
        "continuousEDM": {
            "choices": edm_results,
            "zeroSigmaMinRejected": edm_zero_rejected,
            "reversedBounds": [float(reversed_edm.sigmas[0]), float(reversed_edm.sigmas[-1])],
        },
        "continuousV": {
            "bounds": [float(continuous_v.sigma_min), float(continuous_v.sigma_max)],
            "roundTrip": continuous_v.sigma(continuous_v.timestep(sigma)).tolist(),
        },
        "stableCascade": {
            "sigmaCount": len(stable.sigmas),
            "shift": stable.shift,
            "shiftZeroUniqueSigmas": torch.unique(stable_zero.sigmas).numel(),
        },
    }


if __name__ == "__main__":
    root = Path(sys.argv[1] if len(sys.argv) > 1 else ".comfyui-source-0.32.0")
    print(json.dumps(run_probe(root), ensure_ascii=False, sort_keys=True))
