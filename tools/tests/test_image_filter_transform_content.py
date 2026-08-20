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
    "core.image-blur": {"directory": "image-blur", "classType": "ImageBlur", "module": "comfy_extras.nodes_post_processing", "fingerprint": "sha256:809db4d281d055fe6477542ee50fa38d47be23709495eb659da288fc35d3d861", "recipe": "blur-canny-control-map"},
    "core.image-sharpen": {"directory": "image-sharpen", "classType": "ImageSharpen", "module": "comfy_extras.nodes_post_processing", "fingerprint": "sha256:2a6bdeb8f8bc6eb8b58c3891ac5fc8198e97e9ca4c01fc7b4c572f538720250e", "recipe": "sharpen-preview"},
    "core.image-blend": {"directory": "image-blend", "classType": "ImageBlend", "module": "comfy_extras.nodes_post_processing", "fingerprint": "sha256:ded4213876b78139868438a7741d597fee0116bc3115ad55d5595c522c8231af", "recipe": "blend-pose-overlay"},
    "core.image-flip": {"directory": "image-flip", "classType": "ImageFlip", "module": "comfy_extras.nodes_images", "fingerprint": "sha256:a83bf972993cfda2a48c4398d9d95272a22e6e19e07948b2a14565cbb78455c4", "recipe": "image-orientation-crop-preview"},
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
HELPERS_SOURCE_SHA256 = "6e9e963b1538bdec3370721cfb16c02aa88a2891dafbbd9dd007c190f68ca935"


def scopes(payload: dict[str, Any]) -> Iterator[dict[str, Any]]:
    if isinstance(payload.get("nodes"), list):
        yield payload
    definitions = payload.get("definitions")
    if isinstance(definitions, dict):
        for subgraph in definitions.get("subgraphs", []):
            if isinstance(subgraph, dict):
                yield subgraph


class ImageFilterTransformContentTests(unittest.TestCase):
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
            for untranslated in (" fragment", " workflow", " preview", " bounding box", " low threshold", " official "):
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
            self.assertEqual(["IMAGE"], runtime["output"])
        self.assertEqual(["normal", "multiply", "screen", "overlay", "soft_light", "difference"], nodes["ImageBlend"]["input"]["required"]["blend_mode"][1]["options"])
        self.assertEqual(["x-axis: vertically", "y-axis: horizontally"], nodes["ImageFlip"]["input"]["required"]["flip_method"][1]["options"])
        self.assertEqual(31, nodes["ImageBlur"]["input"]["required"]["blur_radius"][1]["max"])
        replacements = json.dumps(catalog.load_json(REPLACEMENTS), ensure_ascii=False)
        for spec in SPECS.values():
            self.assertNotIn(spec["classType"], replacements)

    def test_pinned_sources_and_model_free_formulas(self) -> None:
        post_path = SOURCE / "comfy_extras" / "nodes_post_processing.py"
        images_path = SOURCE / "comfy_extras" / "nodes_images.py"
        helpers_path = SOURCE / "node_helpers.py"
        self.assertEqual(POST_SOURCE_SHA256, hashlib.sha256(post_path.read_bytes()).hexdigest())
        self.assertEqual(IMAGES_SOURCE_SHA256, hashlib.sha256(images_path.read_bytes()).hexdigest())
        self.assertEqual(HELPERS_SOURCE_SHA256, hashlib.sha256(helpers_path.read_bytes()).hexdigest())
        post = post_path.read_text(encoding="utf-8")
        images = images_path.read_text(encoding="utf-8")
        helpers = helpers_path.read_text(encoding="utf-8")
        for marker in (
            "return (g / g.sum()).to(dtype)",
            "F.pad(image, (blur_radius,blur_radius,blur_radius,blur_radius), 'reflect')",
            "groups=channels",
            "kernel = gaussian_kernel(kernel_size, sigma, device=image.device, dtype=image.dtype) * -(alpha*10)",
            "kernel[center, center] = kernel[center, center] - kernel.sum() + 1.0",
            "return img1 - img2",
            "image1 * (1 - blend_factor) + blended_image * blend_factor",
            "torch.clamp(blended_image, 0, 1)",
        ):
            self.assertIn(marker, post)
        self.assertIn("image = torch.flip(image, dims=[1])", images)
        self.assertIn("image = torch.flip(image, dims=[2])", images)
        self.assertIn("def image_alpha_fix", helpers)

        first = torch.tensor([0.2, 0.8])
        second = torch.tensor([0.6, 0.1])
        self.assertTrue(torch.allclose(first - second, torch.tensor([-0.4, 0.7])))
        self.assertTrue(torch.allclose(first * 0.5 + second * 0.5, torch.tensor([0.4, 0.45])))
        image = torch.tensor([[[[1.0], [2.0]], [[3.0], [4.0]]]])
        self.assertEqual([[[[3.0], [4.0]], [[1.0], [2.0]]]], torch.flip(image, dims=[1]).tolist())
        self.assertEqual([[[[2.0], [1.0]], [[4.0], [3.0]]]], torch.flip(image, dims=[2]).tolist())

    def test_docs_and_exact_official_workflow_census(self) -> None:
        self.assertEqual(DOCS_SHA256, hashlib.sha256(DOCS.read_bytes()).hexdigest())
        with zipfile.ZipFile(DOCS) as archive:
            names = set(archive.namelist())
            for spec in SPECS.values():
                self.assertIn(f"comfyui_embedded_docs/docs/{spec['classType']}/en.md", names)
                self.assertIn(f"comfyui_embedded_docs/docs/{spec['classType']}/ru.md", names)
        self.assertEqual(WORKFLOWS_SHA256, hashlib.sha256(WORKFLOWS.read_bytes()).hexdigest())
        counts: Counter[str] = Counter()
        widgets: dict[str, list[Any]] = {spec["classType"]: [] for spec in SPECS.values()}
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
                            widgets[node_type].append(node.get("widgets_values"))
        self.assertEqual((512, 496, 272), (json_count, root_count, subgraph_count))
        self.assertEqual(Counter({"ImageBlur": 2, "ImageBlend": 2}), counts)
        self.assertEqual([[31, 1], [31, 1]], widgets["ImageBlur"])
        self.assertEqual([[0.5, "normal"], [0.5, "normal"]], widgets["ImageBlend"])
        self.assertEqual([], widgets["ImageSharpen"])
        self.assertEqual([], widgets["ImageFlip"])


if __name__ == "__main__":
    unittest.main()
