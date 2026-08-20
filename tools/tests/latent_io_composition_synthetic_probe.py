from __future__ import annotations

import ast
import hashlib
import json
import logging
import os
import shutil
import struct
import sys
import tempfile
import time
import types
from pathlib import Path


def compile_named(path: Path, names: set[str]):
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    body = [
        node
        for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
        and node.name in names
    ]
    found = {node.name for node in body}
    if found != names:
        raise AssertionError(f"missing source declarations in {path}: {sorted(names - found)}")
    return compile(ast.Module(body=body, type_ignores=[]), str(path), "exec")


class SafeTensorCompat:
    """Small safetensors-compatible codec used only by this isolated probe."""

    _to_name = None
    _from_name = None

    @classmethod
    def configure(cls, torch):
        cls._to_name = {
            torch.float16: "F16",
            torch.float32: "F32",
            torch.float64: "F64",
            torch.int64: "I64",
            torch.int32: "I32",
            torch.uint8: "U8",
        }
        cls._from_name = {value: key for key, value in cls._to_name.items()}

    @classmethod
    def save_file(cls, tensors, filename, metadata=None):
        header: dict[str, object] = {}
        if metadata is not None:
            if not all(isinstance(key, str) and isinstance(value, str) for key, value in metadata.items()):
                raise TypeError("safetensors metadata must contain string keys and values")
            header["__metadata__"] = dict(metadata)

        chunks: list[bytes] = []
        offset = 0
        for name, tensor in tensors.items():
            tensor = tensor.detach().cpu().contiguous()
            dtype_name = cls._to_name.get(tensor.dtype)
            if dtype_name is None:
                raise TypeError(f"unsupported probe dtype: {tensor.dtype}")
            chunk = tensor.numpy().tobytes(order="C")
            header[name] = {
                "dtype": dtype_name,
                "shape": list(tensor.shape),
                "data_offsets": [offset, offset + len(chunk)],
            }
            chunks.append(chunk)
            offset += len(chunk)

        encoded = json.dumps(header, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        encoded += b" " * ((8 - len(encoded) % 8) % 8)
        with open(filename, "wb") as handle:
            handle.write(struct.pack("<Q", len(encoded)))
            handle.write(encoded)
            for chunk in chunks:
                handle.write(chunk)

    @classmethod
    def read_file(cls, filename, torch):
        with open(filename, "rb") as handle:
            header_length = struct.unpack("<Q", handle.read(8))[0]
            header = json.loads(handle.read(header_length).decode("utf-8"))
            data = handle.read()
        metadata = header.pop("__metadata__", None)
        tensors = {}
        for name, record in header.items():
            dtype = cls._from_name[record["dtype"]]
            shape = tuple(record["shape"])
            start, end = record["data_offsets"]
            if end == start:
                tensor = torch.empty(shape, dtype=dtype)
            else:
                tensor = torch.frombuffer(bytearray(data[start:end]), dtype=dtype).clone().reshape(shape)
            tensors[name] = tensor
        return tensors, metadata

    @classmethod
    def load_file(cls, filename, device="cpu"):
        import torch

        tensors, _ = cls.read_file(filename, torch)
        return {name: tensor.to(device) for name, tensor in tensors.items()}


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit("usage: latent_io_composition_synthetic_probe.py <pinned-comfyui-source>")

    source = Path(sys.argv[1]).resolve()
    import torch

    SafeTensorCompat.configure(torch)

    class DummyIo:
        class ComfyNode:
            pass

        class NodeOutput:
            def __init__(self, *args):
                self.args = args

    core_namespace = {
        "MAX_RESOLUTION": 16384,
        "torch": torch,
        "json": json,
        "hashlib": hashlib,
        "os": os,
    }
    exec(
        compile_named(
            source / "nodes.py",
            {"LatentComposite", "SaveLatent", "LoadLatent"},
        ),
        core_namespace,
    )

    wan_namespace = {"torch": torch, "io": DummyIo}
    exec(
        compile_named(source / "comfy_extras" / "nodes_wan.py", {"TrimVideoLatent"}),
        wan_namespace,
    )

    base_marker = {"origin": "samples_to"}
    noise_mask = torch.arange(36, dtype=torch.float32).reshape(1, 6, 6)
    destination_tensor = torch.zeros((2, 4, 6, 7), dtype=torch.float32)
    source_tensor = torch.ones((1, 4, 4, 4), dtype=torch.float32) * 9
    destination = {
        "samples": destination_tensor,
        "noise_mask": noise_mask,
        "batch_index": [10, 11],
        "custom": base_marker,
    }
    source_latent = {
        "samples": source_tensor,
        "noise_mask": torch.ones((1, 4, 4)),
        "source_only": True,
    }
    composite_cls = core_namespace["LatentComposite"]
    hard = composite_cls().composite(destination, source_latent, x=16, y=8, feather=0)[0]
    assert tuple(hard["samples"].shape) == (2, 4, 6, 7)
    assert torch.count_nonzero(destination_tensor).item() == 0
    assert torch.all(hard["samples"][:, :, 1:5, 2:6] == 9)
    assert hard["noise_mask"] is noise_mask
    assert hard["batch_index"] is destination["batch_index"]
    assert hard["custom"] is base_marker
    assert "source_only" not in hard

    cropped = composite_cls().composite(destination, source_latent, x=40, y=32, feather=0)[0]
    assert torch.all(cropped["samples"][:, :, 4:6, 5:7] == 9)
    assert torch.count_nonzero(cropped["samples"]).item() == 2 * 4 * 2 * 2

    feather_destination = {"samples": torch.zeros((1, 1, 6, 6))}
    feather_source = {"samples": torch.ones((1, 1, 4, 4))}
    feathered = composite_cls().composite(
        feather_destination, feather_source, x=8, y=8, feather=16
    )[0]["samples"][0, 0, 1:5, 1:5]
    assert torch.isclose(feathered[0, 0], torch.tensor(0.25))
    assert torch.isclose(feathered[0, 1], torch.tensor(0.5))
    assert torch.isclose(feathered[1, 1], torch.tensor(1.0))

    far_offset_error = None
    try:
        composite_cls().composite(destination, source_latent, x=64, y=0, feather=0)
    except RuntimeError as exc:
        far_offset_error = str(exc)
    assert far_offset_error is not None

    trim_cls = wan_namespace["TrimVideoLatent"]
    video_samples = torch.arange(2 * 3 * 6 * 2 * 2, dtype=torch.float32).reshape(2, 3, 6, 2, 2)
    temporal_mask = torch.ones((2, 1, 6, 2, 2))
    video_marker = {"kind": "wan"}
    video_latent = {
        "samples": video_samples,
        "noise_mask": temporal_mask,
        "batch_index": [4, 5],
        "custom": video_marker,
    }
    trimmed = trim_cls.execute(video_latent, 2).args[0]
    assert tuple(trimmed["samples"].shape) == (2, 3, 4, 2, 2)
    assert torch.equal(trimmed["samples"], video_samples[:, :, 2:])
    assert trimmed["samples"].untyped_storage().data_ptr() == video_samples.untyped_storage().data_ptr()
    assert trimmed["noise_mask"] is temporal_mask
    assert tuple(trimmed["noise_mask"].shape) == (2, 1, 6, 2, 2)
    assert trimmed["custom"] is video_marker
    empty_time = trim_cls.execute(video_latent, 99).args[0]
    assert tuple(empty_time["samples"].shape) == (2, 3, 0, 2, 2)
    image_like = {"samples": torch.zeros((1, 4, 8, 8))}
    image_like_trimmed = trim_cls.execute(image_like, 2).args[0]
    assert tuple(image_like_trimmed["samples"].shape) == (1, 4, 6, 8)

    with tempfile.TemporaryDirectory(prefix="nodes-wizard-latent-io-") as temporary:
        temporary_path = Path(temporary)
        input_directory = temporary_path / "input"
        output_directory = temporary_path / "output"
        temp_directory = temporary_path / "temp"
        input_directory.mkdir()
        output_directory.mkdir()
        temp_directory.mkdir()

        folder_namespace = {
            "os": os,
            "time": time,
            "logging": logging,
            "input_directory": str(input_directory),
            "output_directory": str(output_directory),
            "temp_directory": str(temp_directory),
        }
        exec(
            compile_named(
                source / "folder_paths.py",
                {
                    "get_output_directory",
                    "get_temp_directory",
                    "get_input_directory",
                    "annotated_filepath",
                    "is_within_directory",
                    "get_annotated_filepath",
                    "exists_annotated_filepath",
                    "get_save_image_path",
                },
            ),
            folder_namespace,
        )
        folder_paths = types.SimpleNamespace(
            **{name: folder_namespace[name] for name in (
                "get_output_directory",
                "get_input_directory",
                "get_annotated_filepath",
                "exists_annotated_filepath",
                "get_save_image_path",
            )}
        )

        safetensors = types.SimpleNamespace(torch=SafeTensorCompat)
        utils_namespace = {"safetensors": safetensors}
        exec(
            compile_named(source / "comfy" / "utils.py", {"save_torch_file"}),
            utils_namespace,
        )
        args = types.SimpleNamespace(disable_metadata=False)
        core_namespace.update(
            {
                "folder_paths": folder_paths,
                "safetensors": safetensors,
                "comfy": types.SimpleNamespace(
                    utils=types.SimpleNamespace(save_torch_file=utils_namespace["save_torch_file"])
                ),
                "args": args,
            }
        )

        samples = torch.arange(24, dtype=torch.float16).reshape(1, 3, 2, 4).transpose(2, 3)
        assert not samples.is_contiguous()
        disk_latent = {
            "samples": samples,
            "noise_mask": torch.ones((1, 4, 2)),
            "batch_index": [17],
            "custom": {"not": "serialized"},
        }
        save_node = core_namespace["SaveLatent"]()
        saved_result = save_node.save(
            disk_latent,
            filename_prefix="latents/wizard-probe",
            prompt={"3": {"class_type": "KSampler"}},
            extra_pnginfo={"workflow": {"id": "probe"}},
        )
        locator = saved_result["ui"]["latents"][0]
        saved_path = output_directory / locator["subfolder"] / locator["filename"]
        assert saved_path.exists()
        assert saved_result["result"][0] is disk_latent
        saved_tensors, saved_metadata = SafeTensorCompat.read_file(saved_path, torch)
        assert set(saved_tensors) == {"latent_tensor", "latent_format_version_0"}
        assert saved_tensors["latent_tensor"].is_contiguous()
        assert saved_tensors["latent_tensor"].dtype == torch.float16
        assert torch.equal(saved_tensors["latent_tensor"], samples.contiguous())
        assert saved_metadata == {
            "prompt": json.dumps({"3": {"class_type": "KSampler"}}),
            "workflow": json.dumps({"id": "probe"}),
        }

        input_saved = input_directory / saved_path.name
        shutil.copy2(saved_path, input_saved)
        load_node = core_namespace["LoadLatent"]()
        choices = load_node.INPUT_TYPES()["required"]["latent"][0]
        assert choices == [saved_path.name]
        loaded = load_node.load(saved_path.name)[0]
        assert set(loaded) == {"samples"}
        assert loaded["samples"].dtype == torch.float32
        assert torch.equal(loaded["samples"], samples.float())
        assert load_node.VALIDATE_INPUTS(saved_path.name) is True
        assert load_node.VALIDATE_INPUTS("missing.latent") == "Invalid latent file: missing.latent"
        assert load_node.IS_CHANGED(saved_path.name) == hashlib.sha256(input_saved.read_bytes()).hexdigest()

        legacy_path = input_directory / "legacy.latent"
        SafeTensorCompat.save_file(
            {"latent_tensor": torch.tensor([0.18215], dtype=torch.float32)},
            legacy_path,
        )
        legacy = load_node.load(legacy_path.name)[0]["samples"]
        assert torch.allclose(legacy, torch.tensor([1.0]), atol=1e-6)

        args.disable_metadata = True
        no_metadata = save_node.save(disk_latent, filename_prefix="latents/no-metadata")
        no_metadata_locator = no_metadata["ui"]["latents"][0]
        no_metadata_path = output_directory / no_metadata_locator["subfolder"] / no_metadata_locator["filename"]
        _, disabled_metadata = SafeTensorCompat.read_file(no_metadata_path, torch)
        assert disabled_metadata is None

        traversal_blocked = False
        previous_logging_disable = logging.root.manager.disable
        logging.disable(logging.CRITICAL)
        try:
            try:
                save_node.save(disk_latent, filename_prefix="../escape")
            except Exception:
                traversal_blocked = True
        finally:
            logging.disable(previous_logging_disable)
        assert traversal_blocked

        file_probe = {
            "savedKeys": sorted(saved_tensors),
            "savedDtype": str(saved_tensors["latent_tensor"].dtype),
            "loadedDtype": str(loaded["samples"].dtype),
            "metadataKeys": sorted(saved_metadata),
            "legacyValue": legacy.item(),
            "returnedOriginal": saved_result["result"][0] is disk_latent,
            "pathTraversalBlocked": traversal_blocked,
        }

    print(
        json.dumps(
            {
                "latentComposite": {
                    "shape": list(hard["samples"].shape),
                    "broadcastSourceBatchOne": bool(torch.all(hard["samples"][:, :, 1:5, 2:6] == 9)),
                    "croppedNonzero": int(torch.count_nonzero(cropped["samples"]).item()),
                    "featherCorner": feathered[0, 0].item(),
                    "featherInner": feathered[1, 1].item(),
                    "metadataFromDestination": hard["custom"] is base_marker,
                    "farOffsetError": far_offset_error,
                },
                "trimVideoLatent": {
                    "shape": list(trimmed["samples"].shape),
                    "sharesStorage": trimmed["samples"].untyped_storage().data_ptr()
                    == video_samples.untyped_storage().data_ptr(),
                    "noiseMaskShapeUnchanged": list(trimmed["noise_mask"].shape),
                    "oversizedTrimShape": list(empty_time["samples"].shape),
                    "fourDimensionalInputShape": list(image_like_trimmed["samples"].shape),
                },
                "fileRoundtrip": file_probe,
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
