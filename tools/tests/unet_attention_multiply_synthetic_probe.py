from __future__ import annotations

import ast
import json
import logging
import sys
from pathlib import Path
from types import SimpleNamespace

import torch


SOURCE = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else Path(__file__).resolve().parents[2] / ".comfyui-source-0.32.0"


class DummyNodeOutput:
    def __init__(self, *values: object) -> None:
        self.values = values


def load_attention_classes() -> dict[str, type]:
    path = SOURCE / "comfy_extras" / "nodes_attention_multiply.py"
    tree = ast.parse(path.read_text(encoding="utf-8"))
    names = {
        "UNetSelfAttentionMultiply",
        "UNetCrossAttentionMultiply",
        "UNetTemporalAttentionMultiply",
    }
    selected = [
        node
        for node in tree.body
        if (isinstance(node, ast.FunctionDef) and node.name == "attention_multiply")
        or (isinstance(node, ast.ClassDef) and node.name in names)
    ]
    if {node.name for node in selected if isinstance(node, ast.ClassDef)} != names:
        raise AssertionError("pinned attention multiply classes were not found")
    namespace: dict[str, object] = {
        "io": SimpleNamespace(ComfyNode=object, Schema=object, NodeOutput=DummyNodeOutput)
    }
    exec(
        compile(ast.Module(body=selected, type_ignores=[]), str(path), "exec"),
        namespace,
    )
    return {name: namespace[name] for name in names}  # type: ignore[return-value]


def load_calculate_weight():
    path = SOURCE / "comfy" / "lora.py"
    tree = ast.parse(path.read_text(encoding="utf-8"))
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
    exec(
        compile(ast.Module(body=[selected], type_ignores=[]), str(path), "exec"),
        namespace,
    )
    return namespace["calculate_weight"]


class RecordingModel:
    def __init__(
        self,
        state_dict: dict[str, torch.Tensor],
        inherited: list[dict[str, object]] | None = None,
    ) -> None:
        self.state_dict = state_dict
        self.added = list(inherited or [])

    def clone(self) -> "RecordingModel":
        return RecordingModel(self.state_dict, self.added)

    def model_state_dict(self) -> dict[str, torch.Tensor]:
        return self.state_dict

    def add_patches(
        self,
        patches: dict[str, object],
        strength_patch: float,
        strength_model: float,
    ) -> None:
        self.added.append(
            {
                "key": next(iter(patches)),
                "patch": next(iter(patches.values())),
                "strength_patch": strength_patch,
                "strength_model": strength_model,
            }
        )


def projection_state() -> dict[str, torch.Tensor]:
    state: dict[str, torch.Tensor] = {}
    value = torch.tensor([2.0, 4.0])
    for attention in ("attn1", "attn2"):
        for projection in ("to_q", "to_k", "to_v", "to_out.0"):
            for suffix in ("weight", "bias"):
                state[
                    f"diffusion_model.blocks.0.{attention}.{projection}.{suffix}"
                ] = value
    state["diffusion_model.blocks.0.attn10.to_q.weight"] = value
    state["diffusion_model.blocks.0.attn1.to_out.weight"] = value
    state["diffusion_model.blocks.0.ff.net.0.weight"] = value
    return state


def temporal_state() -> dict[str, torch.Tensor]:
    state: dict[str, torch.Tensor] = {}
    value = torch.tensor([2.0, 4.0])
    for attention in ("attn1", "attn2"):
        for prefix in (
            "diffusion_model.blocks.0",
            "diffusion_model.blocks.0.time_stack.1",
        ):
            for suffix in ("weight", "bias"):
                state[f"{prefix}.{attention}.to_out.0.{suffix}"] = value
        state[f"diffusion_model.blocks.0.{attention}.to_q.weight"] = value
        state[f"diffusion_model.blocks.0.{attention}.to_v.bias"] = value
    state["diffusion_model.blocks.0.attn2.to_out.weight"] = value
    return state


def call_map(model: RecordingModel) -> dict[str, dict[str, object]]:
    return {
        str(call["key"]): {
            "patch": call["patch"],
            "strength_patch": call["strength_patch"],
            "strength_model": call["strength_model"],
        }
        for call in model.added
        if "key" in call
    }


def run() -> dict[str, object]:
    classes = load_attention_classes()
    state = projection_state()

    original_self = RecordingModel(state, [{"inherited": True}])
    self_output = classes["UNetSelfAttentionMultiply"].execute(
        original_self, q=0.5, k=1.5, v=2.0, out=0.0
    ).values[0]
    assert self_output is not original_self
    assert len(original_self.added) == 1
    self_calls = call_map(self_output)
    assert len(self_calls) == 8
    assert all(".attn1." in key for key in self_calls)
    assert all(call["patch"] == (None,) for call in self_calls.values())
    assert all(call["strength_patch"] == 0.0 for call in self_calls.values())
    for key, call in self_calls.items():
        expected = {"to_q": 0.5, "to_k": 1.5, "to_v": 2.0, "to_out.0": 0.0}
        call_factor = next(value for marker, value in expected.items() if marker in key)
        assert call["strength_model"] == call_factor

    original_cross = RecordingModel(state)
    cross_output = classes["UNetCrossAttentionMultiply"].execute(
        original_cross, q=0.4, k=0.6, v=0.8, out=1.2
    ).values[0]
    cross_calls = call_map(cross_output)
    assert len(cross_calls) == 8
    assert all(".attn2." in key for key in cross_calls)
    for key, call in cross_calls.items():
        expected = {"to_q": 0.4, "to_k": 0.6, "to_v": 0.8, "to_out.0": 1.2}
        call_factor = next(value for marker, value in expected.items() if marker in key)
        assert call["strength_model"] == call_factor

    original_temporal = RecordingModel(temporal_state())
    temporal_output = classes["UNetTemporalAttentionMultiply"].execute(
        original_temporal,
        self_structural=0.4,
        self_temporal=0.5,
        cross_structural=0.6,
        cross_temporal=0.7,
    ).values[0]
    temporal_calls = call_map(temporal_output)
    assert len(temporal_calls) == 8
    for key, call in temporal_calls.items():
        assert ".to_out.0." in key
        if ".attn1." in key:
            expected = 0.5 if ".time_stack." in key else 0.4
        else:
            expected = 0.7 if ".time_stack." in key else 0.6
        assert call["strength_model"] == expected

    calculate_weight = load_calculate_weight()
    base = torch.tensor([2.0, 4.0])
    scaled = calculate_weight(
        [(0.0, (None,), 1.5, None, None)], base.clone(), "weight"
    )
    zeroed = calculate_weight(
        [(0.0, (None,), 0.0, None, None)], base.clone(), "weight"
    )
    sequential = calculate_weight(
        [
            (0.0, (None,), 0.5, None, None),
            (0.0, (None,), 0.5, None, None),
        ],
        base.clone(),
        "weight",
    )
    assert torch.equal(scaled, torch.tensor([3.0, 6.0]))
    assert torch.equal(zeroed, torch.tensor([0.0, 0.0]))
    assert torch.equal(sequential, torch.tensor([0.5, 1.0]))

    return {
        "self": {"matched": len(self_calls), "factors": sorted({call["strength_model"] for call in self_calls.values()})},
        "cross": {"matched": len(cross_calls), "factors": sorted({call["strength_model"] for call in cross_calls.values()})},
        "temporal": {"matched": len(temporal_calls), "factors": sorted({call["strength_model"] for call in temporal_calls.values()})},
        "weights": {"scaled": scaled.tolist(), "zeroed": zeroed.tolist(), "sequential": sequential.tolist()},
    }


if __name__ == "__main__":
    print(json.dumps(run(), ensure_ascii=False, sort_keys=True))
