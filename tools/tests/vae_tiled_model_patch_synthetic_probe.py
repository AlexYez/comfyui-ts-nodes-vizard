from __future__ import annotations

import json
import sys
from contextlib import nullcontext
from pathlib import Path


def output_args(output):
    return output.args


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit("usage: vae_tiled_model_patch_synthetic_probe.py <pinned-comfyui-source>")
    source = Path(sys.argv[1]).resolve()
    sys.path.insert(0, str(source))

    import torch
    import nodes
    import comfy.sd as comfy_sd
    import comfy_extras.nodes_model_downscale as nodes_downscale
    import comfy_extras.nodes_tomesd as nodes_tomesd

    class FakeDecodeVAE:
        def __init__(self, temporal=4) -> None:
            self.temporal = temporal
            self.calls: list[dict[str, object]] = []

        def temporal_compression_decode(self):
            return self.temporal

        def spacial_compression_decode(self):
            return 8

        def decode_tiled(self, latent, **kwargs):
            self.calls.append({"latent_shape": list(latent.shape), "latent_first": latent.reshape(-1)[0].item(), **kwargs})
            return torch.zeros((1, 2, 16, 20, 3))

    decode_vae = FakeDecodeVAE()
    (decoded,) = nodes.VAEDecodeTiled().decode(
        decode_vae,
        {"samples": torch.zeros((1, 4, 8, 10))},
        tile_size=128,
        overlap=64,
        temporal_size=16,
        temporal_overlap=12,
    )
    assert list(decoded.shape) == [2, 16, 20, 3]
    assert decode_vae.calls == [{
        "latent_shape": [1, 4, 8, 10],
        "latent_first": 0.0,
        "tile_x": 16,
        "tile_y": 16,
        "overlap": 4,
        "tile_t": 4,
        "overlap_t": 1,
    }]

    image_vae = FakeDecodeVAE(temporal=None)
    nodes.VAEDecodeTiled().decode(
        image_vae,
        {"samples": torch.zeros((1, 4, 8, 8))},
        tile_size=512,
        overlap=64,
        temporal_size=64,
        temporal_overlap=8,
    )
    assert image_vae.calls[0]["tile_t"] is None
    assert image_vae.calls[0]["overlap_t"] is None

    nested_samples = torch.nested.nested_tensor([
        torch.ones((4, 8, 10)),
        torch.full((4, 6, 8), 2.0),
    ])
    assert nested_samples.is_nested
    nested_vae = FakeDecodeVAE(temporal=None)
    nodes.VAEDecodeTiled().decode(
        nested_vae,
        {"samples": nested_samples},
        tile_size=512,
        overlap=64,
        temporal_size=64,
        temporal_overlap=8,
    )
    assert nested_vae.calls[0]["latent_shape"] == [4, 8, 10]
    assert nested_vae.calls[0]["latent_first"] == 1.0

    class FakeEncodeVAE:
        def __init__(self) -> None:
            self.calls: list[dict[str, object]] = []
            self.out = torch.arange(16.0).reshape(1, 1, 4, 4)

        def encode_tiled(self, pixels, **kwargs):
            self.calls.append({"pixels_identity": id(pixels), "pixels_shape": list(pixels.shape), **kwargs})
            return self.out

    pixels = torch.zeros((2, 32, 48, 3))
    encode_vae = FakeEncodeVAE()
    (latent,) = nodes.VAEEncodeTiled().encode(encode_vae, pixels, 512, 128, 64, 8)
    assert latent == {"samples": encode_vae.out}
    assert encode_vae.calls == [{
        "pixels_identity": id(pixels),
        "pixels_shape": [2, 32, 48, 3],
        "tile_x": 512,
        "tile_y": 512,
        "overlap": 128,
        "tile_t": 64,
        "overlap_t": 8,
    }]

    crop_vae = object.__new__(comfy_sd.VAE)
    crop_vae.crop_input = True
    crop_vae.downscale_ratio = 8
    crop_vae.output_channels = 3
    crop_vae.pad_channel_value = 0.25
    rgba = torch.arange(1 * 10 * 19 * 4, dtype=torch.float32).reshape(1, 10, 19, 4)
    cropped = comfy_sd.VAE.vae_encode_crop_pixels(crop_vae, rgba)
    assert list(cropped.shape) == [1, 8, 16, 3]
    assert torch.equal(cropped, rgba[:, 1:9, 1:17, :3])
    padded = comfy_sd.VAE.vae_encode_crop_pixels(crop_vae, torch.zeros((1, 8, 16, 2)))
    assert list(padded.shape) == [1, 8, 16, 3]
    assert torch.all(padded[..., :2] == 0) and torch.all(padded[..., 2] == 0.25)

    class DirectTilerVAE:
        def __init__(self) -> None:
            self.first_stage_model = object()
            self.process_input = lambda value: value
            self.process_output = lambda value: value
            self.vae_dtype = torch.float32
            self.device = torch.device("cpu")
            self.output_device = torch.device("cpu")
            self.downscale_ratio = 8
            self.upscale_ratio = 8
            self.latent_channels = 4

        def vae_output_dtype(self):
            return torch.float32

    tiled_calls: list[dict[str, object]] = []
    original_steps = comfy_sd.comfy.utils.get_tiled_scale_steps
    original_progress = comfy_sd.comfy.utils.ProgressBar
    original_tiled_scale = comfy_sd.comfy.utils.tiled_scale

    def fake_tiled_scale(samples, function, tile_x, tile_y, overlap, **kwargs):
        tiled_calls.append({"tile_x": tile_x, "tile_y": tile_y, "overlap": overlap, "out_channels": kwargs.get("out_channels")})
        value = float(len(tiled_calls))
        channels = kwargs.get("out_channels", 3)
        return torch.full((samples.shape[0], channels, 2, 3), value)

    comfy_sd.comfy.utils.get_tiled_scale_steps = lambda *args, **kwargs: 1
    comfy_sd.comfy.utils.ProgressBar = lambda steps: object()
    comfy_sd.comfy.utils.tiled_scale = fake_tiled_scale
    try:
        direct_vae = DirectTilerVAE()
        base_encode = comfy_sd.VAE.encode_tiled_(direct_vae, torch.zeros((1, 3, 12, 16)), tile_x=8, tile_y=6, overlap=2)
        encode_grids = [dict(call) for call in tiled_calls]
        assert [(call["tile_x"], call["tile_y"]) for call in encode_grids] == [(8, 6), (16, 3), (4, 12)]
        assert torch.all(base_encode == 2.0)
        tiled_calls.clear()
        base_decode = comfy_sd.VAE.decode_tiled_(direct_vae, torch.zeros((1, 4, 2, 3)), tile_x=8, tile_y=6, overlap=2)
        decode_grids = [dict(call) for call in tiled_calls]
        assert [(call["tile_x"], call["tile_y"]) for call in decode_grids] == [(4, 12), (16, 3), (8, 6)]
        assert torch.all(base_decode == 2.0)
    finally:
        comfy_sd.comfy.utils.get_tiled_scale_steps = original_steps
        comfy_sd.comfy.utils.ProgressBar = original_progress
        comfy_sd.comfy.utils.tiled_scale = original_tiled_scale

    class RoutingVAE:
        def __init__(self, latent_dim, handles_tiling=False) -> None:
            self.latent_dim = latent_dim
            self.handles_tiling = handles_tiling
            self.not_video = False
            self.extra_1d_channel = None
            self.vae_dtype = torch.float32
            self.device = torch.device("cpu")
            self.output_device = torch.device("cpu")
            self.patcher = object()
            self.disable_offload = False
            self.format_encoded = None
            self.downscale_ratio = (lambda value: max(0, (value + 3) // 4), 8, 8)
            self.upscale_ratio = (lambda value: max(0, value * 4 - 3), 8, 8)
            self.calls: list[dict[str, object]] = []

        def throw_exception_if_invalid(self):
            return None

        def vae_encode_crop_pixels(self, pixels):
            return pixels

        def memory_used_encode(self, shape, dtype):
            return 1

        def memory_used_decode(self, shape, dtype):
            return 1

        def _owned_tiled_args(self, tile_x=None, tile_y=None, overlap=None, tile_t=None, overlap_t=None):
            return comfy_sd.VAE._owned_tiled_args(self, tile_x, tile_y, overlap, tile_t, overlap_t)

        def _tile_bounded_shape(self, shape, tile_x, tile_y, tile_t):
            return comfy_sd.VAE._tile_bounded_shape(self, shape, tile_x, tile_y, tile_t)

        def encode_tiled_(self, pixels, **kwargs):
            self.calls.append({"route": "encode-2d", "shape": list(pixels.shape), **kwargs})
            return torch.zeros((1, 4, 2, 3))

        def encode_tiled_3d(self, pixels, **kwargs):
            self.calls.append({"route": "encode-3d", "shape": list(pixels.shape), **kwargs})
            return torch.zeros((1, 4, pixels.shape[2], 2, 3))

        def _encode_tiled_owned(self, pixels, **kwargs):
            self.calls.append({"route": "encode-owned", "shape": list(pixels.shape), **kwargs})
            return torch.zeros((1, 4, pixels.shape[2], 2, 3))

        def decode_tiled_(self, samples, **kwargs):
            self.calls.append({"route": "decode-2d", "shape": list(samples.shape), **kwargs})
            return torch.zeros((1, 3, 16, 20))

        def decode_tiled_3d(self, samples, **kwargs):
            self.calls.append({"route": "decode-3d", "shape": list(samples.shape), **kwargs})
            return torch.zeros((1, 3, samples.shape[2], 16, 20))

        def _decode_tiled_owned(self, samples, **kwargs):
            self.calls.append({"route": "decode-owned", "shape": list(samples.shape), **kwargs})
            return torch.zeros((1, 3, samples.shape[2], 16, 20))

    original_load_models = comfy_sd.model_management.load_models_gpu
    original_device_context = comfy_sd.model_management.cuda_device_context
    comfy_sd.model_management.load_models_gpu = lambda *args, **kwargs: None
    comfy_sd.model_management.cuda_device_context = lambda device: nullcontext()
    try:
        route_encode_2d = RoutingVAE(2)
        comfy_sd.VAE.encode_tiled(route_encode_2d, torch.zeros((1, 12, 16, 3)), tile_x=8, tile_y=6, overlap=2, tile_t=64, overlap_t=8)
        assert route_encode_2d.calls == [{"route": "encode-2d", "shape": [1, 3, 12, 16], "tile_x": 8, "tile_y": 6, "overlap": 2}]

        route_encode_3d = RoutingVAE(3)
        comfy_sd.VAE.encode_tiled(route_encode_3d, torch.zeros((10, 12, 16, 3)), tile_x=8, tile_y=6, overlap=2, tile_t=64, overlap_t=8)
        assert route_encode_3d.calls == [{"route": "encode-3d", "shape": [1, 3, 9, 12, 16], "tile_x": 8, "tile_y": 6, "overlap": (5, 2, 2), "tile_t": 61}]

        route_encode_owned = RoutingVAE(3, handles_tiling=True)
        comfy_sd.VAE.encode_tiled(route_encode_owned, torch.zeros((10, 12, 16, 3)), tile_x=8, tile_y=6, overlap=2, tile_t=64, overlap_t=8)
        assert route_encode_owned.calls == [{"route": "encode-owned", "shape": [1, 3, 10, 12, 16], "tile_x": 8, "tile_y": 6, "overlap": 2, "tile_t": 64, "overlap_t": 8}]

        route_decode_2d = RoutingVAE(2)
        decoded_2d = comfy_sd.VAE.decode_tiled(route_decode_2d, torch.zeros((1, 4, 2, 3)), tile_x=8, tile_y=6, overlap=2, tile_t=64, overlap_t=8)
        assert route_decode_2d.calls == [{"route": "decode-2d", "shape": [1, 4, 2, 3], "tile_x": 8, "tile_y": 6, "overlap": 2}]
        assert list(decoded_2d.shape) == [1, 16, 20, 3]

        route_decode_3d = RoutingVAE(3)
        decoded_3d = comfy_sd.VAE.decode_tiled(route_decode_3d, torch.zeros((1, 4, 9, 2, 3)), tile_x=8, tile_y=6, overlap=2, tile_t=7, overlap_t=3)
        assert route_decode_3d.calls == [{"route": "decode-3d", "shape": [1, 4, 9, 2, 3], "tile_x": 8, "tile_y": 6, "overlap": (3, 2, 2), "tile_t": 7}]
        assert list(decoded_3d.shape) == [1, 9, 16, 20, 3]

        route_decode_owned = RoutingVAE(3, handles_tiling=True)
        comfy_sd.VAE.decode_tiled(route_decode_owned, torch.zeros((1, 4, 9, 2, 3)), tile_x=8, tile_y=6, overlap=2, tile_t=7, overlap_t=3)
        assert route_decode_owned.calls == [{"route": "decode-owned", "shape": [1, 4, 9, 2, 3], "tile_x": 8, "tile_y": 6, "overlap": 2, "tile_t": 7, "overlap_t": 3}]
    finally:
        comfy_sd.model_management.load_models_gpu = original_load_models
        comfy_sd.model_management.cuda_device_context = original_device_context

    class FakeTomeModel:
        def __init__(self, origin="source") -> None:
            self.origin = origin
            self.attn1 = None
            self.attn1_output = None

        def clone(self):
            return FakeTomeModel(origin="clone")

        def set_model_attn1_patch(self, fn):
            self.attn1 = fn

        def set_model_attn1_output_patch(self, fn):
            self.attn1_output = fn

    original_tome = FakeTomeModel()
    (patched_tome,) = output_args(nodes_tomesd.TomePatchModel.execute(original_tome, 0.25))
    assert patched_tome is not original_tome and patched_tome.origin == "clone"
    assert callable(patched_tome.attn1) and callable(patched_tome.attn1_output)
    torch.manual_seed(1234)
    q = torch.arange(32.0).reshape(1, 16, 2) + 1.0
    k = q + 100
    v = q + 200
    merged_q, returned_k, returned_v = patched_tome.attn1(q, k, v, {"original_shape": (1, 4, 4, 4)})
    assert list(merged_q.shape) == [1, 12, 2]
    assert returned_k is k and returned_v is v
    restored = patched_tome.attn1_output(merged_q, {})
    assert list(restored.shape) == [1, 16, 2]
    downsampled = torch.arange(8.0).reshape(1, 4, 2) + 1.0
    identity_merge, identity_unmerge = nodes_tomesd.get_functions(downsampled, 0.5, (1, 4, 4, 4))
    assert identity_merge(downsampled) is downsampled
    assert identity_unmerge(downsampled) is downsampled
    zero_merge, zero_unmerge = nodes_tomesd.get_functions(q, 0.0, (1, 4, 4, 4))
    assert zero_merge(q) is q and zero_unmerge(q) is q
    zero_metric = torch.zeros((1, 16, 2))
    zero_metric_merge, _ = nodes_tomesd.get_functions(zero_metric, 0.25, (1, 4, 4, 4))
    assert list(zero_metric_merge(zero_metric).shape) == [1, 12, 2]
    try:
        nodes_tomesd.get_functions(torch.ones((1, 17, 2)), 0.25, (1, 4, 4, 4))
    except ZeroDivisionError:
        query_longer_error = True
    else:
        query_longer_error = False
    assert query_longer_error

    class FakeSampling:
        def percent_to_sigma(self, percent):
            return 10.0 * (1.0 - percent)

    class FakeDownscaleModel:
        def __init__(self, origin="source") -> None:
            self.origin = origin
            self.input_patch = None
            self.after_skip_patch = None
            self.output_patch = None

        def get_model_object(self, name):
            assert name == "model_sampling"
            return FakeSampling()

        def clone(self):
            return FakeDownscaleModel(origin="clone")

        def set_model_input_block_patch(self, fn):
            self.input_patch = fn

        def set_model_input_block_patch_after_skip(self, fn):
            self.after_skip_patch = fn

        def set_model_output_block_patch(self, fn):
            self.output_patch = fn

    resize_calls: list[dict[str, object]] = []
    original_upscale = nodes_downscale.comfy.utils.common_upscale

    def fake_upscale(tensor, width, height, method, crop):
        resize_calls.append({"input": list(tensor.shape), "width": width, "height": height, "method": method, "crop": crop})
        return torch.zeros((tensor.shape[0], tensor.shape[1], height, width), dtype=tensor.dtype)

    nodes_downscale.comfy.utils.common_upscale = fake_upscale
    try:
        original_model = FakeDownscaleModel()
        (patched_downscale,) = output_args(nodes_downscale.PatchModelAddDownscale.execute(
            original_model, 3, 2.0, 0.0, 0.35, True, "bicubic", "bilinear"
        ))
        assert patched_downscale is not original_model and patched_downscale.origin == "clone"
        assert patched_downscale.input_patch is None and callable(patched_downscale.after_skip_patch)
        h = torch.zeros((1, 4, 8, 10))
        shrunk = patched_downscale.after_skip_patch(h, {"block": ("input", 3), "sigmas": torch.tensor([8.0])})
        assert list(shrunk.shape) == [1, 4, 4, 5]
        assert patched_downscale.after_skip_patch(h, {"block": ("input", 2), "sigmas": torch.tensor([8.0])}) is h
        assert patched_downscale.after_skip_patch(h, {"block": ("input", 3), "sigmas": torch.tensor([6.0])}) is h
        hsp = torch.zeros((1, 4, 8, 10))
        expanded, returned_hsp = patched_downscale.output_patch(shrunk, hsp, {})
        assert list(expanded.shape) == [1, 4, 8, 10] and returned_hsp is hsp
        width_only = torch.zeros((1, 4, 8, 5))
        same_width_only, _ = patched_downscale.output_patch(width_only, hsp, {})
        assert same_width_only is width_only

        (before_skip,) = output_args(nodes_downscale.PatchModelAddDownscale.execute(
            original_model, 3, 2.0, 0.0, 0.35, False, "area", "nearest-exact"
        ))
        assert callable(before_skip.input_patch) and before_skip.after_skip_patch is None
    finally:
        nodes_downscale.comfy.utils.common_upscale = original_upscale

    assert resize_calls[0] == {"input": [1, 4, 8, 10], "width": 5, "height": 4, "method": "bicubic", "crop": "disabled"}
    assert resize_calls[1] == {"input": [1, 4, 4, 5], "width": 10, "height": 8, "method": "bilinear", "crop": "disabled"}

    print(json.dumps({
        "decode": {"shape": list(decoded.shape), "call": decode_vae.calls[0], "imageTemporal": [image_vae.calls[0]["tile_t"], image_vae.calls[0]["overlap_t"]], "nestedShape": nested_vae.calls[0]["latent_shape"], "nestedFirst": nested_vae.calls[0]["latent_first"]},
        "encode": {"shape": list(latent["samples"].shape), "call": encode_vae.calls[0], "cropShape": list(cropped.shape), "padShape": list(padded.shape), "padValue": padded[0, 0, 0, 2].item()},
        "vaeCore": {"encodeGrids": encode_grids, "decodeGrids": decode_grids, "baseEncodeMean": base_encode.mean().item(), "baseDecodeMean": base_decode.mean().item(), "encode2d": route_encode_2d.calls[0], "encode3d": route_encode_3d.calls[0], "encodeOwned": route_encode_owned.calls[0], "decode2d": route_decode_2d.calls[0], "decode3d": route_decode_3d.calls[0], "decodeOwned": route_decode_owned.calls[0]},
        "tome": {"merged": list(merged_q.shape), "restored": list(restored.shape), "clone": patched_tome.origin, "zeroMetricMerged": list(zero_metric_merge(zero_metric).shape), "queryLongerError": query_longer_error},
        "downscale": {"shrunk": list(shrunk.shape), "expanded": list(expanded.shape), "resizeCalls": resize_calls, "heightOnlySkipped": same_width_only is width_only},
    }, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
