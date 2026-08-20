from __future__ import annotations

import hashlib
import json
import re
import unittest
import zipfile
from collections import Counter
from typing import Any, Iterator

import numpy as np
import torch

from tools import catalog


SPECS = {
    "core.center-crop-images": ("center-crop-images", "CenterCropImages", "comfy_extras.nodes_dataset", "sha256:1114d93311ebcf87a55e8def1ec5c25cbe032bd86bdb7babdcc6c347e1433146", "center-crop-preview"),
    "core.random-crop-images": ("random-crop-images", "RandomCropImages", "comfy_extras.nodes_dataset", "sha256:df09f1018e467a499417cad3d3a343cef18973a1c67a24c22dd30a41187fc496", "random-crop-preview"),
    "core.crop-by-bboxes": ("crop-by-bboxes", "CropByBBoxes", "comfy_extras.nodes_sdpose", "sha256:803a5322612840080886cd30c3a36dfee807414438342496e6432276b7aec248", "crop-bbox-preview"),
    "core.layers-from-bounding-boxes": ("layers-from-bounding-boxes", "LayersFromBoundingBoxes", "comfy_extras.nodes_compositor", "sha256:9c5070fbe565ef4841aafb9de4fca7d8310f9c311a5a6bc21ba06fbba26e9f20", "layers-from-bbox"),
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


class ImageBboxCropContentTests(unittest.TestCase):
    def test_content_contracts_and_natural_russian(self) -> None:
        schema_names = ("article.schema.v1.json", "recipe.schema.v1.json", "recipe-fragment.schema.v1.json", "article-research.schema.v1.json")
        schemas = {name: catalog.load_json(catalog.CONTENT / "schemas" / name) for name in schema_names}
        article_ids = {catalog.load_json(path)["articleId"] for path in (catalog.CONTENT / "articles").rglob("manifest.json")}
        errors: list[str] = []
        for article_id, (directory, _class_type, _module, _fingerprint, recipe_id) in SPECS.items():
            article_path = catalog.CONTENT / "articles" / "core" / directory / "manifest.json"
            article = catalog.load_json(article_path)
            self.assertEqual([], catalog.json_schema_errors(article, schemas["article.schema.v1.json"]), article_id)
            catalog.validate_article(article_path, article, errors)
            self.assertEqual(("draft", "in_review"), (article["status"], article["editorial"]["state"]))
            self.assertEqual(10, len(re.findall(r"^## ", (article_path.parent / article["body"]).read_text(encoding="utf-8"), re.MULTILINE)))
            ledger = catalog.load_json(catalog.CONTENT / "research" / "reviews" / f"{article_id}.json")
            self.assertEqual([], catalog.json_schema_errors(ledger, schemas["article-research.schema.v1.json"]), article_id)
            self.assertEqual("fact_checked", ledger["state"])
            self.assertFalse(ledger["checks"]["exampleExecuted"])
            self.assertIn("Человеческое утверждение", " ".join(ledger["knownGaps"]))
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
            for phrase in ("official workflow", "full fragment", "synthetic batch", "backend crop", "target"):
                self.assertNotIn(phrase, prose, recipe_id)
        self.assertEqual([], errors)

    def test_runtime_identity_options_and_no_replacements(self) -> None:
        nodes = catalog.object_info_nodes(catalog.load_json(INVENTORY))
        for article_id, (directory, class_type, module, fingerprint, _recipe_id) in SPECS.items():
            runtime = nodes[class_type]
            article = catalog.load_json(catalog.CONTENT / "articles" / "core" / directory / "manifest.json")
            self.assertEqual(module, runtime["python_module"])
            self.assertEqual(fingerprint, catalog.schema_fingerprint(class_type, runtime), article_id)
            self.assertEqual(fingerprint, article["editorial"]["schemaHash"])
            self.assertFalse(runtime.get("api_node", False))
            self.assertFalse(runtime.get("deprecated", False))
        self.assertEqual(18446744073709551615, nodes["RandomCropImages"]["input"]["required"]["seed"][1]["max"])
        self.assertEqual(["stretch", "pad"], nodes["CropByBBoxes"]["input"]["required"]["keep_aspect"][1]["options"])
        self.assertEqual(["BOUNDING_BOX,ARRAY,STRING", {"tooltip": nodes["LayersFromBoundingBoxes"]["input"]["required"]["bboxes"][1]["tooltip"]}], nodes["LayersFromBoundingBoxes"]["input"]["required"]["bboxes"])
        replacements = json.dumps(catalog.load_json(REPLACEMENTS), ensure_ascii=False)
        for spec in SPECS.values():
            self.assertNotIn(spec[1], replacements)

    def test_pinned_sources_and_edge_math(self) -> None:
        paths = {
            "dataset": SOURCE / "comfy_extras" / "nodes_dataset.py",
            "sdpose": SOURCE / "comfy_extras" / "nodes_sdpose.py",
            "compositor": SOURCE / "comfy_extras" / "nodes_compositor.py",
        }
        self.assertEqual("1bde15deb4402cf11d9e57d8bf9e1a3fdab3c34e7a648b9aa51d4d346d18915a", hashlib.sha256(paths["dataset"].read_bytes()).hexdigest())
        self.assertEqual("eb9ad7181c8d236a7531e238d7d0e1e2deab726085a30556203bd2c043b4812c", hashlib.sha256(paths["sdpose"].read_bytes()).hexdigest())
        self.assertEqual("f2bf266dea48d468df26be2fc7d4b1db0bbd62a903fa08a2aa7c38b54226b6b8", hashlib.sha256(paths["compositor"].read_bytes()).hexdigest())
        dataset = paths["dataset"].read_text(encoding="utf-8")
        sdpose = paths["sdpose"].read_text(encoding="utf-8")
        compositor = paths["compositor"].read_text(encoding="utf-8")
        for marker in ("np.random.seed(seed % (2**32 - 1))", "left = max(0, (img.width - width) // 2)", "for i in range(images.shape[0])"):
            self.assertIn(marker, dataset)
        for marker in ("frame_bboxes = bboxes[min(frame_idx, len(bboxes) - 1)]", "if not frame_bboxes:", 'if keep_aspect == "pad"'):
            self.assertIn(marker, sdpose)
        for marker in ("box = boxes[index] if index < len(boxes) else {}", 'rect = meta.get("content_rect")', 'document: dict = {"version": 1, "layers": items}'):
            self.assertIn(marker, compositor)
        self.assertEqual((1, 1, 5, 4), (max(0, (7 - 4) // 2), max(0, (5 - 3) // 2), min(7, 1 + 4), min(5, 1 + 3)))
        np.random.seed(42 % (2**32 - 1)); first = (np.random.randint(0, 4), np.random.randint(0, 3))
        np.random.seed((42 + (2**32 - 1)) % (2**32 - 1)); second = (np.random.randint(0, 4), np.random.randint(0, 3))
        self.assertEqual(first, second)
        image = torch.zeros(2, 5, 7, 3)
        self.assertEqual((2, 5, 7, 3), tuple(image.shape))

    def test_docs_and_exhaustive_workflow_zero_census(self) -> None:
        self.assertEqual("30afae432a71c96aa59421d0f37388c66ff6572b8cbeee8ff045e4d5f84f896c", hashlib.sha256(DOCS.read_bytes()).hexdigest())
        with zipfile.ZipFile(DOCS) as archive:
            names = set(archive.namelist())
            for class_type in ("CenterCropImages", "RandomCropImages", "CropByBBoxes"):
                self.assertIn(f"comfyui_embedded_docs/docs/{class_type}/en.md", names)
                self.assertIn(f"comfyui_embedded_docs/docs/{class_type}/ru.md", names)
            self.assertNotIn("comfyui_embedded_docs/docs/LayersFromBoundingBoxes/en.md", names)
        self.assertEqual("242982d65e1c51ca03d892bc1009bb6843f457e7dfc0c20afe6438770b7a14a3", hashlib.sha256(WORKFLOWS.read_bytes()).hexdigest())
        targets = {spec[1] for spec in SPECS.values()}
        counts: Counter[str] = Counter()
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
