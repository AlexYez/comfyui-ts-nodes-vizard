from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path


def make_video(path: Path, levels: list[int], fps: int = 4) -> None:
    import av
    import numpy as np

    with av.open(str(path), mode="w") as container:
        stream = container.add_stream("ffv1", rate=fps)
        stream.width = 16
        stream.height = 16
        stream.pix_fmt = "yuv444p"
        for level in levels:
            pixels = np.full((16, 16, 3), level, dtype=np.uint8)
            frame = av.VideoFrame.from_ndarray(pixels, format="rgb24")
            for packet in stream.encode(frame):
                container.mux(packet)
        for packet in stream.encode(None):
            container.mux(packet)


def decoded_ids(images, levels: list[int]) -> list[int]:
    result: list[int] = []
    for image in images:
        value = float(image.mean().item() * 255.0)
        result.append(min(range(len(levels)), key=lambda index: abs(levels[index] - value)))
    return result


def relative_sources(videos, base: Path) -> list[str]:
    return [
        Path(video.get_stream_source()).resolve().relative_to(base.resolve()).as_posix()
        for video in videos
    ]


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit(
            "usage: dataset_video_load_sample_crop_synthetic_probe.py "
            "<pinned-comfyui-source>"
        )

    source = Path(sys.argv[1]).resolve()
    sys.path.insert(0, str(source))

    import numpy as np
    import folder_paths
    from comfy_api.latest import InputImpl
    from comfy_extras.nodes_dataset import (
        LoadVideoDataSetFromFolderNode,
        LoadVideoTextDataSetFromFolderNode,
        VideoFrameSampleNode,
        VideoTemporalCropNode,
    )

    levels = [16 + index * 30 for index in range(8)]
    with tempfile.TemporaryDirectory(prefix="nodes-wizard-video-dataset-") as tmp:
        input_root = Path(tmp) / "input"
        input_root.mkdir()
        original_input_directory = folder_paths.get_input_directory
        folder_paths.get_input_directory = lambda: str(input_root)
        try:
            plain = input_root / "plain"
            plain.mkdir()
            (plain / "z.MP4").write_bytes(b"")
            (plain / "a.mkv").write_bytes(b"")
            (plain / "notes.txt").write_text("ignored", encoding="utf-8")
            (plain / "nested").mkdir()
            (plain / "nested" / "inside.mov").write_bytes(b"")

            plain_videos = LoadVideoDataSetFromFolderNode.execute(
                folder="plain"
            ).args[0]
            assert relative_sources(plain_videos, plain) == ["a.mkv", "z.MP4"]

            paired = input_root / "paired"
            paired.mkdir()
            (paired / "b.mov").write_bytes(b"")
            (paired / "b.txt").write_text("  bravo\n", encoding="utf-8")
            repeated = paired / "2_class"
            repeated.mkdir()
            (repeated / "a.mkv").write_bytes(b"")
            (repeated / "a.txt").write_text("\n alpha  ", encoding="utf-8")
            (repeated / "c.WEBM").write_bytes(b"")
            zero_repeat = paired / "0_skip"
            zero_repeat.mkdir()
            (zero_repeat / "never.avi").write_bytes(b"")
            ordinary = paired / "plain_class"
            ordinary.mkdir()
            (ordinary / "d.avi").write_bytes(b"")
            (ordinary / "d.txt").write_text("delta", encoding="utf-8")
            (ordinary / "deeper").mkdir()
            (ordinary / "deeper" / "ignored.mkv").write_bytes(b"")

            paired_videos, paired_texts = LoadVideoTextDataSetFromFolderNode.execute(
                folder="paired"
            ).args
            paired_sources = relative_sources(paired_videos, paired)
            assert paired_sources == [
                "2_class/a.mkv",
                "2_class/c.WEBM",
                "2_class/a.mkv",
                "2_class/c.WEBM",
                "b.mov",
                "plain_class/d.avi",
            ]
            assert paired_texts == ["alpha", "", "alpha", "", "bravo", "delta"]

            empty = input_root / "empty"
            empty.mkdir()
            plain_empty_error = None
            paired_empty_error = None
            traversal_error = None
            try:
                LoadVideoDataSetFromFolderNode.execute(folder="empty")
            except ValueError as exc:
                plain_empty_error = str(exc)
            try:
                LoadVideoTextDataSetFromFolderNode.execute(folder="empty")
            except ValueError as exc:
                paired_empty_error = str(exc)
            try:
                LoadVideoDataSetFromFolderNode.execute(folder="../outside")
            except ValueError as exc:
                traversal_error = str(exc)
            assert plain_empty_error and plain_empty_error.startswith("No video files found")
            assert paired_empty_error and paired_empty_error.startswith("No video files found")
            assert traversal_error and traversal_error.startswith("Invalid folder name")

            # AVI exposes an exact stream frame count to the pinned VideoFromFile
            # implementation, keeping this probe independent of container-duration
            # fallbacks.
            signal_path = input_root / "signal.avi"
            make_video(signal_path, levels)
            signal = InputImpl.VideoFromFile(str(signal_path))
            assert signal.get_frame_count() == 8
            assert float(signal.get_frame_rate()) == 4.0

            head = VideoFrameSampleNode.execute(
                video=signal, num_frames=3, strategy="head", seed=99
            ).args[0]
            tail = VideoFrameSampleNode.execute(
                video=signal, num_frames=3, strategy="tail", seed=99
            ).args[0]
            assert head.get_active_trim_window() == (0.0, 0.75)
            assert tail.get_active_trim_window() == (1.25, 0.75)
            assert head.get_stream_source() == signal.get_stream_source()
            assert tail.get_stream_source() == signal.get_stream_source()

            uniform = VideoFrameSampleNode.execute(
                video=signal, num_frames=4, strategy="uniform", seed=99
            ).args[0]
            uniform_components = uniform.get_components()
            uniform_ids = decoded_ids(uniform_components.images, levels)
            assert uniform_ids == [0, 2, 5, 7]
            assert float(uniform_components.frame_rate) == 4.0
            assert uniform_components.audio is None

            middle = VideoFrameSampleNode.execute(
                video=signal, num_frames=1, strategy="uniform", seed=99
            ).args[0]
            middle_ids = decoded_ids(middle.get_components().images, levels)
            assert middle_ids == [4]

            all_frames = VideoFrameSampleNode.execute(
                video=signal, num_frames=9999, strategy="uniform", seed=99
            ).args[0]
            all_ids = decoded_ids(all_frames.get_components().images, levels)
            assert all_ids == list(range(8))

            seed = 11
            modulus = 2**32 - 1
            expected_random = sorted(
                np.random.RandomState(seed).choice(8, size=4, replace=False).tolist()
            )
            np.random.seed(1234)
            expected_global_next = int(np.random.RandomState(1234).randint(0, 2**31))
            random_video = VideoFrameSampleNode.execute(
                video=signal, num_frames=4, strategy="random", seed=seed
            ).args[0]
            random_ids = decoded_ids(random_video.get_components().images, levels)
            global_next = int(np.random.randint(0, 2**31))
            random_wrapped = VideoFrameSampleNode.execute(
                video=signal,
                num_frames=4,
                strategy="random",
                seed=modulus + seed,
            ).args[0]
            random_wrapped_ids = decoded_ids(
                random_wrapped.get_components().images, levels
            )
            assert random_ids == expected_random
            assert random_wrapped_ids == expected_random
            assert global_next == expected_global_next
            assert random_video.get_components().audio is None

            unknown_strategy_error = None
            try:
                VideoFrameSampleNode.execute(
                    video=signal, num_frames=2, strategy="unknown", seed=0
                )
            except ValueError as exc:
                unknown_strategy_error = str(exc)
            assert unknown_strategy_error == "Unknown strategy: unknown"

            crop = VideoTemporalCropNode.execute(
                video=signal, start_frame=2, length=3
            ).args[0]
            crop_past_end = VideoTemporalCropNode.execute(
                video=signal, start_frame=99999, length=99999
            ).args[0]
            crop_truncated = VideoTemporalCropNode.execute(
                video=signal, start_frame=6, length=99999
            ).args[0]
            assert crop.get_active_trim_window() == (0.5, 0.75)
            assert crop_past_end.get_active_trim_window() == (1.75, 0.25)
            assert crop_truncated.get_active_trim_window() == (1.5, 0.5)
            assert crop.get_stream_source() == signal.get_stream_source()

            cropped_head = VideoFrameSampleNode.execute(
                video=crop, num_frames=2, strategy="head", seed=0
            ).args[0]
            assert cropped_head.get_active_trim_window() == (0.5, 0.5)

            cropped_four = VideoTemporalCropNode.execute(
                video=signal, start_frame=2, length=4
            ).args[0]
            cropped_middle = VideoFrameSampleNode.execute(
                video=cropped_four, num_frames=1, strategy="uniform", seed=0
            ).args[0]
            cropped_middle_ids = decoded_ids(
                cropped_middle.get_components().images, levels
            )
            # The pinned helper reopens the underlying stream and indexes it from
            # zero, so it does not add VideoFromFile's active trim offset.
            assert cropped_middle_ids == [2]

            print(
                json.dumps(
                    {
                        "loadVideo": {
                            "caseInsensitiveExtensions": True,
                            "emptyRejected": True,
                            "nestedIgnored": True,
                            "sortedSources": relative_sources(plain_videos, plain),
                            "traversalRejected": True,
                        },
                        "loadVideoText": {
                            "captions": paired_texts,
                            "missingCaptionEmpty": True,
                            "nestedDepth": 1,
                            "repeatPrefixApplied": True,
                            "sources": paired_sources,
                            "whitespaceStripped": True,
                            "zeroRepeatDropsFolder": True,
                        },
                        "sample": {
                            "allRequestClamped": all_ids,
                            "globalRngUntouched": global_next == expected_global_next,
                            "headTrim": list(head.get_active_trim_window()),
                            "middleId": middle_ids[0],
                            "randomIdsSeed11": random_ids,
                            "randomModuloCollision": random_wrapped_ids == random_ids,
                            "selectedAudioAbsent": uniform_components.audio is None,
                            "tailTrim": list(tail.get_active_trim_window()),
                            "trimmedInputOffsetIgnored": cropped_middle_ids == [2],
                            "uniformIds": uniform_ids,
                            "unknownStrategyRejected": True,
                        },
                        "temporalCrop": {
                            "chainedLazyHeadAddsOffset": list(
                                cropped_head.get_active_trim_window()
                            ),
                            "pastEndClampedToLast": list(
                                crop_past_end.get_active_trim_window()
                            ),
                            "requested": list(crop.get_active_trim_window()),
                            "tailLengthTruncated": list(
                                crop_truncated.get_active_trim_window()
                            ),
                            "fullyLazy": True,
                        },
                    },
                    sort_keys=True,
                )
            )
        finally:
            folder_paths.get_input_directory = original_input_directory


if __name__ == "__main__":
    main()
