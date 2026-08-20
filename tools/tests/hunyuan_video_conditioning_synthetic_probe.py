from __future__ import annotations

import ast
import json
import math
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import torch
import torch.nn.functional as functional


class DummyNodeOutput:
    def __init__(self, *values: object) -> None:
        self.values = values


class DummyComfyNode:
    pass


class DummyLatentFormat:
    pass


class UpscaleSpy:
    calls: list[dict[str, object]] = []

    @classmethod
    def common_upscale(
        cls,
        value: torch.Tensor,
        width: int,
        height: int,
        method: str,
        crop: str,
    ) -> torch.Tensor:
        cls.calls.append(
            {
                "inputShape": list(value.shape),
                "width": width,
                "height": height,
                "method": method,
                "crop": crop,
            }
        )
        return functional.interpolate(value, size=(height, width), mode="bilinear")


def conditioning_set_values(
    conditioning: list[list[object]], values: dict[str, object]
) -> list[list[object]]:
    output: list[list[object]] = []
    for tensor, metadata in conditioning:
        copied = dict(metadata)
        copied.update(values)
        output.append([tensor, copied])
    return output


def extract_nodes(source_root: Path) -> dict[str, type]:
    path = source_root / "comfy_extras" / "nodes_hunyuan.py"
    tree = ast.parse(path.read_text(encoding="utf-8"))
    wanted = {
        "HunyuanVideo15ImageToVideo",
        "HunyuanVideo15SuperResolution",
        "HunyuanImageToVideo",
        "HunyuanRefinerLatent",
    }
    selected = [
        node
        for node in tree.body
        if isinstance(node, ast.ClassDef) and node.name in wanted
    ]
    found = {node.name for node in selected}
    if found != wanted:
        raise AssertionError(f"missing exact classes: {sorted(wanted - found)}")

    namespace: dict[str, Any] = {
        "torch": torch,
        "io": SimpleNamespace(ComfyNode=DummyComfyNode, NodeOutput=DummyNodeOutput),
        "comfy": SimpleNamespace(
            model_management=SimpleNamespace(
                intermediate_device=lambda: torch.device("cpu")
            ),
            utils=SimpleNamespace(common_upscale=UpscaleSpy.common_upscale),
        ),
        "node_helpers": SimpleNamespace(
            conditioning_set_values=conditioning_set_values
        ),
    }
    exec(compile(ast.Module(body=selected, type_ignores=[]), str(path), "exec"), namespace)
    return {name: namespace[name] for name in wanted}


def extract_refiner_format(source_root: Path) -> type:
    path = source_root / "comfy" / "latent_formats.py"
    tree = ast.parse(path.read_text(encoding="utf-8"))
    selected = [
        node
        for node in tree.body
        if isinstance(node, ast.ClassDef) and node.name == "HunyuanImage21Refiner"
    ]
    if len(selected) != 1:
        raise AssertionError("missing exact HunyuanImage21Refiner latent format")
    namespace: dict[str, Any] = {
        "torch": torch,
        "LatentFormat": DummyLatentFormat,
    }
    exec(compile(ast.Module(body=selected, type_ignores=[]), str(path), "exec"), namespace)
    return namespace["HunyuanImage21Refiner"]


class FakeVideoVae:
    def __init__(
        self,
        channels: int,
        spatial_divisor: int,
        temporal_divisor: int = 4,
    ) -> None:
        self.channels = channels
        self.spatial_divisor = spatial_divisor
        self.temporal_divisor = temporal_divisor
        self.input_shapes: list[list[int]] = []

    def encode(self, images: torch.Tensor) -> torch.Tensor:
        self.input_shapes.append(list(images.shape))
        frames, height, width, channels = images.shape
        assert channels == 3
        temporal = math.ceil(frames / self.temporal_divisor)
        encoded = torch.empty(
            (1, self.channels, temporal, height // self.spatial_divisor, width // self.spatial_divisor),
            dtype=torch.float32,
        )
        for channel in range(self.channels):
            encoded[:, channel] = 10.25 + channel
        return encoded


def make_conditioning(label: str) -> list[list[object]]:
    return [[torch.tensor([1.0]), {"label": label}]]


def metadata(conditioning: list[list[object]]) -> dict[str, object]:
    return conditioning[0][1]  # type: ignore[return-value]


def probe_video15_i2v(classes: dict[str, type]) -> dict[str, object]:
    node = classes["HunyuanVideo15ImageToVideo"]
    positive = make_conditioning("positive")
    negative = make_conditioning("negative")
    vae = FakeVideoVae(32, 16)
    start_image = torch.linspace(0, 1, 6 * 24 * 32 * 4).reshape(6, 24, 32, 4)
    clip_vision_output = SimpleNamespace(last_hidden_state=torch.ones(1, 4, 8))

    out_positive, out_negative, out_latent = node.execute(
        positive,
        negative,
        vae,
        64,
        48,
        9,
        2,
        start_image=start_image,
        clip_vision_output=clip_vision_output,
    ).values
    samples = out_latent["samples"]
    positive_meta = metadata(out_positive)
    negative_meta = metadata(out_negative)
    concat = positive_meta["concat_latent_image"]
    mask = positive_meta["concat_mask"]

    assert list(samples.shape) == [2, 32, 3, 3, 4]
    assert torch.count_nonzero(samples) == 0
    assert sorted(out_latent) == ["samples"]
    assert vae.input_shapes == [[6, 48, 64, 3]]
    assert list(concat.shape) == [2, 32, 3, 3, 4]
    assert torch.equal(concat[0], concat[1])
    assert torch.count_nonzero(concat[:, :, 2]) == 0
    assert list(mask.shape) == [1, 1, 3, 3, 4]
    assert torch.count_nonzero(mask[:, :, :2]) == 0
    assert torch.all(mask[:, :, 2] == 1)
    assert positive_meta["clip_vision_output"] is clip_vision_output
    assert negative_meta["clip_vision_output"] is clip_vision_output
    assert negative_meta["concat_latent_image"] is concat
    assert negative_meta["concat_mask"] is mask

    untouched_positive = make_conditioning("without-image")
    untouched_negative = make_conditioning("without-image-negative")
    no_image = node.execute(
        untouched_positive,
        untouched_negative,
        vae,
        64,
        48,
        1,
        1,
    ).values
    assert no_image[0] is untouched_positive
    assert no_image[1] is untouched_negative
    assert vae.input_shapes == [[6, 48, 64, 3]]

    return {
        "latentShape": list(samples.shape),
        "latentKeys": sorted(out_latent),
        "vaeInputShape": vae.input_shapes[0],
        "concatShape": list(concat.shape),
        "maskTemporalValues": mask[0, 0, :, 0, 0].tolist(),
        "clipVisionForwardedToBoth": True,
        "vaeUnusedWithoutStartImage": True,
    }


def probe_video15_super_resolution(classes: dict[str, type]) -> dict[str, object]:
    node = classes["HunyuanVideo15SuperResolution"]
    positive = make_conditioning("positive")
    negative = make_conditioning("negative")
    samples = torch.arange(2 * 32 * 3 * 3 * 4, dtype=torch.float32).reshape(2, 32, 3, 3, 4)
    latent = {"samples": samples, "noise_mask": torch.ones(1, 1, 3, 3, 4)}
    clip_vision_output = SimpleNamespace(last_hidden_state=torch.ones(1, 4, 8))
    vae = FakeVideoVae(32, 16)
    start_image = torch.ones(5, 20, 20, 4)

    out_positive, out_negative, out_latent = node.execute(
        positive,
        negative,
        latent,
        0.7,
        vae=vae,
        start_image=start_image,
        clip_vision_output=clip_vision_output,
    ).values
    positive_meta = metadata(out_positive)
    negative_meta = metadata(out_negative)
    concat = positive_meta["concat_latent_image"]
    assert out_latent is latent
    assert list(concat.shape) == [2, 66, 3, 3, 4]
    assert concat.dtype == torch.float32
    assert torch.all(concat[:, 32] == 0)
    assert torch.all(concat[:, 65] == 1)
    assert torch.all(concat[:, :32, :2] != 0)
    assert torch.count_nonzero(concat[:, :32, 2]) == 0
    assert torch.all(concat[:, 33, 0] == 1)
    assert torch.equal(concat[:, 33, 1:], samples[:, 0, 1:])
    assert torch.equal(concat[:, 34:65], samples[:, 1:])
    assert positive_meta["noise_augmentation"] == 0.7
    assert negative_meta["noise_augmentation"] == 0.7
    assert positive_meta["clip_vision_output"] is clip_vision_output
    assert negative_meta["clip_vision_output"] is clip_vision_output

    without_image = node.execute(
        make_conditioning("p"),
        make_conditioning("n"),
        latent,
        0.0,
    ).values
    without_image_concat = metadata(without_image[0])["concat_latent_image"]
    assert torch.equal(without_image_concat[:, 33:65], samples)
    assert torch.all(without_image_concat[:, 65] == 1)

    missing_vae_error = None
    try:
        node.execute(
            make_conditioning("p"),
            make_conditioning("n"),
            latent,
            0.7,
            start_image=start_image,
        )
    except AttributeError as error:
        missing_vae_error = type(error).__name__
    assert missing_vae_error == "AttributeError"

    return {
        "conditioningShape": list(concat.shape),
        "inputLatentReturnedByIdentity": out_latent is latent,
        "startImageVaeInputShape": vae.input_shapes[0],
        "startMaskChannel": 32,
        "writtenMarkerChannel": 33,
        "lowQualitySlice": [33, 65],
        "lastMaskChannelAllOnes": bool(torch.all(concat[:, 65] == 1)),
        "missingVaeWithStartImage": missing_vae_error,
        "noiseAugmentationStoredNotAppliedByNode": positive_meta["noise_augmentation"],
    }


def probe_legacy_hunyuan_i2v(classes: dict[str, type]) -> dict[str, object]:
    node = classes["HunyuanImageToVideo"]
    start_image = torch.ones(5, 20, 20, 4)
    results: dict[str, object] = {}

    for guidance_type in ("v1 (concat)", "v2 (replace)", "custom"):
        vae = FakeVideoVae(16, 8)
        positive = make_conditioning(guidance_type)
        out_positive, out_latent = node.execute(
            positive,
            vae,
            64,
            48,
            9,
            2,
            guidance_type,
            start_image=start_image,
        ).values
        samples = out_latent["samples"]
        meta = metadata(out_positive)
        assert list(samples.shape) == [2, 16, 3, 6, 8]
        assert vae.input_shapes == [[5, 48, 64, 3]]

        if guidance_type == "v1 (concat)":
            assert sorted(meta) == ["concat_latent_image", "concat_mask", "label"]
            assert sorted(out_latent) == ["samples"]
            assert torch.count_nonzero(samples) == 0
            assert meta["concat_mask"][0, 0, :, 0, 0].tolist() == [0.0, 0.0, 1.0]
        elif guidance_type == "v2 (replace)":
            assert meta["guiding_frame_index"] == 0
            assert sorted(out_latent) == ["noise_mask", "samples"]
            assert out_latent["noise_mask"][0, 0, :, 0, 0].tolist() == [0.0, 0.0, 1.0]
            assert torch.count_nonzero(samples[:, :, :2]) > 0
            assert torch.count_nonzero(samples[:, :, 2]) == 0
        else:
            assert sorted(meta) == ["label", "ref_latent"]
            assert sorted(out_latent) == ["samples"]
            assert torch.count_nonzero(samples) == 0

        results[guidance_type] = {
            "conditioningKeys": sorted(key for key in meta if key != "label"),
            "latentKeys": sorted(out_latent),
            "nonZeroSamples": int(torch.count_nonzero(samples)),
        }

    no_image_positive = make_conditioning("no-image")
    no_image_vae = FakeVideoVae(16, 8)
    out_positive, out_latent = node.execute(
        no_image_positive,
        no_image_vae,
        64,
        48,
        9,
        1,
        "v2 (replace)",
    ).values
    assert out_positive is no_image_positive
    assert no_image_vae.input_shapes == []
    assert torch.count_nonzero(out_latent["samples"]) == 0
    results["withoutStartImage"] = {
        "conditioningUnchanged": out_positive is no_image_positive,
        "vaeUnused": True,
    }
    return results


def probe_refiner(classes: dict[str, type]) -> dict[str, object]:
    node = classes["HunyuanRefinerLatent"]
    input_samples = torch.ones((2, 32, 3, 4, 5), dtype=torch.float64)
    latent = {"samples": input_samples, "noise_mask": torch.ones(1)}
    out_positive, out_negative, out_latent = node.execute(
        make_conditioning("positive"),
        make_conditioning("negative"),
        latent,
        0.1,
    ).values
    output = out_latent["samples"]
    assert list(output.shape) == [2, 32, 3, 4, 5]
    assert output.dtype == torch.float32
    assert torch.count_nonzero(output) == 0
    assert sorted(out_latent) == ["samples"]
    assert metadata(out_positive)["concat_latent_image"] is input_samples
    assert metadata(out_negative)["concat_latent_image"] is input_samples
    assert metadata(out_positive)["noise_augmentation"] == 0.1
    assert metadata(out_negative)["noise_augmentation"] == 0.1

    image_like = torch.ones((2, 64, 4, 5))
    image_like_output = node.execute(
        make_conditioning("positive"),
        make_conditioning("negative"),
        {"samples": image_like},
        0.0,
    ).values[2]["samples"]
    assert list(image_like_output.shape) == [2, 32, 64, 4, 5]

    return {
        "videoLikeInputShape": list(input_samples.shape),
        "videoLikeOutputShape": list(output.shape),
        "outputDtype": str(output.dtype),
        "outputKeys": sorted(out_latent),
        "inputTensorForwardedToBothConditionings": True,
        "fourDimensionalInputOutputShape": list(image_like_output.shape),
    }


def probe_refiner_consumer_shape(format_class: type) -> dict[str, object]:
    latent_format = format_class()
    condition_t9 = torch.arange(1 * 32 * 9 * 2 * 2, dtype=torch.float32).reshape(1, 32, 9, 2, 2)
    packed_t9 = latent_format.process_in(condition_t9)
    assert list(packed_t9.shape) == [1, 64, 5, 2, 2]
    restored_t9 = latent_format.process_out(packed_t9)
    assert list(restored_t9.shape) == list(condition_t9.shape)
    assert torch.allclose(restored_t9, condition_t9)

    blank_t9 = torch.zeros((1, 32, 9, 2, 2))
    fixed_blank_t9 = blank_t9.repeat(1, 2, 1, 1, 1)
    mismatch_error = None
    try:
        torch.cat((fixed_blank_t9, packed_t9), dim=1)
    except RuntimeError as error:
        mismatch_error = str(error)
    assert mismatch_error is not None and "Sizes of tensors must match" in mismatch_error

    condition_t1 = torch.ones((1, 32, 1, 2, 2))
    packed_t1 = latent_format.process_in(condition_t1)
    fixed_blank_t1 = torch.zeros((1, 64, 1, 2, 2))
    joined_t1 = torch.cat((fixed_blank_t1, packed_t1), dim=1)
    assert list(packed_t1.shape) == [1, 64, 1, 2, 2]
    assert list(joined_t1.shape) == [1, 128, 1, 2, 2]

    return {
        "conditionT9": list(condition_t9.shape),
        "packedConditionT9": list(packed_t9.shape),
        "blankAfterChannelFixT9": list(fixed_blank_t9.shape),
        "temporalConcatT9": "RuntimeError: Sizes of tensors must match",
        "conditionT1": list(condition_t1.shape),
        "packedConditionT1": list(packed_t1.shape),
        "joinedT1": list(joined_t1.shape),
    }


def run_probe(source_root: Path) -> dict[str, object]:
    UpscaleSpy.calls = []
    classes = extract_nodes(source_root)
    refiner_format = extract_refiner_format(source_root)
    return {
        "hunyuanVideo15ImageToVideo": probe_video15_i2v(classes),
        "hunyuanVideo15SuperResolution": probe_video15_super_resolution(classes),
        "hunyuanImageToVideo": probe_legacy_hunyuan_i2v(classes),
        "hunyuanRefinerLatent": probe_refiner(classes),
        "hunyuanRefinerConsumerShape": probe_refiner_consumer_shape(refiner_format),
        "upscaleCalls": UpscaleSpy.calls,
    }


if __name__ == "__main__":
    root = Path(sys.argv[1] if len(sys.argv) > 1 else ".comfyui-source-0.32.0")
    print(json.dumps(run_probe(root), ensure_ascii=False, sort_keys=True))
