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
    "core.batch-masks-node": ("batch-masks-node", "BatchMasksNode", "comfy_extras.nodes_post_processing", "sha256:c286ce874e86e3eb4b52f19b4aff92ffcb0252c67256394a93936bbcdd5001df", "batch-masks-preview"),
    "core.mask-preview": ("mask-preview", "MaskPreview", "comfy_extras.nodes_mask", "sha256:99354e0366dca2b1818e04a04c11c9ae3088005745b14cfb5cb42b7f6b36a36a", "preview-mask"),
    "core.void-quadmask-preprocess": ("void-quadmask-preprocess", "VOIDQuadmaskPreprocess", "comfy_extras.nodes_void", "sha256:b2b3b4c96e62ff97665644b4882776cb9b242f6d7a2c229e6d31416a01aa6ed4", "void-quadmask-preview"),
    "core.split-image-with-alpha": ("split-image-with-alpha", "SplitImageWithAlpha", "comfy_extras.nodes_compositing", "sha256:dab2f1b1ed91cea8c28bcad284f54f3ece224badae7a6f958f8620596f154c11", "split-alpha-preview"),
}
ROOT = catalog.ROOT
INVENTORY = catalog.CONTENT / "runtime" / "comfyui-0.32.0.object-info.json"
REPLACEMENTS = catalog.CONTENT / "runtime" / "comfyui-0.32.0.node-replacements.json"
SOURCE = ROOT / ".comfyui-source-0.32.0"
DOCS = ROOT / ".upstream-cache" / "comfyui_embedded_docs-0.5.9-py3-none-any.whl"
WORKFLOWS = ROOT / ".upstream-cache" / "comfyui_workflow_templates_json-0.1.42-py3-none-any.whl"


def scopes(payload: dict[str, Any]) -> Iterator[tuple[str, dict[str, Any]]]:
    if isinstance(payload.get("nodes"), list):
        yield "root", payload
    definitions = payload.get("definitions")
    if isinstance(definitions, dict):
        for index, subgraph in enumerate(definitions.get("subgraphs", [])):
            if isinstance(subgraph, dict):
                yield f"subgraph:{index}", subgraph


class MaskPreviewAlphaContentTests(unittest.TestCase):
    def test_content_schemas_honesty_and_natural_russian(self) -> None:
        schemas = {name: catalog.load_json(catalog.CONTENT / "schemas" / name) for name in (
            "article.schema.v1.json", "recipe.schema.v1.json", "recipe-fragment.schema.v1.json", "article-research.schema.v1.json"
        )}
        article_ids = {catalog.load_json(path)["articleId"] for path in (catalog.CONTENT / "articles").rglob("manifest.json")}
        errors: list[str] = []
        for article_id, (directory, _class_type, _module, _fingerprint, recipe_id) in SPECS.items():
            article_path = catalog.CONTENT / "articles" / "core" / directory / "manifest.json"
            article = catalog.load_json(article_path)
            self.assertEqual([], catalog.json_schema_errors(article, schemas["article.schema.v1.json"]), article_id)
            catalog.validate_article(article_path, article, errors)
            self.assertEqual(("draft", "in_review"), (article["status"], article["editorial"]["state"]))
            body = (article_path.parent / article["body"]).read_text(encoding="utf-8")
            self.assertEqual(10, len(re.findall(r"^## ", body, re.MULTILINE)), article_id)
            ledger = catalog.load_json(catalog.CONTENT / "research" / "reviews" / f"{article_id}.json")
            self.assertEqual([], catalog.json_schema_errors(ledger, schemas["article-research.schema.v1.json"]), article_id)
            self.assertEqual("fact_checked", ledger["state"])
            self.assertFalse(ledger["checks"]["exampleExecuted"])
            self.assertTrue(any("утверждение" in gap.casefold() for gap in ledger["knownGaps"]))
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
            for phrase in ("official workflow", "synthetic tensor", "full fragment", "through frontend", "preview будет", "input —"):
                self.assertNotIn(phrase, prose, recipe_id)
        self.assertEqual([], errors)

    def test_runtime_fingerprints_ports_and_replacements(self) -> None:
        nodes = catalog.object_info_nodes(catalog.load_json(INVENTORY))
        for article_id, (directory, class_type, module, fingerprint, _recipe_id) in SPECS.items():
            runtime = nodes[class_type]
            article = catalog.load_json(catalog.CONTENT / "articles" / "core" / directory / "manifest.json")
            self.assertEqual(module, runtime["python_module"])
            self.assertEqual(fingerprint, catalog.schema_fingerprint(class_type, runtime), article_id)
            self.assertEqual(fingerprint, article["editorial"]["schemaHash"])
            self.assertFalse(runtime.get("api_node", False))
            self.assertFalse(runtime.get("deprecated", False))
        self.assertTrue(nodes["MaskPreview"]["output_node"])
        self.assertEqual(["MASK"], nodes["BatchMasksNode"]["output"])
        template = nodes["BatchMasksNode"]["input"]["required"]["masks"][1]["template"]
        self.assertEqual((1, 50, "mask"), (template["min"], template["max"], template["prefix"]))
        self.assertEqual(50, nodes["VOIDQuadmaskPreprocess"]["input"]["required"]["dilate_width"][1]["max"])
        self.assertEqual(["IMAGE", "MASK"], nodes["SplitImageWithAlpha"]["output"])
        replacements = json.dumps(catalog.load_json(REPLACEMENTS), ensure_ascii=False)
        for spec in SPECS.values():
            self.assertNotIn(spec[1], replacements)

    def test_pinned_sources_and_exact_tensor_semantics(self) -> None:
        files = {
            "post": (SOURCE / "comfy_extras" / "nodes_post_processing.py", "6d28d37a0947947ff6bb724c4de465bacc012f7f23e11d916d7a5161953158aa"),
            "mask": (SOURCE / "comfy_extras" / "nodes_mask.py", "39d21d7c96cb18035200167ff9883db2cdb3674513837094b3e5326188eabc1f"),
            "void": (SOURCE / "comfy_extras" / "nodes_void.py", "242dcd84baf0a7934cd3c980f01d6c73992abc7f4b2e18d87712619a7425af90"),
            "compose": (SOURCE / "comfy_extras" / "nodes_compositing.py", "e500fc0d5accdb396f3e0f346a36e69ee9d09a17d0e3044f9cde3d443aa99dfc"),
            "ui": (SOURCE / "comfy_api" / "latest" / "_ui.py", "ef5fb612305207d1673eda16172a82407e6657b958f85ad14d0d0272b0745d38"),
        }
        sources = {}
        for key, (path, digest) in files.items():
            self.assertEqual(digest, hashlib.sha256(path.read_bytes()).hexdigest())
            sources[key] = path.read_text(encoding="utf-8")
        for marker in ('common_upscale(mask, first_mask_shape[2], first_mask_shape[1], "bilinear", "center")', "return torch.cat(resized_masks, dim=0)"):
            self.assertIn(marker, sources["post"])
        self.assertIn("return IO.NodeOutput(mask, ui=UI.PreviewMask(mask))", sources["mask"])
        self.assertIn("m = torch.where((m > 95) & (m <= 191), torch.full_like(m, 127), m)", sources["void"])
        self.assertIn("return io.NodeOutput(torch.stack(out_images), 1.0 - torch.stack(out_alphas))", sources["compose"])
        self.assertIn("preview = mask.reshape((-1, 1, mask.shape[-2], mask.shape[-1])).movedim(1, -1).expand(-1, -1, -1, 3)", sources["ui"])

        rgba = torch.tensor([[[[0.1, 0.2, 0.3, 0.25], [0.4, 0.5, 0.6, 1.0]]]])
        rgb = rgba[..., :3]
        mask = 1.0 - rgba[..., 3]
        joined = torch.cat((rgb, (1.0 - mask).unsqueeze(-1)), dim=-1)
        self.assertTrue(torch.equal(rgba, joined))
        self.assertTrue(torch.equal(torch.zeros(1, 1, 2), 1.0 - torch.ones(1, 1, 2)))

        raw = torch.tensor([[[0.0, 31 / 255, 32 / 255, 95 / 255, 96 / 255, 191 / 255, 192 / 255, 1.0]]])
        m = raw * 255.0
        m = torch.where(m <= 31, torch.zeros_like(m), m)
        m = torch.where((m > 31) & (m <= 95), torch.full_like(m, 63), m)
        m = torch.where((m > 95) & (m <= 191), torch.full_like(m, 127), m)
        m = torch.where(m > 191, torch.full_like(m, 255), m)
        self.assertTrue(torch.equal((255.0 - m) / 255.0, torch.tensor([[[1.0, 1.0, 192 / 255, 192 / 255, 128 / 255, 128 / 255, 0.0, 0.0]]])))

    def test_docs_and_complete_workflow_census(self) -> None:
        self.assertEqual("30afae432a71c96aa59421d0f37388c66ff6572b8cbeee8ff045e4d5f84f896c", hashlib.sha256(DOCS.read_bytes()).hexdigest())
        with zipfile.ZipFile(DOCS) as archive:
            names = set(archive.namelist())
            for class_type in ("BatchMasksNode", "MaskPreview", "VOIDQuadmaskPreprocess", "SplitImageWithAlpha"):
                self.assertIn(f"comfyui_embedded_docs/docs/{class_type}/en.md", names)
                self.assertIn(f"comfyui_embedded_docs/docs/{class_type}/ru.md", names)
        self.assertEqual("242982d65e1c51ca03d892bc1009bb6843f457e7dfc0c20afe6438770b7a14a3", hashlib.sha256(WORKFLOWS.read_bytes()).hexdigest())
        targets = {spec[1] for spec in SPECS.values()}
        counts: Counter[str] = Counter()
        locations: dict[str, list[tuple[str, str, dict[str, Any]]]] = {target: [] for target in targets}
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
                for label, graph in graphs:
                    for node in graph.get("nodes", []):
                        node_count += 1
                        node_type = node.get("type") if isinstance(node, dict) else None
                        if node_type in targets:
                            counts[node_type] += 1
                            locations[node_type].append((member, label, node))
        self.assertEqual((512, 496, 272, 8120), (json_count, root_count, subgraph_count, node_count))
        self.assertEqual(Counter({"MaskPreview": 23, "BatchMasksNode": 1, "SplitImageWithAlpha": 1}), counts)
        self.assertEqual([], locations["VOIDQuadmaskPreprocess"])
        batch = locations["BatchMasksNode"][0][2]
        self.assertEqual(["masks.mask0", "masks.mask1", "masks.mask2"], [item["name"] for item in batch["inputs"]])
        self.assertEqual([21, 22, None], [item.get("link") for item in batch["inputs"]])
        split_member, split_scope, split = locations["SplitImageWithAlpha"][0]
        self.assertTrue(split_member.endswith("templates_mjm_looped_restyler.json"))
        self.assertEqual("subgraph:2", split_scope)
        self.assertEqual(158, split["inputs"][0]["link"])
        self.assertEqual([123, 124], split["outputs"][0]["links"])
        self.assertIsNone(split["outputs"][1]["links"])


if __name__ == "__main__":
    unittest.main()
