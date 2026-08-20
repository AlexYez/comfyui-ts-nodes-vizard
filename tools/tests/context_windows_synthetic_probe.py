from __future__ import annotations

import ast
import json
from pathlib import Path


def assigned_expression(tree: ast.AST, class_name: str, function: str, target: str) -> ast.expr:
    cls = next(n for n in ast.walk(tree) if isinstance(n, ast.ClassDef) and n.name == class_name)
    fn = next(n for n in cls.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == function)
    for node in ast.walk(fn):
        if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == target for t in node.targets):
            return node.value
    raise AssertionError(f"{class_name}.{function}: assignment to {target} not found")


def evaluate(expr: ast.expr, **values: object) -> object:
    code = compile(ast.Expression(expr), "<pinned-source-expression>", "eval")
    return eval(code, {"max": max}, values)


def static_windows(num_frames: int, context_length: int, overlap: int) -> list[list[int]]:
    windows: list[list[int]] = []
    if num_frames <= context_length:
        return [list(range(num_frames))]
    delta = context_length - overlap
    for start in range(0, num_frames, delta):
        ending = start + context_length
        if ending >= num_frames:
            final_start = start - (ending - num_frames)
            windows.append(list(range(final_start, final_start + context_length)))
            break
        windows.append(list(range(start, ending)))
    return windows


def run(root: Path) -> dict[str, object]:
    nodes_path = root / ".comfyui-source-0.32.0" / "comfy_extras" / "nodes_context_windows.py"
    engine_path = root / ".comfyui-source-0.32.0" / "comfy" / "context_windows.py"
    if not nodes_path.is_file() or not engine_path.is_file():
        raise AssertionError("pinned ComfyUI source is required")
    nodes_text = nodes_path.read_text(encoding="utf-8")
    engine_text = engine_path.read_text(encoding="utf-8")
    tree = ast.parse(nodes_text)

    wan_len = assigned_expression(tree, "WanContextWindowsManualNode", "execute", "context_length")
    wan_overlap = assigned_expression(tree, "WanContextWindowsManualNode", "execute", "context_overlap")
    ltx_len = assigned_expression(tree, "LTXVContextWindowsNode", "execute", "context_length")
    ltx_overlap = assigned_expression(tree, "LTXVContextWindowsNode", "execute", "context_overlap")
    conversions = {
        "wan_81_30": [evaluate(wan_len, context_length=81), evaluate(wan_overlap, context_overlap=30)],
        "wan_80_31": [evaluate(wan_len, context_length=80), evaluate(wan_overlap, context_overlap=31)],
        "ltxv_145_40": [evaluate(ltx_len, context_length=145), evaluate(ltx_overlap, context_overlap=40)],
    }
    assert conversions == {"wan_81_30": [21, 7], "wan_80_31": [20, 7], "ltxv_145_40": [19, 5]}

    assert "cond_retain_index_list=retain_index_list" in nodes_text
    assert "latent_retain_index_list=retain_index_list" in nodes_text
    assert "dim=2" in nodes_text
    assert "if total_frame_count > self.context_length" in engine_text
    assert "[int(x.strip()) for x in cond_retain_index_list.split(\",\")]" in engine_text
    assert "if freenoise:" in nodes_text and "create_sampler_sample_wrapper(model)" in nodes_text

    windows = static_windows(50, 21, 8)
    assert windows == [list(range(0, 21)), list(range(13, 34)), list(range(26, 47)), list(range(29, 50))]
    zero_step = False
    try:
        static_windows(50, 21, 21)
    except ValueError:
        zero_step = True
    assert zero_step
    return {"conversions": conversions, "static_windows": [[w[0], w[-1]] for w in windows], "zero_step_rejected": zero_step}


if __name__ == "__main__":
    print(json.dumps(run(Path(__file__).resolve().parents[2]), sort_keys=True))
