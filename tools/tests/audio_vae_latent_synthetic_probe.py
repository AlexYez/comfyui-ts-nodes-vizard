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


class NestedLatent:
    is_nested = True

    def __init__(self, *items):
        self.items = items

    def unbind(self):
        return self.items


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit("usage: audio_vae_latent_synthetic_probe.py <pinned-comfyui-source>")
    source = Path(sys.argv[1]).resolve()
    sys.path.insert(0, str(source))

    import torch
    import comfy_extras.nodes_audio as nodes_audio
    import comfy_extras.nodes_lt_audio as nodes_lt_audio

    class FakeVAE:
        audio_sample_rate = 16000
        audio_sample_rate_output = 22050
        first_stage_model = SimpleNamespace(output_sample_rate=24000)

        def __init__(self):
            self.encode_shapes: list[list[int]] = []
            self.decode_tiled_calls: list[dict[str, object]] = []
            self.decode_inputs: list[torch.Tensor] = []
            self.decode_tiled_result = torch.arange(12, dtype=torch.float32).reshape(1, 6, 2)
            self.decode_result = torch.arange(12, dtype=torch.float32).reshape(1, 6, 2)

        def encode(self, waveform):
            self.encode_shapes.append(list(waveform.shape))
            return waveform.mean(dim=-1, keepdim=True).movedim(1, -1)

        def decode_tiled(self, latent, **kwargs):
            self.decode_tiled_calls.append({
                "latentMean": float(latent.float().mean()),
                **kwargs,
            })
            return self.decode_tiled_result.clone()

        def decode(self, latent):
            self.decode_inputs.append(latent)
            return self.decode_result.clone()

    fake = FakeVAE()
    source_audio = {
        "waveform": torch.arange(8, dtype=torch.float32).reshape(1, 1, 8),
        "sample_rate": 8000,
        "metadata": "not copied",
    }
    encoded = output_arg(nodes_audio.VAEEncodeAudio.execute(fake, source_audio))
    assert fake.encode_shapes == [[1, 16, 1]]
    assert set(encoded) == {"samples"}
    assert list(encoded["samples"].shape) == [1, 1, 16]
    assert "input audio is None" in raises(
        ValueError,
        lambda: nodes_audio.VAEEncodeAudio.execute(fake, None),
    )

    ltx_encoded = output_arg(nodes_lt_audio.LTXVAudioVAEEncode.execute(source_audio, fake))
    assert fake.encode_shapes[-1] == [1, 16, 1]
    assert set(ltx_encoded) == {"samples"}
    assert list(ltx_encoded["samples"].shape) == [1, 1, 16]

    latent = torch.full((1, 4, 3), 2.0)
    tiled = output_arg(nodes_audio.VAEDecodeAudioTiled.execute(fake, {"samples": latent}, 512, 64))
    assert fake.decode_tiled_calls[-1] == {
        "latentMean": 2.0,
        "tile_x": 512,
        "tile_y": 512,
        "overlap": 64,
    }
    assert list(tiled["waveform"].shape) == [1, 2, 6]
    assert tiled["sample_rate"] == 22050
    assert float(tiled["waveform"].std()) < float(fake.decode_tiled_result.movedim(-1, 1).std())

    nested = NestedLatent(torch.zeros((1, 1, 1)), torch.full((1, 1, 1), 9.0))
    tiled_override = output_arg(
        nodes_audio.VAEDecodeAudioTiled.execute(
            fake,
            {"samples": nested, "sample_rate": 12345},
            256,
            32,
        )
    )
    assert fake.decode_tiled_calls[-1]["latentMean"] == 9.0
    assert tiled_override["sample_rate"] == 12345

    fake.decode_tiled_result = torch.ones((1, 1, 1), dtype=torch.float32)
    singleton = output_arg(
        nodes_audio.VAEDecodeAudioTiled.execute(fake, {"samples": latent}, 32, 0)
    )
    assert bool(torch.isnan(singleton["waveform"]).all())

    fake.decode_result = torch.arange(12, dtype=torch.float32).reshape(1, 6, 2)
    ltx_nested = NestedLatent(torch.zeros((1, 2, 2)), torch.full((1, 2, 2), 7.0))
    ltx_decoded = output_arg(
        nodes_lt_audio.LTXVAudioVAEDecode.execute(
            {"samples": ltx_nested, "sample_rate": 11111},
            fake,
        )
    )
    assert float(fake.decode_inputs[-1].mean()) == 7.0
    assert list(ltx_decoded["waveform"].shape) == [1, 2, 6]
    assert torch.equal(ltx_decoded["waveform"], fake.decode_result.movedim(-1, 1))
    assert ltx_decoded["sample_rate"] == 24000

    print(
        json.dumps(
            {
                "genericEncode": {
                    "vaeInputShape": fake.encode_shapes[0],
                    "latentShape": list(encoded["samples"].shape),
                    "keys": sorted(encoded),
                },
                "ltxEncode": {
                    "vaeInputShape": fake.encode_shapes[-1],
                    "keys": sorted(ltx_encoded),
                },
                "tiledDecode": {
                    "shape": list(tiled["waveform"].shape),
                    "sampleRate": tiled["sample_rate"],
                    "overrideRate": tiled_override["sample_rate"],
                    "nestedLastMean": fake.decode_tiled_calls[-2]["latentMean"],
                    "singletonNaN": bool(torch.isnan(singleton["waveform"]).all()),
                },
                "ltxDecode": {
                    "shape": list(ltx_decoded["waveform"].shape),
                    "sampleRate": ltx_decoded["sample_rate"],
                    "nestedLastMean": float(fake.decode_inputs[-1].mean()),
                    "unscaled": torch.equal(ltx_decoded["waveform"], fake.decode_result.movedim(-1, 1)),
                },
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
