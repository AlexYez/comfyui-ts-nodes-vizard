from __future__ import annotations

import hashlib
import json
import shutil
import sys
import tempfile
from pathlib import Path


def saved_path(root: Path, folder: str, result: dict[str, object]) -> Path:
    return root / folder / str(result["subfolder"]) / str(result["filename"])


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit(
            "usage: audio_io_synthetic_probe.py <pinned-comfyui-source>"
        )
    source = Path(sys.argv[1]).resolve()
    sys.path.insert(0, str(source))

    import av
    import folder_paths
    import torch

    from comfy.cli_args import args
    from comfy_extras.nodes_audio import (
        AudioMerge,
        LoadAudio,
        PreviewAudio,
        SaveAudioAdvanced,
        load,
    )

    previous_directories = (
        folder_paths.get_input_directory(),
        folder_paths.get_output_directory(),
        folder_paths.get_temp_directory(),
    )
    previous_disable_metadata = args.disable_metadata

    with tempfile.TemporaryDirectory(prefix="nodes-wizard-audio-io-") as temp_name:
        root = Path(temp_name)
        for name in ("input", "output", "temp"):
            (root / name).mkdir()
        folder_paths.set_input_directory(str(root / "input"))
        folder_paths.set_output_directory(str(root / "output"))
        folder_paths.set_temp_directory(str(root / "temp"))
        # Direct class calls do not receive execution-time hidden prompt fields.
        args.disable_metadata = True

        try:
            batch_waveform = (
                torch.arange(2 * 2 * 800, dtype=torch.float32)
                .reshape(2, 2, 800)
                / 6400.0
                - 0.25
            )
            batch_audio = {"waveform": batch_waveform, "sample_rate": 8000}
            batch_saved = SaveAudioAdvanced.execute(
                audio=batch_audio,
                filename_prefix="probe/batch_%batch_num%",
                format={"format": "flac"},
            )
            assert batch_saved.args[0] is batch_audio
            batch_results = batch_saved.ui.results
            assert len(batch_results) == 2
            assert [item["type"] for item in batch_results] == ["output", "output"]
            assert [item["filename"] for item in batch_results] == [
                "batch_0_00001.flac",
                "batch_1_00002.flac",
            ]

            first_flac = saved_path(root, "output", batch_results[0])
            input_flac = root / "input" / "probe.flac"
            shutil.copy2(first_flac, input_flac)
            loaded = LoadAudio.execute(audio="probe.flac").args[0]
            assert loaded["waveform"].shape == (1, 2, 800)
            assert loaded["waveform"].dtype == torch.float32
            assert loaded["sample_rate"] == 8000
            expected_hash = hashlib.sha256(input_flac.read_bytes()).hexdigest()
            assert LoadAudio.fingerprint_inputs("probe.flac") == expected_hash

            output_before_preview = sorted((root / "output").rglob("*"))
            previewed = PreviewAudio.execute(audio=loaded)
            assert previewed.args[0] is loaded
            preview_results = previewed.ui.values
            assert len(preview_results) == 1
            assert preview_results[0]["type"] == "temp"
            assert preview_results[0]["filename"].endswith(".flac")
            preview_file = saved_path(root, "temp", preview_results[0])
            assert preview_file.is_file()
            assert sorted((root / "output").rglob("*")) == output_before_preview

            format_results: dict[str, dict[str, object]] = {}
            mono_44100 = {
                "waveform": torch.linspace(-0.1, 0.1, 4410).reshape(1, 1, -1),
                "sample_rate": 44100,
            }
            stereo_44100 = {
                "waveform": mono_44100["waveform"].repeat(1, 2, 1),
                "sample_rate": 44100,
            }
            variants = [
                ("flac", None),
                ("mp3", "V0"),
                ("mp3", "128k"),
                ("mp3", "320k"),
                ("opus", "64k"),
                ("opus", "96k"),
                ("opus", "128k"),
                ("opus", "192k"),
                ("opus", "320k"),
            ]
            opus_320k_mono_rejected = False
            try:
                SaveAudioAdvanced.execute(
                    audio=mono_44100,
                    filename_prefix="formats/opus_320k_mono",
                    format={"format": "opus", "quality": "320k"},
                )
            except Exception as exc:
                opus_320k_mono_rejected = "libopus" in str(exc)
            assert opus_320k_mono_rejected

            for index, (file_format, quality) in enumerate(variants):
                setting = {"format": file_format}
                if quality is not None:
                    setting["quality"] = quality
                test_audio = (
                    stereo_44100
                    if file_format == "opus" and quality == "320k"
                    else mono_44100
                )
                node_output = SaveAudioAdvanced.execute(
                    audio=test_audio,
                    filename_prefix=f"formats/probe_{index}",
                    format=setting,
                )
                assert node_output.args[0] is test_audio
                result = node_output.ui.results[0]
                path = saved_path(root, "output", result)
                assert path.suffix == f".{file_format}"
                with av.open(str(path)) as container:
                    stream = container.streams.audio[0]
                    codec = stream.codec_context.name
                    decoded_rate = stream.codec_context.sample_rate
                    layout = stream.codec_context.layout.name
                if file_format == "flac":
                    assert codec == "flac"
                    assert decoded_rate == 44100
                elif file_format == "mp3":
                    assert codec.startswith("mp3")
                    assert decoded_rate == 44100
                else:
                    assert codec == "opus"
                    assert decoded_rate == 48000
                expected_layout = (
                    "stereo"
                    if file_format == "opus" and quality == "320k"
                    else "mono"
                )
                assert layout == expected_layout
                format_results[f"{file_format}:{quality or '-'}"] = {
                    "codec": codec,
                    "sampleRate": decoded_rate,
                }

            multichannel_decoded: dict[str, list[int]] = {}
            for channels in (3, 4):
                multichannel_audio = {
                    "waveform": torch.arange(
                        channels * 80, dtype=torch.float32
                    ).reshape(1, channels, 80)
                    / 1000.0,
                    "sample_rate": 8000,
                }
                node_output = SaveAudioAdvanced.execute(
                    audio=multichannel_audio,
                    filename_prefix=f"channels/c{channels}",
                    format={"format": "flac"},
                )
                path = saved_path(root, "output", node_output.ui.results[0])
                decoded, decoded_rate = load(str(path))
                assert decoded_rate == 8000
                expected_length = channels * 80 // 2
                assert decoded.shape == (2, expected_length)
                multichannel_decoded[str(channels)] = list(decoded.shape)

            audio1 = {
                "waveform": torch.tensor(
                    [
                        [[0.2, 0.4, 0.6, 0.8], [0.1, 0.2, 0.3, 0.4]],
                        [[0.1, 0.1, 0.1, 0.1], [0.3, 0.3, 0.3, 0.3]],
                    ],
                    dtype=torch.float32,
                ),
                "sample_rate": 8000,
            }
            audio2 = {
                "waveform": torch.tensor(
                    [[[0.5, 1.0]]], dtype=torch.float32
                ),
                "sample_rate": 8000,
            }
            padded_audio2 = torch.tensor(
                [[[0.5, 1.0, 0.0, 0.0]]], dtype=torch.float32
            )
            merge_shapes: dict[str, list[int]] = {}
            for method in ("add", "mean", "subtract", "multiply"):
                merged = AudioMerge.execute(
                    audio1=audio1, audio2=audio2, merge_method=method
                ).args[0]
                if method == "add":
                    expected = audio1["waveform"] + padded_audio2
                elif method == "mean":
                    expected = (audio1["waveform"] + padded_audio2) / 2
                elif method == "subtract":
                    expected = audio1["waveform"] - padded_audio2
                else:
                    expected = audio1["waveform"] * padded_audio2
                peak = expected.abs().max()
                if peak > 1:
                    expected = expected / peak
                assert torch.allclose(merged["waveform"], expected)
                assert merged["sample_rate"] == 8000
                assert merged["waveform"].shape == (2, 2, 4)
                merge_shapes[method] = list(merged["waveform"].shape)

            resampled = AudioMerge.execute(
                audio1={
                    "waveform": torch.zeros((1, 1, 4), dtype=torch.float32),
                    "sample_rate": 4000,
                },
                audio2={
                    "waveform": torch.zeros((1, 1, 8), dtype=torch.float32),
                    "sample_rate": 8000,
                },
                merge_method="add",
            ).args[0]
            assert resampled["sample_rate"] == 8000
            assert resampled["waveform"].shape == (1, 1, 8)

            incompatible_error = None
            try:
                AudioMerge.execute(
                    audio1=audio1,
                    audio2={
                        "waveform": torch.zeros((1, 3, 4)),
                        "sample_rate": 8000,
                    },
                    merge_method="add",
                )
            except RuntimeError as exc:
                incompatible_error = str(exc)
            assert incompatible_error is not None

            print(
                json.dumps(
                    {
                        "loadAudio": {
                            "shape": list(loaded["waveform"].shape),
                            "sampleRate": loaded["sample_rate"],
                            "fingerprint": expected_hash,
                        },
                        "previewAudio": {
                            "files": len(preview_results),
                            "folderType": preview_results[0]["type"],
                            "passthroughIdentity": previewed.args[0] is loaded,
                        },
                        "saveAudioAdvanced": {
                            "batchFiles": len(batch_results),
                            "formats": format_results,
                            "multichannelDecodedShapes": multichannel_decoded,
                            "opus320kMonoRejected": opus_320k_mono_rejected,
                        },
                        "audioMerge": {
                            "shapes": merge_shapes,
                            "resampledShape": list(resampled["waveform"].shape),
                            "resampledRate": resampled["sample_rate"],
                            "incompatibleShapeRejected": True,
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
