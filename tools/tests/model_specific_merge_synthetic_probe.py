from __future__ import annotations

import ast
import json
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any


class _BaseMergeBlocks:
    pass


def _extract_classes(source_root: Path) -> dict[str, type]:
    path = source_root / "comfy_extras" / "nodes_model_merging_model_specific.py"
    tree = ast.parse(path.read_text(encoding="utf-8"))
    wanted = {
        "ModelMergeFlux1", "ModelMergeSD35_Large", "ModelMergeWAN2_1", "ModelMergeLTXV",
        "ModelMergeAuraflow", "ModelMergeMochiPreview", "ModelMergeCosmos7B", "ModelMergeCosmos14B",
        "ModelMergeCosmosPredict2_2B", "ModelMergeCosmosPredict2_14B", "ModelMergeQwenImage", "ModelMergeKrea2",
    }
    body = [
        node for node in tree.body if isinstance(node, ast.ClassDef) and node.name in wanted
    ]
    namespace: dict[str, Any] = {
        "comfy_extras": SimpleNamespace(
            nodes_model_merging=SimpleNamespace(ModelMergeBlocks=_BaseMergeBlocks)
        )
    }
    exec(compile(ast.Module(body=body, type_ignores=[]), str(path), "exec"), namespace)
    return {name: namespace[name] for name in wanted}


def select_ratio(key: str, ordered_kwargs: dict[str, float]) -> tuple[str | None, float]:
    default_ratio = next(iter(ordered_kwargs.values()))
    selected: str | None = None
    ratio = default_ratio
    last_arg_size = 0
    for name, value in ordered_kwargs.items():
        if key.startswith(name) and last_arg_size < len(name):
            selected = name
            ratio = value
            last_arg_size = len(name)
    return selected, ratio


def run_probe(source_root: Path) -> dict[str, Any]:
    classes = _extract_classes(source_root)
    schemas = {
        name: cls.INPUT_TYPES()["required"] for name, cls in classes.items()
    }

    assert list(schemas["ModelMergeFlux1"])[:7] == [
        "model1", "model2", "img_in.", "time_in.", "guidance_in", "vector_in.", "txt_in."
    ]
    assert len([key for key in schemas["ModelMergeFlux1"] if key.startswith("double_blocks.")]) == 19
    assert len([key for key in schemas["ModelMergeFlux1"] if key.startswith("single_blocks.")]) == 38
    assert "final_layer." in schemas["ModelMergeFlux1"]

    assert len([key for key in schemas["ModelMergeSD35_Large"] if key.startswith("joint_blocks.")]) == 38
    assert list(schemas["ModelMergeSD35_Large"])[2:7] == [
        "pos_embed.", "x_embedder.", "context_embedder.", "y_embedder.", "t_embedder."
    ]

    assert len([key for key in schemas["ModelMergeWAN2_1"] if key.startswith("blocks.")]) == 40
    assert "img_emb." in schemas["ModelMergeWAN2_1"]
    assert "head." in schemas["ModelMergeWAN2_1"]

    assert len([key for key in schemas["ModelMergeLTXV"] if key.startswith("transformer_blocks.")]) == 28
    assert "scale_shift_table" in schemas["ModelMergeLTXV"]
    assert "proj_out." in schemas["ModelMergeLTXV"]

    assert len([key for key in schemas["ModelMergeAuraflow"] if key.startswith("double_layers.")]) == 4
    assert len([key for key in schemas["ModelMergeAuraflow"] if key.startswith("single_layers.")]) == 32
    assert "positional_encoding" in schemas["ModelMergeAuraflow"]
    assert "register_tokens" in schemas["ModelMergeAuraflow"]
    assert len([key for key in schemas["ModelMergeMochiPreview"] if key.startswith("blocks.")]) == 48
    assert len([key for key in schemas["ModelMergeCosmos7B"] if key.startswith("blocks.block")]) == 28
    assert len([key for key in schemas["ModelMergeCosmos14B"] if key.startswith("blocks.block")]) == 36
    assert "affline_norm." in schemas["ModelMergeCosmos7B"]
    assert len([key for key in schemas["ModelMergeCosmosPredict2_2B"] if key.startswith("blocks.")]) == 28
    assert len([key for key in schemas["ModelMergeCosmosPredict2_14B"] if key.startswith("blocks.")]) == 36
    assert list(schemas["ModelMergeCosmosPredict2_2B"])[2:6] == [
        "pos_embedder.", "x_embedder.", "t_embedder.", "t_embedding_norm."
    ]
    assert len([key for key in schemas["ModelMergeQwenImage"] if key.startswith("transformer_blocks.")]) == 60
    assert list(schemas["ModelMergeQwenImage"])[2:7] == [
        "pos_embeds.", "img_in.", "txt_norm.", "txt_in.", "time_text_embed."
    ]
    assert len([key for key in schemas["ModelMergeKrea2"] if key.startswith("blocks.")]) == 28
    assert len([key for key in schemas["ModelMergeKrea2"] if key.startswith("txtfusion.layerwise_blocks.")]) == 2
    assert len([key for key in schemas["ModelMergeKrea2"] if key.startswith("txtfusion.refiner_blocks.")]) == 2
    assert "txtfusion.projector." in schemas["ModelMergeKrea2"]

    flux_kwargs = {
        key: (0.25 if key == "double_blocks.0." else 1.0)
        for key in list(schemas["ModelMergeFlux1"])[2:]
    }
    selected, ratio = select_ratio("double_blocks.0.attn.to_q.weight", flux_kwargs)
    assert selected == "double_blocks.0." and ratio == 0.25
    selected, ratio = select_ratio("double_blocks.10.attn.to_q.weight", flux_kwargs)
    assert selected == "double_blocks.10." and ratio == 1.0
    selected, ratio = select_ratio("unlisted_norm.weight", flux_kwargs)
    assert selected is None and ratio == 1.0

    ltxv_kwargs = {
        key: (0.4 if key == "scale_shift_table" else 1.0)
        for key in list(schemas["ModelMergeLTXV"])[2:]
    }
    selected, ratio = select_ratio("scale_shift_table", ltxv_kwargs)
    assert selected == "scale_shift_table" and ratio == 0.4
    selected, ratio = select_ratio("scale_shift_table_extra", ltxv_kwargs)
    assert selected == "scale_shift_table" and ratio == 0.4

    common = ("FLOAT", {"default": 1.0, "min": 0.0, "max": 1.0, "step": 0.01})
    for required in schemas.values():
        for name, definition in required.items():
            if name not in {"model1", "model2"}:
                assert definition == common

    return {
        "ModelMergeFlux1": {"ratioInputs": len(schemas["ModelMergeFlux1"]) - 2, "double": 19, "single": 38},
        "ModelMergeSD35_Large": {"ratioInputs": len(schemas["ModelMergeSD35_Large"]) - 2, "joint": 38},
        "ModelMergeWAN2_1": {"ratioInputs": len(schemas["ModelMergeWAN2_1"]) - 2, "blocks": 40, "hasImageEmbedding": True},
        "ModelMergeLTXV": {"ratioInputs": len(schemas["ModelMergeLTXV"]) - 2, "transformerBlocks": 28, "barePrefixMatch": True},
        "ModelMergeAuraflow": {"ratioInputs": len(schemas["ModelMergeAuraflow"]) - 2, "double": 4, "single": 32},
        "ModelMergeMochiPreview": {"ratioInputs": len(schemas["ModelMergeMochiPreview"]) - 2, "blocks": 48},
        "ModelMergeCosmos7B": {"ratioInputs": len(schemas["ModelMergeCosmos7B"]) - 2, "blocks": 28},
        "ModelMergeCosmos14B": {"ratioInputs": len(schemas["ModelMergeCosmos14B"]) - 2, "blocks": 36},
        "ModelMergeCosmosPredict2_2B": {"ratioInputs": len(schemas["ModelMergeCosmosPredict2_2B"]) - 2, "blocks": 28},
        "ModelMergeCosmosPredict2_14B": {"ratioInputs": len(schemas["ModelMergeCosmosPredict2_14B"]) - 2, "blocks": 36},
        "ModelMergeQwenImage": {"ratioInputs": len(schemas["ModelMergeQwenImage"]) - 2, "blocks": 60},
        "ModelMergeKrea2": {
            "ratioInputs": len(schemas["ModelMergeKrea2"]) - 2,
            "blocks": 28,
            "layerwise": 2,
            "refiner": 2,
        },
        "prefixSelection": {"exactIndexedPrefix": True, "unmatchedUsesFirstRatio": True},
    }


if __name__ == "__main__":
    root = Path(sys.argv[1] if len(sys.argv) > 1 else ".comfyui-source-0.32.0")
    print(json.dumps(run_probe(root), ensure_ascii=False, sort_keys=True))
