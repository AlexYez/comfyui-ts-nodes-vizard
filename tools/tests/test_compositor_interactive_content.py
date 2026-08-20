from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import sys
import unittest
import zipfile
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterator

from tools import catalog


ARTICLE_SPECS = {
    "core.image-compositor": ("image-compositor", "ImageCompositor", "comfy_extras.nodes_compositor", "sha256:d98296fced86cb56fef2b789e930e08391575563b710c0f23b32bfd4366e7b29"),
    "core.add-layer": ("add-layer", "AddLayer", "comfy_extras.nodes_compositor", "sha256:0764ea1e16921100d86aab5107366a29c8662fe0420b9f31a71752fd54cd975f"),
    "core.image-compare": ("image-compare", "ImageCompare", "comfy_extras.nodes_image_compare", "sha256:d59234d40e68653cd5ecd8f0c1c445df414a6e58c56803d9b9d51125e1211ed3"),
    "core.painter": ("painter", "Painter", "comfy_extras.nodes_painter", "sha256:9750aa7367fb09b9e3ad329385b8aff81894b4d91f448efd326c3e4cf97f9e20"),
}
RECIPE_DIRS = {
    "recipe.compose-two-image-layers": "compose-two-image-layers",
    "recipe.compare-original-and-result": "compare-original-and-result",
    "recipe.paint-mask-preview": "paint-mask-preview",
}
INVENTORY = catalog.CONTENT / "runtime" / "comfyui-0.32.0.object-info.json"
SOURCE = catalog.ROOT / ".comfyui-source-0.32.0"
FRONTEND = catalog.ROOT / ".frontend-source-1.48.7"
WORKFLOW_WHEEL = catalog.ROOT / ".upstream-cache" / "comfyui_workflow_templates_json-0.1.42-py3-none-any.whl"
PROBE = Path(__file__).with_name("compositor_interactive_synthetic_probe.py")


def records(payload: dict[str, Any]) -> Iterator[tuple[str, dict[str, Any], dict[str, Any]]]:
    for node in payload.get("nodes", []):
        if isinstance(node, dict):
            yield "root", node, payload
    definitions = payload.get("definitions")
    if isinstance(definitions, dict):
        for subgraph in definitions.get("subgraphs", []):
            if isinstance(subgraph, dict):
                for node in subgraph.get("nodes", []):
                    if isinstance(node, dict):
                        yield "subgraph", node, subgraph


class CompositorInteractiveContentTests(unittest.TestCase):
    def test_schema_identity_honesty_and_natural_russian(self) -> None:
        article_schema = catalog.load_json(catalog.CONTENT / "schemas" / "article.schema.v1.json")
        recipe_schema = catalog.load_json(catalog.CONTENT / "schemas" / "recipe.schema.v1.json")
        fragment_schema = catalog.load_json(catalog.CONTENT / "schemas" / "recipe-fragment.schema.v1.json")
        research_schema = catalog.load_json(catalog.CONTENT / "schemas" / "article-research.schema.v1.json")
        article_ids = {catalog.load_json(path)["articleId"] for path in (catalog.CONTENT / "articles").rglob("manifest.json")}
        inventory = catalog.load_json(INVENTORY)
        validation_errors: list[str] = []
        text_paths: list[Path] = []
        for article_id, (directory, class_type, module, fingerprint) in ARTICLE_SPECS.items():
            path = catalog.CONTENT / "articles" / "core" / directory / "manifest.json"
            article = catalog.load_json(path)
            self.assertEqual([], catalog.json_schema_errors(article, article_schema))
            catalog.validate_article(path, article, validation_errors)
            self.assertEqual(article_id, article["articleId"])
            self.assertEqual("draft", article["status"])
            self.assertEqual("in_review", article["editorial"]["state"])
            self.assertEqual(module, article["runtimeIdentity"]["pythonModule"])
            self.assertEqual(fingerprint, article["editorial"]["schemaHash"])
            self.assertEqual(fingerprint, catalog.schema_fingerprint(class_type, inventory[class_type]))
            self.assertNotIn("approved", json.dumps(article).lower())
            for relation in article["relations"]["related"] + article["relations"]["alternatives"]:
                self.assertIn(relation, article_ids)
            body = path.parent / "ru.md"
            self.assertEqual(10, len(re.findall(r"^## ", body.read_text(encoding="utf-8"), re.MULTILINE)))
            text_paths.append(body)
            research = catalog.load_json(catalog.CONTENT / "research" / "reviews" / f"{article_id}.json")
            self.assertEqual([], catalog.json_schema_errors(research, research_schema))
            self.assertEqual("fact_checked", research["state"])
            self.assertEqual("automated_assisted", research["reviewMode"])
            self.assertFalse(research["checks"]["exampleExecuted"])

        for recipe_id, directory in RECIPE_DIRS.items():
            path = catalog.CONTENT / "recipes" / directory / "recipe.json"
            recipe = catalog.load_json(path)
            self.assertEqual([], catalog.json_schema_errors(recipe, recipe_schema))
            catalog.validate_recipe(path, recipe, article_ids, validation_errors)
            self.assertEqual(recipe_id, recipe["recipeId"])
            self.assertEqual("in_review", recipe["editorial"]["state"])
            self.assertNotIn("workflow", recipe)
            fragment = catalog.load_json(path.parent / "fragment.json")
            self.assertEqual([], catalog.json_schema_errors(fragment, fragment_schema))
            catalog.validate_fragment(path.parent / "fragment.json", fragment, validation_errors)
            text_paths.append(path.parent / "ru.md")

        self.assertEqual([], validation_errors)
        forbidden = ("важно отметить", "стоит отметить", "таким образом", "в современном мире", "давайте", "погрузимся")
        for path in text_paths:
            text = path.read_text(encoding="utf-8").lower()
            self.assertNotIn("\ufffd", text)
            for phrase in forbidden:
                self.assertNotIn(phrase, text, path)

    def test_runtime_ports_and_fragment_connections(self) -> None:
        inventory = catalog.load_json(INVENTORY)
        self.assertEqual(["IMAGE", "MASK"], inventory["ImageCompositor"]["output"])
        self.assertEqual("LAYERS", inventory["ImageCompositor"]["input"]["required"]["layers"][0])
        self.assertEqual(["LAYERS"], inventory["AddLayer"]["output"])
        self.assertEqual("IMAGE", inventory["AddLayer"]["input"]["required"]["image"][0])
        self.assertEqual([], inventory["ImageCompare"]["output"])
        self.assertTrue(inventory["ImageCompare"]["output_node"])
        self.assertEqual(["IMAGE", "MASK"], inventory["Painter"]["output"])
        self.assertTrue(inventory["Painter"]["has_intermediate_output"])
        self.assertEqual("STRING", inventory["Painter"]["input"]["required"]["mask"][0])

        compose = catalog.load_json(catalog.CONTENT / "recipes" / "compose-two-image-layers" / "fragment.json")
        self.assertEqual(["AddLayer", "AddLayer", "ImageCompositor"], [node["classType"] for node in compose["nodes"]])
        self.assertEqual([("base_layer", "overlay_layer"), ("overlay_layer", "compositor")], [(link["from"], link["to"]) for link in compose["connections"]])
        compare = catalog.load_json(catalog.CONTENT / "recipes" / "compare-original-and-result" / "fragment.json")
        self.assertEqual([], compare["connections"])
        self.assertEqual({"image_a", "image_b"}, {item["input"] for item in compare["externalInputs"]})
        painter = catalog.load_json(catalog.CONTENT / "recipes" / "paint-mask-preview" / "fragment.json")
        self.assertEqual({("IMAGE", "images"), ("MASK", "mask")}, {(link["output"], link["input"]) for link in painter["connections"]})

    @unittest.skipUnless(SOURCE.exists() and FRONTEND.exists(), "pinned source checkouts are absent")
    def test_pinned_backend_and_frontend_contracts(self) -> None:
        self.assertEqual("c2bcbecd82ec5ae66594340b395c24ef0217b238", (SOURCE / ".git" / "HEAD").read_text(encoding="ascii").strip())
        self.assertEqual("6d6af63c00f132cd25dc29307fc56bd2c094fa22", (FRONTEND / ".git" / "HEAD").read_text(encoding="ascii").strip())
        compositor = (SOURCE / "comfy_extras" / "nodes_compositor.py").read_text(encoding="utf-8")
        self.assertIn("Compositor supports at most {MAX_LAYERS} layers", compositor)
        self.assertIn("alpha * inv", compositor)
        self.assertIn("math.radians(rotation)", compositor)
        self.assertIn("state[\"inputs\"] == fp", compositor)
        painter_backend = (SOURCE / "comfy_extras" / "nodes_painter.py").read_text(encoding="utf-8")
        self.assertIn("base_image = image[:1]", painter_backend)
        self.assertIn("painter_rgb * painter_alpha + base_np * (1.0 - painter_alpha)", painter_backend)
        compare_backend = (SOURCE / "comfy_extras" / "nodes_image_compare.py").read_text(encoding="utf-8")
        self.assertIn('save_images(image_a, "comfy.compare.a")', compare_backend)

        compare_widget = (FRONTEND / "src" / "renderer" / "extensions" / "vueNodes" / "widgets" / "components" / "WidgetImageCompare.vue").read_text(encoding="utf-8")
        self.assertIn("useMouseInElement", compare_widget)
        self.assertIn("beforeBatchCount.value > 1 || afterBatchCount.value > 1", compare_widget)
        painter_frontend = (FRONTEND / "src" / "composables" / "painter" / "usePainter.ts").read_text(encoding="utf-8")
        self.assertIn("api.fetchApi('/upload/image'", painter_frontend)
        self.assertIn("targetWidget.serializeValue = serializeValue", painter_frontend)
        compositor_widget = (FRONTEND / "src" / "renderer" / "extensions" / "compositor" / "components" / "WidgetCompositor.vue").read_text(encoding="utf-8")
        self.assertIn("compositor.runWorkflowFirst", compositor_widget)
        self.assertIn("downloadPsd", compositor_widget)
        for relative, label in [
            ("src/lib/litegraph/src/widgets/ImageCompareWidget.ts", "node2only"),
            ("src/lib/litegraph/src/widgets/PainterWidget.ts", "drawVueOnlyWarning"),
            ("src/lib/litegraph/src/widgets/CompositorWidget.ts", "drawVueOnlyWarning"),
        ]:
            self.assertIn(label, (FRONTEND / relative).read_text(encoding="utf-8"))

    @unittest.skipUnless(WORKFLOW_WHEEL.exists(), "official workflow wheel is absent")
    def test_exhaustive_official_workflow_census_and_topology(self) -> None:
        self.assertEqual("242982d65e1c51ca03d892bc1009bb6843f457e7dfc0c20afe6438770b7a14a3", hashlib.sha256(WORKFLOW_WHEEL.read_bytes()).hexdigest())
        counts: Counter[tuple[str, str]] = Counter()
        files: dict[str, set[str]] = defaultdict(set)
        widgets: dict[str, Counter[str]] = defaultdict(Counter)
        workflows: dict[str, dict[str, Any]] = {}
        parsed = graphs = 0
        with zipfile.ZipFile(WORKFLOW_WHEEL) as archive:
            for member in sorted(name for name in archive.namelist() if name.endswith(".json")):
                payload = json.loads(archive.read(member).decode("utf-8"))
                parsed += 1
                if not isinstance(payload, dict):
                    continue
                if isinstance(payload.get("nodes"), list):
                    graphs += 1
                workflows[member] = payload
                for scope, node, _graph in records(payload):
                    class_type = node.get("type")
                    if class_type in {spec[1] for spec in ARTICLE_SPECS.values()}:
                        counts[(class_type, scope)] += 1
                        files[class_type].add(member)
                        widgets[class_type][json.dumps(node.get("widgets_values"), sort_keys=True)] += 1
        self.assertEqual((512, 496), (parsed, graphs))
        self.assertEqual((1, 0, 1), (counts[("ImageCompositor", "root")], counts[("ImageCompositor", "subgraph")], len(files["ImageCompositor"])))
        self.assertEqual((0, 0), (counts[("AddLayer", "root")], counts[("AddLayer", "subgraph")]))
        self.assertEqual((34, 0, 34), (counts[("ImageCompare", "root")], counts[("ImageCompare", "subgraph")], len(files["ImageCompare"])))
        self.assertEqual((4, 0, 3), (counts[("Painter", "root")], counts[("Painter", "subgraph")], len(files["Painter"])))
        self.assertEqual(31, widgets["ImageCompare"]["[]"])
        self.assertEqual(1, widgets["ImageCompositor"]["[{}]"])

        separation = next(payload for name, payload in workflows.items() if name.endswith("/api_bytedance_seedream_5_0_layer_separation.json"))
        nodes = {node["id"]: node for node in separation["nodes"]}
        self.assertEqual("ImageCompositor", nodes[25]["type"])
        self.assertEqual([{}], nodes[25]["widgets_values"])
        self.assertIn([29, 14, 5, 25, 0, "LAYERS"], separation["links"])
        anima = next(payload for name, payload in workflows.items() if name.endswith("/image_anima_lllite_image_inpainting.json"))
        anima_nodes = {node["id"]: node for node in anima["nodes"]}
        self.assertEqual("Painter", anima_nodes[694]["type"])
        self.assertEqual(["painter/painter-694-1784648658071.png [temp]", 1024, 1024, "#000000"], anima_nodes[694]["widgets_values"])
        self.assertIn([1736, 694, 1, 695, 0, "MASK"], anima["links"])
        magnific = next(payload for name, payload in workflows.items() if name.endswith("/api_magnific_image_upscale_creative.json"))
        self.assertIn([3, 2, 0, 4, 0, "IMAGE"], magnific["links"])
        self.assertIn([4, 1, 0, 4, 1, "IMAGE"], magnific["links"])

    @unittest.skipUnless(SOURCE.exists(), "pinned ComfyUI source checkout is absent")
    def test_safe_exact_source_probe(self) -> None:
        candidates = [Path(os.environ.get("TEMP", "")) / "nodes-wizard-comfyui-v0.32.0-venv" / "Scripts" / "python.exe", Path(sys.executable)]
        python = next((candidate for candidate in candidates if candidate.exists()), None)
        if python is None:
            self.skipTest("no Python interpreter for probe")
        result = subprocess.run([str(python), str(PROBE), str(SOURCE)], cwd=catalog.ROOT, text=True, capture_output=True, timeout=120, check=False)
        if result.returncode != 0 and python != Path(sys.executable):
            self.fail(result.stderr or result.stdout)
        if result.returncode != 0:
            self.skipTest(f"probe dependencies unavailable: {result.stderr}")
        payload = json.loads(result.stdout.strip().splitlines()[-1])
        self.assertEqual(2, payload["addLayer"]["frames"])
        self.assertAlmostEqual(1.5707963267948966, payload["addLayer"]["rotationRadians"])
        self.assertEqual([1, 2, 3, 3], payload["compositor"]["opaqueShape"])
        self.assertEqual([1, 4, 5, 4], payload["compositor"]["transparentShape"])
        self.assertEqual((2, 1), (payload["imageCompare"]["aFiles"], payload["imageCompare"]["bFiles"]))
        self.assertEqual([1, 4, 6, 3], payload["painter"]["paintedShape"])
        self.assertEqual([1, 64, 128, 3], payload["painter"]["blankShape"])


if __name__ == "__main__":
    unittest.main()
