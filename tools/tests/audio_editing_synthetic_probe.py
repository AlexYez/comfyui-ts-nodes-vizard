from __future__ import annotations

import json
import math
import sys
from pathlib import Path


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
        raise SystemExit("usage: audio_editing_synthetic_probe.py <pinned-comfyui-source>")
    source = Path(sys.argv[1]).resolve()
    sys.path.insert(0, str(source))

    import torch
    import torchaudio
    import comfy_extras.nodes_audio as nodes_audio

    TrimAudioDuration = nodes_audio.TrimAudioDuration
    SplitAudioChannels = nodes_audio.SplitAudioChannels
    JoinAudioChannels = nodes_audio.JoinAudioChannels
    AudioAdjustVolume = nodes_audio.AudioAdjustVolume
    AudioEqualizer3Band = nodes_audio.AudioEqualizer3Band

    stereo = {
        "waveform": torch.arange(16, dtype=torch.float32).reshape(1, 2, 8),
        "sample_rate": 8,
        "marker": "not copied on normal branches",
    }

    trimmed = output_arg(TrimAudioDuration.execute(stereo, 0.25, 0.375))
    assert trimmed["waveform"].tolist() == [[[2.0, 3.0, 4.0], [10.0, 11.0, 12.0]]]
    assert trimmed["waveform"].untyped_storage().data_ptr() == stereo["waveform"].untyped_storage().data_ptr()
    assert set(trimmed) == {"waveform", "sample_rate"}
    negative = output_arg(TrimAudioDuration.execute(stereo, -0.5, 0.25))
    assert negative["waveform"].tolist() == [[[4.0, 5.0], [12.0, 13.0]]]
    clamped = output_arg(TrimAudioDuration.execute(stereo, -5.0, 0.25))
    assert clamped["waveform"].tolist() == [[[0.0, 1.0], [8.0, 9.0]]]
    # Python round uses ties-to-even: 0.0625 s * 8 Hz = 0.5 -> frame 0.
    tie = output_arg(TrimAudioDuration.execute(stereo, 0.0625, 0.125))
    assert tie["waveform"].tolist() == [[[0.0], [8.0]]]
    assert "Start time must be less" in raises(ValueError, lambda: TrimAudioDuration.execute(stereo, 0.0, 0.0))
    assert "Start time must be less" in raises(ValueError, lambda: TrimAudioDuration.execute(stereo, 2.0, 0.1))
    empty_audio = {"waveform": torch.empty((1, 2, 0)), "sample_rate": 8, "marker": "kept"}
    assert output_arg(TrimAudioDuration.execute(empty_audio, 5.0, 0.0)) is empty_audio
    assert output_arg(TrimAudioDuration.execute(None, 0.0, 1.0)) is None

    left, right = SplitAudioChannels.execute(stereo).args
    assert left["waveform"].shape == right["waveform"].shape == (1, 1, 8)
    assert left["waveform"].tolist() == [[[float(i) for i in range(8)]]]
    assert right["waveform"].tolist() == [[[float(i) for i in range(8, 16)]]]
    assert left["waveform"].untyped_storage().data_ptr() == stereo["waveform"].untyped_storage().data_ptr()
    assert right["waveform"].untyped_storage().data_ptr() == stereo["waveform"].untyped_storage().data_ptr()
    assert set(left) == set(right) == {"waveform", "sample_rate"}
    assert "must be stereo" in raises(
        ValueError,
        lambda: SplitAudioChannels.execute({"waveform": torch.zeros((1, 1, 8)), "sample_rate": 8}),
    )
    assert "must be stereo" in raises(
        ValueError,
        lambda: SplitAudioChannels.execute({"waveform": torch.zeros((1, 3, 8)), "sample_rate": 8}),
    )
    assert SplitAudioChannels.execute(None).args == (None, None)

    left_short = {"waveform": torch.arange(6, dtype=torch.float32).reshape(1, 1, 6), "sample_rate": 8, "left_meta": 1}
    right_short = {"waveform": torch.ones((1, 1, 4)), "sample_rate": 8, "right_meta": 2}
    joined = output_arg(JoinAudioChannels.execute(left_short, right_short))
    assert joined["waveform"].shape == (1, 2, 4)
    assert joined["waveform"][:, 0:1, :].tolist() == [[[0.0, 1.0, 2.0, 3.0]]]
    assert joined["waveform"][:, 1:2, :].tolist() == [[[1.0, 1.0, 1.0, 1.0]]]
    assert set(joined) == {"waveform", "sample_rate"}
    resampled = output_arg(
        JoinAudioChannels.execute(
            {"waveform": torch.arange(4, dtype=torch.float32).reshape(1, 1, 4), "sample_rate": 4},
            {"waveform": torch.ones((1, 1, 10)), "sample_rate": 8},
        )
    )
    assert resampled["sample_rate"] == 8
    assert resampled["waveform"].shape == (1, 2, 8)
    empty_join = output_arg(
        JoinAudioChannels.execute(
            {"waveform": torch.empty((1, 1, 0)), "sample_rate": 8},
            {"waveform": torch.empty((1, 1, 0)), "sample_rate": 8},
        )
    )
    assert empty_join["waveform"].shape == (1, 2, 0)
    assert output_arg(JoinAudioChannels.execute(None, right_short)) is right_short
    assert output_arg(JoinAudioChannels.execute(left_short, None)) is left_short
    assert output_arg(JoinAudioChannels.execute(None, None)) is None
    assert "must be mono" in raises(
        ValueError,
        lambda: JoinAudioChannels.execute(stereo, right_short),
    )
    raises(
        RuntimeError,
        lambda: JoinAudioChannels.execute(
            {"waveform": torch.zeros((2, 1, 4)), "sample_rate": 8},
            {"waveform": torch.zeros((1, 1, 4)), "sample_rate": 8},
        ),
    )

    volume_factors: dict[str, float] = {}
    for db in (-100, -6, 0, 1, 6, 100):
        result = output_arg(AudioAdjustVolume.execute(stereo, db))
        if db == 0:
            assert result is stereo
            factor = 1.0
        else:
            factor = 10 ** (db / 20)
            assert torch.allclose(result["waveform"], stereo["waveform"] * factor)
            assert set(result) == {"waveform", "sample_rate"}
        volume_factors[str(db)] = factor
    assert math.isclose(volume_factors["6"], 1.9952623149688795)
    assert float(output_arg(AudioAdjustVolume.execute(stereo, 100))["waveform"].max()) > 1.0
    assert output_arg(AudioAdjustVolume.execute(None, 6)) is None

    impulse = {"waveform": torch.zeros((1, 2, 128), dtype=torch.float32), "sample_rate": 8000, "meta": 1}
    impulse["waveform"][..., 64] = 1.0
    zero_eq = output_arg(AudioEqualizer3Band.execute(impulse, 0.0, 100, 0.0, 1000, 0.707, 0.0, 3000))
    assert torch.equal(zero_eq["waveform"], impulse["waveform"])
    assert zero_eq["waveform"].untyped_storage().data_ptr() != impulse["waveform"].untyped_storage().data_ptr()
    assert set(zero_eq) == {"waveform", "sample_rate"}
    assert output_arg(AudioEqualizer3Band.execute(None, 0.0, 100, 0.0, 1000, 0.707, 0.0, 3000)) is None
    empty_eq = {"waveform": torch.empty((1, 1, 0)), "sample_rate": 8000, "marker": 1}
    assert output_arg(AudioEqualizer3Band.execute(empty_eq, 1.0, 100, 1.0, 1000, 0.707, 1.0, 3000)) is empty_eq

    calls: list[tuple[str, float, float]] = []
    original = (
        nodes_audio.torchaudio.functional.bass_biquad,
        nodes_audio.torchaudio.functional.equalizer_biquad,
        nodes_audio.torchaudio.functional.treble_biquad,
    )

    def fake_bass(waveform, sample_rate, gain, central_freq, Q):
        calls.append(("low", float(central_freq), float(Q)))
        return waveform + 1

    def fake_mid(waveform, sample_rate, center_freq, gain, Q):
        calls.append(("mid", float(center_freq), float(Q)))
        return waveform + 2

    def fake_high(waveform, sample_rate, gain, central_freq, Q):
        calls.append(("high", float(central_freq), float(Q)))
        return waveform + 3

    try:
        nodes_audio.torchaudio.functional.bass_biquad = fake_bass
        nodes_audio.torchaudio.functional.equalizer_biquad = fake_mid
        nodes_audio.torchaudio.functional.treble_biquad = fake_high
        ordered = output_arg(AudioEqualizer3Band.execute(impulse, 2.0, 120, -2.0, 900, 1.5, 1.0, 4500))
        assert calls == [("low", 120.0, 0.707), ("mid", 900.0, 1.5), ("high", 4500.0, 0.707)]
        assert torch.equal(ordered["waveform"], impulse["waveform"] + 6)
    finally:
        (
            nodes_audio.torchaudio.functional.bass_biquad,
            nodes_audio.torchaudio.functional.equalizer_biquad,
            nodes_audio.torchaudio.functional.treble_biquad,
        ) = original

    assert torchaudio.__version__.startswith("2.11.")
    sample_rate = 8000
    time = torch.arange(sample_rate, dtype=torch.float32) / sample_rate
    sine = {"waveform": (0.5 * torch.sin(2 * torch.pi * 50 * time)).reshape(1, 1, -1), "sample_rate": sample_rate}
    boosted = output_arg(AudioEqualizer3Band.execute(sine, 24.0, 100, 0.0, 1000, 0.707, 0.0, 3000))
    assert bool(torch.isfinite(boosted["waveform"]).all())
    assert float(boosted["waveform"].abs().max()) <= 1.0
    above_nyquist = output_arg(AudioEqualizer3Band.execute(impulse, 0.0, 100, 0.0, 1000, 0.707, 6.0, 15000))
    assert bool(torch.isfinite(above_nyquist["waveform"]).all())

    print(
        json.dumps(
            {
                "trim": {"positive": [2, 5], "negative": [4, 6], "sharesStorage": True},
                "split": {"left": [1, 1, 8], "right": [1, 1, 8], "sharesStorage": True},
                "join": {"sameRate": [1, 2, 4], "resampled": [1, 2, 8], "outputRate": 8},
                "volumeFactors": volume_factors,
                "equalizer": {"order": [item[0] for item in calls], "torchaudio": torchaudio.__version__, "clampedPeak": float(boosted["waveform"].abs().max())},
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
