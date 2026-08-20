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
    "core.image-upscale-with-model": ("image-upscale-with-model", "ImageUpscaleWithModel", "comfy_extras.nodes_upscale_model", "sha256:973ea716f7547aae900981b59964a10a6726372dfb948b507218bfbad9ab127e", "gan-video-upscale"),
    "core.latent-upscale-by": ("latent-upscale-by", "LatentUpscaleBy", "nodes", "sha256:df843a62421f7f44c9ee321900fe4c596d1ab8ca17e5a0ab4b10f4ee2584b03f", "latent-upscale-by-second-pass"),
    "core.resize-images-by-shorter-edge": ("resize-images-by-shorter-edge", "ResizeImagesByShorterEdge", "comfy_extras.nodes_dataset", "sha256:0ee355f08a404527c9bcb23e7c228f56d9bde76185e1966bb581bdc29761cb30", "resize-shorter-edge-legacy"),
    "core.photomaker-loader": ("photomaker-loader", "PhotoMakerLoader", "comfy_extras.nodes_photomaker", "sha256:aca010222e4ae18a3c8a7ab74342a855d1746b1616acd860f7f86ffc96a018d6", "load-photomaker-model"),
}
ROOT = catalog.ROOT
INVENTORY = catalog.CONTENT / "runtime" / "comfyui-0.32.0.object-info.json"
REPLACEMENTS = catalog.CONTENT / "runtime" / "comfyui-0.32.0.node-replacements.json"
SOURCE = ROOT / ".comfyui-source-0.32.0"
DOCS = ROOT / ".upstream-cache" / "comfyui_embedded_docs-0.5.9-py3-none-any.whl"
WORKFLOWS = ROOT / ".upstream-cache" / "comfyui_workflow_templates_json-0.1.42-py3-none-any.whl"


def scopes(payload: dict[str, Any]) -> Iterator[dict[str, Any]]:
    if not isinstance(payload, dict):
        return
    if isinstance(payload.get("nodes"), list):
        yield payload
    definitions = payload.get("definitions")
    if isinstance(definitions, dict):
        yield from (graph for graph in definitions.get("subgraphs", []) if isinstance(graph, dict))


class UpscalePhotoMakerLoaderContentTests(unittest.TestCase):
    def test_content_contracts_ten_sections_and_honesty(self) -> None:
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
            self.assertTrue(any("человечес" in gap.casefold() for gap in ledger["knownGaps"]))
            recipe_path = catalog.CONTENT / "recipes" / recipe_id / "recipe.json"
            recipe = catalog.load_json(recipe_path)
            self.assertEqual([], catalog.json_schema_errors(recipe, schemas["recipe.schema.v1.json"]), recipe_id)
            catalog.validate_recipe(recipe_path, recipe, article_ids, errors)
            fragment_path = recipe_path.parent / recipe["fragment"]["path"]
            fragment = catalog.load_json(fragment_path)
            self.assertEqual([], catalog.json_schema_errors(fragment, schemas["recipe-fragment.schema.v1.json"]), recipe_id)
            catalog.validate_fragment(fragment_path, fragment, errors)
        self.assertEqual([], errors)

    def test_runtime_fingerprints_ports_and_lifecycle_mismatch(self) -> None:
        nodes = catalog.object_info_nodes(catalog.load_json(INVENTORY))
        for article_id, (directory, class_type, module, fingerprint, _recipe_id) in SPECS.items():
            runtime = nodes[class_type]
            article = catalog.load_json(catalog.CONTENT / "articles" / "core" / directory / "manifest.json")
            self.assertEqual(module, runtime["python_module"])
            self.assertEqual(fingerprint, catalog.schema_fingerprint(class_type, runtime), article_id)
            self.assertEqual(fingerprint, article["editorial"]["schemaHash"])
            self.assertFalse(runtime.get("api_node", False))
        self.assertEqual(["nearest-exact", "bilinear", "area", "bicubic", "bislerp"], nodes["LatentUpscaleBy"]["input"]["required"]["upscale_method"][0])
        self.assertEqual((0.01, 8.0, 1.5), tuple(nodes["LatentUpscaleBy"]["input"]["required"]["scale_by"][1][key] for key in ("min", "max", "default")))
        self.assertTrue(nodes["ResizeImagesByShorterEdge"].get("experimental", False))
        self.assertFalse(nodes["ResizeImagesByShorterEdge"].get("deprecated", False))
        self.assertEqual([], nodes["PhotoMakerLoader"]["input"]["required"]["photomaker_model_name"][1]["options"])
        replacements = json.dumps(catalog.load_json(REPLACEMENTS), ensure_ascii=False)
        for spec in SPECS.values():
            self.assertNotIn(spec[1], replacements)

    def test_pinned_source_semantics(self) -> None:
        paths = {
            "nodes": (SOURCE / "nodes.py", "ffb2b5c999f47b720dbd81767c8fa4234255d939ba8dbb80ee64da9721c383ad"),
            "upscale": (SOURCE / "comfy_extras" / "nodes_upscale_model.py", "3cd8a5f93ca8b4f28e5360897ee0d2e25ab3c40b050e6545586b95af1514173a"),
            "dataset": (SOURCE / "comfy_extras" / "nodes_dataset.py", "1bde15deb4402cf11d9e57d8bf9e1a3fdab3c34e7a648b9aa51d4d346d18915a"),
            "photo": (SOURCE / "comfy_extras" / "nodes_photomaker.py", "16241bf82c5cfcf0d2684cc6819392f6b9e8aff334560c233647db69dd15bacc"),
        }
        text = {}
        for key, (path, digest) in paths.items():
            self.assertEqual(digest, hashlib.sha256(path.read_bytes()).hexdigest())
            text[key] = path.read_text(encoding="utf-8")
        for marker in ("class LatentUpscaleBy", "round(samples[\"samples\"].shape[-1] * scale_by)", 'upscale_method, "disabled"'):
            self.assertIn(marker, text["nodes"])
        for marker in ("tile = 512", "overlap = 32", "tile //= 2", "if tile < 128", "torch.clamp"):
            self.assertIn(marker, text["upscale"])
        self.assertIn("is_deprecated = True", text["dataset"])
        self.assertIn("superseded by Resize Image/Mask with resize_type = scale shorter dimension", text["dataset"])
        for marker in ('get_full_path_or_raise("photomaker"', 'load_torch_file(photomaker_model_path, safe_load=True)', 'if "id_encoder" in data'):
            self.assertIn(marker, text["photo"])

    def test_docs_and_exhaustive_workflow_census(self) -> None:
        expected_docs = {
            "ImageUpscaleWithModel": ("9a53f631dae4f53f57d3b9b5f992e4e017d49e418b194ee2c2c18c7e55219516", "73a64c49ad4d0bcd6543afdd9a0431cef6d27a4d4c256b987477f88689b18b28"),
            "LatentUpscaleBy": ("f3f1f8cea7d7fd7ff46196e0e4a65c3986fe8002a572a290b06eac2bec559e7e", "35a6574ed336fdf59a32b51ddf65e6badcce5660b19f51ab64aed1b8390d77c6"),
            "ResizeImagesByShorterEdge": ("081824fbe5cff3c7dbd3e6a850d1b8dc5c64682c746a4288173d5b618100972b", "60abf6da33034489ddcc26857f129fcf1688f140d9b83d9a4e6545ddf879ce56"),
            "PhotoMakerLoader": ("1cdfcb1e951819788dc70b50ddb001cb97ab6da19dd159e00351d806ce860d86", "67a38af6d9d8c46dfb60836c8e65667d6f765116b8efd9c5ebc4e2c87688486b"),
        }
        with zipfile.ZipFile(DOCS) as archive:
            for class_type, hashes in expected_docs.items():
                for locale, digest in zip(("en", "ru"), hashes):
                    self.assertEqual(digest, hashlib.sha256(archive.read(f"comfyui_embedded_docs/docs/{class_type}/{locale}.md")).hexdigest())
        targets = {spec[1] for spec in SPECS.values()}; counts: Counter[str] = Counter()
        totals = [0, 0, 0, 0]
        with zipfile.ZipFile(WORKFLOWS) as archive:
            for member in archive.namelist():
                if "/templates/" not in member or not member.endswith(".json"):
                    continue
                totals[0] += 1; payload = json.loads(archive.read(member).decode("utf-8")); graphs = list(scopes(payload))
                has_root = isinstance(payload, dict) and isinstance(payload.get("nodes"), list); totals[1] += int(has_root); totals[2] += len(graphs) - int(has_root)
                for graph in graphs:
                    for node in graph.get("nodes", []):
                        totals[3] += 1
                        if isinstance(node, dict) and node.get("type") in targets:
                            counts[node["type"]] += 1
        self.assertEqual([512, 496, 272, 8120], totals)
        self.assertEqual(Counter({"ImageUpscaleWithModel": 4}), counts)


if __name__ == "__main__":
    unittest.main()
