from __future__ import annotations

import json
import struct
import sys
import tempfile
import wave
from pathlib import Path


def saved_path(root: Path, result: dict[str, object]) -> Path:
    return root / "output" / str(result["subfolder"]) / str(result["filename"])


def inspect_audio(path: Path) -> dict[str, object]:
    import av

    with av.open(str(path)) as container:
        stream = container.streams.audio[0]
        return {
            "codec": stream.codec_context.name,
            "sampleRate": stream.codec_context.sample_rate,
            "layout": stream.codec_context.layout.name,
        }


def write_pcm16_wav(path: Path) -> list[int]:
    samples = [-32768, -16384, -1, 0, 1, 8192, 16384, 32767] * 10
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as output:
        output.setnchannels(1)
        output.setsampwidth(2)
        output.setframerate(8000)
        output.writeframes(struct.pack(f"<{len(samples)}h", *samples))
    return samples


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit(
            "usage: deprecated_audio_synthetic_probe.py <pinned-comfyui-source>"
        )
    source = Path(sys.argv[1]).resolve()
    sys.path.insert(0, str(source))

    import folder_paths
    import torch

    from comfy.cli_args import args
    from comfy_extras.nodes_audio import (
        RecordAudio,
        SaveAudio,
        SaveAudioMP3,
        SaveAudioOpus,
        load,
    )

    previous_directories = (
        folder_paths.get_input_directory(),
        folder_paths.get_output_directory(),
        folder_paths.get_temp_directory(),
    )
    previous_disable_metadata = args.disable_metadata

    with tempfile.TemporaryDirectory(prefix="nodes-wizard-deprecated-audio-") as name:
        root = Path(name)
        for directory in ("input", "output", "temp"):
            (root / directory).mkdir()
        folder_paths.set_input_directory(str(root / "input"))
        folder_paths.set_output_directory(str(root / "output"))
        folder_paths.set_temp_directory(str(root / "temp"))
        # Direct class calls have no execution-time hidden prompt fields.
        args.disable_metadata = True

        try:
            stereo_batch = {
                "waveform": (
                    torch.arange(2 * 2 * 800, dtype=torch.float32)
                    .reshape(2, 2, 800)
                    / 6400.0
                    - 0.25
                ),
                "sample_rate": 8000,
            }
            flac_output = SaveAudio.execute(
                audio=stereo_batch,
                filename_prefix="legacy/flac_%batch_num%",
            )
            assert flac_output.args[0] is stereo_batch
            flac_results = flac_output.ui.results
            assert len(flac_results) == 2
            assert [item["type"] for item in flac_results] == ["output", "output"]
            assert [item["filename"] for item in flac_results] == [
                "flac_0_00001.flac",
                "flac_1_00002.flac",
            ]
            flac_info = inspect_audio(saved_path(root, flac_results[0]))
            assert flac_info == {
                "codec": "flac",
                "sampleRate": 8000,
                "layout": "stereo",
            }
            multichannel_audio = {
                "waveform": torch.arange(3 * 80, dtype=torch.float32).reshape(
                    1, 3, 80
                )
                / 1000.0,
                "sample_rate": 8000,
            }
            multichannel_output = SaveAudio.execute(
                audio=multichannel_audio,
                filename_prefix="legacy/flac_three_channels",
            )
            multichannel_path = saved_path(root, multichannel_output.ui.results[0])
            multichannel_decoded, multichannel_rate = load(str(multichannel_path))
            assert multichannel_rate == 8000
            assert multichannel_decoded.shape == (2, 120)

            mono_44100 = {
                "waveform": torch.linspace(-0.1, 0.1, 4410).reshape(1, 1, -1),
                "sample_rate": 44100,
            }
            stereo_44100 = {
                "waveform": mono_44100["waveform"].repeat(1, 2, 1),
                "sample_rate": 44100,
            }

            mp3_results: dict[str, dict[str, object]] = {}
            for quality in ("V0", "128k", "320k"):
                output = SaveAudioMP3.execute(
                    audio=mono_44100,
                    filename_prefix=f"legacy/mp3_{quality}",
                    quality=quality,
                )
                assert output.args[0] is mono_44100
                result = output.ui.results[0]
                info = inspect_audio(saved_path(root, result))
                assert str(info["codec"]).startswith("mp3")
                assert info["sampleRate"] == 44100
                assert info["layout"] == "mono"
                mp3_results[quality] = info

            # The direct Python default is 128k; the runtime schema default is V0.
            mp3_default = SaveAudioMP3.execute(
                audio=mono_44100,
                filename_prefix="legacy/mp3_python_default",
            )
            assert mp3_default.args[0] is mono_44100
            assert saved_path(root, mp3_default.ui.results[0]).is_file()

            opus_results: dict[str, dict[str, object]] = {}
            for quality in ("64k", "96k", "128k", "192k", "320k"):
                audio = stereo_44100 if quality == "320k" else mono_44100
                output = SaveAudioOpus.execute(
                    audio=audio,
                    filename_prefix=f"legacy/opus_{quality}",
                    quality=quality,
                )
                assert output.args[0] is audio
                result = output.ui.results[0]
                info = inspect_audio(saved_path(root, result))
                assert info["codec"] == "opus"
                assert info["sampleRate"] == 48000
                assert info["layout"] == ("stereo" if quality == "320k" else "mono")
                opus_results[quality] = info

            opus_320k_mono_error = ""
            try:
                SaveAudioOpus.execute(
                    audio=mono_44100,
                    filename_prefix="legacy/opus_320k_mono",
                    quality="320k",
                )
            except Exception as exc:
                opus_320k_mono_error = str(exc)
            assert "Invalid argument" in opus_320k_mono_error

            # The direct Python default is the stale value V3. The helper accepts it,
            # but it does not select one of the explicit bitrate branches.
            opus_default = SaveAudioOpus.execute(
                audio=mono_44100,
                filename_prefix="legacy/opus_python_default",
            )
            assert opus_default.args[0] is mono_44100
            assert saved_path(root, opus_default.ui.results[0]).is_file()

            none_errors: dict[str, str] = {}
            for node in (SaveAudio, SaveAudioMP3, SaveAudioOpus):
                try:
                    node.execute(audio=None)
                except ValueError as exc:
                    none_errors[node.__name__] = str(exc)
            assert set(none_errors) == {"SaveAudio", "SaveAudioMP3", "SaveAudioOpus"}
            assert all("input audio is None" in value for value in none_errors.values())

            samples = write_pcm16_wav(root / "temp" / "audio" / "recording.wav")
            recorded = RecordAudio.execute(
                audio="audio/recording.wav [temp]"
            ).args[0]
            assert recorded["sample_rate"] == 8000
            assert recorded["waveform"].shape == (1, 1, 80)
            assert recorded["waveform"].dtype == torch.float32
            expected = torch.tensor(samples, dtype=torch.float32).reshape(1, 1, -1) / 32768
            assert torch.allclose(recorded["waveform"], expected)

            print(
                json.dumps(
                    {
                        "saveAudio": {
                            "batchFiles": len(flac_results),
                            "passthroughIdentity": flac_output.args[0] is stereo_batch,
                            "stream": flac_info,
                            "threeChannelDecodedShape": list(
                                multichannel_decoded.shape
                            ),
                        },
                        "saveAudioMP3": {
                            "qualities": mp3_results,
                            "pythonDefaultFile": True,
                        },
                        "saveAudioOpus": {
                            "qualities": opus_results,
                            "mono320kRejected": True,
                            "pythonDefaultFile": True,
                        },
                        "noneErrors": none_errors,
                        "recordAudio": {
                            "shape": list(recorded["waveform"].shape),
                            "sampleRate": recorded["sample_rate"],
                            "first": float(recorded["waveform"][0, 0, 0]),
                            "last": float(recorded["waveform"][0, 0, -1]),
                            "browserExecuted": False,
                        },
                    },
                    sort_keys=True,
                )
            )
        finally:
            folder_paths.set_input_directory(previous_directories[0])
            folder_paths.set_output_directory(previous_directories[1])
            folder_paths.set_temp_directory(previous_directories[2])
            args.disable_metadata = previous_disable_metadata


if __name__ == "__main__":
    main()
