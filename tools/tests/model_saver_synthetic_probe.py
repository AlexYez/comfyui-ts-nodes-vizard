from __future__ import annotations

import ast
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


PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


TARGET_CLASSES = {"CheckpointSave", "CLIPSave", "VAESave", "ModelSave"}


def _extract_functions(path: Path, names: set[str], namespace: dict[str, Any]) -> dict[str, Any]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    nodes = [
        node
        for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name in names
    ]
    found = {node.name for node in nodes}
    if found != names:
        raise AssertionError(f"missing functions in {path}: {sorted(names - found)}")
    exec(compile(ast.Module(body=nodes, type_ignores=[]), str(path), "exec"), namespace)
    return {name: namespace[name] for name in names}


def _extract_savers(path: Path, namespace: dict[str, Any]) -> dict[str, type]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    nodes: list[ast.stmt] = []
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name == "save_checkpoint":
            nodes.append(node)
        elif isinstance(node, ast.ClassDef) and node.name in TARGET_CLASSES:
            nodes.append(node)
    exec(compile(ast.Module(body=nodes, type_ignores=[]), str(path), "exec"), namespace)
    return {name: namespace[name] for name in TARGET_CLASSES}


class _SDXL:
    pass


class _SDXLEdit(_SDXL):
    pass


class _SDXLRefiner:
    pass


class _SVD:
    pass


class _SD3:
    pass


class _UnknownModel:
    pass


class _EDM:
    pass


class _VPredictionSampling:
    pass


class _EDMVPrediction(_EDM, _VPredictionSampling):
    sigma_max = 80.0
    sigma_min = 0.002
    zsnr = True


class _BasicSampling:
    zsnr = False


class _Model:
    def __init__(self, model_base: Any, model_type: str, sampling: Any) -> None:
        self.model = model_base
        self.model.model_type = model_type
        self._sampling = sampling

    def get_model_object(self, name: str) -> Any:
        assert name == "model_sampling"
        return self._sampling


class _Clip:
    def __init__(self, state: dict[str, torch.Tensor]) -> None:
        self.state = state
        self.loaded = 0

    def load_model(self) -> "_Clip":
        self.loaded += 1
        return self

    def state_dict_for_saving(self) -> dict[str, torch.Tensor]:
        return dict(self.state)


class _VAE:
    def __init__(self, state: dict[str, torch.Tensor]) -> None:
        self.state = state
        self.calls = 0

    def get_sd(self) -> dict[str, torch.Tensor]:
        self.calls += 1
        return dict(self.state)


def run_probe(source_root: Path) -> dict[str, Any]:
    folder_namespace: dict[str, Any] = {
        "os": os,
        "time": time,
        "logging": logging,
    }
    folder_functions = _extract_functions(
        source_root / "folder_paths.py",
        {"is_within_directory", "get_save_image_path"},
        folder_namespace,
    )

    utils_namespace: dict[str, Any] = {}
    utils_functions = _extract_functions(
        source_root / "comfy" / "utils.py",
        {"state_dict_prefix_replace"},
        utils_namespace,
    )

    checkpoint_writes: list[dict[str, Any]] = []
    tensor_writes: list[dict[str, Any]] = []
    args = SimpleNamespace(disable_metadata=False)

    with tempfile.TemporaryDirectory(prefix="nodes-wizard-model-savers-") as tmp:
        output_dir = Path(tmp) / "output"
        output_dir.mkdir()

        def capture_tensor_write(
            state: dict[str, torch.Tensor],
            path: str,
            metadata: dict[str, str] | None = None,
        ) -> None:
            target = Path(path)
            target.write_bytes(b"synthetic capture; not a safetensors payload")
            tensor_writes.append(
                {
                    "path": target.relative_to(output_dir).as_posix(),
                    "keys": sorted(state),
                    "metadata": dict(metadata or {}),
                }
            )

        def capture_checkpoint_write(
            path: str,
            model: Any,
            clip: Any = None,
            vae: Any = None,
            clip_vision: Any = None,
            metadata: dict[str, str] | None = None,
            extra_keys: dict[str, torch.Tensor] | None = None,
        ) -> None:
            target = Path(path)
            target.write_bytes(b"synthetic checkpoint capture; not a safetensors payload")
            extras = extra_keys or {}
            checkpoint_writes.append(
                {
                    "path": target.relative_to(output_dir).as_posix(),
                    "clip": clip is not None,
                    "vae": vae is not None,
                    "clipVision": clip_vision is not None,
                    "metadata": dict(metadata or {}),
                    "extraKeys": sorted(extras),
                    "extraScalars": {
                        key: float(value)
                        for key, value in extras.items()
                        if value.numel() == 1
                    },
                }
            )

        folder_paths = SimpleNamespace(
            get_output_directory=lambda: str(output_dir),
            get_save_image_path=folder_functions["get_save_image_path"],
            is_within_directory=folder_functions["is_within_directory"],
        )
        comfy = SimpleNamespace(
            model_base=SimpleNamespace(
                SDXL=_SDXL,
                SDXL_instructpix2pix=_SDXLEdit,
                SDXLRefiner=_SDXLRefiner,
                SVD_img2vid=_SVD,
                SD3=_SD3,
                ModelType=SimpleNamespace(EPS="eps", V_PREDICTION="v"),
            ),
            model_sampling=SimpleNamespace(
                ModelSamplingContinuousEDM=_EDM,
                V_PREDICTION=_VPredictionSampling,
            ),
            sd=SimpleNamespace(save_checkpoint=capture_checkpoint_write),
            utils=SimpleNamespace(
                state_dict_prefix_replace=utils_functions["state_dict_prefix_replace"],
                save_torch_file=capture_tensor_write,
            ),
        )
        saver_namespace: dict[str, Any] = {
            "comfy": comfy,
            "folder_paths": folder_paths,
            "json": json,
            "os": os,
            "torch": torch,
            "args": args,
        }
        classes = _extract_savers(
            source_root / "comfy_extras" / "nodes_model_merging.py",
            saver_namespace,
        )

        # The exact helper rejects traversal, creates folders, and derives counters
        # from existing names. Two calls before a file is created demonstrate that
        # the counter is not reserved atomically.
        first = folder_paths.get_save_image_path("race/same", str(output_dir))[2]
        second = folder_paths.get_save_image_path("race/same", str(output_dir))[2]
        assert (first, second) == (1, 1)
        counter_dir = output_dir / "counter"
        counter_dir.mkdir()
        (counter_dir / "sample_00004_.safetensors").write_bytes(b"x")
        (counter_dir / "sample_bad_.safetensors").write_bytes(b"x")
        assert folder_paths.get_save_image_path("counter/sample", str(output_dir))[2] == 5
        previous_disable = logging.root.manager.disable
        logging.disable(logging.CRITICAL)
        try:
            try:
                folder_paths.get_save_image_path("../escape", str(output_dir))
            except Exception:
                traversal_rejected = True
            else:
                traversal_rejected = False
        finally:
            logging.disable(previous_disable)
        assert traversal_rejected

        clip = _Clip(
            {
                "clip_l.transformer.encoder.weight": torch.tensor([1.0]),
                "clip_g.text_projection": torch.tensor([2.0]),
                "transformer.shared.weight": torch.tensor([3.0]),
                "custom.bias": torch.tensor([4.0]),
            }
        )
        clip_result = classes["CLIPSave"]().save(
            clip,
            "clip/test",
            prompt={"1": {"class_type": "CLIPSave"}},
            extra_pnginfo={"workflow": {"id": "synthetic"}},
        )
        assert clip_result == {}
        assert clip.loaded == 1
        clip_writes = list(tensor_writes)
        assert [entry["path"] for entry in clip_writes] == [
            "clip/test_clip_l_00001_.safetensors",
            "clip/test_clip_g_00001_.safetensors",
            "clip/test_00001_.safetensors",
        ]
        assert clip_writes[0]["keys"] == ["encoder.weight"]
        assert clip_writes[1]["keys"] == ["text_projection"]
        assert clip_writes[2]["keys"] == ["custom.bias", "shared.weight"]
        assert all(entry["metadata"]["format"] == "pt" for entry in clip_writes)

        vae = _VAE({"decoder.weight": torch.tensor([5.0])})
        vae_node = classes["VAESave"]()
        first_vae = vae_node.save(
            vae,
            "vae/test",
            prompt={"2": {"class_type": "VAESave"}},
            extra_pnginfo={"workflow": {"id": "synthetic"}},
        )
        second_vae = vae_node.save(vae, "vae/test")
        assert first_vae == second_vae == {}
        assert vae.calls == 2
        vae_writes = tensor_writes[3:]
        assert [entry["path"] for entry in vae_writes] == [
            "vae/test_00001_.safetensors",
            "vae/test_00002_.safetensors",
        ]
        assert vae_writes[0]["keys"] == ["decoder.weight"]
        assert "prompt" in vae_writes[0]["metadata"]

        edit_model = _Model(_SDXLEdit(), "v", _EDMVPrediction())
        checkpoint_result = classes["CheckpointSave"]().save(
            edit_model,
            clip,
            vae,
            "checkpoints/test",
            prompt={"3": {"class_type": "CheckpointSave"}},
            extra_pnginfo={"workflow": {"id": "synthetic"}},
        )
        assert checkpoint_result == {}
        checkpoint = checkpoint_writes[-1]
        assert checkpoint["clip"] and checkpoint["vae"] and not checkpoint["clipVision"]
        assert checkpoint["metadata"]["modelspec.architecture"] == "stable-diffusion-xl-v1-edit"
        assert checkpoint["metadata"]["modelspec.predict_key"] == "v"
        assert checkpoint["extraKeys"] == [
            "edm_vpred.sigma_max",
            "edm_vpred.sigma_min",
            "v_pred",
            "ztsnr",
        ]
        assert checkpoint["extraScalars"] == {
            "edm_vpred.sigma_max": 80.0,
            "edm_vpred.sigma_min": 0.0020000000949949026,
        }

        args.disable_metadata = True
        eps_model = _Model(_UnknownModel(), "eps", _BasicSampling())
        model_result = classes["ModelSave"]().save(
            eps_model,
            "diffusion_models/test",
            prompt={"4": {"class_type": "ModelSave"}},
            extra_pnginfo={"workflow": {"id": "must-not-be-written"}},
        )
        assert model_result == {}
        model_write = checkpoint_writes[-1]
        assert not model_write["clip"] and not model_write["vae"]
        assert model_write["metadata"] == {"modelspec.predict_key": "epsilon"}
        assert model_write["extraKeys"] == []

        return {
            "workflowExampleExecuted": False,
            "writer": "capture-only; no production safetensors dependency installed",
            "path": {
                "traversalRejected": traversal_rejected,
                "unreservedCounters": [first, second],
                "existingCounterNext": 5,
            },
            "clip": {
                "loaded": clip.loaded,
                "files": [entry["path"] for entry in clip_writes],
                "keys": [entry["keys"] for entry in clip_writes],
            },
            "vae": {
                "getSdCalls": vae.calls,
                "files": [entry["path"] for entry in vae_writes],
            },
            "checkpoint": checkpoint,
            "modelOnlyMetadataDisabled": model_write,
        }


if __name__ == "__main__":
    root = Path(sys.argv[1] if len(sys.argv) > 1 else ".comfyui-source-0.32.0")
    print(json.dumps(run_probe(root), ensure_ascii=False, sort_keys=True))
