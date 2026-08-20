from __future__ import annotations

import ast
import importlib.util
import io as stdlib_io
import json
import os
import sys
import tempfile
from dataclasses import dataclass
from enum import Enum
from fractions import Fraction
from pathlib import Path
from types import SimpleNamespace
from typing import Optional

import numpy as np
import torch


def compile_named_classes(path: Path, names: set[str], globals_dict: dict[str, object]) -> dict[str, type]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    classes = [
        node
        for node in tree.body
        if isinstance(node, ast.ClassDef) and node.name in names
    ]
    missing = names - {node.name for node in classes}
    if missing:
        raise AssertionError(f"classes not found in {path}: {sorted(missing)}")
    module = ast.Module(body=classes, type_ignores=[])
    ast.fix_missing_locations(module)
    exec(compile(module, str(path), "exec"), globals_dict)
    return {name: globals_dict[name] for name in names}


class FakeNodeOutput:
    def __init__(self, *args, ui=None):
        self.args = args
        self.ui = ui


class FakeComfyNode:
    pass


class FakeDynamicCombo:
    Type = dict


class FakeFolderType:
    output = "output"


class FakeIO:
    ComfyNode = FakeComfyNode
    DynamicCombo = FakeDynamicCombo
    NodeOutput = FakeNodeOutput
    FolderType = FakeFolderType


class FakeInput:
    Image = object
    Audio = object
    Video = object


class FakePreviewVideo:
    def __init__(self, values):
        self.values = values


class FakeUI:
    PreviewVideo = FakePreviewVideo

    @staticmethod
    def SavedResult(filename, subfolder, folder_type):
        return {
            "filename": filename,
            "subfolder": subfolder,
            "type": folder_type,
        }


class FakeFolderPaths:
    def __init__(self, output: Path):
        self.output = output

    def get_output_directory(self) -> str:
        return str(self.output)

    def get_save_image_path(self, prefix, output, width, height):
        normalized = str(prefix).replace("\\", "/")
        subfolder, filename = os.path.split(normalized)
        full = Path(output) / subfolder
        full.mkdir(parents=True, exist_ok=True)
        return str(full), filename, 1, subfolder, prefix


class FakeVideoFrame:
    def __init__(self, array: np.ndarray, format_name: str):
        self.array = array
        self.format_name = format_name

    @classmethod
    def from_ndarray(cls, array, format):
        return cls(array, format)


class FakeStream:
    def __init__(self, codec: str, rate: Fraction):
        self.codec = codec
        self.rate = rate
        self.width = None
        self.height = None
        self.pix_fmt = None
        self.bit_rate = None
        self.options = {}
        self.frames: list[FakeVideoFrame] = []

    def encode(self, frame=None):
        if frame is None:
            return ["flush"]
        self.frames.append(frame)
        return [f"frame-{len(self.frames)}"]


class FakeContainer:
    def __init__(self, path: str, mode: str):
        self.path = path
        self.mode = mode
        self.metadata = {}
        self.streams: list[FakeStream] = []
        self.muxed = []
        self.closed = False

    def add_stream(self, codec: str, rate: Fraction):
        stream = FakeStream(codec, rate)
        self.streams.append(stream)
        return stream

    def mux(self, packet):
        self.muxed.append(packet)

    def close(self):
        self.closed = True


class FakeAV:
    VideoFrame = FakeVideoFrame

    def __init__(self):
        self.containers: list[FakeContainer] = []

    def open(self, path, mode="r"):
        container = FakeContainer(str(path), mode)
        self.containers.append(container)
        return container


class RecordingVideo:
    def __init__(self):
        self.calls = []

    def get_dimensions(self):
        return 64, 32

    def save_to(self, path, **kwargs):
        self.calls.append((path, kwargs))


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit("usage: video_io_synthetic_probe.py <pinned-comfyui-source>")

    source = Path(sys.argv[1]).resolve()
    nodes_path = source / "comfy_extras" / "nodes_video.py"
    util_path = source / "comfy_api" / "latest" / "_util" / "video_types.py"
    impl_path = source / "comfy_api" / "latest" / "_input_impl" / "video_types.py"

    util_globals: dict[str, object] = {
        "__builtins__": __builtins__,
        "dataclass": dataclass,
        "Enum": Enum,
        "Fraction": Fraction,
        "Optional": Optional,
        "ImageInput": object,
        "AudioInput": object,
        "MaskInput": object,
    }
    util_classes = compile_named_classes(
        util_path,
        {"VideoCodec", "VideoContainer", "VideoComponents"},
        util_globals,
    )
    VideoCodec = util_classes["VideoCodec"]
    VideoContainer = util_classes["VideoContainer"]
    VideoComponents = util_classes["VideoComponents"]

    class VideoInput:
        pass

    impl_globals: dict[str, object] = {
        "__builtins__": __builtins__,
        "VideoInput": VideoInput,
        "VideoComponents": VideoComponents,
        "VideoContainer": VideoContainer,
        "VideoCodec": VideoCodec,
        "Optional": Optional,
        "io": stdlib_io,
        "av": SimpleNamespace(),
        "json": json,
        "math": __import__("math"),
        "np": np,
        "torch": torch,
    }
    VideoFromComponents = compile_named_classes(
        impl_path, {"VideoFromComponents"}, impl_globals
    )["VideoFromComponents"]

    with tempfile.TemporaryDirectory(prefix="nodes-wizard-video-io-") as temp_name:
        folder_paths = FakeFolderPaths(Path(temp_name) / "output")
        fake_av = FakeAV()
        args = SimpleNamespace(disable_metadata=False)
        Types = SimpleNamespace(
            VideoContainer=VideoContainer,
            VideoComponents=VideoComponents,
        )
        InputImpl = SimpleNamespace(VideoFromComponents=VideoFromComponents)
        nodes_globals: dict[str, object] = {
            "__builtins__": __builtins__,
            "os": os,
            "av": fake_av,
            "torch": torch,
            "folder_paths": folder_paths,
            "json": json,
            "Optional": Optional,
            "Fraction": Fraction,
            "io": FakeIO,
            "ui": FakeUI,
            "Input": FakeInput,
            "InputImpl": InputImpl,
            "Types": Types,
            "args": args,
        }
        classes = compile_named_classes(
            nodes_path,
            {"SaveWEBM", "SaveVideo", "CreateVideo", "GetVideoComponents"},
            nodes_globals,
        )
        SaveWEBM = classes["SaveWEBM"]
        SaveVideo = classes["SaveVideo"]
        CreateVideo = classes["CreateVideo"]
        GetVideoComponents = classes["GetVideoComponents"]

        SaveWEBM.hidden = SimpleNamespace(
            prompt={"node": "probe"}, extra_pnginfo={"seed": 7}
        )
        rgba = torch.linspace(-0.25, 1.25, 2 * 4 * 6 * 4).reshape(2, 4, 6, 4)
        vp9_output = SaveWEBM.execute(
            images=rgba,
            codec="vp9",
            fps=23.9764,
            filename_prefix="video/alpha",
            crf=32,
        )
        vp9_container = fake_av.containers[-1]
        vp9_stream = vp9_container.streams[0]
        assert vp9_output.args[0] is rgba
        assert vp9_container.closed
        assert vp9_stream.codec == "libvpx-vp9"
        assert vp9_stream.rate == Fraction(2997, 125)
        assert (vp9_stream.width, vp9_stream.height) == (6, 4)
        assert vp9_stream.pix_fmt == "yuva420p"
        assert vp9_stream.options == {"crf": "32"}
        assert len(vp9_stream.frames) == 2
        assert all(frame.format_name == "rgba" for frame in vp9_stream.frames)
        assert all(frame.array.shape == (4, 6, 4) for frame in vp9_stream.frames)
        assert min(frame.array.min() for frame in vp9_stream.frames) == 0
        assert max(frame.array.max() for frame in vp9_stream.frames) == 255
        assert json.loads(vp9_container.metadata["prompt"]) == {"node": "probe"}
        assert json.loads(vp9_container.metadata["seed"]) == 7

        av1_output = SaveWEBM.execute(
            images=rgba,
            codec="av1",
            fps=24,
            filename_prefix="video/opaque",
            crf=40,
        )
        av1_container = fake_av.containers[-1]
        av1_stream = av1_container.streams[0]
        assert av1_output.args[0] is rgba
        assert av1_stream.codec == "libsvtav1"
        assert av1_stream.pix_fmt == "yuv420p10le"
        assert av1_stream.options == {"crf": "40", "preset": "6"}
        assert all(frame.format_name == "rgb24" for frame in av1_stream.frames)
        assert all(frame.array.shape == (4, 6, 3) for frame in av1_stream.frames)

        SaveVideo.hidden = SimpleNamespace(
            prompt={"workflow": "probe"}, extra_pnginfo={"note": "synthetic"}
        )
        recording_video = RecordingVideo()
        saved = SaveVideo.execute(
            video=recording_video,
            filename_prefix="video/probe",
            format="mp4",
            codec={
                "codec": "h264",
                "encoding": {"encoding": "re-encode", "crf": 19},
            },
        )
        assert saved.args[0] is recording_video
        assert len(recording_video.calls) == 1
        save_path, save_kwargs = recording_video.calls[0]
        assert save_path.endswith(os.path.join("video", "probe_00001_.mp4"))
        assert save_kwargs["format"] == VideoContainer.MP4
        assert save_kwargs["codec"] == "h264"
        assert save_kwargs["crf"] == 19
        assert save_kwargs["metadata"] == {
            "note": "synthetic",
            "prompt": {"workflow": "probe"},
        }
        assert saved.ui.values[0]["filename"] == "probe_00001_.mp4"

        frames = torch.arange(3 * 2 * 4 * 3, dtype=torch.float32).reshape(3, 2, 4, 3) / 100
        audio = {
            "waveform": torch.zeros((1, 2, 4800), dtype=torch.float32),
            "sample_rate": 48000,
        }
        created_output = CreateVideo.execute(
            images=frames, fps=29.97, audio=audio, bit_depth=10
        )
        created_video = created_output.args[0]
        components = created_video.get_components()
        assert components.images is frames
        assert components.audio is audio
        assert components.frame_rate == Fraction(29.97)
        assert created_video.get_bit_depth() == 10

        extracted = GetVideoComponents.execute(created_video)
        assert extracted.args[0] is frames
        assert extracted.args[1] is audio
        assert extracted.args[2] == float(Fraction(29.97))
        assert extracted.args[3] == 10

        print(
            json.dumps(
                {
                    "saveWebm": {
                        "vp9PixelFormat": vp9_stream.pix_fmt,
                        "vp9FrameFormat": vp9_stream.frames[0].format_name,
                        "av1PixelFormat": av1_stream.pix_fmt,
                        "av1FrameFormat": av1_stream.frames[0].format_name,
                        "fps": float(vp9_stream.rate),
                        "frameCount": len(vp9_stream.frames),
                    },
                    "saveVideo": {
                        "extension": Path(save_path).suffix,
                        "codec": save_kwargs["codec"],
                        "crf": save_kwargs["crf"],
                        "passthrough": saved.args[0] is recording_video,
                    },
                    "createAndExtract": {
                        "frameShape": list(frames.shape),
                        "fps": extracted.args[2],
                        "bitDepth": extracted.args[3],
                        "frameIdentity": extracted.args[0] is frames,
                        "audioIdentity": extracted.args[1] is audio,
                    },
                    "realEncodingExecuted": False,
                    "pyavAvailable": importlib.util.find_spec("av") is not None,
                },
                ensure_ascii=False,
                sort_keys=True,
            )
        )


if __name__ == "__main__":
    main()
