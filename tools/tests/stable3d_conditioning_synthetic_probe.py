from __future__ import annotations

import ast
import json
import math
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import numpy as np
import torch


ROOT = Path(__file__).resolve().parents[2]
NODE_SOURCE = ROOT / ".comfyui-source-0.32.0" / "comfy_extras" / "nodes_stable3d.py"
UTILS_SOURCE = ROOT / ".comfyui-source-0.32.0" / "comfy" / "utils.py"
CLIP_SOURCE = ROOT / ".comfyui-source-0.32.0" / "comfy" / "clip_model.py"
MODEL_SOURCE = ROOT / ".comfyui-source-0.32.0" / "comfy" / "model_base.py"
SAMPLE_SOURCE = ROOT / ".comfyui-source-0.32.0" / "comfy" / "sample.py"


class DummyNodeOutput:
    def __init__(self, *values: object) -> None:
        self.values = values


class DummyComfyNode:
    pass


def extract_functions(
    source_path: Path,
    names: set[str],
    namespace: dict[str, object],
) -> dict[str, Any]:
    tree = ast.parse(source_path.read_text(encoding="utf-8"))
    selected = [
        node
        for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and node.name in names
    ]
    found = {node.name for node in selected}
    if found != names:
        raise AssertionError(f"missing exact functions in {source_path}: {sorted(names - found)}")
    exec(compile(ast.Module(body=selected, type_ignores=[]), str(source_path), "exec"), namespace)
    return {name: namespace[name] for name in names}


def extract_method(source_path: Path, class_name: str, method_name: str) -> Any:
    tree = ast.parse(source_path.read_text(encoding="utf-8"))
    classes = [
        node
        for node in tree.body
        if isinstance(node, ast.ClassDef) and node.name == class_name
    ]
    if len(classes) != 1:
        raise AssertionError(f"exact class {class_name} was not found")
    methods = [
        node
        for node in classes[0].body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and node.name == method_name
    ]
    if len(methods) != 1:
        raise AssertionError(f"exact method {class_name}.{method_name} was not found")
    method = methods[0]
    method.decorator_list = []
    namespace: dict[str, object] = {
        "torch": torch,
        "utils": SimpleNamespace(resize_to_batch_size=extract_resize_to_batch_size()),
    }
    exec(compile(ast.Module(body=[method], type_ignores=[]), str(source_path), "exec"), namespace)
    return namespace[method_name]


def extract_common_upscale() -> Any:
    return extract_functions(
        UTILS_SOURCE,
        {"common_upscale"},
        {
            "torch": torch,
            "bislerp": lambda *_args, **_kwargs: None,
            "lanczos": lambda *_args, **_kwargs: None,
        },
    )["common_upscale"]


def extract_repeat_to_batch_size() -> Any:
    return extract_functions(
        UTILS_SOURCE,
        {"repeat_to_batch_size"},
        {"math": math},
    )["repeat_to_batch_size"]


def extract_resize_to_batch_size() -> Any:
    return extract_functions(
        UTILS_SOURCE,
        {"resize_to_batch_size"},
        {"math": math, "torch": torch},
    )["resize_to_batch_size"]


def extract_clip_preprocess() -> Any:
    return extract_functions(
        CLIP_SOURCE,
        {"clip_preprocess"},
        {"torch": torch},
    )["clip_preprocess"]


def extract_prepare_noise() -> Any:
    functions = extract_functions(
        SAMPLE_SOURCE,
        {"prepare_noise_inner", "prepare_noise"},
        {
            "np": np,
            "torch": torch,
            "comfy": SimpleNamespace(nested_tensor=SimpleNamespace()),
        },
    )
    # The exact prepare_noise body resolves its sibling by the global name.
    functions["prepare_noise"].__globals__["prepare_noise_inner"] = functions[
        "prepare_noise_inner"
    ]
    return functions["prepare_noise"]


def extract_nodes(common_upscale: Any, repeat_to_batch_size: Any) -> dict[str, Any]:
    tree = ast.parse(NODE_SOURCE.read_text(encoding="utf-8"))
    wanted_functions = {"camera_embeddings"}
    wanted_classes = {
        "StableZero123_Conditioning",
        "StableZero123_Conditioning_Batched",
        "SV3D_Conditioning",
    }
    selected = [
        node
        for node in tree.body
        if (
            isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            and node.name in wanted_functions
        )
        or (isinstance(node, ast.ClassDef) and node.name in wanted_classes)
    ]
    found_functions = {
        node.name
        for node in selected
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }
    found_classes = {node.name for node in selected if isinstance(node, ast.ClassDef)}
    if found_functions != wanted_functions or found_classes != wanted_classes:
        raise AssertionError("exact stable3d definitions were not found")

    io = SimpleNamespace(ComfyNode=DummyComfyNode, NodeOutput=DummyNodeOutput)
    namespace: dict[str, object] = {
        "io": io,
        "torch": torch,
        "comfy": SimpleNamespace(
            utils=SimpleNamespace(
                common_upscale=common_upscale,
                repeat_to_batch_size=repeat_to_batch_size,
            )
        ),
    }
    exec(compile(ast.Module(body=selected, type_ignores=[]), str(NODE_SOURCE), "exec"), namespace)
    return {
        "camera_embeddings": namespace["camera_embeddings"],
        **{name: namespace[name] for name in wanted_classes},
    }


class FakeClipVision:
    def __init__(self, feature_width: int = 6) -> None:
        self.feature_width = feature_width
        self.inputs: list[torch.Tensor] = []

    def encode_image(self, image: torch.Tensor) -> SimpleNamespace:
        self.inputs.append(image)
        embeds = torch.arange(
            image.shape[0] * self.feature_width,
            dtype=torch.float32,
        ).reshape(image.shape[0], self.feature_width)
        return SimpleNamespace(image_embeds=embeds)


class FakeVAE:
    def __init__(self) -> None:
        self.inputs: list[torch.Tensor] = []

    def encode(self, image: torch.Tensor) -> torch.Tensor:
        self.inputs.append(image.clone())
        mono = image.movedim(-1, 1).mean(dim=1, keepdim=True)
        return torch.nn.functional.avg_pool2d(mono, 8, 8).repeat(1, 4, 1, 1)


class RecordingEmbedder:
    def __init__(self, width: int) -> None:
        self.width = width
        self.calls: list[torch.Tensor] = []

    def __call__(self, values: torch.Tensor) -> torch.Tensor:
        values = values.clone()
        self.calls.append(values)
        return values.reshape(-1, 1).repeat(1, self.width)


def unpack(output: DummyNodeOutput) -> tuple[Any, ...]:
    return tuple(output.values)


def camera_rows(elevations: list[float], azimuths: list[float]) -> torch.Tensor:
    return torch.tensor(
        [
            [
                math.radians(-elevation),
                math.sin(math.radians(azimuth)),
                math.cos(math.radians(azimuth)),
                math.pi / 2,
            ]
            for elevation, azimuth in zip(elevations, azimuths)
        ],
        dtype=torch.float32,
    ).unsqueeze(1)


def probe_zero123(nodes: dict[str, Any], image: torch.Tensor, expected_rgb: torch.Tensor) -> dict[str, object]:
    clip = FakeClipVision()
    vae = FakeVAE()
    positive, negative, latent = unpack(
        nodes["StableZero123_Conditioning"].execute(
            clip,
            image,
            vae,
            56,
            40,
            3,
            12.5,
            -30.0,
        )
    )
    positive_tensor, positive_meta = positive[0]
    negative_tensor, negative_meta = negative[0]
    expected_camera = camera_rows([12.5], [-30.0])

    multi_image_error = None
    try:
        nodes["StableZero123_Conditioning"].execute(
            FakeClipVision(), image.repeat(2, 1, 1, 1), FakeVAE(), 56, 40, 2, 0.0, 0.0
        )
    except RuntimeError as exc:
        multi_image_error = str(exc)

    return {
        "clipSawOriginalShape": list(clip.inputs[0].shape),
        "vaeSawResizedRgb": bool(torch.equal(vae.inputs[0], expected_rgb)),
        "positiveShape": list(positive_tensor.shape),
        "negativeShape": list(negative_tensor.shape),
        "cameraEncodingMatches": bool(
            torch.allclose(positive_tensor[..., -4:], expected_camera, atol=1e-6)
        ),
        "positiveReferenceLatentShape": list(positive_meta["concat_latent_image"].shape),
        "negativeReferenceIsZero": bool(
            torch.count_nonzero(negative_meta["concat_latent_image"]) == 0
        ),
        "latentShape": list(latent["samples"].shape),
        "latentIsZero": bool(torch.count_nonzero(latent["samples"]) == 0),
        "hasBatchIndex": "batch_index" in latent,
        "multiImageBatchShapeMismatch": multi_image_error is not None,
    }


def probe_zero123_batched(
    nodes: dict[str, Any], image: torch.Tensor, prepare_noise: Any
) -> dict[str, object]:
    clip = FakeClipVision()
    vae = FakeVAE()
    positive, negative, latent = unpack(
        nodes["StableZero123_Conditioning_Batched"].execute(
            clip,
            image,
            vae,
            56,
            40,
            4,
            10.0,
            -45.0,
            -5.0,
            30.0,
        )
    )
    elevations = [10.0, 5.0, 0.0, -5.0]
    azimuths = [-45.0, -15.0, 15.0, 45.0]
    expected_camera = camera_rows(elevations, azimuths)
    positive_tensor = positive[0][0]
    negative_tensor = negative[0][0]
    fixed_noise = prepare_noise(latent["samples"], 123, latent["batch_index"])
    random_noise = prepare_noise(latent["samples"], 123, None)
    fixed_equal = all(torch.equal(fixed_noise[0], fixed_noise[i]) for i in range(1, 4))
    random_differs = any(not torch.equal(random_noise[0], random_noise[i]) for i in range(1, 4))

    multi_image_error = None
    try:
        nodes["StableZero123_Conditioning_Batched"].execute(
            FakeClipVision(), image.repeat(2, 1, 1, 1), FakeVAE(), 56, 40, 2, 0.0, 0.0, 0.0, 1.0
        )
    except RuntimeError as exc:
        multi_image_error = str(exc)

    return {
        "positiveShape": list(positive_tensor.shape),
        "negativeShape": list(negative_tensor.shape),
        "cameraEncodingMatches": bool(
            torch.allclose(positive_tensor[..., -4:], expected_camera, atol=1e-6)
        ),
        "elevations": elevations,
        "azimuths": azimuths,
        "latentShape": list(latent["samples"].shape),
        "batchIndex": latent["batch_index"],
        "batchIndexMakesInitialNoiseIdentical": fixed_equal,
        "noiseWithoutBatchIndexDiffers": random_differs,
        "referenceLatentBatch": positive[0][1]["concat_latent_image"].shape[0],
        "multiImageBatchShapeMismatch": multi_image_error is not None,
    }


def probe_sv3d(nodes: dict[str, Any], image: torch.Tensor) -> dict[str, object]:
    positive, negative, latent = unpack(
        nodes["SV3D_Conditioning"].execute(
            FakeClipVision(), image, FakeVAE(), 56, 40, 5, 15.0
        )
    )
    positive_meta = positive[0][1]
    negative_meta = negative[0][1]
    single_positive, _, single_latent = unpack(
        nodes["SV3D_Conditioning"].execute(
            FakeClipVision(), image, FakeVAE(), 56, 40, 1, -7.5
        )
    )
    return {
        "elevations": positive_meta["elevation"],
        "azimuths": positive_meta["azimuth"],
        "negativeUsesSameSchedule": (
            negative_meta["elevation"] == positive_meta["elevation"]
            and negative_meta["azimuth"] == positive_meta["azimuth"]
        ),
        "referenceLatentShape": list(positive_meta["concat_latent_image"].shape),
        "latentShape": list(latent["samples"].shape),
        "latentIsZero": bool(torch.count_nonzero(latent["samples"]) == 0),
        "singleFrameElevation": single_positive[0][1]["elevation"],
        "singleFrameAzimuth": single_positive[0][1]["azimuth"],
        "singleFrameLatentShape": list(single_latent["samples"].shape),
    }


def probe_sv3d_model_angle_consumption() -> dict[str, object]:
    encode_u = extract_method(MODEL_SOURCE, "SV3D_u", "encode_adm")
    encode_p = extract_method(MODEL_SOURCE, "SV3D_p", "encode_adm")

    u_embedder = RecordingEmbedder(256)
    u_self = SimpleNamespace(embedder=u_embedder)
    u_a = encode_u(u_self, elevation=[10.0, 20.0], azimuth=[0.0, 180.0])
    u_b = encode_u(u_self, elevation=[-40.0, 80.0], azimuth=[90.0, 270.0])

    p_embedder = RecordingEmbedder(256)
    p_angles = RecordingEmbedder(512)
    p_self = SimpleNamespace(embedder=p_embedder, embedder_512=p_angles)
    elevations = [15.0] * 5
    azimuths = [0.0, 90.0, 180.0, 270.0, 360.0]
    p_output = encode_p(
        p_self,
        elevation=elevations,
        azimuth=azimuths,
        noise=torch.zeros(5, 4, 5, 7),
    )
    expected_polar = torch.deg2rad(torch.fmod(90 - torch.tensor(elevations), 360.0))
    expected_azimuth = torch.deg2rad(torch.fmod(torch.tensor(azimuths), 360.0))
    return {
        "uIgnoresCameraSchedules": bool(torch.equal(u_a, u_b)),
        "uAdmShape": list(u_a.shape),
        "pPolarInputMatches": bool(torch.allclose(p_angles.calls[0], expected_polar)),
        "pAzimuthInputMatches": bool(torch.allclose(p_angles.calls[1], expected_azimuth)),
        "pAdmShape": list(p_output.shape),
    }


def run() -> dict[str, object]:
    common_upscale = extract_common_upscale()
    repeat_to_batch_size = extract_repeat_to_batch_size()
    clip_preprocess = extract_clip_preprocess()
    prepare_noise = extract_prepare_noise()
    nodes = extract_nodes(common_upscale, repeat_to_batch_size)

    image = torch.linspace(0, 1, 1 * 37 * 61 * 4, dtype=torch.float32).reshape(1, 37, 61, 4)
    expected_rgb = common_upscale(
        image.movedim(-1, 1), 56, 40, "bilinear", "center"
    ).movedim(1, -1)[..., :3]
    clip_rgb = clip_preprocess(image, size=32)

    return {
        "helpers": {
            "clipPreprocessDropsAlpha": list(clip_rgb.shape) == [1, 3, 32, 32],
            "clipPreprocessFinite": bool(torch.isfinite(clip_rgb).all()),
        },
        "stableZero123": probe_zero123(nodes, image, expected_rgb),
        "stableZero123Batched": probe_zero123_batched(nodes, image, prepare_noise),
        "sv3d": probe_sv3d(nodes, image),
        "sv3dModels": probe_sv3d_model_angle_consumption(),
    }


if __name__ == "__main__":
    print(json.dumps(run(), ensure_ascii=False, sort_keys=True))
