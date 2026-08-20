from __future__ import annotations

import ast
import json
import os
import shutil
import tempfile
from io import BytesIO
from pathlib import Path
from types import SimpleNamespace
from typing import IO as TypingIO


ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / ".comfyui-source-0.32.0"
LOAD3D_SOURCE = SOURCE / "comfy_extras" / "nodes_load_3d.py"
GEOMETRY_SOURCE = SOURCE / "comfy_api" / "latest" / "_util" / "geometry_types.py"


class DummyNodeOutput:
    def __init__(self, *values: object, ui: object | None = None) -> None:
        self.values = values
        self.ui = ui


class DummyComfyNode:
    pass


class DummyIO:
    ComfyNode = DummyComfyNode
    NodeOutput = DummyNodeOutput


class DummyUI:
    @staticmethod
    def PreviewUI3D(model_file: str, camera_info: object, *, bg_image: object = None):
        return {
            "kind": "PreviewUI3D",
            "result": [model_file, camera_info, bg_image],
        }

    @staticmethod
    def PreviewUI3DAdvanced(model_file: str, camera_info: object, model_3d_info: object):
        return {
            "kind": "PreviewUI3DAdvanced",
            "result": [model_file, camera_info, model_3d_info],
        }


class DummyLoadImage:
    def load_image(self, image: str):
        return f"image:{image}", f"mask:{image}"


class DummyVideoFromFile:
    def __init__(self, path: str) -> None:
        self.path = path


class FixedUUID:
    def __init__(self) -> None:
        self.counter = 0

    def uuid4(self):
        self.counter += 1
        return SimpleNamespace(hex=f"{self.counter:032x}")


def extract_classes(path: Path, names: set[str], namespace: dict[str, object]) -> dict[str, type]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    selected = [node for node in tree.body if isinstance(node, ast.ClassDef) and node.name in names]
    found = {node.name for node in selected}
    if found != names:
        raise AssertionError(f"missing exact classes in {path}: {sorted(names - found)}")
    exec(compile(ast.Module(body=selected, type_ignores=[]), str(path), "exec"), namespace)
    return {name: namespace[name] for name in names}


def load_file3d_class() -> type:
    return extract_classes(
        GEOMETRY_SOURCE,
        {"File3D"},
        {
            "BytesIO": BytesIO,
            "IO": TypingIO,
            "Path": Path,
            "shutil": shutil,
        },
    )["File3D"]


def run() -> dict[str, object]:
    File3D = load_file3d_class()
    fixed_uuid = FixedUUID()

    with tempfile.TemporaryDirectory(prefix="nodes-wizard-load3d-") as root_dir:
        root = Path(root_dir)
        input_dir = root / "input"
        output_dir = root / "output"
        temp_dir = root / "temp"
        model_path = input_dir / "3d" / "probe.glb"
        recording_path = input_dir / "capture.webm"
        model_path.parent.mkdir(parents=True)
        output_dir.mkdir()
        temp_dir.mkdir()
        model_path.write_bytes(b"synthetic-glb-payload")
        recording_path.write_bytes(b"synthetic-video-payload")

        def annotated_path(value: str) -> str:
            if value == "3d/probe.glb":
                return str(model_path)
            if value == "capture.webm":
                return str(recording_path)
            return str(input_dir / value)

        folder_paths = SimpleNamespace(
            get_input_directory=lambda: str(input_dir),
            get_output_directory=lambda: str(output_dir),
            get_temp_directory=lambda: str(temp_dir),
            get_annotated_filepath=annotated_path,
            exists_annotated_filepath=lambda value: Path(annotated_path(value)).is_file(),
        )
        definitions = extract_classes(
            LOAD3D_SOURCE,
            {"Load3D", "Load3DAdvanced", "Preview3D", "Preview3DAdvanced"},
            {
                "IO": DummyIO,
                "UI": DummyUI,
                "Types": SimpleNamespace(File3D=File3D),
                "InputImpl": SimpleNamespace(VideoFromFile=DummyVideoFromFile),
                "nodes": SimpleNamespace(LoadImage=DummyLoadImage),
                "folder_paths": folder_paths,
                "os": os,
                "Path": Path,
                "uuid": fixed_uuid,
            },
        )

        viewport = {
            "camera_info": {"source": "viewport", "zoom": 1.25},
            "model_3d_info": [{"source": "viewport", "scale": [1, 1, 1]}],
        }
        captured = {
            "image": "scene.png",
            "mask": "mask.png",
            "normal": "normal.png",
            "recording": "capture.webm",
            "camera_info": {"source": "load-widget"},
            "model_3d_info": [{"source": "load-widget"}],
        }

        load_output = definitions["Load3D"].execute("3d/probe.glb", captured)
        load_values = load_output.values
        empty_capture = dict(captured, recording="")
        load_none = definitions["Load3D"].execute("none", empty_capture)

        advanced_output = definitions["Load3DAdvanced"].execute(
            "3d/probe.glb", viewport, 800, 600
        )
        advanced_none = definitions["Load3DAdvanced"].execute("none", "invalid-state", 1, 4096)

        preview_file = File3D(BytesIO(b"preview-output-bytes"), file_format="glb")
        preview_output = definitions["Preview3D"].execute(
            preview_file,
            camera_info={"source": "preview-input"},
            bg_image="synthetic-bg",
        )
        preview_result = preview_output.ui["result"]
        preview_path = output_dir / preview_result[0]
        output_files_before_string = sorted(path.name for path in output_dir.iterdir())
        string_output = definitions["Preview3D"].execute("service/result.glb")
        output_files_after_string = sorted(path.name for path in output_dir.iterdir())

        advanced_preview_file = File3D(BytesIO(b"preview-temp-bytes"), file_format="obj")
        advanced_preview = definitions["Preview3DAdvanced"].execute(
            advanced_preview_file,
            viewport,
            1280,
            720,
            camera_info={"source": "explicit"},
            model_3d_info=[],
        )
        advanced_result = advanced_preview.ui["result"]
        advanced_path = temp_dir / advanced_result[0]

        fallback_file = File3D(BytesIO(b"fallback-bytes"), file_format="fbx")
        fallback_preview = definitions["Preview3DAdvanced"].execute(
            fallback_file,
            viewport,
            1024,
            1024,
        )
        blank_file = File3D(BytesIO(b"blank-bytes"), file_format="stl")
        blank_preview = definitions["Preview3DAdvanced"].execute(
            blank_file,
            "not-a-dict",
            1,
            4096,
        )

        return {
            "load3d": {
                "values": [
                    load_values[0],
                    load_values[1],
                    load_values[2],
                    load_values[3],
                    load_values[4],
                    load_values[5].path,
                    load_values[6].format,
                    load_values[7],
                ],
                "fileBytesPreserved": load_values[6].get_bytes() == b"synthetic-glb-payload",
                "noneFileAndPath": [load_none.values[6] is None, load_none.values[2]],
                "validAccepted": definitions["Load3D"].validate_inputs("3d/probe.glb") is True,
                "noneAccepted": definitions["Load3D"].validate_inputs("none") is True,
                "missingRejected": definitions["Load3D"].validate_inputs("3d/missing.glb"),
            },
            "load3dAdvanced": {
                "fileBytesPreserved": advanced_output.values[0].get_bytes() == b"synthetic-glb-payload",
                "values": [
                    advanced_output.values[1],
                    advanced_output.values[2],
                    advanced_output.values[3],
                    advanced_output.values[4],
                ],
                "noneAndInvalidViewport": [
                    advanced_none.values[0] is None,
                    advanced_none.values[1],
                    advanced_none.values[2],
                    advanced_none.values[3],
                    advanced_none.values[4],
                ],
                "missingRejected": definitions["Load3DAdvanced"].validate_inputs("3d/missing.obj"),
            },
            "preview3d": {
                "filename": preview_result[0],
                "outputExists": preview_path.is_file(),
                "outputBytesPreserved": preview_path.read_bytes() == b"preview-output-bytes",
                "cameraAndBackground": preview_result[1:],
                "stringResult": string_output.ui["result"],
                "stringBranchCreatesNoFile": output_files_before_string == output_files_after_string,
            },
            "preview3dAdvanced": {
                "filename": advanced_result[0],
                "tempExists": advanced_path.is_file(),
                "tempBytesPreserved": advanced_path.read_bytes() == b"preview-temp-bytes",
                "explicitCameraAndEmptyModelInfo": advanced_result[1:],
                "passThrough": [
                    advanced_preview.values[0] is advanced_preview_file,
                    advanced_preview.values[1],
                    advanced_preview.values[2],
                    advanced_preview.values[3],
                    advanced_preview.values[4],
                ],
                "viewportFallback": [fallback_preview.values[1], fallback_preview.values[2]],
                "invalidViewportDefaults": [blank_preview.values[1], blank_preview.values[2]],
            },
        }


if __name__ == "__main__":
    print(json.dumps(run(), ensure_ascii=False, sort_keys=True))
