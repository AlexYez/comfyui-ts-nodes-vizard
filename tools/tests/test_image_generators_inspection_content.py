from __future__ import annotations

import hashlib
import json
import re
import unittest
import zipfile
from collections import Counter
from pathlib import Path
from typing import Any, Iterator

from tools import catalog


ARTICLE_SPECS = {
    "core.empty-image": {
        "directory": "empty-image",
        "classType": "EmptyImage",
        "pythonModule": "nodes",
        "fingerprint": "sha256:14389665a294c78c961b480a288b61982b7172576ef2de6586978aac2986636f",
        "recipe": "recipe.solid-color-mask-composite",
    },
    "core.get-image-size": {
        "directory": "get-image-size",
        "classType": "GetImageSize",
        "pythonModule": "comfy_extras.nodes_images",
        "fingerprint": "sha256:23e941a8b36623f77b9ea14bf8be52c3dd5c75a1299a559307c4c3d89b0e682d",
        "recipe": "recipe.select-last-video-frame-by-size",
    },
    "core.primitive-bounding-box": {
        "directory": "primitive-bounding-box",
        "classType": "PrimitiveBoundingBox",
        "pythonModule": "comfy_extras.nodes_images",
        "fingerprint": "sha256:5d7f7c677b3ae9c48ead0216ab6fc0798cdd0b021e52020a2ef4375bbe79f234",
        "recipe": "recipe.crop-image-by-bounding-box",
    },
    "core.resize-and-pad-image": {
        "directory": "resize-and-pad-image",
        "classType": "ResizeAndPadImage",
        "pythonModule": "comfy_extras.nodes_images",
        "fingerprint": "sha256:9a92139128eeb67ae2f22986236a7852e34bd21293525e0febd514aef72915ca",
        "recipe": "recipe.fit-image-batch-1280x720",
    },
}

RECIPE_DIRECTORIES = {
    "recipe.solid-color-mask-composite": "solid-color-mask-composite",
    "recipe.select-last-video-frame-by-size": "select-last-video-frame-by-size",
    "recipe.crop-image-by-bounding-box": "crop-image-by-bounding-box",
    "recipe.fit-image-batch-1280x720": "fit-image-batch-1280x720",
}

EXPECTED_FRAGMENT_NODES = {
    "recipe.solid-color-mask-composite": [
        (
            "EmptyImage",
            {"width": 1024, "height": 1024, "batch_size": 1, "color": 0},
        ),
        (
            "EmptyImage",
            {
                "width": 1024,
                "height": 1024,
                "batch_size": 1,
                "color": 16711680,
            },
        ),
        ("ImageCompositeMasked", {"x": 0, "y": 0, "resize_source": False}),
    ],
    "recipe.select-last-video-frame-by-size": [
        ("GetVideoComponents", {}),
        ("GetImageSize", {}),
        ("ImageFromBatch", {"batch_index": 0, "length": 1}),
    ],
    "recipe.crop-image-by-bounding-box": [
        (
            "PrimitiveBoundingBox",
            {"x": 64, "y": 64, "width": 512, "height": 512},
        ),
        ("ImageCropV2", {}),
    ],
    "recipe.fit-image-batch-1280x720": [
        (
            "ResizeAndPadImage",
            {
                "target_width": 1280,
                "target_height": 720,
                "padding_color": "black",
                "interpolation": "lanczos",
            },
        ),
        ("GetImageSize", {}),
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
TARGET_TYPES = {
    "EmptyImage",
    "GetImageSize",
    "PrimitiveBoundingBox",
    "ResizeAndPadImage",
}


def article_path(spec: dict[str, str]) -> Path:
    return catalog.CONTENT / "articles" / "core" / spec["directory"] / "manifest.json"


def all_article_ids() -> set[str]:
    result: set[str] = set()
    for path in (catalog.CONTENT / "articles").rglob("manifest.json"):
        payload = catalog.load_json(path)
        if isinstance(payload, dict) and isinstance(payload.get("articleId"), str):
            result.add(payload["articleId"])
    return result


def workflow_node_records(
    payload: dict[str, Any], member: str
) -> Iterator[dict[str, Any]]:
    workflow_id = payload.get("id")
    for index, node in enumerate(payload.get("nodes", [])):
        if isinstance(node, dict):
            yield {
                "member": member,
                "workflowId": workflow_id,
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
                    "workflowId": workflow_id,
                    "scope": "subgraph",
                    "subgraphIndex": subgraph_index,
                    "subgraphId": subgraph.get("id"),
                    "index": index,
                    "node": node,
                }


def load_official_workflows() -> tuple[list[dict[str, Any]], int]:
    workflows: list[dict[str, Any]] = []
    json_count = 0
    with zipfile.ZipFile(WORKFLOW_WHEEL) as archive:
        for member in sorted(archive.namelist()):
            if not member.endswith(".json"):
                continue
            json_count += 1
            payload = json.loads(archive.read(member).decode("utf-8"))
            if (
                isinstance(payload, dict)
                and isinstance(payload.get("nodes"), list)
            ):
                workflows.append({"member": member, "payload": payload})
    return workflows, json_count


def input_type(definition: Any) -> str | None:
    if isinstance(definition, list) and definition:
        first = definition[0]
        if isinstance(first, str):
            return first
        if isinstance(first, list):
            return "COMBO"
    if isinstance(definition, str):
        return definition
    return None


class ImageGeneratorsInspectionContentTests(unittest.TestCase):
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
        errors: list[str] = []

        for article_id, spec in ARTICLE_SPECS.items():
            path = article_path(spec)
            article = catalog.load_json(path)
            self.assertEqual([], catalog.json_schema_errors(article, article_schema))
            catalog.validate_article(path, article, errors)
            self.assertEqual(article_id, article["articleId"])
            self.assertEqual("draft", article["status"])
            self.assertEqual("in_review", article["editorial"]["state"])
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
            self.assertNotEqual("human_approved", record["state"])
            self.assertTrue(record["knownGaps"])

        for recipe_id, directory in RECIPE_DIRECTORIES.items():
            path = catalog.CONTENT / "recipes" / directory / "recipe.json"
            recipe = catalog.load_json(path)
            self.assertEqual([], catalog.json_schema_errors(recipe, recipe_schema))
            catalog.validate_recipe(path, recipe, article_ids, errors)
            self.assertEqual(recipe_id, recipe["recipeId"])
            self.assertEqual("draft", recipe["editorial"]["state"])
            self.assertNotIn("workflow", recipe)
            fragment = catalog.load_json(path.parent / recipe["fragment"]["path"])
            self.assertEqual([], catalog.json_schema_errors(fragment, fragment_schema))
            self.assertEqual(
                EXPECTED_FRAGMENT_NODES[recipe_id],
                [(node["classType"], node["settings"]) for node in fragment["nodes"]],
            )

        self.assertEqual([], errors)

    def test_runtime_contracts_fingerprints_and_fragment_ports(self) -> None:
        nodes = catalog.object_info_nodes(catalog.load_json(FULL_INVENTORY))
        self.assertNotIn("BoundingBox", nodes)

        for article_id, spec in ARTICLE_SPECS.items():
            article = catalog.load_json(article_path(spec))
            class_type = spec["classType"]
            runtime = nodes[class_type]
            self.assertEqual(spec["pythonModule"], runtime["python_module"])
            self.assertEqual(spec["fingerprint"], catalog.schema_fingerprint(class_type, runtime))
            self.assertEqual(spec["fingerprint"], article["editorial"]["schemaHash"])

        empty = nodes["EmptyImage"]
        self.assertEqual(["IMAGE"], empty["output"])
        self.assertEqual(
            {"default": 0, "min": 0, "max": 16777215, "step": 1, "display": "color"},
            empty["input"]["required"]["color"][1],
        )
        self.assertEqual(
            {"default": 1, "min": 1, "max": 4096},
            empty["input"]["required"]["batch_size"][1],
        )

        size = nodes["GetImageSize"]
        self.assertEqual(["INT", "INT", "INT"], size["output"])
        self.assertEqual(["width", "height", "batch_size"], size["output_name"])
        self.assertNotIn("IMAGE", size["output"])
        self.assertEqual(["UNIQUE_ID"], size["input"]["hidden"]["unique_id"])

        box = nodes["PrimitiveBoundingBox"]
        self.assertEqual("Bounding Box", box["display_name"])
        self.assertEqual(["BOUNDING_BOX"], box["output"])
        self.assertEqual(
            {"default": 0, "min": 0, "max": 16384},
            box["input"]["required"]["x"][1],
        )
        self.assertEqual(
            {"default": 512, "min": 1, "max": 16384},
            box["input"]["required"]["width"][1],
        )

        resize = nodes["ResizeAndPadImage"]
        self.assertEqual(
            ["white", "black"],
            resize["input"]["required"]["padding_color"][1]["options"],
        )
        self.assertEqual(
            ["area", "bicubic", "nearest-exact", "bilinear", "lanczos"],
            resize["input"]["required"]["interpolation"][1]["options"],
        )

        for recipe_id, directory in RECIPE_DIRECTORIES.items():
            fragment = catalog.load_json(
                catalog.CONTENT / "recipes" / directory / "fragment.json"
            )
            node_by_ref = {node["ref"]: node for node in fragment["nodes"]}
            for node in fragment["nodes"]:
                runtime = nodes[node["classType"]]
                declared = {
                    key
                    for section in ("required", "optional")
                    for key in runtime.get("input", {}).get(section, {})
                }
                self.assertTrue(set(node["settings"]).issubset(declared), recipe_id)

            for external in fragment["externalInputs"]:
                target = node_by_ref[external["to"]]
                runtime = nodes[target["classType"]]
                definition = None
                for section in ("required", "optional"):
                    definition = runtime.get("input", {}).get(section, {}).get(external["input"])
                    if definition is not None:
                        break
                self.assertEqual(external["type"], input_type(definition), external)

            for connection in fragment["connections"]:
                source_node = node_by_ref[connection["from"]]
                target_node = node_by_ref[connection["to"]]
                source_runtime = nodes[source_node["classType"]]
                target_runtime = nodes[target_node["classType"]]
                output_index = source_runtime["output_name"].index(connection["output"])
                source_type = source_runtime["output"][output_index]
                target_definition = None
                for section in ("required", "optional"):
                    target_definition = target_runtime.get("input", {}).get(section, {}).get(connection["input"])
                    if target_definition is not None:
                        break
                self.assertEqual(source_type, input_type(target_definition), connection)

    @unittest.skipUnless(SOURCE.exists(), "pinned ComfyUI source checkout is absent")
    def test_pinned_source_semantics(self) -> None:
        nodes_source = (SOURCE / "nodes.py").read_text(encoding="utf-8")
        image_source = (SOURCE / "comfy_extras" / "nodes_images.py").read_text(
            encoding="utf-8"
        )

        self.assertIn("((color >> 16) & 0xFF) / 0xFF", nodes_source)
        self.assertIn("((color >> 8) & 0xFF) / 0xFF", nodes_source)
        self.assertIn("((color) & 0xFF) / 0xFF", nodes_source)
        self.assertIn("torch.cat((r, g, b), dim=-1)", nodes_source)

        self.assertIn('node_id="PrimitiveBoundingBox"', image_source)
        self.assertIn(
            'return IO.NodeOutput({"x": x, "y": y, "width": width, "height": height})',
            image_source,
        )
        self.assertIn("crop_region.get(\"x\", 0)", image_source)

        self.assertIn("scale = min(scale_w, scale_h)", image_source)
        self.assertIn("new_width = int(orig_width * scale)", image_source)
        self.assertIn("new_height = int(orig_height * scale)", image_source)
        self.assertIn('pad_value = 0.0 if padding_color == "black" else 1.0', image_source)
        self.assertIn("y_offset = (target_height - new_height) // 2", image_source)
        self.assertIn("x_offset = (target_width - new_width) // 2", image_source)

        self.assertIn("height = image.shape[1]", image_source)
        self.assertIn("width = image.shape[2]", image_source)
        self.assertIn("batch_size = image.shape[0]", image_source)
        self.assertIn("return IO.NodeOutput(width, height, batch_size)", image_source)

    @unittest.skipUnless(WORKFLOW_WHEEL.exists(), "official workflow wheel is absent")
    def test_exhaustive_official_workflow_inventory_and_topology(self) -> None:
        self.assertEqual(
            WORKFLOW_WHEEL_SHA256,
            hashlib.sha256(WORKFLOW_WHEEL.read_bytes()).hexdigest(),
        )
        with zipfile.ZipFile(WORKFLOW_WHEEL) as archive:
            self.assertIsNone(archive.testzip())

        workflows, json_count = load_official_workflows()
        self.assertEqual(512, json_count)
        self.assertEqual(496, len(workflows))
        all_records = [
            record
            for workflow in workflows
            for record in workflow_node_records(
                workflow["payload"], workflow["member"]
            )
        ]
        records = [record for record in all_records if record["node"].get("type") in TARGET_TYPES]
        by_type = Counter(record["node"]["type"] for record in records)
        root_by_type = Counter(
            record["node"]["type"] for record in records if record["scope"] == "root"
        )
        file_count = {
            class_type: len(
                {record["member"] for record in records if record["node"]["type"] == class_type}
            )
            for class_type in TARGET_TYPES
        }
        mode_count = {
            class_type: Counter(
                record["node"].get("mode", 0)
                for record in records
                if record["node"]["type"] == class_type
            )
            for class_type in TARGET_TYPES
        }

        self.assertEqual(
            {"EmptyImage": 9, "GetImageSize": 80, "ResizeAndPadImage": 11},
            dict(by_type),
        )
        self.assertEqual(
            {"EmptyImage": 3, "GetImageSize": 25, "ResizeAndPadImage": 3},
            dict(root_by_type),
        )
        self.assertEqual(8, file_count["EmptyImage"])
        self.assertEqual(60, file_count["GetImageSize"])
        self.assertEqual(0, file_count["PrimitiveBoundingBox"])
        self.assertEqual(9, file_count["ResizeAndPadImage"])
        self.assertEqual(Counter({0: 9}), mode_count["EmptyImage"])
        self.assertEqual(Counter({0: 78, 4: 2}), mode_count["GetImageSize"])
        self.assertEqual(Counter(), mode_count["PrimitiveBoundingBox"])
        self.assertEqual(Counter({0: 11}), mode_count["ResizeAndPadImage"])
        self.assertFalse(
            any(record["node"].get("type") == "BoundingBox" for record in all_records)
        )

        def root_node(file_name: str, node_id: int) -> dict[str, Any]:
            matches = [
                record["node"]
                for record in all_records
                if Path(record["member"]).name == file_name
                and record["scope"] == "root"
                and record["node"].get("id") == node_id
            ]
            self.assertEqual(1, len(matches), (file_name, node_id))
            return matches[0]

        black = root_node("basic_mask_operations_and_compositing.json", 1)
        red = root_node("basic_mask_operations_and_compositing.json", 360)
        composite = root_node("basic_mask_operations_and_compositing.json", 359)
        self.assertEqual([1024, 1024, 1, 0], black["widgets_values"])
        self.assertEqual([1024, 1024, 1, 16711680], red["widgets_values"])
        self.assertEqual([676, 677, 679], black["outputs"][0]["links"])
        self.assertEqual([669, 681], red["outputs"][0]["links"])
        self.assertEqual([679, 669], [item["link"] for item in composite["inputs"][:2]])

        product_size = root_node("templates-product_ad-v2.0.json", 17)
        product_resize = root_node("templates-product_ad-v2.0.json", 16)
        self.assertEqual([16], product_size["outputs"][0]["links"])
        self.assertEqual([17], product_size["outputs"][1]["links"])
        self.assertEqual([19, 16, 17], [item["link"] for item in product_resize["inputs"]])
        self.assertEqual([512, 512, "white", "area"], product_resize["widgets_values"])

        vidu_size = root_node("api_vidu_video_extension.json", 10)
        vidu_select = root_node("api_vidu_video_extension.json", 5)
        self.assertEqual([5], vidu_size["outputs"][2]["links"])
        self.assertEqual([6, 5], [item["link"] for item in vidu_select["inputs"]])
        self.assertEqual([0, 1], vidu_select["widgets_values"])

        ltx_resize = root_node("template_ltx2_3_ic_lora_ingredients.json", 722)
        ltx_size = root_node("template_ltx2_3_ic_lora_ingredients.json", 721)
        self.assertEqual([1280, 720, "black", "lanczos"], ltx_resize["widgets_values"])
        self.assertEqual([1821], [item["link"] for item in ltx_resize["inputs"]])
        self.assertEqual([1822, 1823, 1824], ltx_resize["outputs"][0]["links"])
        self.assertEqual(1822, ltx_size["inputs"][0]["link"])

        resize_records = [
            record for record in records if record["node"]["type"] == "ResizeAndPadImage"
        ]
        linked_target_count = 0
        for record in resize_records:
            inputs = {item["name"]: item.get("link") for item in record["node"].get("inputs", [])}
            if inputs.get("target_width") is not None and inputs.get("target_height") is not None:
                linked_target_count += 1
        self.assertEqual(10, linked_target_count)


if __name__ == "__main__":
    unittest.main()
