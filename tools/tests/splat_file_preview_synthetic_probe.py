from __future__ import annotations

import ast
import gzip
import importlib.util
import json
import logging
import os
import struct
import tempfile
from io import BytesIO
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import torch


ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / ".comfyui-source-0.32.0"
GAUSSIAN_SOURCE = SOURCE / "comfy_extras" / "nodes_gaussian_splat.py"
LOAD3D_SOURCE = SOURCE / "comfy_extras" / "nodes_load_3d.py"
GEOMETRY_TYPES_SOURCE = SOURCE / "comfy_api" / "latest" / "_util" / "geometry_types.py"


def load_geometry_types():
    spec = importlib.util.spec_from_file_location("wizard_probe_geometry_types", GEOMETRY_TYPES_SOURCE)
    if spec is None or spec.loader is None:
        raise AssertionError("could not load pinned geometry_types.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


GEOMETRY = load_geometry_types()


class DummyNodeOutput:
    def __init__(self, *values: object, ui: object | None = None) -> None:
        self.values = values
        self.ui = ui


class DummyComfyNode:
    pass


class DummyIO:
    ComfyNode = DummyComfyNode
    NodeOutput = DummyNodeOutput


class DummyTypes:
    File3D = GEOMETRY.File3D
    SPLAT = GEOMETRY.SPLAT


class DummyUI:
    @staticmethod
    def PreviewUI3DAdvanced(model_file: str, camera_info: object, model_3d_info: object):
        return {
            "result": [model_file, camera_info, model_3d_info],
            "kind": "PreviewUI3DAdvanced",
        }


class FixedUUID:
    def __init__(self) -> None:
        self.value = 0

    def uuid4(self):
        self.value += 1
        return SimpleNamespace(hex=f"{self.value:032x}")


def extract(
    path: Path,
    *,
    functions: set[str] = frozenset(),
    classes: set[str] = frozenset(),
    assignments: set[str] = frozenset(),
    namespace: dict[str, object],
) -> dict[str, object]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    selected: list[ast.stmt] = []
    found_functions: set[str] = set()
    found_classes: set[str] = set()
    found_assignments: set[str] = set()
    for node in tree.body:
        if isinstance(node, (ast.Assign, ast.AnnAssign)):
            names: set[str] = set()
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            for target in targets:
                if isinstance(target, ast.Name):
                    names.add(target.id)
            if names & assignments:
                selected.append(node)
                found_assignments.update(names & assignments)
        elif isinstance(node, ast.FunctionDef) and node.name in functions:
            selected.append(node)
            found_functions.add(node.name)
        elif isinstance(node, ast.ClassDef) and node.name in classes:
            selected.append(node)
            found_classes.add(node.name)
    if found_functions != functions or found_classes != classes or found_assignments != assignments:
        raise AssertionError(
            f"missing exact definitions in {path}: functions={functions - found_functions}, "
            f"classes={classes - found_classes}, assignments={assignments - found_assignments}"
        )
    exec(compile(ast.Module(body=selected, type_ignores=[]), str(path), "exec"), namespace)
    return {name: namespace[name] for name in functions | classes | assignments}


def gaussian_definitions() -> dict[str, object]:
    functions = {
        "_real_len",
        "_gaussian_ply_bytes",
        "_gaussian_ksplat_bytes",
        "_gaussian_spz_bytes",
        "_rgb_to_sh_dc",
        "_norm_quat",
        "_parse_ply_gaussian",
        "_parse_splat_gaussian",
        "_parse_ksplat_gaussian",
        "_parse_spz_gaussian",
        "_detect_splat_format",
    }
    assignments = {
        "_C0",
        "_KSPLAT_HEADER_BYTES",
        "_KSPLAT_SECTION_HEADER_BYTES",
        "_KSPLAT_BYTES_PER_SPLAT",
        "_KSPLAT_VERSION",
        "_SPZ_MAGIC",
        "_SPZ_VERSION",
        "_SPZ_FRACTIONAL_BITS",
        "_SPZ_COLOR_SCALE",
        "_PLY_DTYPES",
        "_KSPLAT_COMPRESSION",
        "_KSPLAT_SH_COMPONENTS",
        "_GAUSSIAN_PARSERS",
    }
    return extract(
        GAUSSIAN_SOURCE,
        functions=functions,
        classes={"SplatToFile3D", "File3DToSplat"},
        assignments=assignments,
        namespace={
            "gzip": gzip,
            "logging": logging,
            "math": __import__("math"),
            "struct": struct,
            "BytesIO": BytesIO,
            "np": np,
            "torch": torch,
            "IO": DummyIO,
            "Types": DummyTypes,
        },
    )


def sample_splat() -> object:
    positions = torch.tensor(
        [
            [[0.125, -0.25, 0.5], [1.0, 2.0, -3.0], [99.0, 99.0, 99.0]],
            [[-1.0, 0.0, 1.0], [88.0, 88.0, 88.0], [77.0, 77.0, 77.0]],
        ],
        dtype=torch.float32,
    )
    scales = torch.tensor(
        [
            [[0.05, 0.10, 0.20], [0.3, 0.4, 0.5], [1.0, 1.0, 1.0]],
            [[0.2, 0.2, 0.2], [1.0, 1.0, 1.0], [1.0, 1.0, 1.0]],
        ],
        dtype=torch.float32,
    )
    rotations = torch.tensor(
        [
            [[1.0, 0.0, 0.0, 0.0], [0.9238795, 0.0, 0.3826834, 0.0], [1.0, 0.0, 0.0, 0.0]],
            [[1.0, 0.0, 0.0, 0.0], [1.0, 0.0, 0.0, 0.0], [1.0, 0.0, 0.0, 0.0]],
        ],
        dtype=torch.float32,
    )
    opacities = torch.tensor(
        [[[0.25], [0.75], [1.0]], [[0.5], [1.0], [1.0]]], dtype=torch.float32
    )
    sh = torch.zeros(2, 3, 4, 3, dtype=torch.float32)
    sh[0, 0, 0] = torch.tensor([-0.5, 0.0, 0.5])
    sh[0, 1, 0] = torch.tensor([0.25, -0.25, 0.75])
    sh[0, :2, 1:] = torch.tensor(
        [
            [[0.01, 0.02, 0.03], [0.04, 0.05, 0.06], [0.07, 0.08, 0.09]],
            [[-0.01, -0.02, -0.03], [-0.04, -0.05, -0.06], [-0.07, -0.08, -0.09]],
        ]
    )
    return GEOMETRY.SPLAT(
        positions,
        scales,
        rotations,
        opacities,
        sh,
        counts=torch.tensor([2, 1], dtype=torch.int64),
    )


def run_file_roundtrip_probe() -> dict[str, object]:
    definitions = gaussian_definitions()
    to_file = definitions["SplatToFile3D"]
    from_file = definitions["File3DToSplat"]
    source = sample_splat()
    summary: dict[str, object] = {}

    exported: dict[str, object] = {}
    for file_format in ("ply", "ksplat", "spz"):
        file_3d = to_file.execute(source, file_format).values[0]
        data = file_3d.get_bytes()
        decoded = from_file.execute(file_3d).values[0]
        exported[file_format] = {
            "format": file_3d.format,
            "byteLength": len(data),
            "positionsShape": list(decoded.positions.shape),
            "shShape": list(decoded.sh.shape),
            "counts": decoded.counts,
            "positionsClose": bool(torch.allclose(decoded.positions[0], source.positions[0, :2], atol=3e-4)),
            "scalesClose": bool(torch.allclose(decoded.scales[0], source.scales[0, :2], atol=7e-2, rtol=7e-2)),
            "rotationsNormalized": bool(torch.allclose(decoded.rotations.norm(dim=-1), torch.ones(1, 2), atol=2e-3)),
            "opacitiesClose": bool(torch.allclose(decoded.opacities[0], source.opacities[0, :2], atol=5e-3)),
        }
        if file_format == "ply":
            exported[file_format]["fullSHClose"] = bool(torch.allclose(decoded.sh[0], source.sh[0, :2], atol=1e-6))
            exported[file_format]["binaryLittleEndian"] = b"format binary_little_endian 1.0" in data[:100]
        elif file_format == "ksplat":
            exported[file_format]["levelZeroUncompressed"] = data[20:22] == b"\x00\x00"
        else:
            exported[file_format]["gzipMagic"] = data[:2] == b"\x1f\x8b"

    ply = to_file.execute(source, "ply").values[0]
    detected = GEOMETRY.File3D(BytesIO(ply.get_bytes()), file_format="")
    detected_splat = from_file.execute(detected).values[0]

    record = struct.pack(
        "<6f8B",
        1.0,
        2.0,
        3.0,
        0.1,
        0.2,
        0.3,
        255,
        128,
        0,
        64,
        255,
        128,
        128,
        128,
    )
    raw_splat = from_file.execute(GEOMETRY.File3D(BytesIO(record), file_format="")).values[0]
    empty_splat = from_file.execute(GEOMETRY.File3D(BytesIO(b""), file_format="")).values[0]

    unsupported_raised = False
    try:
        to_file.execute(source, "splat")
    except ValueError:
        unsupported_raised = True

    empty_export_raised = False
    empty = GEOMETRY.SPLAT(
        torch.zeros(1, 0, 3),
        torch.zeros(1, 0, 3),
        torch.zeros(1, 0, 4),
        torch.zeros(1, 0, 1),
        torch.zeros(1, 0, 1, 3),
    )
    try:
        to_file.execute(empty, "ply")
    except ValueError:
        empty_export_raised = True

    invalid_detect_raised = False
    try:
        from_file.execute(GEOMETRY.File3D(BytesIO(b"x" * 31), file_format=""))
    except ValueError:
        invalid_detect_raised = True

    recognized_metadata_precedence = False
    spz = to_file.execute(source, "spz").values[0]
    try:
        from_file.execute(GEOMETRY.File3D(BytesIO(spz.get_bytes()), file_format="ply"))
    except ValueError as error:
        recognized_metadata_precedence = "not a PLY" in str(error)

    summary["formats"] = exported
    summary["batchTwoUsesFirstCountTwo"] = all(
        item["positionsShape"] == [1, 2, 3] for item in exported.values()
    )
    summary["blankFormatDetectsPLY"] = list(detected_splat.positions.shape) == [1, 2, 3]
    summary["rawSplatDetectedFromThirtyTwoBytes"] = list(raw_splat.positions.shape) == [1, 1, 3]
    summary["emptyBytesBecomeEmptySplat"] = list(empty_splat.positions.shape) == [1, 0, 3]
    summary["unsupportedWriterRaises"] = unsupported_raised
    summary["emptyExportRaises"] = empty_export_raised
    summary["invalidContentDetectionRaises"] = invalid_detect_raised
    summary["recognizedFormatMetadataTakesPrecedence"] = recognized_metadata_precedence
    return summary


def run_preview_probe() -> dict[str, object]:
    fixed_uuid = FixedUUID()
    with tempfile.TemporaryDirectory(prefix="nodes-wizard-preview-3d-") as temp_dir:
        folder_paths = SimpleNamespace(get_temp_directory=lambda: temp_dir)
        definitions = extract(
            LOAD3D_SOURCE,
            classes={"PreviewGaussianSplat", "PreviewPointCloud"},
            namespace={
                "IO": DummyIO,
                "Types": DummyTypes,
                "UI": DummyUI,
                "folder_paths": folder_paths,
                "os": os,
                "uuid": fixed_uuid,
            },
        )
        viewport = {
            "camera_info": {"source": "viewport"},
            "model_3d_info": [{"source": "viewport"}],
        }
        splat_file = GEOMETRY.File3D(BytesIO(b"splat-preview-bytes"), file_format="ply")
        splat_output = definitions["PreviewGaussianSplat"].execute(
            splat_file,
            viewport,
            800,
            600,
            camera_info={"source": "explicit"},
            model_3d_info=[{"source": "explicit"}],
        )
        splat_result = splat_output.ui["result"]
        splat_path = Path(temp_dir) / splat_result[0]

        point_file = GEOMETRY.File3D(BytesIO(b"point-cloud-preview-bytes"), file_format="ply")
        point_output = definitions["PreviewPointCloud"].execute(
            point_file,
            viewport,
            1024,
            1024,
        )
        point_result = point_output.ui["result"]
        point_path = Path(temp_dir) / point_result[0]

        blank_file = GEOMETRY.File3D(BytesIO(b"blank-state"), file_format="ply")
        blank_output = definitions["PreviewPointCloud"].execute(
            blank_file,
            "not-a-dict",
            1,
            4096,
        )

        return {
            "splatFilename": splat_result[0],
            "pointFilename": point_result[0],
            "tempFilesExistDuringExecution": splat_path.exists() and point_path.exists(),
            "splatBytesPreserved": splat_path.read_bytes() == b"splat-preview-bytes",
            "pointBytesPreserved": point_path.read_bytes() == b"point-cloud-preview-bytes",
            "explicitCameraOverridesViewport": splat_result[1] == {"source": "explicit"},
            "explicitModelInfoOverridesViewport": splat_result[2] == [{"source": "explicit"}],
            "pointUsesViewportCamera": point_result[1] == {"source": "viewport"},
            "pointUsesViewportModelInfo": point_result[2] == [{"source": "viewport"}],
            "splatPassThroughValues": [
                splat_output.values[0] is splat_file,
                splat_output.values[1] == [{"source": "explicit"}],
                splat_output.values[2] == {"source": "explicit"},
                splat_output.values[3] == 800,
                splat_output.values[4] == 600,
            ],
            "nonDictViewportDefaults": [blank_output.values[1], blank_output.values[2]],
            "uiKind": splat_output.ui["kind"],
        }


def run() -> dict[str, object]:
    return {
        "fileRoundTrip": run_file_roundtrip_probe(),
        "preview": run_preview_probe(),
    }


if __name__ == "__main__":
    print(json.dumps(run(), ensure_ascii=False, sort_keys=True))
