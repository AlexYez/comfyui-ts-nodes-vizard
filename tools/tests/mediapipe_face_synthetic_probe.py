from __future__ import annotations

import ast
import json
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import numpy as np
import torch
from PIL import Image, ImageColor, ImageDraw


class DummyComfyNode:
    pass


class DummyNodeOutput:
    def __init__(self, *values: object) -> None:
        self.values = values


class DummyProgressBar:
    instances: list["DummyProgressBar"] = []

    def __init__(self, total: int) -> None:
        self.total = int(total)
        self.current = 0
        self.updates: list[int] = []
        self.instances.append(self)

    def update_absolute(self, value: int) -> None:
        self.current = int(value)
        self.updates.append(self.current)


class DummyTqdm:
    def __init__(self, *, total: int, desc: str) -> None:
        self.total = total
        self.desc = desc
        self.current = 0

    def __enter__(self) -> "DummyTqdm":
        return self

    def __exit__(self, *_args: object) -> None:
        return None

    def update(self, value: int) -> None:
        self.current += int(value)


def _compile_exact_module_parts(
    path: Path,
    *,
    namespace: dict[str, Any],
    functions: set[str] = frozenset(),
    classes: set[str] = frozenset(),
    assignments: set[str] = frozenset(),
) -> dict[str, Any]:
    """Compile selected top-level definitions from the pinned source verbatim."""

    source = path.read_text(encoding="utf-8")
    tree = ast.parse(source, filename=str(path))
    selected: list[ast.stmt] = []
    found_functions: set[str] = set()
    found_classes: set[str] = set()
    found_assignments: set[str] = set()

    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if node.name in functions:
                selected.append(node)
                found_functions.add(node.name)
        elif isinstance(node, ast.ClassDef):
            if node.name in classes:
                selected.append(node)
                found_classes.add(node.name)
        elif isinstance(node, (ast.Assign, ast.AnnAssign)):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            names = {
                target.id for target in targets if isinstance(target, ast.Name)
            }
            if names & assignments:
                selected.append(node)
                found_assignments.update(names & assignments)

    missing = {
        "functions": sorted(functions - found_functions),
        "classes": sorted(classes - found_classes),
        "assignments": sorted(assignments - found_assignments),
    }
    if any(missing.values()):
        raise AssertionError(f"missing exact source definitions in {path}: {missing}")

    future_annotations = ast.ImportFrom(
        module="__future__", names=[ast.alias(name="annotations")], level=0
    )
    module = ast.Module(body=[future_annotations, *selected], type_ignores=[])
    ast.fix_missing_locations(module)
    exec(compile(module, str(path), "exec"), namespace)
    return {
        name: namespace[name]
        for name in functions | classes | assignments
    }


def _canonical_data() -> dict[str, np.ndarray]:
    vertices = np.array(
        [
            [-1.0, -1.0, 0.0],
            [1.0, -1.0, 0.0],
            [1.0, 1.0, 0.0],
            [-1.0, 1.0, 0.0],
            [0.0, 0.0, 1.0],
        ],
        dtype=np.float32,
    )
    return {
        "canonical_vertices": vertices,
        "procrustes_indices": np.arange(len(vertices), dtype=np.int32),
        "procrustes_weights": np.ones(len(vertices), dtype=np.float32),
    }


def _face(
    x_offset: float,
    *,
    variant_code: float = 1.0,
    score: float = 0.75,
) -> dict[str, Any]:
    canonical = _canonical_data()["canonical_vertices"].copy()
    landmarks_xy = np.stack(
        [
            8.0 + x_offset + 2.0 * canonical[:, 0] + 0.2 * canonical[:, 2],
            8.0 + 2.0 * canonical[:, 1] + 0.1 * canonical[:, 2],
        ],
        axis=1,
    ).astype(np.float32)
    return {
        "bbox_xyxy": np.array(
            [5.0 + x_offset, 5.0, 11.0 + x_offset, 11.0], dtype=np.float32
        ),
        "blendshapes": {"variant": float(variant_code), "smile": 0.25},
        "landmarks_xy": landmarks_xy,
        "landmarks_3d": canonical,
        "presence": 0.8,
        "score": float(score),
    }


def _topology_payload() -> dict[str, Any]:
    points = np.array(
        [
            [2.0, 2.0],
            [9.0, 2.0],
            [9.0, 9.0],
            [2.0, 9.0],
            [4.0, 4.0],
            [7.0, 4.0],
            [7.0, 7.0],
            [4.0, 7.0],
            [11.0, 11.0],
            [15.0, 11.0],
        ],
        dtype=np.float32,
    )
    oval = frozenset({(0, 1), (1, 2), (2, 3), (3, 0)})
    inner = frozenset({(4, 5), (5, 6), (6, 7), (7, 4)})
    empty: frozenset[tuple[int, int]] = frozenset()
    sets = {
        "face_oval": oval,
        "lips": inner,
        "left_eye": empty,
        "right_eye": empty,
        "left_eyebrow": empty,
        "right_eyebrow": empty,
        "irises": empty,
        "nose": empty,
        "tesselation": frozenset({(8, 9)}),
    }
    first = {
        "landmarks_xy": points,
        "bbox_xyxy": np.array([2.0, 2.0, 15.0, 11.0], dtype=np.float32),
        "blendshapes": {},
        "landmarks_3d": np.pad(points, ((0, 0), (0, 1))),
        "presence": 1.0,
        "score": 1.0,
    }
    second = dict(first)
    second["landmarks_xy"] = points + np.array([3.0, 0.0], dtype=np.float32)
    return {
        "frames": [[first, second], []],
        "image_size": (20, 20),
        "connection_sets": sets,
    }


class FakeFolderPaths:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []

    def get_full_path_or_raise(self, category: str, filename: str) -> str:
        self.calls.append((category, filename))
        return f"/synthetic/models/{category}/{filename}"


class FakeLoadUtils:
    def __init__(self) -> None:
        self.calls: list[tuple[str, bool]] = []
        self.state = {"sentinel": torch.tensor([1.0])}

    def load_torch_file(self, path: str, *, safe_load: bool = False) -> dict[str, Any]:
        self.calls.append((path, safe_load))
        return self.state


class FakeWrapper:
    def __init__(self, state_dict: dict[str, Any]) -> None:
        self.state_dict = state_dict


class FakeDetectionModel:
    def __init__(self) -> None:
        self.canonical_data = _canonical_data()
        self.connection_sets = _topology_payload()["connection_sets"]
        self.calls: dict[str, list[dict[str, Any]]] = {"short": [], "full": []}

    def detect_batch(
        self,
        images: list[np.ndarray],
        *,
        num_faces: int,
        score_thresh: float,
        variant: str,
    ) -> list[list[dict[str, Any]]]:
        indices = [int(image[0, 0, 0]) for image in images]
        self.calls[variant].append(
            {
                "batch": len(images),
                "indices": indices,
                "num_faces": num_faces,
                "score_thresh": score_thresh,
            }
        )
        output: list[list[dict[str, Any]]] = []
        code = 1.0 if variant == "short" else 2.0
        for index in indices:
            remainder = index % 3
            if variant == "short":
                count = 2 if remainder == 0 else 1
            else:
                count = 2 if remainder == 1 else 1
            output.append(
                [
                    _face(index * 0.1 + face_index * 8.0, variant_code=code)
                    for face_index in range(count)
                ]
            )
        return output


def _nonzero_pixels(tensor: torch.Tensor) -> int:
    return int(torch.count_nonzero(tensor).item())


def run_probe(source_root: Path) -> dict[str, Any]:
    source_root = Path(source_root)
    node_path = source_root / "comfy_extras" / "nodes_mediapipe.py"
    geometry_path = source_root / "comfy_extras" / "mediapipe" / "face_geometry.py"

    geometry_namespace: dict[str, Any] = {"np": np, "math": __import__("math")}
    geometry = _compile_exact_module_parts(
        geometry_path,
        namespace=geometry_namespace,
        functions={
            "_solve_weighted_orthogonal_problem",
            "_estimate_scale",
            "solve_facial_transformation_matrix",
            "transformation_matrix_from_detection",
        },
    )

    fake_folder_paths = FakeFolderPaths()
    fake_load_utils = FakeLoadUtils()
    comfy = SimpleNamespace(
        utils=SimpleNamespace(ProgressBar=DummyProgressBar),
        model_management=SimpleNamespace(
            intermediate_device=lambda: torch.device("cpu"),
            intermediate_dtype=lambda: torch.float32,
        ),
    )
    io = SimpleNamespace(ComfyNode=DummyComfyNode, NodeOutput=DummyNodeOutput)
    namespace: dict[str, Any] = {
        "np": np,
        "torch": torch,
        "Image": Image,
        "ImageColor": ImageColor,
        "ImageDraw": ImageDraw,
        "comfy": comfy,
        "io": io,
        "folder_paths": fake_folder_paths,
        "FaceLandmarkerModel": FakeWrapper,
        "tqdm": lambda *, total, desc: DummyTqdm(total=total, desc=desc),
        "transformation_matrix_from_detection": geometry[
            "transformation_matrix_from_detection"
        ],
    }
    parts = _compile_exact_module_parts(
        node_path,
        namespace=namespace,
        functions={
            "_image_to_uint8",
            "_parse_color",
            "_copy_face",
            "_lerp_face",
            "_match_faces",
            "_fill_missing_frames",
            "_ordered_rings",
            "_draw_mesh",
        },
        classes={
            "LoadMediaPipeFaceLandmarker",
            "MediaPipeFaceLandmarker",
            "MediaPipeFaceMeshVisualize",
            "MediaPipeFaceMask",
        },
        assignments={
            "_CONTOUR_PARTS",
            "_FALLBACK_MODES",
            "_ALL_CONNECTION_PARTS",
            "_CUSTOM_FEATURES",
            "_MASK_REGIONS",
            "_MASK_CUSTOM_FEATURES",
        },
    )
    comfy.utils.load_torch_file = fake_load_utils.load_torch_file

    loader_output = parts["LoadMediaPipeFaceLandmarker"].execute(
        "mediapipe_face_fp32.safetensors"
    ).values[0]

    leading = [[], [_face(0.0)], []]
    parts["_fill_missing_frames"](leading, "previous")
    previous_copy_independent = (
        leading[2][0] is not leading[1][0]
        and leading[2][0]["landmarks_xy"] is not leading[1][0]["landmarks_xy"]
        and leading[2][0]["blendshapes"] is not leading[1][0]["blendshapes"]
    )
    bracketed = [[_face(0.0)], [], [_face(10.0)]]
    parts["_fill_missing_frames"](bracketed, "interpolate")
    interpolated_x = float(bracketed[1][0]["bbox_xyxy"][0])
    endpoints = [[], [_face(2.0)], [], []]
    parts["_fill_missing_frames"](endpoints, "interpolate")
    mismatch = [[_face(0.0), _face(20.0)], [], [_face(1.0)]]
    parts["_fill_missing_frames"](mismatch, "interpolate")

    fake_model = FakeDetectionModel()
    frame_values = torch.arange(18, dtype=torch.float32).view(18, 1, 1, 1) / 255.0
    images = frame_values.expand(18, 24, 24, 3).clone()
    original_images = images.clone()
    detector_output = parts["MediaPipeFaceLandmarker"].execute(
        fake_model,
        images,
        "both",
        0,
        0.5,
        "empty",
    ).values
    landmarks, bboxes = detector_output
    chosen_codes = [
        frame[0]["blendshapes"]["variant"] for frame in landmarks["frames"][:3]
    ]
    matrices = [
        face["transformation_matrix"]
        for frame in landmarks["frames"]
        for face in frame
    ]

    topology = _topology_payload()
    visualize = parts["MediaPipeFaceMeshVisualize"]
    black_all = visualize.execute(
        topology,
        {"connections": "all"},
        "not-a-color",
        1,
        0,
        image=None,
    ).values[0]
    custom_tessellation = visualize.execute(
        topology,
        {"connections": "custom", "tesselation": True},
        "#ff0000",
        1,
        0,
        image=None,
    ).values[0]
    custom_points = visualize.execute(
        topology,
        {"connections": "custom"},
        "#0000ff",
        0,
        2,
        image=None,
    ).values[0]
    fill = visualize.execute(
        topology,
        {"connections": "fill"},
        "#ff0000",
        0,
        16,
        image=None,
    ).values[0]
    external = torch.full((3, 20, 20, 3), 0.25, dtype=torch.float32)
    external_copy = visualize.execute(
        topology,
        {"connections": "custom"},
        "#ffffff",
        0,
        0,
        image=external,
    ).values[0]

    mask_node = parts["MediaPipeFaceMask"]
    mask_all = mask_node.execute(topology, {"regions": "all"}).values[0]
    mask_none = mask_node.execute(
        topology,
        {
            "regions": "custom",
            "face_oval": False,
            "lips": False,
            "left_eye": False,
            "right_eye": False,
            "irises": False,
        },
    ).values[0]
    mask_lips = mask_node.execute(
        topology,
        {"regions": "custom", "lips": True},
    ).values[0]
    single_face_payload = dict(topology)
    single_face_payload["frames"] = [[topology["frames"][0][0]]]
    mask_single = mask_node.execute(
        single_face_payload, {"regions": "custom", "face_oval": True}
    ).values[0]

    canonical = _canonical_data()
    canonical_vertices = canonical["canonical_vertices"]
    geometry_face = _face(0.0)
    matrix = geometry["transformation_matrix_from_detection"](
        geometry_face, 24, 24, canonical
    )
    degenerate_raised = False
    try:
        geometry["_solve_weighted_orthogonal_problem"](
            np.zeros((3, 4), dtype=np.float32),
            np.zeros((3, 4), dtype=np.float32),
            np.ones(4, dtype=np.float32),
        )
    except ValueError as error:
        degenerate_raised = "denominator collapsed" in str(error)

    return {
        "workflowExampleExecuted": False,
        "networkUsed": False,
        "weightsLoaded": False,
        "gpuUsed": False,
        "loader": {
            "folderCalls": fake_folder_paths.calls,
            "loadCalls": fake_load_utils.calls,
            "safeLoad": fake_load_utils.calls == [
                (
                    "/synthetic/models/detection/mediapipe_face_fp32.safetensors",
                    True,
                )
            ],
            "wrapperReceivedExactState": loader_output.state_dict
            is fake_load_utils.state,
        },
        "fallback": {
            "previousLeadingEmpty": leading[0] == [],
            "previousFilledTrailing": len(leading[2]) == 1,
            "previousCopyIndependent": previous_copy_independent,
            "interpolatedFirstX": interpolated_x,
            "endpointCounts": [len(frame) for frame in endpoints],
            "mismatchedCount": len(mismatch[1]),
        },
        "detector": {
            "inputUnchanged": torch.equal(images, original_images),
            "shortChunks": [call["batch"] for call in fake_model.calls["short"]],
            "fullChunks": [call["batch"] for call in fake_model.calls["full"]],
            "forwardedNumFaces": sorted(
                {call["num_faces"] for calls in fake_model.calls.values() for call in calls}
            ),
            "forwardedThresholds": sorted(
                {call["score_thresh"] for calls in fake_model.calls.values() for call in calls}
            ),
            "chosenVariantCodes": chosen_codes,
            "frameCount": len(landmarks["frames"]),
            "bboxFrameCount": len(bboxes),
            "firstBBox": bboxes[0][0],
            "allMatricesFinite4x4": bool(
                matrices
                and all(
                    value.shape == (4, 4) and np.isfinite(value).all()
                    for value in matrices
                )
            ),
        },
        "visualize": {
            "blackCanvasShape": list(black_all.shape),
            "invalidColorFallsBackGreen": bool(
                black_all[0, 2, 5, 1] > 0.9
                and black_all[0, 2, 5, 0] == 0
                and black_all[0, 2, 5, 2] == 0
            ),
            "allOmitsTessellation": bool(torch.all(black_all[0, 11, 13] == 0)),
            "customDrawsTessellation": bool(custom_tessellation[0, 11, 13, 0] > 0.9),
            "customEmptyStillDrawsPoints": bool(custom_points[0, 11, 11, 2] > 0.9),
            "fillIgnoresPointDrawing": bool(
                fill[0, 5, 5, 0] > 0.9 and torch.all(fill[0, 11, 11] == 0)
            ),
            "externalBatchShape": list(external_copy.shape),
            "extraExternalFrameUnchanged": bool(
                torch.allclose(external_copy[2], external[2], atol=1.0 / 255.0)
            ),
        },
        "mask": {
            "shape": list(mask_all.shape),
            "binaryValues": sorted(float(value) for value in torch.unique(mask_all)),
            "emptyFrameZero": _nonzero_pixels(mask_all[1]) == 0,
            "customNoneZero": _nonzero_pixels(mask_none) == 0,
            "lipsSmallerThanAll": _nonzero_pixels(mask_lips[0])
            < _nonzero_pixels(mask_all[0]),
            "multipleFacesUnion": _nonzero_pixels(mask_all[0])
            > _nonzero_pixels(mask_single[0]),
        },
        "geometry": {
            "shape": list(matrix.shape),
            "finite": bool(np.isfinite(matrix).all()),
            "homogeneousBottomRow": matrix[3].tolist(),
            "canonicalShape": list(canonical_vertices.shape),
            "degenerateRaised": degenerate_raised,
        },
    }


def main() -> int:
    if len(sys.argv) != 2:
        raise SystemExit(
            "usage: mediapipe_face_synthetic_probe.py <pinned-comfyui-source>"
        )
    print(json.dumps(run_probe(Path(sys.argv[1])), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
