from __future__ import annotations

import __future__
import ast
import io
import json
import logging
import os
import sys
import tempfile
import time
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import torch


ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / ".comfyui-source-0.32.0"


def extract_nodes(
    path: Path,
    *,
    classes: set[str] = frozenset(),
    functions: set[str] = frozenset(),
    namespace: dict[str, Any],
) -> dict[str, Any]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    selected: list[ast.stmt] = []
    for node in tree.body:
        if isinstance(node, ast.ClassDef) and node.name in classes:
            selected.append(node)
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name in functions:
            selected.append(node)
    expected = classes | functions
    found = {node.name for node in selected}  # type: ignore[attr-defined]
    if found != expected:
        raise AssertionError(f"missing exact definitions in {path}: {sorted(expected - found)}")
    code = compile(
        ast.Module(body=selected, type_ignores=[]),
        str(path),
        "exec",
        flags=__future__.annotations.compiler_flag,
        dont_inherit=True,
    )
    exec(code, namespace)
    return {name: namespace[name] for name in expected}


class FakeNodeOutput:
    def __init__(self, *values: Any, ui: dict[str, Any] | None = None) -> None:
        self.values = values
        self.ui = ui or {}


class FakeSavedResult:
    def __init__(self, *, filename: str, subfolder: str, type: str) -> None:
        self.filename = filename
        self.subfolder = subfolder
        self.type = type


class FakeSVG:
    Type = object


def load_folder_helpers() -> dict[str, Any]:
    namespace: dict[str, Any] = {"os": os, "time": time, "logging": logging}
    return extract_nodes(
        SOURCE / "folder_paths.py",
        functions={"is_within_directory", "get_save_image_path"},
        namespace=namespace,
    )


def run_svg_probe(folder_helpers: dict[str, Any]) -> dict[str, Any]:
    with tempfile.TemporaryDirectory(prefix="nodes-wizard-svg-") as temp:
        output = Path(temp) / "output"
        output.mkdir()
        folder_paths = SimpleNamespace(
            get_output_directory=lambda: str(output),
            get_save_image_path=folder_helpers["get_save_image_path"],
        )
        IO = SimpleNamespace(
            ComfyNode=object,
            SVG=FakeSVG,
            NodeOutput=FakeNodeOutput,
            FolderType=SimpleNamespace(output="output"),
        )
        UI = SimpleNamespace(SavedResult=FakeSavedResult)
        namespace: dict[str, Any] = {
            "IO": IO,
            "UI": UI,
            "folder_paths": folder_paths,
            "json": json,
            "os": os,
            "re": __import__("re"),
        }
        SaveSVGNode = extract_nodes(
            SOURCE / "comfy_extras" / "nodes_images.py",
            classes={"SaveSVGNode"},
            namespace=namespace,
        )["SaveSVGNode"]

        first = io.BytesIO(b'<svg xmlns="http://www.w3.org/2000/svg"><rect/></svg>')
        second = io.BytesIO(b"<svg><g><svg><circle/></svg></g></svg>")
        svg = SimpleNamespace(data=[first, second])
        SaveSVGNode.hidden = SimpleNamespace(
            prompt={"from": "prompt"},
            extra_pnginfo={"prompt": {"from": "extra"}, "workflow": {"id": "synthetic"}},
        )
        result = SaveSVGNode.execute(svg, "svg/wizard-%batch_num%")
        files = sorted((output / "svg").glob("*.svg"))
        texts = [path.read_text(encoding="utf-8") for path in files]
        assert result.values == (svg,)
        assert [path.name for path in files] == [
            "wizard-0_00001_.svg",
            "wizard-1_00002_.svg",
        ]
        assert [item.filename for item in result.ui["images"]] == [
            "wizard-0_00001_.svg",
            "wizard-1_00002_.svg",
        ]
        assert [stream.tell() for stream in svg.data] == [len(first.getvalue()), len(second.getvalue())]
        assert texts[0].count("<metadata>") == 1
        assert texts[1].count("<metadata>") == 2
        assert '"from": "extra"' in texts[0] and '"from": "prompt"' not in texts[0]

        no_tag = SimpleNamespace(data=[io.BytesIO(b"not-an-svg-tag")])
        SaveSVGNode.hidden = SimpleNamespace(prompt={"still": "present"}, extra_pnginfo=None)
        no_tag_result = SaveSVGNode.execute(no_tag, "svg/no-tag")
        no_tag_path = output / "svg" / no_tag_result.ui["images"][0].filename
        assert no_tag_path.read_text(encoding="utf-8") == "not-an-svg-tag"

        broken_cdata = SimpleNamespace(data=[io.BytesIO(b"<svg/>")])
        SaveSVGNode.hidden = SimpleNamespace(prompt={"text": "]] >".replace(" ", "")}, extra_pnginfo=None)
        cdata_result = SaveSVGNode.execute(broken_cdata, "svg/cdata")
        cdata_text = (output / "svg" / cdata_result.ui["images"][0].filename).read_text(encoding="utf-8")
        assert '"text": "]]>"' in cdata_text
        assert cdata_text.count("]]>") == 2

        invalid = SimpleNamespace(data=[io.BytesIO(b"\xff\xfe")])
        SaveSVGNode.hidden = SimpleNamespace(prompt=None, extra_pnginfo=None)
        try:
            SaveSVGNode.execute(invalid, "svg/invalid")
        except UnicodeDecodeError:
            invalid_utf8_rejected = True
        else:
            invalid_utf8_rejected = False
        assert invalid_utf8_rejected

        return {
            "files": [path.name for path in files],
            "passthroughIdentity": result.values[0] is svg,
            "cursorAtEof": [stream.tell() == len(stream.getvalue()) for stream in svg.data],
            "metadataCounts": [text.count("<metadata>") for text in texts],
            "extraPromptOverridesHiddenPrompt": '"from": "extra"' in texts[0],
            "noSvgTagStillWritten": no_tag_path.read_text(encoding="utf-8") == "not-an-svg-tag",
            "cdataTerminatorUnescaped": (
                '"text": "]]>"' in cdata_text and cdata_text.count("]]>") == 2
            ),
            "invalidUtf8Rejected": invalid_utf8_rejected,
        }


def run_video_nodes_probe() -> dict[str, Any]:
    load_calls: list[dict[str, Any]] = []

    def load_checkpoint_guess_config(path: str, **kwargs: Any) -> tuple[Any, ...]:
        load_calls.append({"path": path, **kwargs})
        return ("MODEL", "TEXT_CLIP", "VAE", "CLIP_VISION")

    folder_paths = SimpleNamespace(
        get_filename_list=lambda _kind: ["svd_xt.safetensors"],
        get_full_path_or_raise=lambda kind, name: f"/{kind}/{name}",
        get_folder_paths=lambda kind: [f"/{kind}"],
    )
    comfy = SimpleNamespace(
        sd=SimpleNamespace(load_checkpoint_guess_config=load_checkpoint_guess_config),
        utils=SimpleNamespace(common_upscale=None),
    )
    fake_checkpoint_calls: list[dict[str, Any]] = []

    class FakeCheckpointSave:
        RETURN_TYPES: tuple[Any, ...] = ()
        FUNCTION = "save"
        OUTPUT_NODE = True
        SEARCH_ALIASES = ["save model", "export checkpoint", "merge save"]

        def __init__(self) -> None:
            self.output_dir = "/synthetic-output"

    def capture_image_only_save(model: Any, **kwargs: Any) -> None:
        fake_checkpoint_calls.append({"model": model, **kwargs})

    comfy_extras = SimpleNamespace(
        nodes_model_merging=SimpleNamespace(
            CheckpointSave=FakeCheckpointSave,
            save_checkpoint=capture_image_only_save,
        )
    )
    nodes_namespace: dict[str, Any] = {
        "nodes": SimpleNamespace(MAX_RESOLUTION=16384),
        "torch": torch,
        "comfy": comfy,
        "folder_paths": folder_paths,
        "comfy_extras": comfy_extras,
    }
    classes = extract_nodes(
        SOURCE / "comfy_extras" / "nodes_video_model.py",
        classes={"ImageOnlyCheckpointLoader", "SVD_img2vid_Conditioning", "ImageOnlyCheckpointSave"},
        namespace=nodes_namespace,
    )

    loader = classes["ImageOnlyCheckpointLoader"]()
    loaded = loader.load_checkpoint("svd_xt.safetensors", output_vae=False, output_clip=True)
    assert loaded == ("MODEL", "CLIP_VISION", "VAE")
    assert load_calls == [
        {
            "path": "/checkpoints/svd_xt.safetensors",
            "output_vae": True,
            "output_clip": False,
            "output_clipvision": True,
            "embedding_directory": ["/embeddings"],
        }
    ]

    folder_paths.get_full_path_or_raise = lambda _kind, _name: (_ for _ in ()).throw(FileNotFoundError("missing"))
    try:
        loader.load_checkpoint("missing.safetensors")
    except FileNotFoundError:
        path_error_propagated = True
    else:
        path_error_propagated = False
    assert path_error_propagated

    class FakeClipVision:
        def __init__(self) -> None:
            self.inputs: list[torch.Tensor] = []

        def encode_image(self, image: torch.Tensor) -> Any:
            self.inputs.append(image)
            embeds = torch.arange(image.shape[0] * 3, dtype=torch.float32).reshape(image.shape[0], 3)
            return SimpleNamespace(image_embeds=embeds)

    class FakeVAE:
        def __init__(self) -> None:
            self.inputs: list[torch.Tensor] = []

        def encode(self, image: torch.Tensor) -> torch.Tensor:
            self.inputs.append(image.clone())
            return torch.ones((image.shape[0], 4, image.shape[1] // 8, image.shape[2] // 8))

    # Use the exact pinned common_upscale implementation for the bilinear path.
    upscale_namespace: dict[str, Any] = {"torch": torch, "bislerp": None, "lanczos": None}
    common_upscale = extract_nodes(
        SOURCE / "comfy" / "utils.py",
        functions={"common_upscale"},
        namespace=upscale_namespace,
    )["common_upscale"]
    comfy.utils.common_upscale = common_upscale

    conditioning = classes["SVD_img2vid_Conditioning"]()
    clip = FakeClipVision()
    vae = FakeVAE()
    image = (
        torch.arange(12, dtype=torch.float32)
        .reshape(1, 12, 1, 1)
        .expand(1, 12, 16, 3)
        .clone()
        / 11
    )
    positive, negative, latent = conditioning.encode(
        clip,
        image,
        vae,
        width=16,
        height=8,
        video_frames=5,
        motion_bucket_id=127,
        fps=6,
        augmentation_level=0.0,
    )
    assert clip.inputs[0] is image
    assert vae.inputs[0].shape == (1, 8, 16, 3)
    assert torch.equal(vae.inputs[0], image[:, 2:10, :, :])
    assert positive[0][0].shape == (1, 1, 3)
    assert torch.count_nonzero(negative[0][0]) == 0
    assert torch.count_nonzero(negative[0][1]["concat_latent_image"]) == 0
    assert latent["samples"].shape == (5, 4, 1, 2)
    assert latent["samples"].device.type == "cpu" and latent["samples"].dtype == torch.float32
    assert positive[0][1]["motion_bucket_id"] == 127
    assert positive[0][1]["fps"] == 6

    direct_floor = conditioning.encode(
        FakeClipVision(),
        torch.zeros((1, 9, 17, 3)),
        FakeVAE(),
        width=17,
        height=9,
        video_frames=2,
        motion_bucket_id=1,
        fps=1,
        augmentation_level=0.0,
    )[2]["samples"].shape
    assert direct_floor == (2, 4, 1, 2)

    rgba = torch.zeros((1, 8, 16, 4))
    rgba_vae = FakeVAE()
    conditioning.encode(
        FakeClipVision(), rgba, rgba_vae, 16, 8, 2, 127, 6, 0.0
    )
    assert rgba_vae.inputs[0].shape[-1] == 3
    try:
        conditioning.encode(
            FakeClipVision(), rgba, FakeVAE(), 16, 8, 2, 127, 6, 0.1
        )
    except RuntimeError:
        rgba_augmentation_fails = True
    else:
        rgba_augmentation_fails = False
    assert rgba_augmentation_fails

    save = classes["ImageOnlyCheckpointSave"]()
    save_result = save.save(
        "MODEL",
        "CLIP_VISION",
        "VAE",
        "checkpoints/wizard",
        prompt={"node": "save"},
        extra_pnginfo={"workflow": {"id": "synthetic"}},
    )
    assert save_result == {}
    assert fake_checkpoint_calls == [
        {
            "model": "MODEL",
            "clip_vision": "CLIP_VISION",
            "vae": "VAE",
            "filename_prefix": "checkpoints/wizard",
            "output_dir": "/synthetic-output",
            "prompt": {"node": "save"},
            "extra_pnginfo": {"workflow": {"id": "synthetic"}},
        }
    ]

    return {
        "loader": {
            "outputs": list(loaded),
            "call": load_calls[0],
            "pathErrorPropagated": path_error_propagated,
        },
        "conditioning": {
            "clipReceivesOriginalIdentity": clip.inputs[0] is image,
            "vaeInputShape": list(vae.inputs[0].shape),
            "centerCropMatchesExpected": torch.equal(vae.inputs[0], image[:, 2:10, :, :]),
            "positiveShape": list(positive[0][0].shape),
            "negativeZero": int(torch.count_nonzero(negative[0][0])) == 0,
            "latentShape": list(latent["samples"].shape),
            "latentDevice": latent["samples"].device.type,
            "latentDtype": str(latent["samples"].dtype),
            "directNonMultipleOfEightShape": list(direct_floor),
            "rgbaAlphaDroppedAtZeroAugmentation": rgba_vae.inputs[0].shape[-1] == 3,
            "rgbaAugmentationShapeError": rgba_augmentation_fails,
        },
        "imageOnlySave": {
            "returnsEmptyObject": save_result == {},
            "call": fake_checkpoint_calls[0],
            "inheritedOutputNode": bool(save.OUTPUT_NODE),
        },
    }


class SVDModelBase:
    pass


class ModelSamplingContinuousEDM:
    pass


class VPredictionSampling:
    pass


class SVDModelSampling(ModelSamplingContinuousEDM, VPredictionSampling):
    sigma_max = 700.0
    sigma_min = 0.002
    zsnr = False


class FakeSVDModel:
    def __init__(self) -> None:
        self.model = SVDModelBase()
        self.model.model_type = "v_prediction_edm"
        self.sampling = SVDModelSampling()

    def get_model_object(self, name: str) -> Any:
        assert name == "model_sampling"
        return self.sampling


def run_shared_checkpoint_probe(folder_helpers: dict[str, Any]) -> dict[str, Any]:
    captures: list[dict[str, Any]] = []
    args = SimpleNamespace(disable_metadata=False)

    with tempfile.TemporaryDirectory(prefix="nodes-wizard-image-only-save-") as temp:
        output = Path(temp) / "output"
        output.mkdir()

        def capture_save(
            path: str,
            model: Any,
            clip: Any = None,
            vae: Any = None,
            clip_vision: Any = None,
            metadata: dict[str, str] | None = None,
            extra_keys: dict[str, torch.Tensor] | None = None,
        ) -> None:
            captures.append(
                {
                    "path": Path(path).relative_to(output).as_posix(),
                    "clip": clip is not None,
                    "vae": vae is not None,
                    "clipVision": clip_vision is not None,
                    "metadata": dict(metadata or {}),
                    "extraKeys": sorted((extra_keys or {}).keys()),
                }
            )

        comfy = SimpleNamespace(
            model_base=SimpleNamespace(
                SDXL=type("SDXL", (), {}),
                SDXL_instructpix2pix=type("SDXLEdit", (), {}),
                SDXLRefiner=type("SDXLRefiner", (), {}),
                SVD_img2vid=SVDModelBase,
                SD3=type("SD3", (), {}),
                ModelType=SimpleNamespace(EPS="eps", V_PREDICTION="v_prediction"),
            ),
            model_sampling=SimpleNamespace(
                ModelSamplingContinuousEDM=ModelSamplingContinuousEDM,
                V_PREDICTION=VPredictionSampling,
            ),
            sd=SimpleNamespace(save_checkpoint=capture_save),
        )
        folder_paths = SimpleNamespace(get_save_image_path=folder_helpers["get_save_image_path"])
        namespace: dict[str, Any] = {
            "comfy": comfy,
            "folder_paths": folder_paths,
            "json": json,
            "os": os,
            "torch": torch,
            "args": args,
        }
        save_checkpoint = extract_nodes(
            SOURCE / "comfy_extras" / "nodes_model_merging.py",
            functions={"save_checkpoint"},
            namespace=namespace,
        )["save_checkpoint"]
        save_checkpoint(
            FakeSVDModel(),
            clip_vision=object(),
            vae=object(),
            filename_prefix="checkpoints/svd",
            output_dir=str(output),
            prompt={"node": "ImageOnlyCheckpointSave"},
            extra_pnginfo={"workflow": {"id": "synthetic"}},
        )
        base = captures[0]
        assert base["path"] == "checkpoints/svd_00001_.safetensors"
        assert base["clip"] is False and base["clipVision"] and base["vae"]
        assert base["extraKeys"] == ["edm_vpred.sigma_max", "edm_vpred.sigma_min"]
        assert "modelspec.predict_key" not in base["metadata"]
        assert base["metadata"]["modelspec.architecture"] == "stable-video-diffusion-img2vid-v1"
        assert base["metadata"]["prompt"] == '{"node": "ImageOnlyCheckpointSave"}'

        save_checkpoint(
            FakeSVDModel(),
            clip_vision=object(),
            vae=object(),
            filename_prefix="checkpoints/svd-collision",
            output_dir=str(output),
            prompt={"node": "ImageOnlyCheckpointSave"},
            extra_pnginfo={"modelspec.architecture": "override", "prompt": "extra"},
        )
        collision = captures[1]
        assert collision["metadata"]["modelspec.architecture"] == '"override"'
        assert collision["metadata"]["prompt"] == '"extra"'
        return {"base": base, "collision": collision}


def run_probe() -> dict[str, Any]:
    folder_helpers = load_folder_helpers()
    return {
        "workflowExampleExecuted": False,
        "svg": run_svg_probe(folder_helpers),
        "videoNodes": run_video_nodes_probe(),
        "sharedCheckpoint": run_shared_checkpoint_probe(folder_helpers),
    }


if __name__ == "__main__":
    print(json.dumps(run_probe(), ensure_ascii=False, sort_keys=True))
