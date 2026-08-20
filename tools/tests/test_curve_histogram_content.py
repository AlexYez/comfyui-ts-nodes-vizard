from __future__ import annotations

import hashlib
import json
import re
import unittest
import zipfile
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterator

from tools import catalog
from tools.tests.curve_histogram_synthetic_probe import run


SPECS = {
    "core.curve-editor": (
        "curve-editor",
        "CurveEditor",
        "sha256:104813cdc38a6a7e82700aa6ec366b63067fd1c213b1baa0008d194da15df982",
    ),
    "core.image-histogram": (
        "image-histogram",
        "ImageHistogram",
        "sha256:7cfb08c3514079d781df71a5d12e2d85b7223c90375d8f24570852e71c1322dc",
    ),
}
DOCS = {
    "CurveEditor": (
        "6aade13208261e2b97460e255ff301f52540a26a5bf59048344cf62d3497b4e1",
        "2f74ce53fb43cdda0c30eb87463dc95bb31a1db40061cf82783ff01ce754f879",
    ),
    "ImageHistogram": (
        "097f4e53aadd450ac5dfec92d35c7823f286ae0400d3af081a8cf71401f78a9d",
        "4c2ff346e3b01d914ff6eed98af9c390d6262afcb90ddee1f0351a98d279e3e5",
    ),
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
            for subgraph in definitions.get("subgraphs", []):
                yield from graphs(subgraph)


class CurveHistogramContentTests(unittest.TestCase):
    def test_schema_runtime_and_editorial_contract(self):
        schemas = {
            name: catalog.load_json(catalog.CONTENT / f"schemas/{name}.schema.v1.json")
            for name in ("article", "recipe", "recipe-fragment", "article-research")
        }
        runtime = catalog.object_info_nodes(
            catalog.load_json(catalog.CONTENT / "runtime/comfyui-0.32.0.object-info.json")
        )
        article_ids = {
            catalog.load_json(path)["articleId"]
            for path in (catalog.CONTENT / "articles").rglob("manifest.json")
        }
        errors: list[str] = []
        for article_id, (slug, class_type, fingerprint) in SPECS.items():
            path = catalog.CONTENT / "articles/core" / slug / "manifest.json"
            article = catalog.load_json(path)
            self.assertEqual([], catalog.json_schema_errors(article, schemas["article"]))
            catalog.validate_article(path, article, errors)
            self.assertEqual("draft", article["status"])
            self.assertEqual("in_review", article["editorial"]["state"])
            self.assertEqual(10, len(re.findall(r"^## ", (path.parent / "ru.md").read_text("utf8"), re.M)))
            self.assertEqual(fingerprint, catalog.schema_fingerprint(class_type, runtime[class_type]))
            research = catalog.load_json(catalog.CONTENT / "research/reviews" / f"{article_id}.json")
            self.assertEqual([], catalog.json_schema_errors(research, schemas["article-research"]))
            self.assertFalse(research["checks"]["exampleExecuted"])
        recipe_path = catalog.CONTENT / "recipes/curve-editor-with-histogram/recipe.json"
        recipe = catalog.load_json(recipe_path)
        catalog.validate_recipe(recipe_path, recipe, article_ids, errors)
        self.assertEqual([], catalog.json_schema_errors(recipe, schemas["recipe"]))
        fragment = catalog.load_json(recipe_path.parent / "fragment.json")
        self.assertEqual([], catalog.json_schema_errors(fragment, schemas["recipe-fragment"]))
        self.assertEqual([], errors)

    def test_pinned_sources_and_frontend(self):
        hashes = {
            ".comfyui-source-0.32.0/comfy_extras/nodes_curve.py": "3308c5b698ebe73bc8b34f59c895c5eef5282131d2053e2d507564511f0f3dec",
            ".comfyui-source-0.32.0/comfy_api/latest/_input/curve_types.py": "8839d77be7d0147b330a1fc49ea5c52ec016ed92eae27351050196a862c4d5bd",
            ".frontend-source-1.48.7/src/components/curve/WidgetCurve.vue": "c9871d2ab0d39b61fe4b1cdefd9746436d20f448335fddfbc5a29d904bb2d9e1",
            ".frontend-source-1.48.7/src/composables/useCurveEditor.ts": "eccd1b01706fd29950ccfc04076c9874e3e2efe0a61f2a815ed001a7d6c659ad",
            ".frontend-source-1.48.7/src/components/curve/curveUtils.ts": "e9125516602281030c8b3176170f98dfd82a622ede6b65a2cb38cf8fc1d4b00e",
        }
        for relative, expected in hashes.items():
            path = catalog.ROOT / relative
            self.assertTrue(path.is_file(), relative)
            self.assertEqual(expected, hashlib.sha256(path.read_bytes()).hexdigest())
        source = (catalog.ROOT / ".comfyui-source-0.32.0/comfy_extras/nodes_curve.py").read_text("utf8")
        self.assertIn("img = image[0].cpu().numpy()", source)
        self.assertIn("rgb = ((hist_r + hist_g + hist_b) // 3).tolist()", source)
        self.assertIn("0.2126 * img[:, :, 0]", source)
        self.assertIn("NodeOutput(result, ui=ui)", source)

    def test_embedded_docs_hashes(self):
        wheel = catalog.ROOT / ".upstream-cache/comfyui_embedded_docs-0.5.9-py3-none-any.whl"
        self.assertTrue(wheel.is_file())
        with zipfile.ZipFile(wheel) as archive:
            for class_type, (en_hash, ru_hash) in DOCS.items():
                base = f"comfyui_embedded_docs/docs/{class_type}"
                self.assertEqual(en_hash, hashlib.sha256(archive.read(f"{base}/en.md")).hexdigest())
                self.assertEqual(ru_hash, hashlib.sha256(archive.read(f"{base}/ru.md")).hexdigest())

    def test_official_workflow_census_and_settings(self):
        wheel = catalog.ROOT / ".upstream-cache/comfyui_workflow_templates_json-0.1.42-py3-none-any.whl"
        self.assertTrue(wheel.is_file())
        counts: Counter[str] = Counter()
        widgets: dict[str, list[Any]] = defaultdict(list)
        with zipfile.ZipFile(wheel) as archive:
            names = [name for name in archive.namelist() if name.endswith(".json")]
            self.assertEqual(512, len(names))
            for name in names:
                for graph in graphs(json.loads(archive.read(name))):
                    for node in graph.get("nodes", []):
                        if node.get("type") in {"CurveEditor", "ImageHistogram"}:
                            counts[node["type"]] += 1
                            widgets[node["type"]].append(node.get("widgets_values", []))
        self.assertEqual({"CurveEditor": 4, "ImageHistogram": 1}, dict(counts))
        self.assertEqual([[]], widgets["ImageHistogram"])
        self.assertEqual(4, len(widgets["CurveEditor"]))
        self.assertTrue(all(value[0]["interpolation"] == "monotone_cubic" for value in widgets["CurveEditor"]))
        self.assertEqual([[0, 0], [1, 1]], widgets["CurveEditor"][3][0]["points"])

    def test_fragment_topology(self):
        fragment = catalog.load_json(catalog.CONTENT / "recipes/curve-editor-with-histogram/fragment.json")
        self.assertEqual([("histogram", "ImageHistogram"), ("curve", "CurveEditor")], [(n["ref"], n["classType"]) for n in fragment["nodes"]])
        self.assertEqual({"points": [[0, 0], [1, 1]], "interpolation": "monotone_cubic"}, fragment["nodes"][1]["settings"]["curve"])
        self.assertEqual([{"from": "histogram", "output": "rgb", "to": "curve", "input": "histogram"}], fragment["connections"])
        self.assertEqual(["image"], [item["id"] for item in fragment["externalInputs"]])

    def test_exact_curve_and_histogram_probe(self):
        result = run(catalog.ROOT / ".comfyui-source-0.32.0")
        self.assertEqual({"linearQuarter": 0.125, "rgbCount": 0, "luminanceCount": 2}, result)


if __name__ == "__main__":
    unittest.main()
