from __future__ import annotations

import ast
import json
import sys
import types
from pathlib import Path

import numpy as np
import torch


class _IO:
    ComfyNode = object

    @staticmethod
    def NodeOutput(*values):
        return values


def selected_definitions(path: Path, names: set[str]) -> list[ast.stmt]:
    """Select top-level definitions without importing the ComfyUI module."""

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


def quiet_range(count, disable=None):
    del disable
    return range(count)


class RecordingSamplers:
    def __init__(self):
        self.calls: list[dict] = []

    def ksampler(self, name, options=None, inpaint_options=None):
        result = {
            "kind": "named",
            "name": name,
            "options": dict(options or {}),
            "inpaintOptions": dict(inpaint_options or {}),
        }
        self.calls.append(result)
        return result

    def KSAMPLER(self, function, extra_options=None, inpaint_options=None):
        result = {
            "kind": "callable",
            "function": function.__name__,
            "options": dict(extra_options or {}),
            "inpaintOptions": dict(inpaint_options or {}),
        }
        self.calls.append(result)
        return result


class UpscaleRecorder:
    def __init__(self):
        self.calls: list[dict] = []

    def common_upscale(self, value, width, height, method, crop):
        self.calls.append(
            {
                "inputShape": list(value.shape),
                "width": int(width),
                "height": int(height),
                "method": method,
                "crop": crop,
            }
        )
        return value.new_zeros((value.shape[0], value.shape[1], height, width))


class LCMNoiseScaling:
    def __init__(self):
        self.calls: list[dict] = []

    def noise_scaling(self, sigma, noise, latent):
        self.calls.append(
            {
                "sigma": float(sigma),
                "noise": noise.detach().clone(),
                "latentShape": list(latent.shape),
            }
        )
        return latent + noise


class LCMModel:
    def __init__(self, model_sampling):
        patcher = types.SimpleNamespace(
            get_model_object=lambda name: model_sampling
            if name == "model_sampling"
            else (_ for _ in ()).throw(AssertionError(name))
        )
        self.inner_model = types.SimpleNamespace(model_patcher=patcher)

    def __call__(self, value, sigma, **extra_args):
        del sigma, extra_args
        return torch.zeros_like(value)


class DenoiseToZero:
    def __call__(self, value, sigma, **extra_args):
        del sigma, extra_args
        return torch.zeros_like(value)


def main() -> None:
    source_root = Path(sys.argv[1]).resolve()
    advanced_path = source_root / "comfy_extras" / "nodes_advanced_samplers.py"
    ar_node_path = source_root / "comfy_extras" / "nodes_ar_video.py"
    sampling_path = source_root / "comfy" / "k_diffusion" / "sampling.py"

    factory = RecordingSamplers()
    upscale_recorder = UpscaleRecorder()
    comfy_stub = types.SimpleNamespace(
        samplers=factory,
        utils=upscale_recorder,
        model_patcher=types.SimpleNamespace(
            set_model_options_post_cfg_function=lambda options, function, **kwargs: {
                **options,
                "post_cfg_function": function,
                **kwargs,
            }
        ),
    )
    advanced_ns = {
        "np": np,
        "torch": torch,
        "trange": quiet_range,
        "comfy": comfy_stub,
        "io": _IO,
        "to_d": lambda value, sigma, denoised: (value - denoised) / sigma,
    }
    execute_definitions(
        advanced_path,
        {
            "sample_lcm_upscale",
            "sample_euler_pp",
            "SamplerLCMUpscale",
            "SamplerLCM",
            "SamplerEulerCFGpp",
        },
        advanced_ns,
    )

    euler_regular = advanced_ns["SamplerEulerCFGpp"].execute("regular")[0]
    euler_alternative = advanced_ns["SamplerEulerCFGpp"].execute("alternative")[0]
    lcm_constructor = advanced_ns["SamplerLCM"].execute("1.0", "0.25", "2.5")[0]
    upscale_auto = advanced_ns["SamplerLCMUpscale"].execute(2.0, -1, "bislerp")[0]
    upscale_explicit = advanced_ns["SamplerLCMUpscale"].execute(1.5, 3, "bicubic")[0]

    ar_ns = {"torch": torch, "comfy": comfy_stub, "io": _IO}
    execute_definitions(ar_node_path, {"SamplerARVideo"}, ar_ns)
    ar_constructor = ar_ns["SamplerARVideo"].execute(3)[0]

    wrapper_calls: list[dict] = []

    def euler_ancestral_stub(model, value, sigmas, **kwargs):
        del model, value, sigmas
        wrapper_calls.append(kwargs)
        return torch.tensor([17.0])

    sampling_ns = {
        "torch": torch,
        "trange": quiet_range,
        "default_noise_sampler": lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("an explicit noise_sampler was supplied")
        ),
        "sample_euler_ancestral_cfg_pp": euler_ancestral_stub,
    }
    execute_definitions(
        sampling_path,
        {"sample_lcm", "sample_euler_cfg_pp", "sample_ar_video"},
        sampling_ns,
    )

    euler_wrapper_result = sampling_ns["sample_euler_cfg_pp"](
        object(),
        torch.tensor([1.0]),
        torch.tensor([1.0, 0.0]),
        extra_args={"seed": 9},
        callback=None,
        disable=True,
    )

    interpolation_scaling = LCMNoiseScaling()
    sampling_ns["sample_lcm"](
        LCMModel(interpolation_scaling),
        torch.zeros((1, 1, 2, 2)),
        torch.tensor([3.0, 2.0, 1.0, 0.0]),
        noise_sampler=lambda sigma, sigma_next: torch.ones((1, 1, 2, 2)),
        s_noise=1.0,
        s_noise_end=3.0,
        noise_clip_std=0.0,
        disable=True,
    )

    raw_clip_noise = torch.tensor([[[[-10.0, -1.0], [1.0, 10.0]]]])
    clipping_scaling = LCMNoiseScaling()
    sampling_ns["sample_lcm"](
        LCMModel(clipping_scaling),
        torch.zeros_like(raw_clip_noise),
        torch.tensor([2.0, 1.0, 0.0]),
        noise_sampler=lambda sigma, sigma_next: raw_clip_noise.clone(),
        s_noise=1.0,
        s_noise_end=1.0,
        noise_clip_std=0.5,
        disable=True,
    )
    expected_clip = float(0.5 * raw_clip_noise.std())

    constant_scaling = LCMNoiseScaling()
    sampling_ns["sample_lcm"](
        LCMModel(constant_scaling),
        torch.zeros((1, 1, 2, 2)),
        torch.tensor([2.0, 1.0, 0.0]),
        noise_sampler=lambda sigma, sigma_next: torch.ones((1, 1, 2, 2)),
        s_noise=0.5,
        s_noise_end=None,
        noise_clip_std=0.0,
        disable=True,
    )

    sigmas = torch.tensor([3.0, 2.0, 1.0, 0.0])
    upscale_recorder.calls.clear()
    auto_result = advanced_ns["sample_lcm_upscale"](
        DenoiseToZero(),
        torch.zeros((1, 1, 3, 4)),
        sigmas,
        total_upscale=2.0,
        upscale_method="bislerp",
        upscale_steps=None,
        disable=True,
    )
    auto_calls = list(upscale_recorder.calls)
    upscale_recorder.calls.clear()
    explicit_result = advanced_ns["sample_lcm_upscale"](
        DenoiseToZero(),
        torch.zeros((1, 1, 3, 4)),
        sigmas,
        total_upscale=2.0,
        upscale_method="bicubic",
        upscale_steps=1,
        disable=True,
    )
    explicit_calls = list(upscale_recorder.calls)

    try:
        sampling_ns["sample_ar_video"](
            None,
            torch.zeros((1, 4, 8, 8)),
            torch.tensor([1.0, 0.0]),
            disable=True,
        )
    except ValueError as error:
        ar_rank_error = str(error)
    else:
        raise AssertionError("sample_ar_video accepted a 4-D latent")

    unsupported_model = types.SimpleNamespace(
        inner_model=types.SimpleNamespace(
            inner_model=types.SimpleNamespace(diffusion_model=object())
        )
    )
    try:
        sampling_ns["sample_ar_video"](
            unsupported_model,
            torch.zeros((1, 4, 2, 8, 8)),
            torch.tensor([1.0, 0.0]),
            disable=True,
        )
    except TypeError as error:
        ar_interface_error = str(error)
    else:
        raise AssertionError("sample_ar_video accepted a model without the cache interface")

    print(
        json.dumps(
            {
                "constructors": {
                    "eulerRegular": euler_regular,
                    "eulerAlternative": euler_alternative,
                    "lcm": lcm_constructor,
                    "lcmUpscaleAuto": upscale_auto,
                    "lcmUpscaleExplicit": upscale_explicit,
                    "arVideo": ar_constructor,
                },
                "eulerWrapper": {
                    "result": float(euler_wrapper_result[0]),
                    "forwarded": wrapper_calls,
                },
                "lcmAlgorithm": {
                    "interpolatedNoiseMeans": [
                        float(call["noise"].mean()) for call in interpolation_scaling.calls
                    ],
                    "interpolatedSigmas": [
                        call["sigma"] for call in interpolation_scaling.calls
                    ],
                    "constantNoiseMeans": [
                        float(call["noise"].mean()) for call in constant_scaling.calls
                    ],
                    "clippedMaximum": float(
                        clipping_scaling.calls[0]["noise"].abs().max()
                    ),
                    "expectedClip": expected_clip,
                },
                "upscaleAlgorithm": {
                    "autoCalls": auto_calls,
                    "autoResultShape": list(auto_result.shape),
                    "explicitCalls": explicit_calls,
                    "explicitResultShape": list(explicit_result.shape),
                },
                "arValidation": {
                    "rankError": ar_rank_error,
                    "interfaceError": ar_interface_error,
                },
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
