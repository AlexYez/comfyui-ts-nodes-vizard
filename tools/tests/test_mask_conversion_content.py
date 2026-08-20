from __future__ import annotations

import hashlib
import json
import re
import unittest
import zipfile
from collections import Counter
from pathlib import Path
from typing import Any, Iterator

import torch

from tools import catalog


SPECS: dict[str, dict[str, str]] = {
    "core.load-image-mask": {
        "directory": "load-image-mask",
        "classType": "LoadImageMask",
        "module": "nodes",
        "fingerprint": "sha256:e99cd173f840736e55a62a2894c47bc8ef0f3323c46d2e6062b1489216d8a966",
        "recipe": "mask-from-channel",
    },
    "core.image-color-to-mask": {
        "directory": "image-color-to-mask",
        "classType": "ImageColorToMask",
        "module": "comfy_extras.nodes_mask",
        "fingerprint": "sha256:ba956a6bbfe8610f626d7bf1dd4747007023c6bb67ebe7060ceac5d9de43174f",
        "recipe": "color-key-mask",
    },
    "core.crop-mask": {
        "directory": "crop-mask",
        "classType": "CropMask",
        "module": "comfy_extras.nodes_mask",
        "fingerprint": "sha256:24c9772a80e89c8f6f99df240d4c2782919704b8a56366ea095473d6eaf31103",
        "recipe": "crop-mask-preview",
    },
    "core.threshold-mask": {
        "directory": "threshold-mask",
        "classType": "ThresholdMask",
        "module": "comfy_extras.nodes_mask",
        "fingerprint": "sha256:697b641daa57b5f3c664160a8ed469add01a3f10c4b6c29d270bdbd39dbce3bd",
        "recipe": "mask-conversions",
    },
}

INVENTORY = catalog.CONTENT / "runtime" / "comfyui-0.32.0.object-info.json"
REPLACEMENTS = catalog.CONTENT / "runtime" / "comfyui-0.32.0.node-replacements.json"
SOURCE = catalog.ROOT / ".comfyui-source-0.32.0"
DOCS = catalog.ROOT / ".upstream-cache" / "comfyui_embedded_docs-0.5.9-py3-none-any.whl"
WORKFLOWS = catalog.ROOT / ".upstream-cache" / "comfyui_workflow_templates_json-0.1.42-py3-none-any.whl"
DOCS_SHA256 = "30afae432a71c96aa59421d0f37388c66ff6572b8cbeee8ff045e4d5f84f896c"
WORKFLOWS_SHA256 = "242982d65e1c51ca03d892bc1009bb6843f457e7dfc0c20afe6438770b7a14a3"
NODES_SHA256 = "ffb2b5c999f47b720dbd81767c8fa4234255d939ba8dbb80ee64da9721c383ad"
MASK_SOURCE_SHA256 = "39d21d7c96cb18035200167ff9883db2cdb3674513837094b3e5326188eabc1f"


def scopes(payload: dict[str, Any]) -> Iterator[dict[str, Any]]:
    if isinstance(payload.get("nodes"), list):
        yield payload
    definitions = payload.get("definitions")
    if isinstance(definitions, dict):
        for subgraph in definitions.get("subgraphs", []):
            if isinstance(subgraph, dict):
                yield subgraph


class MaskConversionContentTests(unittest.TestCase):
    def test_articles_recipes_ledgers_and_natural_russian(self) -> None:
        article_schema = catalog.load_json(catalog.CONTENT / "schemas" / "article.schema.v1.json")
        recipe_schema = catalog.load_json(catalog.CONTENT / "schemas" / "recipe.schema.v1.json")
        fragment_schema = catalog.load_json(catalog.CONTENT / "schemas" / "recipe-fragment.schema.v1.json")
        research_schema = catalog.load_json(catalog.CONTENT / "schemas" / "article-research.schema.v1.json")
        article_ids = {catalog.load_json(path)["articleId"] for path in (catalog.CONTENT / "articles").rglob("manifest.json")}
        errors: list[str] = []
        for article_id, spec in SPECS.items():
            article_path = catalog.CONTENT / "articles" / "core" / spec["directory"] / "manifest.json"
            article = catalog.load_json(article_path)
            self.assertEqual([], catalog.json_schema_errors(article, article_schema), article_id)
            catalog.validate_article(article_path, article, errors)
            self.assertEqual(("draft", "in_review"), (article["status"], article["editorial"]["state"]))
            body = (article_path.parent / article["body"]).read_text(encoding="utf-8")
            self.assertEqual(10, len(re.findall(r"^## ", body, re.MULTILINE)), article_id)
            record = catalog.load_json(catalog.CONTENT / "research" / "reviews" / f"{article_id}.json")
            self.assertEqual([], catalog.json_schema_errors(record, research_schema), article_id)
            self.assertEqual("fact_checked", record["state"])
            self.assertFalse(record["checks"]["exampleExecuted"])
            self.assertTrue(record["knownGaps"])

            recipe_path = catalog.CONTENT / "recipes" / spec["recipe"] / "recipe.json"
            recipe = catalog.load_json(recipe_path)
            self.assertEqual([], catalog.json_schema_errors(recipe, recipe_schema), spec["recipe"])
            catalog.validate_recipe(recipe_path, recipe, article_ids, errors)
            self.assertNotIn("workflow", recipe)
            fragment_path = recipe_path.parent / recipe["fragment"]["path"]
            fragment = catalog.load_json(fragment_path)
            self.assertEqual([], catalog.json_schema_errors(fragment, fragment_schema), spec["recipe"])
            catalog.validate_fragment(fragment_path, fragment, errors)
            prose = re.sub(r"`[^`]+`|https?://\S+", "", (recipe_path.parent / recipe["body"]).read_text(encoding="utf-8")).casefold()
            for untranslated in (" fragment", " preview", " padding", " lossless", " runtime", " workflow"):
                self.assertNotIn(untranslated, prose, spec["recipe"])
        self.assertEqual([], errors)

    def test_runtime_identity_fingerprints_ports_and_replacements(self) -> None:
        nodes = catalog.object_info_nodes(catalog.load_json(INVENTORY))
        for article_id, spec in SPECS.items():
            runtime = nodes[spec["classType"]]
            article = catalog.load_json(catalog.CONTENT / "articles" / "core" / spec["directory"] / "manifest.json")
            self.assertEqual(spec["module"], runtime["python_module"])
            self.assertEqual(spec["fingerprint"], catalog.schema_fingerprint(spec["classType"], runtime), article_id)
            self.assertEqual(spec["fingerprint"], article["editorial"]["schemaHash"])
            self.assertFalse(runtime.get("api_node", False))
            self.assertFalse(runtime.get("deprecated", False))
            self.assertEqual(["MASK"], runtime["output"])
        self.assertEqual(["alpha", "red", "green", "blue"], nodes["LoadImageMask"]["input"]["required"]["channel"][0])
        self.assertEqual(16777215, nodes["ImageColorToMask"]["input"]["required"]["color"][1]["max"])
        self.assertEqual(0.5, nodes["ThresholdMask"]["input"]["required"]["value"][1]["default"])
        replacements = json.dumps(catalog.load_json(REPLACEMENTS), ensure_ascii=False)
        for spec in SPECS.values():
            self.assertNotIn(spec["classType"], replacements)

    def test_pinned_source_and_model_free_semantics(self) -> None:
        nodes_source = SOURCE / "nodes.py"
        mask_source = SOURCE / "comfy_extras" / "nodes_mask.py"
        self.assertEqual(NODES_SHA256, hashlib.sha256(nodes_source.read_bytes()).hexdigest())
        self.assertEqual(MASK_SOURCE_SHA256, hashlib.sha256(mask_source.read_bytes()).hexdigest())
        nodes_text = nodes_source.read_text(encoding="utf-8")
        mask_text = mask_source.read_text(encoding="utf-8")
        for marker in (
            "(1.0 - components.alpha[..., -1])",
            "mask = 1. - torch.from_numpy(mask)",
            "channel_idx = {'R': 0, 'G': 1, 'B': 2}.get(c, 0)",
            "return (image_tensor[..., channel_idx].clone(),)",
        ):
            self.assertIn(marker, nodes_text)
        for marker in (
            "torch.clamp(image, 0, 1.0) * 255.0",
            "torch.where(temp == color, 1.0, 0).float()",
            "mask.reshape((-1, mask.shape[-2], mask.shape[-1]))",
            "mask[:, y:y + height, x:x + width]",
            "mask = (mask > value).float()",
        ):
            self.assertIn(marker, mask_text)

        image = torch.tensor([[[[-0.1, 1.2, 0.0], [0.0, 1.0, 0.0], [0.0, 254.49 / 255.0, 0.0]]]])
        packed = (torch.clamp(image, 0, 1) * 255).round().to(torch.int)
        packed = (packed[..., 0] << 16) + (packed[..., 1] << 8) + packed[..., 2]
        self.assertEqual([[1.0, 1.0, 0.0]], (packed == 0x00FF00).float().tolist()[0])
        mask = torch.arange(2 * 4 * 5, dtype=torch.float32).reshape(2, 4, 5)
        self.assertEqual((2, 2, 2), tuple(mask.reshape(-1, 4, 5)[:, 2:5, 3:7].shape))
        self.assertEqual([0.0, 0.0, 1.0], (torch.tensor([0.49, 0.5, 0.51]) > 0.5).float().tolist())

    def test_embedded_docs_and_exact_official_workflow_census(self) -> None:
        self.assertEqual(DOCS_SHA256, hashlib.sha256(DOCS.read_bytes()).hexdigest())
        with zipfile.ZipFile(DOCS) as archive:
            names = set(archive.namelist())
            for spec in SPECS.values():
                self.assertIn(f"comfyui_embedded_docs/docs/{spec['classType']}/en.md", names)
                self.assertIn(f"comfyui_embedded_docs/docs/{spec['classType']}/ru.md", names)
        self.assertEqual(WORKFLOWS_SHA256, hashlib.sha256(WORKFLOWS.read_bytes()).hexdigest())
        counts: Counter[str] = Counter()
        threshold_widgets: list[Any] = []
        json_count = root_count = subgraph_count = 0
        targets = {spec["classType"] for spec in SPECS.values()}
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
                        if not isinstance(node, dict) or node.get("type") not in targets:
                            continue
                        counts[node["type"]] += 1
                        if node["type"] == "ThresholdMask":
                            threshold_widgets.append(node.get("widgets_values"))
        self.assertEqual((512, 496, 272), (json_count, root_count, subgraph_count))
        self.assertEqual(Counter({"ThresholdMask": 1}), counts)
        self.assertEqual([[0.4099999999999999]], threshold_widgets)


if __name__ == "__main__":
    unittest.main()
