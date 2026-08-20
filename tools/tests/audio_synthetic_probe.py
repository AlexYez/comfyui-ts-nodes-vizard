from __future__ import annotations

import json
import sys
from pathlib import Path


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit("usage: audio_synthetic_probe.py <pinned-comfyui-source>")
    source = Path(sys.argv[1]).resolve()
    sys.path.insert(0, str(source))

    import torch

    from comfy_extras.nodes_audio import (
        ConditioningStableAudio,
        EmptyAudio,
        EmptyLatentAudio,
        VAEDecodeAudio,
    )

    silent = EmptyAudio.execute(duration=0.01, sample_rate=8000, channels=1).args[0]
    assert silent["waveform"].shape == (1, 1, 80)
    assert silent["waveform"].dtype == torch.float32
    assert torch.count_nonzero(silent["waveform"]).item() == 0
    assert silent["sample_rate"] == 8000

    latent = EmptyLatentAudio.execute(seconds=1.0, batch_size=2).args[0]
    assert latent["samples"].shape == (2, 64, 22)
    assert torch.count_nonzero(latent["samples"]).item() == 0
    assert latent["type"] == "audio"
    assert latent["downscale_ratio_temporal"] == 2048

    positive_tensor = torch.arange(6, dtype=torch.float32).reshape(1, 2, 3)
    negative_tensor = torch.ones((1, 2, 3), dtype=torch.float32)
    positive = [[positive_tensor, {"source": "positive"}]]
    negative = [[negative_tensor, {"source": "negative"}]]
    timed_positive, timed_negative = ConditioningStableAudio.execute(
        positive=positive,
        negative=negative,
        seconds_start=2.5,
        seconds_total=12.0,
    ).args
    assert timed_positive[0][0] is positive_tensor
    assert timed_negative[0][0] is negative_tensor
    assert timed_positive[0][1] == {
        "source": "positive",
        "seconds_start": 2.5,
        "seconds_total": 12.0,
    }
    assert timed_negative[0][1] == {
        "source": "negative",
        "seconds_start": 2.5,
        "seconds_total": 12.0,
    }
    assert positive[0][1] == {"source": "positive"}
    assert negative[0][1] == {"source": "negative"}

    class StubVAE:
        audio_sample_rate_output = 48000

        def decode(self, samples):
            assert samples.shape == (1, 4, 2)
            return torch.arange(8, dtype=torch.float32).reshape(1, 4, 2)

    decoded = VAEDecodeAudio.execute(
        vae=StubVAE(),
        samples={
            "samples": torch.zeros((1, 4, 2), dtype=torch.float32),
            "sample_rate": 32000,
        },
    ).args[0]
    raw = torch.arange(8, dtype=torch.float32).reshape(1, 4, 2).movedim(-1, 1)
    divisor = torch.std(raw, dim=[1, 2], keepdim=True) * 5.0
    divisor[divisor < 1.0] = 1.0
    assert decoded["waveform"].shape == (1, 2, 4)
    assert torch.allclose(decoded["waveform"], raw / divisor)
    assert decoded["sample_rate"] == 32000

    vae_rate = VAEDecodeAudio.execute(
        vae=StubVAE(),
        samples={"samples": torch.zeros((1, 4, 2), dtype=torch.float32)},
    ).args[0]
    assert vae_rate["sample_rate"] == 48000

    print(
        json.dumps(
            {
                "conditioning": {
                    "positiveEntries": len(timed_positive),
                    "negativeEntries": len(timed_negative),
                    "secondsStart": timed_positive[0][1]["seconds_start"],
                    "secondsTotal": timed_positive[0][1]["seconds_total"],
                },
                "emptyAudio": {
                    "shape": list(silent["waveform"].shape),
                    "sampleRate": silent["sample_rate"],
                    "nonzero": int(torch.count_nonzero(silent["waveform"]).item()),
                },
                "emptyLatentAudio": {
                    "shape": list(latent["samples"].shape),
                    "type": latent["type"],
                    "downscaleRatioTemporal": latent["downscale_ratio_temporal"],
                    "nonzero": int(torch.count_nonzero(latent["samples"]).item()),
                },
                "vaeDecodeAudio": {
                    "shape": list(decoded["waveform"].shape),
                    "sampleRateFromSamples": decoded["sample_rate"],
                    "sampleRateFromVae": vae_rate["sample_rate"],
                },
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
