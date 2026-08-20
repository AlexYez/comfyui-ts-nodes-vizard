from __future__ import annotations

import base64
import csv
import hashlib
import io
import json
import re
import unittest
import zipfile
from pathlib import Path
from typing import Any

from tools import catalog
from tools.tests.model_merge_specific_synthetic_probe import run_probe


SD1_RATIOS = (
    ["time_embed.", "label_emb."]
    + [f"input_blocks.{index}." for index in range(12)]
    + [f"middle_block.{index}." for index in range(3)]
    + [f"output_blocks.{index}." for index in range(12)]
    + ["out."]
)
SDXL_RATIOS = (
    ["time_embed.", "label_emb."]
    + [f"input_blocks.{index}" for index in range(9)]
    + [f"middle_block.{index}" for index in range(3)]
    + [f"output_blocks.{index}" for index in range(9)]
    + ["out."]
)
SD3_RATIOS = (
    ["pos_embed.", "x_embedder.", "context_embedder.", "y_embedder.", "t_embedder."]
    + [f"joint_blocks.{index}." for index in range(24)]
    + ["final_layer."]
)

ARTICLE_SPECS = {
    "core.model-merge-sd1": {
        "directory": "model-merge-sd1",
        "classType": "ModelMergeSD1",
        "ratios": SD1_RATIOS,
        "fingerprint": "sha256:219085f7923d0d2c82dc4910e651e375b11ee52bd53ac098fe81a373fa5faf9a",
        "recipe": "recipe.merge-sd1-block-map",
    },
    "core.model-merge-sd2": {
        "directory": "model-merge-sd2",
        "classType": "ModelMergeSD2",
        "ratios": SD1_RATIOS,
        "fingerprint": "sha256:539c4b286dd07aac5cf4e77a0246c5a49cbefd46967fbd270795fa4747fda542",
        "recipe": "recipe.merge-sd2-block-map",
    },
    "core.model-merge-sdxl": {
        "directory": "model-merge-sdxl",
        "classType": "ModelMergeSDXL",
        "ratios": SDXL_RATIOS,
        "fingerprint": "sha256:861aa981443c8542b0b55aad8ff003d07523c7cbbd2ab42bbd5894bafdfddac1",
        "recipe": "recipe.merge-sdxl-block-map",
    },
    "core.model-merge-sd3-2b": {
        "directory": "model-merge-sd3-2b",
        "classType": "ModelMergeSD3_2B",
        "ratios": SD3_RATIOS,
        "fingerprint": "sha256:d67eabcbe78499f3a74d93ee1b41d19b58b83e85e32f862f30f19a7b78a0a5cd",
        "recipe": "recipe.merge-sd3-2b-block-map",
    },
}

RECIPE_SPECS = {
    "recipe.merge-sd1-block-map": {
        "directory": "merge-sd1-block-map",
        "classType": "ModelMergeSD1",
        "settings": {
            "input_blocks.1.": 0.75,
            "middle_block.1.": 0.5,
            "output_blocks.11.": 0.0,
        },
    },
    "recipe.merge-sd2-block-map": {
        "directory": "merge-sd2-block-map",
        "classType": "ModelMergeSD2",
        "settings": {"time_embed.": 1.0, "output_blocks.11.": 0.25},
    },
    "recipe.merge-sdxl-block-map": {
        "directory": "merge-sdxl-block-map",
        "classType": "ModelMergeSDXL",
        "settings": {
            "middle_block.0": 0.5,
            "middle_block.1": 0.5,
            "middle_block.2": 0.5,
        },
    },
    "recipe.merge-sd3-2b-block-map": {
        "directory": "merge-sd3-2b-block-map",
        "classType": "ModelMergeSD3_2B",
        "settings": {"joint_blocks.23.": 0.8, "final_layer.": 0.1},
    },
}

DOC_HASHES = {
    ("ModelMergeSD1", "en"): "7472a4cf5f32aec1823d072c236564b8172e62ddf4b3fd8bd3e5cf0ac8e618c9",
    ("ModelMergeSD1", "ru"): "804f3fb03dd5eb30dcf6e2374f80eb7a0484ee64c5f735e3af24e48974c3f0ec",
    ("ModelMergeSDXL", "en"): "683ef9c22f64d4600b67ce318fb8a1a0970278709cb84ca2aececcb09f3155c2",
    ("ModelMergeSDXL", "ru"): "e777b01a1254c4b94cb05b9ecd7d1ffb75dbcb01c903ee0c00865ce6995951ff",
    ("ModelMergeSD3_2B", "en"): "d25902389132ac42893fa8584004fb5237a675efff355ed68a603c09cb0c0e23",
    ("ModelMergeSD3_2B", "ru"): "fc282b779d823225a0ecdd0ca0b6c64cde9d2b1c82e773588dc3fe6a2ac461be",
}

SOURCE = catalog.ROOT / ".comfyui-source-0.32.0"
INVENTORY = catalog.CONTENT / "runtime" / "comfyui-0.32.0.object-info.json"
REPLACEMENTS = catalog.CONTENT / "runtime" / "comfyui-0.32.0.node-replacements.json"
WORKFLOW_WHEEL = catalog.ROOT / ".upstream-cache" / "comfyui_workflow_templates_json-0.1.42-py3-none-any.whl"
WORKFLOW_SHA256 = "242982d65e1c51ca03d892bc1009bb6843f457e7dfc0c20afe6438770b7a14a3"
DOCS_WHEEL = catalog.ROOT / ".upstream-cache" / "comfyui_embedded_docs-0.5.9-py3-none-any.whl"
DOCS_SHA256 = "30afae432a71c96aa59421d0f37388c66ff6572b8cbeee8ff045e4d5f84f896c"
TARGET_TYPES = {spec["classType"] for spec in ARTICLE_SPECS.values()}


def all_article_ids() -> set[str]:
    result: set[str] = set()
    for path in (catalog.CONTENT / "articles").rglob("manifest.json"):
        payload = catalog.load_json(path)
        if isinstance(payload, dict) and isinstance(payload.get("articleId"), str):
            result.add(payload["articleId"])
    return result


class ModelMergeSpecificContentTests(unittest.TestCase):
    def test_batch_ids_and_runtime_identities_are_unique(self) -> None:
        article_id_counts: dict[str, int] = {}
        identity_counts: dict[tuple[str, str, str], int] = {}
        for path in (catalog.CONTENT / "articles").rglob("manifest.json"):
            article = catalog.load_json(path)
            if not isinstance(article, dict):
                continue
            article_id = article.get("articleId")
            if isinstance(article_id, str):
                article_id_counts[article_id] = article_id_counts.get(article_id, 0) + 1
            identity = article.get("runtimeIdentity")
            if not isinstance(identity, dict):
                continue
            key = (
                str(identity.get("packageId")),
                str(identity.get("pythonModule")),
                str(identity.get("classType")),
            )
            identity_counts[key] = identity_counts.get(key, 0) + 1

        recipe_id_counts: dict[str, int] = {}
        for path in (catalog.CONTENT / "recipes").rglob("recipe.json"):
            recipe = catalog.load_json(path)
            if isinstance(recipe, dict) and isinstance(recipe.get("recipeId"), str):
                recipe_id = recipe["recipeId"]
                recipe_id_counts[recipe_id] = recipe_id_counts.get(recipe_id, 0) + 1

        for article_id, spec in ARTICLE_SPECS.items():
            self.assertEqual(1, article_id_counts.get(article_id), article_id)
            identity = (
                "comfy-core",
                "comfy_extras.nodes_model_merging_model_specific",
                spec["classType"],
            )
            self.assertEqual(1, identity_counts.get(identity), identity)
            self.assertEqual(1, recipe_id_counts.get(spec["recipe"]), spec["recipe"])

    def test_articles_recipes_ledgers_and_natural_russian(self) -> None:
        article_schema = catalog.load_json(catalog.CONTENT / "schemas" / "article.schema.v1.json")
        recipe_schema = catalog.load_json(catalog.CONTENT / "schemas" / "recipe.schema.v1.json")
        fragment_schema = catalog.load_json(catalog.CONTENT / "schemas" / "recipe-fragment.schema.v1.json")
        research_schema = catalog.load_json(catalog.CONTENT / "schemas" / "article-research.schema.v1.json")
        article_ids = all_article_ids()
        article_errors: list[str] = []

        for article_id, spec in ARTICLE_SPECS.items():
            path = catalog.CONTENT / "articles" / "core" / spec["directory"] / "manifest.json"
            article = catalog.load_json(path)
            self.assertEqual([], catalog.json_schema_errors(article, article_schema))
            catalog.validate_article(path, article, article_errors)
            self.assertEqual(article_id, article["articleId"])
            self.assertEqual("draft", article["status"])
            self.assertEqual("in_review", article["editorial"]["state"])
            self.assertFalse(article["experimental"])
            self.assertEqual(spec["fingerprint"], article["editorial"]["schemaHash"])
            self.assertIn(spec["recipe"], [asset["id"] for asset in article["assets"]])
            related_ids = (
                list(article["relations"]["related"])
                + list(article["relations"]["alternatives"])
                + ([article["relations"]["replacedBy"]] if article["relations"]["replacedBy"] else [])
            )
            self.assertTrue(set(related_ids).issubset(article_ids))

            body = (path.parent / article["body"]).read_text(encoding="utf-8")
            self.assertEqual(10, len(re.findall(r"^## .+$", body, flags=re.MULTILINE)), article_id)
            self.assertIn("Редактор пока не проверил материал вручную.", body)
            self.assertNotIn("\ufffd", body)
            self.assertNotRegex(
                body.lower(),
                r"важно отметить|стоит отметить|в современном мире|революционн|"
                r"данная нода|давайте разбер|подводя итог|мощный инструмент|"
                r"не просто .{0,80}, а",
            )

            ledger_path = catalog.CONTENT / "research" / "reviews" / f"{article_id}.json"
            ledger = catalog.load_json(ledger_path)
            self.assertEqual([], catalog.json_schema_errors(ledger, research_schema))
            self.assertEqual("fact_checked", ledger["state"])
            self.assertEqual("automated_assisted", ledger["reviewMode"])
            self.assertFalse(ledger["checks"]["exampleExecuted"])
            self.assertTrue(ledger["checks"]["factsRecheckedAfterEditing"])
            self.assertTrue(
                any("Редактор пока не проверил материал вручную." in gap for gap in ledger["knownGaps"])
            )
            self.assertNotIn("approved", json.dumps(ledger, ensure_ascii=False).lower())

        self.assertEqual([], article_errors)

        inventory = catalog.load_json(INVENTORY)
        recipe_errors: list[str] = []
        for recipe_id, spec in RECIPE_SPECS.items():
            path = catalog.CONTENT / "recipes" / spec["directory"] / "recipe.json"
            recipe = catalog.load_json(path)
            self.assertEqual([], catalog.json_schema_errors(recipe, recipe_schema))
            catalog.validate_recipe(path, recipe, article_ids, recipe_errors)
            self.assertEqual(recipe_id, recipe["recipeId"])
            self.assertEqual("draft", recipe["editorial"]["state"])
            self.assertNotIn("workflow", recipe)
            source_urls = {source["url"] for source in recipe["sources"]}
            self.assertTrue(any("/comfy/lora.py#L438-L501" in url for url in source_urls))
            self.assertTrue(any("/workflow_templates/tree/" in url for url in source_urls))
            if recipe_id == "recipe.merge-sd2-block-map":
                self.assertTrue(any("/nodes_model_merging.py#L138-L168" in url for url in source_urls))
                self.assertTrue(any("/embedded-docs/tree/" in url for url in source_urls))
            body = (path.parent / recipe["body"]).read_text(encoding="utf-8")
            self.assertIn("Редактор пока не проверил материал вручную.", body)

            fragment_path = path.parent / recipe["fragment"]["path"]
            fragment = catalog.load_json(fragment_path)
            self.assertEqual([], catalog.json_schema_errors(fragment, fragment_schema))
            catalog.validate_fragment(fragment_path, fragment, recipe_errors)
            self.assertEqual(1, len(fragment["nodes"]))
            node = fragment["nodes"][0]
            self.assertEqual(spec["classType"], node["classType"])
            self.assertEqual(spec["settings"], node["settings"])
            self.assertEqual([], fragment["connections"])
            self.assertEqual({"model1", "model2"}, {item["input"] for item in fragment["externalInputs"]})
            valid_settings = set(inventory[spec["classType"]]["input_order"]["required"][2:])
            self.assertTrue(set(node["settings"]).issubset(valid_settings))

        self.assertEqual([], recipe_errors)

    def test_runtime_contracts_fingerprints_flags_and_replacements(self) -> None:
        inventory = catalog.load_json(INVENTORY)
        ratio_spec = ["FLOAT", {"default": 1.0, "min": 0.0, "max": 1.0, "step": 0.01}]
        for spec in ARTICLE_SPECS.values():
            class_type = spec["classType"]
            definition = inventory[class_type]
            self.assertEqual(
                "comfy_extras.nodes_model_merging_model_specific",
                definition["python_module"],
            )
            self.assertEqual("model/merging/model specific", definition["category"])
            self.assertEqual(["model1", "model2", *spec["ratios"]], definition["input_order"]["required"])
            self.assertEqual(["MODEL"], definition["output"])
            self.assertEqual(["MODEL"], definition["output_name"])
            for ratio_name in spec["ratios"]:
                self.assertEqual(ratio_spec, definition["input"]["required"][ratio_name])
            for flag in ("deprecated", "experimental", "dev_only", "api_node", "output_node"):
                self.assertFalse(definition.get(flag, False), (class_type, flag))
            self.assertEqual(spec["fingerprint"], catalog.schema_fingerprint(class_type, definition))

        self.assertEqual(
            inventory["ModelMergeSD1"]["input"],
            inventory["ModelMergeSD2"]["input"],
        )
        self.assertEqual(30, len(SD1_RATIOS))
        self.assertEqual(24, len(SDXL_RATIOS))
        self.assertEqual(30, len(SD3_RATIOS))
        self.assertNotIn("input_blocks.0.", SDXL_RATIOS)
        self.assertIn("input_blocks.0", SDXL_RATIOS)

        replacements = catalog.load_json(REPLACEMENTS)
        serialized = json.dumps(replacements, ensure_ascii=False)
        for class_type in TARGET_TYPES:
            self.assertNotIn(class_type, replacements)
            self.assertNotIn(class_type, serialized)

    def test_pinned_source_registration_and_embedded_docs(self) -> None:
        self.assertEqual(
            "c2bcbecd82ec5ae66594340b395c24ef0217b238",
            (SOURCE / ".git" / "HEAD").read_text(encoding="ascii").strip(),
        )
        specific = (SOURCE / "comfy_extras" / "nodes_model_merging_model_specific.py").read_text(encoding="utf-8")
        common = (SOURCE / "comfy_extras" / "nodes_model_merging.py").read_text(encoding="utf-8")
        patcher = (SOURCE / "comfy" / "model_patcher.py").read_text(encoding="utf-8")
        weight_math = (SOURCE / "comfy" / "lora.py").read_text(encoding="utf-8")
        self.assertIn('"ModelMergeSD1": ModelMergeSD1', specific)
        self.assertIn('"ModelMergeSD2": ModelMergeSD1, #SD1 and SD2 have the same blocks', specific)
        self.assertIn('"ModelMergeSDXL": ModelMergeSDXL', specific)
        self.assertIn('"ModelMergeSD3_2B": ModelMergeSD3_2B', specific)
        self.assertIn('arg_dict["input_blocks.{}.".format(i)]', specific)
        self.assertIn('arg_dict["input_blocks.{}".format(i)]', specific)
        self.assertIn('arg_dict["joint_blocks.{}.".format(i)]', specific)
        self.assertIn("default_ratio = next(iter(kwargs.values()))", common)
        self.assertIn("if k_unet.startswith(arg) and last_arg_size < len(arg):", common)
        self.assertIn("m.add_patches({k: kp[k]}, 1.0 - ratio, ratio)", common)
        self.assertIn("if key in model_sd:", patcher)
        self.assertIn("WARNING SHAPE MISMATCH", weight_math)

        self.assertEqual(DOCS_SHA256, hashlib.sha256(DOCS_WHEEL.read_bytes()).hexdigest())
        with zipfile.ZipFile(DOCS_WHEEL) as archive:
            self.assertIsNone(archive.testzip())
            names = set(archive.namelist())
            for (class_type, locale), expected_hash in DOC_HASHES.items():
                path = f"comfyui_embedded_docs/docs/{class_type}/{locale}.md"
                self.assertIn(path, names)
                self.assertEqual(expected_hash, hashlib.sha256(archive.read(path)).hexdigest())
            self.assertFalse(any("/ModelMergeSD2/" in name for name in names))
            self.assertFalse(any(b"ModelMergeSD2" in archive.read(name) for name in names if not name.endswith("/")))
            for class_type in ("ModelMergeSD1", "ModelMergeSDXL", "ModelMergeSD3_2B"):
                locales = {
                    Path(name).stem
                    for name in names
                    if f"/docs/{class_type}/" in name and name.endswith(".md")
                }
                self.assertEqual(
                    {"ar", "en", "es", "fa", "fr", "ja", "ko", "pt-BR", "ru", "tr", "zh-TW", "zh"},
                    locales,
                )

    def test_workflow_wheel_integrity_and_exhaustive_zero_census(self) -> None:
        self.assertEqual(WORKFLOW_SHA256, hashlib.sha256(WORKFLOW_WHEEL.read_bytes()).hexdigest())
        json_members = 0
        root_graphs = 0
        root_nodes = 0
        subgraphs = 0
        subgraph_nodes = 0
        matches: list[tuple[str, str]] = []
        with zipfile.ZipFile(WORKFLOW_WHEEL) as archive:
            self.assertIsNone(archive.testzip())
            self.assertEqual(517, len(archive.namelist()))
            record_name = next(name for name in archive.namelist() if name.endswith(".dist-info/RECORD"))
            rows = list(csv.reader(io.StringIO(archive.read(record_name).decode("utf-8"))))
            self.assertEqual(517, len(rows))
            verified = 0
            for name, digest, size in rows:
                if not digest:
                    self.assertEqual(record_name, name)
                    continue
                algorithm, encoded = digest.split("=", 1)
                self.assertEqual("sha256", algorithm)
                expected = base64.urlsafe_b64decode(encoded + "=" * (-len(encoded) % 4))
                data = archive.read(name)
                self.assertEqual(expected, hashlib.sha256(data).digest())
                self.assertEqual(int(size), len(data))
                verified += 1
            self.assertEqual(516, verified)

            for name in archive.namelist():
                data = archive.read(name)
                for class_type in TARGET_TYPES:
                    self.assertNotIn(class_type.encode(), data, (name, class_type))
                    self.assertNotIn(class_type.lower().encode(), data.lower(), (name, class_type))
                if not name.endswith(".json") or "/templates/" not in name:
                    continue
                json_members += 1
                payload = json.loads(data)
                if not isinstance(payload, dict) or not isinstance(payload.get("nodes"), list):
                    continue
                root_graphs += 1
                root_nodes += len(payload["nodes"])
                for node in payload["nodes"]:
                    if isinstance(node, dict) and node.get("type") in TARGET_TYPES:
                        matches.append((name, node["type"]))
                definitions = payload.get("definitions")
                nested = definitions.get("subgraphs", []) if isinstance(definitions, dict) else []
                subgraphs += len(nested)
                for subgraph in nested:
                    if not isinstance(subgraph, dict):
                        continue
                    subgraph_nodes += len(subgraph.get("nodes", []))
                    for node in subgraph.get("nodes", []):
                        if isinstance(node, dict) and node.get("type") in TARGET_TYPES:
                            matches.append((name, node["type"]))

        self.assertEqual((512, 496, 272), (json_members, root_graphs, subgraphs))
        self.assertEqual((4083, 4037, 8120), (root_nodes, subgraph_nodes, root_nodes + subgraph_nodes))
        self.assertEqual([], matches)

    def test_exact_source_probe_ratio_prefix_missing_keys_and_shape_mismatch(self) -> None:
        with self.assertLogs(level="WARNING") as captured:
            result = run_probe(SOURCE)
        self.assertTrue(any("SHAPE MISMATCH" in message for message in captured.output))
        self.assertEqual("ratio*model1+(1-ratio)*model2", result["formula"])
        self.assertAlmostEqual(13.0, result["sd1"]["inputBlock1"])
        self.assertAlmostEqual(33.0, result["sd1"]["inputBlock10"])
        self.assertAlmostEqual(93.0, result["sd1"]["unmatchedUsesTimeEmbed"])
        self.assertEqual(14.0, result["sd1"]["model1OnlyUnchanged"])
        self.assertTrue(result["sd1"]["model2OnlyIgnored"])
        self.assertAlmostEqual(24.6, result["sdxl"]["inputBlock8"], places=5)
        self.assertAlmostEqual(
            22.75,
            result["sdxl"]["incompatibleInputBlock10UsesBlock1"],
            places=5,
        )
        self.assertAlmostEqual(32.0, result["sdxl"]["unmatchedUsesTimeEmbed"])
        self.assertAlmostEqual(11.2, result["sd3"]["jointBlock23"], places=5)
        self.assertAlmostEqual(54.6, result["sd3"]["finalLayer"], places=5)
        self.assertAlmostEqual(58.4, result["sd3"]["unmatchedUsesPosEmbed"], places=5)
        self.assertEqual([0.5, 1.0], result["shapeMismatch"])
        self.assertEqual([2.0, 4.0], result["shapeMismatchRatioOne"])
        self.assertAlmostEqual(91.0, result["reorderedKwargsUnmatchedUsesFirstValue"])


if __name__ == "__main__":
    unittest.main()
