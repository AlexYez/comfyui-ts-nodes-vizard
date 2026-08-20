from __future__ import annotations

import ast
import json
import sys
from pathlib import Path
from types import SimpleNamespace


class DummyNodeOutput:
    def __init__(self, *values: object) -> None:
        self.values = values


class DummyComfyNode:
    pass


IO = SimpleNamespace(ComfyNode=DummyComfyNode, NodeOutput=DummyNodeOutput)


def extract_definitions(
    path: Path,
    *,
    functions: set[str] = frozenset(),
    classes: set[str] = frozenset(),
    namespace: dict[str, object],
) -> dict[str, object]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
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


class ModelStub:
    def __init__(self, marker: str = "original") -> None:
        self.marker = marker
        self.pre_cfg = None

    def clone(self) -> "ModelStub":
        return ModelStub("clone")

    def set_model_sampler_pre_cfg_function(self, function: object) -> None:
        self.pre_cfg = function


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit(
            "usage: latent_operation_apply_synthetic_probe.py <pinned-comfyui-source>"
        )

    source = Path(sys.argv[1]).resolve()
    import torch

    gaussian = extract_definitions(
        source / "comfy_extras" / "nodes_post_processing.py",
        functions={"gaussian_kernel"},
        namespace={"torch": torch},
    )["gaussian_kernel"]
    comfy_extras = SimpleNamespace(
        nodes_post_processing=SimpleNamespace(gaussian_kernel=gaussian)
    )
    definitions = extract_definitions(
        source / "comfy_extras" / "nodes_latent.py",
        classes={
            "LatentApplyOperation",
            "LatentApplyOperationCFG",
            "LatentOperationTonemapReinhard",
            "LatentOperationSharpen",
        },
        namespace={"torch": torch, "io": IO, "comfy_extras": comfy_extras},
    )

    apply_node = definitions["LatentApplyOperation"]
    marker = {"kept": [1, 2, 3]}
    original_tensor = torch.arange(16, dtype=torch.float32).reshape(1, 1, 4, 4)
    call_record: dict[str, object] = {}

    def add_three(*, latent: torch.Tensor) -> torch.Tensor:
        call_record["latent"] = latent
        return latent + 3

    source_latent = {
        "samples": original_tensor,
        "noise_mask": torch.ones(1, 4, 4),
        "metadata": marker,
    }
    applied = apply_node.execute(source_latent, add_three).values[0]
    assert applied is not source_latent
    assert applied["samples"] is not original_tensor
    assert torch.equal(applied["samples"], original_tensor + 3)
    assert call_record["latent"] is original_tensor
    assert applied["metadata"] is marker
    assert applied["noise_mask"] is source_latent["noise_mask"]
    assert source_latent["samples"] is original_tensor

    cfg_node = definitions["LatentApplyOperationCFG"]
    model = ModelStub()
    patched = cfg_node.execute(model, lambda *, latent: latent * 2).values[0]
    assert patched is not model and patched.marker == "clone"
    assert model.pre_cfg is None and callable(patched.pre_cfg)

    two = [torch.tensor([30.0]), torch.tensor([10.0])]
    two_returned = patched.pre_cfg({"conds_out": two})
    assert two_returned is two
    assert two[0].item() == 50.0 and two[1].item() == 10.0

    one = [torch.tensor([7.0])]
    one_returned = patched.pre_cfg({"conds_out": one})
    assert one_returned is one and one[0].item() == 14.0

    three = [torch.tensor([2.0]), torch.tensor([3.0]), torch.tensor([4.0])]
    three_returned = patched.pre_cfg({"conds_out": three})
    assert three_returned is three
    assert [item.item() for item in three] == [4.0, 3.0, 4.0]

    tonemap_node = definitions["LatentOperationTonemapReinhard"]
    tonemap = tonemap_node.execute(1.0).values[0]
    latent = torch.tensor(
        [[[[3.0, 0.0], [4.0, 12.0]], [[4.0, 5.0], [3.0, 5.0]]]],
        dtype=torch.float32,
    )
    tonemapped = tonemap(latent=latent)
    before_norm = torch.linalg.vector_norm(latent, dim=1)
    after_norm = torch.linalg.vector_norm(tonemapped, dim=1)
    before_direction = latent / (before_norm[:, None] + 1e-10)
    after_direction = tonemapped / (after_norm[:, None] + 1e-10)
    assert torch.isfinite(tonemapped).all()
    assert torch.allclose(before_direction, after_direction, atol=1e-5, rtol=1e-5)
    assert torch.all(after_norm <= before_norm + 1e-5)

    multiplier_zero = tonemap_node.execute(0.0).values[0](latent=latent)
    assert not torch.isfinite(multiplier_zero).all()
    singleton = tonemap_node.execute(1.0).values[0](
        latent=torch.ones(1, 4, 1, 1)
    )
    assert not torch.isfinite(singleton).all()

    sharpen_node = definitions["LatentOperationSharpen"]
    sharpen_identity = sharpen_node.execute(2, 1.0, 0.0).values[0]
    sharpen_input = torch.randn(1, 4, 8, 9)
    identity_output = sharpen_identity(latent=sharpen_input)
    assert identity_output.shape == sharpen_input.shape
    assert torch.allclose(identity_output, sharpen_input, atol=2e-5, rtol=2e-5)

    sharpen = sharpen_node.execute(2, 1.0, 0.1).values[0]
    sharpened = sharpen(latent=sharpen_input)
    assert sharpened.shape == sharpen_input.shape
    assert torch.isfinite(sharpened).all()
    assert not torch.allclose(sharpened, sharpen_input)

    reflect_error = ""
    try:
        sharpen(latent=torch.ones(1, 4, 2, 5))
    except RuntimeError as exc:
        reflect_error = str(exc)
    assert reflect_error

    rank_error = ""
    try:
        sharpen(latent=torch.ones(1, 4, 2, 8, 8))
    except RuntimeError as exc:
        rank_error = str(exc)
    assert rank_error

    print(
        json.dumps(
            {
                "apply": {
                    "samplesReplaced": applied["samples"] is not original_tensor,
                    "metadataIdentityPreserved": applied["metadata"] is marker,
                    "operationReceivedOriginalTensor": call_record["latent"] is original_tensor,
                },
                "cfg": {
                    "cloneReturned": patched is not model,
                    "twoConditionResult": [item.item() for item in two],
                    "singleConditionResult": [item.item() for item in one],
                    "threeConditionResult": [item.item() for item in three],
                    "sameListsReturned": two_returned is two
                    and one_returned is one
                    and three_returned is three,
                },
                "tonemap": {
                    "directionPreserved": bool(
                        torch.allclose(before_direction, after_direction, atol=1e-5, rtol=1e-5)
                    ),
                    "normsNotIncreased": bool(torch.all(after_norm <= before_norm + 1e-5)),
                    "multiplierZeroFinite": bool(torch.isfinite(multiplier_zero).all()),
                    "singletonFinite": bool(torch.isfinite(singleton).all()),
                },
                "sharpen": {
                    "alphaZeroIdentity": bool(
                        torch.allclose(identity_output, sharpen_input, atol=2e-5, rtol=2e-5)
                    ),
                    "shape": list(sharpened.shape),
                    "changesValues": not torch.allclose(sharpened, sharpen_input),
                    "smallSpatialRejected": bool(reflect_error),
                    "fiveDimensionalRejected": bool(rank_error),
                },
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
