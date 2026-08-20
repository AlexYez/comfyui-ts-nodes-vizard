from __future__ import annotations

import hashlib
import json
import re
import unittest
import zipfile
from typing import Any, Iterator

from tools import catalog
from tools.tests.model_specific_merge_synthetic_probe import run_probe


SPECS = {
    "core.model-merge-flux1": ("model-merge-flux1", "ModelMergeFlux1", "sha256:f69c9f9c98fd776d67fa0085209fe817b6bb5bc2a92340dfeff2e197d45f637f", "recipe.merge-flux1-first-double-block"),
    "core.model-merge-sd35-large": ("model-merge-sd35-large", "ModelMergeSD35_Large", "sha256:7c6946424139ae4703ccacff5ae2af2c97e3cff0bad250cfd844d10b1f6f63d7", "recipe.merge-sd35-first-joint-block"),
    "core.model-merge-wan21": ("model-merge-wan21", "ModelMergeWAN2_1", "sha256:4d43f654c2236fe50d8307354802058d6b33b78ba1271213e7fb79d45714b61a", "recipe.merge-wan-first-block"),
    "core.model-merge-ltxv": ("model-merge-ltxv", "ModelMergeLTXV", "sha256:1e517ca37ca62c406d0cfa5564861b32cd0e1fbece38353def90c431d603e1e7", "recipe.merge-ltxv-first-transformer-block"),
    "core.model-merge-auraflow": ("model-merge-auraflow", "ModelMergeAuraflow", "sha256:5f71f343a4e76d21e23661d87aea14f3c246a8bc52467bb4627fb2d1f3cdbf34", "recipe.merge-auraflow-first-layer"),
    "core.model-merge-mochi-preview": ("model-merge-mochi-preview", "ModelMergeMochiPreview", "sha256:709939b3c7fb550c05f8258015583a75c18a87235a904e1c8f8cf6fc94103eaa", "recipe.merge-mochi-first-block"),
    "core.model-merge-cosmos7b": ("model-merge-cosmos7b", "ModelMergeCosmos7B", "sha256:5b869250c5ca246fdc15be751bb974afab6b4b5e04f5ab09e7ec1a7184717c03", "recipe.merge-cosmos7b-first-block"),
    "core.model-merge-cosmos14b": ("model-merge-cosmos14b", "ModelMergeCosmos14B", "sha256:80074ffefa20b7153b33d643062af09fc39ec829ab329a48cd4ebffe05c6d482", "recipe.merge-cosmos14b-first-block"),
    "core.model-merge-cosmos-predict2-2b": ("model-merge-cosmos-predict2-2b", "ModelMergeCosmosPredict2_2B", "sha256:a06998993132624fc263c9a793da452ef29a54947b80330f9724cc8316fadd95", "recipe.merge-cosmos-predict2-2b-first-block"),
    "core.model-merge-cosmos-predict2-14b": ("model-merge-cosmos-predict2-14b", "ModelMergeCosmosPredict2_14B", "sha256:7d52f00b23fe75835758c221acfbaf6106fef28ddf369a82a47c08a332b98ff2", "recipe.merge-cosmos-predict2-14b-first-block"),
    "core.model-merge-qwen-image": ("model-merge-qwen-image", "ModelMergeQwenImage", "sha256:1211ee88d7d82a82513fb1453a9b5018033a696aaa3a3e2c885804537d5884b9", "recipe.merge-qwen-image-first-transformer-block"),
    "core.model-merge-krea2": ("model-merge-krea2", "ModelMergeKrea2", "sha256:7bf0d276405b8fcc407e621734a167e710ad75275c7e3400cd4c5c5331469dfc", "recipe.merge-krea2-first-block"),
}
RECIPES = {
    "recipe.merge-flux1-first-double-block": ("merge-flux1-first-double-block", "ModelMergeFlux1", {"double_blocks.0.": 0.5}),
    "recipe.merge-sd35-first-joint-block": ("merge-sd35-first-joint-block", "ModelMergeSD35_Large", {"joint_blocks.0.": 0.5}),
    "recipe.merge-wan-first-block": ("merge-wan-first-block", "ModelMergeWAN2_1", {"blocks.0.": 0.5}),
    "recipe.merge-ltxv-first-transformer-block": ("merge-ltxv-first-transformer-block", "ModelMergeLTXV", {"transformer_blocks.0.": 0.5}),
    "recipe.merge-auraflow-first-layer": ("merge-auraflow-first-layer", "ModelMergeAuraflow", {"double_layers.0.": 0.5}),
    "recipe.merge-mochi-first-block": ("merge-mochi-first-block", "ModelMergeMochiPreview", {"blocks.0.": 0.5}),
    "recipe.merge-cosmos7b-first-block": ("merge-cosmos7b-first-block", "ModelMergeCosmos7B", {"blocks.block0.": 0.5}),
    "recipe.merge-cosmos14b-first-block": ("merge-cosmos14b-first-block", "ModelMergeCosmos14B", {"blocks.block0.": 0.5}),
    "recipe.merge-cosmos-predict2-2b-first-block": ("merge-cosmos-predict2-2b-first-block", "ModelMergeCosmosPredict2_2B", {"blocks.0.": 0.5}),
    "recipe.merge-cosmos-predict2-14b-first-block": ("merge-cosmos-predict2-14b-first-block", "ModelMergeCosmosPredict2_14B", {"blocks.0.": 0.5}),
    "recipe.merge-qwen-image-first-transformer-block": ("merge-qwen-image-first-transformer-block", "ModelMergeQwenImage", {"transformer_blocks.0.": 0.5}),
    "recipe.merge-krea2-first-block": ("merge-krea2-first-block", "ModelMergeKrea2", {"blocks.0.": 0.5}),
}
DOC_HASHES = {
    ("ModelMergeFlux1", "en"): "589e7cf03d40f431078b53272646fb2366192aff6d613e48df2f77e618e3615f",
    ("ModelMergeFlux1", "ru"): "a322a7c69606463052d7378db4a3c7ad44e6a31eb2a0c9790ce8c390c29ff306",
    ("ModelMergeSD35_Large", "en"): "766af7f60a7328577e7cd93c14fcc193ef3268d968aa8597225924513d1d8735",
    ("ModelMergeSD35_Large", "ru"): "96c015bea8b9f927881156f57d80a4bc20d9020d80623407861f464103e28da3",
    ("ModelMergeWAN2_1", "en"): "a8820daef07991d3c2ae014895508bce5cccab4cf0ff0939f5eff2e67f469719",
    ("ModelMergeWAN2_1", "ru"): "8c51b390c671584c7f2721b13211bbb6539a1dbd0fc4150699187dc729de1805",
    ("ModelMergeLTXV", "en"): "4820197fc3ac59d155da1115164c72dd6d243c46acfa90ceb83ac0274adc7939",
    ("ModelMergeLTXV", "ru"): "080da4afeeb24772dcb890d15779c6ff230e2a636d403e6a4a3307f63dc26f14",
    ("ModelMergeAuraflow", "en"): "e65f73c675a18a2781c09a2c69949a32dfdbb9e1ef4a4327e58259c91d199821",
    ("ModelMergeAuraflow", "ru"): "03d89a1fed7bbcbbd0ef15abe3382d949a974f40db26727d02f79d466be05a0f",
    ("ModelMergeMochiPreview", "en"): "d3c5051d7cbca3b5dfdfaa7e9b55617bc60a6f36c823a5b61fac51e5b50fc6ba",
    ("ModelMergeMochiPreview", "ru"): "09fb0a38df0ed3caad622793d086cc8b9e5b569769e4d3b74ca3ef07bcf142ce",
    ("ModelMergeCosmos7B", "en"): "88045ade1595f5c53695584373b23fe9231859d180b7d11fa03f4d3bed55f799",
    ("ModelMergeCosmos7B", "ru"): "5d7759b69086cb84defa1c566ddfb06905c4e174f2bd2ad3a68d5ff770ced5b4",
    ("ModelMergeCosmos14B", "en"): "6314d2dfb1602ecae30a302f5152b01335aee15dcfe01dc2637249735c42a4bf",
    ("ModelMergeCosmos14B", "ru"): "47521b0dcd72c388efa557ac06c39f3e1a0e53e73a5d56f67c25ac37231d0310",
    ("ModelMergeCosmosPredict2_2B", "en"): "2c738a167611ea189106035caf62a32f8db74800713336859dbffe5fbd157486",
    ("ModelMergeCosmosPredict2_2B", "ru"): "a3ae0de01d62df58625cd631d2cc2c885d89d33d2da92ae8a0104b1ffa42bfb2",
    ("ModelMergeCosmosPredict2_14B", "en"): "0b274755c54c32275989a0561a3439152133e9bca19c0852261c4a353ae93c12",
    ("ModelMergeCosmosPredict2_14B", "ru"): "ab550c7526efef85ef54140ee3225b780c4b59b157a816ef8cf24b9c01d98d72",
    ("ModelMergeQwenImage", "en"): "6adbc929d531358770609499ea6f187d7049f99784428056c2fadb7244d07ded",
    ("ModelMergeQwenImage", "ru"): "374c95a9f1969d660c573e7688f367a3768c025caf7e2a4c3cd8b5f16c2dbe20",
    ("ModelMergeKrea2", "en"): "3e069e538194d7a2cd80532b3803a3c0799b25a58204108227f009d9b8f71071",
    ("ModelMergeKrea2", "ru"): "5476fadd2c32845a6165bf00b8673c007d316bd0edfcb92cc4d58d41e893555a",
}
ROOT = catalog.ROOT
CONTENT = catalog.CONTENT
SOURCE = ROOT / ".comfyui-source-0.32.0"
INVENTORY = CONTENT / "runtime" / "comfyui-0.32.0.object-info.json"
WORKFLOW = ROOT / ".upstream-cache" / "comfyui_workflow_templates_json-0.1.42-py3-none-any.whl"
DOCS = ROOT / ".upstream-cache" / "comfyui_embedded_docs-0.5.9-py3-none-any.whl"
TARGETS = {item[1] for item in SPECS.values()}


def article_ids() -> set[str]:
    return {catalog.load_json(path)["articleId"] for path in (CONTENT / "articles").rglob("manifest.json")}


def nodes(payload: dict[str, Any]) -> Iterator[dict[str, Any]]:
    yield from (node for node in payload.get("nodes", []) if isinstance(node, dict))
    defs = payload.get("definitions")
    for subgraph in defs.get("subgraphs", []) if isinstance(defs, dict) else []:
        yield from (node for node in subgraph.get("nodes", []) if isinstance(node, dict))


class ModelSpecificMergeContentTests(unittest.TestCase):
    def test_content_schemas_honesty_and_russian(self) -> None:
        schemas = {name: catalog.load_json(CONTENT / "schemas" / name) for name in ("article.schema.v1.json", "recipe.schema.v1.json", "recipe-fragment.schema.v1.json", "article-research.schema.v1.json")}
        ids = article_ids()
        errors: list[str] = []
        for article_id, (directory, _, fingerprint, recipe_id) in SPECS.items():
            path = CONTENT / "articles" / "core" / directory / "manifest.json"
            article = catalog.load_json(path)
            self.assertEqual([], catalog.json_schema_errors(article, schemas["article.schema.v1.json"]))
            catalog.validate_article(path, article, errors)
            self.assertEqual("draft", article["status"])
            self.assertEqual("in_review", article["editorial"]["state"])
            self.assertEqual(fingerprint, article["editorial"]["schemaHash"])
            self.assertIn(recipe_id, [asset["id"] for asset in article["assets"]])
            rels = article["relations"]["related"] + article["relations"]["alternatives"]
            self.assertTrue(set(rels).issubset(ids))
            body = (path.parent / "ru.md").read_text(encoding="utf-8")
            self.assertEqual(10, len(re.findall(r"^## ", body, flags=re.MULTILINE)))
            self.assertIn("Редактор пока не проверил материал вручную.", body)
            self.assertNotRegex(body.lower(), r"важно отметить|стоит отметить|в современном мире|революционн|данная нода|давайте разбер|подводя итог|мощный инструмент")
            ledger = catalog.load_json(CONTENT / "research" / "reviews" / f"{article_id}.json")
            self.assertEqual([], catalog.json_schema_errors(ledger, schemas["article-research.schema.v1.json"]))
            self.assertEqual("fact_checked", ledger["state"])
            self.assertEqual("automated_assisted", ledger["reviewMode"])
            self.assertFalse(ledger["checks"]["exampleExecuted"])
        for recipe_id, (directory, class_type, expected_settings) in RECIPES.items():
            path = CONTENT / "recipes" / directory / "recipe.json"
            recipe = catalog.load_json(path)
            self.assertEqual([], catalog.json_schema_errors(recipe, schemas["recipe.schema.v1.json"]))
            catalog.validate_recipe(path, recipe, ids, errors)
            self.assertEqual("in_review", recipe["editorial"]["state"])
            self.assertNotIn("workflow", recipe)
            fragment_path = path.parent / "fragment.json"
            fragment = catalog.load_json(fragment_path)
            self.assertEqual([], catalog.json_schema_errors(fragment, schemas["recipe-fragment.schema.v1.json"]))
            catalog.validate_fragment(fragment_path, fragment, errors)
            self.assertEqual([(class_type, expected_settings)], [(n["classType"], n["settings"]) for n in fragment["nodes"]])
        self.assertEqual([], errors)

    def test_runtime_fingerprints_and_exact_input_maps(self) -> None:
        inventory = catalog.load_json(INVENTORY)
        for _, class_type, fingerprint, _ in SPECS.values():
            definition = inventory[class_type]
            self.assertEqual("comfy_extras.nodes_model_merging_model_specific", definition["python_module"])
            self.assertEqual("model/merging/model specific", definition["category"])
            self.assertEqual(fingerprint, catalog.schema_fingerprint(class_type, definition))
            self.assertEqual(["MODEL"], definition["output"])
        self.assertEqual(63, len(inventory["ModelMergeFlux1"]["input_order"]["required"]) - 2)
        self.assertEqual(44, len(inventory["ModelMergeSD35_Large"]["input_order"]["required"]) - 2)
        self.assertEqual(46, len(inventory["ModelMergeWAN2_1"]["input_order"]["required"]) - 2)
        self.assertEqual(33, len(inventory["ModelMergeLTXV"]["input_order"]["required"]) - 2)
        self.assertEqual(43, len(inventory["ModelMergeAuraflow"]["input_order"]["required"]) - 2)
        self.assertEqual(53, len(inventory["ModelMergeMochiPreview"]["input_order"]["required"]) - 2)
        self.assertEqual(34, len(inventory["ModelMergeCosmos7B"]["input_order"]["required"]) - 2)
        self.assertEqual(42, len(inventory["ModelMergeCosmos14B"]["input_order"]["required"]) - 2)
        self.assertEqual(33, len(inventory["ModelMergeCosmosPredict2_2B"]["input_order"]["required"]) - 2)
        self.assertEqual(41, len(inventory["ModelMergeCosmosPredict2_14B"]["input_order"]["required"]) - 2)
        self.assertEqual(66, len(inventory["ModelMergeQwenImage"]["input_order"]["required"]) - 2)
        self.assertEqual(38, len(inventory["ModelMergeKrea2"]["input_order"]["required"]) - 2)

    def test_exact_source_schema_and_prefix_probe(self) -> None:
        result = run_probe(SOURCE)
        self.assertEqual({"double": 19, "single": 38, "ratioInputs": 63}, result["ModelMergeFlux1"])
        self.assertEqual(38, result["ModelMergeSD35_Large"]["joint"])
        self.assertEqual(40, result["ModelMergeWAN2_1"]["blocks"])
        self.assertEqual(28, result["ModelMergeLTXV"]["transformerBlocks"])
        self.assertTrue(result["ModelMergeLTXV"]["barePrefixMatch"])
        self.assertEqual({"ratioInputs": 43, "double": 4, "single": 32}, result["ModelMergeAuraflow"])
        self.assertEqual({"ratioInputs": 53, "blocks": 48}, result["ModelMergeMochiPreview"])
        self.assertEqual({"ratioInputs": 34, "blocks": 28}, result["ModelMergeCosmos7B"])
        self.assertEqual({"ratioInputs": 42, "blocks": 36}, result["ModelMergeCosmos14B"])
        self.assertEqual({"ratioInputs": 33, "blocks": 28}, result["ModelMergeCosmosPredict2_2B"])
        self.assertEqual({"ratioInputs": 41, "blocks": 36}, result["ModelMergeCosmosPredict2_14B"])
        self.assertEqual({"ratioInputs": 66, "blocks": 60}, result["ModelMergeQwenImage"])
        self.assertEqual({"ratioInputs": 38, "blocks": 28, "layerwise": 2, "refiner": 2}, result["ModelMergeKrea2"])
        source = (SOURCE / "comfy_extras" / "nodes_model_merging_model_specific.py").read_text(encoding="utf-8")
        self.assertIn("for i in range(19):", source)
        self.assertIn("for i in range(38):", source)
        self.assertIn('arg_dict["img_emb."] = argument', source)
        self.assertIn('arg_dict["scale_shift_table"] = argument', source)
        self.assertIn('arg_dict["pos_embedder."] = argument', source)
        self.assertIn('arg_dict["pos_embeds."] = argument', source)
        self.assertIn('arg_dict["txtfusion.projector."] = argument', source)

    def test_docs_hashes(self) -> None:
        self.assertEqual("30afae432a71c96aa59421d0f37388c66ff6572b8cbeee8ff045e4d5f84f896c", hashlib.sha256(DOCS.read_bytes()).hexdigest())
        with zipfile.ZipFile(DOCS) as archive:
            for (class_type, locale), expected in DOC_HASHES.items():
                self.assertEqual(expected, hashlib.sha256(archive.read(f"comfyui_embedded_docs/docs/{class_type}/{locale}.md")).hexdigest())

    def test_workflow_census_exact_absence(self) -> None:
        self.assertEqual("242982d65e1c51ca03d892bc1009bb6843f457e7dfc0c20afe6438770b7a14a3", hashlib.sha256(WORKFLOW.read_bytes()).hexdigest())
        count = roots = subgraphs = 0
        found: list[str] = []
        with zipfile.ZipFile(WORKFLOW) as archive:
            for name in archive.namelist():
                if not name.endswith(".json"): continue
                count += 1
                payload = json.loads(archive.read(name))
                if isinstance(payload, dict) and isinstance(payload.get("nodes"), list): roots += 1
                if isinstance(payload, dict):
                    defs = payload.get("definitions")
                    if isinstance(defs, dict): subgraphs += len(defs.get("subgraphs", []))
                    found.extend(node["type"] for node in nodes(payload) if node.get("type") in TARGETS)
        self.assertEqual((512, 496, 272), (count, roots, subgraphs))
        self.assertEqual([], found)


if __name__ == "__main__": unittest.main()
