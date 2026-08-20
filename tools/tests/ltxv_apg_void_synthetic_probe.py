from __future__ import annotations

import ast
import json
import math
from pathlib import Path
from types import SimpleNamespace
from typing import Optional, Tuple

import torch
import torch.nn as nn
import torch.nn.functional as F
from einops import rearrange


ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / ".comfyui-source-0.32.0"
LTX_NODE_SOURCE = SOURCE / "comfy_extras" / "nodes_lt_upsampler.py"
LTX_MODEL_SOURCE = SOURCE / "comfy" / "ldm" / "lightricks" / "latent_upsampler.py"
MINIMAX_NODE_SOURCE = SOURCE / "comfy_extras" / "nodes_minimax_h3.py"
MODEL_SAMPLING_SOURCE = SOURCE / "comfy" / "model_sampling.py"
MINIMAX_MODEL_SOURCE = SOURCE / "comfy" / "ldm" / "minimax" / "model.py"
APG_SOURCE = SOURCE / "comfy_extras" / "nodes_apg.py"
VOID_SOURCE = SOURCE / "comfy_extras" / "nodes_void.py"


class DummyNodeOutput:
    def __init__(self, *values: object) -> None:
        self.values = values


class DummyComfyNode:
    pass


class DummySchema:
    def __init__(self, **kwargs: object) -> None:
        self.kwargs = kwargs


class DummySampler:
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
    Schema=DummySchema,
    Latent=DummyType,
    LatentUpscaleModel=DummyType,
    Vae=DummyType,
    Model=DummyType,
    Float=DummyType,
    Sampler=DummyType,
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


class TrackingStatistics:
    def __init__(self) -> None:
        self.calls: list[tuple[str, torch.dtype, tuple[int, ...]]] = []

    def un_normalize(self, value: torch.Tensor) -> torch.Tensor:
        self.calls.append(("un_normalize", value.dtype, tuple(value.shape)))
        return value + 10.0

    def normalize(self, value: torch.Tensor) -> torch.Tensor:
        self.calls.append(("normalize", value.dtype, tuple(value.shape)))
        return value - 10.0


class RepeatSpatialModel:
    def __init__(self) -> None:
        self.seen: list[tuple[torch.dtype, torch.device, tuple[int, ...]]] = []

    def __call__(self, value: torch.Tensor) -> torch.Tensor:
        self.seen.append((value.dtype, value.device, tuple(value.shape)))
        return value.repeat_interleave(2, dim=-2).repeat_interleave(2, dim=-1)


class DummyUpscalePatcher:
    def __init__(self) -> None:
        self.load_device = torch.device("cpu")
        self.model = RepeatSpatialModel()

    def model_dtype(self) -> torch.dtype:
        return torch.float64


class DummyModelConfig:
    sampling_settings = {"shift": 12.0, "audio_shift": 3.0, "noise_scale": 1.0}


class DummyMiniMaxModel:
    def __init__(self, original_sampling: object, model_options: dict[str, object] | None = None) -> None:
        self._original_sampling = original_sampling
        self.model = SimpleNamespace(model_config=DummyModelConfig())
        self.model_options = model_options or {"transformer_options": {"kept": "yes"}, "other": 7}
        self.patches: dict[str, object] = {}

    def clone(self) -> "DummyMiniMaxModel":
        transformer = dict(self.model_options.get("transformer_options", {}))
        copied = dict(self.model_options)
        copied["transformer_options"] = transformer
        return DummyMiniMaxModel(self._original_sampling, copied)

    def get_model_object(self, name: str) -> object:
        assert name == "model_sampling"
        return self._original_sampling

    def add_object_patch(self, name: str, value: object) -> None:
        self.patches[name] = value


class DummyAPGModel:
    def __init__(self, marker: str = "original") -> None:
        self.marker = marker
        self.pre_cfg: object | None = None

    def clone(self) -> "DummyAPGModel":
        return DummyAPGModel("clone")

    def set_model_sampler_pre_cfg_function(self, function: object) -> None:
        self.pre_cfg = function


def run_ltx_probe() -> dict[str, object]:
    memory_calls: list[tuple[list[object], float]] = []
    model_management = SimpleNamespace(
        load_models_gpu=lambda models, memory_required: memory_calls.append((models, memory_required)),
        intermediate_device=lambda: torch.device("cpu"),
    )
    definitions = extract(
        LTX_NODE_SOURCE,
        classes={"LTXVLatentUpsampler"},
        namespace={"IO": IO, "math": math, "model_management": model_management},
    )
    node = definitions["LTXVLatentUpsampler"]
    source_tensor = torch.arange(2 * 3 * 4 * 5 * 6, dtype=torch.float32).reshape(2, 3, 4, 5, 6)
    noise_mask = torch.ones(2, 4, 5, 6)
    metadata = {"nested": ["preserved"]}
    samples = {
        "samples": source_tensor,
        "noise_mask": noise_mask,
        "batch_index": torch.tensor([9, 10]),
        "metadata": metadata,
    }
    patcher = DummyUpscalePatcher()
    statistics = TrackingStatistics()
    vae = SimpleNamespace(first_stage_model=SimpleNamespace(per_channel_statistics=statistics))
    result = node.execute(samples, patcher, vae).values[0]

    assert result is not samples
    assert result["samples"].shape == (2, 3, 4, 10, 12)
    assert result["samples"].dtype == source_tensor.dtype
    assert result["metadata"] is metadata
    assert result["batch_index"] is samples["batch_index"]
    assert "noise_mask" not in result and samples["noise_mask"] is noise_mask
    assert patcher.model.seen == [(torch.float64, torch.device("cpu"), (2, 3, 4, 5, 6))]
    assert statistics.calls == [
        ("un_normalize", torch.float64, (2, 3, 4, 5, 6)),
        ("normalize", torch.float64, (2, 3, 4, 10, 12)),
    ]
    expected_memory = math.prod(source_tensor.shape) * 3000.0
    assert memory_calls == [([patcher], expected_memory)]

    model_definitions = extract(
        LTX_MODEL_SOURCE,
        functions={"_rational_for_scale"},
        classes={"PixelShuffleND", "BlurDownsample", "SpatialRationalResampler", "ResBlock", "LatentUpsampler"},
        namespace={
            "Optional": Optional,
            "Tuple": Tuple,
            "torch": torch,
            "nn": nn,
            "F": F,
            "rearrange": rearrange,
        },
    )
    operations = SimpleNamespace(Conv2d=nn.Conv2d, Conv3d=nn.Conv3d, GroupNorm=nn.GroupNorm)
    latent_model = model_definitions["LatentUpsampler"](
        operations=operations,
        in_channels=1,
        mid_channels=32,
        num_blocks_per_stage=0,
        dims=2,
        spatial_upsample=True,
        temporal_upsample=False,
        spatial_scale=2.0,
        rational_resampler=False,
    )
    synthetic = torch.randn(1, 1, 2, 3, 4)
    synthetic_output = latent_model(synthetic)
    assert synthetic_output.shape == (1, 1, 2, 6, 8)

    return {
        "inputShape": list(source_tensor.shape),
        "outputShape": list(result["samples"].shape),
        "outputDtype": str(result["samples"].dtype),
        "modelInputDtype": str(patcher.model.seen[0][0]),
        "memoryRequired": memory_calls[0][1],
        "statisticsCalls": [[name, str(dtype), list(shape)] for name, dtype, shape in statistics.calls],
        "noiseMaskRemovedFromCopyOnly": "noise_mask" not in result and "noise_mask" in samples,
        "metadataIdentityPreserved": result["metadata"] is metadata,
        "exactModelSyntheticShape": list(synthetic_output.shape),
    }


def run_minimax_probe() -> dict[str, object]:
    sampling = extract(
        MODEL_SAMPLING_SOURCE,
        functions={"reshape_sigma", "time_snr_shift"},
        classes={"CONST", "ModelSamplingDiscreteFlow", "ModelSamplingAV"},
        namespace={"torch": torch},
    )
    comfy = SimpleNamespace(
        model_sampling=SimpleNamespace(
            CONST=sampling["CONST"],
            ModelSamplingAV=sampling["ModelSamplingAV"],
        )
    )
    node_definitions = extract(
        MINIMAX_NODE_SOURCE,
        classes={"MiniMaxH3SigmaShift"},
        namespace={"io": IO, "comfy": comfy},
    )
    original_sampling = SimpleNamespace(noise_scale=2.5)
    original = DummyMiniMaxModel(original_sampling)
    result = node_definitions["MiniMaxH3SigmaShift"].execute(original, 12.0, 3.0).values[0]
    patched = result.patches["model_sampling"]
    assert result is not original
    assert patched.shift == 12.0 and patched.audio_shift == 3.0
    assert patched.audio_scale == 4.0 and patched.noise_scale == 2.5
    assert patched.sigmas.shape == (1000,)
    assert result.model_options["transformer_options"] == {
        "kept": "yes",
        "minimax_h3_sigma_shift_video": 12.0,
        "minimax_h3_sigma_shift_audio": 3.0,
    }
    assert original.model_options["transformer_options"] == {"kept": "yes"}

    minimax = extract(
        MINIMAX_MODEL_SOURCE,
        functions={"time_shift_sigma"},
        namespace={"torch": torch},
    )
    base = torch.tensor([0.1, 0.5, 0.9])
    video = sampling["time_snr_shift"](12.0, base)
    audio_direct = sampling["time_snr_shift"](3.0, base)
    audio_from_video = minimax["time_shift_sigma"](video, 12.0, 3.0)
    assert torch.allclose(audio_from_video, audio_direct)
    equal_shift = minimax["time_shift_sigma"](video, 12.0, 12.0)
    assert torch.allclose(equal_shift, video)

    return {
        "shiftVideo": patched.shift,
        "shiftAudio": patched.audio_shift,
        "audioScale": patched.audio_scale,
        "noiseScalePreserved": patched.noise_scale,
        "sigmaMin": float(patched.sigma_min),
        "sigmaMax": float(patched.sigma_max),
        "base": base.tolist(),
        "videoSigmas": video.tolist(),
        "audioSigmas": audio_direct.tolist(),
        "audioMappingMatches": torch.allclose(audio_from_video, audio_direct),
        "equalShiftsAreIdentity": torch.allclose(equal_shift, video),
        "originalTransformerOptionsUnchanged": original.model_options["transformer_options"] == {"kept": "yes"},
    }


def run_apg_probe() -> dict[str, object]:
    definitions = extract(
        APG_SOURCE,
        functions={"project"},
        classes={"APG"},
        namespace={"torch": torch, "io": IO},
    )
    model = DummyAPGModel()
    patched_model = definitions["APG"].execute(model, 1.0, 0.0, 0.0).values[0]
    assert patched_model is not model and patched_model.pre_cfg is not None
    hook = patched_model.pre_cfg

    cond = torch.tensor([[[[2.0, 1.0], [0.0, -1.0]]]])
    uncond = torch.tensor([[[[0.5, -0.5], [0.5, 0.0]]]])
    cfg = 4.0
    returned = hook(
        {"conds_out": [cond, uncond], "sigma": torch.tensor([1.0]), "cond_scale": cfg}
    )
    standard_cfg_after_hook = uncond + (returned[0] - uncond) * cfg
    guidance = cond - uncond
    expected = cond + cfg * guidance
    assert torch.allclose(standard_cfg_after_hook, expected)
    assert not torch.allclose(standard_cfg_after_hook, uncond + cfg * guidance)

    singleton = [cond]
    assert hook({"conds_out": singleton, "sigma": torch.tensor([0.9]), "cond_scale": 1.0}) is singleton

    clipped_model = definitions["APG"].execute(model, 0.0, 1.0, 0.0).values[0]
    clipped_hook = clipped_model.pre_cfg
    large_cond = torch.tensor([[[[10.0, 0.0], [0.0, 0.0]]]])
    clipped = clipped_hook(
        {"conds_out": [large_cond, torch.zeros_like(large_cond)], "sigma": torch.tensor([1.0]), "cond_scale": 2.0}
    )
    assert torch.isfinite(clipped[0]).all()

    momentum_model = definitions["APG"].execute(model, 1.0, 0.0, -0.5).values[0]
    momentum_hook = momentum_model.pre_cfg
    g1 = torch.ones(1, 1, 2, 2)
    first = momentum_hook(
        {"conds_out": [g1, torch.zeros_like(g1)], "sigma": torch.tensor([1.0]), "cond_scale": 2.0}
    )[0]
    g2 = torch.full_like(g1, 2.0)
    second = momentum_hook(
        {"conds_out": [g2, torch.zeros_like(g2)], "sigma": torch.tensor([0.5]), "cond_scale": 2.0}
    )[0]
    reset = momentum_hook(
        {"conds_out": [g2, torch.zeros_like(g2)], "sigma": torch.tensor([1.5]), "cond_scale": 2.0}
    )[0]
    assert torch.allclose(first, torch.full_like(first, 1.5))
    assert torch.allclose(second, torch.full_like(second, 2.5))
    assert torch.allclose(reset, torch.full_like(reset, 3.0))

    zero_cfg_model = definitions["APG"].execute(model, 1.0, 0.0, 0.0).values[0]
    zero_cfg = zero_cfg_model.pre_cfg(
        {"conds_out": [cond, uncond], "sigma": torch.tensor([1.0]), "cond_scale": 0.0}
    )[0]
    assert not torch.isfinite(zero_cfg).all()

    vector = torch.tensor([[[[3.0, 4.0], [0.0, 0.0]]]])
    reference = torch.tensor([[[[1.0, 0.0], [0.0, 0.0]]]])
    parallel, orthogonal = definitions["project"](vector, reference)
    assert torch.allclose(parallel + orthogonal, vector)
    assert torch.allclose(parallel, torch.tensor([[[[3.0, 0.0], [0.0, 0.0]]]]))

    return {
        "etaOneNoModifiersStandardCfg": standard_cfg_after_hook.tolist(),
        "etaOneNoModifiersExpectedCondPlusCfgGuidance": expected.tolist(),
        "ordinaryCfgWouldBe": (uncond + cfg * guidance).tolist(),
        "singleConditionBypassed": True,
        "reverseMomentumFirstSecondReset": [
            float(first.flatten()[0]),
            float(second.flatten()[0]),
            float(reset.flatten()[0]),
        ],
        "cfgZeroIsFinite": bool(torch.isfinite(zero_cfg).all()),
        "projectionReconstructs": bool(torch.allclose(parallel + orthogonal, vector)),
    }


def run_void_probe() -> dict[str, object]:
    comfy = SimpleNamespace(samplers=SimpleNamespace(Sampler=DummySampler))
    definitions = extract(
        VOID_SOURCE,
        classes={"VOID_DDIM", "VOIDSampler"},
        namespace={"torch": torch, "trange": lambda count, disable=False: range(count), "comfy": comfy, "io": IO},
    )
    sampler = definitions["VOIDSampler"].execute().values[0]
    assert isinstance(sampler, definitions["VOID_DDIM"])

    calls: list[dict[str, object]] = []
    callbacks: list[tuple[int, int]] = []

    def model_wrap(value: torch.Tensor, sigma: torch.Tensor, *, model_options: object, seed: object) -> torch.Tensor:
        calls.append(
            {
                "value": value.clone(),
                "sigma": sigma.clone(),
                "model_options": model_options,
                "seed": seed,
            }
        )
        return value * 0.25 + 0.125

    def callback(step: int, denoised: torch.Tensor, value: torch.Tensor, total: int) -> None:
        callbacks.append((step, total))

    noise = torch.tensor([[[[[1.0, -1.0]]]]], dtype=torch.float64)
    sigmas = torch.tensor([2.0, 1.0, 0.5, 0.0], dtype=torch.float32)
    model_options = {"marker": "forwarded"}
    result = sampler.sample(
        model_wrap,
        sigmas,
        {"model_options": model_options, "seed": 123},
        callback,
        noise,
        latent_image=object(),
        denoise_mask=object(),
        disable_pbar=True,
    )

    manual = noise.to(torch.float32)
    for index in range(len(sigmas) - 1):
        sigma = sigmas[index]
        sigma_next = sigmas[index + 1]
        denoised = manual * 0.25 + 0.125
        if sigma_next == 0:
            manual = denoised
        else:
            alpha_t = 1.0 / (1.0 + sigma**2)
            alpha_prev = 1.0 / (1.0 + sigma_next**2)
            pred_eps = (manual - alpha_t**0.5 * denoised) / (1.0 - alpha_t) ** 0.5
            manual = alpha_prev**0.5 * denoised + (1.0 - alpha_prev) ** 0.5 * pred_eps
    assert torch.allclose(result, manual)
    assert result.dtype == torch.float32
    assert callbacks == [(0, 3), (1, 3), (2, 3)]
    assert len(calls) == 3
    assert all(call["model_options"] is model_options and call["seed"] == 123 for call in calls)

    one_call_count = len(calls)
    one_sigma = sampler.sample(
        model_wrap,
        torch.tensor([1.0]),
        {},
        None,
        noise,
        latent_image=object(),
        denoise_mask=object(),
        disable_pbar=True,
    )
    one_sigma_skipped_model = len(calls) == one_call_count
    assert one_sigma_skipped_model
    assert torch.equal(one_sigma, noise.to(torch.float32))

    final = sampler.sample(
        model_wrap,
        torch.tensor([1.0, 0.0]),
        {},
        None,
        noise,
        disable_pbar=True,
    )
    assert torch.allclose(final, noise.to(torch.float32) * 0.25 + 0.125)

    return {
        "dtype": str(result.dtype),
        "steps": len(sigmas) - 1,
        "callbackRecords": callbacks,
        "matchesManualAlphaUpdate": bool(torch.allclose(result, manual)),
        "oneSigmaSkipsModel": one_sigma_skipped_model,
        "oneSigmaOutput": one_sigma.tolist(),
        "terminalZeroReturnsDenoised": bool(torch.allclose(final, noise.to(torch.float32) * 0.25 + 0.125)),
        "latentAndMaskAcceptedButUnused": True,
    }


def run() -> dict[str, object]:
    return {
        "ltxvLatentUpsampler": run_ltx_probe(),
        "miniMaxH3SigmaShift": run_minimax_probe(),
        "apg": run_apg_probe(),
        "voidSampler": run_void_probe(),
    }


if __name__ == "__main__":
    print(json.dumps(run(), ensure_ascii=False, sort_keys=True))
