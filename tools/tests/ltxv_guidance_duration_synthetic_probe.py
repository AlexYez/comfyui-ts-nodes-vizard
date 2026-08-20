from __future__ import annotations

import ast
import importlib.util
import json
import logging
import math
import re
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import torch


ROOT = Path(__file__).resolve().parents[2]
NODES_SOURCE = ROOT / ".comfyui-source-0.32.0" / "comfy_extras" / "nodes_lt.py"
DURATION_SOURCE = ROOT / ".comfyui-source-0.32.0" / "comfy" / "ldm" / "lightricks" / "duration_head.py"


class DummyNodeOutput:
    def __init__(self, *values: object) -> None:
        self.values = values


class DummyComfyNode:
    pass


class DummyCFGGuider:
    def __init__(self, model: object) -> None:
        self.model_patcher = model
        self.original_conds: dict[str, object] = {}
        self.cfg = 1.0
        self.sample_calls: list[dict[str, object]] = []
        self.predict_calls: list[dict[str, object]] = []

    def inner_set_conds(self, conds: dict[str, object]) -> None:
        self.original_conds = conds

    def sample(self, noise: object, latent_image: object, *args: object, **kwargs: object) -> str:
        self.sample_calls.append({"noise": noise, "latent": latent_image, "args": args, "kwargs": kwargs})
        return "sampled"

    def predict_noise(
        self,
        x: torch.Tensor,
        timestep: torch.Tensor,
        model_options: dict[str, object] | None = None,
        seed: int | None = None,
    ) -> dict[str, object]:
        options = {} if model_options is None else model_options
        call: dict[str, object] = {"cfg": self.cfg, "model_options": options, "seed": seed}
        function = options.get("sampler_cfg_function")
        if callable(function):
            cond = torch.ones_like(x)
            uncond = torch.zeros_like(x)
            call["dual_cfg"] = function({"cond": cond, "uncond": uncond})
        self.predict_calls.append(call)
        return call


class SamplersProbe:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []
        self.next_prediction = torch.tensor([[[1.0, 1.0]]])

    def calc_cond_batch(
        self,
        model: object,
        conds: list[object],
        x: torch.Tensor,
        sigma: torch.Tensor,
        model_options: dict[str, object],
    ) -> tuple[torch.Tensor]:
        self.calls.append({
            "model": model,
            "conds": conds,
            "x": x,
            "sigma": sigma,
            "model_options": model_options,
        })
        return (self.next_prediction.clone(),)


class SamplingProbe:
    @staticmethod
    def percent_to_sigma(percent: float) -> float:
        return 10.0 * (1.0 - percent)


class ModelProbe:
    def __init__(self, callbacks: list[object] | None = None) -> None:
        self.callbacks = list(callbacks or [])
        self.model_options: dict[str, object] = {
            "sampler_post_cfg_function": self.callbacks,
            "transformer_options": {"keep": "original"},
        }
        self.sampling = SamplingProbe()
        self.clone_parent: ModelProbe | None = None

    def clone(self) -> "ModelProbe":
        result = ModelProbe(self.callbacks)
        result.clone_parent = self
        return result

    def get_model_object(self, name: str) -> object:
        if name != "model_sampling":
            raise AssertionError(name)
        return self.sampling

    def set_model_sampler_post_cfg_function(self, callback: object) -> None:
        self.callbacks = self.callbacks + [callback]
        self.model_options["sampler_post_cfg_function"] = self.callbacks


class NestedProbe:
    is_nested = True

    def __init__(self, parts: list[torch.Tensor]) -> None:
        self.parts = parts

    def unbind(self) -> list[torch.Tensor]:
        return self.parts


class FlatProbe:
    is_nested = False


class ModelManagementProbe:
    def __init__(self) -> None:
        self.load_calls: list[list[object]] = []

    def load_models_gpu(self, models: list[object]) -> None:
        self.load_calls.append(models)


def load_duration_module() -> Any:
    spec = importlib.util.spec_from_file_location("exact_ltxv_duration_head", DURATION_SOURCE)
    if spec is None or spec.loader is None:
        raise AssertionError("duration_head module cannot be loaded")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def extract_classes(samplers_probe: SamplersProbe, model_management: ModelManagementProbe, duration_module: Any) -> dict[str, type]:
    tree = ast.parse(NODES_SOURCE.read_text(encoding="utf-8"))
    wanted = {
        "LTXVSpatioTemporalGuidance",
        "LTXVModalityGuidance",
        "Guider_LTXAVDualCFG",
        "LTXVDualCFGGuider",
        "LTXVDurationPredictor",
    }
    selected = [node for node in tree.body if isinstance(node, ast.ClassDef) and node.name in wanted]
    found = {node.name for node in selected}
    if found != wanted:
        raise AssertionError(f"missing exact classes: {sorted(wanted - found)}")

    io = SimpleNamespace(ComfyNode=DummyComfyNode, NodeOutput=DummyNodeOutput)
    comfy = SimpleNamespace(
        samplers=SimpleNamespace(CFGGuider=DummyCFGGuider, calc_cond_batch=samplers_probe.calc_cond_batch),
        model_management=model_management,
        ldm=SimpleNamespace(lightricks=SimpleNamespace(duration_head=duration_module)),
    )
    namespace: dict[str, object] = {
        "io": io,
        "comfy": comfy,
        "torch": torch,
        "math": math,
        "re": re,
        "logging": logging,
    }
    exec(compile(ast.Module(body=selected, type_ignores=[]), str(NODES_SOURCE), "exec"), namespace)
    return {name: namespace[name] for name in wanted}  # type: ignore[return-value]


def callback_args(sigma: float) -> dict[str, object]:
    return {
        "sigma": torch.tensor([sigma]),
        "cond_denoised": torch.tensor([[[4.0, 4.0]]]),
        "cond": [{"prompt": "positive"}],
        "denoised": torch.tensor([[[2.0, 2.0]]]),
        "model_options": {"transformer_options": {"keep": "callback"}},
        "input": torch.tensor([[[9.0, 9.0]]]),
        "model": object(),
    }


def probe_guidance(classes: dict[str, type], samplers_probe: SamplersProbe) -> dict[str, object]:
    base = ModelProbe()
    modality_output = classes["LTXVModalityGuidance"].execute(base, 3.0, 0.2, 0.8)
    modality = modality_output.values[0]
    modality_callback = modality.callbacks[-1]
    samplers_probe.next_prediction = torch.tensor([[[1.0, 1.0]]])
    inside = modality_callback(callback_args(5.0))
    modality_options = samplers_probe.calls[-1]["model_options"]
    before_disabled_calls = len(samplers_probe.calls)
    disabled_model = classes["LTXVModalityGuidance"].execute(base, 1.0, 0.0, 1.0).values[0]
    disabled_result = disabled_model.callbacks[-1](callback_args(5.0))
    disabled_avoids_pass = len(samplers_probe.calls) == before_disabled_calls
    before_outside_calls = len(samplers_probe.calls)
    outside_result = modality_callback(callback_args(9.0))
    outside_avoids_pass = len(samplers_probe.calls) == before_outside_calls

    stg_base = ModelProbe()
    stg_output = classes["LTXVSpatioTemporalGuidance"].execute(stg_base, 1.5, "29, 3-5, -7, 29", 0.2, 0.8)
    stg = stg_output.values[0]
    stg_callback = stg.callbacks[-1]
    samplers_probe.next_prediction = torch.tensor([[[1.0, 1.0]]])
    stg_inside = stg_callback(callback_args(5.0))
    stg_options = samplers_probe.calls[-1]["model_options"]
    before_empty_calls = len(samplers_probe.calls)
    empty_blocks_model = classes["LTXVSpatioTemporalGuidance"].execute(stg_base, 1.5, "none", 0.0, 1.0).values[0]
    empty_blocks_result = empty_blocks_model.callbacks[-1](callback_args(5.0))
    empty_blocks_avoid_pass = len(samplers_probe.calls) == before_empty_calls
    before_zero_calls = len(samplers_probe.calls)
    zero_scale_model = classes["LTXVSpatioTemporalGuidance"].execute(stg_base, 0.0, "29", 0.0, 1.0).values[0]
    zero_scale_result = zero_scale_model.callbacks[-1](callback_args(5.0))
    zero_scale_avoids_pass = len(samplers_probe.calls) == before_zero_calls

    stacked_modality = classes["LTXVModalityGuidance"].execute(ModelProbe(), 3.0, 0.0, 1.0).values[0]
    stacked = classes["LTXVSpatioTemporalGuidance"].execute(stacked_modality, 1.0, "29", 0.0, 1.0).values[0]
    return {
        "modality": {
            "sourceUnchanged": len(base.callbacks) == 0,
            "cloneParentIdentity": modality.clone_parent is base,
            "thresholds": [modality.sampling.percent_to_sigma(0.2), modality.sampling.percent_to_sigma(0.8)],
            "insideResult": inside.tolist(),
            "flags": {
                "a2v": modality_options["transformer_options"]["a2v_cross_attn"],
                "v2a": modality_options["transformer_options"]["v2a_cross_attn"],
                "kept": modality_options["transformer_options"]["keep"],
            },
            "callbackOptionsUnchanged": "a2v_cross_attn" not in callback_args(5.0)["model_options"]["transformer_options"],
            "scaleOneIdentity": disabled_result is not None and torch.equal(disabled_result, callback_args(5.0)["denoised"]),
            "scaleOneAvoidsPass": disabled_avoids_pass,
            "outsideIdentity": torch.equal(outside_result, callback_args(9.0)["denoised"]),
            "outsideAvoidsPass": outside_avoids_pass,
        },
        "stg": {
            "sourceUnchanged": len(stg_base.callbacks) == 0,
            "insideResult": stg_inside.tolist(),
            "parsedBlocks": sorted(stg_options["transformer_options"]["stg_self_attn_blocks"]),
            "kept": stg_options["transformer_options"]["keep"],
            "emptyBlocksIdentity": torch.equal(empty_blocks_result, callback_args(5.0)["denoised"]),
            "emptyBlocksAvoidPass": empty_blocks_avoid_pass,
            "zeroScaleIdentity": torch.equal(zero_scale_result, callback_args(5.0)["denoised"]),
            "zeroScaleAvoidsPass": zero_scale_avoids_pass,
        },
        "stackedCallbackCount": len(stacked.callbacks),
    }


def probe_dual_cfg(classes: dict[str, type]) -> dict[str, object]:
    model = object()
    positive = [["positive", {}]]
    negative = [["negative", {}]]
    output = classes["LTXVDualCFGGuider"].execute(model, positive, negative, 3.0, 7.0)
    guider = output.values[0]
    video = torch.zeros((2, 3, 4, 5))
    audio = torch.zeros((2, 6, 7))
    third = torch.zeros((2, 8))
    nested = NestedProbe([video, audio, third])
    sample_result = guider.sample(object(), nested, "sampler", "sigmas", seed=123)
    initial_cfg = guider.cfg
    input_options = {"keep": True}
    prediction = guider.predict_noise(torch.zeros((1, 1, 3 * 4 * 5 + 6 * 7 + 8)), torch.tensor([1.0]), input_options, 99)
    dual = prediction["dual_cfg"]

    equal = classes["LTXVDualCFGGuider"].execute(model, positive, negative, 1.0, 1.0).values[0]
    equal.sample(object(), nested)
    equal_prediction = equal.predict_noise(torch.zeros((1, 1, 8)), torch.tensor([1.0]), {"keep": True}, 1)

    flat = classes["LTXVDualCFGGuider"].execute(model, positive, negative, 2.0, 9.0).values[0]
    flat.sample(object(), FlatProbe())
    flat_prediction = flat.predict_noise(torch.zeros((1, 1, 8)), torch.tensor([1.0]), {"keep": True}, 2)
    return {
        "modelIdentity": guider.model_patcher is model,
        "positiveIdentity": guider.original_conds["positive"] is positive,
        "negativeIdentity": guider.original_conds["negative"] is negative,
        "initialCfgIsMax": initial_cfg == 7.0 == max(guider.video_cfg, guider.audio_cfg),
        "sampleResult": sample_result,
        "videoNumelExcludesBatch": guider._v_numel,
        "dualVideoValues": sorted(set(dual[..., :60].flatten().tolist())),
        "dualTailValues": sorted(set(dual[..., 60:].flatten().tolist())),
        "disableCfgOneOptimization": prediction["model_options"]["disable_cfg1_optimization"],
        "inputOptionsUnchanged": input_options == {"keep": True},
        "equalFallsBack": "dual_cfg" not in equal_prediction and equal_prediction["cfg"] == 1.0,
        "flatFallsBackToVideo": "dual_cfg" not in flat_prediction and flat_prediction["cfg"] == 2.0,
    }


class DiffusionProbe:
    cross_attention_dim = 4

    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    def preprocess_text_embeds(self, context: torch.Tensor, unprocessed: bool = False) -> torch.Tensor:
        self.calls.append({"shape": list(context.shape), "dtype": str(context.dtype), "unprocessed": unprocessed})
        return context * 2


class InferenceModelProbe:
    def __init__(self, diffusion_model: DiffusionProbe) -> None:
        self.diffusion_model = diffusion_model

    @staticmethod
    def get_dtype_inference() -> torch.dtype:
        return torch.float16


class DurationModelProbe:
    def __init__(self, diffusion_model: DiffusionProbe) -> None:
        self.model = InferenceModelProbe(diffusion_model)
        self.load_device = torch.device("cpu")


def probe_duration(classes: dict[str, type], model_management: ModelManagementProbe, duration_module: Any) -> dict[str, object]:
    class ProbeDurationHead(duration_module.DurationHead):
        def __init__(self) -> None:
            torch.nn.Module.__init__(self)
            self.calls: list[dict[str, object]] = []

        def forward(self, video_tokens: torch.Tensor, audio_tokens: torch.Tensor) -> torch.Tensor:
            self.calls.append({
                "videoShape": list(video_tokens.shape),
                "audioShape": list(audio_tokens.shape),
                "videoDtype": str(video_tokens.dtype),
                "audioDtype": str(audio_tokens.dtype),
            })
            return torch.tensor([30.0], device=video_tokens.device)

    diffusion = DiffusionProbe()
    model = DurationModelProbe(diffusion)
    head = ProbeDurationHead()
    duration_patch = SimpleNamespace(model=head)
    context = torch.arange(2 * 3 * 6, dtype=torch.float32).reshape(2, 3, 6)
    positive = [
        [context, {"unprocessed_ltxav_embeds": True, "keep": "first"}],
        [torch.zeros((1, 1, 6)), {"keep": "ignored"}],
    ]
    output = classes["LTXVDurationPredictor"].execute(model, positive, duration_patch, 24.0, 1.0, 20.0)
    wrong_patch_rejected = False
    before_wrong_loads = len(model_management.load_calls)
    try:
        classes["LTXVDurationPredictor"].execute(
            model,
            positive,
            SimpleNamespace(model=object()),
            24.0,
            1.0,
            20.0,
        )
    except ValueError:
        wrong_patch_rejected = True

    deterministic_head = duration_module.DurationHead(
        video_cross_attention_dim=4,
        audio_cross_attention_dim=2,
        pooler_hidden_dim=4,
        num_queries=1,
        num_pooler_heads=1,
        mlp_hidden=4,
    )
    with torch.no_grad():
        for parameter in deterministic_head.parameters():
            parameter.zero_()
    deterministic_seconds = deterministic_head(torch.zeros((1, 2, 4)), torch.zeros((1, 3, 2)))
    no_tokens_rejected = False
    try:
        deterministic_head()
    except ValueError:
        no_tokens_rejected = True

    convert = duration_module.seconds_to_num_frames
    return {
        "numFrames": output.values[0],
        "rawSeconds": output.values[1],
        "loadCallUsesBothPatchers": model_management.load_calls[0] == [model, duration_patch],
        "preprocess": diffusion.calls[0],
        "headCall": head.calls[0],
        "wrongPatchRejectedBeforeLoad": wrong_patch_rejected and len(model_management.load_calls) == before_wrong_loads,
        "gridExamples": {
            "belowMin": convert(0.1, 24.0, 1.0, 20.0),
            "inside": convert(2.37, 24.0, 1.0, 20.0),
            "aboveMax": convert(30.0, 24.0, 1.0, 20.0),
            "tightBoundsMayBeOffGrid": convert(0.5, 24.0, 0.5, 0.5),
            "reversedBounds": convert(10.0, 24.0, 20.0, 1.0),
        },
        "zeroWeightsPredictOneSecond": deterministic_seconds.tolist(),
        "noTokensRejected": no_tokens_rejected,
    }


def run() -> dict[str, object]:
    duration_module = load_duration_module()
    samplers_probe = SamplersProbe()
    model_management = ModelManagementProbe()
    classes = extract_classes(samplers_probe, model_management, duration_module)
    return {
        "guidance": probe_guidance(classes, samplers_probe),
        "dualCFG": probe_dual_cfg(classes),
        "duration": probe_duration(classes, model_management, duration_module),
    }


if __name__ == "__main__":
    print(json.dumps(run(), ensure_ascii=False, sort_keys=True))
