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


SPECS: dict[str, dict[str, str]] = {
    "core.image-rotate": {"directory": "image-rotate", "classType": "ImageRotate", "module": "comfy_extras.nodes_images", "fingerprint": "sha256:5a7773fc41cf91e10dc4bf3ff7322bd04f3e80aeaae5f154e8b68beee1414eb4", "recipe": "image-orientation-crop-preview"},
    "core.image-scale-by": {"directory": "image-scale-by", "classType": "ImageScaleBy", "module": "nodes", "fingerprint": "sha256:7bd2f5fb2dbbdb505aeb46be653d0f97a9a849fff4173b96d2c812eadc19d26a", "recipe": "image-scale-by-save"},
    "core.image-scale-to-total-pixels": {"directory": "image-scale-to-total-pixels", "classType": "ImageScaleToTotalPixels", "module": "comfy_extras.nodes_post_processing", "fingerprint": "sha256:72e008937e13a21596f5d4d931ed42bb23a5f0358442908fde9bbb3db6b9b0ed", "recipe": "image-scale-total-pixels-inspect"},
    "core.image-scale-to-max-dimension": {"directory": "image-scale-to-max-dimension", "classType": "ImageScaleToMaxDimension", "module": "comfy_extras.nodes_images", "fingerprint": "sha256:2e51f40f80764214dc9842b47d06a40c7f6bc73b45fc0bb52709d5db6d985cbe", "recipe": "image-scale-max-dimension-encode"},
}

INVENTORY = catalog.CONTENT / "runtime" / "comfyui-0.32.0.object-info.json"
REPLACEMENTS = catalog.CONTENT / "runtime" / "comfyui-0.32.0.node-replacements.json"
SOURCE = catalog.ROOT / ".comfyui-source-0.32.0"
DOCS = catalog.ROOT / ".upstream-cache" / "comfyui_embedded_docs-0.5.9-py3-none-any.whl"
WORKFLOWS = catalog.ROOT / ".upstream-cache" / "comfyui_workflow_templates_json-0.1.42-py3-none-any.whl"
DOCS_SHA256 = "30afae432a71c96aa59421d0f37388c66ff6572b8cbeee8ff045e4d5f84f896c"
WORKFLOWS_SHA256 = "242982d65e1c51ca03d892bc1009bb6843f457e7dfc0c20afe6438770b7a14a3"
NODES_SHA256 = "ffb2b5c999f47b720dbd81767c8fa4234255d939ba8dbb80ee64da9721c383ad"
POST_SOURCE_SHA256 = "6d28d37a0947947ff6bb724c4de465bacc012f7f23e11d916d7a5161953158aa"
IMAGES_SOURCE_SHA256 = "6f4b5cfdcc01ce59f4b034a7b00ec47da76f600c0dd2c8b251cd8014058cb0a9"


def scopes(payload: dict[str, Any]) -> Iterator[dict[str, Any]]:
    if isinstance(payload.get("nodes"), list):
        yield payload
    definitions = payload.get("definitions")
    if isinstance(definitions, dict):
        for subgraph in definitions.get("subgraphs", []):
            if isinstance(subgraph, dict):
                yield subgraph


class ImageScaleRotateContentTests(unittest.TestCase):
    def test_articles_recipes_ledgers_and_natural_russian(self) -> None:
        schemas = {name: catalog.load_json(catalog.CONTENT / "schemas" / name) for name in (
            "article.schema.v1.json", "recipe.schema.v1.json", "recipe-fragment.schema.v1.json", "article-research.schema.v1.json"
        )}
        article_ids = {catalog.load_json(path)["articleId"] for path in (catalog.CONTENT / "articles").rglob("manifest.json")}
        errors: list[str] = []
        for article_id, spec in SPECS.items():
            article_path = catalog.CONTENT / "articles" / "core" / spec["directory"] / "manifest.json"
            article = catalog.load_json(article_path)
            self.assertEqual([], catalog.json_schema_errors(article, schemas["article.schema.v1.json"]), article_id)
            catalog.validate_article(article_path, article, errors)
            self.assertEqual(("draft", "in_review"), (article["status"], article["editorial"]["state"]))
            self.assertEqual(10, len(re.findall(r"^## ", (article_path.parent / article["body"]).read_text(encoding="utf-8"), re.MULTILINE)), article_id)
            record = catalog.load_json(catalog.CONTENT / "research" / "reviews" / f"{article_id}.json")
            self.assertEqual([], catalog.json_schema_errors(record, schemas["article-research.schema.v1.json"]), article_id)
            self.assertEqual("fact_checked", record["state"])
            self.assertFalse(record["checks"]["exampleExecuted"])
            self.assertTrue(record["knownGaps"])
            recipe_path = catalog.CONTENT / "recipes" / spec["recipe"] / "recipe.json"
            recipe = catalog.load_json(recipe_path)
            self.assertEqual([], catalog.json_schema_errors(recipe, schemas["recipe.schema.v1.json"]), spec["recipe"])
            catalog.validate_recipe(recipe_path, recipe, article_ids, errors)
            self.assertNotIn("workflow", recipe)
            fragment_path = recipe_path.parent / recipe["fragment"]["path"]
            fragment = catalog.load_json(fragment_path)
            self.assertEqual([], catalog.json_schema_errors(fragment, schemas["recipe-fragment.schema.v1.json"]), spec["recipe"])
            catalog.validate_fragment(fragment_path, fragment, errors)
            prose = re.sub(r"`[^`]+`|https?://\S+", "", (recipe_path.parent / recipe["body"]).read_text(encoding="utf-8")).casefold()
            for untranslated in (" fragment", " workflow", " output-каталог", " batch", " bounding box"):
                self.assertNotIn(untranslated, prose, spec["recipe"])
        self.assertEqual([], errors)

    def test_runtime_fingerprints_options_and_replacements(self) -> None:
        nodes = catalog.object_info_nodes(catalog.load_json(INVENTORY))
        for article_id, spec in SPECS.items():
            runtime = nodes[spec["classType"]]
            article = catalog.load_json(catalog.CONTENT / "articles" / "core" / spec["directory"] / "manifest.json")
            self.assertEqual(spec["module"], runtime["python_module"])
            self.assertEqual(spec["fingerprint"], catalog.schema_fingerprint(spec["classType"], runtime), article_id)
            self.assertEqual(spec["fingerprint"], article["editorial"]["schemaHash"])
            self.assertFalse(runtime.get("api_node", False))
            self.assertFalse(runtime.get("deprecated", False))
            self.assertEqual(["IMAGE"], runtime["output"])
        self.assertEqual(["none", "90 degrees", "180 degrees", "270 degrees"], nodes["ImageRotate"]["input"]["required"]["rotation"][1]["options"])
        self.assertEqual(0.01, nodes["ImageScaleBy"]["input"]["required"]["scale_by"][1]["min"])
        self.assertEqual(256, nodes["ImageScaleToTotalPixels"]["input"]["required"]["resolution_steps"][1]["max"])
        self.assertEqual(["area", "lanczos", "bilinear", "nearest-exact", "bilinear", "bicubic"], nodes["ImageScaleToMaxDimension"]["input"]["required"]["upscale_method"][1]["options"])
        replacements = json.dumps(catalog.load_json(REPLACEMENTS), ensure_ascii=False)
        self.assertIn("ImageScaleBy", replacements)
        self.assertIn("ResizeImageMaskNode", replacements)
        self.assertIn("ResizeImagesByLongerEdge", replacements)
        self.assertIn("ImageScaleToMaxDimension", replacements)
        self.assertNotIn("ImageRotate", replacements)
        self.assertNotIn("ImageScaleToTotalPixels", replacements)

    def test_pinned_sources_and_dimension_math(self) -> None:
        nodes_path = SOURCE / "nodes.py"
        post_path = SOURCE / "comfy_extras" / "nodes_post_processing.py"
        images_path = SOURCE / "comfy_extras" / "nodes_images.py"
        self.assertEqual(NODES_SHA256, hashlib.sha256(nodes_path.read_bytes()).hexdigest())
        self.assertEqual(POST_SOURCE_SHA256, hashlib.sha256(post_path.read_bytes()).hexdigest())
        self.assertEqual(IMAGES_SOURCE_SHA256, hashlib.sha256(images_path.read_bytes()).hexdigest())
        nodes_source = nodes_path.read_text(encoding="utf-8")
        post_source = post_path.read_text(encoding="utf-8")
        images_source = images_path.read_text(encoding="utf-8")
        for marker in (
            "width = round(samples.shape[3] * scale_by)",
            "height = round(samples.shape[2] * scale_by)",
            'comfy.utils.common_upscale(samples, width, height, upscale_method, "disabled")',
        ):
            self.assertIn(marker, nodes_source)
        for marker in (
            "total = megapixels * 1024 * 1024",
            "scale_by = math.sqrt(total / (samples.shape[3] * samples.shape[2]))",
            "width = round(samples.shape[3] * scale_by / resolution_steps) * resolution_steps",
            "height = round(samples.shape[2] * scale_by / resolution_steps) * resolution_steps",
        ):
            self.assertIn(marker, post_source)
        for marker in (
            "image = torch.rot90(image, k=rotate_by, dims=[2, 1])",
            "width = round((width / height) * largest_size)",
            "height = round((height / width) * largest_size)",
        ):
            self.assertIn(marker, images_source)
        self.assertEqual((200, 100), (round(100 * 2), round(50 * 2)))
        self.assertEqual((1536, 1024), (round(1200 * (1536 / 1200)), round(800 * (1536 / 1200))))
        image = torch.arange(1 * 2 * 3 * 1).reshape(1, 2, 3, 1)
        self.assertEqual((1, 3, 2, 1), tuple(torch.rot90(image, k=1, dims=[2, 1]).shape))

    def test_docs_and_full_workflow_census(self) -> None:
        self.assertEqual(DOCS_SHA256, hashlib.sha256(DOCS.read_bytes()).hexdigest())
        with zipfile.ZipFile(DOCS) as archive:
            names = set(archive.namelist())
            for spec in SPECS.values():
                self.assertIn(f"comfyui_embedded_docs/docs/{spec['classType']}/en.md", names)
                self.assertIn(f"comfyui_embedded_docs/docs/{spec['classType']}/ru.md", names)
        self.assertEqual(WORKFLOWS_SHA256, hashlib.sha256(WORKFLOWS.read_bytes()).hexdigest())
        counts: Counter[str] = Counter()
        widgets: dict[str, Counter[tuple[Any, ...]]] = {spec["classType"]: Counter() for spec in SPECS.values()}
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
                        if node_type in widgets:
                            counts[node_type] += 1
                            widgets[node_type][tuple(node.get("widgets_values") or [])] += 1
        self.assertEqual((512, 496, 272), (json_count, root_count, subgraph_count))
        self.assertEqual(Counter({"ImageScaleToTotalPixels": 47, "ImageScaleBy": 13, "ImageScaleToMaxDimension": 7}), counts)
        self.assertEqual(Counter({("lanczos", 0.5): 9, ("nearest-exact", 4): 1, ("lanczos", 2): 1, ("lanczos", 4): 1, ("nearest-exact", 0.5): 1}), widgets["ImageScaleBy"])
        self.assertEqual(Counter({("area", 1536): 3, ("lanczos", 640): 2, ("area", 512): 1, ("lanczos", 1024): 1}), widgets["ImageScaleToMaxDimension"])
        self.assertEqual(47, sum(widgets["ImageScaleToTotalPixels"].values()))
        self.assertEqual(2, widgets["ImageScaleToTotalPixels"][("nearest-exact", 1, 16)])
        self.assertEqual(Counter(), widgets["ImageRotate"])


if __name__ == "__main__":
    unittest.main()
