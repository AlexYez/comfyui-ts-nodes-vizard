from __future__ import annotations

import ast
import json
import re
from pathlib import Path
from types import SimpleNamespace

import torch


ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / ".comfyui-source-0.32.0" / "comfy_extras" / "nodes_custom_sampler.py"


class DummyNodeOutput:
    def __init__(self, *values: object) -> None:
        self.values = values


def load_exact_classes() -> dict[str, type]:
    tree = ast.parse(SOURCE.read_text(encoding="utf-8"))
    names = {"ManualSigmas", "FlipSigmas", "SetFirstSigma", "SplitSigmas"}
    selected = [
        node
        for node in tree.body
        if isinstance(node, ast.ClassDef) and node.name in names
    ]
    if {node.name for node in selected} != names:
        raise AssertionError("pinned sigma classes were not found")
    io = SimpleNamespace(ComfyNode=object, NodeOutput=DummyNodeOutput)
    namespace: dict[str, object] = {"io": io, "torch": torch, "re": re}
    exec(
        compile(ast.Module(body=selected, type_ignores=[]), str(SOURCE), "exec"),
        namespace,
    )
    return {name: namespace[name] for name in names}  # type: ignore[return-value]


def values(output: DummyNodeOutput) -> tuple[object, ...]:
    return output.values


def run() -> dict[str, object]:
    classes = load_exact_classes()

    manual = classes["ManualSigmas"]
    parsed = values(manual.execute("1, +.5; -2.25 words 3."))[0]
    empty_manual = values(manual.execute("no values here"))[0]
    exponent_like = values(manual.execute("1e-3"))[0]
    malformed_error = None
    try:
        manual.execute("1..2")
    except ValueError as exc:
        malformed_error = type(exc).__name__
    assert torch.equal(parsed, torch.tensor([1.0, 0.5, -2.25, 3.0]))
    assert parsed.dtype == torch.float32 and parsed.device.type == "cpu"
    assert empty_manual.numel() == 0
    assert torch.equal(exponent_like, torch.tensor([1.0, -3.0]))
    assert malformed_error == "ValueError"

    flip = classes["FlipSigmas"]
    descending = torch.tensor([4.0, 2.0, 0.0], dtype=torch.float64)
    flipped = values(flip.execute(descending))[0]
    empty_input = torch.empty(0, dtype=torch.float64)
    empty_flipped = values(flip.execute(empty_input))[0]
    singleton_zero = values(flip.execute(torch.tensor([0.0])))[0]
    assert torch.equal(descending, torch.tensor([4.0, 2.0, 0.0], dtype=torch.float64))
    assert torch.equal(flipped, torch.tensor([0.0001, 2.0, 4.0], dtype=torch.float64))
    assert flipped.dtype == descending.dtype
    assert flipped.data_ptr() != descending.data_ptr()
    assert empty_flipped is empty_input
    assert torch.equal(singleton_zero, torch.tensor([0.0001]))

    set_first = classes["SetFirstSigma"]
    original = torch.tensor([5.0, 3.0, 0.0], dtype=torch.float64)
    replaced = values(set_first.execute(original, 7.5))[0]
    singleton_replaced = values(set_first.execute(torch.tensor([1.0]), 9.0))[0]
    empty_error = None
    try:
        set_first.execute(torch.empty(0), 1.0)
    except IndexError as exc:
        empty_error = type(exc).__name__
    assert torch.equal(original, torch.tensor([5.0, 3.0, 0.0], dtype=torch.float64))
    assert torch.equal(replaced, torch.tensor([7.5, 3.0, 0.0], dtype=torch.float64))
    assert replaced.data_ptr() != original.data_ptr()
    assert torch.equal(singleton_replaced, torch.tensor([9.0]))
    assert empty_error == "IndexError"

    split = classes["SplitSigmas"]
    schedule = torch.tensor([5.0, 4.0, 3.0, 2.0, 0.0])
    high, low = values(split.execute(schedule, 2))
    at_zero = values(split.execute(schedule, 0))
    at_last = values(split.execute(schedule, 4))
    past_end = values(split.execute(schedule, 5))
    empty_split = values(split.execute(torch.empty(0), 0))
    singleton_split = values(split.execute(torch.tensor([6.0]), 0))
    assert torch.equal(high, torch.tensor([5.0, 4.0, 3.0]))
    assert torch.equal(low, torch.tensor([3.0, 2.0, 0.0]))
    assert high[-1] == low[0] == schedule[2]
    assert high.untyped_storage().data_ptr() == schedule.untyped_storage().data_ptr()
    assert low.untyped_storage().data_ptr() == schedule.untyped_storage().data_ptr()
    assert [tensor.numel() for tensor in at_zero] == [1, 5]
    assert [tensor.numel() for tensor in at_last] == [5, 1]
    assert [tensor.numel() for tensor in past_end] == [5, 0]
    assert [tensor.numel() for tensor in empty_split] == [0, 0]
    assert [tensor.numel() for tensor in singleton_split] == [1, 1]

    return {
        "manual": {
            "parsed": parsed.tolist(),
            "dtype": str(parsed.dtype),
            "device": parsed.device.type,
            "emptyLength": int(empty_manual.numel()),
            "exponentLike": exponent_like.tolist(),
            "malformedError": malformed_error,
        },
        "flip": {
            "input": descending.tolist(),
            "output": flipped.tolist(),
            "copied": flipped.data_ptr() != descending.data_ptr(),
            "emptyIdentity": empty_flipped is empty_input,
            "singletonZero": singleton_zero.tolist(),
        },
        "setFirst": {
            "input": original.tolist(),
            "output": replaced.tolist(),
            "cloned": replaced.data_ptr() != original.data_ptr(),
            "singleton": singleton_replaced.tolist(),
            "emptyError": empty_error,
        },
        "split": {
            "step2High": high.tolist(),
            "step2Low": low.tolist(),
            "sharedStorage": (
                high.untyped_storage().data_ptr() == schedule.untyped_storage().data_ptr()
                and low.untyped_storage().data_ptr() == schedule.untyped_storage().data_ptr()
            ),
            "step0Lengths": [int(tensor.numel()) for tensor in at_zero],
            "lastLengths": [int(tensor.numel()) for tensor in at_last],
            "pastEndLengths": [int(tensor.numel()) for tensor in past_end],
            "emptyLengths": [int(tensor.numel()) for tensor in empty_split],
            "singletonLengths": [int(tensor.numel()) for tensor in singleton_split],
        },
    }


if __name__ == "__main__":
    print(json.dumps(run(), ensure_ascii=False, sort_keys=True))
