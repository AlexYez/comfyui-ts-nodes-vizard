from __future__ import annotations

import json
import sys
from pathlib import Path
from types import SimpleNamespace


def output_arg(node_output, index: int = 0):
    return node_output.args[index]


def raises(expected: type[BaseException], callback) -> str:
    try:
        callback()
    except expected as exc:
        return str(exc)
    raise AssertionError(f"expected {expected.__name__}")


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit("usage: audio_model_loaders_synthetic_probe.py <pinned-comfyui-source>")
    source = Path(sys.argv[1]).resolve()
    sys.path.insert(0, str(source))

    import torch
    import comfy.audio_encoders.audio_encoders as audio_models
    import comfy.sd  # Populate the package attribute used by nodes_lt_audio.
    import comfy_extras.nodes_audio_encoder as audio_nodes
    import comfy_extras.nodes_lt_audio as ltx_nodes

    report: dict[str, object] = {}

    # Execute the exact LTXVAudioVAELoader method while replacing filesystem/model
    # boundaries. The production prefix helper is intentionally left intact.
    original_ltx = (
        ltx_nodes.folder_paths.get_full_path_or_raise,
        ltx_nodes.comfy.utils.load_torch_file,
        ltx_nodes.comfy.sd.VAE,
    )
    ltx_calls: dict[str, object] = {}

    class FakeVAE:
        fail = False

        def __init__(self, sd, metadata):
            self.sd = sd
            self.metadata = metadata
            self.validated = False

        def throw_exception_if_invalid(self):
            self.validated = True
            if self.fail:
                raise RuntimeError("invalid fake VAE")

    try:
        def fake_full_path(category, name):
            ltx_calls["path"] = [category, name]
            return f"/models/{category}/{name}"

        def fake_load_torch_file(path, return_metadata=False):
            ltx_calls["load"] = [path, return_metadata]
            return (
                {
                    "audio_vae.encoder.weight": torch.tensor([1.0]),
                    "vocoder.block.weight": torch.tensor([2.0]),
                    "diffusion_model.weight": torch.tensor([3.0]),
                },
                {"format": "synthetic-ltx"},
            )

        ltx_nodes.folder_paths.get_full_path_or_raise = fake_full_path
        ltx_nodes.comfy.utils.load_torch_file = fake_load_torch_file
        ltx_nodes.comfy.sd.VAE = FakeVAE
        vae = output_arg(ltx_nodes.LTXVAudioVAELoader.execute("ltx-test.safetensors"))
        assert isinstance(vae, FakeVAE)
        assert vae.validated
        assert sorted(vae.sd) == ["autoencoder.encoder.weight", "vocoder.block.weight"]
        assert vae.metadata == {"format": "synthetic-ltx"}
        assert ltx_calls["path"] == ["checkpoints", "ltx-test.safetensors"]
        assert ltx_calls["load"] == ["/models/checkpoints/ltx-test.safetensors", True]
        FakeVAE.fail = True
        assert "invalid fake VAE" in raises(
            RuntimeError,
            lambda: ltx_nodes.LTXVAudioVAELoader.execute("bad.safetensors"),
        )
        FakeVAE.fail = False
        report["ltxAudioVaeLoader"] = {
            "keys": sorted(vae.sd),
            "metadata": vae.metadata,
            "validated": vae.validated,
            "invalidRejected": True,
        }
    finally:
        (
            ltx_nodes.folder_paths.get_full_path_or_raise,
            ltx_nodes.comfy.utils.load_torch_file,
            ltx_nodes.comfy.sd.VAE,
        ) = original_ltx

    # Capture the exact two-file CLIP loader contract, including CPU placement.
    original_text = (
        ltx_nodes.folder_paths.get_full_path_or_raise,
        ltx_nodes.folder_paths.get_folder_paths,
        ltx_nodes.comfy.sd.load_clip,
    )
    clip_calls: list[dict[str, object]] = []
    clip_sentinel = object()
    try:
        ltx_nodes.folder_paths.get_full_path_or_raise = (
            lambda category, name: f"/models/{category}/{name}"
        )
        ltx_nodes.folder_paths.get_folder_paths = lambda category: [f"/models/{category}"]

        def fake_load_clip(**kwargs):
            clip_calls.append(kwargs)
            return clip_sentinel

        ltx_nodes.comfy.sd.load_clip = fake_load_clip
        default_clip = output_arg(
            ltx_nodes.LTXAVTextEncoderLoader.execute(
                "gemma.safetensors", "ltx.safetensors", "default"
            )
        )
        cpu_clip = output_arg(
            ltx_nodes.LTXAVTextEncoderLoader.execute(
                "gemma.safetensors", "ltx.safetensors", "cpu"
            )
        )
        assert default_clip is clip_sentinel and cpu_clip is clip_sentinel
        assert clip_calls[0]["ckpt_paths"] == [
            "/models/text_encoders/gemma.safetensors",
            "/models/checkpoints/ltx.safetensors",
        ]
        assert clip_calls[0]["embedding_directory"] == ["/models/embeddings"]
        assert clip_calls[0]["clip_type"] is ltx_nodes.comfy.sd.CLIPType.LTXV
        assert clip_calls[0]["model_options"] == {}
        cpu_options = clip_calls[1]["model_options"]
        assert cpu_options["load_device"] == torch.device("cpu")
        assert cpu_options["offload_device"] == torch.device("cpu")
        report["ltxTextEncoderLoader"] = {
            "paths": clip_calls[0]["ckpt_paths"],
            "clipType": str(clip_calls[0]["clip_type"]),
            "defaultOptions": clip_calls[0]["model_options"],
            "cpuDevices": [
                str(cpu_options["load_device"]),
                str(cpu_options["offload_device"]),
            ],
        }
    finally:
        (
            ltx_nodes.folder_paths.get_full_path_or_raise,
            ltx_nodes.folder_paths.get_folder_paths,
            ltx_nodes.comfy.sd.load_clip,
        ) = original_text

    # Exercise AudioEncoderLoader without allocating a real transformer.
    original_audio_loader = (
        audio_nodes.folder_paths.get_full_path_or_raise,
        audio_nodes.comfy.utils.load_torch_file,
        audio_nodes.comfy.audio_encoders.audio_encoders.load_audio_encoder_from_sd,
    )
    loader_calls: dict[str, object] = {}
    encoder_sentinel = object()
    try:
        audio_nodes.folder_paths.get_full_path_or_raise = (
            lambda category, name: f"/models/{category}/{name}"
        )

        def fake_audio_load(path, safe_load=False):
            loader_calls["load"] = [path, safe_load]
            return {"encoder.layer_norm.bias": torch.zeros(1024)}

        def fake_encoder_from_sd(sd):
            loader_calls["stateKeys"] = sorted(sd)
            return encoder_sentinel

        audio_nodes.comfy.utils.load_torch_file = fake_audio_load
        audio_nodes.comfy.audio_encoders.audio_encoders.load_audio_encoder_from_sd = fake_encoder_from_sd
        loaded = output_arg(audio_nodes.AudioEncoderLoader.execute("encoder.safetensors"))
        assert loaded is encoder_sentinel
        assert loader_calls["load"] == [
            "/models/audio_encoders/encoder.safetensors",
            True,
        ]
        audio_nodes.comfy.audio_encoders.audio_encoders.load_audio_encoder_from_sd = lambda sd: None
        assert "invalid" in raises(
            RuntimeError,
            lambda: audio_nodes.AudioEncoderLoader.execute("bad.safetensors"),
        )
        report["audioEncoderLoader"] = {
            "load": loader_calls["load"],
            "stateKeys": loader_calls["stateKeys"],
            "invalidRejected": True,
        }
    finally:
        (
            audio_nodes.folder_paths.get_full_path_or_raise,
            audio_nodes.comfy.utils.load_torch_file,
            audio_nodes.comfy.audio_encoders.audio_encoders.load_audio_encoder_from_sd,
        ) = original_audio_loader

    # The node is a direct delegate. Keep identity assertions so future copying or
    # key rewriting becomes visible.
    waveform = torch.arange(16, dtype=torch.float32).reshape(1, 2, 8)
    encoder_output = {
        "encoded_audio": torch.ones((1, 2, 3)),
        "encoded_audio_all_layers": (torch.zeros((1, 2, 3)),),
        "audio_samples": 8,
    }

    class FakeEncoder:
        def __init__(self):
            self.args = None

        def encode_audio(self, input_waveform, sample_rate):
            self.args = (input_waveform, sample_rate)
            return encoder_output

    fake_encoder = FakeEncoder()
    delegated = output_arg(
        audio_nodes.AudioEncoderEncode.execute(
            fake_encoder,
            {"waveform": waveform, "sample_rate": 8000, "metadata": "ignored"},
        )
    )
    assert fake_encoder.args[0] is waveform and fake_encoder.args[1] == 8000
    assert delegated is encoder_output

    # Execute the production AudioEncoderModel.encode_audio method with only its
    # heavy neural model and resampler replaced.
    original_wrapper = (
        audio_models.comfy.model_management.load_model_gpu,
        audio_models.torchaudio.functional.resample,
    )
    wrapper_calls: dict[str, object] = {}

    class FakeModel:
        def __call__(self, audio):
            wrapper_calls["modelInputShape"] = list(audio.shape)
            final = audio.mean(dim=1).unsqueeze(-1)
            return final, (final - 1, final)

    fake_wrapper = SimpleNamespace(
        patcher=object(),
        model_sample_rate=16000,
        load_device=torch.device("cpu"),
        model=FakeModel(),
    )
    try:
        audio_models.comfy.model_management.load_model_gpu = (
            lambda patcher: wrapper_calls.setdefault("patcher", patcher)
        )

        def fake_resample(input_waveform, source_rate, target_rate):
            wrapper_calls["resample"] = [source_rate, target_rate, list(input_waveform.shape)]
            return input_waveform.repeat_interleave(2, dim=-1)

        audio_models.torchaudio.functional.resample = fake_resample
        wrapper_output = audio_models.AudioEncoderModel.encode_audio(
            fake_wrapper, waveform, 8000
        )
        assert wrapper_calls["patcher"] is fake_wrapper.patcher
        assert wrapper_calls["resample"] == [8000, 16000, [1, 2, 8]]
        assert wrapper_calls["modelInputShape"] == [1, 2, 16]
        assert wrapper_output["audio_samples"] == 16
        assert len(wrapper_output["encoded_audio_all_layers"]) == 2
        report["audioEncoderEncode"] = {
            "delegatesIdentity": delegated is encoder_output,
            "resample": wrapper_calls["resample"],
            "modelInputShape": wrapper_calls["modelInputShape"],
            "keys": sorted(wrapper_output),
            "audioSamples": wrapper_output["audio_samples"],
            "layerCount": len(wrapper_output["encoded_audio_all_layers"]),
        }
    finally:
        (
            audio_models.comfy.model_management.load_model_gpu,
            audio_models.torchaudio.functional.resample,
        ) = original_wrapper

    print(json.dumps(report, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
