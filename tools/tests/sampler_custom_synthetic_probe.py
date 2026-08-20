from __future__ import annotations

import ast
import json
import sys
import types
from pathlib import Path

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
        self.sampler_object_calls: list[str] = []
        self.ksampler_calls: list[tuple[str, dict]] = []

    def sampler_object(self, name):
        self.sampler_object_calls.append(name)
        return {"factory": "sampler_object", "name": name}

    def ksampler(self, name, options):
        self.ksampler_calls.append((name, dict(options)))
        return {"factory": "ksampler", "name": name, "options": dict(options)}


class ProcessModel:
    def __init__(self):
        self.processed: list[torch.Tensor] = []

    def process_latent_out(self, value):
        self.processed.append(value.clone())
        return value + 100


class ModelPatcher:
    def __init__(self):
        self.model = ProcessModel()


class RecordingSample:
    def __init__(self):
        self.prepare_noise_calls: list[tuple[int, object]] = []
        self.sample_custom_calls: list[dict] = []

    @staticmethod
    def fix_empty_latent_channels(model, latent, spatial, temporal):
        assert model is not None
        assert spatial == 8
        assert temporal == 2
        return latent + 1

    def prepare_noise(self, latent, seed, batch_inds):
        self.prepare_noise_calls.append((seed, batch_inds))
        return torch.full_like(latent, 3.0)

    def sample_custom(
        self,
        model,
        noise,
        cfg,
        sampler,
        sigmas,
        positive,
        negative,
        latent_image,
        **kwargs,
    ):
        self.sample_custom_calls.append(
            {
                "model": model,
                "noise": noise.clone(),
                "cfg": cfg,
                "sampler": sampler,
                "sigmas": sigmas.clone(),
                "positive": positive,
                "negative": negative,
                "latent": latent_image.clone(),
                **kwargs,
            }
        )
        kwargs["callback"](0, torch.zeros_like(latent_image), torch.full_like(latent_image, 7.0), 1)
        return latent_image + noise


class Preview:
    @staticmethod
    def prepare_callback(model, steps, x0_output):
        assert steps >= 0

        def callback(step, x0, x, total_steps):
            del step, x0, total_steps
            x0_output["x0"] = x

        return callback


class FixedNoise:
    seed = 77

    def __init__(self):
        self.seen = None

    def generate_noise(self, latent):
        self.seen = latent
        return torch.full_like(latent["samples"], 4.0)


class RecordingGuider:
    def __init__(self):
        self.model_patcher = ModelPatcher()
        self.calls: list[dict] = []

    def sample(self, noise, latent, sampler, sigmas, **kwargs):
        self.calls.append(
            {
                "noise": noise.clone(),
                "latent": latent.clone(),
                "sampler": sampler,
                "sigmas": sigmas.clone(),
                **kwargs,
            }
        )
        kwargs["callback"](0, torch.zeros_like(latent), torch.full_like(latent, 9.0), 1)
        return latent + noise


def load_nodes(source_root: Path):
    samplers = RecordingSamplers()
    sample = RecordingSample()
    comfy = types.SimpleNamespace(
        samplers=samplers,
        sample=sample,
        utils=types.SimpleNamespace(PROGRESS_BAR_ENABLED=True, unpack_latents=lambda x, shapes: [x]),
        nested_tensor=types.SimpleNamespace(NestedTensor=lambda values: values),
        model_management=types.SimpleNamespace(intermediate_device=lambda: torch.device("cpu")),
    )
    namespace = {"torch": torch, "comfy": comfy, "io": _IO, "latent_preview": Preview}
    execute_definitions(
        source_root / "comfy_extras" / "nodes_custom_sampler.py",
        {
            "Noise_EmptyNoise",
            "Noise_RandomNoise",
            "KSamplerSelect",
            "SamplerCustom",
            "SamplerCustomAdvanced",
            "SamplerEulerAncestral",
        },
        namespace,
    )
    return namespace, samplers, sample


def main() -> None:
    source_root = Path(sys.argv[1]).resolve()
    nodes, samplers, sample = load_nodes(source_root)

    selected = nodes["KSamplerSelect"].execute("euler")[0]
    ancestral = nodes["SamplerEulerAncestral"].execute(0.0, 1.25)[0]
    assert selected == {"factory": "sampler_object", "name": "euler"}
    assert ancestral["name"] == "euler_ancestral"
    assert ancestral["options"] == {"eta": 0.0, "s_noise": 1.25}

    model = ModelPatcher()
    source = {
        "samples": torch.zeros(1, 1, 2, 2),
        "noise_mask": torch.ones(1, 1, 2, 2),
        "downscale_ratio_spacial": 8,
        "downscale_ratio_temporal": 2,
        "owner": "input",
    }
    sigmas = torch.tensor([1.0, 0.0])
    output, denoised = nodes["SamplerCustom"].execute(
        model, True, 42, 1.5, "positive", "negative", selected, sigmas, source
    )
    call = sample.sample_custom_calls[-1]
    assert sample.prepare_noise_calls == [(42, None)]
    assert torch.equal(call["noise"], torch.full_like(call["noise"], 3.0))
    assert call["cfg"] == 1.5 and call["seed"] == 42
    assert call["positive"] == "positive" and call["negative"] == "negative"
    assert call["noise_mask"] is source["noise_mask"]
    assert torch.equal(call["latent"], torch.ones_like(call["latent"]))
    assert output["owner"] == "input" and output is not source
    assert "downscale_ratio_spacial" not in output and "downscale_ratio_temporal" not in output
    assert torch.equal(output["samples"], torch.full_like(output["samples"], 4.0))
    assert torch.equal(denoised["samples"], torch.full_like(denoised["samples"], 107.0))
    assert torch.equal(source["samples"], torch.zeros_like(source["samples"]))

    no_noise_output, _ = nodes["SamplerCustom"].execute(
        model, False, 99, 2.0, "p", "n", selected, sigmas, source
    )
    no_noise_call = sample.sample_custom_calls[-1]
    assert torch.count_nonzero(no_noise_call["noise"]) == 0
    assert no_noise_call["seed"] == 99
    assert torch.equal(no_noise_output["samples"], torch.ones_like(no_noise_output["samples"]))

    guider = RecordingGuider()
    fixed = FixedNoise()
    advanced_output, advanced_denoised = nodes["SamplerCustomAdvanced"].execute(
        fixed, guider, ancestral, sigmas, source
    )
    advanced_call = guider.calls[-1]
    assert fixed.seen is not source and fixed.seen["owner"] == "input"
    assert advanced_call["seed"] == 77
    assert advanced_call["denoise_mask"] is source["noise_mask"]
    assert advanced_call["disable_pbar"] is False
    assert torch.equal(advanced_call["latent"], torch.ones_like(advanced_call["latent"]))
    assert torch.equal(advanced_output["samples"], torch.full_like(advanced_output["samples"], 5.0))
    assert torch.equal(advanced_denoised["samples"], torch.full_like(advanced_denoised["samples"], 109.0))

    sampling_source = (source_root / "comfy" / "k_diffusion" / "sampling.py").read_text(encoding="utf-8")
    assert "sigma_down, sigma_up = get_ancestral_step(sigmas[i], sigmas[i + 1], eta=eta)" in sampling_source
    assert "noise_sampler(sigmas[i], sigmas[i + 1]) * s_noise * sigma_up" in sampling_source
    assert "isinstance(model.inner_model.inner_model.model_sampling, comfy.model_sampling.CONST)" in sampling_source

    print(
        json.dumps(
            {
                "factory": {
                    "samplerObjectCalls": samplers.sampler_object_calls,
                    "ksamplerCalls": samplers.ksampler_calls,
                },
                "custom": {
                    "randomSeed": call["seed"],
                    "zeroNoiseSeedStillForwarded": no_noise_call["seed"],
                    "maskForwarded": call["noise_mask"] is source["noise_mask"],
                    "outputValue": float(output["samples"][0, 0, 0, 0]),
                    "x0Value": float(denoised["samples"][0, 0, 0, 0]),
                },
                "advanced": {
                    "noiseSeed": advanced_call["seed"],
                    "maskForwarded": advanced_call["denoise_mask"] is source["noise_mask"],
                    "outputValue": float(advanced_output["samples"][0, 0, 0, 0]),
                    "x0Value": float(advanced_denoised["samples"][0, 0, 0, 0]),
                },
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
