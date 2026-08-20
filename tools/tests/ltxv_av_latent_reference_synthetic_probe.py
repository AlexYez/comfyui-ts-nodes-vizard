from __future__ import annotations

import json
import sys
from pathlib import Path
from types import SimpleNamespace


def output_args(node_output):
    return node_output.args


def raises(expected: type[BaseException], callback) -> str:
    try:
        callback()
    except expected as exc:
        return str(exc)
    raise AssertionError(f"expected {expected.__name__}")


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit("usage: ltxv_av_latent_reference_synthetic_probe.py <pinned-comfyui-source>")
    source = Path(sys.argv[1]).resolve()
    sys.path.insert(0, str(source))

    import torch
    import comfy.nested_tensor
    import comfy_extras.nodes_lt as nodes_lt
    import comfy_extras.nodes_lt_audio as nodes_lt_audio

    class EmptyAudioVAE:
        latent_channels = 4

        def __init__(self) -> None:
            self.calls: list[tuple[int, float]] = []
            self.first_stage_model = SimpleNamespace(
                latent_frequency_bins=6,
                num_of_latents_from_frames=self.num_of_latents_from_frames,
            )

        def num_of_latents_from_frames(self, frames: int, rate: float) -> int:
            self.calls.append((frames, rate))
            return 11

    empty_vae = EmptyAudioVAE()
    old_device = nodes_lt_audio.comfy.model_management.intermediate_device
    nodes_lt_audio.comfy.model_management.intermediate_device = lambda: torch.device("cpu")
    try:
        (empty_latent,) = output_args(
            nodes_lt_audio.LTXVEmptyLatentAudio.execute(97, 25.0, 2, empty_vae)
        )
    finally:
        nodes_lt_audio.comfy.model_management.intermediate_device = old_device
    assert empty_vae.calls == [(97, 25.0)]
    assert list(empty_latent["samples"].shape) == [2, 4, 11, 6]
    assert empty_latent["samples"].dtype == torch.float32
    assert empty_latent["samples"].device.type == "cpu"
    assert not bool(empty_latent["samples"].any())
    assert empty_latent["type"] == "audio"
    assert "Audio VAE model is required" in raises(
        AssertionError,
        lambda: nodes_lt_audio.LTXVEmptyLatentAudio.execute(97, 25.0, 1, None),
    )

    video = torch.arange(24, dtype=torch.float32).reshape(1, 2, 3, 2, 2)
    audio = torch.arange(40, dtype=torch.float32).reshape(1, 2, 5, 4)
    video_mask = torch.zeros_like(video)
    shared_video = {"source": "video"}
    shared_audio = {"source": "audio"}
    video_latent = {
        "samples": video,
        "noise_mask": video_mask,
        "origin": "video",
        "shared": shared_video,
        "video_only": 7,
    }
    audio_latent = {
        "samples": audio,
        "origin": "audio",
        "shared": shared_audio,
        "audio_only": 9,
    }
    (joint,) = output_args(nodes_lt.LTXVConcatAVLatent.execute(video_latent, audio_latent))
    streams = joint["samples"].unbind()
    masks = joint["noise_mask"].unbind()
    assert streams[0] is video and streams[1] is audio
    assert masks[0] is video_mask and torch.equal(masks[1], torch.ones_like(audio))
    assert joint["origin"] == "audio" and joint["shared"] is shared_audio
    assert joint["video_only"] == 7 and joint["audio_only"] == 9
    assert joint["samples"].shape == video.shape
    assert joint["samples"].ndim == 5

    video_out, audio_out = output_args(nodes_lt.LTXVSeparateAVLatent.execute(joint))
    assert video_out is not joint and audio_out is not joint
    assert video_out["samples"] is video and audio_out["samples"] is audio
    assert video_out["noise_mask"] is video_mask
    assert torch.equal(audio_out["noise_mask"], torch.ones_like(audio))
    assert video_out["shared"] is shared_audio and audio_out["shared"] is shared_audio

    old_audio = torch.full((1, 2, 5, 4), 8.0)
    old_audio_mask = torch.zeros_like(old_audio)
    existing = {
        "samples": comfy.nested_tensor.NestedTensor((video, old_audio)),
        "noise_mask": comfy.nested_tensor.NestedTensor((video_mask, old_audio_mask)),
        "stage": "first",
    }
    short_audio = torch.full((1, 2, 3, 4), 2.0)
    short_mask = torch.zeros_like(short_audio)
    (replaced,) = output_args(
        nodes_lt.LTXVConcatAVLatent.execute(
            existing,
            {"samples": short_audio, "noise_mask": short_mask, "stage": "second"},
        )
    )
    replaced_audio = replaced["samples"].unbind()[1]
    replaced_mask = replaced["noise_mask"].unbind()[1]
    assert list(replaced_audio.shape) == [1, 2, 5, 4]
    assert torch.equal(replaced_audio[:, :, :3], short_audio)
    assert not bool(replaced_audio[:, :, 3:].any())
    assert not bool(replaced_mask[:, :, :3].any())
    assert bool(replaced_mask[:, :, 3:].all())
    assert replaced["stage"] == "second"

    long_audio = torch.arange(56, dtype=torch.float32).reshape(1, 2, 7, 4)
    (trimmed,) = output_args(
        nodes_lt.LTXVConcatAVLatent.execute(existing, {"samples": long_audio})
    )
    assert torch.equal(trimmed["samples"].unbind()[1], long_audio[:, :, :5])
    mismatch_error = raises(
        ValueError,
        lambda: nodes_lt.LTXVConcatAVLatent.execute(
            existing,
            {"samples": torch.zeros((2, 2, 3, 4))},
        ),
    )
    assert "cannot be fitted" in mismatch_error

    extra = torch.ones((1, 1, 1))
    extra_joint = {"samples": comfy.nested_tensor.NestedTensor((video, audio, extra))}
    extra_video, extra_audio = output_args(nodes_lt.LTXVSeparateAVLatent.execute(extra_joint))
    assert extra_video["samples"] is video and extra_audio["samples"] is audio

    class ReferenceVAE:
        audio_sample_rate = 16000

        def __init__(self) -> None:
            self.encode_shapes: list[list[int]] = []

        def encode(self, waveform):
            self.encode_shapes.append(list(waveform.shape))
            return torch.arange(24, dtype=torch.float32).reshape(1, 2, 3, 4)

    class Sampling:
        @staticmethod
        def percent_to_sigma(percent: float) -> float:
            return (1.0 - percent) * 10.0

    class FakeModel:
        def __init__(self, marker: str = "original") -> None:
            self.marker = marker
            self.callback = None
            self.sampling = Sampling()

        def clone(self):
            return FakeModel("clone")

        def get_model_object(self, name: str):
            assert name == "model_sampling"
            return self.sampling

        def set_model_sampler_post_cfg_function(self, callback) -> None:
            self.callback = callback

    reference_vae = ReferenceVAE()
    reference_audio = {
        "waveform": torch.arange(8, dtype=torch.float32).reshape(1, 1, 8),
        "sample_rate": 8000,
    }
    positive = [[torch.tensor([[1.0]]), {"branch": "positive"}]]
    negative = [[torch.tensor([[0.0]]), {"branch": "negative"}]]
    patched, positive_out, negative_out = output_args(
        nodes_lt.LTXVReferenceAudio.execute(
            FakeModel(), positive, negative, reference_audio, reference_vae, 3.0, 0.0, 1.0
        )
    )
    assert patched.marker == "clone" and patched.callback is not None
    assert reference_vae.encode_shapes == [[1, 16, 1]]
    assert "ref_audio" not in positive[0][1] and "ref_audio" not in negative[0][1]
    positive_tokens = positive_out[0][1]["ref_audio"]["tokens"]
    negative_tokens = negative_out[0][1]["ref_audio"]["tokens"]
    assert list(positive_tokens.shape) == [1, 3, 8]
    assert positive_tokens is negative_tokens

    calls: list[dict[str, object]] = []
    old_calc = nodes_lt.comfy.samplers.calc_cond_batch

    def fake_calc(model, conds, x, sigma, model_options):
        calls.append({"conds": conds, "options": model_options, "sigma": sigma.clone()})
        return (torch.ones_like(x),)

    nodes_lt.comfy.samplers.calc_cond_batch = fake_calc
    try:
        cond_entry = {"model_conds": {"ref_audio": {"tokens": positive_tokens}, "keep": 4}, "tag": "original"}
        denoised = torch.full((1, 1, 2, 2), 2.0)
        cond_prediction = torch.full_like(denoised, 5.0)
        guided = patched.callback(
            {
                "model": object(),
                "cond_denoised": cond_prediction,
                "cond": [cond_entry],
                "denoised": denoised,
                "sigma": torch.tensor([5.0]),
                "model_options": {"kept": True},
                "input": torch.zeros_like(denoised),
            }
        )
        assert torch.equal(guided, torch.full_like(denoised, 14.0))
        assert len(calls) == 1
        no_ref_entry = calls[0]["conds"][0][0]
        assert "ref_audio" not in no_ref_entry["model_conds"]
        assert no_ref_entry["model_conds"]["keep"] == 4
        assert "ref_audio" in cond_entry["model_conds"]

        zero_model, zero_positive, _ = output_args(
            nodes_lt.LTXVReferenceAudio.execute(
                FakeModel(), positive, negative, reference_audio, reference_vae, 0.0, 0.0, 1.0
            )
        )
        before = len(calls)
        zero_result = zero_model.callback(
            {
                "denoised": denoised,
                "sigma": torch.tensor([5.0]),
            }
        )
        assert zero_result is denoised and len(calls) == before
        assert "ref_audio" in zero_positive[0][1]

        window_model, _, _ = output_args(
            nodes_lt.LTXVReferenceAudio.execute(
                FakeModel(), positive, negative, reference_audio, reference_vae, 3.0, 0.2, 0.4
            )
        )
        before = len(calls)
        outside_result = window_model.callback(
            {
                "denoised": denoised,
                "sigma": torch.tensor([9.0]),
            }
        )
        assert outside_result is denoised and len(calls) == before
    finally:
        nodes_lt.comfy.samplers.calc_cond_batch = old_calc

    print(
        json.dumps(
            {
                "empty": {
                    "shape": list(empty_latent["samples"].shape),
                    "dtype": str(empty_latent["samples"].dtype),
                    "type": empty_latent["type"],
                    "vaeCall": list(empty_vae.calls[0]),
                },
                "concat": {
                    "streamShapes": [list(t.shape) for t in streams],
                    "metadataWinner": joint["origin"],
                    "replacementShape": list(replaced_audio.shape),
                    "paddedTailMaskOnes": bool(replaced_mask[:, :, 3:].all()),
                    "trimmedLength": trimmed["samples"].unbind()[1].shape[2],
                    "mismatchRejected": "cannot be fitted" in mismatch_error,
                },
                "separate": {
                    "identityPreserved": video_out["samples"] is video and audio_out["samples"] is audio,
                    "extraStreamIgnored": extra_video["samples"] is video and extra_audio["samples"] is audio,
                },
                "reference": {
                    "vaeInputShape": reference_vae.encode_shapes[0],
                    "tokenShape": list(positive_tokens.shape),
                    "guidedMean": float(guided.mean()),
                    "noReferenceCalls": len(calls),
                    "scaleZeroKeepsTokens": "ref_audio" in zero_positive[0][1],
                    "scaleZeroBypassesExtraCall": zero_result is denoised,
                    "outsideWindowBypassesExtraCall": outside_result is denoised,
                },
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
