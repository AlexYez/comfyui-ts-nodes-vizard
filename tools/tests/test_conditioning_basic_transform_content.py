from __future__ import annotations

import hashlib
import json
import re
import unittest
import zipfile
from collections import Counter
from typing import Any, Iterator

import torch

from tools import catalog


SPECS = {
    "core.conditioning-average": ("conditioning-average", "ConditioningAverage", "sha256:71b33eb0e875dd7d5e0887f77697a3b5a8bf973738986e79fd47685845b5e8ab", "average-conditioning"),
    "core.conditioning-concat": ("conditioning-concat", "ConditioningConcat", "sha256:bf03631f6fc8a5fcabda4cae8d20453a5ccefee353fc7f0f2a9488b1aa4a314b", "concat-conditioning-tokens"),
    "core.conditioning-set-mask": ("conditioning-set-mask", "ConditioningSetMask", "sha256:4e3eccf69b817672886fc0c4339e357f4b04f00938c5c9ff0436d432404b1b5d", "masked-conditioning-region"),
    "core.conditioning-set-timestep-range": ("conditioning-set-timestep-range", "ConditioningSetTimestepRange", "sha256:614f9c58dbf5668777e7ae3c2e767d8d0b76ca4a83102e1393c82ddbd9ea7a42", "timed-conditioning-window"),
}
ROOT = catalog.ROOT
INVENTORY = catalog.CONTENT / "runtime" / "comfyui-0.32.0.object-info.json"
REPLACEMENTS = catalog.CONTENT / "runtime" / "comfyui-0.32.0.node-replacements.json"
SOURCE = ROOT / ".comfyui-source-0.32.0"
DOCS = ROOT / ".upstream-cache" / "comfyui_embedded_docs-0.5.9-py3-none-any.whl"
WORKFLOWS = ROOT / ".upstream-cache" / "comfyui_workflow_templates_json-0.1.42-py3-none-any.whl"


def scopes(payload: dict[str, Any]) -> Iterator[dict[str, Any]]:
    if isinstance(payload.get("nodes"), list):
        yield payload
    definitions = payload.get("definitions")
    if isinstance(definitions, dict):
        for subgraph in definitions.get("subgraphs", []):
            if isinstance(subgraph, dict):
                yield subgraph


class ConditioningBasicTransformContentTests(unittest.TestCase):
    def test_content_contracts_honesty_and_language(self) -> None:
        schemas = {name: catalog.load_json(catalog.CONTENT / "schemas" / name) for name in (
            "article.schema.v1.json", "recipe.schema.v1.json", "recipe-fragment.schema.v1.json", "article-research.schema.v1.json"
        )}
        article_ids = {catalog.load_json(path)["articleId"] for path in (catalog.CONTENT / "articles").rglob("manifest.json")}
        errors: list[str] = []
        for article_id, (directory, _class_type, _fingerprint, recipe_id) in SPECS.items():
            path = catalog.CONTENT / "articles" / "core" / directory / "manifest.json"
            article = catalog.load_json(path)
            self.assertEqual([], catalog.json_schema_errors(article, schemas["article.schema.v1.json"]), article_id)
            catalog.validate_article(path, article, errors)
            self.assertEqual(("draft", "in_review"), (article["status"], article["editorial"]["state"]))
            self.assertEqual(10, len(re.findall(r"^## ", (path.parent / article["body"]).read_text(encoding="utf-8"), re.MULTILINE)))
            ledger = catalog.load_json(catalog.CONTENT / "research" / "reviews" / f"{article_id}.json")
            self.assertEqual([], catalog.json_schema_errors(ledger, schemas["article-research.schema.v1.json"]), article_id)
            self.assertEqual("fact_checked", ledger["state"])
            self.assertFalse(ledger["checks"]["exampleExecuted"])
            self.assertTrue(any("человеческое" in gap.casefold() for gap in ledger["knownGaps"]))
            recipe_path = catalog.CONTENT / "recipes" / recipe_id / "recipe.json"
            recipe = catalog.load_json(recipe_path)
            self.assertEqual([], catalog.json_schema_errors(recipe, schemas["recipe.schema.v1.json"]), recipe_id)
            catalog.validate_recipe(recipe_path, recipe, article_ids, errors)
            self.assertNotIn("workflow", recipe)
            fragment_path = recipe_path.parent / recipe["fragment"]["path"]
            fragment = catalog.load_json(fragment_path)
            self.assertEqual([], catalog.json_schema_errors(fragment, schemas["recipe-fragment.schema.v1.json"]), recipe_id)
            catalog.validate_fragment(fragment_path, fragment, errors)
            prose = re.sub(r"`[^`]+`|https?://\S+", "", (recipe_path.parent / recipe["body"]).read_text(encoding="utf-8")).casefold()
            for phrase in ("official workflow", "full fragment", "runtime-контракт", "batch-размер", "sampling-run", "widget values"):
                self.assertNotIn(phrase, prose, recipe_id)
        self.assertEqual([], errors)

    def test_runtime_identity_constraints_and_no_replacements(self) -> None:
        nodes = catalog.object_info_nodes(catalog.load_json(INVENTORY))
        for article_id, (directory, class_type, fingerprint, _recipe_id) in SPECS.items():
            runtime = nodes[class_type]
            article = catalog.load_json(catalog.CONTENT / "articles" / "core" / directory / "manifest.json")
            self.assertEqual("nodes", runtime["python_module"])
            self.assertEqual(fingerprint, catalog.schema_fingerprint(class_type, runtime), article_id)
            self.assertEqual(fingerprint, article["editorial"]["schemaHash"])
            self.assertFalse(runtime.get("api_node", False))
            self.assertFalse(runtime.get("deprecated", False))
            self.assertEqual(["CONDITIONING"], runtime["output"])
        self.assertEqual((0.0, 1.0), (nodes["ConditioningAverage"]["input"]["required"]["conditioning_to_strength"][1]["min"], nodes["ConditioningAverage"]["input"]["required"]["conditioning_to_strength"][1]["max"]))
        self.assertEqual(["default", "mask bounds"], nodes["ConditioningSetMask"]["input"]["required"]["set_cond_area"][0])
        self.assertEqual(0.001, nodes["ConditioningSetTimestepRange"]["input"]["required"]["start"][1]["step"])
        replacements_payload = catalog.load_json(REPLACEMENTS)
        self.assertEqual("ConditioningAverage", replacements_payload["ConditioningAverage "][0]["new_node_id"])
        self.assertEqual("ConditioningAverage ", replacements_payload["ConditioningAverage "][0]["old_node_id"])
        replacements = json.dumps(replacements_payload, ensure_ascii=False)
        for class_type in ("ConditioningConcat", "ConditioningSetMask", "ConditioningSetTimestepRange"):
            self.assertNotIn(class_type, replacements)

    def test_pinned_sources_and_tensor_semantics(self) -> None:
        paths = {
            "nodes": (SOURCE / "nodes.py", "ffb2b5c999f47b720dbd81767c8fa4234255d939ba8dbb80ee64da9721c383ad"),
            "helpers": (SOURCE / "node_helpers.py", "6e9e963b1538bdec3370721cfb16c02aa88a2891dafbbd9dd007c190f68ca935"),
            "samplers": (SOURCE / "comfy" / "samplers.py", "aabb644b0f864cd18110e64a9216701b8cbebec7a54c425477ae36a821a99e8e"),
        }
        text = {}
        for key, (path, digest) in paths.items():
            self.assertEqual(digest, hashlib.sha256(path.read_bytes()).hexdigest())
            text[key] = path.read_text(encoding="utf-8")
        for marker in ("class ConditioningAverage", "class ConditioningConcat", "class ConditioningSetMask", "class ConditioningSetTimestepRange"):
            self.assertIn(marker, text["nodes"])
        for marker in ("conditioning_from[0][0]", "torch.cat((t1, cond_from),1)", '"mask_strength": strength', '"start_percent": start'):
            self.assertIn(marker, text["nodes"])
        self.assertIn("def conditioning_set_values", text["helpers"])
        self.assertIn('percent_to_sigma', text["samplers"])

        to = torch.tensor([[[1.0, 2.0], [3.0, 4.0], [5.0, 6.0]]])
        source = torch.tensor([[[10.0, 20.0], [30.0, 40.0]]])
        padded = torch.cat((source, torch.zeros(1, 1, 2)), dim=1)
        averaged = to * 0.5 + padded * 0.5
        self.assertEqual((1, 3, 2), tuple(averaged.shape))
        self.assertTrue(torch.equal(averaged[0, 2], torch.tensor([2.5, 3.0])))
        concatenated = torch.cat((to, source), dim=1)
        self.assertEqual((1, 5, 2), tuple(concatenated.shape))
        mask = torch.ones(4, 8)
        normalized = mask.reshape((-1, 1, mask.shape[-2], mask.shape[-1]))
        self.assertEqual((1, 1, 4, 8), tuple(normalized.shape))

    def test_docs_and_exhaustive_zero_workflow_census(self) -> None:
        self.assertEqual("30afae432a71c96aa59421d0f37388c66ff6572b8cbeee8ff045e4d5f84f896c", hashlib.sha256(DOCS.read_bytes()).hexdigest())
        with zipfile.ZipFile(DOCS) as archive:
            names = set(archive.namelist())
            for class_type in ("ConditioningAverage", "ConditioningConcat", "ConditioningSetMask"):
                self.assertIn(f"comfyui_embedded_docs/docs/{class_type}/en.md", names)
            self.assertNotIn("comfyui_embedded_docs/docs/ConditioningSetTimestepRange/en.md", names)
            self.assertIn("comfyui_embedded_docs/docs/ConditioningSettimestepRange/en.md", names)
        self.assertEqual("242982d65e1c51ca03d892bc1009bb6843f457e7dfc0c20afe6438770b7a14a3", hashlib.sha256(WORKFLOWS.read_bytes()).hexdigest())
        targets = {spec[1] for spec in SPECS.values()}; counts: Counter[str] = Counter()
        json_count = root_count = subgraph_count = node_count = 0
        with zipfile.ZipFile(WORKFLOWS) as archive:
            for member in archive.namelist():
                if "/templates/" not in member or not member.endswith(".json"):
                    continue
                json_count += 1
                payload = json.loads(archive.read(member).decode("utf-8"))
                graphs = list(scopes(payload)) if isinstance(payload, dict) else []
                has_root = isinstance(payload, dict) and isinstance(payload.get("nodes"), list)
                root_count += int(has_root); subgraph_count += len(graphs) - int(has_root)
                for graph in graphs:
                    for node in graph.get("nodes", []):
                        node_count += 1
                        if isinstance(node, dict) and node.get("type") in targets:
                            counts[node["type"]] += 1
        self.assertEqual((512, 496, 272, 8120), (json_count, root_count, subgraph_count, node_count))
        self.assertEqual(Counter(), counts)


if __name__ == "__main__":
    unittest.main()
