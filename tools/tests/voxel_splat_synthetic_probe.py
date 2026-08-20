from __future__ import annotations

import ast
import json
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import torch


ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / ".comfyui-source-0.32.0"
HUNYUAN_SOURCE = SOURCE / "comfy_extras" / "nodes_hunyuan3d.py"
SPLAT_SOURCE = SOURCE / "comfy_extras" / "nodes_gaussian_splat.py"


class QuietProgressBar:
    def __init__(self, total: int) -> None:
        self.total = total

    def update(self, _amount: int) -> None:
        return None


class Splat:
    def __init__(
        self,
        positions: torch.Tensor,
        scales: torch.Tensor,
        rotations: torch.Tensor,
        opacities: torch.Tensor,
        sh: torch.Tensor,
        counts: torch.Tensor | None = None,
    ) -> None:
        self.positions = positions
        self.scales = scales
        self.rotations = rotations
        self.opacities = opacities
        self.sh = sh
        self.counts = counts


def extract_functions(path: Path, names: set[str], namespace: dict[str, object]) -> dict[str, object]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    selected = [
        node
        for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name in names
    ]
    found = {node.name for node in selected}
    if found != names:
        raise AssertionError(f"missing exact definitions in {path}: {sorted(names - found)}")
    exec(compile(ast.Module(body=selected, type_ignores=[]), str(path), "exec"), namespace)
    return {name: namespace[name] for name in names}


def load_definitions() -> tuple[dict[str, object], dict[str, object]]:
    voxel_namespace: dict[str, object] = {
        "torch": torch,
        "comfy": SimpleNamespace(utils=SimpleNamespace(ProgressBar=QuietProgressBar)),
    }
    voxel = extract_functions(
        HUNYUAN_SOURCE,
        {"voxel_to_mesh", "voxel_to_mesh_surfnet"},
        voxel_namespace,
    )

    splat_namespace: dict[str, object] = {
        "np": np,
        "torch": torch,
        "Types": SimpleNamespace(SPLAT=Splat),
    }
    splat = extract_functions(
        SPLAT_SOURCE,
        {
            "_real_len",
            "_pad_stack",
            "_merge_gaussians",
            "_inverse_covariance",
            "_splat_density",
            "_surface_nets",
            "_otsu_level",
        },
        splat_namespace,
    )
    return voxel, splat


def run_voxel_probe(definitions: dict[str, object]) -> dict[str, object]:
    basic = definitions["voxel_to_mesh"]
    surface_net = definitions["voxel_to_mesh_surfnet"]

    volume = torch.zeros((12, 12, 12), dtype=torch.float32)
    volume[3:9, 3:9, 3:9] = 1.0
    basic_vertices, basic_faces = basic(volume, threshold=0.6, device=torch.device("cpu"))
    surface_vertices, surface_faces = surface_net(volume, threshold=0.6, device=torch.device("cpu"))

    equal_to_threshold = torch.full((2, 2, 2), 0.6, dtype=torch.float32)
    empty_basic_vertices, empty_basic_faces = basic(
        equal_to_threshold,
        threshold=0.6,
        device=torch.device("cpu"),
    )
    empty_surface_vertices, empty_surface_faces = surface_net(
        equal_to_threshold,
        threshold=0.6,
        device=torch.device("cpu"),
    )

    tiny = torch.zeros((2, 2, 2), dtype=torch.float32)
    tiny[0, 0, 0] = 1.0
    tiny_error: str | None = None
    try:
        surface_net(tiny, threshold=0.6, device=torch.device("cpu"))
    except Exception as exc:  # Exact pinned helper currently fails on a tiny active shell.
        tiny_error = type(exc).__name__

    return {
        "basic": {
            "vertices": list(basic_vertices.shape),
            "faces": list(basic_faces.shape),
            "faceDtype": str(basic_faces.dtype),
            "bounds": [float(basic_vertices.min()), float(basic_vertices.max())],
        },
        "surfaceNet": {
            "vertices": list(surface_vertices.shape),
            "faces": list(surface_faces.shape),
            "faceDtype": str(surface_faces.dtype),
            "bounds": [float(surface_vertices.min()), float(surface_vertices.max())],
        },
        "strictThreshold": {
            "basicSentinelVertices": list(empty_basic_vertices.shape),
            "basicSentinelFaces": list(empty_basic_faces.shape),
            "basicSentinelFaceDtype": str(empty_basic_faces.dtype),
            "basicSentinelVertex": empty_basic_vertices[0].tolist(),
            "basicSentinelFace": empty_basic_faces[0].tolist(),
            "surfaceVertices": list(empty_surface_vertices.shape),
            "surfaceFaces": list(empty_surface_faces.shape),
        },
        "tinySurfaceNetError": tiny_error,
    }


def make_splat(
    positions: torch.Tensor,
    counts: list[int] | None,
    sh_terms: int,
    value_offset: float = 0.0,
) -> Splat:
    batch, length, _ = positions.shape
    scales = torch.full((batch, length, 3), 0.2, dtype=torch.float32)
    rotations = torch.zeros((batch, length, 4), dtype=torch.float32)
    rotations[..., 0] = 1.0
    opacities = torch.full((batch, length, 1), 0.8, dtype=torch.float32)
    sh = torch.full((batch, length, sh_terms, 3), value_offset, dtype=torch.float32)
    count_tensor = None if counts is None else torch.tensor(counts, dtype=torch.int64)
    return Splat(positions, scales, rotations, opacities, sh, count_tensor)


def run_merge_probe(definitions: dict[str, object]) -> dict[str, object]:
    merge = definitions["_merge_gaussians"]
    first_positions = torch.tensor(
        [
            [[1.0, 0.0, 0.0], [2.0, 0.0, 0.0], [99.0, 99.0, 99.0]],
            [[3.0, 0.0, 0.0], [99.0, 99.0, 99.0], [99.0, 99.0, 99.0]],
        ],
        dtype=torch.float32,
    )
    second_positions = torch.tensor(
        [
            [[10.0, 0.0, 0.0], [98.0, 98.0, 98.0]],
            [[20.0, 0.0, 0.0], [97.0, 97.0, 97.0]],
        ],
        dtype=torch.float32,
    )
    first = make_splat(first_positions, [2, 1], sh_terms=1, value_offset=1.0)
    second = make_splat(second_positions, [1, 1], sh_terms=4, value_offset=2.0)
    merged = merge([first, None, second])

    mismatch_error: str | None = None
    try:
        mismatch = make_splat(second_positions[:1], [1], sh_terms=1)
        merge([first, mismatch])
    except Exception as exc:
        mismatch_error = str(exc)

    return {
        "shape": list(merged.positions.shape),
        "counts": merged.counts.tolist() if merged.counts is not None else None,
        "shShape": list(merged.sh.shape),
        "firstBatchX": merged.positions[0, :, 0].tolist(),
        "secondBatchX": merged.positions[1, :, 0].tolist(),
        "firstInputShPaddingIsZero": bool(torch.count_nonzero(merged.sh[0, :2, 1:]) == 0),
        "mismatchError": mismatch_error,
    }


def run_splat_density_probe(definitions: dict[str, object]) -> dict[str, object]:
    density = definitions["_splat_density"]
    surface_nets = definitions["_surface_nets"]
    otsu = definitions["_otsu_level"]

    xyz = torch.tensor([[-0.2, 0.0, 0.0], [0.2, 0.0, 0.0]], dtype=torch.float32)
    opacity = torch.tensor([0.9, 0.8], dtype=torch.float32)
    scale = torch.tensor([[0.22, 0.18, 0.16], [0.22, 0.18, 0.16]], dtype=torch.float32)
    quat = torch.tensor([[1.0, 0.0, 0.0, 0.0], [1.0, 0.0, 0.0, 0.0]], dtype=torch.float32)
    rgb = torch.tensor([[1.0, 0.1, 0.1], [0.1, 0.1, 1.0]], dtype=torch.float32)

    vol1, col1, norm1, origin, voxel = density(
        xyz,
        opacity,
        scale,
        quat,
        rgb,
        24,
        1,
        torch.device("cpu"),
        color_sharpen=1.0,
        col_dtype=torch.float32,
    )
    vol3_plain, _col3_plain, norm3_plain, _origin3_plain, _voxel3_plain = density(
        xyz,
        opacity,
        scale,
        quat,
        rgb,
        24,
        3,
        torch.device("cpu"),
        color_sharpen=1.0,
        col_dtype=torch.float32,
    )
    vol3, col3, norm3, origin3, voxel3 = density(
        xyz,
        opacity,
        scale,
        quat,
        rgb,
        24,
        3,
        torch.device("cpu"),
        color_sharpen=2.0,
        col_dtype=torch.float32,
    )
    occupied = vol3[vol3 > float(vol3.max()) * 1e-3]
    auto_level = otsu(occupied.numpy())
    biased_level = min(
        max(auto_level * 0.4, float(vol3.min()) + 1e-6 * float(vol3.max() - vol3.min())),
        float(vol3.max()) - 1e-6 * float(vol3.max() - vol3.min()),
    )
    vertices, faces = surface_nets(
        vol3,
        biased_level,
        voxel3,
        origin3,
        torch.device("cpu"),
    )

    return {
        "gridShape": list(vol3.shape),
        "kernelOneNonzero": int(torch.count_nonzero(vol1)),
        "kernelThreeNonzero": int(torch.count_nonzero(vol3)),
        "densityIndependentOfColorSharpen": bool(torch.allclose(vol3_plain, vol3)),
        "colorNormalizerDiffers": bool(not torch.allclose(norm3_plain, norm3)),
        "autoLevel": float(auto_level),
        "biasedLevel": float(biased_level),
        "meshVertices": int(len(vertices)),
        "meshFaces": int(len(faces)),
        "origin": [float(value) for value in origin3],
        "voxel": float(voxel3),
        "colorVolumesFinite": bool(torch.isfinite(col1).all() and torch.isfinite(col3).all()),
    }


def run() -> dict[str, object]:
    voxel, splat = load_definitions()
    return {
        "voxel": run_voxel_probe(voxel),
        "merge": run_merge_probe(splat),
        "splatDensity": run_splat_density_probe(splat),
    }


if __name__ == "__main__":
    print(json.dumps(run(), ensure_ascii=False, sort_keys=True))
