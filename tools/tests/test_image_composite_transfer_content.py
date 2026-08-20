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
    "core.color-transfer": ("color-transfer", "ColorTransfer", "comfy_extras.nodes_post_processing", "sha256:53738c4278ad18c35588c36d5a61c56563812084d72b414646c3f20faf5f5f3b", "color-transfer-preview"),
    "core.morphology": ("morphology", "Morphology", "comfy_extras.nodes_morphology", "sha256:edc82849b9472b52f257b0018548a9c0e3971b950a7da1b9594349d9b5813641", "morphology-close-mask"),
    "core.image-stitch": ("image-stitch", "ImageStitch", "comfy_extras.nodes_images", "sha256:eda709cd60535e4ab0fa4dae964e9c55d197a65e15ae777c6c90aa854bba47b0", "four-image-stitch-grid"),
    "core.porter-duff-image-composite": ("porter-duff-image-composite", "PorterDuffImageComposite", "comfy_extras.nodes_compositing", "sha256:ecffa7f29d455841a4e892436f92635a883b839716fedb3bd5cc333d7c73af7c", "porter-duff-src-over-preview"),
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


class ImageCompositeTransferContentTests(unittest.TestCase):
    def test_articles_recipes_ledgers_and_language(self) -> None:
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
            self.assertEqual(10, len(re.findall(r"^## ", (path.parent / article["body"]).read_text(encoding="utf-8"), re.MULTILINE)), article_id)
            ledger = catalog.load_json(catalog.CONTENT / "research" / "reviews" / f"{article_id}.json")
            self.assertEqual([], catalog.json_schema_errors(ledger, schemas["article-research.schema.v1.json"]), article_id)
            self.assertEqual("fact_checked", ledger["state"])
            self.assertFalse(ledger["checks"]["exampleExecuted"])
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
            for phrase in ("synthetic tensor", "full fragment", "official topology", "rgb batch", " preview"):
                self.assertNotIn(phrase, prose, recipe_id)
        self.assertEqual([], errors)

    def test_runtime_contracts_and_replacements(self) -> None:
        nodes = catalog.object_info_nodes(catalog.load_json(INVENTORY))
        for article_id, (directory, class_type, module, fingerprint, _recipe_id) in SPECS.items():
            runtime = nodes[class_type]
            article = catalog.load_json(catalog.CONTENT / "articles" / "core" / directory / "manifest.json")
            self.assertEqual(module, runtime["python_module"])
            self.assertEqual(fingerprint, catalog.schema_fingerprint(class_type, runtime), article_id)
            self.assertEqual(fingerprint, article["editorial"]["schemaHash"])
            self.assertFalse(runtime.get("api_node", False))
            self.assertFalse(runtime.get("deprecated", False))
        self.assertEqual(["reinhard_lab", "mkl_lab", "histogram"], nodes["ColorTransfer"]["input"]["required"]["method"][1]["options"])
        self.assertEqual(["erode", "dilate", "open", "close", "gradient", "bottom_hat", "top_hat"], nodes["Morphology"]["input"]["required"]["operation"][1]["options"])
        self.assertEqual(["right", "down", "left", "up"], nodes["ImageStitch"]["input"]["required"]["direction"][1]["options"])
        self.assertEqual(18, len(nodes["PorterDuffImageComposite"]["input"]["required"]["mode"][1]["options"]))
        replacements = json.dumps(catalog.load_json(REPLACEMENTS), ensure_ascii=False)
        for spec in SPECS.values():
            self.assertNotIn(spec[1], replacements)

    def test_pinned_sources_and_basic_math(self) -> None:
        files = {
            "post": (SOURCE / "comfy_extras" / "nodes_post_processing.py", "6d28d37a0947947ff6bb724c4de465bacc012f7f23e11d916d7a5161953158aa"),
            "morph": (SOURCE / "comfy_extras" / "nodes_morphology.py", "09df35ff4a2775b064174014546c988b3dc9515120728d5b9df47862bd92ea53"),
            "images": (SOURCE / "comfy_extras" / "nodes_images.py", "6f4b5cfdcc01ce59f4b034a7b00ec47da76f600c0dd2c8b251cd8014058cb0a9"),
            "compose": (SOURCE / "comfy_extras" / "nodes_compositing.py", "e500fc0d5accdb396f3e0f346a36e69ee9d09a17d0e3044f9cde3d443aa99dfc"),
        }
        text = {}
        for key, (path, digest) in files.items():
            self.assertEqual(digest, hashlib.sha256(path.read_bytes()).hexdigest())
            text[key] = path.read_text(encoding="utf-8")
        for marker in ("class ColorTransfer", '"reinhard_lab"', '"target_frame"'):
            self.assertIn(marker, text["post"])
        for marker in ("from kornia.morphology import dilation, erosion", "output = dilation(image_k, kernel)", "output = erosion(image_k, kernel)", "kernel_size"):
            self.assertIn(marker, text["morph"])
        for marker in ("class ImageStitch", 'if direction in ["left", "right"]', 'images = [image2, image1] if direction in ["left", "up"] else [image1, image2]', "spacing_width"):
            self.assertIn(marker, text["images"])
        for marker in ("class PorterDuffImageComposite", "PorterDuffMode", "porter_duff_composite"):
            self.assertIn(marker, text["compose"])
        source = torch.tensor([[[0.8, 0.2, 0.1]]])
        destination = torch.tensor([[[0.1, 0.2, 0.8]]])
        source_alpha = torch.tensor([[[0.5]]])
        destination_alpha = torch.tensor([[[1.0]]])
        out_alpha = source_alpha + destination_alpha * (1 - source_alpha)
        out_color = (source * source_alpha + destination * destination_alpha * (1 - source_alpha)) / out_alpha
        self.assertTrue(torch.allclose(out_color, torch.tensor([[[0.45, 0.2, 0.45]]])))

    def test_docs_and_exact_workflow_census(self) -> None:
        self.assertEqual("30afae432a71c96aa59421d0f37388c66ff6572b8cbeee8ff045e4d5f84f896c", hashlib.sha256(DOCS.read_bytes()).hexdigest())
        with zipfile.ZipFile(DOCS) as archive:
            names = set(archive.namelist())
            for spec in SPECS.values():
                self.assertIn(f"comfyui_embedded_docs/docs/{spec[1]}/en.md", names)
                self.assertIn(f"comfyui_embedded_docs/docs/{spec[1]}/ru.md", names)
        self.assertEqual("242982d65e1c51ca03d892bc1009bb6843f457e7dfc0c20afe6438770b7a14a3", hashlib.sha256(WORKFLOWS.read_bytes()).hexdigest())
        targets = {spec[1] for spec in SPECS.values()}
        counts: Counter[str] = Counter(); widgets = {target: Counter() for target in targets}
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
                        node_type = node.get("type") if isinstance(node, dict) else None
                        if node_type in targets:
                            counts[node_type] += 1
                            widgets[node_type][tuple(node.get("widgets_values") or [])] += 1
        self.assertEqual((512, 496, 272, 8120), (json_count, root_count, subgraph_count, node_count))
        self.assertEqual(Counter({"ImageStitch": 14, "ColorTransfer": 2}), counts)
        self.assertEqual(Counter({("reinhard_lab", "per_frame", 1): 2}), widgets["ColorTransfer"])
        self.assertEqual(Counter({("right", True, 0, "white"): 9, ("right", True, 8, "white"): 2, ("up", True, 8, "white"): 1, ("right", True, 20, "white"): 1, ("down", True, 0, "white"): 1}), widgets["ImageStitch"])
        self.assertEqual(Counter(), widgets["Morphology"])
        self.assertEqual(Counter(), widgets["PorterDuffImageComposite"])


if __name__ == "__main__":
    unittest.main()
