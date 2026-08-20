from __future__ import annotations

import ast
import json
import logging
import math
import sys
import types
from pathlib import Path

import torch


class _IO:
    ComfyNode = object

    @staticmethod
    def NodeOutput(value):
        return (value,)


def repeat_to_batch_size(tensor, batch_size, dim=0):
    if tensor.shape[dim] > batch_size:
        return tensor.narrow(dim, 0, batch_size)
    if tensor.shape[dim] < batch_size:
        repeats = dim * [1] + [math.ceil(batch_size / tensor.shape[dim])] + [1] * (len(tensor.shape) - 1 - dim)
        return tensor.repeat(repeats).narrow(dim, 0, batch_size)
    return tensor


def load_classes(source_root: Path):
    path = source_root / "comfy_extras" / "nodes_latent.py"
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    wanted = {"LatentConcat", "LatentCut", "LatentCutToBatch", "ReplaceVideoLatentFrames"}
    selected = [node for node in tree.body if isinstance(node, ast.ClassDef) and node.name in wanted]
    module = ast.Module(body=selected, type_ignores=[])
    ast.fix_missing_locations(module)
    namespace = {
        "io": _IO,
        "nodes": types.SimpleNamespace(MAX_RESOLUTION=16384),
        "torch": torch,
        "math": math,
        "logging": logging,
        "comfy": types.SimpleNamespace(utils=types.SimpleNamespace(repeat_to_batch_size=repeat_to_batch_size)),
    }
    exec(compile(module, str(path), "exec"), namespace)
    return namespace


def main() -> None:
    source_root = Path(sys.argv[1]).resolve()
    ns = load_classes(source_root)

    concat = ns["LatentConcat"]
    s1 = torch.arange(2 * 1 * 2 * 2 * 3, dtype=torch.float32).reshape(2, 1, 2, 2, 3)
    s2 = torch.full((1, 1, 1, 2, 3), 100.0)
    out = concat.execute({"samples": s1, "owner": "first"}, {"samples": s2, "owner": "second"}, "t")[0]
    assert list(out["samples"].shape) == [2, 1, 3, 2, 3]
    assert out["owner"] == "first"
    assert torch.equal(out["samples"][:, :, :2], s1)
    assert torch.equal(out["samples"][:, :, 2:], s2.repeat(2, 1, 1, 1, 1))
    reverse = concat.execute({"samples": s1}, {"samples": s2}, "-t")[0]["samples"]
    assert torch.equal(reverse[:, :, :1], s2.repeat(2, 1, 1, 1, 1))
    image_t = concat.execute({"samples": torch.zeros(1, 4, 2, 2)}, {"samples": torch.ones(1, 1, 2, 2)}, "t")[0]["samples"]
    assert list(image_t.shape) == [1, 5, 2, 2]

    cut = ns["LatentCut"]
    video = torch.arange(1 * 1 * 5 * 1 * 1, dtype=torch.float32).reshape(1, 1, 5, 1, 1)
    last_two = cut.execute({"samples": video, "tag": "kept"}, "t", -2, 100)[0]
    assert last_two["tag"] == "kept"
    assert torch.equal(last_two["samples"].flatten(), torch.tensor([3.0, 4.0]))
    clamped = cut.execute({"samples": video}, "t", 999, 4)[0]["samples"]
    assert torch.equal(clamped.flatten(), torch.tensor([4.0]))
    cut_image_t = cut.execute({"samples": torch.arange(4.0).reshape(1, 4, 1, 1)}, "t", 1, 2)[0]["samples"]
    assert list(cut_image_t.shape) == [1, 2, 1, 1]

    to_batch = ns["LatentCutToBatch"]
    packed = to_batch.execute({"samples": torch.arange(2 * 1 * 5 * 2 * 2.0).reshape(2, 1, 5, 2, 2), "tag": "input"}, "t", 2)[0]
    assert list(packed["samples"].shape) == [4, 1, 2, 2, 2]
    assert packed["tag"] == "input"
    image_dict = {"samples": torch.zeros(1, 4, 3, 3), "same": object()}
    unchanged_4d_t = to_batch.execute(image_dict, "t", 1)[0]
    assert unchanged_4d_t is image_dict

    replace = ns["ReplaceVideoLatentFrames"]
    destination = {"samples": torch.zeros(1, 1, 5, 1, 1), "origin": "destination"}
    source = {"samples": torch.tensor([[[[[7.0]], [[8.0]]]]]), "origin": "source", "source_meta": 9}
    replaced = replace.execute(destination, 1, source)[0]
    assert torch.equal(replaced["samples"].flatten(), torch.tensor([0.0, 7.0, 8.0, 0.0, 0.0]))
    assert replaced["origin"] == "source" and replaced["source_meta"] == 9
    assert torch.equal(destination["samples"], torch.zeros_like(destination["samples"]))
    assert replace.execute(destination, 0, None)[0] is destination
    assert replace.execute(destination, 4, source)[0] is destination
    negative = replace.execute(destination, -2, source)[0]["samples"]
    assert torch.equal(negative.flatten(), torch.tensor([0.0, 0.0, 0.0, 7.0, 8.0]))
    too_negative_failed = False
    try:
        replace.execute(destination, -6, source)
    except RuntimeError:
        too_negative_failed = True
    assert too_negative_failed

    print(json.dumps({
        "concat": {"videoShape": list(out["samples"].shape), "imageTShape": list(image_t.shape)},
        "cut": {"lastTwo": last_two["samples"].flatten().tolist(), "imageTShape": list(cut_image_t.shape)},
        "cutToBatch": {"shape": list(packed["samples"].shape), "fourDTIsIdentity": unchanged_4d_t is image_dict},
        "replace": {"frames": replaced["samples"].flatten().tolist(), "metadataOrigin": replaced["origin"], "tooNegativeRaises": too_negative_failed},
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
