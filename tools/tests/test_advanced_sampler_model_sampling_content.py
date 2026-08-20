from __future__ import annotations

import hashlib
import json
import re
import unittest
import zipfile
from collections import Counter
from typing import Any, Iterator

from tools import catalog


SPECS = {
    "core.ksampler-advanced": ("ksampler-advanced", "KSamplerAdvanced", "nodes", "sha256:8af1ee77d5a7d5ad8793f4648d35a6c705b794a983c2e560e7f8c1670b2f4f81", "advanced-sampling-external-vae"),
    "core.model-sampling-continuous-edm": ("model-sampling-continuous-edm", "ModelSamplingContinuousEDM", "comfy_extras.nodes_model_advanced", "sha256:b1663fc7cc78e2263abb51d5bc9c5a9b02146adbd1f03b5869b21ed2879c548b", "playground-edm-model-sampling"),
    "core.model-sampling-continuous-v": ("model-sampling-continuous-v", "ModelSamplingContinuousV", "comfy_extras.nodes_model_advanced", "sha256:0bbabd71ce38f46339c02d3035e04c19f21803752228807a68c3c338ebcf8532", "stable-audio-continuous-v-sampling"),
    "core.model-sampling-stable-cascade": ("model-sampling-stable-cascade", "ModelSamplingStableCascade", "comfy_extras.nodes_model_advanced", "sha256:80bd44d7639b88dd5428daa6bd4c6ee50c676de869457854c198674803ccab73", "stable-cascade-shift-sampling"),
}
ROOT = catalog.ROOT
INVENTORY = catalog.CONTENT / "runtime" / "comfyui-0.32.0.object-info.json"
SOURCE = ROOT / ".comfyui-source-0.32.0"
DOCS = ROOT / ".upstream-cache" / "comfyui_embedded_docs-0.5.9-py3-none-any.whl"
WORKFLOWS = ROOT / ".upstream-cache" / "comfyui_workflow_templates_json-0.1.42-py3-none-any.whl"


def scopes(payload: dict[str, Any]) -> Iterator[dict[str, Any]]:
    if isinstance(payload.get("nodes"), list):
        yield payload
    definitions = payload.get("definitions")
    if isinstance(definitions, dict):
        yield from (graph for graph in definitions.get("subgraphs", []) if isinstance(graph, dict))


class AdvancedSamplerModelSamplingContentTests(unittest.TestCase):
    def test_content_schema_sections_and_honesty(self) -> None:
        schemas = {name: catalog.load_json(catalog.CONTENT / "schemas" / name) for name in (
            "article.schema.v1.json", "recipe.schema.v1.json", "recipe-fragment.schema.v1.json", "article-research.schema.v1.json"
        )}
        article_ids = {catalog.load_json(path)["articleId"] for path in (catalog.CONTENT / "articles").rglob("manifest.json")}
        errors: list[str] = []
        for article_id, (directory, _class_type, _module, _fingerprint, recipe_id) in SPECS.items():
            path = catalog.CONTENT / "articles" / "core" / directory / "manifest.json"
            article = catalog.load_json(path)
            self.assertEqual([], catalog.json_schema_errors(article, schemas["article.schema.v1.json"]), article_id)
            catalog.validate_article(path, article, errors)
            self.assertEqual(("draft", "in_review"), (article["status"], article["editorial"]["state"]))
            self.assertEqual(10, len(re.findall(r"^## ", (path.parent / article["body"]).read_text(encoding="utf-8"), re.MULTILINE)))
            ledger = catalog.load_json(catalog.CONTENT / "research" / "reviews" / f"{article_id}.json")
            self.assertEqual([], catalog.json_schema_errors(ledger, schemas["article-research.schema.v1.json"]), article_id)
            self.assertFalse(ledger["checks"]["exampleExecuted"])
            self.assertTrue(any("человеческое" in gap.casefold() or "human editorial approval" in gap.casefold() for gap in ledger["knownGaps"]))
            recipe_path = catalog.CONTENT / "recipes" / recipe_id / "recipe.json"
            recipe = catalog.load_json(recipe_path)
            self.assertEqual([], catalog.json_schema_errors(recipe, schemas["recipe.schema.v1.json"]), recipe_id)
            catalog.validate_recipe(recipe_path, recipe, article_ids, errors)
            fragment_path = recipe_path.parent / recipe["fragment"]["path"]
            fragment = catalog.load_json(fragment_path)
            self.assertEqual([], catalog.json_schema_errors(fragment, schemas["recipe-fragment.schema.v1.json"]), recipe_id)
            catalog.validate_fragment(fragment_path, fragment, errors)
        self.assertEqual([], errors)

    def test_runtime_fingerprints_ports_and_settings(self) -> None:
        nodes = catalog.object_info_nodes(catalog.load_json(INVENTORY))
        for article_id, (directory, class_type, module, fingerprint, _recipe_id) in SPECS.items():
            runtime = nodes[class_type]
            article = catalog.load_json(catalog.CONTENT / "articles" / "core" / directory / "manifest.json")
            self.assertEqual(module, runtime["python_module"])
            self.assertEqual(fingerprint, catalog.schema_fingerprint(class_type, runtime), article_id)
            self.assertEqual(fingerprint, article["editorial"]["schemaHash"])
            self.assertFalse(runtime.get("api_node", False))
        advanced = nodes["KSamplerAdvanced"]["input"]["required"]
        self.assertEqual(["enable", "disable"], advanced["add_noise"][0])
        self.assertEqual(["disable", "enable"], advanced["return_with_leftover_noise"][0])
        self.assertEqual((0, 10000), (advanced["start_at_step"][1]["min"], advanced["end_at_step"][1]["max"]))
        edm = nodes["ModelSamplingContinuousEDM"]["input"]["required"]
        self.assertEqual(["v_prediction", "edm", "edm_playground_v2.5", "eps", "cosmos_rflow"], edm["sampling"][0])
        self.assertEqual(120.0, edm["sigma_max"][1]["default"])
        self.assertEqual(0.03, nodes["ModelSamplingContinuousV"]["input"]["required"]["sigma_min"][1]["default"])
        self.assertEqual(2.0, nodes["ModelSamplingStableCascade"]["input"]["required"]["shift"][1]["default"])

    def test_pinned_source_branches(self) -> None:
        paths = {
            "nodes": (SOURCE / "nodes.py", "ffb2b5c999f47b720dbd81767c8fa4234255d939ba8dbb80ee64da9721c383ad"),
            "advanced": (SOURCE / "comfy_extras" / "nodes_model_advanced.py", "88f9fcb97a9cd8b003b693620ddcccec29f213ed50656d72f7da210b43cfb806"),
        }
        text = {}
        for key, (path, digest) in paths.items():
            self.assertEqual(digest, hashlib.sha256(path.read_bytes()).hexdigest())
            text[key] = path.read_text(encoding="utf-8")
        for marker in ("class KSamplerAdvanced", 'return_with_leftover_noise == "enable"', 'add_noise == "disable"', "force_full_denoise=force_full_denoise"):
            self.assertIn(marker, text["nodes"])
        for marker in ("class ModelSamplingContinuousEDM", "ModelSamplingCosmosRFlow", "SDXL_Playground_2_5", "class ModelSamplingContinuousV", "class ModelSamplingStableCascade", "model_sampling.set_parameters(shift)"):
            self.assertIn(marker, text["advanced"])

    def test_docs_and_exhaustive_workflow_census(self) -> None:
        self.assertEqual("30afae432a71c96aa59421d0f37388c66ff6572b8cbeee8ff045e4d5f84f896c", hashlib.sha256(DOCS.read_bytes()).hexdigest())
        with zipfile.ZipFile(DOCS) as archive:
            names = set(archive.namelist())
            self.assertNotIn("comfyui_embedded_docs/docs/ModelSamplingContinuousEDM/en.md", names)
            expected = {
                "KSamplerAdvanced": ("c1f82a8c06470fc525d6a72b1b60413e7dd42089aa571ca35ba7649b6eab77ed", "1a2cd4f99a06051731dc94eafa005f6d7068f774f92d2a1e5a95d2e9c0d315d9"),
                "ModelSamplingContinuousV": ("5bbddcaf75d09bc225408e20a3ef132a64bbfb8c47cc9351d1796c4c57a89a9d", "2efbf1a7b0e719f46bfeb660b11a5db9e25f8902cde71d113e7ba175fe28e43c"),
                "ModelSamplingStableCascade": ("5d54f7dc44f8daf8b79c37dc0c7effd5dff0049ae2b2fc03a6097190e2018c2c", "64e0332d6a05528e244d1decd5e9667415a51bb5f2c37ebdf4efb24f63acac64"),
            }
            for class_type, hashes in expected.items():
                for locale, digest in zip(("en", "ru"), hashes):
                    self.assertEqual(digest, hashlib.sha256(archive.read(f"comfyui_embedded_docs/docs/{class_type}/{locale}.md")).hexdigest())

        self.assertEqual("242982d65e1c51ca03d892bc1009bb6843f457e7dfc0c20afe6438770b7a14a3", hashlib.sha256(WORKFLOWS.read_bytes()).hexdigest())
        targets = {spec[1] for spec in SPECS.values()}; counts: Counter[str] = Counter()
        json_count = root_count = subgraph_count = node_count = 0
        with zipfile.ZipFile(WORKFLOWS) as archive:
            for member in archive.namelist():
                if "/templates/" not in member or not member.endswith(".json"):
                    continue
                json_count += 1; payload = json.loads(archive.read(member).decode("utf-8"))
                graphs = list(scopes(payload)) if isinstance(payload, dict) else []
                has_root = isinstance(payload, dict) and isinstance(payload.get("nodes"), list)
                root_count += int(has_root); subgraph_count += len(graphs) - int(has_root)
                for graph in graphs:
                    for node in graph.get("nodes", []):
                        node_count += 1
                        if isinstance(node, dict) and node.get("type") in targets:
                            counts[node["type"]] += 1
        self.assertEqual((512, 496, 272, 8120), (json_count, root_count, subgraph_count, node_count))
        self.assertEqual(Counter({"KSamplerAdvanced": 38}), counts)


if __name__ == "__main__":
    unittest.main()
