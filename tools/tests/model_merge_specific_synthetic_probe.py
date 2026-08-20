from __future__ import annotations

import ast
import json
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import torch

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from tools.tests.model_merge_synthetic_probe import (
    _FakeModel,
    _extract_calculate_weight,
)


TARGET_CLASSES = {"ModelMergeSD1", "ModelMergeSDXL", "ModelMergeSD3_2B"}


def _extract_specific_classes(source_root: Path) -> dict[str, type]:
    common_path = source_root / "comfy_extras" / "nodes_model_merging.py"
    common_tree = ast.parse(common_path.read_text(encoding="utf-8"))
    common_node = next(
        node
        for node in common_tree.body
        if isinstance(node, ast.ClassDef) and node.name == "ModelMergeBlocks"
    )
    common_namespace: dict[str, Any] = {}
    exec(
        compile(ast.Module(body=[common_node], type_ignores=[]), str(common_path), "exec"),
        common_namespace,
    )

    specific_path = source_root / "comfy_extras" / "nodes_model_merging_model_specific.py"
    specific_tree = ast.parse(specific_path.read_text(encoding="utf-8"))
    specific_nodes = [
        node
        for node in specific_tree.body
        if isinstance(node, ast.ClassDef) and node.name in TARGET_CLASSES
    ]
    namespace: dict[str, Any] = {
        "comfy_extras": SimpleNamespace(
            nodes_model_merging=SimpleNamespace(
                ModelMergeBlocks=common_namespace["ModelMergeBlocks"]
            )
        )
    }
    exec(
        compile(ast.Module(body=specific_nodes, type_ignores=[]), str(specific_path), "exec"),
        namespace,
    )
    return {name: namespace[name] for name in TARGET_CLASSES}


def _default_ratios(node_class: type) -> dict[str, float]:
    required = node_class.INPUT_TYPES()["required"]
    return {
        name: float(spec[1]["default"])
        for name, spec in required.items()
        if name not in {"model1", "model2"}
    }


def _merge(
    node_class: type,
    model1_weights: dict[str, torch.Tensor],
    model2_weights: dict[str, torch.Tensor],
    calculate_weight: Any,
    updates: dict[str, float],
) -> _FakeModel:
    ratios = _default_ratios(node_class)
    ratios.update(updates)
    model1 = _FakeModel(model1_weights, calculate_weight)
    model2 = _FakeModel(model2_weights, calculate_weight)
    return node_class().merge(model1, model2, **ratios)[0]


def run_probe(source_root: Path) -> dict[str, Any]:
    calculate_weight = _extract_calculate_weight(source_root)
    classes = _extract_specific_classes(source_root)

    sd1_keys = {
        "time": "diffusion_model.time_embed.0.weight",
        "input1": "diffusion_model.input_blocks.1.0.weight",
        "input10": "diffusion_model.input_blocks.10.0.weight",
        "middle": "diffusion_model.middle_block.1.weight",
        "out": "diffusion_model.out.0.weight",
        "unmatched": "diffusion_model.extra_norm.weight",
        "only1": "diffusion_model.only_model1.weight",
    }
    sd1_model1 = {
        sd1_keys["time"]: torch.tensor([2.0]),
        sd1_keys["input1"]: torch.tensor([4.0]),
        sd1_keys["input10"]: torch.tensor([6.0]),
        sd1_keys["middle"]: torch.tensor([8.0]),
        sd1_keys["out"]: torch.tensor([10.0]),
        sd1_keys["unmatched"]: torch.tensor([12.0]),
        sd1_keys["only1"]: torch.tensor([14.0]),
    }
    sd1_model2 = {
        sd1_keys["time"]: torch.tensor([20.0]),
        sd1_keys["input1"]: torch.tensor([40.0]),
        sd1_keys["input10"]: torch.tensor([60.0]),
        sd1_keys["middle"]: torch.tensor([80.0]),
        sd1_keys["out"]: torch.tensor([100.0]),
        sd1_keys["unmatched"]: torch.tensor([120.0]),
        "diffusion_model.only_model2.weight": torch.tensor([160.0]),
    }
    sd1 = _merge(
        classes["ModelMergeSD1"],
        sd1_model1,
        sd1_model2,
        calculate_weight,
        {
            "time_embed.": 0.25,
            "input_blocks.1.": 0.75,
            "input_blocks.10.": 0.5,
            "middle_block.1.": 0.0,
            "out.": 1.0,
        },
    )
    torch.testing.assert_close(sd1.weights[sd1_keys["time"]], torch.tensor([15.5]))
    torch.testing.assert_close(sd1.weights[sd1_keys["input1"]], torch.tensor([13.0]))
    torch.testing.assert_close(sd1.weights[sd1_keys["input10"]], torch.tensor([33.0]))
    torch.testing.assert_close(sd1.weights[sd1_keys["middle"]], torch.tensor([80.0]))
    torch.testing.assert_close(sd1.weights[sd1_keys["out"]], torch.tensor([10.0]))
    torch.testing.assert_close(sd1.weights[sd1_keys["unmatched"]], torch.tensor([93.0]))
    torch.testing.assert_close(sd1.weights[sd1_keys["only1"]], torch.tensor([14.0]))
    assert "diffusion_model.only_model2.weight" not in sd1.weights

    sdxl_input = "diffusion_model.input_blocks.8.1.weight"
    sdxl_incompatible_index = "diffusion_model.input_blocks.10.0.weight"
    sdxl_unmatched = "diffusion_model.extra.weight"
    sdxl = _merge(
        classes["ModelMergeSDXL"],
        {
            sdxl_input: torch.tensor([3.0]),
            sdxl_incompatible_index: torch.tensor([7.0]),
            sdxl_unmatched: torch.tensor([5.0]),
        },
        {
            sdxl_input: torch.tensor([30.0]),
            sdxl_incompatible_index: torch.tensor([70.0]),
            sdxl_unmatched: torch.tensor([50.0]),
        },
        calculate_weight,
        {"time_embed.": 0.4, "input_blocks.1": 0.75, "input_blocks.8": 0.2},
    )
    torch.testing.assert_close(sdxl.weights[sdxl_input], torch.tensor([24.6]))
    torch.testing.assert_close(
        sdxl.weights[sdxl_incompatible_index],
        torch.tensor([22.75]),
    )
    torch.testing.assert_close(sdxl.weights[sdxl_unmatched], torch.tensor([32.0]))

    sd3_joint = "diffusion_model.joint_blocks.23.attn.weight"
    sd3_final = "diffusion_model.final_layer.linear.weight"
    sd3_unmatched = "diffusion_model.extra.weight"
    sd3 = _merge(
        classes["ModelMergeSD3_2B"],
        {
            sd3_joint: torch.tensor([4.0]),
            sd3_final: torch.tensor([6.0]),
            sd3_unmatched: torch.tensor([8.0]),
        },
        {
            sd3_joint: torch.tensor([40.0]),
            sd3_final: torch.tensor([60.0]),
            sd3_unmatched: torch.tensor([80.0]),
        },
        calculate_weight,
        {"pos_embed.": 0.3, "joint_blocks.23.": 0.8, "final_layer.": 0.1},
    )
    torch.testing.assert_close(sd3.weights[sd3_joint], torch.tensor([11.2]))
    torch.testing.assert_close(sd3.weights[sd3_final], torch.tensor([54.6]))
    torch.testing.assert_close(sd3.weights[sd3_unmatched], torch.tensor([58.4]))

    reordered_unmatched = "diffusion_model.reordered_extra.weight"
    reordered_model1 = _FakeModel(
        {reordered_unmatched: torch.tensor([10.0])},
        calculate_weight,
    )
    reordered_model2 = _FakeModel(
        {reordered_unmatched: torch.tensor([100.0])},
        calculate_weight,
    )
    # The common implementation does not look up a named fallback. It takes
    # the first value in the actual kwargs order. A nonstandard caller can
    # therefore change the fallback by reordering otherwise valid fields.
    reordered = classes["ModelMergeSD1"]().merge(
        reordered_model1,
        reordered_model2,
        **{"out.": 0.1, "time_embed.": 0.9},
    )[0]
    torch.testing.assert_close(
        reordered.weights[reordered_unmatched],
        torch.tensor([91.0]),
    )

    shape_key = "diffusion_model.middle_block.0.weight"
    mismatch = _merge(
        classes["ModelMergeSDXL"],
        {shape_key: torch.tensor([2.0, 4.0])},
        {shape_key: torch.tensor([10.0, 20.0, 30.0])},
        calculate_weight,
        {"middle_block.0": 0.25},
    )
    torch.testing.assert_close(mismatch.weights[shape_key], torch.tensor([0.5, 1.0]))

    mismatch_ratio_one = _merge(
        classes["ModelMergeSDXL"],
        {shape_key: torch.tensor([2.0, 4.0])},
        {shape_key: torch.tensor([10.0, 20.0, 30.0])},
        calculate_weight,
        {"middle_block.0": 1.0},
    )
    torch.testing.assert_close(
        mismatch_ratio_one.weights[shape_key],
        torch.tensor([2.0, 4.0]),
    )

    return {
        "sd1": {
            "inputBlock1": float(sd1.weights[sd1_keys["input1"]][0]),
            "inputBlock10": float(sd1.weights[sd1_keys["input10"]][0]),
            "unmatchedUsesTimeEmbed": float(sd1.weights[sd1_keys["unmatched"]][0]),
            "model1OnlyUnchanged": float(sd1.weights[sd1_keys["only1"]][0]),
            "model2OnlyIgnored": True,
        },
        "sdxl": {
            "inputBlock8": float(sdxl.weights[sdxl_input][0]),
            "incompatibleInputBlock10UsesBlock1": float(
                sdxl.weights[sdxl_incompatible_index][0]
            ),
            "unmatchedUsesTimeEmbed": float(sdxl.weights[sdxl_unmatched][0]),
        },
        "sd3": {
            "jointBlock23": float(sd3.weights[sd3_joint][0]),
            "finalLayer": float(sd3.weights[sd3_final][0]),
            "unmatchedUsesPosEmbed": float(sd3.weights[sd3_unmatched][0]),
        },
        "shapeMismatch": mismatch.weights[shape_key].tolist(),
        "shapeMismatchRatioOne": mismatch_ratio_one.weights[shape_key].tolist(),
        "reorderedKwargsUnmatchedUsesFirstValue": float(
            reordered.weights[reordered_unmatched][0]
        ),
        "formula": "ratio*model1+(1-ratio)*model2",
    }


if __name__ == "__main__":
    root = Path(sys.argv[1] if len(sys.argv) > 1 else ".comfyui-source-0.32.0")
    print(json.dumps(run_probe(root), ensure_ascii=False, sort_keys=True))
