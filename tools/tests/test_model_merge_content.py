from __future__ import annotations

import hashlib
import json
import re
import unittest
import zipfile
from pathlib import Path
from typing import Any, Iterator

from tools import catalog
from tools.tests.model_merge_synthetic_probe import run_probe


ARTICLE_SPECS = {
    "core.model-merge-simple": {
        "directory": "model-merge-simple",
        "classType": "ModelMergeSimple",
        "fingerprint": "sha256:8ec9c5cc40a0396b37c821d9812605d89c5d649c5d09c6f53bd96cb468c1c957",
        "recipe": "recipe.merge-models-75-25",
    },
    "core.model-merge-add": {
        "directory": "model-merge-add",
        "classType": "ModelMergeAdd",
        "fingerprint": "sha256:ca6aefdbb362021ebd52c96f9db30cf62915cca6cba04c9c0e479942ff2b1ce4",
        "recipe": "recipe.transfer-model-delta",
    },
    "core.model-merge-subtract": {
        "directory": "model-merge-subtract",
        "classType": "ModelMergeSubtract",
        "fingerprint": "sha256:b67dae30dde6147a38dd7968335ed934aee8f33cfe6e531cfe283d76cbe177a3",
        "recipe": "recipe.transfer-model-delta",
    },
    "core.model-merge-blocks": {
        "directory": "model-merge-blocks",
        "classType": "ModelMergeBlocks",
        "fingerprint": "sha256:4116c42af2a422cedd6654898a49a0045e189b2a0fe72c6c78e63f9ede9a7dbb",
        "recipe": "recipe.merge-unet-block-groups",
    },
}

RECIPE_DIRECTORIES = {
    "recipe.merge-models-75-25": "merge-models-75-25",
    "recipe.transfer-model-delta": "transfer-model-delta",
    "recipe.merge-unet-block-groups": "merge-unet-block-groups",
}

EXPECTED_FRAGMENT_NODES = {
    "recipe.merge-models-75-25": [
        ("ModelMergeSimple", {"ratio": 0.75}),
    ],
    "recipe.transfer-model-delta": [
        ("ModelMergeSubtract", {"multiplier": 1.0}),
        ("ModelMergeAdd", {}),
    ],
    "recipe.merge-unet-block-groups": [
        ("ModelMergeBlocks", {"input": 1.0, "middle": 0.5, "out": 0.0}),
    ],
}

ROOT = catalog.ROOT
CONTENT = catalog.CONTENT
SOURCE = ROOT / ".comfyui-source-0.32.0"
INVENTORY = CONTENT / "runtime" / "comfyui-0.32.0.object-info.json"
REPLACEMENTS = CONTENT / "runtime" / "comfyui-0.32.0.node-replacements.json"
WORKFLOW_WHEEL = ROOT / ".upstream-cache" / "comfyui_workflow_templates_json-0.1.42-py3-none-any.whl"
WORKFLOW_SHA256 = "242982d65e1c51ca03d892bc1009bb6843f457e7dfc0c20afe6438770b7a14a3"
DOCS_WHEEL = ROOT / ".upstream-cache" / "comfyui_embedded_docs-0.5.9-py3-none-any.whl"
DOCS_SHA256 = "30afae432a71c96aa59421d0f37388c66ff6572b8cbeee8ff045e4d5f84f896c"
DOC_HASHES = {
    ("ModelMergeSimple", "en"): "c4c5150529a46a5a32a162157df1794b6076d271d3851130ec685e6aad8cbee2",
    ("ModelMergeSimple", "ru"): "9d15fb2bbf45889926d6c68265fb7bd8b2c2ee689854aad1cbb69581b8934b08",
    ("ModelMergeAdd", "en"): "b9f04d63ee04fccf5bad3fd80be2b04c9eecc56438539e31560caa1519cdfcc9",
    ("ModelMergeAdd", "ru"): "431839f9b6a823657c37888fa6e3cc56d06a134ee75b225af94ba127ffb9d8c2",
    ("ModelMergeSubtract", "en"): "80ca57006fb62340697643724b610144497cbc9b0220d995db2513537a10c953",
    ("ModelMergeSubtract", "ru"): "922f7d9443c2aefa1eeba44fed15ab92c82516b186aa5859ea3f0fef3fcf94ee",
    ("ModelMergeBlocks", "en"): "5cfaab02307c2695c9a4c831b8d5dadb2f1875bdf5b14995f0a6cf7dcf8294ad",
    ("ModelMergeBlocks", "ru"): "9cb5502b14726648e5ea9d427bd747083a5bd66c8a916e035fad768c4ccb0886",
}
TARGET_TYPES = {spec["classType"] for spec in ARTICLE_SPECS.values()}


def all_article_ids() -> set[str]:
    ids: set[str] = set()
    for path in (CONTENT / "articles").rglob("manifest.json"):
        payload = catalog.load_json(path)
        if isinstance(payload, dict) and isinstance(payload.get("articleId"), str):
            ids.add(payload["articleId"])
    return ids


def graph_nodes(payload: dict[str, Any]) -> Iterator[dict[str, Any]]:
    for node in payload.get("nodes", []):
        if isinstance(node, dict):
            yield node
    definitions = payload.get("definitions")
    subgraphs = definitions.get("subgraphs", []) if isinstance(definitions, dict) else []
    for subgraph in subgraphs:
        if not isinstance(subgraph, dict):
            continue
        for node in subgraph.get("nodes", []):
            if isinstance(node, dict):
                yield node


class ModelMergeContentTests(unittest.TestCase):
    def test_articles_recipes_ledgers_and_editorial_contract(self) -> None:
        article_schema = catalog.load_json(CONTENT / "schemas" / "article.schema.v1.json")
        recipe_schema = catalog.load_json(CONTENT / "schemas" / "recipe.schema.v1.json")
        fragment_schema = catalog.load_json(CONTENT / "schemas" / "recipe-fragment.schema.v1.json")
        research_schema = catalog.load_json(CONTENT / "schemas" / "article-research.schema.v1.json")
        article_ids = all_article_ids()
        article_errors: list[str] = []

        for article_id, spec in ARTICLE_SPECS.items():
            path = CONTENT / "articles" / "core" / spec["directory"] / "manifest.json"
            article = catalog.load_json(path)
            self.assertEqual([], catalog.json_schema_errors(article, article_schema))
            catalog.validate_article(path, article, article_errors)
            self.assertEqual(article_id, article["articleId"])
            self.assertEqual("draft", article["status"])
            self.assertEqual("in_review", article["editorial"]["state"])
            self.assertFalse(article["experimental"])
            self.assertEqual(spec["fingerprint"], article["editorial"]["schemaHash"])
            self.assertIn(spec["recipe"], [asset["id"] for asset in article["assets"]])
            relation_targets = list(article["relations"]["related"]) + list(article["relations"]["alternatives"])
            if article["relations"]["replacedBy"] is not None:
                relation_targets.append(article["relations"]["replacedBy"])
            self.assertTrue(set(relation_targets).issubset(article_ids))

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

            ledger = catalog.load_json(CONTENT / "research" / "reviews" / f"{article_id}.json")
            self.assertEqual([], catalog.json_schema_errors(ledger, research_schema))
            self.assertEqual("fact_checked", ledger["state"])
            self.assertEqual("automated_assisted", ledger["reviewMode"])
            self.assertFalse(ledger["checks"]["exampleExecuted"])
            self.assertTrue(ledger["checks"]["factsRecheckedAfterEditing"])
            self.assertTrue(any("Редактор пока" in gap for gap in ledger["knownGaps"]))

        self.assertEqual([], article_errors)

        inventory = catalog.load_json(INVENTORY)
        recipe_errors: list[str] = []
        for recipe_id, directory in RECIPE_DIRECTORIES.items():
            path = CONTENT / "recipes" / directory / "recipe.json"
            recipe = catalog.load_json(path)
            self.assertEqual([], catalog.json_schema_errors(recipe, recipe_schema))
            catalog.validate_recipe(path, recipe, article_ids, recipe_errors)
            self.assertEqual(recipe_id, recipe["recipeId"])
            self.assertEqual("in_review", recipe["editorial"]["state"])
            self.assertNotIn("workflow", recipe)
            body = (path.parent / recipe["body"]).read_text(encoding="utf-8")
            self.assertIn("Редактор пока не проверил материал вручную.", body)

            fragment_path = path.parent / recipe["fragment"]["path"]
            fragment = catalog.load_json(fragment_path)
            self.assertEqual([], catalog.json_schema_errors(fragment, fragment_schema))
            catalog.validate_fragment(fragment_path, fragment, recipe_errors)
            actual = [(node["classType"], node["settings"]) for node in fragment["nodes"]]
            self.assertEqual(EXPECTED_FRAGMENT_NODES[recipe_id], actual)
            self.assertTrue(all(node["classType"] in inventory for node in fragment["nodes"]))
            refs = {node["ref"] for node in fragment["nodes"]}
            self.assertTrue(all(item["to"] in refs for item in fragment["externalInputs"]))
            self.assertTrue(all(link["from"] in refs and link["to"] in refs for link in fragment["connections"]))

        self.assertEqual([], recipe_errors)

    def test_runtime_contracts_fingerprints_and_replacements(self) -> None:
        inventory = catalog.load_json(INVENTORY)
        for spec in ARTICLE_SPECS.values():
            definition = inventory[spec["classType"]]
            self.assertEqual("comfy_extras.nodes_model_merging", definition["python_module"])
            self.assertEqual("model/merging", definition["category"])
            self.assertEqual(["MODEL"], definition["output"])
            self.assertEqual(["MODEL"], definition["output_name"])
            self.assertEqual(spec["fingerprint"], catalog.schema_fingerprint(spec["classType"], definition))
            for flag in ("deprecated", "experimental", "dev_only", "api_node", "output_node"):
                self.assertFalse(definition.get(flag, False), (spec["classType"], flag))

        simple = inventory["ModelMergeSimple"]
        self.assertEqual(["model1", "model2", "ratio"], simple["input_order"]["required"])
        self.assertEqual(
            {"default": 1.0, "min": 0.0, "max": 1.0, "step": 0.01},
            simple["input"]["required"]["ratio"][1],
        )
        add = inventory["ModelMergeAdd"]
        self.assertEqual(["model1", "model2"], add["input_order"]["required"])
        subtract = inventory["ModelMergeSubtract"]
        self.assertEqual(["model1", "model2", "multiplier"], subtract["input_order"]["required"])
        self.assertEqual(
            {"default": 1.0, "min": -10.0, "max": 10.0, "step": 0.01},
            subtract["input"]["required"]["multiplier"][1],
        )
        blocks = inventory["ModelMergeBlocks"]
        self.assertEqual(["model1", "model2", "input", "middle", "out"], blocks["input_order"]["required"])
        for name in ("input", "middle", "out"):
            self.assertEqual(
                {"default": 1.0, "min": 0.0, "max": 1.0, "step": 0.01},
                blocks["input"]["required"][name][1],
            )

        replacements = catalog.load_json(REPLACEMENTS)
        serialized = json.dumps(replacements, ensure_ascii=False)
        for class_type in TARGET_TYPES:
            self.assertNotIn(class_type, replacements)
            self.assertNotIn(f'"new_node_id": "{class_type}"', serialized)

    def test_exact_source_tensor_probe_and_registration(self) -> None:
        result = run_probe(SOURCE)
        self.assertEqual(8.0, result["simple"]["ratioQuarter"])
        self.assertEqual("ratio*model1+(1-ratio)*model2", result["simple"]["formula"])
        self.assertTrue(result["simple"]["model2OnlyKeyIgnored"])
        self.assertTrue(result["simple"]["nonDiffusionUnchanged"])
        self.assertEqual(12.0, result["add"]["result"])
        self.assertEqual(-16.0, result["subtract"]["multiplierTwo"])
        self.assertEqual(8.0, result["subtract"]["multiplierMinusOne"])
        self.assertEqual("multiplier*(model1-model2)", result["subtract"]["formula"])
        self.assertEqual(
            {"input": 2.0, "middle": 12.0, "out": 30.0, "unmatchedDefault": 8.0, "unmatchedReorderedKwargs": 24.0},
            result["blocks"],
        )
        self.assertEqual([0.5, 1.0], result["shapeMismatch"]["model1AfterRatioScale"])

        source = (SOURCE / "comfy_extras" / "nodes_model_merging.py").read_text(encoding="utf-8")
        patcher = (SOURCE / "comfy" / "model_patcher.py").read_text(encoding="utf-8")
        lora = (SOURCE / "comfy" / "lora.py").read_text(encoding="utf-8")
        for class_name in ("ModelMergeSimple", "ModelSubtract", "ModelAdd", "ModelMergeBlocks"):
            self.assertIn(f"class {class_name}", source)
        self.assertIn('"ModelMergeSubtract": ModelSubtract', source)
        self.assertIn('"ModelMergeAdd": ModelAdd', source)
        self.assertIn('kp = model2.get_key_patches("diffusion_model.")', source)
        self.assertIn("m.add_patches({k: kp[k]}, - multiplier, multiplier)", source)
        self.assertIn("default_ratio = next(iter(kwargs.values()))", source)
        self.assertIn("if k_unet.startswith(arg) and last_arg_size < len(arg):", source)
        self.assertIn("if key in model_sd:", patcher)
        self.assertIn("current_patches.append((strength_patch, patches[k], strength_model, offset, function))", patcher)
        self.assertIn("weight *= strength_model", lora)
        self.assertIn("WARNING SHAPE MISMATCH", lora)

    def test_pinned_embedded_docs_hashes(self) -> None:
        self.assertEqual(DOCS_SHA256, hashlib.sha256(DOCS_WHEEL.read_bytes()).hexdigest())
        with zipfile.ZipFile(DOCS_WHEEL) as archive:
            names = set(archive.namelist())
            for (class_type, locale), expected_hash in DOC_HASHES.items():
                path = f"comfyui_embedded_docs/docs/{class_type}/{locale}.md"
                self.assertIn(path, names)
                self.assertEqual(expected_hash, hashlib.sha256(archive.read(path)).hexdigest())
            subtract_docs = archive.read("comfyui_embedded_docs/docs/ModelMergeSubtract/en.md").decode("utf-8")
            self.assertIn("based on a specified multiplier", subtract_docs)
            self.assertNotIn("multiplier * (model1 - model2)", subtract_docs)
            blocks_docs = archive.read("comfyui_embedded_docs/docs/ModelMergeBlocks/en.md").decode("utf-8")
            self.assertIn("input layer", blocks_docs)
            self.assertNotIn("startswith", blocks_docs)

    def test_workflow_wheel_integrity_and_exhaustive_absence(self) -> None:
        self.assertEqual(WORKFLOW_SHA256, hashlib.sha256(WORKFLOW_WHEEL.read_bytes()).hexdigest())
        json_members = 0
        root_graphs = 0
        subgraphs = 0
        found: list[tuple[str, str]] = []
        with zipfile.ZipFile(WORKFLOW_WHEEL) as archive:
            for member in archive.namelist():
                if not member.endswith(".json"):
                    continue
                json_members += 1
                payload = json.loads(archive.read(member))
                if isinstance(payload, dict) and isinstance(payload.get("nodes"), list):
                    root_graphs += 1
                if not isinstance(payload, dict):
                    continue
                definitions = payload.get("definitions")
                if isinstance(definitions, dict):
                    subgraphs += len(definitions.get("subgraphs", []))
                for node in graph_nodes(payload):
                    if node.get("type") in TARGET_TYPES:
                        found.append((member, node["type"]))
        self.assertEqual(512, json_members)
        self.assertEqual(496, root_graphs)
        self.assertEqual(272, subgraphs)
        self.assertEqual([], found)


if __name__ == "__main__":
    unittest.main()
