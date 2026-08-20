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


SPECS: dict[str, dict[str, str]] = {
    "core.solid-mask": {"directory": "solid-mask", "classType": "SolidMask", "fingerprint": "sha256:310b40c0e9620c5712643dc192b5870d4d8677e1bd0c106fb60f6872664b74b9"},
    "core.feather-mask": {"directory": "feather-mask", "classType": "FeatherMask", "fingerprint": "sha256:c86d1f9d2962dc1756d63de1321443f22c49a1af77a27498006b699165f242f8"},
    "core.grow-mask": {"directory": "grow-mask", "classType": "GrowMask", "fingerprint": "sha256:ad8c5b34177e449726a4213a9ac24077650ce36822ce481d06ef1cc9df16e70c"},
    "core.mask-composite": {"directory": "mask-composite", "classType": "MaskComposite", "fingerprint": "sha256:f296c8ab23f829374dda6d1cc4232915103aefed26f0729925dec36dab54ff9b"},
}

INVENTORY = catalog.CONTENT / "runtime" / "comfyui-0.32.0.object-info.json"
REPLACEMENTS = catalog.CONTENT / "runtime" / "comfyui-0.32.0.node-replacements.json"
SOURCE = catalog.ROOT / ".comfyui-source-0.32.0"
DOCS = catalog.ROOT / ".upstream-cache" / "comfyui_embedded_docs-0.5.9-py3-none-any.whl"
WORKFLOWS = catalog.ROOT / ".upstream-cache" / "comfyui_workflow_templates_json-0.1.42-py3-none-any.whl"
DOCS_SHA256 = "30afae432a71c96aa59421d0f37388c66ff6572b8cbeee8ff045e4d5f84f896c"
WORKFLOWS_SHA256 = "242982d65e1c51ca03d892bc1009bb6843f457e7dfc0c20afe6438770b7a14a3"


def article_path(spec: dict[str, str]) -> Path:
    return catalog.CONTENT / "articles" / "core" / spec["directory"] / "manifest.json"


def scopes(payload: dict[str, Any]) -> Iterator[dict[str, Any]]:
    if isinstance(payload.get("nodes"), list):
        yield payload
    definitions = payload.get("definitions")
    if isinstance(definitions, dict):
        for subgraph in definitions.get("subgraphs", []):
            if isinstance(subgraph, dict):
                yield subgraph


class MaskCoreContentTests(unittest.TestCase):
    def test_articles_recipe_ledgers_and_natural_russian(self) -> None:
        article_schema = catalog.load_json(catalog.CONTENT / "schemas" / "article.schema.v1.json")
        recipe_schema = catalog.load_json(catalog.CONTENT / "schemas" / "recipe.schema.v1.json")
        fragment_schema = catalog.load_json(catalog.CONTENT / "schemas" / "recipe-fragment.schema.v1.json")
        research_schema = catalog.load_json(catalog.CONTENT / "schemas" / "article-research.schema.v1.json")
        article_ids = {catalog.load_json(path)["articleId"] for path in (catalog.CONTENT / "articles").rglob("manifest.json")}
        errors: list[str] = []
        for article_id, spec in SPECS.items():
            path = article_path(spec)
            article = catalog.load_json(path)
            self.assertEqual([], catalog.json_schema_errors(article, article_schema), article_id)
            catalog.validate_article(path, article, errors)
            self.assertEqual("draft", article["status"])
            self.assertEqual("in_review", article["editorial"]["state"])
            body = (path.parent / article["body"]).read_text(encoding="utf-8")
            self.assertEqual(10, len(re.findall(r"^## ", body, re.MULTILINE)), article_id)
            record = catalog.load_json(catalog.CONTENT / "research" / "reviews" / f"{article_id}.json")
            self.assertEqual([], catalog.json_schema_errors(record, research_schema), article_id)
            self.assertEqual("fact_checked", record["state"])
            self.assertFalse(record["checks"]["exampleExecuted"])
            self.assertTrue(record["knownGaps"])

        recipe_path = catalog.CONTENT / "recipes" / "mask-compose-edge-control" / "recipe.json"
        recipe = catalog.load_json(recipe_path)
        self.assertEqual([], catalog.json_schema_errors(recipe, recipe_schema))
        catalog.validate_recipe(recipe_path, recipe, article_ids, errors)
        self.assertNotIn("workflow", recipe)
        fragment_path = recipe_path.parent / recipe["fragment"]["path"]
        fragment = catalog.load_json(fragment_path)
        self.assertEqual([], catalog.json_schema_errors(fragment, fragment_schema))
        catalog.validate_fragment(fragment_path, fragment, errors)
        body = (recipe_path.parent / recipe["body"]).read_text(encoding="utf-8")
        prose = re.sub(r"`[^`]+`|https?://\S+", "", body).casefold()
        for untranslated in (" fragment", " workflow", " destination", " source", " preview", " production-", " runtime"):
            self.assertNotIn(untranslated, prose)
        self.assertEqual([], errors)

    def test_runtime_contract_fingerprints_and_replacements(self) -> None:
        nodes = catalog.object_info_nodes(catalog.load_json(INVENTORY))
        for article_id, spec in SPECS.items():
            runtime = nodes[spec["classType"]]
            article = catalog.load_json(article_path(spec))
            self.assertEqual("comfy_extras.nodes_mask", runtime["python_module"])
            self.assertEqual(spec["fingerprint"], catalog.schema_fingerprint(spec["classType"], runtime), article_id)
            self.assertEqual(spec["fingerprint"], article["editorial"]["schemaHash"])
            self.assertFalse(runtime.get("api_node", False))
            self.assertFalse(runtime.get("deprecated", False))
        self.assertEqual(["multiply", "add", "subtract", "and", "or", "xor"], nodes["MaskComposite"]["input"]["required"]["operation"][1]["options"])
        self.assertEqual(True, nodes["GrowMask"]["input"]["required"]["tapered_corners"][1]["default"])
        replacements = json.dumps(catalog.load_json(REPLACEMENTS), ensure_ascii=False)
        for spec in SPECS.values():
            self.assertNotIn(spec["classType"], replacements)

    def test_pinned_source_semantics(self) -> None:
        source = (SOURCE / "comfy_extras" / "nodes_mask.py").read_text(encoding="utf-8")
        for marker in (
            "torch.full((1, height, width), value",
            "destination_portion * source_portion",
            "torch.bitwise_xor(destination_portion.round().bool()",
            "output = torch.clamp(output, 0.0, 1.0)",
            "feather_rate = (x + 1.0) / left",
            "c = 0 if tapered_corners else 1",
            "scipy.ndimage.grey_erosion",
            "scipy.ndimage.grey_dilation",
        ):
            self.assertIn(marker, source)

    def test_docs_and_exact_workflow_census(self) -> None:
        self.assertEqual(DOCS_SHA256, hashlib.sha256(DOCS.read_bytes()).hexdigest())
        with zipfile.ZipFile(DOCS) as archive:
            names = set(archive.namelist())
            for spec in SPECS.values():
                self.assertIn(f"comfyui_embedded_docs/docs/{spec['classType']}/en.md", names)
        self.assertEqual(WORKFLOWS_SHA256, hashlib.sha256(WORKFLOWS.read_bytes()).hexdigest())
        counts: Counter[str] = Counter()
        settings: dict[str, list[Any]] = {spec["classType"]: [] for spec in SPECS.values()}
        json_count = root_count = subgraph_count = 0
        with zipfile.ZipFile(WORKFLOWS) as archive:
            for member in archive.namelist():
                if "/templates/" not in member or not member.endswith(".json"):
                    continue
                json_count += 1
                payload = json.loads(archive.read(member).decode("utf-8"))
                graph_list = list(scopes(payload)) if isinstance(payload, dict) else []
                has_root = isinstance(payload, dict) and isinstance(payload.get("nodes"), list)
                root_count += int(has_root)
                subgraph_count += len(graph_list) - int(has_root)
                for graph in graph_list:
                    for node in graph.get("nodes", []):
                        node_type = node.get("type") if isinstance(node, dict) else None
                        if node_type in settings:
                            counts[node_type] += 1
                            settings[node_type].append(node.get("widgets_values"))
        self.assertEqual((512, 496, 272), (json_count, root_count, subgraph_count))
        self.assertEqual({"SolidMask": 9, "FeatherMask": 2, "GrowMask": 3, "MaskComposite": 7}, dict(counts))
        self.assertEqual(Counter({(0, True): 1, (20, True): 2}), Counter(tuple(item) for item in settings["GrowMask"]))
        self.assertIn([40, 40, 40, 40], settings["FeatherMask"])
        self.assertEqual(Counter({"add": 3, "multiply": 1, "and": 1, "or": 1, "xor": 1}), Counter(item[2] for item in settings["MaskComposite"]))


if __name__ == "__main__":
    unittest.main()
