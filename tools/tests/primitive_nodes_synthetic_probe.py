from __future__ import annotations

import ast
import json
import math
import sys
from pathlib import Path
from types import SimpleNamespace


class DummyNodeOutput:
    def __init__(self, *values: object) -> None:
        self.values = values


class DummyComfyNode:
    pass


def extract_classes(path: Path, names: set[str]) -> dict[str, object]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    selected = [node for node in tree.body if isinstance(node, ast.ClassDef) and node.name in names]
    if {node.name for node in selected} != names:
        raise AssertionError(f"missing exact classes in {path}")
    namespace: dict[str, object] = {
        "io": SimpleNamespace(ComfyNode=DummyComfyNode, NodeOutput=DummyNodeOutput),
        "sys": sys,
    }
    exec(compile(ast.Module(body=selected, type_ignores=[]), str(path), "exec"), namespace)
    return {name: namespace[name] for name in names}


def output(node: object, value: object) -> object:
    result = node.execute(value)  # type: ignore[attr-defined]
    assert isinstance(result, DummyNodeOutput)
    assert len(result.values) == 1
    return result.values[0]


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit("usage: primitive_nodes_synthetic_probe.py <pinned-comfyui-source>")
    source = Path(sys.argv[1]).resolve() / "comfy_extras" / "nodes_primitive.py"
    definitions = extract_classes(source, {"String", "StringMultiline", "Int", "Float", "Boolean"})

    short_values = ["", "plain text", "Привет, ComfyUI 🧙"]
    short_outputs = [output(definitions["String"], value) for value in short_values]
    assert all(result is value for result, value in zip(short_outputs, short_values))

    multiline_values = ["первая строка\nвторая строка", "  края сохранены  \n", ""]
    multiline_outputs = [output(definitions["StringMultiline"], value) for value in multiline_values]
    assert all(result is value for result, value in zip(multiline_outputs, multiline_values))

    integer_values = [0, -17, -sys.maxsize, sys.maxsize]
    integer_outputs = [output(definitions["Int"], value) for value in integer_values]
    assert integer_outputs == integer_values
    assert all(type(result) is int for result in integer_outputs)

    float_values = [1.5, -2.25, -0.0, float(sys.maxsize)]
    float_outputs = [output(definitions["Float"], value) for value in float_values]
    assert float_outputs == float_values
    assert all(type(result) is float for result in float_outputs)
    assert math.copysign(1.0, float_outputs[2]) == -1.0

    boolean_values = [True, False]
    boolean_outputs = [output(definitions["Boolean"], value) for value in boolean_values]
    assert boolean_outputs == boolean_values
    assert all(type(result) is bool for result in boolean_outputs)

    print(
        json.dumps(
            {
                "string": {"values": short_outputs, "sameObjects": True},
                "multiline": {"values": multiline_outputs, "sameObjects": True, "newlinesPreserved": multiline_outputs[0].count("\n") == 1},
                "integer": {"values": integer_outputs, "types": [type(value).__name__ for value in integer_outputs]},
                "float": {"values": float_outputs, "negativeZeroPreserved": math.copysign(1.0, float_outputs[2]) == -1.0},
                "boolean": {"values": boolean_outputs, "types": [type(value).__name__ for value in boolean_outputs]},
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
