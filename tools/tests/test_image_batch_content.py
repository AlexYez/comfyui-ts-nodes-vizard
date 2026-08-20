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
    "core.image-invert": {
        "directory": "image-invert",
        "classType": "ImageInvert",
        "pythonModule": "nodes",
        "fingerprint": "sha256:1b45f864166fe1b48efd7f6b089e74af3f72e1d280f4d66c94697160b7883cd8",
        "recipe": "recipe.invert-canny-control-image",
    },
    "core.image-batch": {
        "directory": "image-batch",
        "classType": "ImageBatch",
        "pythonModule": "nodes",
        "fingerprint": "sha256:1e3c0373917964c4bf0b86ca747f095b91f7bbaacf1c9c1a6195e7ef57a0455b",
        "recipe": "recipe.combine-two-image-batches",
    },
    "core.image-from-batch": {
        "directory": "image-from-batch",
        "classType": "ImageFromBatch",
        "pythonModule": "comfy_extras.nodes_images",
        "fingerprint": "sha256:9b2447b7aee9e6a4c205c6827e21df3812c16eba51e62d0e9e68a71fd25d7266",
        "recipe": "recipe.select-image-batch-segment",
    },
    "core.repeat-image-batch": {
        "directory": "repeat-image-batch",
        "classType": "RepeatImageBatch",
        "pythonModule": "comfy_extras.nodes_images",
        "fingerprint": "sha256:ace759b4101f8e4788880d1b91bdbeba453b4a0b9d9ae4db89b05330333d73f0",
        "recipe": "recipe.repeat-image-mask-sequence",
    },
}

RECIPE_DIRECTORIES = {
    "recipe.invert-canny-control-image": "invert-canny-control-image",
    "recipe.combine-two-image-batches": "combine-two-image-batches",
    "recipe.select-image-batch-segment": "select-image-batch-segment",
    "recipe.repeat-image-mask-sequence": "repeat-image-mask-sequence",
}

EXPECTED_FRAGMENT_NODES = {
    "recipe.invert-canny-control-image": [
        ("ImageInvert", {}),
        ("PreviewImage", {}),
    ],
    "recipe.combine-two-image-batches": [("ImageBatch", {})],
    "recipe.select-image-batch-segment": [
        ("ImageFromBatch", {"batch_index": -1, "length": 1})
    ],
    "recipe.repeat-image-mask-sequence": [
        ("RepeatImageBatch", {"amount": 17}),
        ("ImageToMask", {"channel": "red"}),
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


def article_path(spec: dict[str, str]) -> Path:
    return catalog.CONTENT / "articles" / "core" / spec["directory"] / "manifest.json"


def recipe_path(recipe_id: str) -> Path:
    return catalog.CONTENT / "recipes" / RECIPE_DIRECTORIES[recipe_id] / "recipe.json"


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


def load_official_node_records() -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    with zipfile.ZipFile(WORKFLOW_WHEEL) as archive:
        for member in sorted(archive.namelist()):
            if "/templates/" not in member or not member.endswith(".json"):
                continue
            payload = json.loads(archive.read(member).decode("utf-8"))
            if isinstance(payload, dict):
                records.extend(workflow_node_records(payload, member))
    return records


class ImageBatchContentTests(unittest.TestCase):
    def test_articles_and_fragment_only_recipes_are_structurally_valid(self) -> None:
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
            for source in article["sources"]:
                if "github.com/Comfy-Org/ComfyUI/" in source["url"]:
                    self.assertIn("c2bcbecd82ec5ae66594340b395c24ef0217b238", source["url"])
                if "github.com/Comfy-Org/embedded-docs/" in source["url"]:
                    self.assertIn("1d258cf6e374d60d138a2bfcd273c7e11f750ef9", source["url"])
                if "github.com/Comfy-Org/workflow_templates/" in source["url"]:
                    self.assertIn("cca1ea5ea4560108ecc2f44dee951f41ea433062", source["url"])

            relations = article["relations"]
            targets = relations["related"] + relations["alternatives"]
            if relations["replacedBy"] is not None:
                targets.append(relations["replacedBy"])
            self.assertTrue(set(targets).issubset(article_ids))

            body = (path.parent / article["body"]).read_text(encoding="utf-8")
            semantic_h2 = [
                heading
                for heading in re.findall(r"^## (.+)$", body, flags=re.MULTILINE)
                if heading != "Источники"
            ]
            self.assertGreaterEqual(len(semantic_h2), 10, article_id)
            self.assertNotRegex(
                body.lower(),
                r"важно отметить|в современном мире|революционн|данная нода|является незаменим",
            )

        for recipe_id, directory in RECIPE_DIRECTORIES.items():
            path = catalog.CONTENT / "recipes" / directory / "recipe.json"
            recipe = catalog.load_json(path)
            self.assertEqual([], catalog.json_schema_errors(recipe, recipe_schema))
            catalog.validate_recipe(path, recipe, article_ids, errors)
            self.assertEqual(recipe_id, recipe["recipeId"])
            self.assertNotIn("workflow", recipe)
            self.assertEqual("draft", recipe["editorial"]["state"])
            fragment = catalog.load_json(path.parent / recipe["fragment"]["path"])
            self.assertEqual([], catalog.json_schema_errors(fragment, fragment_schema))
            self.assertEqual(
                EXPECTED_FRAGMENT_NODES[recipe_id],
                [(node["classType"], node["settings"]) for node in fragment["nodes"]],
            )
            for source in recipe["sources"]:
                if "github.com/Comfy-Org/ComfyUI/" in source["url"]:
                    self.assertIn("c2bcbecd82ec5ae66594340b395c24ef0217b238", source["url"])
                if "github.com/Comfy-Org/workflow_templates/" in source["url"]:
                    self.assertIn("cca1ea5ea4560108ecc2f44dee951f41ea433062", source["url"])

        self.assertEqual([], errors)

    def test_research_records_are_honest_and_match_articles(self) -> None:
        schema = catalog.load_json(
            catalog.CONTENT / "schemas" / "article-research.schema.v1.json"
        )
        for article_id, spec in ARTICLE_SPECS.items():
            record_path = (
                catalog.CONTENT / "research" / "reviews" / f"{article_id}.json"
            )
            record = catalog.load_json(record_path)
            self.assertEqual([], catalog.json_schema_errors(record, schema))
            self.assertEqual(article_id, record["articleId"])
            self.assertEqual(spec["classType"], record["node"]["classType"])
            self.assertEqual(spec["pythonModule"], record["node"]["pythonModule"])
            self.assertEqual("fact_checked", record["state"])
            self.assertEqual("automated_assisted", record["reviewMode"])
            self.assertFalse(record["checks"]["exampleExecuted"])
            self.assertNotEqual("human_approved", record["state"])
            self.assertTrue(record["knownGaps"])

    def test_runtime_identity_and_schema_fingerprints_match_full_inventory(self) -> None:
        nodes = catalog.object_info_nodes(catalog.load_json(FULL_INVENTORY))
        for article_id, spec in ARTICLE_SPECS.items():
            article = catalog.load_json(article_path(spec))
            class_type = spec["classType"]
            runtime = nodes[class_type]
            identity = article["runtimeIdentity"]
            self.assertEqual(class_type, identity["classType"], article_id)
            self.assertEqual(runtime["python_module"], identity["pythonModule"])
            self.assertEqual(
                spec["fingerprint"], catalog.schema_fingerprint(class_type, runtime)
            )
            self.assertEqual(spec["fingerprint"], article["editorial"]["schemaHash"])

        self.assertTrue(nodes["ImageBatch"]["deprecated"])
        self.assertEqual("Batch Images (DEPRECATED)", nodes["ImageBatch"]["display_name"])
        self.assertEqual(
            {"default": 0, "min": -16384, "max": 16384},
            nodes["ImageFromBatch"]["input"]["required"]["batch_index"][1],
        )
        self.assertEqual(
            {"default": 1, "min": 1, "max": 4096},
            nodes["RepeatImageBatch"]["input"]["required"]["amount"][1],
        )

    @unittest.skipUnless(SOURCE.exists(), "pinned ComfyUI source checkout is absent")
    def test_articles_track_exact_pinned_implementations(self) -> None:
        nodes_source = (SOURCE / "nodes.py").read_text(encoding="utf-8")
        image_source = (SOURCE / "comfy_extras" / "nodes_images.py").read_text(
            encoding="utf-8"
        )
        replacements = (
            SOURCE / "comfy_extras" / "nodes_replacements.py"
        ).read_text(encoding="utf-8")

        self.assertIn("s = 1.0 - image", nodes_source)
        self.assertIn("torch.cat((image1, image2), dim=0)", nodes_source)
        self.assertIn('new_node_id="BatchImagesNode"', replacements)
        self.assertIn('old_node_id="ImageBatch"', replacements)
        self.assertIn('{"new_id": "images.image0", "old_id": "image1"}', replacements)
        self.assertIn('{"new_id": "images.image1", "old_id": "image2"}', replacements)
        self.assertIn("image.repeat((amount, 1,1,1))", image_source)
        self.assertIn("batch_index += s_in.shape[0]", image_source)
        self.assertIn(
            "batch_index = max(0, min(s_in.shape[0] - 1, batch_index))",
            image_source,
        )
        self.assertIn("length = min(s_in.shape[0] - batch_index, length)", image_source)

    @unittest.skipUnless(WORKFLOW_WHEEL.exists(), "official workflow wheel is absent")
    def test_official_wheel_inventory_and_representative_cases(self) -> None:
        self.assertEqual(
            WORKFLOW_WHEEL_SHA256,
            hashlib.sha256(WORKFLOW_WHEEL.read_bytes()).hexdigest(),
        )
        all_records = load_official_node_records()
        records = [
            record
            for record in all_records
            if record["node"].get("type")
            in {spec["classType"] for spec in ARTICLE_SPECS.values()}
        ]

        by_type = Counter(record["node"]["type"] for record in records)
        root_by_type = Counter(
            record["node"]["type"] for record in records if record["scope"] == "root"
        )
        path_count = {
            class_type: len(
                {record["member"] for record in records if record["node"]["type"] == class_type}
            )
            for class_type in by_type
        }
        mode_count = {
            class_type: Counter(
                record["node"].get("mode", 0)
                for record in all_records
                if record["node"]["type"] == class_type
            )
            for class_type in by_type
        }

        self.assertEqual(
            {
                "ImageInvert": 6,
                "ImageBatch": 5,
                "ImageFromBatch": 40,
                "RepeatImageBatch": 4,
            },
            dict(by_type),
        )
        self.assertEqual(
            {
                "ImageInvert": 1,
                "ImageBatch": 2,
                "ImageFromBatch": 6,
                "RepeatImageBatch": 3,
            },
            dict(root_by_type),
        )
        self.assertEqual(
            {
                "ImageInvert": 6,
                "ImageBatch": 4,
                "ImageFromBatch": 14,
                "RepeatImageBatch": 4,
            },
            path_count,
        )
        self.assertEqual(Counter({0: 39, 4: 1}), mode_count["ImageFromBatch"])
        self.assertEqual(Counter({0: 3, 4: 1}), mode_count["RepeatImageBatch"])

        root_image_from_files = {
            Path(record["member"]).name
            for record in records
            if record["scope"] == "root"
            and record["node"]["type"] == "ImageFromBatch"
        }
        self.assertEqual(
            {
                "api_vidu_video_extension.json",
                "template_seedance2_0_viral_videos_character_swap.json",
                "video_ltx2_canny_to_video.json",
                "video_ltx2_depth_to_video.json",
                "video_wan2_2_14B_s2v.json",
            },
            root_image_from_files,
        )

        negative = [
            record
            for record in records
            if Path(record["member"]).name
            == "video_wan21_scail2_character_replacement.json"
            and record["node"].get("id") == 253
        ]
        self.assertEqual(1, len(negative))
        self.assertEqual([-1, 1], negative[0]["node"]["widgets_values"])

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

        anima_invert = root_node("image_anima_lllite_any_control_to_image.json", 93)
        anima_preview = root_node("image_anima_lllite_any_control_to_image.json", 92)
        self.assertEqual(167, anima_invert["inputs"][0]["link"])
        self.assertEqual([168], anima_invert["outputs"][0]["links"])
        self.assertEqual(168, anima_preview["inputs"][0]["link"])

        product_batch = root_node("templates-product_ad-v2.0.json", 18)
        self.assertEqual([27, 28], [item["link"] for item in product_batch["inputs"]])
        self.assertEqual([24], product_batch["outputs"][0]["links"])
        logotype_batch = root_node("templates-textured_logotype-v2.1.json", 5)
        self.assertEqual([1, 21], [item["link"] for item in logotype_batch["inputs"]])
        self.assertEqual([4], logotype_batch["outputs"][0]["links"])

        vidu_size = root_node("api_vidu_video_extension.json", 10)
        vidu_selector = root_node("api_vidu_video_extension.json", 5)
        vidu_extend = root_node("api_vidu_video_extension.json", 1)
        self.assertEqual("batch_size", vidu_size["outputs"][2]["name"])
        self.assertEqual([5], vidu_size["outputs"][2]["links"])
        self.assertEqual([6, 5], [item["link"] for item in vidu_selector["inputs"]])
        self.assertEqual([0, 1], vidu_selector["widgets_values"])
        self.assertEqual([9], vidu_selector["outputs"][0]["links"])
        self.assertEqual("end_frame", vidu_extend["inputs"][1]["name"])
        self.assertEqual(9, vidu_extend["inputs"][1]["link"])

        active_repeat = [
            record
            for record in records
            if record["node"]["type"] == "RepeatImageBatch"
            and record["node"].get("mode", 0) == 0
        ]
        self.assertEqual(
            {
                ("template_ltx2_3_ic_lora_ingredients.json", 709, (125,)),
                ("video_wan_vace_flf2v.json", 149, (30,)),
                ("video_wan_vace_outpainting.json", 129, (17,)),
            },
            {
                (
                    Path(record["member"]).name,
                    record["node"]["id"],
                    tuple(record["node"]["widgets_values"]),
                )
                for record in active_repeat
            },
        )
        bypassed_repeat = [
            record
            for record in records
            if record["node"]["type"] == "RepeatImageBatch"
            and record["node"].get("mode") == 4
        ]
        self.assertEqual(1, len(bypassed_repeat))
        self.assertEqual("video_wan_vace_14B_ref2v.json", Path(bypassed_repeat[0]["member"]).name)
        self.assertEqual(132, bypassed_repeat[0]["node"]["id"])

        outpaint_repeat = root_node("video_wan_vace_outpainting.json", 129)
        outpaint_to_mask = root_node("video_wan_vace_outpainting.json", 130)
        self.assertEqual([201, 212], [item["link"] for item in outpaint_repeat["inputs"]])
        self.assertEqual([202], outpaint_repeat["outputs"][0]["links"])
        self.assertEqual(202, outpaint_to_mask["inputs"][0]["link"])
        self.assertEqual(["red"], outpaint_to_mask["widgets_values"])


if __name__ == "__main__":
    unittest.main()
