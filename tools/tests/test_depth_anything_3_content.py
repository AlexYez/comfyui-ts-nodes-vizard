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
    "core.load-da3-model": ("load-da3-model", "LoadDA3Model", "sha256:d70b5c31e41883858e8aa5f03889363100caacbf06637c407448b58fd4b59350"),
    "core.da3-inference": ("da3-inference", "DA3Inference", "sha256:96ef9a881875104fac15ea109c5fd8a513a19b98db53554075b6a7cfa9d49331"),
    "core.da3-render": ("da3-render", "DA3Render", "sha256:65eb74a1219727e7a25ae8d553bc6f1a3342f95f8251cd7797ad8b8c06bc03c5"),
    "core.da3-geometry-to-mesh": ("da3-geometry-to-mesh", "DA3GeometryToMesh", "sha256:085ff626e7252ba47166057c97080ad4e02c7310542d3d68d04c528e3db7fdc3"),
}

DOCS = {
    "LoadDA3Model": ("eba353acf6cbdd183059503f9feca87ed0321c4954b6d0ccc33bf0f8da119ec3", "56c4f02c6cb3936832f8a8b3f3ff5be0f3666f3927b970f4474436428d9d1dc8"),
    "DA3Inference": ("16936fdd33737d153497762849c68dcde869bec4a52deb6cae1ef0193c21dea6", "63040d4750a20f577cc0b439a089b56eaafe52ebcdf6c78f6dad52878c5f375a"),
    "DA3Render": ("931b1c790f1021edfecce0d5223e161329f08e713810f3959764c382dd1c42ee", "2c737123fdc29dc9f31b02b67203d887a3194ffc1094ecc0b240e8ea6b74c916"),
    "DA3GeometryToMesh": ("6371c72486ded6c938ebe25babc4d1974cb97414404881769a55a54c5e29dc93", "1a013bde85fc9afe805668d4dede76897f7b71e6e193a117f5246cfd0e5916ad"),
}


def graphs(value: Any) -> Iterator[dict[str, Any]]:
    if isinstance(value, list):
        for item in value:
            yield from graphs(item)
    elif isinstance(value, dict):
        if isinstance(value.get("nodes"), list):
            yield value
        definitions = value.get("definitions")
        if isinstance(definitions, dict):
            for item in definitions.get("subgraphs", []):
                yield from graphs(item)


class DepthAnything3ContentTests(unittest.TestCase):
    def test_schemas_identities_and_honesty(self) -> None:
        schemas = {name: catalog.load_json(catalog.CONTENT / f"schemas/{name}.schema.v1.json") for name in ("article", "recipe", "recipe-fragment", "article-research")}
        article_ids = {catalog.load_json(path)["articleId"] for path in (catalog.CONTENT / "articles").rglob("manifest.json")}
        nodes = catalog.object_info_nodes(catalog.load_json(catalog.CONTENT / "runtime/comfyui-0.32.0.object-info.json"))
        errors: list[str] = []
        for article_id, (directory, class_type, fingerprint) in SPECS.items():
            path = catalog.CONTENT / "articles/core" / directory / "manifest.json"
            article = catalog.load_json(path)
            self.assertEqual([], catalog.json_schema_errors(article, schemas["article"]))
            catalog.validate_article(path, article, errors)
            self.assertEqual(10, len(re.findall(r"^## ", (path.parent / "ru.md").read_text(encoding="utf8"), re.M)))
            self.assertEqual("draft", article["status"])
            self.assertEqual("in_review", article["editorial"]["state"])
            self.assertEqual("comfy_extras.nodes_depth_anything_3", article["runtimeIdentity"]["pythonModule"])
            self.assertEqual(fingerprint, catalog.schema_fingerprint(class_type, nodes[class_type]))
            self.assertFalse(any(bool(nodes[class_type].get(flag, False)) for flag in ("experimental", "deprecated", "dev_only", "api_node")))
            ledger = catalog.load_json(catalog.CONTENT / "research/reviews" / f"{article_id}.json")
            self.assertEqual([], catalog.json_schema_errors(ledger, schemas["article-research"]))
            self.assertEqual("fact_checked", ledger["state"])
            self.assertFalse(ledger["checks"]["exampleExecuted"])
        for directory in ("da3-official-depth", "da3-geometry-mesh"):
            path = catalog.CONTENT / "recipes" / directory / "recipe.json"
            recipe = catalog.load_json(path)
            catalog.validate_recipe(path, recipe, article_ids, errors)
            self.assertEqual([], catalog.json_schema_errors(recipe, schemas["recipe"]))
            self.assertEqual([], catalog.json_schema_errors(catalog.load_json(path.parent / "fragment.json"), schemas["recipe-fragment"]))
            self.assertNotIn("workflow", recipe)
        self.assertEqual([], errors)

    def test_pinned_source_and_docs(self) -> None:
        source = catalog.ROOT / ".comfyui-source-0.32.0/comfy_extras/nodes_depth_anything_3.py"
        self.assertEqual("10a1ae27157bb9246cbda78cf6faeb3933e86d37c59748676757d93228de06ee", hashlib.sha256(source.read_bytes()).hexdigest())
        text = source.read_text(encoding="utf8")
        for snippet in (
            'get_full_path_or_raise("geometry_estimation", model_name)',
            'mode_val = mode["mode"]',
            'if not has_cam_dec and not has_dualdpt:',
            'normalization == "v2_style"',
            'mask = mask & (geometry["sky"][b] < 0.5)',
            'verts = verts * torch.tensor([1.0, -1.0, -1.0]',
            'faces = faces[:, [0, 2, 1]].contiguous()',
        ):
            self.assertIn(snippet, text)
        with zipfile.ZipFile(catalog.ROOT / ".upstream-cache/comfyui_embedded_docs-0.5.9-py3-none-any.whl") as archive:
            for class_type, (english_hash, russian_hash) in DOCS.items():
                base = f"comfyui_embedded_docs/docs/{class_type}"
                self.assertEqual(english_hash, hashlib.sha256(archive.read(f"{base}/en.md")).hexdigest())
                self.assertEqual(russian_hash, hashlib.sha256(archive.read(f"{base}/ru.md")).hexdigest())

    def test_official_workflow_census(self) -> None:
        targets = {spec[1] for spec in SPECS.values()}
        found: list[tuple[str, Any, int]] = []
        json_count = graph_count = 0
        with zipfile.ZipFile(catalog.ROOT / ".upstream-cache/comfyui_workflow_templates_json-0.1.42-py3-none-any.whl") as archive:
            for name in archive.namelist():
                if not name.endswith(".json"):
                    continue
                json_count += 1
                for graph in graphs(json.loads(archive.read(name))):
                    graph_count += 1
                    for node in graph.get("nodes", []):
                        if node.get("type") in targets:
                            found.append((node["type"], node.get("widgets_values"), node.get("mode", 0)))
        self.assertEqual((512, 768), (json_count, graph_count))
        self.assertEqual({"LoadDA3Model": 3, "DA3Inference": 3, "DA3Render": 3}, dict(Counter(item[0] for item in found)))
        self.assertTrue(all(values == ["depth_anything_3_mono_large.safetensors", "default"] and mode == 0 for kind, values, mode in found if kind == "LoadDA3Model"))
        self.assertEqual(Counter({(504, "upper_bound_resize", "mono"): 2, (504, "lower_bound_resize", "mono"): 1}), Counter(tuple(values) for kind, values, _mode in found if kind == "DA3Inference"))
        self.assertTrue(all(values == ["depth", "v2_style", False] and mode == 0 for kind, values, mode in found if kind == "DA3Render"))

    def test_fragment_contracts(self) -> None:
        official = catalog.load_json(catalog.CONTENT / "recipes/da3-official-depth/fragment.json")
        self.assertEqual(["LoadDA3Model", "DA3Inference", "DA3Render"], [node["classType"] for node in official["nodes"]])
        self.assertEqual(2, len(official["connections"]))
        self.assertEqual({"resolution": 504, "resize_method": "upper_bound_resize", "mode": "mono"}, official["nodes"][1]["settings"])
        mesh = catalog.load_json(catalog.CONTENT / "recipes/da3-geometry-mesh/fragment.json")
        self.assertEqual("DA3GeometryToMesh", mesh["nodes"][0]["classType"])
        self.assertEqual({"batch_index": 0, "decimation": 1, "discontinuity_threshold": 0.04, "confidence_threshold": 0.1, "use_sky_mask": True, "texture": True}, mesh["nodes"][0]["settings"])
        self.assertEqual([], mesh["connections"])

    def test_natural_russian_regression(self) -> None:
        forbidden = re.compile(r"\b(?:official|workflow|source-derived|human approval pending|default model|input image|output image|case|instances)\b", re.I)
        for article_id, (directory, _class_type, _fingerprint) in SPECS.items():
            prose = (catalog.CONTENT / "articles/core" / directory / "ru.md").read_text(encoding="utf8")
            ledger = catalog.load_json(catalog.CONTENT / "research/reviews" / f"{article_id}.json")
            prose += "\n" + "\n".join(item["assessment"] for item in ledger["evidence"]["embeddedDocs"])
            prose += "\n" + "\n".join(item["role"] for item in ledger["evidence"]["workflows"])
            prose += "\n" + "\n".join(ledger["knownGaps"])
            self.assertIsNone(forbidden.search(re.sub(r"`[^`]+`|https?://\S+", "", prose)), directory)


if __name__ == "__main__":
    unittest.main()
