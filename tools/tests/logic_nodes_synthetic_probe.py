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


class BoolProbe:
    def __init__(self, value: bool, label: str, calls: list[str]) -> None:
        self.value = value
        self.label = label
        self.calls = calls

    def __bool__(self) -> bool:
        self.calls.append(self.label)
        return self.value


class BombBool:
    def __bool__(self) -> bool:
        raise AssertionError("short-circuited value was evaluated")


def extract_classes(path: Path, names: set[str]) -> dict[str, object]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    selected = [node for node in tree.body if isinstance(node, ast.ClassDef) and node.name in names]
    if {node.name for node in selected} != names:
        raise AssertionError(f"missing exact classes in {path}")
    io = SimpleNamespace(
        ComfyNode=DummyComfyNode,
        NodeOutput=DummyNodeOutput,
        Autogrow=SimpleNamespace(Type=dict),
        Combo=SimpleNamespace(Type=str),
    )
    namespace: dict[str, object] = {"io": io}
    exec(compile(ast.Module(body=selected, type_ignores=[]), str(path), "exec"), namespace)
    return {name: namespace[name] for name in names}


def value(result: object) -> object:
    assert isinstance(result, DummyNodeOutput)
    assert len(result.values) == 1
    return result.values[0]


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit("usage: logic_nodes_synthetic_probe.py <pinned-comfyui-source>")
    source = Path(sys.argv[1]).resolve() / "comfy_extras" / "nodes_logic.py"
    definitions = extract_classes(source, {"NotNode", "AndNode", "OrNode", "SwitchNode", "CustomComboNode"})

    switch = definitions["SwitchNode"]
    true_marker = {"branch": "true"}
    false_marker = {"branch": "false"}
    selected_true = value(switch.execute(True, on_true=true_marker, on_false=false_marker))
    selected_false = value(switch.execute(False, on_true=true_marker, on_false=false_marker))
    assert selected_true is true_marker and selected_false is false_marker
    assert switch.check_lazy_status(True, on_true=None, on_false=false_marker) == ["on_true"]
    assert switch.check_lazy_status(False, on_true=true_marker, on_false=None) == ["on_false"]
    assert switch.check_lazy_status(True, on_true=true_marker, on_false=None) is None
    assert switch.check_lazy_status(False, on_true=None, on_false=false_marker) is None

    combo = definitions["CustomComboNode"]
    assert combo.validate_inputs("Music", index=2, option1="Music") is True
    combo_result = combo.execute("SFX", index=2, option1="Music", option2="SFX")
    assert isinstance(combo_result, DummyNodeOutput)
    assert combo_result.values == ("SFX", 2)
    default_combo_result = combo.execute("Music")
    assert default_combo_result.values == ("Music", 0)

    not_node = definitions["NotNode"]
    not_cases = {
        "false": value(not_node.execute(False)),
        "zero": value(not_node.execute(0)),
        "empty_string": value(not_node.execute("")),
        "empty_list": value(not_node.execute([])),
        "true": value(not_node.execute(True)),
        "one": value(not_node.execute(1)),
        "nonempty_string": value(not_node.execute("false")),
    }
    assert not_cases == {
        "false": True,
        "zero": True,
        "empty_string": True,
        "empty_list": True,
        "true": False,
        "one": False,
        "nonempty_string": False,
    }

    and_node = definitions["AndNode"]
    or_node = definitions["OrNode"]
    assert value(and_node.execute({"value0": True, "value1": "ready", "value2": 1})) is True
    assert value(and_node.execute({"value0": True, "value1": "", "value2": 1})) is False
    assert value(or_node.execute({"value0": False, "value1": "", "value2": 2})) is True
    assert value(or_node.execute({"value0": False, "value1": "", "value2": 0})) is False
    assert value(and_node.execute({})) is True
    assert value(or_node.execute({})) is False

    and_calls: list[str] = []
    and_short = value(and_node.execute({"first": BoolProbe(False, "first", and_calls), "bomb": BombBool()}))
    assert and_short is False and and_calls == ["first"]
    or_calls: list[str] = []
    or_short = value(or_node.execute({"first": BoolProbe(True, "first", or_calls), "bomb": BombBool()}))
    assert or_short is True and or_calls == ["first"]

    import torch

    tensor_errors: dict[str, str] = {}
    for name, node, arguments in (
        ("not", not_node, torch.tensor([1, 0])),
        ("and", and_node, {"value0": torch.tensor([1, 0])}),
        ("or", or_node, {"value0": torch.tensor([1, 0])}),
    ):
        try:
            node.execute(arguments)
        except RuntimeError as exc:
            tensor_errors[name] = str(exc)
    assert set(tensor_errors) == {"not", "and", "or"}
    assert all("ambiguous" in message.lower() for message in tensor_errors.values())

    print(
        json.dumps(
            {
                "switch": {
                    "trueIdentity": selected_true is true_marker,
                    "falseIdentity": selected_false is false_marker,
                    "missingTrueRequest": ["on_true"],
                    "missingFalseRequest": ["on_false"],
                    "unselectedMissingIgnored": True,
                },
                "combo": {"selected": list(combo_result.values), "defaultIndex": default_combo_result.values[1], "validationAcceptedDynamicOptions": True},
                "not": not_cases,
                "and": {"allTruthy": True, "oneFalsy": False, "emptyDirect": True, "shortCircuitCalls": and_calls},
                "or": {"oneTruthy": True, "allFalsy": False, "emptyDirect": False, "shortCircuitCalls": or_calls},
                "multiElementTensorErrors": tensor_errors,
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
