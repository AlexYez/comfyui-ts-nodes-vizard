from __future__ import annotations

import ast
import json
from pathlib import Path


class NodeOutput:
    def __init__(self, *values): self.values = values


class IO:
    class ComfyNode: pass
    NodeOutput = NodeOutput


def run(root: Path) -> dict[str, object]:
    path = root / ".comfyui-source-0.32.0/comfy_extras/nodes_string.py"
    if not path.is_file(): raise AssertionError("pinned source is required")
    tree = ast.parse(path.read_text(encoding="utf-8"))
    names = {"StringCompare", "StringContains", "StringLength", "StringSubstring"}
    selected = [n for n in tree.body if isinstance(n, ast.ClassDef) and n.name in names]
    scope = {"io": IO}
    exec(compile(ast.Module(body=selected, type_ignores=[]), str(path), "exec"), scope)
    compare, contains = scope["StringCompare"], scope["StringContains"]
    length, substring = scope["StringLength"], scope["StringSubstring"]
    assert compare.execute("Nano Banana 2", "nano banana 2", "Starts With", False).values == (True,)
    assert compare.execute("abc", "BC", "Ends With", False).values == (True,)
    assert compare.execute("abc", "", "Starts With", True).values == (True,)
    assert contains.execute("Status: Warning", "warning", False).values == (True,)
    assert contains.execute("abc", ".*", True).values == (False,)
    assert contains.execute("abc", "", True).values == (True,)
    assert length.execute("e\u0301😀").values == (3,)
    slices = [substring.execute("abcdef", 1, 4).values[0], substring.execute("abcdef", -3, 99).values[0], substring.execute("abc", 3, 1).values[0]]
    assert slices == ["bcd", "def", ""]
    return {"compare": True, "contains": True, "length": 3, "slices": slices}


if __name__ == "__main__": print(json.dumps(run(Path(__file__).resolve().parents[2]), ensure_ascii=False, sort_keys=True))
