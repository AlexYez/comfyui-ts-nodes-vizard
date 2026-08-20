from __future__ import annotations

import hashlib
import json
import math
import re
import unittest
import zipfile
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterator

from tools import catalog


ARTICLE_SPECS = {
    "core.batch-images-node": {
        "directory": "batch-images-node",
        "classType": "BatchImagesNode",
        "pythonModule": "comfy_extras.nodes_post_processing",
        "fingerprint": "sha256:869c0b291c45827301d226e394f959e9416f5c1974e4a1a0d79a84e1d7ab681f",
        "recipe": "recipe.batch-reference-images",
        "experimental": False,
    },
    "core.image-grid": {
        "directory": "image-grid",
        "classType": "ImageGrid",
        "pythonModule": "comfy_extras.nodes_dataset",
        "fingerprint": "sha256:4d1e7e90db7a75b83ee618ff2bea4ef0659153ed6e7da64852133201b9996b04",
        "recipe": "recipe.make-image-contact-sheet",
        "experimental": True,
    },
    "core.split-image-to-tile-list": {
        "directory": "split-image-to-tile-list",
        "classType": "SplitImageToTileList",
        "pythonModule": "comfy_extras.nodes_images",
        "fingerprint": "sha256:ebf988228cdbc33cca5a1f902fa625215b9d5c0c79b0e33de14f437ae5f279bc",
        "recipe": "recipe.split-overlapping-tiles-preview",
        "experimental": False,
    },
    "core.image-merge-tile-list": {
        "directory": "image-merge-tile-list",
        "classType": "ImageMergeTileList",
        "pythonModule": "comfy_extras.nodes_images",
        "fingerprint": "sha256:8fee555867642814e97a32bb2a26ae2c5cc300c5ad680d82e8b4304a1488573a",
        "recipe": "recipe.merge-overlapping-tile-roundtrip",
        "experimental": False,
    },
}

RECIPE_DIRECTORIES = {
    "recipe.batch-reference-images": "batch-reference-images",
    "recipe.make-image-contact-sheet": "make-image-contact-sheet",
    "recipe.split-overlapping-tiles-preview": "split-overlapping-tiles-preview",
    "recipe.merge-overlapping-tile-roundtrip": "merge-overlapping-tile-roundtrip",
}

EXPECTED_FRAGMENT_NODES = {
    "recipe.batch-reference-images": [
        ("BatchImagesNode", {}),
        ("PreviewImage", {}),
    ],
    "recipe.make-image-contact-sheet": [
        ("BatchImagesNode", {}),
        (
            "ImageGrid",
            {"columns": 2, "cell_width": 256, "cell_height": 256, "padding": 4},
        ),
        ("PreviewImage", {}),
    ],
    "recipe.split-overlapping-tiles-preview": [
        (
            "SplitImageToTileList",
            {"tile_width": 1024, "tile_height": 1024, "overlap": 128},
        ),
        (
            "ImageGrid",
            {"columns": 4, "cell_width": 256, "cell_height": 256, "padding": 4},
        ),
        ("PreviewImage", {}),
    ],
    "recipe.merge-overlapping-tile-roundtrip": [
        (
            "SplitImageToTileList",
            {"tile_width": 1024, "tile_height": 1024, "overlap": 128},
        ),
        (
            "ImageMergeTileList",
            {"final_width": 2048, "final_height": 1536, "overlap": 128},
        ),
        ("PreviewImage", {}),
    ],
}

FULL_INVENTORY = catalog.CONTENT / "runtime" / "comfyui-0.32.0.object-info.json"
SOURCE = catalog.ROOT / ".comfyui-source-0.32.0"
WORKFLOW_WHEEL = (
    catalog.ROOT
    / ".upstream-cache"
    / "comfyui_workflow_templates_json-0.1.42-py3-none-any.whl"
)
WORKFLOW_WHEEL_SHA256 = (
    "242982d65e1c51ca03d892bc1009bb6843f457e7dfc0c20afe6438770b7a14a3"
)
EMBEDDED_DOCS_WHEEL = (
    catalog.ROOT
    / ".upstream-cache"
    / "comfyui_embedded_docs-0.5.9-py3-none-any.whl"
)
EMBEDDED_DOCS_WHEEL_SHA256 = (
    "30afae432a71c96aa59421d0f37388c66ff6572b8cbeee8ff045e4d5f84f896c"
)
TARGET_TYPES = {
    "BatchImagesNode",
    "ImageGrid",
    "SplitImageToTileList",
    "ImageMergeTileList",
}


def article_path(spec: dict[str, Any]) -> Path:
    return catalog.CONTENT / "articles" / "core" / spec["directory"] / "manifest.json"


def all_article_ids() -> set[str]:
    ids: set[str] = set()
    for path in (catalog.CONTENT / "articles").rglob("manifest.json"):
        payload = catalog.load_json(path)
        if isinstance(payload, dict) and isinstance(payload.get("articleId"), str):
            ids.add(payload["articleId"])
    return ids


def workflow_node_records(
    payload: dict[str, Any], member: str
) -> Iterator[dict[str, Any]]:
    for index, node in enumerate(payload.get("nodes", [])):
        if isinstance(node, dict):
            yield {
                "member": member,
                "workflowId": payload.get("id"),
                "scope": "root",
                "index": index,
                "node": node,
            }
    definitions = payload.get("definitions")
    subgraphs = definitions.get("subgraphs", []) if isinstance(definitions, dict) else []
    for subgraph_index, subgraph in enumerate(subgraphs):
        if not isinstance(subgraph, dict):
            continue
        for index, node in enumerate(subgraph.get("nodes", [])):
            if isinstance(node, dict):
                yield {
                    "member": member,
                    "workflowId": payload.get("id"),
                    "scope": "subgraph",
                    "subgraphIndex": subgraph_index,
                    "subgraphId": subgraph.get("id"),
                    "index": index,
                    "node": node,
                }


def get_grid_coords(
    width: int,
    height: int,
    tile_width: int,
    tile_height: int,
    overlap: int,
) -> list[tuple[int, int, int, int]]:
    """Pure-Python mirror of the pinned SplitImageToTileList helper."""
    coords: list[tuple[int, int, int, int]] = []
    stride_x = round(max(tile_width * 0.25, tile_width - overlap))
    stride_y = round(max(tile_height * 0.25, tile_height - overlap))
    y = 0
    while y < height:
        x = 0
        y_end = min(y + tile_height, height)
        y_start = max(0, y_end - tile_height)
        while x < width:
            x_end = min(x + tile_width, width)
            x_start = max(0, x_end - tile_width)
            coords.append((x_start, y_start, x_end, y_end))
            if x_end >= width:
                break
            x += stride_x
        if y_end >= height:
            break
        y += stride_y
    return coords


def split_plane(
    image: list[list[float]], tile_width: int, tile_height: int, overlap: int
) -> list[list[list[float]]]:
    height = len(image)
    width = len(image[0])
    return [
        [row[x0:x1] for row in image[y0:y1]]
        for x0, y0, x1, y1 in get_grid_coords(
            width, height, tile_width, tile_height, overlap
        )
    ]


def merge_plane(
    tiles: list[list[list[float]]],
    final_width: int,
    final_height: int,
    overlap: int,
) -> list[list[float]]:
    """Single-batch/single-channel mirror of the pinned weighted merge."""
    tile_height = len(tiles[0])
    tile_width = len(tiles[0][0])
    coords = get_grid_coords(
        final_width, final_height, tile_width, tile_height, overlap
    )
    canvas = [[0.0 for _ in range(final_width)] for _ in range(final_height)]
    weights = [[0.0 for _ in range(final_width)] for _ in range(final_height)]
    if overlap > 0:
        y_weight = [
            max(math.sin(math.pi * i / (tile_height - 1)), 1e-5)
            for i in range(tile_height)
        ]
        x_weight = [
            max(math.sin(math.pi * i / (tile_width - 1)), 1e-5)
            for i in range(tile_width)
        ]
    else:
        y_weight = [1.0] * tile_height
        x_weight = [1.0] * tile_width
    for index, (x0, y0, x1, y1) in enumerate(coords):
        if index >= len(tiles):
            break
        tile = tiles[index]
        real_height = min(y1 - y0, len(tile))
        real_width = min(x1 - x0, len(tile[0]))
        for ty in range(real_height):
            for tx in range(real_width):
                weight = y_weight[ty] * x_weight[tx]
                canvas[y0 + ty][x0 + tx] += tile[ty][tx] * weight
                weights[y0 + ty][x0 + tx] += weight
    for y in range(final_height):
        for x in range(final_width):
            if weights[y][x] == 0:
                weights[y][x] = 1.0
            canvas[y][x] /= weights[y][x]
    return canvas


class ImageBatchGridTileContentTests(unittest.TestCase):
    def test_articles_recipes_and_research_records_are_valid_and_honest(self) -> None:
        article_ids = all_article_ids()
        article_schema = catalog.load_json(
            catalog.CONTENT / "schemas" / "article.schema.v1.json"
        )
        recipe_schema = catalog.load_json(
            catalog.CONTENT / "schemas" / "recipe.schema.v1.json"
        )
        fragment_schema = catalog.load_json(
            catalog.CONTENT / "schemas" / "recipe-fragment.schema.v1.json"
        )
        research_schema = catalog.load_json(
            catalog.CONTENT / "schemas" / "article-research.schema.v1.json"
        )
        validation_errors: list[str] = []

        for article_id, spec in ARTICLE_SPECS.items():
            path = article_path(spec)
            article = catalog.load_json(path)
            self.assertEqual([], catalog.json_schema_errors(article, article_schema))
            catalog.validate_article(path, article, validation_errors)
            self.assertEqual(article_id, article["articleId"])
            self.assertEqual("draft", article["status"])
            self.assertEqual("in_review", article["editorial"]["state"])
            self.assertEqual(spec["experimental"], article["experimental"])
            self.assertEqual(spec["recipe"], article["assets"][0]["id"])
            self.assertNotIn("\ufffd", json.dumps(article, ensure_ascii=False))

            relations = article["relations"]
            targets = relations["related"] + relations["alternatives"]
            if relations["replacedBy"] is not None:
                targets.append(relations["replacedBy"])
            self.assertTrue(set(targets).issubset(article_ids), article_id)

            body = (path.parent / article["body"]).read_text(encoding="utf-8")
            headings = re.findall(r"^## (.+)$", body, flags=re.MULTILINE)
            semantic_h2 = [heading for heading in headings if heading != "Источники"]
            self.assertEqual(10, len(semantic_h2), article_id)
            self.assertNotIn("Human approval pending", body)
            self.assertNotIn("human approval", body.lower())
            self.assertNotIn("человеческое редакционное утверждение", body.lower())
            self.assertNotRegex(
                body.lower(),
                r"важно отметить|стоит отметить|в современном мире|революционн|"
                r"является незаменим|данная нода|давайте разбер|подводя итог|"
                r"мощный инструмент|не просто .{0,80}, а",
            )

            for source in article["sources"]:
                url = source["url"]
                if "github.com/Comfy-Org/ComfyUI/" in url:
                    self.assertIn(
                        "c2bcbecd82ec5ae66594340b395c24ef0217b238", url
                    )
                if "github.com/Comfy-Org/embedded-docs/" in url:
                    self.assertIn(
                        "1d258cf6e374d60d138a2bfcd273c7e11f750ef9", url
                    )
                if "github.com/Comfy-Org/workflow_templates/" in url:
                    self.assertIn(
                        "cca1ea5ea4560108ecc2f44dee951f41ea433062", url
                    )

            record = catalog.load_json(
                catalog.CONTENT / "research" / "reviews" / f"{article_id}.json"
            )
            self.assertEqual([], catalog.json_schema_errors(record, research_schema))
            self.assertEqual(spec["classType"], record["node"]["classType"])
            self.assertEqual(spec["pythonModule"], record["node"]["pythonModule"])
            self.assertEqual("fact_checked", record["state"])
            self.assertEqual("automated_assisted", record["reviewMode"])
            self.assertFalse(record["checks"]["exampleExecuted"])
            self.assertTrue(record["checks"]["officialCasesInspected"])
            self.assertNotEqual("human_approved", record["state"])
            self.assertTrue(record["knownGaps"])

        self.assertEqual([], validation_errors)

        for recipe_id, directory in RECIPE_DIRECTORIES.items():
            path = catalog.CONTENT / "recipes" / directory / "recipe.json"
            recipe = catalog.load_json(path)
            self.assertEqual([], catalog.json_schema_errors(recipe, recipe_schema))
            self.assertEqual(recipe_id, recipe["recipeId"])
            self.assertEqual("draft", recipe["editorial"]["state"])
            self.assertTrue(set(recipe["articleIds"]).issubset(article_ids))
            self.assertNotIn("approved", json.dumps(recipe).lower())

            fragment = catalog.load_json(path.parent / recipe["fragment"]["path"])
            self.assertEqual([], catalog.json_schema_errors(fragment, fragment_schema))
            actual_nodes = [
                (node["classType"], node["settings"]) for node in fragment["nodes"]
            ]
            self.assertEqual(EXPECTED_FRAGMENT_NODES[recipe_id], actual_nodes)

            refs = {node["ref"] for node in fragment["nodes"]}
            for external in fragment["externalInputs"]:
                self.assertIn(external["to"], refs)
            for connection in fragment["connections"]:
                self.assertIn(connection["from"], refs)
                self.assertIn(connection["to"], refs)

            body = (path.parent / recipe["body"]).read_text(encoding="utf-8")
            self.assertNotIn("\ufffd", body)
            self.assertNotIn("Human approval pending", body)

    def test_runtime_contracts_and_fingerprints_match_object_info(self) -> None:
        inventory = catalog.load_json(FULL_INVENTORY)
        for spec in ARTICLE_SPECS.values():
            definition = inventory[spec["classType"]]
            self.assertEqual(spec["pythonModule"], definition["python_module"])
            self.assertEqual(
                spec["fingerprint"],
                catalog.schema_fingerprint(spec["classType"], definition),
            )

        batch = inventory["BatchImagesNode"]
        autogrow = batch["input"]["required"]["images"]
        self.assertEqual("COMFY_AUTOGROW_V3", autogrow[0])
        template = autogrow[1]["template"]
        self.assertEqual("image", template["prefix"])
        self.assertEqual((1, 50), (template["min"], template["max"]))
        self.assertEqual("IMAGE", template["input"]["required"]["image"][0])
        self.assertFalse(batch["is_input_list"])
        self.assertEqual([False], batch["output_is_list"])

        grid = inventory["ImageGrid"]
        self.assertTrue(grid["is_input_list"])
        self.assertTrue(grid["experimental"])
        self.assertEqual([False], grid["output_is_list"])
        grid_inputs = grid["input"]["required"]
        self.assertEqual((1, 20), (grid_inputs["columns"][1]["min"], grid_inputs["columns"][1]["max"]))
        self.assertEqual((32, 2048), (grid_inputs["cell_width"][1]["min"], grid_inputs["cell_width"][1]["max"]))
        self.assertEqual((0, 50), (grid_inputs["padding"][1]["min"], grid_inputs["padding"][1]["max"]))

        split = inventory["SplitImageToTileList"]
        self.assertFalse(split["is_input_list"])
        self.assertEqual([True], split["output_is_list"])
        split_inputs = split["input"]["required"]
        self.assertEqual((64, 16384), (split_inputs["tile_width"][1]["min"], split_inputs["tile_width"][1]["max"]))
        self.assertEqual((0, 4096), (split_inputs["overlap"][1]["min"], split_inputs["overlap"][1]["max"]))

        merge = inventory["ImageMergeTileList"]
        self.assertTrue(merge["is_input_list"])
        self.assertEqual([False], merge["output_is_list"])
        merge_inputs = merge["input"]["required"]
        self.assertEqual((64, 32768), (merge_inputs["final_width"][1]["min"], merge_inputs["final_width"][1]["max"]))
        self.assertEqual((0, 4096), (merge_inputs["overlap"][1]["min"], merge_inputs["overlap"][1]["max"]))

    def test_pinned_source_contains_the_reviewed_algorithms(self) -> None:
        batching = (SOURCE / "comfy_extras" / "nodes_post_processing.py").read_text(
            encoding="utf-8"
        )
        self.assertIn("def batch_images(images: list[torch.Tensor])", batching)
        self.assertIn("max_channels = max(image.shape[-1] for image in images)", batching)
        self.assertIn("value=1.0", batching)
        self.assertIn('first_image_shape[2], first_image_shape[1], "bilinear", "center"', batching)
        self.assertIn("return torch.cat(resized_images, dim=0)", batching)
        self.assertIn('prefix="image", min=1, max=50', batching)

        dataset = (SOURCE / "comfy_extras" / "nodes_dataset.py").read_text(
            encoding="utf-8"
        )
        self.assertIn("class ImageGridNode(ImageProcessingNode)", dataset)
        self.assertIn("rows = (num_images + columns - 1) // columns", dataset)
        self.assertIn("grid_width = columns * cell_width + (columns - 1) * padding", dataset)
        self.assertIn('Image.new("RGB", (grid_width, grid_height), (0, 0, 0))', dataset)
        self.assertIn("Image.Resampling.LANCZOS", dataset)
        self.assertIn("astype(np.uint8)", dataset)

        images = (SOURCE / "comfy_extras" / "nodes_images.py").read_text(
            encoding="utf-8"
        )
        self.assertIn("class SplitImageToTileList(IO.ComfyNode)", images)
        self.assertIn("round(max(tile_width * 0.25, tile_width - overlap))", images)
        self.assertIn("image[:, y_start:y_end, x_start:x_end, :]", images)
        self.assertIn("IO.Image.Output(is_output_list=True)", images)
        self.assertIn("class ImageMergeTileList(IO.ComfyNode)", images)
        self.assertIn("is_input_list=True", images)
        self.assertIn("torch.sin(math.pi * torch.linspace", images)
        self.assertIn("if i >= len(image_list):", images)
        self.assertIn("weights[weights == 0] = 1.0", images)

    def test_embedded_docs_are_pinned_and_known_discrepancies_stay_visible(self) -> None:
        self.assertEqual(
            EMBEDDED_DOCS_WHEEL_SHA256,
            hashlib.sha256(EMBEDDED_DOCS_WHEEL.read_bytes()).hexdigest(),
        )
        with zipfile.ZipFile(EMBEDDED_DOCS_WHEEL) as archive:
            docs = {
                class_type: archive.read(
                    f"comfyui_embedded_docs/docs/{class_type}/en.md"
                ).decode("utf-8")
                for class_type in TARGET_TYPES
            }
        self.assertTrue(
            all("This documentation was AI-generated" in text for text in docs.values())
        )
        self.assertIn("between 2 and 50", docs["BatchImagesNode"])
        self.assertIn("1048576", docs["SplitImageToTileList"])
        self.assertIn("first tile", docs["ImageMergeTileList"].lower())
        self.assertIn("cell_width", docs["ImageGrid"])

    def test_workflow_wheel_census_and_representative_topology(self) -> None:
        self.assertEqual(
            WORKFLOW_WHEEL_SHA256,
            hashlib.sha256(WORKFLOW_WHEEL.read_bytes()).hexdigest(),
        )
        occurrences: Counter[str] = Counter()
        scopes: Counter[tuple[str, str]] = Counter()
        files: dict[str, set[str]] = defaultdict(set)
        workflow_ids: dict[str, set[str]] = defaultdict(set)
        modes: dict[str, Counter[int]] = defaultdict(Counter)
        connected_inputs: Counter[int] = Counter()
        serialized_inputs: Counter[int] = Counter()
        widget_serialization: Counter[str] = Counter()
        json_count = 0
        workflow_count = 0
        representative: dict[str, Any] | None = None

        with zipfile.ZipFile(WORKFLOW_WHEEL) as archive:
            self.assertIsNone(archive.testzip())
            for member in sorted(archive.namelist()):
                if not member.endswith(".json"):
                    continue
                json_count += 1
                payload = json.loads(archive.read(member).decode("utf-8"))
                if not isinstance(payload, dict) or not isinstance(payload.get("nodes"), list):
                    continue
                workflow_count += 1
                for record in workflow_node_records(payload, member):
                    node = record["node"]
                    node_type = node.get("type")
                    if node_type not in TARGET_TYPES:
                        continue
                    occurrences[node_type] += 1
                    scopes[(node_type, record["scope"])] += 1
                    files[node_type].add(member)
                    workflow_ids[node_type].add(str(record["workflowId"]))
                    modes[node_type][node.get("mode", 0)] += 1
                    if node_type == "BatchImagesNode":
                        inputs = node.get("inputs", [])
                        serialized_inputs[len(inputs)] += 1
                        connected_inputs[
                            sum(item.get("link") is not None for item in inputs)
                        ] += 1
                        self.assertIn(node.get("widgets_values"), (None, []))
                        widget_serialization[
                            "missing" if "widgets_values" not in node else "empty"
                        ] += 1
                        self.assertIsNone(inputs[-1].get("link"))
                    if member.endswith("/api_bfl_flux2_max_sofa_swap.json"):
                        representative = payload

        self.assertEqual((512, 496), (json_count, workflow_count))
        self.assertEqual(Counter({"BatchImagesNode": 55}), occurrences)
        self.assertEqual(37, scopes[("BatchImagesNode", "root")])
        self.assertEqual(18, scopes[("BatchImagesNode", "subgraph")])
        self.assertEqual(43, len(files["BatchImagesNode"]))
        self.assertEqual(31, len(workflow_ids["BatchImagesNode"]))
        self.assertEqual(Counter({0: 44, 4: 11}), modes["BatchImagesNode"])
        self.assertEqual(Counter({1: 12, 2: 28, 3: 12, 4: 1, 5: 1, 7: 1}), connected_inputs)
        self.assertEqual(Counter({2: 12, 3: 28, 4: 12, 5: 1, 6: 1, 8: 1}), serialized_inputs)
        self.assertEqual(Counter({"empty": 47, "missing": 8}), widget_serialization)

        self.assertIsNotNone(representative)
        assert representative is not None
        self.assertEqual(
            "649f68f7-fb15-4740-973f-97235ae353be", representative["id"]
        )
        by_id = {node["id"]: node for node in representative["nodes"]}
        batch = by_id[15]
        self.assertEqual("BatchImagesNode", batch["type"])
        self.assertEqual(
            [20, 21, 22, None],
            [item.get("link") for item in batch["inputs"]],
        )
        links = {link[0]: link for link in representative["links"]}
        self.assertEqual([2, 3, 10], [links[index][1] for index in (20, 21, 22)])
        self.assertTrue(all(by_id[node_id]["type"] == "LoadImage" for node_id in (2, 3, 10)))
        self.assertEqual([23, 15, 0, 1, 0, "IMAGE"], links[23])
        self.assertEqual("Flux2MaxImageNode", by_id[1]["type"])

    def test_safe_synthetic_batch_grid_and_tile_semantics(self) -> None:
        # Same-size one-pixel frames exercise the exact max-channel/pad/order path.
        inputs = [
            [[[0.1, 0.2, 0.3]], [[0.4, 0.5, 0.6]]],
            [[[0.7, 0.8, 0.9, 0.25]]],
        ]
        max_channels = max(len(frame[0]) for batch in inputs for frame in batch)
        output: list[list[list[float]]] = []
        for batch in inputs:
            for frame in batch:
                pixel = list(frame[0])
                if len(pixel) < max_channels:
                    pixel.append(1.0)
                output.append([pixel])
        self.assertEqual(
            [
                [[0.1, 0.2, 0.3, 1.0]],
                [[0.4, 0.5, 0.6, 1.0]],
                [[0.7, 0.8, 0.9, 0.25]],
            ],
            output,
        )

        columns, cell_width, cell_height, padding, count = 4, 256, 128, 4, 5
        rows = (count + columns - 1) // columns
        grid_width = columns * cell_width + (columns - 1) * padding
        grid_height = rows * cell_height + (rows - 1) * padding
        positions = [
            (
                (index % columns) * (cell_width + padding),
                (index // columns) * (cell_height + padding),
            )
            for index in range(count)
        ]
        self.assertEqual((2, 1036, 260), (rows, grid_width, grid_height))
        self.assertEqual((0, 132), positions[-1])
        self.assertEqual(3, rows * columns - count)
        quantized = int(max(0.0, min(1.0, 0.5)) * 255) / 255.0
        self.assertEqual(127 / 255.0, quantized)

        coords = get_grid_coords(2048, 1536, 1024, 1024, 128)
        self.assertEqual(
            [
                (0, 0, 1024, 1024),
                (896, 0, 1920, 1024),
                (1024, 0, 2048, 1024),
                (0, 512, 1024, 1536),
                (896, 512, 1920, 1536),
                (1024, 512, 2048, 1536),
            ],
            coords,
        )
        self.assertEqual(256, round(max(1024 * 0.25, 1024 - 1000)))
        high_overlap_edge = get_grid_coords(1100, 1024, 1024, 1024, 1000)
        self.assertEqual(
            [(0, 0, 1024, 1024), (76, 0, 1100, 1024)],
            high_overlap_edge,
        )
        self.assertGreater(
            high_overlap_edge[0][2] - high_overlap_edge[1][0],
            0.75 * 1024,
        )
        zero_requested_overlap = get_grid_coords(1500, 1024, 1024, 1024, 0)
        self.assertEqual(
            [(0, 0, 1024, 1024), (476, 0, 1500, 1024)],
            zero_requested_overlap,
        )
        self.assertEqual(
            548,
            zero_requested_overlap[0][2] - zero_requested_overlap[1][0],
        )

        image = [[float(y * 8 + x) / 47.0 for x in range(8)] for y in range(6)]
        tiles = split_plane(image, tile_width=4, tile_height=4, overlap=1)
        self.assertEqual(6, len(tiles))
        merged = merge_plane(tiles, final_width=8, final_height=6, overlap=1)
        for expected_row, actual_row in zip(image, merged):
            for expected, actual in zip(expected_row, actual_row):
                self.assertAlmostEqual(expected, actual, places=12)

        missing = merge_plane(tiles[:-1], final_width=8, final_height=6, overlap=1)
        self.assertEqual(0.0, missing[-1][-1])
        with_extra = merge_plane(
            tiles + [[[99.0] * 4 for _ in range(4)]],
            final_width=8,
            final_height=6,
            overlap=1,
        )
        self.assertEqual(merged, with_extra)


if __name__ == "__main__":
    unittest.main()
