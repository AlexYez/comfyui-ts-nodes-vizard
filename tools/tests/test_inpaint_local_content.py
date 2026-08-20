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
    "core.inpaint-model-conditioning": {"directory": "inpaint-model-conditioning", "classType": "InpaintModelConditioning", "module": "nodes", "fingerprint": "sha256:b53b99f14cb2fc6f36ee7d6e31c182738011e4ea8367bca4ec35f7212cf95218", "recipe": "outpaint-conditioning"},
    "core.vae-encode-for-inpaint": {"directory": "vae-encode-for-inpaint", "classType": "VAEEncodeForInpaint", "module": "nodes", "fingerprint": "sha256:6abd61d86bbc9f9ae330df2408ef34cb0315e1d1606827cbb2f04a2aee7a782a", "recipe": "inpaint-latent"},
    "core.image-pad-for-outpaint": {"directory": "image-pad-for-outpaint", "classType": "ImagePadForOutpaint", "module": "nodes", "fingerprint": "sha256:efdf03cd855409bd2b638ec8e61590fa8574861a8e8c9bcf61d05a1d5e8e2fa4", "recipe": "outpaint-conditioning"},
    "core.latent-composite-masked": {"directory": "latent-composite-masked", "classType": "LatentCompositeMasked", "module": "comfy_extras.nodes_mask", "fingerprint": "sha256:5a454e0177960eefc58b7e3f458d444614a052a8f13b4e56675d16d33586d0d8", "recipe": "latent-composite-preview"},
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


class InpaintLocalContentTests(unittest.TestCase):
    def test_articles_recipes_ledgers_and_natural_russian(self) -> None:
        schemas = {name: catalog.load_json(catalog.CONTENT / "schemas" / name) for name in (
            "article.schema.v1.json", "recipe.schema.v1.json", "recipe-fragment.schema.v1.json", "article-research.schema.v1.json"
        )}
        article_ids = {catalog.load_json(path)["articleId"] for path in (catalog.CONTENT / "articles").rglob("manifest.json")}
        errors: list[str] = []
        checked_recipes: set[str] = set()
        for article_id, spec in SPECS.items():
            path = catalog.CONTENT / "articles" / "core" / spec["directory"] / "manifest.json"
            article = catalog.load_json(path)
            self.assertEqual([], catalog.json_schema_errors(article, schemas["article.schema.v1.json"]), article_id)
            catalog.validate_article(path, article, errors)
            self.assertEqual(("draft", "in_review"), (article["status"], article["editorial"]["state"]))
            self.assertEqual(10, len(re.findall(r"^## ", (path.parent / article["body"]).read_text(encoding="utf-8"), re.MULTILINE)))
            record = catalog.load_json(catalog.CONTENT / "research" / "reviews" / f"{article_id}.json")
            self.assertEqual([], catalog.json_schema_errors(record, schemas["article-research.schema.v1.json"]), article_id)
            self.assertEqual("fact_checked", record["state"])
            self.assertFalse(record["checks"]["exampleExecuted"])
            self.assertTrue(record["knownGaps"])
            if spec["recipe"] in checked_recipes:
                continue
            checked_recipes.add(spec["recipe"])
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
            for untranslated in (" fragment", " workflow", " preview", " padding", " loader", " positive ", " negative ", " masked latent"):
                self.assertNotIn(untranslated, prose, spec["recipe"])
        self.assertEqual([], errors)

    def test_runtime_fingerprints_ports_and_replacements(self) -> None:
        nodes = catalog.object_info_nodes(catalog.load_json(INVENTORY))
        for article_id, spec in SPECS.items():
            runtime = nodes[spec["classType"]]
            article = catalog.load_json(catalog.CONTENT / "articles" / "core" / spec["directory"] / "manifest.json")
            self.assertEqual(spec["module"], runtime["python_module"])
            self.assertEqual(spec["fingerprint"], catalog.schema_fingerprint(spec["classType"], runtime), article_id)
            self.assertEqual(spec["fingerprint"], article["editorial"]["schemaHash"])
            self.assertFalse(runtime.get("api_node", False))
            self.assertFalse(runtime.get("deprecated", False))
        self.assertEqual(["CONDITIONING", "CONDITIONING", "LATENT"], nodes["InpaintModelConditioning"]["output"])
        self.assertEqual(True, nodes["InpaintModelConditioning"]["input"]["required"]["noise_mask"][1]["default"])
        self.assertEqual(6, nodes["VAEEncodeForInpaint"]["input"]["required"]["grow_mask_by"][1]["default"])
        self.assertIn("mask", nodes["LatentCompositeMasked"]["input"]["optional"])
        replacements = json.dumps(catalog.load_json(REPLACEMENTS), ensure_ascii=False)
        for spec in SPECS.values():
            self.assertNotIn(spec["classType"], replacements)

    def test_pinned_source_and_model_free_semantics(self) -> None:
        nodes_path = SOURCE / "nodes.py"
        mask_path = SOURCE / "comfy_extras" / "nodes_mask.py"
        self.assertEqual(NODES_SHA256, hashlib.sha256(nodes_path.read_bytes()).hexdigest())
        self.assertEqual(MASK_SOURCE_SHA256, hashlib.sha256(mask_path.read_bytes()).hexdigest())
        nodes_source = nodes_path.read_text(encoding="utf-8")
        mask_source = mask_path.read_text(encoding="utf-8")
        for marker in (
            "downscale_ratio = vae.spacial_compression_encode()",
            "torch.nn.functional.conv2d(mask.round(), kernel_tensor",
            '"noise_mask": (mask_erosion[:,:,:x,:y].round())',
            '"concat_latent_image": concat_latent',
            '"concat_mask": mask',
            'if noise_mask:',
            'out_latent["noise_mask"] = mask',
            ') * 0.5',
            'if feathering > 0 and feathering * 2 < d2 and feathering * 2 < d3:',
            't[i, j] = v * v',
        ):
            self.assertIn(marker, nodes_source)
        for marker in (
            "source = comfy.utils.repeat_to_batch_size(source, destination.shape[0])",
            "left, top = (x // multiplier, y // multiplier)",
            "mask = torch.nn.functional.interpolate",
            "output = destination.copy()",
            'destination = destination["samples"].clone()',
        ):
            self.assertIn(marker, mask_source)

        pixels = torch.zeros((1, 4, 5, 3))
        expanded = torch.ones((1, 7, 12, 3), dtype=torch.float32) * 0.5
        expanded[:, 1:5, 2:7] = pixels
        self.assertEqual((1, 7, 12, 3), tuple(expanded.shape))
        self.assertTrue(torch.equal(torch.zeros((1, 4, 5, 3)), expanded[:, 1:5, 2:7]))
        values = torch.tensor([0.0, 0.5, 1.0])
        self.assertEqual([0.0, 0.25, 1.0], (values * values).tolist())

    def test_docs_and_full_official_workflow_census(self) -> None:
        self.assertEqual(DOCS_SHA256, hashlib.sha256(DOCS.read_bytes()).hexdigest())
        with zipfile.ZipFile(DOCS) as archive:
            names = set(archive.namelist())
            for class_type in ("InpaintModelConditioning", "ImagePadForOutpaint", "LatentCompositeMasked"):
                self.assertIn(f"comfyui_embedded_docs/docs/{class_type}/en.md", names)
                self.assertIn(f"comfyui_embedded_docs/docs/{class_type}/ru.md", names)
            self.assertNotIn("comfyui_embedded_docs/docs/VAEEncodeForInpaint/en.md", names)
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
        self.assertEqual(Counter({"ImagePadForOutpaint": 5, "InpaintModelConditioning": 4}), counts)
        self.assertEqual(Counter({(448, 304, 448, 304, 40): 1, (400, 0, 400, 400, 24): 1, (40, 0, 104, 104, 40): 1, (200, 200, 0, 200, 0): 1, (120, 120, 120, 200, 0): 1}), Counter(tuple(item) for item in widgets["ImagePadForOutpaint"]))
        self.assertEqual(Counter({(True,): 2, (False,): 2}), Counter(tuple(item) for item in widgets["InpaintModelConditioning"]))


if __name__ == "__main__":
    unittest.main()
