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
    "core.image-quantize": {"directory": "image-quantize", "classType": "ImageQuantize", "module": "comfy_extras.nodes_post_processing", "fingerprint": "sha256:39ab957f6182ce6b869b86c46e421697028e246802b9fdebe49135d2257a7a5d", "recipe": "quantize-palette-preview"},
    "core.image-add-noise": {"directory": "image-add-noise", "classType": "ImageAddNoise", "module": "comfy_extras.nodes_images", "fingerprint": "sha256:e9b75e3699bf89d9902068fe02058266c5a92eb1b4883b511da9154942988097", "recipe": "add-noise-preview"},
    "core.image-rgb-to-yuv": {"directory": "image-rgb-to-yuv", "classType": "ImageRGBToYUV", "module": "comfy_extras.nodes_morphology", "fingerprint": "sha256:5f2893015bc1e165e482764604e13eedf2fcf252681178a5793ac1f88931a1e5", "recipe": "yuv-luma-preview"},
    "core.image-yuv-to-rgb": {"directory": "image-yuv-to-rgb", "classType": "ImageYUVToRGB", "module": "comfy_extras.nodes_morphology", "fingerprint": "sha256:9ad439b60501810f5a9a60d13eec0d203c6c8d89368716db95469c7f6db16c3b", "recipe": "yuv-roundtrip"},
}

INVENTORY = catalog.CONTENT / "runtime" / "comfyui-0.32.0.object-info.json"
REPLACEMENTS = catalog.CONTENT / "runtime" / "comfyui-0.32.0.node-replacements.json"
SOURCE = catalog.ROOT / ".comfyui-source-0.32.0"
DOCS = catalog.ROOT / ".upstream-cache" / "comfyui_embedded_docs-0.5.9-py3-none-any.whl"
WORKFLOWS = catalog.ROOT / ".upstream-cache" / "comfyui_workflow_templates_json-0.1.42-py3-none-any.whl"
DOCS_SHA256 = "30afae432a71c96aa59421d0f37388c66ff6572b8cbeee8ff045e4d5f84f896c"
WORKFLOWS_SHA256 = "242982d65e1c51ca03d892bc1009bb6843f457e7dfc0c20afe6438770b7a14a3"
POST_SOURCE_SHA256 = "6d28d37a0947947ff6bb724c4de465bacc012f7f23e11d916d7a5161953158aa"
IMAGES_SOURCE_SHA256 = "6f4b5cfdcc01ce59f4b034a7b00ec47da76f600c0dd2c8b251cd8014058cb0a9"
MORPH_SOURCE_SHA256 = "09df35ff4a2775b064174014546c988b3dc9515120728d5b9df47862bd92ea53"


def scopes(payload: dict[str, Any]) -> Iterator[dict[str, Any]]:
    if isinstance(payload.get("nodes"), list):
        yield payload
    definitions = payload.get("definitions")
    if isinstance(definitions, dict):
        for subgraph in definitions.get("subgraphs", []):
            if isinstance(subgraph, dict):
                yield subgraph


class ImageColorNoiseContentTests(unittest.TestCase):
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
            for untranslated in (" fragment", " preview", " official ", " output", " tensor path", " round-trip", " batch", " alpha "):
                self.assertNotIn(untranslated, prose, spec["recipe"])
        self.assertEqual([], errors)

    def test_runtime_fingerprints_ports_options_and_replacements(self) -> None:
        nodes = catalog.object_info_nodes(catalog.load_json(INVENTORY))
        for article_id, spec in SPECS.items():
            runtime = nodes[spec["classType"]]
            article = catalog.load_json(catalog.CONTENT / "articles" / "core" / spec["directory"] / "manifest.json")
            self.assertEqual(spec["module"], runtime["python_module"])
            self.assertEqual(spec["fingerprint"], catalog.schema_fingerprint(spec["classType"], runtime), article_id)
            self.assertEqual(spec["fingerprint"], article["editorial"]["schemaHash"])
            self.assertFalse(runtime.get("api_node", False))
            self.assertFalse(runtime.get("deprecated", False))
        self.assertEqual(["none", "floyd-steinberg", "bayer-2", "bayer-4", "bayer-8", "bayer-16"], nodes["ImageQuantize"]["input"]["required"]["dither"][1]["options"])
        self.assertEqual(18446744073709551615, nodes["ImageAddNoise"]["input"]["required"]["seed"][1]["max"])
        self.assertEqual(["IMAGE", "IMAGE", "IMAGE"], nodes["ImageRGBToYUV"]["output"])
        self.assertEqual({"Y", "U", "V"}, set(nodes["ImageYUVToRGB"]["input"]["required"]))
        replacements = json.dumps(catalog.load_json(REPLACEMENTS), ensure_ascii=False)
        for spec in SPECS.values():
            self.assertNotIn(spec["classType"], replacements)

    def test_pinned_sources_and_model_free_semantics(self) -> None:
        post_path = SOURCE / "comfy_extras" / "nodes_post_processing.py"
        images_path = SOURCE / "comfy_extras" / "nodes_images.py"
        morph_path = SOURCE / "comfy_extras" / "nodes_morphology.py"
        self.assertEqual(POST_SOURCE_SHA256, hashlib.sha256(post_path.read_bytes()).hexdigest())
        self.assertEqual(IMAGES_SOURCE_SHA256, hashlib.sha256(images_path.read_bytes()).hexdigest())
        self.assertEqual(MORPH_SOURCE_SHA256, hashlib.sha256(morph_path.read_bytes()).hexdigest())
        post = post_path.read_text(encoding="utf-8")
        images = images_path.read_text(encoding="utf-8")
        morph = morph_path.read_text(encoding="utf-8")
        for marker in (
            "for b in range(batch_size):",
            "Image.fromarray((image[b] * 255).to(torch.uint8).numpy(), mode='RGB')",
            "pal_im = im.quantize(colors=colors)",
            'elif dither.startswith("bayer"):',
            "quantized_array = torch.tensor(np.array(quantized_image.convert(\"RGB\"))).float() / 255",
        ):
            self.assertIn(marker, post)
        for marker in (
            "generator = torch.manual_seed(seed)",
            'torch.randn(image.size(), generator=generator, device="cpu").to(image)',
            "torch.clip((image + strength *",
        ):
            self.assertIn(marker, images)
        for marker in (
            "kornia.color.rgb_to_ycbcr",
            "out[..., 0:1].expand_as(image)",
            "torch.mean(Y, dim=-1, keepdim=True)",
            "kornia.color.ycbcr_to_rgb",
        ):
            self.assertIn(marker, morph)

        image = torch.full((2, 3, 4, 3), 0.5)
        generator = torch.manual_seed(123)
        first = torch.clip(image + 0.03 * torch.randn(image.size(), generator=generator, device="cpu"), 0, 1)
        generator = torch.manual_seed(123)
        second = torch.clip(image + 0.03 * torch.randn(image.size(), generator=generator, device="cpu"), 0, 1)
        self.assertTrue(torch.equal(first, second))
        self.assertFalse(torch.equal(first[0], first[1]))
        self.assertGreaterEqual(float(first.min()), 0.0)
        self.assertLessEqual(float(first.max()), 1.0)
        component = torch.tensor([[[[0.2, 0.4, 0.6]]]])
        self.assertAlmostEqual(0.4, float(torch.mean(component, dim=-1, keepdim=True).item()))

    def test_docs_and_full_zero_workflow_census(self) -> None:
        self.assertEqual(DOCS_SHA256, hashlib.sha256(DOCS.read_bytes()).hexdigest())
        with zipfile.ZipFile(DOCS) as archive:
            names = set(archive.namelist())
            for spec in SPECS.values():
                self.assertIn(f"comfyui_embedded_docs/docs/{spec['classType']}/en.md", names)
                self.assertIn(f"comfyui_embedded_docs/docs/{spec['classType']}/ru.md", names)
        self.assertEqual(WORKFLOWS_SHA256, hashlib.sha256(WORKFLOWS.read_bytes()).hexdigest())
        counts: Counter[str] = Counter()
        targets = {spec["classType"] for spec in SPECS.values()}
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
                        if isinstance(node, dict) and node.get("type") in targets:
                            counts[node["type"]] += 1
        self.assertEqual((512, 496, 272), (json_count, root_count, subgraph_count))
        self.assertEqual(Counter(), counts)


if __name__ == "__main__":
    unittest.main()
