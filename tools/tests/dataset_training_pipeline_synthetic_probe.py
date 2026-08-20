from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path


def latent(sample_id: int, height: int = 2, width: int = 3):
    import torch

    return {
        "samples": torch.full(
            (1, 1, height, width), float(sample_id), dtype=torch.float32
        )
    }


def conditioning(sample_id: int):
    import torch

    return [torch.tensor([float(sample_id)], dtype=torch.float32)]


def latent_ids(values):
    return [int(item["samples"].reshape(-1)[0].item()) for item in values]


class DummyVAE:
    def __init__(self) -> None:
        self.input_shapes: list[list[int]] = []

    def encode(self, image):
        self.input_shapes.append(list(image.shape))
        return image.permute(0, 3, 1, 2)[:, :2].contiguous()


class DummyCLIP:
    def __init__(self) -> None:
        self.tokenized: list[str] = []

    def tokenize(self, text: str):
        self.tokenized.append(text)
        return {"text": text}

    def encode_from_tokens_scheduled(self, tokens):
        return [tokens["text"]]


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit(
            "usage: dataset_training_pipeline_synthetic_probe.py "
            "<pinned-comfyui-source>"
        )

    source = Path(sys.argv[1]).resolve()
    sys.path.insert(0, str(source))

    import folder_paths
    import torch

    from comfy_extras.nodes_dataset import (
        LoadTrainingDataset,
        MakeTrainingDataset,
        ResolutionBucket,
        SaveTrainingDataset,
        get_dataset_dir,
        get_dataset_save_dir,
        list_dataset_folders,
    )

    targets = (
        MakeTrainingDataset,
        SaveTrainingDataset,
        LoadTrainingDataset,
        ResolutionBucket,
    )
    schemas = {}
    expected_input_lists = {
        "MakeTrainingDataset": True,
        "SaveTrainingDataset": True,
        "LoadTrainingDataset": False,
        "ResolutionBucket": True,
    }
    expected_output_lists = {
        "MakeTrainingDataset": [True, True],
        "SaveTrainingDataset": [],
        "LoadTrainingDataset": [True, True],
        "ResolutionBucket": [True, True],
    }
    for cls in targets:
        cls.VALIDATE_CLASS()
        info = cls.GET_NODE_INFO_V1()
        schemas[info["name"]] = {
            "apiNode": info.get("api_node", False),
            "deprecated": info.get("deprecated", False),
            "devOnly": info.get("dev_only", False),
            "experimental": info.get("experimental", False),
            "inputIsList": cls.INPUT_IS_LIST,
            "outputIsList": cls.OUTPUT_IS_LIST,
            "outputNode": info.get("output_node", False),
        }
        assert cls.INPUT_IS_LIST is expected_input_lists[info["name"]]
        assert cls.OUTPUT_IS_LIST == expected_output_lists[info["name"]]
        assert info.get("experimental", False) is True
        assert info.get("deprecated", False) is False
        assert info.get("dev_only", False) is False
        assert info.get("api_node", False) is False

    vae = DummyVAE()
    clip = DummyCLIP()
    images = [
        torch.arange(1 * 4 * 5 * 4, dtype=torch.float32).reshape(1, 4, 5, 4),
        torch.zeros((1, 6, 7, 3), dtype=torch.float32),
        torch.ones((1, 3, 2, 3), dtype=torch.float32),
    ]
    made = MakeTrainingDataset.execute(images, [vae], [clip], ["caption"])
    made_latents, made_conditioning = made.args
    assert len(made_latents) == 3
    assert [list(item["samples"].shape) for item in made_latents] == [
        [1, 2, 4, 5],
        [1, 2, 6, 7],
        [1, 2, 3, 2],
    ]
    assert vae.input_shapes[0] == [1, 4, 5, 3]
    assert made_conditioning == [["caption"], ["caption"], ["caption"]]
    assert clip.tokenized == ["caption", "caption", "caption"]

    empty_caption_clip = DummyCLIP()
    empty_captions = MakeTrainingDataset.execute(
        images[:2], [DummyVAE()], [empty_caption_clip], []
    ).args[1]
    assert empty_captions == [[""], [""]]
    assert empty_caption_clip.tokenized == ["", ""]

    batched_image = torch.zeros((2, 4, 5, 3), dtype=torch.float32)
    batched_output = MakeTrainingDataset.execute(
        [batched_image], [DummyVAE()], [DummyCLIP()], ["one outer item"]
    ).args
    assert len(batched_output[0]) == 1
    assert list(batched_output[0][0]["samples"].shape) == [2, 2, 4, 5]
    assert len(batched_output[1]) == 1

    text_mismatch_error = None
    try:
        MakeTrainingDataset.execute(
            images[:2], [DummyVAE()], [DummyCLIP()], ["a", "b", "c"]
        )
    except ValueError as exc:
        text_mismatch_error = str(exc)
    assert text_mismatch_error is not None
    assert "does not match number of images" in text_mismatch_error

    empty_images_error = None
    try:
        MakeTrainingDataset.execute([], [DummyVAE()], [DummyCLIP()], None)
    except ValueError as exc:
        empty_images_error = str(exc)
    assert empty_images_error is not None
    assert "length 0, 1, or 0" in empty_images_error

    bucket_latents = [
        {
            "samples": torch.stack(
                [
                    torch.full((1, 4, 6), 0.0),
                    torch.full((1, 4, 6), 1.0),
                ],
                dim=0,
            ),
            "noise_mask": torch.ones((2, 4, 6)),
        },
        {"samples": torch.full((1, 1, 8, 6), 2.0)},
        {"samples": torch.full((1, 1, 4, 6), 3.0)},
        {"samples": torch.full((1, 1, 5, 6), 4.0)},
    ]
    bucket_conditions = [
        ["condition-0", "condition-1"],
        ["condition-2"],
        ["condition-3"],
        ["condition-4"],
    ]
    bucketed_latents, bucketed_conditions = ResolutionBucket.execute(
        bucket_latents, bucket_conditions
    ).args
    assert [list(item["samples"].shape) for item in bucketed_latents] == [
        [3, 1, 4, 6],
        [1, 1, 8, 6],
        [1, 1, 5, 6],
    ]
    assert [latent_ids([item]) for item in bucketed_latents] == [[0], [2], [4]]
    assert [
        [int(sample.reshape(-1)[0].item()) for sample in item["samples"]]
        for item in bucketed_latents
    ] == [[0, 1, 3], [2], [4]]
    assert bucketed_conditions == [
        ["condition-0", "condition-1", "condition-3"],
        ["condition-2"],
        ["condition-4"],
    ]
    assert all(set(item) == {"samples"} for item in bucketed_latents)

    empty_bucket = ResolutionBucket.execute([], []).args
    assert empty_bucket == ([], [])

    outer_bucket_mismatch = None
    try:
        ResolutionBucket.execute([latent(0)], [])
    except ValueError as exc:
        outer_bucket_mismatch = type(exc).__name__
    assert outer_bucket_mismatch == "ValueError"

    short_inner_condition = None
    try:
        ResolutionBucket.execute([bucket_latents[0]], [["only-one"]])
    except IndexError as exc:
        short_inner_condition = type(exc).__name__
    assert short_inner_condition == "IndexError"

    long_inner = ResolutionBucket.execute(
        [latent(7, 4, 6)], [["kept", "ignored"]]
    ).args[1]
    assert long_inner == [["kept"]]

    incompatible_same_resolution = None
    try:
        ResolutionBucket.execute(
            [
                {"samples": torch.zeros((1, 1, 4, 6))},
                {"samples": torch.zeros((1, 2, 4, 6))},
            ],
            [["one-channel"], ["two-channel"]],
        )
    except RuntimeError as exc:
        incompatible_same_resolution = type(exc).__name__
    assert incompatible_same_resolution == "RuntimeError"

    previous_datasets = folder_paths.folder_names_and_paths["datasets"]
    with tempfile.TemporaryDirectory(
        prefix="nodes-wizard-training-dataset-"
    ) as temp_name:
        temp_root = Path(temp_name)
        dataset_root = temp_root / "datasets"
        outside_root = temp_root / "outside"
        dataset_root.mkdir()
        outside_root.mkdir()
        folder_paths.folder_names_and_paths["datasets"] = (
            [str(dataset_root)],
            set(),
        )

        try:
            save_latents = [latent(index) for index in range(5)]
            save_conditioning = [conditioning(index) for index in range(5)]
            save_result = SaveTrainingDataset.execute(
                save_latents,
                save_conditioning,
                ["project/run1"],
                [2],
            )
            assert save_result.args == ()

            saved_dir = dataset_root / "project" / "run1"
            shard_names = sorted(path.name for path in saved_dir.glob("shard_*.pkl"))
            assert shard_names == [
                "shard_0000.pkl",
                "shard_0001.pkl",
                "shard_0002.pkl",
            ]
            metadata = json.loads((saved_dir / "metadata.json").read_text(encoding="utf-8"))
            assert metadata == {"num_samples": 5, "num_shards": 3, "shard_size": 2}
            assert "project/run1" in list_dataset_folders()
            assert get_dataset_save_dir("project/run1") == str(saved_dir)
            assert get_dataset_dir("project/run1") == str(saved_dir)

            loaded = LoadTrainingDataset.execute("project/run1").args
            assert latent_ids(loaded[0]) == [0, 1, 2, 3, 4]
            assert [int(item[0].item()) for item in loaded[1]] == [0, 1, 2, 3, 4]

            (saved_dir / "metadata.json").write_text(
                json.dumps({"num_samples": 999, "num_shards": 999, "shard_size": 999}),
                encoding="utf-8",
            )
            loaded_ignoring_metadata = LoadTrainingDataset.execute("project/run1").args
            assert latent_ids(loaded_ignoring_metadata[0]) == [0, 1, 2, 3, 4]

            SaveTrainingDataset.execute(
                [latent(99)],
                [conditioning(99)],
                ["project/run1"],
                [2],
            )
            stale_shards = sorted(path.name for path in saved_dir.glob("shard_*.pkl"))
            assert stale_shards == shard_names
            overwrite_metadata = json.loads(
                (saved_dir / "metadata.json").read_text(encoding="utf-8")
            )
            assert overwrite_metadata == {
                "num_samples": 1,
                "num_shards": 1,
                "shard_size": 2,
            }
            loaded_with_stale_shards = LoadTrainingDataset.execute("project/run1").args
            assert latent_ids(loaded_with_stale_shards[0]) == [99, 2, 3, 4]

            mismatch_dir = dataset_root / "mismatch-not-created"
            save_length_mismatch = None
            try:
                SaveTrainingDataset.execute(
                    [latent(0)], [], ["mismatch-not-created"], [2]
                )
            except ValueError as exc:
                save_length_mismatch = type(exc).__name__
            assert save_length_mismatch == "ValueError"
            assert not mismatch_dir.exists()

            empty_result = SaveTrainingDataset.execute(
                [], [], ["empty-set"], [2]
            )
            assert empty_result.args == ()
            empty_dir = dataset_root / "empty-set"
            empty_metadata = json.loads(
                (empty_dir / "metadata.json").read_text(encoding="utf-8")
            )
            assert empty_metadata == {
                "num_samples": 0,
                "num_shards": 0,
                "shard_size": 2,
            }
            assert list(empty_dir.glob("shard_*.pkl")) == []
            assert "empty-set" in list_dataset_folders()
            empty_load_error = None
            try:
                LoadTrainingDataset.execute("empty-set")
            except ValueError as exc:
                empty_load_error = str(exc)
            assert empty_load_error is not None
            assert "No shard files found" in empty_load_error

            manual_dir = dataset_root / "manual-mismatch"
            manual_dir.mkdir()
            (manual_dir / "metadata.json").write_text("{}", encoding="utf-8")
            torch.save(
                {
                    "latents": [latent(10), latent(11)],
                    "conditioning": [conditioning(10)],
                },
                manual_dir / "shard_0000.pkl",
            )
            manual_loaded = LoadTrainingDataset.execute("manual-mismatch").args
            assert len(manual_loaded[0]) == 2
            assert len(manual_loaded[1]) == 1

            traversal_rejections = {}
            for label, folder_name in (
                ("parent", "../outside"),
                ("absolute", str(outside_root)),
                ("root", ""),
            ):
                try:
                    SaveTrainingDataset.execute(
                        [latent(1)], [conditioning(1)], [folder_name], [1]
                    )
                except ValueError:
                    traversal_rejections[label] = True
                else:
                    traversal_rejections[label] = False
            assert traversal_rejections == {
                "parent": True,
                "absolute": True,
                "root": True,
            }

            load_traversal_error = None
            try:
                LoadTrainingDataset.execute("../outside")
            except ValueError as exc:
                load_traversal_error = type(exc).__name__
            assert load_traversal_error == "ValueError"

            print(
                json.dumps(
                    {
                        "bucket": {
                            "bucketConditions": bucketed_conditions,
                            "bucketShapes": [
                                list(item["samples"].shape)
                                for item in bucketed_latents
                            ],
                            "emptyOutputs": [len(empty_bucket[0]), len(empty_bucket[1])],
                            "extraLatentFieldsDropped": all(
                                set(item) == {"samples"}
                                for item in bucketed_latents
                            ),
                            "firstSeenBucketOrder": True,
                            "innerConditionExtraIgnored": long_inner == [["kept"]],
                            "innerConditionShortRejected": short_inner_condition
                            == "IndexError",
                            "noResolutionRounding": True,
                            "sameResolutionIncompatibleShapeRejected": incompatible_same_resolution
                            == "RuntimeError",
                        },
                        "load": {
                            "emptyMetadataDatasetRejected": empty_load_error
                            is not None,
                            "ignoresMetadataCounts": latent_ids(
                                loaded_ignoring_metadata[0]
                            )
                            == [0, 1, 2, 3, 4],
                            "mismatchedShardListsAccepted": [
                                len(manual_loaded[0]),
                                len(manual_loaded[1]),
                            ],
                            "sortedInitialIds": [0, 1, 2, 3, 4],
                            "staleOverwriteIds": latent_ids(
                                loaded_with_stale_shards[0]
                            ),
                        },
                        "make": {
                            "batchedOuterItemCounts": [
                                len(batched_output[0]),
                                len(batched_output[1]),
                            ],
                            "emptyCaptionsRepeated": empty_captions,
                            "emptyImagesRejected": empty_images_error is not None,
                            "latentShapes": [
                                list(item["samples"].shape)
                                for item in made_latents
                            ],
                            "singleCaptionRepeated": made_conditioning,
                            "textMismatchRejected": text_mismatch_error is not None,
                            "vaeReceivesFirstThreeChannels": vae.input_shapes[0]
                            == [1, 4, 5, 3],
                        },
                        "save": {
                            "ceilingShardMetadata": metadata,
                            "emptyMetadata": empty_metadata,
                            "nestedFolderListed": "project/run1"
                            in list_dataset_folders(),
                            "staleShardFilesRemain": stale_shards,
                            "traversalRejected": traversal_rejections,
                        },
                        "schemas": schemas,
                    },
                    ensure_ascii=False,
                    sort_keys=True,
                )
            )
        finally:
            folder_paths.folder_names_and_paths["datasets"] = previous_datasets


if __name__ == "__main__":
    main()
