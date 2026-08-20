from __future__ import annotations

import ast
import json
import math
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import torch
import numpy as np


class _Splat:
    def __init__(self, positions, scales, rotations, opacities, sh, counts=None):
        self.positions = positions
        self.scales = scales
        self.rotations = rotations
        self.opacities = opacities
        self.sh = sh
        self.counts = counts


class _NodeOutput:
    def __init__(self, *values):
        self.values = values


class _ProgressBar:
    def __init__(self, total):
        self.total = total

    def update(self, value):
        return None


def _load_exact(source_root: Path) -> dict[str, Any]:
    path = source_root / "comfy_extras" / "nodes_gaussian_splat.py"
    tree = ast.parse(path.read_text(encoding="utf-8"))
    wanted_functions = {
        "_real_len", "_hex_to_rgb", "_quantile", "_quat_to_mat", "_quat_mul", "_euler_to_quat",
        "_mat_to_quat", "_lookat_quat_wxyz", "_lookat_camera_info", "_quat_camera_info",
        "_orbit_camera_info", "_orbit_camera_info_yaw",
    }
    wanted_classes = {"RenderSplat", "CreateCameraInfo", "TransformSplat", "GetSplatCount"}
    body = [
        node for node in tree.body
        if (isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name in wanted_functions)
        or (isinstance(node, ast.ClassDef) and node.name in wanted_classes)
    ]
    io = SimpleNamespace(ComfyNode=object, NodeOutput=_NodeOutput)
    namespace: dict[str, Any] = {
        "torch": torch,
        "np": np,
        "math": math,
        "IO": io,
        "Types": SimpleNamespace(SPLAT=_Splat),
        "comfy": SimpleNamespace(
            model_management=SimpleNamespace(
                get_torch_device=lambda: torch.device("cpu"),
                intermediate_device=lambda: torch.device("cpu"),
                intermediate_dtype=lambda: torch.float32,
            ),
            utils=SimpleNamespace(ProgressBar=_ProgressBar),
        ),
        "PromptServer": SimpleNamespace(instance=SimpleNamespace(send_progress_text=lambda *args: None)),
    }
    exec(compile(ast.Module(body=body, type_ignores=[]), str(path), "exec"), namespace)
    namespace["GetSplatCount"].hidden = SimpleNamespace(unique_id=None)
    return namespace


def run_probe(source_root: Path) -> dict[str, Any]:
    ns = _load_exact(source_root)
    assert ns["_hex_to_rgb"]("#848484") == (132 / 255, 132 / 255, 132 / 255)
    assert ns["_hex_to_rgb"]("bad") == (0.0, 0.0, 0.0)

    camera = ns["CreateCameraInfo"].execute(
        {"mode": "orbit", "yaw": 35.0, "pitch": 30.0, "distance": 2.5},
        0.0, 0.0, 0.0, 0.0, 35.0, 1.0, "perspective",
    ).values[0]
    expected_position = torch.tensor([
        2.5 * math.cos(math.radians(30)) * math.sin(math.radians(35)),
        2.5 * math.sin(math.radians(30)),
        2.5 * math.cos(math.radians(30)) * math.cos(math.radians(35)),
    ])
    got_position = torch.tensor([camera["position"][axis] for axis in "xyz"])
    assert torch.allclose(got_position, expected_position, atol=1e-6)
    q = torch.tensor([camera["quaternion"][key] for key in ("w", "x", "y", "z")])
    assert torch.allclose(q.norm(), torch.tensor(1.0), atol=1e-6)
    assert camera["cameraType"] == "perspective" and camera["zoom"] == 1.0

    quat_a = ns["CreateCameraInfo"].execute(
        {"mode": "quaternion", "position_x": 1.0, "position_y": 2.0, "position_z": 3.0,
         "quat_x": 0.0, "quat_y": 0.0, "quat_z": 0.0, "quat_w": 2.0},
        99.0, 99.0, 99.0, 0.0, 50.0, 2.0, "orthographic",
    ).values[0]
    quat_b = ns["CreateCameraInfo"].execute(
        {"mode": "quaternion", "position_x": 1.0, "position_y": 2.0, "position_z": 3.0,
         "quat_x": 0.0, "quat_y": 0.0, "quat_z": 0.0, "quat_w": 2.0},
        -99.0, -99.0, -99.0, 90.0, 50.0, 2.0, "orthographic",
    ).values[0]
    assert quat_a == quat_b
    assert quat_a["target"] == {"x": 1.0, "y": 2.0, "z": 2.0}

    positions = torch.tensor([[[1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 0.0]]])
    scales = torch.ones((1, 3, 3))
    rotations = torch.tensor([[[1.0, 0.0, 0.0, 0.0]] * 3])
    opacities = torch.ones((1, 3, 1))
    sh = torch.zeros((1, 3, 1, 3))
    splat = _Splat(positions, scales, rotations, opacities, sh, counts=torch.tensor([2]))

    uniform = ns["TransformSplat"].execute(
        splat, 1.0, 2.0, 3.0, 0.0, 90.0, 0.0, 2.0, 2.0, 2.0,
    ).values[0]
    assert torch.allclose(uniform.positions[0, 0], torch.tensor([1.0, 2.0, 1.0]), atol=1e-5)
    assert torch.allclose(uniform.scales, torch.full_like(scales, 2.0))
    assert uniform.opacities is opacities and uniform.sh is sh and uniform.counts is splat.counts
    assert torch.allclose(uniform.rotations.norm(dim=-1), torch.ones((1, 3)), atol=1e-6)

    nonuniform = ns["TransformSplat"].execute(
        splat, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 2.0, 3.0, 4.0,
    ).values[0]
    assert torch.allclose(nonuniform.positions[0, 0], torch.tensor([2.0, 0.0, 0.0]))
    assert torch.allclose(nonuniform.scales.sort().values, torch.tensor([[[2.0, 3.0, 4.0]] * 3]))

    counted = ns["GetSplatCount"].execute(splat)
    assert counted.values[0] is splat and counted.values[1] == 2
    no_counts = _Splat(torch.zeros((2, 3, 3)), scales.expand(2, -1, -1), rotations.expand(2, -1, -1),
                       opacities.expand(2, -1, -1), sh.expand(2, -1, -1, -1), counts=None)
    assert ns["GetSplatCount"].execute(no_counts).values[1] == 6

    # Exercise the exact RenderSplat frame/orbit loop while replacing only the heavyweight rasterizer.
    ns["_gaussian_item"] = lambda value, index, device: (
        value.positions[index], torch.ones((3, 3)), torch.ones(3), torch.ones((3, 3)),
        torch.tensor([[1.0, 0.0, 0.0, 0.0]] * 3),
    )
    calls: list[dict[str, Any]] = []
    def fake_render(xyz, rgb, opacity, scale, rot, width, height, splat_scale, bg, camera_info, **kwargs):
        calls.append(camera_info)
        return torch.zeros((height, width, 3)), torch.ones((height, width))
    ns["_render_gaussian"] = fake_render
    batch_splat = _Splat(torch.zeros((2, 3, 3)), scales.expand(2, -1, -1), rotations.expand(2, -1, -1),
                         opacities.expand(2, -1, -1), sh.expand(2, -1, -1, -1))
    rendered = ns["RenderSplat"].execute(
        batch_splat, 64, 72, -3, 1.0, 2.0, 0.0, 0.0, "#000000", "color", camera_info=camera,
    )
    assert rendered.values[0].shape == (6, 72, 64, 3)
    assert rendered.values[1].shape == (6, 72, 64)
    assert len(calls) == 6

    return {
        "cameraOrbitPosition": [round(float(x), 6) for x in got_position],
        "quaternionNormalized": True,
        "quaternionIgnoresTargetAndRoll": True,
        "uniformTransform": True,
        "nonUniformCovarianceTransform": True,
        "countsAware": True,
        "renderBatchFrames": list(rendered.values[0].shape),
    }


if __name__ == "__main__":
    root = Path(sys.argv[1] if len(sys.argv) > 1 else ".comfyui-source-0.32.0")
    print(json.dumps(run_probe(root), ensure_ascii=False, sort_keys=True))
