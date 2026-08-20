from __future__ import annotations

import json
import sys
import tempfile
from collections import Counter
from pathlib import Path


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit(
            "usage: dataset_folder_io_synthetic_probe.py <pinned-comfyui-source>"
        )

    source = Path(sys.argv[1]).resolve()
    sys.path.insert(0, str(source))

    import folder_paths
    import torch
    from PIL import Image

    from comfy_extras.nodes_dataset import (
        LoadImageDataSetFromFolderNode,
        LoadImageTextDataSetFromFolderNode,
        SaveImageDataSetToFolderNode,
        SaveImageTextDataSetToFolderNode,
        save_images_to_folder,
    )

    previous_input = folder_paths.get_input_directory()
    previous_output = folder_paths.get_output_directory()

    with tempfile.TemporaryDirectory(prefix="nodes-wizard-dataset-folder-io-") as temp_name:
        root = Path(temp_name)
        input_root = root / "input"
        output_root = root / "output"
        input_root.mkdir()
        output_root.mkdir()
        folder_paths.set_input_directory(str(input_root))
        folder_paths.set_output_directory(str(output_root))

        try:
            image_only = input_root / "image_only"
            image_only.mkdir()
            Image.new("RGB", (6, 5), (255, 0, 0)).save(image_only / "red.PNG")
            Image.new("RGB", (7, 4), (0, 255, 0)).save(image_only / "green.webp")
            Image.new("RGB", (8, 3), (0, 0, 255)).save(image_only / "ignored.gif")
            (image_only / "note.txt").write_text("not an image", encoding="utf-8")
            nested = image_only / "nested"
            nested.mkdir()
            Image.new("RGB", (9, 2), (255, 255, 0)).save(nested / "nested.png")

            loaded_images = LoadImageDataSetFromFolderNode.execute("image_only").args[0]
            assert len(loaded_images) == 2
            assert {tuple(image.shape) for image in loaded_images} == {
                (1, 5, 6, 3),
                (1, 4, 7, 3),
            }
            assert all(image.dtype == torch.float32 for image in loaded_images)
            assert all(0.0 <= image.min() <= image.max() <= 1.0 for image in loaded_images)

            empty_folder = input_root / "empty"
            empty_folder.mkdir()
            no_image_error = None
            try:
                LoadImageDataSetFromFolderNode.execute("empty")
            except ValueError as exc:
                no_image_error = str(exc)
            assert no_image_error == "No valid images found in input"

            load_traversal_error = None
            try:
                LoadImageDataSetFromFolderNode.execute("../outside")
            except ValueError as exc:
                load_traversal_error = str(exc)
            assert load_traversal_error is not None
            assert "outside" in load_traversal_error

            image_text = input_root / "image_text"
            image_text.mkdir()
            Image.new("RGB", (5, 5), (20, 40, 60)).save(image_text / "direct.png")
            (image_text / "direct.txt").write_text("  direct caption\n", encoding="utf-8")
            repeated = image_text / "3_subject"
            repeated.mkdir()
            Image.new("RGB", (4, 6), (80, 100, 120)).save(repeated / "captioned.jpg")
            (repeated / "captioned.txt").write_text("nested caption\n", encoding="utf-8")
            Image.new("RGB", (3, 7), (140, 160, 180)).save(repeated / "missing.webp")
            skipped = image_text / "0_skip"
            skipped.mkdir()
            Image.new("RGB", (2, 8), (1, 2, 3)).save(skipped / "ignored.png")

            image_text_output = LoadImageTextDataSetFromFolderNode.execute("image_text")
            paired_images, captions = image_text_output.args
            assert len(paired_images) == 7
            assert Counter(captions) == Counter(
                {"direct caption": 1, "nested caption": 3, "": 3}
            )
            assert all(image.shape[0] == 1 and image.shape[-1] == 3 for image in paired_images)

            overwrite = SaveImageDataSetToFolderNode.execute(
                loaded_images,
                ["overwrite_set"],
                ["sample"],
                ["overwrite"],
            )
            assert overwrite.args == ()
            overwrite_dir = output_root / "overwrite_set"
            assert sorted(path.name for path in overwrite_dir.glob("*.png")) == [
                "sample_00000.png",
                "sample_00001.png",
            ]

            SaveImageDataSetToFolderNode.execute(
                [torch.zeros((1, 5, 6, 3), dtype=torch.float32)],
                ["overwrite_set"],
                ["sample"],
                ["overwrite"],
            )
            assert sorted(path.name for path in overwrite_dir.glob("*.png")) == [
                "sample_00000.png",
                "sample_00001.png",
            ]

            SaveImageDataSetToFolderNode.execute(
                loaded_images,
                ["increment_set"],
                ["sample"],
                ["increment"],
            )
            increment_files = sorted(
                path.name for path in (output_root / "increment_set").glob("*.png")
            )
            assert increment_files == [
                "sample_00001_00000.png",
                "sample_00002_00001.png",
            ]

            text_save = SaveImageTextDataSetToFolderNode.execute(
                paired_images[:3],
                ["paired_set"],
                ["pair"],
                ["overwrite"],
                texts=["first", "second"],
            )
            assert text_save.args == ()
            paired_dir = output_root / "paired_set"
            assert sorted(path.name for path in paired_dir.glob("*.png")) == [
                "pair_00000.png",
                "pair_00001.png",
                "pair_00002.png",
            ]
            assert sorted(path.name for path in paired_dir.glob("*.txt")) == [
                "pair_00000.txt",
                "pair_00001.txt",
            ]
            assert (paired_dir / "pair_00000.txt").read_text(encoding="utf-8") == "first"
            assert (paired_dir / "pair_00001.txt").read_text(encoding="utf-8") == "second"

            save_traversal_error = None
            try:
                SaveImageDataSetToFolderNode.execute(
                    loaded_images,
                    ["../outside"],
                    ["sample"],
                    ["overwrite"],
                )
            except ValueError as exc:
                save_traversal_error = str(exc)
            assert save_traversal_error is not None
            assert "outside" in save_traversal_error

            batched_tensor_error = None
            try:
                save_images_to_folder(
                    [torch.zeros((2, 5, 6, 3), dtype=torch.float32)],
                    str(output_root / "invalid_batch"),
                )
            except (TypeError, ValueError) as exc:
                batched_tensor_error = str(exc)
            assert batched_tensor_error is not None

            print(
                json.dumps(
                    {
                        "loadImages": {
                            "count": len(loaded_images),
                            "shapes": sorted([list(image.shape) for image in loaded_images]),
                            "nestedIgnored": True,
                            "emptyRejected": True,
                        },
                        "loadImageText": {
                            "count": len(paired_images),
                            "captions": dict(Counter(captions)),
                            "zeroPrefixSkipped": True,
                        },
                        "saveImages": {
                            "overwriteFiles": sorted(
                                path.name for path in overwrite_dir.glob("*.png")
                            ),
                            "incrementFiles": increment_files,
                            "staleOverwriteFileRemains": True,
                            "batchedTensorRejected": True,
                        },
                        "saveImageText": {
                            "imageFiles": len(list(paired_dir.glob("*.png"))),
                            "captionFiles": len(list(paired_dir.glob("*.txt"))),
                            "shortCaptionListTruncated": True,
                        },
                        "pathTraversalRejected": True,
                    },
                    ensure_ascii=False,
                    sort_keys=True,
                )
            )
        finally:
            folder_paths.set_input_directory(previous_input)
            folder_paths.set_output_directory(previous_output)


if __name__ == "__main__":
    main()
