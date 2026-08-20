from __future__ import annotations

import ast
import copy
import json
import sys
import types
from pathlib import Path

import numpy as np
import torch


class _IO:
    ComfyNode = object

    @staticmethod
    def NodeOutput(value):
        return (value,)


def selected_definitions(path: Path, names: set[str]) -> list[ast.stmt]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    return [
        node
        for node in tree.body
        if isinstance(node, (ast.ClassDef, ast.FunctionDef)) and node.name in names
    ]


def execute_definitions(path: Path, names: set[str], namespace: dict):
    module = ast.Module(body=selected_definitions(path, names), type_ignores=[])
    ast.fix_missing_locations(module)
    exec(compile(module, str(path), "exec"), namespace)
    return namespace


def load_noise_classes(source_root: Path):
    sample_path = source_root / "comfy" / "sample.py"
    sample_ns = {
        "torch": torch,
        "np": np,
        "comfy": types.SimpleNamespace(
            nested_tensor=types.SimpleNamespace(NestedTensor=lambda values: values)
        ),
    }
    execute_definitions(sample_path, {"prepare_noise_inner", "prepare_noise"}, sample_ns)

    comfy = types.SimpleNamespace(
        sample=types.SimpleNamespace(prepare_noise=sample_ns["prepare_noise"]),
        nested_tensor=types.SimpleNamespace(NestedTensor=lambda values: values),
    )
    custom_path = source_root / "comfy_extras" / "nodes_custom_sampler.py"
    custom_ns = {"torch": torch, "comfy": comfy, "io": _IO}
    execute_definitions(
        custom_path,
        {"Noise_EmptyNoise", "Noise_RandomNoise", "DisableNoise", "RandomNoise", "AddNoise"},
        custom_ns,
    )

    model_path = source_root / "comfy_extras" / "nodes_model_advanced.py"
    model_ns: dict = {}
    execute_definitions(model_path, {"ModelNoiseScale"}, model_ns)
    return custom_ns, model_ns


class FixedNoise:
    seed = 123

    def __init__(self, value: float):
        self.value = value
        self.seen_latent = None

    def generate_noise(self, latent):
        self.seen_latent = latent
        return torch.full_like(latent["samples"], self.value)


class RecordingSampling:
    def __init__(self):
        self.scales = []

    def noise_scaling(self, scale, noise, latent):
        self.scales.append(float(scale))
        return latent + noise * scale


class AddNoiseModel:
    def __init__(self, sampling):
        self.sampling = sampling
        self.in_calls = 0
        self.out_calls = 0

    def get_model_object(self, name):
        if name == "model_sampling":
            return self.sampling
        if name == "process_latent_in":
            def process(value):
                self.in_calls += 1
                return value + 10
            return process
        if name == "process_latent_out":
            def process(value):
                self.out_calls += 1
                return value * 2
            return process
        raise KeyError(name)


class PatchSampling:
    def __init__(self, model_config):
        self.model_config = model_config
        self.shift = -1
        self.multiplier = -1
        self.noise_scale = float(model_config["initial_noise_scale"])

    def set_parameters(self, shift, multiplier):
        self.shift = shift
        self.multiplier = multiplier

    def set_noise_scale(self, value):
        self.noise_scale = float(value)


class PatchModel:
    def __init__(self, sampling, config):
        self._sampling = sampling
        self.model = types.SimpleNamespace(model_config=config)

    def clone(self):
        return copy.deepcopy(self)

    def get_model_object(self, name):
        assert name == "model_sampling"
        return self._sampling

    def add_object_patch(self, name, value):
        assert name == "model_sampling"
        self._sampling = value


def main() -> None:
    source_root = Path(sys.argv[1]).resolve()
    custom, model_nodes = load_noise_classes(source_root)

    disable = custom["DisableNoise"].execute()[0]
    zeros = disable.generate_noise({"samples": torch.ones(2, 3, 4, 5, dtype=torch.float16)})
    assert disable.seed == 0
    assert zeros.device.type == "cpu"
    assert zeros.dtype == torch.float16
    assert torch.count_nonzero(zeros) == 0

    random_a = custom["RandomNoise"].execute(42)[0]
    random_b = custom["RandomNoise"].execute(42)[0]
    latent = {"samples": torch.zeros(3, 2, 2, 2, dtype=torch.float16)}
    values_a = random_a.generate_noise(latent)
    values_b = random_b.generate_noise(latent)
    assert random_a.seed == 42
    assert values_a.device.type == "cpu" and values_a.dtype == torch.float16
    assert torch.equal(values_a, values_b)

    indexed = random_a.generate_noise(
        {"samples": torch.zeros(3, 2, 2, 2), "batch_index": [0, 0, 2]}
    )
    assert torch.equal(indexed[0], indexed[1])
    assert not torch.equal(indexed[0], indexed[2])

    add = custom["AddNoise"]
    sampling = RecordingSampling()
    add_model = AddNoiseModel(sampling)
    fixed = FixedNoise(2.0)
    source = {"samples": torch.ones(1, 1, 2, 2), "owner": "input"}
    output = add.execute(add_model, fixed, torch.tensor([5.0, 2.0, 0.0]), source)[0]
    assert fixed.seen_latent is source
    assert sampling.scales == [5.0]
    assert add_model.in_calls == 1 and add_model.out_calls == 1
    assert torch.equal(output["samples"], torch.full((1, 1, 2, 2), 42.0))
    assert output["owner"] == "input" and output is not source
    assert torch.equal(source["samples"], torch.ones_like(source["samples"]))

    empty_source = {"samples": torch.zeros(1, 1, 1, 1)}
    empty_out = add.execute(add_model, FixedNoise(1.0), torch.tensor([2.0]), empty_source)[0]
    assert add_model.in_calls == 1
    assert torch.equal(empty_out["samples"], torch.full((1, 1, 1, 1), 4.0))
    assert add.execute(add_model, fixed, torch.tensor([]), source)[0] is source

    original_sampling = PatchSampling({"initial_noise_scale": 8.0})
    original_sampling.set_parameters(shift=3.0, multiplier=1000)
    original = PatchModel(original_sampling, {"initial_noise_scale": 8.0})
    patched = model_nodes["ModelNoiseScale"]().patch(original, 7.6)[0]
    patched_sampling = patched.get_model_object("model_sampling")
    assert patched is not original
    assert patched_sampling is not original_sampling
    assert type(patched_sampling) is type(original_sampling)
    assert (patched_sampling.shift, patched_sampling.multiplier) == (3.0, 1000)
    assert patched_sampling.noise_scale == 7.6
    assert original_sampling.noise_scale == 8.0

    print(
        json.dumps(
            {
                "disable": {
                    "shape": list(zeros.shape),
                    "dtype": str(zeros.dtype),
                    "device": zeros.device.type,
                },
                "random": {
                    "reproducible": bool(torch.equal(values_a, values_b)),
                    "indexedFirstTwoEqual": bool(torch.equal(indexed[0], indexed[1])),
                    "indexedThirdDiffers": bool(not torch.equal(indexed[0], indexed[2])),
                },
                "add": {
                    "multiSigmaScale": sampling.scales[0],
                    "nonzeroValue": float(output["samples"][0, 0, 0, 0]),
                    "emptyValue": float(empty_out["samples"][0, 0, 0, 0]),
                    "emptySigmasIdentity": add.execute(add_model, fixed, torch.tensor([]), source)[0] is source,
                },
                "modelNoiseScale": {
                    "value": patched_sampling.noise_scale,
                    "shift": patched_sampling.shift,
                    "multiplier": patched_sampling.multiplier,
                    "originalUnchanged": original_sampling.noise_scale == 8.0,
                },
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
