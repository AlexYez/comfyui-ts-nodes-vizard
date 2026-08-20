from __future__ import annotations

import hashlib
import json
import re
import unittest
import zipfile
from typing import Any, Iterator

from tools import catalog
from tools.tests.gaussian_splat_render_transform_synthetic_probe import run_probe


ROOT = catalog.ROOT
CONTENT = catalog.CONTENT
SOURCE = ROOT / ".comfyui-source-0.32.0"
INVENTORY = CONTENT / "runtime" / "comfyui-0.32.0.object-info.json"
WORKFLOW = ROOT / ".upstream-cache" / "comfyui_workflow_templates_json-0.1.42-py3-none-any.whl"
DOCS = ROOT / ".upstream-cache" / "comfyui_embedded_docs-0.5.9-py3-none-any.whl"

SPECS = {
    "core.render-splat": ("render-splat", "RenderSplat", "sha256:6d735bfbee3f828506f1ffdb67e0af8cd186da07f5e608a5bc0f269e0db068c5", "recipe.render-splat-official-turntable"),
    "core.create-camera-info": ("create-camera-info", "CreateCameraInfo", "sha256:969f82b2711d7417f9236ffc7f0c9cf340093ab1f985a4584102cbb674b65cd3", "recipe.render-splat-official-turntable"),
    "core.transform-splat": ("transform-splat", "TransformSplat", "sha256:ea47fd1868d8f0109669ca2585fa783f306cb4331ef2fed6dafa3c009505bbf0", "recipe.transform-splat-yaw-90"),
    "core.get-splat-count": ("get-splat-count", "GetSplatCount", "sha256:f06a5d53cd19254f56754fea9284f245f000099f549a3e64bce9e9bb7788a524", "recipe.inspect-splat-count"),
}
RECIPES = {
    "recipe.render-splat-official-turntable": "render-splat-official-turntable",
    "recipe.transform-splat-yaw-90": "transform-splat-yaw-90",
    "recipe.inspect-splat-count": "inspect-splat-count",
}
DOC_HASHES = {
    ("RenderSplat", "en"): "13e0f3327336235f008443e3c82867dc3391f5826f3c06623bdcb36d74805adb",
    ("RenderSplat", "ru"): "23798494d0dfe8c12f6df4aecb4439a6e0c79178414ec75b37a40132ec31ebcf",
    ("CreateCameraInfo", "en"): "576868223e002238749b228fbe571d52a504de9b0cee4814acb534ece84dc17a",
    ("CreateCameraInfo", "ru"): "55c375c5207f35393165d01f1b3d8318f59620618cc51713917b197f5fa9a95d",
    ("TransformSplat", "en"): "86542b01963e4d9664417bcd6c4a7adee9785b5f683a92734aaf765620bc356c",
    ("TransformSplat", "ru"): "7f077f765cd683e75ddd3fbcabb929f5e87fab692230acda7231c9bf4921cfe2",
    ("GetSplatCount", "en"): "0134d2e39ad4a61622f44f312cb9b64d9306d62de4d42406aeacecaa688f97a4",
    ("GetSplatCount", "ru"): "a88ece3b43c36603df444acbe08e4d165b9bca6223fd3399ed77848182968ac2",
}
TARGETS = {value[1] for value in SPECS.values()}


def iter_nodes(payload: dict[str, Any]) -> Iterator[dict[str, Any]]:
    yield from (node for node in payload.get("nodes", []) if isinstance(node, dict))
    definitions = payload.get("definitions")
    for subgraph in definitions.get("subgraphs", []) if isinstance(definitions, dict) else []:
        yield from (node for node in subgraph.get("nodes", []) if isinstance(node, dict))


def article_ids() -> set[str]:
    return {catalog.load_json(path)["articleId"] for path in (CONTENT / "articles").rglob("manifest.json")}


class GaussianSplatRenderTransformContentTests(unittest.TestCase):
    def test_schemas_honesty_relations_and_russian(self) -> None:
        schemas = {name: catalog.load_json(CONTENT / "schemas" / name) for name in (
            "article.schema.v1.json", "recipe.schema.v1.json", "recipe-fragment.schema.v1.json", "article-research.schema.v1.json"
        )}
        ids = article_ids()
        errors: list[str] = []
        for article_id, (directory, class_type, fingerprint, recipe_id) in SPECS.items():
            path = CONTENT / "articles" / "core" / directory / "manifest.json"
            article = catalog.load_json(path)
            self.assertEqual([], catalog.json_schema_errors(article, schemas["article.schema.v1.json"]))
            catalog.validate_article(path, article, errors)
            self.assertEqual(class_type, article["runtimeIdentity"]["classType"])
            self.assertEqual("draft", article["status"])
            self.assertEqual("in_review", article["editorial"]["state"])
            self.assertEqual(fingerprint, article["editorial"]["schemaHash"])
            self.assertIn(recipe_id, [asset["id"] for asset in article["assets"]])
            self.assertTrue(set(article["relations"]["related"]).issubset(ids))
            body = (path.parent / "ru.md").read_text(encoding="utf-8")
            self.assertEqual(10, len(re.findall(r"^## ", body, flags=re.MULTILINE)))
            self.assertIn("Редактор пока не проверил материал вручную.", body)
            self.assertNotRegex(body.lower(), r"важно отметить|стоит отметить|в современном мире|революционн|данная нода|давайте разбер|подводя итог|мощный инструмент")
            ledger = catalog.load_json(CONTENT / "research" / "reviews" / f"{article_id}.json")
            self.assertEqual([], catalog.json_schema_errors(ledger, schemas["article-research.schema.v1.json"]))
            self.assertEqual("fact_checked", ledger["state"])
            self.assertEqual("automated_assisted", ledger["reviewMode"])
            self.assertFalse(ledger["checks"]["exampleExecuted"])

        for recipe_id, directory in RECIPES.items():
            path = CONTENT / "recipes" / directory / "recipe.json"
            recipe = catalog.load_json(path)
            self.assertEqual(recipe_id, recipe["recipeId"])
            self.assertEqual([], catalog.json_schema_errors(recipe, schemas["recipe.schema.v1.json"]))
            catalog.validate_recipe(path, recipe, ids, errors)
            self.assertEqual("in_review", recipe["editorial"]["state"])
            self.assertNotIn("workflow", recipe)
            fragment_path = path.parent / "fragment.json"
            fragment = catalog.load_json(fragment_path)
            self.assertEqual([], catalog.json_schema_errors(fragment, schemas["recipe-fragment.schema.v1.json"]))
            catalog.validate_fragment(fragment_path, fragment, errors)
        self.assertEqual([], errors)

    def test_runtime_fingerprints_ports_flags_and_constraints(self) -> None:
        inventory = catalog.load_json(INVENTORY)
        for _, class_type, fingerprint, _ in SPECS.values():
            definition = inventory[class_type]
            self.assertEqual("comfy_extras.nodes_gaussian_splat", definition["python_module"])
            self.assertEqual(fingerprint, catalog.schema_fingerprint(class_type, definition))
            for flag in ("experimental", "deprecated", "dev_only", "api_node"):
                self.assertFalse(definition[flag])
        render = inventory["RenderSplat"]
        self.assertEqual(["IMAGE", "MASK"], render["output"])
        self.assertEqual(["image", "mask"], render["output_name"])
        self.assertEqual(["splat", "width", "height", "frames", "splat_scale", "sharpen", "headlight_shading", "opacity_threshold", "render_style", "background"], render["input_order"]["required"])
        self.assertEqual(["bg_image", "camera_info"], render["input_order"]["optional"])
        self.assertEqual({"default": 1024, "min": 64, "max": 2048, "step": 8}, render["input"]["required"]["width"][1])
        self.assertEqual((1, -240, 240), tuple(render["input"]["required"]["frames"][1][key] for key in ("default", "min", "max")))
        self.assertEqual(["color", "clay", "depth", "normal"], render["input"]["required"]["render_style"][1]["options"])

        camera = inventory["CreateCameraInfo"]
        self.assertEqual(["LOAD3D_CAMERA"], camera["output"])
        options = camera["input"]["required"]["mode"][1]["options"]
        self.assertEqual(["orbit", "look_at", "quaternion"], [option["key"] for option in options])
        self.assertEqual(["yaw", "pitch", "distance"], list(options[0]["inputs"]["required"]))
        self.assertEqual(["perspective", "orthographic"], camera["input"]["required"]["camera_type"][1]["options"])

        transform = inventory["TransformSplat"]
        self.assertEqual(["SPLAT"], transform["output"])
        self.assertEqual(0.01, transform["input"]["required"]["scale_x"][1]["min"])
        self.assertEqual(100.0, transform["input"]["required"]["scale_x"][1]["max"])
        count = inventory["GetSplatCount"]
        self.assertEqual(["SPLAT", "INT"], count["output"])
        self.assertEqual(["unique_id"], count["input_order"]["hidden"])

    def test_exact_source_synthetic_probe(self) -> None:
        result = run_probe(SOURCE)
        self.assertEqual([1.241829, 1.25, 1.773516], result["cameraOrbitPosition"])
        self.assertTrue(result["quaternionNormalized"])
        self.assertTrue(result["quaternionIgnoresTargetAndRoll"])
        self.assertTrue(result["uniformTransform"])
        self.assertTrue(result["nonUniformCovarianceTransform"])
        self.assertTrue(result["countsAware"])
        self.assertEqual([6, 72, 64, 3], result["renderBatchFrames"])
        source = (SOURCE / "comfy_extras" / "nodes_gaussian_splat.py").read_text(encoding="utf-8")
        self.assertIn("n_frames = abs(int(frames)) or 1", source)
        self.assertIn("orbit_dir = -1.0 if frames < 0 else 1.0", source)
        self.assertIn("A = D[:, None] * R", source)
        self.assertIn("cov = A @ cov @ A.T", source)
        self.assertIn("count = sum(_real_len(splat, i)", source)

    def test_docs_hashes(self) -> None:
        self.assertEqual("30afae432a71c96aa59421d0f37388c66ff6572b8cbeee8ff045e4d5f84f896c", hashlib.sha256(DOCS.read_bytes()).hexdigest())
        with zipfile.ZipFile(DOCS) as archive:
            for (class_type, locale), expected in DOC_HASHES.items():
                self.assertEqual(expected, hashlib.sha256(archive.read(f"comfyui_embedded_docs/docs/{class_type}/{locale}.md")).hexdigest())

    def test_workflow_census_and_official_topology(self) -> None:
        self.assertEqual("242982d65e1c51ca03d892bc1009bb6843f457e7dfc0c20afe6438770b7a14a3", hashlib.sha256(WORKFLOW.read_bytes()).hexdigest())
        counts = {target: 0 for target in TARGETS}
        json_count = roots = subgraphs = 0
        official: dict[str, Any] | None = None
        with zipfile.ZipFile(WORKFLOW) as archive:
            for name in archive.namelist():
                if not name.endswith(".json"):
                    continue
                json_count += 1
                payload = json.loads(archive.read(name))
                if isinstance(payload, dict) and isinstance(payload.get("nodes"), list):
                    roots += 1
                if isinstance(payload, dict):
                    definitions = payload.get("definitions")
                    if isinstance(definitions, dict):
                        subgraphs += len(definitions.get("subgraphs", []))
                    for node in iter_nodes(payload):
                        if node.get("type") in counts:
                            counts[node["type"]] += 1
                if name.endswith("3d_triposplat_image_to_gaussian_splat.json"):
                    official = payload
        self.assertEqual((512, 496, 272), (json_count, roots, subgraphs))
        self.assertEqual({"RenderSplat": 1, "CreateCameraInfo": 1, "TransformSplat": 0, "GetSplatCount": 0}, counts)
        self.assertIsNotNone(official)
        nodes = {node["type"]: node for node in official["nodes"] if node.get("type") in {"RenderSplat", "CreateCameraInfo", "CreateVideo"}}
        self.assertEqual([35, 30, 2.5, 0, 0, 0, 0, 35, 1, "perspective"], nodes["CreateCameraInfo"]["widgets_values"][1:])
        self.assertEqual([1024, 1024, 75, 1, 2, 0, 0, "color", "#848484"], nodes["RenderSplat"]["widgets_values"])
        self.assertEqual([25], nodes["CreateVideo"]["widgets_values"])
        self.assertIn([160, 79, 0, 75, 2, "LOAD3D_CAMERA"], official["links"])
        self.assertIn([152, 75, 0, 41, 0, "IMAGE"], official["links"])


if __name__ == "__main__":
    unittest.main()
