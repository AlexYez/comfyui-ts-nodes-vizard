from __future__ import annotations

import ast
import json
import logging
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Callable

import torch


class _WeightAdapterBase:
    pass


def _cast_to_device(
    value: torch.Tensor,
    device: torch.device,
    dtype: torch.dtype,
    copy: bool = False,
) -> torch.Tensor:
    result = value.to(device=device, dtype=dtype)
    return result.clone() if copy else result


def _extract_calculate_weight(source_root: Path) -> Callable[..., torch.Tensor]:
    path = source_root / "comfy" / "lora.py"
    tree = ast.parse(path.read_text(encoding="utf-8"))
    node = next(
        item
        for item in tree.body
        if isinstance(item, ast.FunctionDef) and item.name == "calculate_weight"
    )
    namespace: dict[str, Any] = {
        "torch": torch,
        "logging": logging,
        "comfy": SimpleNamespace(
            model_management=SimpleNamespace(cast_to_device=_cast_to_device)
        ),
        "weight_adapter": SimpleNamespace(WeightAdapterBase=_WeightAdapterBase),
        "pad_tensor_to_shape": lambda value, shape: value,
    }
    exec(compile(ast.Module(body=[node], type_ignores=[]), str(path), "exec"), namespace)
    return namespace["calculate_weight"]


class _FakeModel:
    def __init__(
        self,
        weights: dict[str, torch.Tensor],
        calculate_weight: Callable[..., torch.Tensor],
        *,
        origin: "_FakeModel | None" = None,
    ) -> None:
        self.weights = {key: value.clone() for key, value in weights.items()}
        self.calculate_weight = calculate_weight
        self.origin = origin
        self.requests: list[str | None] = []
        self.patch_calls: list[tuple[str, float, float]] = []

    def clone(self) -> "_FakeModel":
        return _FakeModel(self.weights, self.calculate_weight, origin=self)

    def get_key_patches(self, filter_prefix: str | None = None) -> dict[str, Any]:
        self.requests.append(filter_prefix)
        result: dict[str, Any] = {}
        for key, weight in self.weights.items():
            if filter_prefix is None or key.startswith(filter_prefix):
                result[key] = [(weight.clone(), lambda value, inplace=False: value)]
        return result

    def add_patches(
        self,
        patches: dict[str, Any],
        strength_patch: float = 1.0,
        strength_model: float = 1.0,
    ) -> list[str]:
        accepted: list[str] = []
        for key, patch in patches.items():
            if key not in self.weights:
                continue
            patch_record = (strength_patch, patch, strength_model, None, None)
            self.weights[key] = self.calculate_weight(
                [patch_record], self.weights[key].clone(), key
            )
            self.patch_calls.append((key, float(strength_patch), float(strength_model)))
            accepted.append(key)
        return accepted


def _extract_merge_classes(source_root: Path) -> dict[str, type]:
    path = source_root / "comfy_extras" / "nodes_model_merging.py"
    tree = ast.parse(path.read_text(encoding="utf-8"))
    wanted = {"ModelMergeSimple", "ModelSubtract", "ModelAdd", "ModelMergeBlocks"}
    body = [
        node
        for node in tree.body
        if isinstance(node, ast.ClassDef) and node.name in wanted
    ]
    namespace: dict[str, Any] = {}
    exec(compile(ast.Module(body=body, type_ignores=[]), str(path), "exec"), namespace)
    return {name: namespace[name] for name in wanted}


def run_probe(source_root: Path) -> dict[str, Any]:
    calculate_weight = _extract_calculate_weight(source_root)
    classes = _extract_merge_classes(source_root)

    key_input = "diffusion_model.input_blocks.0.weight"
    key_middle = "diffusion_model.middle_block.0.weight"
    key_output = "diffusion_model.output_blocks.0.weight"
    key_other = "diffusion_model.time_embed.0.weight"
    key_non_diffusion = "clip.weight"
    weights1 = {
        key_input: torch.tensor([2.0]),
        key_middle: torch.tensor([4.0]),
        key_output: torch.tensor([6.0]),
        key_other: torch.tensor([8.0]),
        key_non_diffusion: torch.tensor([100.0]),
    }
    weights2 = {
        key_input: torch.tensor([10.0]),
        key_middle: torch.tensor([20.0]),
        key_output: torch.tensor([30.0]),
        key_other: torch.tensor([40.0]),
        key_non_diffusion: torch.tensor([999.0]),
        "diffusion_model.only_in_model2.weight": torch.tensor([77.0]),
    }

    model1 = _FakeModel(weights1, calculate_weight)
    model2 = _FakeModel(weights2, calculate_weight)
    simple = classes["ModelMergeSimple"]().merge(model1, model2, 0.25)[0]
    assert simple.origin is model1
    torch.testing.assert_close(simple.weights[key_input], torch.tensor([8.0]))
    torch.testing.assert_close(simple.weights[key_middle], torch.tensor([16.0]))
    torch.testing.assert_close(simple.weights[key_non_diffusion], torch.tensor([100.0]))
    assert "diffusion_model.only_in_model2.weight" not in simple.weights
    assert model2.requests[-1] == "diffusion_model."

    added = classes["ModelAdd"]().merge(model1, model2)[0]
    torch.testing.assert_close(added.weights[key_input], torch.tensor([12.0]))
    torch.testing.assert_close(added.weights[key_non_diffusion], torch.tensor([100.0]))

    subtracted = classes["ModelSubtract"]().merge(model1, model2, 2.0)[0]
    torch.testing.assert_close(subtracted.weights[key_input], torch.tensor([-16.0]))
    reversed_delta = classes["ModelSubtract"]().merge(model1, model2, -1.0)[0]
    torch.testing.assert_close(reversed_delta.weights[key_input], torch.tensor([8.0]))

    blocks = classes["ModelMergeBlocks"]().merge(
        model1, model2, input=1.0, middle=0.5, out=0.0
    )[0]
    torch.testing.assert_close(blocks.weights[key_input], torch.tensor([2.0]))
    torch.testing.assert_close(blocks.weights[key_middle], torch.tensor([12.0]))
    torch.testing.assert_close(blocks.weights[key_output], torch.tensor([30.0]))
    torch.testing.assert_close(blocks.weights[key_other], torch.tensor([8.0]))

    reordered = classes["ModelMergeBlocks"]().merge(
        model1, model2, middle=0.5, out=0.0, input=1.0
    )[0]
    torch.testing.assert_close(reordered.weights[key_other], torch.tensor([24.0]))

    shape_model1 = _FakeModel(
        {key_input: torch.tensor([2.0, 4.0])}, calculate_weight
    )
    shape_model2 = _FakeModel(
        {key_input: torch.tensor([10.0, 20.0, 30.0])}, calculate_weight
    )
    mismatched = classes["ModelMergeSimple"]().merge(
        shape_model1, shape_model2, 0.25
    )[0]
    torch.testing.assert_close(mismatched.weights[key_input], torch.tensor([0.5, 1.0]))

    return {
        "simple": {
            "ratioQuarter": float(simple.weights[key_input][0]),
            "formula": "ratio*model1+(1-ratio)*model2",
            "model2OnlyKeyIgnored": True,
            "nonDiffusionUnchanged": True,
        },
        "add": {"result": float(added.weights[key_input][0])},
        "subtract": {
            "multiplierTwo": float(subtracted.weights[key_input][0]),
            "multiplierMinusOne": float(reversed_delta.weights[key_input][0]),
            "formula": "multiplier*(model1-model2)",
        },
        "blocks": {
            "input": float(blocks.weights[key_input][0]),
            "middle": float(blocks.weights[key_middle][0]),
            "out": float(blocks.weights[key_output][0]),
            "unmatchedDefault": float(blocks.weights[key_other][0]),
            "unmatchedReorderedKwargs": float(reordered.weights[key_other][0]),
        },
        "shapeMismatch": {
            "model1AfterRatioScale": mismatched.weights[key_input].tolist()
        },
    }


if __name__ == "__main__":
    root = Path(sys.argv[1] if len(sys.argv) > 1 else ".comfyui-source-0.32.0")
    print(json.dumps(run_probe(root), ensure_ascii=False, sort_keys=True))
