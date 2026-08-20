from __future__ import annotations

import json
import sys
from pathlib import Path


def image_ids(images):
    return [int(image.reshape(-1)[0].item()) for image in images]


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit(
            "usage: dataset_shuffle_merge_synthetic_probe.py <pinned-comfyui-source>"
        )

    source = Path(sys.argv[1]).resolve()
    sys.path.insert(0, str(source))

    import numpy as np
    import torch

    from comfy_extras.nodes_dataset import (
        MergeImageListsNode,
        ShuffleDatasetNode,
        ShuffleImageTextDatasetNode,
        ShuffleVideoTextDatasetNode,
    )

    modulus = 2**32 - 1
    batch_a = torch.arange(0, 3, dtype=torch.float32).reshape(3, 1, 1, 1)
    batch_b = torch.arange(3, 8, dtype=torch.float32).reshape(5, 1, 1, 1)

    merged = MergeImageListsNode.execute(images=[batch_a, batch_b]).args[0]
    assert image_ids(merged) == list(range(8))
    assert all(tuple(image.shape) == (1, 1, 1, 1) for image in merged)
    assert MergeImageListsNode.execute(images=[]).args[0] == []

    shuffled_seed_7 = ShuffleDatasetNode.execute(
        images=[batch_a, batch_b], seed=[7]
    ).args[0]
    expected_seed_7 = np.random.RandomState(7).permutation(8).tolist()
    assert image_ids(shuffled_seed_7) == expected_seed_7

    shuffled_seed_7_repeat = ShuffleDatasetNode.execute(
        images=[batch_a, batch_b], seed=[7]
    ).args[0]
    assert image_ids(shuffled_seed_7_repeat) == expected_seed_7
    shuffled_seed_0 = image_ids(
        ShuffleDatasetNode.execute(images=[batch_a, batch_b], seed=[0]).args[0]
    )
    shuffled_seed_0_repeat = image_ids(
        ShuffleDatasetNode.execute(images=[batch_a, batch_b], seed=[0]).args[0]
    )
    assert shuffled_seed_0_repeat == shuffled_seed_0
    shuffled_seed_8 = ShuffleDatasetNode.execute(
        images=[batch_a, batch_b], seed=[8]
    ).args[0]
    assert image_ids(shuffled_seed_8) != expected_seed_7
    wrapped_shuffle = ShuffleDatasetNode.execute(
        images=[batch_a, batch_b], seed=[modulus + 7]
    ).args[0]
    assert image_ids(wrapped_shuffle) == expected_seed_7
    assert ShuffleDatasetNode.execute(images=[], seed=[7]).args[0] == []

    ShuffleDatasetNode.execute(images=[batch_a, batch_b], seed=[19])
    global_rng_next = int(np.random.randint(0, 2**31))
    independent_rng = np.random.RandomState(19)
    independent_rng.permutation(8)
    expected_global_rng_next = int(independent_rng.randint(0, 2**31))
    assert global_rng_next == expected_global_rng_next

    image_items = [
        torch.full((1, 1, 1, 1), float(index), dtype=torch.float32)
        for index in range(8)
    ]
    captions = [f"caption-{index}" for index in range(8)]
    image_text = ShuffleImageTextDatasetNode.execute(
        images=image_items, texts=captions, seed=[23]
    ).args
    image_text_ids = image_ids(image_text[0])
    expected_image_text = np.random.RandomState(23).permutation(8).tolist()
    assert image_text_ids == expected_image_text
    assert image_text[1] == [f"caption-{index}" for index in image_text_ids]
    image_text_repeat = ShuffleImageTextDatasetNode.execute(
        images=image_items, texts=captions, seed=[23]
    ).args
    assert image_ids(image_text_repeat[0]) == image_text_ids
    assert image_text_repeat[1] == image_text[1]
    image_text_wrapped = ShuffleImageTextDatasetNode.execute(
        images=image_items, texts=captions, seed=[modulus + 23]
    ).args
    assert image_ids(image_text_wrapped[0]) == image_text_ids
    assert image_text_wrapped[1] == image_text[1]

    long_texts = captions + ["unused-caption"]
    truncated_long_texts = ShuffleImageTextDatasetNode.execute(
        images=image_items, texts=long_texts, seed=[23]
    ).args[1]
    assert len(truncated_long_texts) == len(image_items)
    assert "unused-caption" not in truncated_long_texts
    image_text_short_error = None
    try:
        ShuffleImageTextDatasetNode.execute(
            images=image_items, texts=[], seed=[23]
        )
    except IndexError as exc:
        image_text_short_error = type(exc).__name__
    assert image_text_short_error == "IndexError"
    image_text_scalar_seed_error = None
    try:
        ShuffleImageTextDatasetNode.execute(
            images=image_items, texts=captions, seed=23
        )
    except TypeError as exc:
        image_text_scalar_seed_error = type(exc).__name__
    assert image_text_scalar_seed_error == "TypeError"
    outer_batch_pair = ShuffleImageTextDatasetNode.execute(
        images=[batch_a], texts=["whole-batch"], seed=[23]
    ).args
    assert len(outer_batch_pair[0]) == 1
    assert tuple(outer_batch_pair[0][0].shape) == (3, 1, 1, 1)
    assert outer_batch_pair[1] == ["whole-batch"]

    videos = [f"video-{index}" for index in range(8)]
    video_text = ShuffleVideoTextDatasetNode.execute(
        videos=videos, texts=captions, seed=[29]
    ).args
    expected_video_text = np.random.RandomState(29).permutation(8).tolist()
    assert video_text[0] == [f"video-{index}" for index in expected_video_text]
    assert video_text[1] == [f"caption-{index}" for index in expected_video_text]
    video_text_scalar = ShuffleVideoTextDatasetNode.execute(
        videos=videos, texts=captions, seed=29
    ).args
    assert video_text_scalar == video_text
    video_text_wrapped = ShuffleVideoTextDatasetNode.execute(
        videos=videos, texts=captions, seed=[modulus + 29]
    ).args
    assert video_text_wrapped == video_text

    video_long_texts = captions + ["unused-caption"]
    truncated_video_texts = ShuffleVideoTextDatasetNode.execute(
        videos=videos, texts=video_long_texts, seed=[29]
    ).args[1]
    assert len(truncated_video_texts) == len(videos)
    assert "unused-caption" not in truncated_video_texts
    video_text_short_error = None
    try:
        ShuffleVideoTextDatasetNode.execute(videos=videos, texts=[], seed=[29])
    except IndexError as exc:
        video_text_short_error = type(exc).__name__
    assert video_text_short_error == "IndexError"
    assert ShuffleVideoTextDatasetNode.execute(
        videos=[], texts=[], seed=[29]
    ).args == ([], [])

    print(
        json.dumps(
            {
                "merge": {
                    "emptyCount": 0,
                    "flattenedCount": len(merged),
                    "order": image_ids(merged),
                    "singletonBatchShapes": [list(image.shape) for image in merged],
                },
                "shuffleImages": {
                    "differentSeedChangesOrder": image_ids(shuffled_seed_8)
                    != expected_seed_7,
                    "emptyCount": 0,
                    "globalRngReseeded": global_rng_next == expected_global_rng_next,
                    "orderSeed7": expected_seed_7,
                    "repeatDeterministic": image_ids(shuffled_seed_7_repeat)
                    == expected_seed_7,
                    "seedModuloCollision": image_ids(wrapped_shuffle)
                    == expected_seed_7,
                    "zeroSeedDeterministic": shuffled_seed_0_repeat
                    == shuffled_seed_0,
                },
                "shuffleImageText": {
                    "alignmentPreserved": image_text[1]
                    == [f"caption-{index}" for index in image_text_ids],
                    "longTextsTruncated": "unused-caption" not in truncated_long_texts,
                    "orderSeed23": image_text_ids,
                    "outerBatchNotFlattened": tuple(outer_batch_pair[0][0].shape)
                    == (3, 1, 1, 1),
                    "repeatDeterministic": image_text_repeat == image_text,
                    "scalarSeedRejected": image_text_scalar_seed_error == "TypeError",
                    "seedModuloCollision": image_text_wrapped == image_text,
                    "shortTextsRejected": image_text_short_error == "IndexError",
                },
                "shuffleVideoText": {
                    "alignmentPreserved": video_text[1]
                    == [f"caption-{index}" for index in expected_video_text],
                    "emptyPairCounts": [0, 0],
                    "longTextsTruncated": "unused-caption" not in truncated_video_texts,
                    "orderSeed29": expected_video_text,
                    "scalarSeedAccepted": video_text_scalar == video_text,
                    "seedModuloCollision": video_text_wrapped == video_text,
                    "shortTextsRejected": video_text_short_error == "IndexError",
                },
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
