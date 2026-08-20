from __future__ import annotations

import ast
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
from PIL import Image


ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / ".comfyui-source-0.32.0"
SAVE_3D_SOURCE = SOURCE / "comfy_extras" / "nodes_save_3d.py"
GEOMETRY_TYPES_SOURCE = SOURCE / "comfy_api" / "latest" / "_util" / "geometry_types.py"


def load_geometry_types():
    spec = importlib.util.spec_from_file_location("wizard_probe_geometry_types_save", GEOMETRY_TYPES_SOURCE)
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
    MESH = GEOMETRY.MESH
    File3D = GEOMETRY.File3D


class DummyUI:
    @staticmethod
    def PreviewUI3DAdvanced(model_file: str, camera_info: object, model_3d_info: object):
        return {
            "result": [model_file, camera_info, model_3d_info],
            "kind": "PreviewUI3DAdvanced",
        }


class FolderPathsProbe:
    def __init__(self, output_dir: Path) -> None:
        self.output_dir = output_dir

    def get_output_directory(self) -> str:
        return str(self.output_dir)

    def get_save_image_path(self, filename_prefix: str, output_dir: str):
        normalized = os.path.normpath(filename_prefix)
        subfolder = os.path.dirname(normalized)
        filename = os.path.basename(normalized)
        full_output_folder = Path(output_dir) / subfolder
        full_output_folder.mkdir(parents=True, exist_ok=True)

        counters: list[int] = []
        prefix = f"{filename}_"
        for candidate in full_output_folder.iterdir():
            if not candidate.name.startswith(prefix):
                continue
            remainder = candidate.name[len(prefix):]
            digits = remainder.split("_", 1)[0].split(".", 1)[0]
            if digits.isdigit():
                counters.append(int(digits))
        counter = max(counters, default=0) + 1
        return str(full_output_folder), filename, counter, subfolder, filename_prefix


def extract_save_definitions(folder_paths: FolderPathsProbe) -> dict[str, object]:
    tree = ast.parse(SAVE_3D_SOURCE.read_text(encoding="utf-8"))
    function_names = {
        "get_mesh_batch_item",
        "save_glb",
        "_save_file3d_to_output",
        "execute_save_3d_advanced",
    }
    class_names = {"SaveGLB", "Save3DAdvanced", "SaveGaussianSplat", "SavePointCloud"}
    selected: list[ast.stmt] = []
    found_functions: set[str] = set()
    found_classes: set[str] = set()
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name in function_names:
            selected.append(node)
            found_functions.add(node.name)
        elif isinstance(node, ast.ClassDef) and node.name in class_names:
            selected.append(node)
            found_classes.add(node.name)
    if found_functions != function_names or found_classes != class_names:
        raise AssertionError(
            f"missing exact definitions: functions={function_names - found_functions}, "
            f"classes={class_names - found_classes}"
        )

    namespace: dict[str, object] = {
        "json": json,
        "logging": logging,
        "os": os,
        "struct": struct,
        "BytesIO": BytesIO,
        "np": np,
        "Image": Image,
        "torch": torch,
        "folder_paths": folder_paths,
        "args": SimpleNamespace(disable_metadata=False),
        "IO": DummyIO,
        "Types": DummyTypes,
        "UI": DummyUI,
    }
    exec(compile(ast.Module(body=selected, type_ignores=[]), str(SAVE_3D_SOURCE), "exec"), namespace)
    return {name: namespace[name] for name in function_names | class_names}


def parse_glb_json(path: Path) -> dict[str, object]:
    data = path.read_bytes()
    magic, version, total_length = struct.unpack_from("<4sII", data, 0)
    if magic != b"glTF" or version != 2 or total_length != len(data):
        raise AssertionError("invalid GLB header")
    json_length, json_kind = struct.unpack_from("<II", data, 12)
    if json_kind != 0x4E4F534A:
        raise AssertionError("missing GLB JSON chunk")
    return json.loads(data[20:20 + json_length].decode("utf-8").rstrip(" "))


def make_mesh() -> object:
    vertices = torch.tensor(
        [
            [[0.0, 0.0, 0.0], [1.0, 0.0, 0.0], [0.0, 1.0, 0.0]],
            [[0.0, 0.0, 0.0], [0.0, 0.0, 0.0], [0.0, 0.0, 0.0]],
        ],
        dtype=torch.float32,
    )
    faces = torch.tensor([[[0, 1, 2]], [[0, 0, 0]]], dtype=torch.int64)
    colors = torch.tensor(
        [
            [[1.5, 0.0, 0.0, 1.0], [0.0, 1.0, 0.0, 1.0], [0.0, 0.0, -0.5, 1.0]],
            [[0.0, 0.0, 0.0, 0.0], [0.0, 0.0, 0.0, 0.0], [0.0, 0.0, 0.0, 0.0]],
        ],
        dtype=torch.float32,
    )
    uvs = torch.tensor(
        [
            [[0.0, 0.0], [1.0, 0.0], [0.0, 1.0]],
            [[0.0, 0.0], [0.0, 0.0], [0.0, 0.0]],
        ],
        dtype=torch.float32,
    )
    return GEOMETRY.MESH(
        vertices,
        faces,
        uvs=uvs,
        vertex_colors=colors,
        vertex_counts=torch.tensor([3, 0], dtype=torch.int64),
        face_counts=torch.tensor([1, 0], dtype=torch.int64),
        unlit=True,
    )


def run_save_glb_probe(definitions: dict[str, object], output_dir: Path) -> dict[str, object]:
    save_glb_node = definitions["SaveGLB"]
    save_glb_node.hidden = SimpleNamespace(
        prompt={"7": {"class_type": "Probe"}},
        extra_pnginfo={"workflow": {"nodes": []}},
    )

    mesh_output = save_glb_node.execute(make_mesh(), "3d/probe_mesh")
    mesh_results = mesh_output.ui["3d"]
    mesh_path = output_dir / mesh_results[0]["subfolder"] / mesh_results[0]["filename"]
    gltf = parse_glb_json(mesh_path)
    primitive = gltf["meshes"][0]["primitives"][0]

    file_bytes = b"exact-spz-payload"
    file_input = GEOMETRY.File3D(BytesIO(file_bytes), file_format="spz")
    file_output = save_glb_node.execute(file_input, "3d/probe_file")
    file_result = file_output.ui["3d"][0]
    file_path = output_dir / file_result["subfolder"] / file_result["filename"]

    blank_format_input = GEOMETRY.File3D(BytesIO(b"opaque-without-format"), file_format="")
    blank_output = save_glb_node.execute(blank_format_input, "3d/probe_blank")
    blank_result = blank_output.ui["3d"][0]
    blank_path = output_dir / blank_result["subfolder"] / blank_result["filename"]

    invalid_face_raised = False
    try:
        definitions["save_glb"](
            torch.tensor([[0.0, 0.0, 0.0]], dtype=torch.float32),
            torch.tensor([[0, 1, 0]], dtype=torch.int64),
            output_dir / "invalid.glb",
        )
    except ValueError:
        invalid_face_raised = True

    return {
        "meshResultCount": len(mesh_results),
        "emptyBatchItemSkipped": len(mesh_results) == 1,
        "meshFilename": mesh_results[0]["filename"],
        "meshIsGLB": mesh_path.read_bytes()[:4] == b"glTF",
        "meshMetadata": gltf["asset"].get("extras"),
        "meshHasUV": "TEXCOORD_0" in primitive["attributes"],
        "meshHasColor": "COLOR_0" in primitive["attributes"],
        "meshUsesUnlit": "KHR_materials_unlit" in gltf.get("extensionsUsed", []),
        "fileBytesPreserved": file_path.read_bytes() == file_bytes,
        "fileExtensionPreserved": file_path.suffix == ".spz",
        "fileFilename": file_result["filename"],
        "blankFormatFallsBackToGLBName": blank_path.suffix == ".glb",
        "blankFormatBytesStillPreserved": blank_path.read_bytes() == b"opaque-without-format",
        "invalidFaceRaises": invalid_face_raised,
    }


def run_advanced_probe(definitions: dict[str, object], output_dir: Path) -> dict[str, object]:
    viewport = {
        "camera_info": {"source": "viewport"},
        "model_3d_info": [{"source": "viewport"}],
    }
    cases = [
        (
            "Save3DAdvanced",
            GEOMETRY.File3D(BytesIO(b"advanced-glb"), file_format="glb"),
            "3d/advanced",
            viewport,
            {"camera_info": {"source": "explicit"}, "model_3d_info": [{"source": "explicit"}]},
            800,
            600,
        ),
        (
            "SaveGaussianSplat",
            GEOMETRY.File3D(BytesIO(b"gaussian-spz"), file_format="spz"),
            "3d/gaussian",
            viewport,
            {},
            1024,
            1024,
        ),
        (
            "SavePointCloud",
            GEOMETRY.File3D(BytesIO(b"point-ply"), file_format="ply"),
            "3d/pointcloud",
            "not-a-dict",
            {},
            1,
            4096,
        ),
    ]
    result: dict[str, object] = {}
    for class_name, file_3d, prefix, state, kwargs, width, height in cases:
        output = definitions[class_name].execute(
            file_3d,
            state,
            width,
            height,
            prefix,
            **kwargs,
        )
        relative_path = output.ui["result"][0]
        saved_path = output_dir / Path(relative_path)
        result[class_name] = {
            "filename": relative_path,
            "saved": saved_path.exists(),
            "bytesPreserved": saved_path.read_bytes() == file_3d.get_bytes(),
            "sameObjectPassedThrough": output.values[0] is file_3d,
            "modelInfo": output.values[1],
            "cameraInfo": output.values[2],
            "dimensions": [output.values[3], output.values[4]],
            "uiKind": output.ui["kind"],
            "uiMatchesOutputs": output.ui["result"][1:] == [output.values[2], output.values[1]],
        }
    return result


def run() -> dict[str, object]:
    with tempfile.TemporaryDirectory(prefix="nodes-wizard-save-3d-") as temp_dir:
        output_dir = Path(temp_dir) / "output"
        output_dir.mkdir()
        folder_paths = FolderPathsProbe(output_dir)
        definitions = extract_save_definitions(folder_paths)
        return {
            "saveGLB": run_save_glb_probe(definitions, output_dir),
            "advanced": run_advanced_probe(definitions, output_dir),
        }


if __name__ == "__main__":
    print(json.dumps(run(), ensure_ascii=False, sort_keys=True))
