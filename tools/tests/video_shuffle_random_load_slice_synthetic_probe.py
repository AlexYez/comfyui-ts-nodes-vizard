from __future__ import annotations

import hashlib
import json
import os
import sys
import tempfile
from pathlib import Path


def make_video(path: Path, frame_count: int = 8, fps: int = 4) -> None:
    import av
    import numpy as np

    with av.open(str(path), mode="w") as container:
        stream = container.add_stream("ffv1", rate=fps)
        stream.width = 16
        stream.height = 16
        stream.pix_fmt = "yuv444p"
        for index in range(frame_count):
            pixels = np.full((16, 16, 3), 16 + index * 24, dtype=np.uint8)
            frame = av.VideoFrame.from_ndarray(pixels, format="rgb24")
            for packet in stream.encode(frame):
                container.mux(packet)
        for packet in stream.encode(None):
            container.mux(packet)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit(
            "usage: video_shuffle_random_load_slice_synthetic_probe.py "
            "<pinned-comfyui-source>"
        )

    source = Path(sys.argv[1]).resolve()
    sys.path.insert(0, str(source))

    import folder_paths
    import numpy as np
    from comfy_extras.nodes_dataset import (
        ShuffleVideoDatasetNode,
        VideoRandomTemporalCropNode,
    )
    from comfy_extras.nodes_video import LoadVideo, VideoSlice

    targets = (
        ShuffleVideoDatasetNode,
        VideoRandomTemporalCropNode,
        LoadVideo,
        VideoSlice,
    )
    schemas = {}
    for cls in targets:
        cls.VALIDATE_CLASS()
        info = cls.GET_NODE_INFO_V1()
        schemas[info["name"]] = {
            "apiNode": info.get("api_node", False),
            "deprecated": info.get("deprecated", False),
            "devOnly": info.get("dev_only", False),
            "experimental": info.get("experimental", False),
            "inputIsList": getattr(cls, "INPUT_IS_LIST", False),
            "outputIsList": getattr(cls, "OUTPUT_IS_LIST", []),
            "outputNode": info.get("output_node", False),
        }

    videos = [object() for _ in range(5)]
    shuffled = ShuffleVideoDatasetNode.execute(videos, [7]).args[0]
    shuffled_indices = [videos.index(item) for item in shuffled]
    assert shuffled_indices == [0, 3, 2, 1, 4]
    assert all(shuffled[index] is videos[value] for index, value in enumerate(shuffled_indices))

    np.random.seed(1234)
    ShuffleVideoDatasetNode.execute(videos, [7])
    global_after_shuffle = int(np.random.randint(0, 2**31))
    expected_rng = np.random.RandomState(7)
    expected_rng.permutation(len(videos))
    expected_global_after_shuffle = int(expected_rng.randint(0, 2**31))
    assert global_after_shuffle == expected_global_after_shuffle

    shuffle_zero = ShuffleVideoDatasetNode.execute(videos, 0).args[0]
    shuffle_max = ShuffleVideoDatasetNode.execute(videos, 2**64 - 1).args[0]
    assert [videos.index(item) for item in shuffle_zero] == [2, 0, 1, 3, 4]
    assert [videos.index(item) for item in shuffle_max] == [2, 0, 1, 3, 4]
    assert ShuffleVideoDatasetNode.execute([], [99]).args[0] == []
    singleton = object()
    assert ShuffleVideoDatasetNode.execute([singleton], [99]).args[0] == [singleton]

    original_input = folder_paths.get_input_directory()
    with tempfile.TemporaryDirectory(prefix="nodes-wizard-video-io-") as temp_name:
        temp_root = Path(temp_name)
        input_root = temp_root / "input"
        outside_root = temp_root / "outside"
        input_root.mkdir()
        outside_root.mkdir()
        folder_paths.set_input_directory(str(input_root))
        try:
            signal_path = input_root / "signal.avi"
            make_video(signal_path)
            (input_root / "notes.txt").write_text("ignored", encoding="utf-8")
            nested = input_root / "nested"
            nested.mkdir()
            (nested / "hidden.mp4").write_bytes(b"not listed")

            fingerprint_path = input_root / "fingerprint.mp4"
            fingerprint_path.write_bytes(b"first payload")

            load_info = LoadVideo.GET_NODE_INFO_V1()
            file_descriptor = load_info["input"]["required"]["file"]
            assert file_descriptor[1]["options"] == ["fingerprint.mp4", "signal.avi"]
            assert file_descriptor[1]["video_upload"] is True

            assert LoadVideo.validate_inputs("signal.avi") is True
            assert LoadVideo.validate_inputs("nested") is True
            missing_error = LoadVideo.validate_inputs("missing.mp4")
            traversal_error = LoadVideo.validate_inputs("../outside/video.mp4")
            assert missing_error == "Invalid video file: missing.mp4"
            assert traversal_error == "Invalid video file: ../outside/video.mp4"

            traversal_execute_error = None
            try:
                LoadVideo.execute("../outside/video.mp4")
            except ValueError as exc:
                traversal_execute_error = str(exc)
            assert traversal_execute_error == "Invalid file path: '../outside/video.mp4'"

            loaded = LoadVideo.execute("signal.avi [input]").args[0]
            assert Path(loaded.get_stream_source()).resolve() == signal_path.resolve()
            assert loaded.get_frame_count() == 8
            assert float(loaded.get_frame_rate()) == 4.0

            original_stat = fingerprint_path.stat()
            fingerprint_before = LoadVideo.fingerprint_inputs("fingerprint.mp4")
            hash_before = sha256(fingerprint_path)
            fingerprint_path.write_bytes(b"second, different payload")
            os.utime(
                fingerprint_path,
                ns=(original_stat.st_atime_ns, original_stat.st_mtime_ns),
            )
            fingerprint_after = LoadVideo.fingerprint_inputs("fingerprint.mp4")
            hash_after = sha256(fingerprint_path)
            assert hash_before != hash_after
            assert fingerprint_before == fingerprint_after

            np.random.seed(4321)
            expected_global_after_crop = int(np.random.RandomState(4321).randint(0, 2**31))
            random_crop = VideoRandomTemporalCropNode.execute(
                loaded, length=3, seed=11
            ).args[0]
            global_after_crop = int(np.random.randint(0, 2**31))
            assert random_crop.get_active_trim_window() == (0.25, 0.75)
            assert random_crop.get_stream_source() == loaded.get_stream_source()
            assert global_after_crop == expected_global_after_crop

            endpoint_crop = VideoRandomTemporalCropNode.execute(
                loaded, length=3, seed=1
            ).args[0]
            assert endpoint_crop.get_active_trim_window() == (1.25, 0.75)

            random_zero = VideoRandomTemporalCropNode.execute(
                loaded, length=3, seed=0
            ).args[0]
            random_wrapped = VideoRandomTemporalCropNode.execute(
                loaded, length=3, seed=2**64 - 1
            ).args[0]
            assert random_zero.get_active_trim_window() == (1.0, 0.75)
            assert (
                random_zero.get_active_trim_window()
                == random_wrapped.get_active_trim_window()
            )

            clamped_random = VideoRandomTemporalCropNode.execute(
                loaded, length=99999, seed=11
            ).args[0]
            assert clamped_random.get_active_trim_window() == (0.0, 2.0)

            five_second_official_pattern = VideoSlice.execute(
                loaded, start_time=0.0, duration=5.0, strict_duration=False
            ).args[0]
            assert five_second_official_pattern.get_active_trim_window() == (0.0, 5.0)
            assert five_second_official_pattern.get_duration() == 2.0
            assert five_second_official_pattern.get_stream_source() == loaded.get_stream_source()

            strict_error = None
            try:
                VideoSlice.execute(
                    loaded, start_time=0.0, duration=5.0, strict_duration=True
                )
            except ValueError as exc:
                strict_error = str(exc)
            assert strict_error is not None
            assert strict_error.startswith("Failed to slice video:\nSource duration: 2.0")

            unlimited = VideoSlice.execute(
                loaded, start_time=0.5, duration=0.0, strict_duration=False
            ).args[0]
            assert unlimited.get_active_trim_window() == (0.5, 0.0)
            assert unlimited.get_duration() == 1.5

            negative_start = VideoSlice.execute(
                loaded, start_time=-0.5, duration=0.0, strict_duration=False
            ).args[0]
            assert negative_start.get_active_trim_window() == (1.5, 0.0)
            assert negative_start.get_duration() == 0.5

            clipped = VideoSlice.execute(
                loaded, start_time=1.5, duration=1.0, strict_duration=False
            ).args[0]
            assert clipped.get_active_trim_window() == (1.5, 1.0)
            assert clipped.get_duration() == 0.5

            parent_trim = VideoSlice.execute(
                loaded, start_time=0.5, duration=0.5, strict_duration=False
            ).args[0]
            child_unlimited = VideoSlice.execute(
                parent_trim, start_time=0.0, duration=0.0, strict_duration=False
            ).args[0]
            assert parent_trim.get_active_trim_window() == (0.5, 0.5)
            assert parent_trim.get_duration() == 0.5
            assert child_unlimited.get_active_trim_window() == (0.5, 0.0)
            assert child_unlimited.get_duration() == 1.5

            print(
                json.dumps(
                    {
                        "load": {
                            "directoryAcceptedByValidation": LoadVideo.validate_inputs(
                                "nested"
                            )
                            is True,
                            "fingerprintIsMtimeOnly": fingerprint_before
                            == fingerprint_after
                            and hash_before != hash_after,
                            "options": file_descriptor[1]["options"],
                            "sourceIsExactInputPath": Path(
                                loaded.get_stream_source()
                            ).resolve()
                            == signal_path.resolve(),
                            "traversalExecuteRejected": traversal_execute_error
                            is not None,
                            "traversalValidateRejected": traversal_error.startswith(
                                "Invalid video file"
                            ),
                            "uploadEnabled": file_descriptor[1]["video_upload"],
                        },
                        "randomCrop": {
                            "clampedToFullWindow": list(
                                clamped_random.get_active_trim_window()
                            ),
                            "endpointStartIncluded": list(
                                endpoint_crop.get_active_trim_window()
                            ),
                            "globalRngUntouched": global_after_crop
                            == expected_global_after_crop,
                            "seed11Window": list(
                                random_crop.get_active_trim_window()
                            ),
                            "seedModuloCollision": random_zero.get_active_trim_window()
                            == random_wrapped.get_active_trim_window(),
                        },
                        "schemas": schemas,
                        "shuffle": {
                            "empty": ShuffleVideoDatasetNode.execute([], [99]).args[0],
                            "globalRngReset": global_after_shuffle
                            == expected_global_after_shuffle,
                            "orderSeed7": shuffled_indices,
                            "referencesPreserved": all(
                                shuffled[index] is videos[value]
                                for index, value in enumerate(shuffled_indices)
                            ),
                            "seedModuloCollision": [videos.index(item) for item in shuffle_zero]
                            == [videos.index(item) for item in shuffle_max],
                            "singletonPreserved": ShuffleVideoDatasetNode.execute(
                                [singleton], [99]
                            ).args[0][0]
                            is singleton,
                        },
                        "slice": {
                            "chainedUnlimitedExtendsParent": {
                                "childDuration": child_unlimited.get_duration(),
                                "childWindow": list(
                                    child_unlimited.get_active_trim_window()
                                ),
                                "parentDuration": parent_trim.get_duration(),
                                "parentWindow": list(
                                    parent_trim.get_active_trim_window()
                                ),
                            },
                            "durationZeroUnlimited": {
                                "duration": unlimited.get_duration(),
                                "window": list(unlimited.get_active_trim_window()),
                            },
                            "negativeStartFromEnd": {
                                "duration": negative_start.get_duration(),
                                "window": list(
                                    negative_start.get_active_trim_window()
                                ),
                            },
                            "nonStrictClipped": {
                                "duration": clipped.get_duration(),
                                "window": list(clipped.get_active_trim_window()),
                            },
                            "officialFiveSecondPattern": {
                                "actualDuration": five_second_official_pattern.get_duration(),
                                "requestedWindow": list(
                                    five_second_official_pattern.get_active_trim_window()
                                ),
                            },
                            "strictLongRequestRejected": strict_error is not None,
                        },
                    },
                    ensure_ascii=False,
                    sort_keys=True,
                )
            )
        finally:
            folder_paths.set_input_directory(original_input)


if __name__ == "__main__":
    main()
