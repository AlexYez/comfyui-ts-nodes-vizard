from __future__ import annotations

import ast
import json
import logging
from pathlib import Path
from types import SimpleNamespace

import torch


ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / ".comfyui-source-0.32.0"


def load_merge_classes() -> dict[str, type]:
    tree = ast.parse(
        (SOURCE / "comfy_extras" / "nodes_model_merging.py").read_text(encoding="utf-8")
    )
    names = {"CLIPMergeSimple", "CLIPSubtract", "CLIPAdd"}
    selected = [
        node
        for node in tree.body
        if isinstance(node, ast.ClassDef) and node.name in names
    ]
    if {node.name for node in selected} != names:
        raise AssertionError("pinned merge classes were not found")
    namespace: dict[str, object] = {}
    exec(
        compile(ast.Module(body=selected, type_ignores=[]), "nodes_model_merging.py", "exec"),
        namespace,
    )
    return {name: namespace[name] for name in names}  # type: ignore[return-value]


class DummyNodeOutput:
    def __init__(self, *values: object) -> None:
        self.values = values


def load_attention_class() -> type:
    tree = ast.parse(
        (SOURCE / "comfy_extras" / "nodes_attention_multiply.py").read_text(
            encoding="utf-8"
        )
    )
    selected = next(
        node
        for node in tree.body
        if isinstance(node, ast.ClassDef) and node.name == "CLIPAttentionMultiply"
    )
    io = SimpleNamespace(
        ComfyNode=object,
        Schema=object,
        NodeOutput=DummyNodeOutput,
    )
    namespace: dict[str, object] = {"io": io}
    exec(
        compile(ast.Module(body=[selected], type_ignores=[]), "nodes_attention_multiply.py", "exec"),
        namespace,
    )
    return namespace["CLIPAttentionMultiply"]  # type: ignore[return-value]


class RecordingMergeClip:
    def __init__(self, name: str, patches: dict[str, object] | None = None) -> None:
        self.name = name
        self.patches = patches or {}
        self.added: list[dict[str, object]] = []
        self.tokenizer = object()

    def clone(self) -> "RecordingMergeClip":
        clone = RecordingMergeClip(f"clone:{self.name}")
        clone.tokenizer = self.tokenizer
        return clone

    def get_key_patches(self) -> dict[str, object]:
        return self.patches

    def add_patches(
        self,
        patches: dict[str, object],
        strength_patch: float,
        strength_model: float,
    ) -> None:
        self.added.append(
            {
                "patches": patches,
                "strength_patch": strength_patch,
                "strength_model": strength_model,
            }
        )


class RecordingPatcher:
    def __init__(self, state_dict: dict[str, torch.Tensor]) -> None:
        self.state_dict = state_dict

    def model_state_dict(self) -> dict[str, torch.Tensor]:
        return self.state_dict


class RecordingAttentionClip:
    def __init__(self, state_dict: dict[str, torch.Tensor]) -> None:
        self.patcher = RecordingPatcher(state_dict)
        self.added: list[dict[str, object]] = []
        self.tokenizer = object()

    def clone(self) -> "RecordingAttentionClip":
        clone = RecordingAttentionClip(self.patcher.state_dict)
        clone.tokenizer = self.tokenizer
        return clone

    def add_patches(
        self,
        patches: dict[str, object],
        strength_patch: float,
        strength_model: float,
    ) -> None:
        self.added.append(
            {
                "patches": patches,
                "strength_patch": strength_patch,
                "strength_model": strength_model,
            }
        )


def load_calculate_weight():
    tree = ast.parse((SOURCE / "comfy" / "lora.py").read_text(encoding="utf-8"))
    selected = next(
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name == "calculate_weight"
    )

    class DummyWeightAdapterBase:
        pass

    def cast_to_device(
        value: torch.Tensor,
        device: torch.device,
        dtype: torch.dtype,
        copy: bool = False,
    ) -> torch.Tensor:
        result = value.to(device=device, dtype=dtype)
        return result.clone() if copy else result

    namespace: dict[str, object] = {
        "torch": torch,
        "logging": logging,
        "comfy": SimpleNamespace(
            model_management=SimpleNamespace(cast_to_device=cast_to_device)
        ),
        "weight_adapter": SimpleNamespace(WeightAdapterBase=DummyWeightAdapterBase),
        "pad_tensor_to_shape": lambda value, shape: value,
    }
    exec(compile(ast.Module(body=[selected], type_ignores=[]), "comfy/lora.py", "exec"), namespace)
    return namespace["calculate_weight"]


def run() -> dict[str, object]:
    classes = load_merge_classes()
    source_patches = {
        "encoder.layer.weight": ("layer",),
        "encoder.layer.bias": ("bias",),
        "encoder.position_ids": ("position",),
        "encoder.logit_scale": ("logit",),
    }
    clip1 = RecordingMergeClip("clip1")
    clip2 = RecordingMergeClip("clip2", source_patches)

    simple = classes["CLIPMergeSimple"]().merge(clip1, clip2, 0.25)[0]
    added = classes["CLIPAdd"]().merge(clip1, clip2)[0]
    subtracted = classes["CLIPSubtract"]().merge(clip1, clip2, 2.0)[0]
    for result in (simple, added, subtracted):
        assert result is not clip1
        assert result.tokenizer is clip1.tokenizer
        assert {next(iter(call["patches"])) for call in result.added} == {
            "encoder.layer.weight",
            "encoder.layer.bias",
        }
    assert {
        (call["strength_patch"], call["strength_model"])
        for call in simple.added
    } == {(0.75, 0.25)}
    assert {
        (call["strength_patch"], call["strength_model"])
        for call in added.added
    } == {(1.0, 1.0)}
    assert {
        (call["strength_patch"], call["strength_model"])
        for call in subtracted.added
    } == {(-2.0, 2.0)}

    calculate_weight = load_calculate_weight()
    first = torch.tensor([2.0, 4.0])
    second = torch.tensor([10.0, 20.0])
    key_patches = [(second, lambda value, **_: value)]
    simple_weight = calculate_weight(
        [(0.75, key_patches, 0.25, None, None)], first.clone(), "weight"
    )
    add_weight = calculate_weight(
        [(1.0, key_patches, 1.0, None, None)], first.clone(), "weight"
    )
    subtract_weight = calculate_weight(
        [(-2.0, key_patches, 2.0, None, None)], first.clone(), "weight"
    )
    attention_weight = calculate_weight(
        [(0.0, (None,), 1.5, None, None)], first.clone(), "weight"
    )
    assert torch.equal(simple_weight, torch.tensor([8.0, 16.0]))
    assert torch.equal(add_weight, torch.tensor([12.0, 24.0]))
    assert torch.equal(subtract_weight, torch.tensor([-16.0, -32.0]))
    assert torch.equal(attention_weight, torch.tensor([3.0, 6.0]))

    state_dict: dict[str, torch.Tensor] = {}
    for projection in ("q", "k", "v"):
        for suffix in ("weight", "bias"):
            state_dict[f"text.layers.0.self_attn.{projection}_proj.{suffix}"] = first
    for suffix in ("weight", "bias"):
        state_dict[f"text.layers.0.self_attn.out_proj.{suffix}"] = first
    state_dict["text.layers.0.cross_attn.q_proj.weight"] = first
    state_dict["text.layers.0.mlp.fc1.weight"] = first

    attention_clip = RecordingAttentionClip(state_dict)
    output = load_attention_class().execute(
        attention_clip, q=0.5, k=1.5, v=2.0, out=0.0
    ).values[0]
    assert output is not attention_clip
    assert output.tokenizer is attention_clip.tokenizer
    calls = {
        next(iter(call["patches"])): (
            call["strength_patch"],
            call["strength_model"],
            next(iter(call["patches"].values())),
        )
        for call in output.added
    }
    assert len(calls) == 8
    assert "text.layers.0.cross_attn.q_proj.weight" not in calls
    assert "text.layers.0.mlp.fc1.weight" not in calls
    for key, (strength_patch, strength_model, patch_value) in calls.items():
        assert strength_patch == 0.0
        assert patch_value == (None,)
        expected = {
            "q_proj": 0.5,
            "k_proj": 1.5,
            "v_proj": 2.0,
            "out_proj": 0.0,
        }
        assert strength_model == next(
            value for marker, value in expected.items() if marker in key
        )

    return {
        "mergeSimple": {
            "coefficients": [0.25, 0.75],
            "weight": simple_weight.tolist(),
            "skippedKeys": ["encoder.position_ids", "encoder.logit_scale"],
        },
        "mergeAdd": {"coefficients": [1.0, 1.0], "weight": add_weight.tolist()},
        "mergeSubtract": {
            "coefficients": [2.0, -2.0],
            "weight": subtract_weight.tolist(),
        },
        "attentionMultiply": {
            "matchedKeys": len(calls),
            "factors": {"q": 0.5, "k": 1.5, "v": 2.0, "out": 0.0},
            "weightAtFactor1_5": attention_weight.tolist(),
        },
    }


if __name__ == "__main__":
    print(json.dumps(run(), ensure_ascii=False, sort_keys=True))
