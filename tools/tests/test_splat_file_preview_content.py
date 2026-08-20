from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import sys
import unittest
import zipfile
from collections import Counter
from pathlib import Path
from typing import Any, Iterator

from tools import catalog


ARTICLE_SPECS = {
    "core.preview-gaussian-splat": {
        "directory": "preview-gaussian-splat",
        "classType": "PreviewGaussianSplat",
        "module": "comfy_extras.nodes_load_3d",
        "category": "3d",
        "experimental": True,
        "outputNode": True,
        "fingerprint": "sha256:99f0a9f4adfd966db8a6a6db55c23ad4bcb7d61ae42013cda266513ddefb2609",
        "recipe": "recipe.preview-gaussian-splat-source",
    },
    "core.preview-point-cloud": {
        "directory": "preview-point-cloud",
        "classType": "PreviewPointCloud",
        "module": "comfy_extras.nodes_load_3d",
        "category": "3d",
        "experimental": True,
        "outputNode": True,
        "fingerprint": "sha256:3d05abf31a3d459ab35688501dd25b541ce6f4d18551f6d0a0f044319e4a15e9",
        "recipe": "recipe.preview-point-cloud-source",
    },
    "core.splat-to-file-3d": {
        "directory": "splat-to-file-3d",
        "classType": "SplatToFile3D",
        "module": "comfy_extras.nodes_gaussian_splat",
        "category": "3d/splat",
        "experimental": False,
        "outputNode": False,
        "fingerprint": "sha256:e4076225f5dadf9e1bed10d7de806916b6780434dd210b72340eecd782395711",
        "recipe": "recipe.splat-to-spz-official-save",
    },
    "core.file-3d-to-splat": {
        "directory": "file-3d-to-splat",
        "classType": "File3DToSplat",
        "module": "comfy_extras.nodes_gaussian_splat",
        "category": "3d/splat",
        "experimental": False,
        "outputNode": False,
        "fingerprint": "sha256:99e395c66254c8c6b3ca404a00c29ab67b2e1d20b0a24df69e5ad1d8ba18ea4f",
        "recipe": "recipe.file-3d-to-splat-inspect",
    },
}

RECIPE_DIRECTORIES = {
    "recipe.preview-gaussian-splat-source": "preview-gaussian-splat-source",
    "recipe.preview-point-cloud-source": "preview-point-cloud-source",
    "recipe.splat-to-spz-official-save": "splat-to-spz-official-save",
    "recipe.file-3d-to-splat-inspect": "file-3d-to-splat-inspect",
}

EXPECTED_HEADINGS = [
    "Что делает нода",
    "Когда использовать и когда не использовать",
    "Короткий рецепт подключения",
    "Входы, выходы и параметры",
    "Типовые связки",
    "Практический пример",
    "Частые ошибки и способы проверки",
    "Производительность и внутреннее поведение",
    "Совместимость, изменения и устаревание",
    "Связанные ноды и источники",
]

FULL_INVENTORY = catalog.CONTENT / "runtime" / "comfyui-0.32.0.object-info.json"
REPLACEMENTS = catalog.CONTENT / "runtime" / "comfyui-0.32.0.node-replacements.json"
SOURCE = catalog.ROOT / ".comfyui-source-0.32.0"
FRONTEND = catalog.ROOT / ".frontend-source-1.48.7"
WORKFLOW_WHEEL = catalog.ROOT / ".upstream-cache" / "comfyui_workflow_templates_json-0.1.42-py3-none-any.whl"
WORKFLOW_WHEEL_SHA256 = "242982d65e1c51ca03d892bc1009bb6843f457e7dfc0c20afe6438770b7a14a3"
DOCS_WHEEL = catalog.ROOT / ".upstream-cache" / "comfyui_embedded_docs-0.5.9-py3-none-any.whl"
DOCS_WHEEL_SHA256 = "30afae432a71c96aa59421d0f37388c66ff6572b8cbeee8ff045e4d5f84f896c"
PROBE = Path(__file__).with_name("splat_file_preview_synthetic_probe.py")


def article_path(spec: dict[str, Any]) -> Path:
    return catalog.CONTENT / "articles" / "core" / spec["directory"] / "manifest.json"


def recipe_path(recipe_id: str) -> Path:
    return catalog.CONTENT / "recipes" / RECIPE_DIRECTORIES[recipe_id] / "recipe.json"


def all_article_ids() -> set[str]:
    result: set[str] = set()
    for path in (catalog.CONTENT / "articles").rglob("manifest.json"):
        payload = catalog.load_json(path)
        if isinstance(payload, dict) and isinstance(payload.get("articleId"), str):
            result.add(payload["articleId"])
    return result


def runtime_inputs(runtime: dict[str, Any]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for group in ("required", "optional"):
        values = runtime.get("input", {}).get(group, {})
        if isinstance(values, dict):
            result.update(values)
    return result


def workflow_graphs(payload: dict[str, Any]) -> Iterator[dict[str, Any]]:
    if isinstance(payload.get("nodes"), list):
        yield payload
    definitions = payload.get("definitions")
    subgraphs = definitions.get("subgraphs", []) if isinstance(definitions, dict) else []
    for subgraph in subgraphs:
        if isinstance(subgraph, dict):
            yield from workflow_graphs(subgraph)


class SplatFilePreviewContentTests(unittest.TestCase):
    def test_articles_recipes_research_and_natural_russian(self) -> None:
        article_ids = all_article_ids()
        article_schema = catalog.load_json(catalog.CONTENT / "schemas" / "article.schema.v1.json")
        recipe_schema = catalog.load_json(catalog.CONTENT / "schemas" / "recipe.schema.v1.json")
        fragment_schema = catalog.load_json(catalog.CONTENT / "schemas" / "recipe-fragment.schema.v1.json")
        research_schema = catalog.load_json(catalog.CONTENT / "schemas" / "article-research.schema.v1.json")
        errors: list[str] = []
        cliche_pattern = re.compile(
            r"без воды|коротко о главном|понятно и доступно|по-честному|"
            r"идеальн|революционн|уникальная возможность|в современном мире|"
            r"давайте разбер|важно отметить|стоит подчеркнуть|подводя итог|"
            r"данная нода|является незаменим|устали от|знакомо\?|успейте",
            re.IGNORECASE,
        )

        for article_id, spec in ARTICLE_SPECS.items():
            path = article_path(spec)
            article = catalog.load_json(path)
            self.assertEqual([], catalog.json_schema_errors(article, article_schema))
            catalog.validate_article(path, article, errors)
            self.assertEqual(article_id, article["articleId"])
            self.assertEqual("draft", article["status"])
            self.assertEqual(spec["experimental"], article["experimental"])
            self.assertEqual("in_review", article["editorial"]["state"])
            self.assertEqual(spec["recipe"], article["assets"][0]["id"])
            targets = article["relations"]["related"] + article["relations"]["alternatives"]
            self.assertTrue(set(targets).issubset(article_ids))

            body = (path.parent / article["body"]).read_text(encoding="utf-8")
            self.assertEqual(EXPECTED_HEADINGS, re.findall(r"^## (.+)$", body, re.MULTILINE))
            self.assertNotIn("�", body)
            self.assertNotRegex(body, cliche_pattern)

            research = catalog.load_json(catalog.CONTENT / "research" / "reviews" / f"{article_id}.json")
            self.assertEqual([], catalog.json_schema_errors(research, research_schema))
            self.assertEqual(spec["classType"], research["node"]["classType"])
            self.assertEqual(spec["module"], research["node"]["pythonModule"])
            self.assertEqual("fact_checked", research["state"])
            self.assertEqual("automated_assisted", research["reviewMode"])
            self.assertFalse(research["checks"]["exampleExecuted"])
            self.assertTrue(research["checks"]["exampleSchemaValidated"])
            self.assertTrue(research["checks"]["russianEdited"])
            self.assertTrue(research["checks"]["factsRecheckedAfterEditing"])
            self.assertTrue(any("человеческ" in gap.lower() for gap in research["knownGaps"]))

        for recipe_id in RECIPE_DIRECTORIES:
            path = recipe_path(recipe_id)
            recipe = catalog.load_json(path)
            self.assertEqual([], catalog.json_schema_errors(recipe, recipe_schema))
            catalog.validate_recipe(path, recipe, article_ids, errors)
            self.assertNotIn("workflow", recipe)
            body = (path.parent / recipe["body"]).read_text(encoding="utf-8")
            self.assertNotRegex(body, cliche_pattern)
            fragment = catalog.load_json(path.parent / recipe["fragment"]["path"])
            self.assertEqual([], catalog.json_schema_errors(fragment, fragment_schema))
            compiled = catalog.compile_recipe(path, recipe)
            self.assertIn("fragmentData", compiled)
            self.assertNotIn("workflowData", compiled)
        self.assertEqual([], errors)

    def test_runtime_fingerprints_flags_ports_and_exact_recipe_settings(self) -> None:
        nodes = catalog.object_info_nodes(catalog.load_json(FULL_INVENTORY))
        for spec in ARTICLE_SPECS.values():
            runtime = dict(nodes[spec["classType"]])
            article = catalog.load_json(article_path(spec))
            self.assertEqual(spec["module"], runtime["python_module"])
            self.assertEqual(spec["category"], runtime["category"])
            self.assertEqual(spec["experimental"], runtime["experimental"])
            self.assertEqual(spec["outputNode"], runtime["output_node"])
            self.assertEqual(spec["fingerprint"], catalog.schema_fingerprint(spec["classType"], runtime))
            self.assertEqual(spec["fingerprint"], article["editorial"]["schemaHash"])
            for flag in ("deprecated", "dev_only", "api_node", "is_input_list"):
                self.assertFalse(runtime[flag])

        splat_preview = nodes["PreviewGaussianSplat"]
        self.assertEqual(["model_3d", "viewport_state", "width", "height"], splat_preview["input_order"]["required"])
        self.assertEqual(["model_3d_info", "camera_info"], splat_preview["input_order"]["optional"])
        self.assertEqual(["FILE_3D_SPLAT_ANY", "LOAD3D_MODEL_INFO", "LOAD3D_CAMERA", "INT", "INT"], splat_preview["output"])
        self.assertEqual(1024, splat_preview["input"]["required"]["width"][1]["default"])
        self.assertEqual(4096, splat_preview["input"]["required"]["height"][1]["max"])

        point_preview = nodes["PreviewPointCloud"]
        self.assertEqual("FILE_3D_POINT_CLOUD_ANY,FILE_3D_PLY", point_preview["input"]["required"]["model_3d"][0])
        self.assertEqual(["FILE_3D_POINT_CLOUD_ANY", "LOAD3D_MODEL_INFO", "LOAD3D_CAMERA", "INT", "INT"], point_preview["output"])

        to_file = nodes["SplatToFile3D"]
        self.assertEqual(["splat", "format"], to_file["input_order"]["required"])
        self.assertEqual(["ply", "ksplat", "spz"], to_file["input"]["required"]["format"][1]["options"])
        self.assertEqual(["FILE_3D_SPLAT_ANY"], to_file["output"])

        from_file = nodes["File3DToSplat"]
        self.assertIn("FILE_3D_SPLAT_ANY", from_file["input"]["required"]["model_3d"][0])
        self.assertEqual(["SPLAT"], from_file["output"])

        expected_nodes = {
            "recipe.preview-gaussian-splat-source": [("PreviewGaussianSplat", {"width": 1024, "height": 1024})],
            "recipe.preview-point-cloud-source": [("PreviewPointCloud", {"width": 1024, "height": 1024})],
            "recipe.splat-to-spz-official-save": [("SplatToFile3D", {"format": "spz"}), ("SaveGLB", {"filename_prefix": "3d/ComfyUI_TripoSplat"})],
            "recipe.file-3d-to-splat-inspect": [("File3DToSplat", {}), ("GetSplatCount", {})],
        }
        for recipe_id, expected in expected_nodes.items():
            path = recipe_path(recipe_id)
            recipe = catalog.load_json(path)
            fragment = catalog.load_json(path.parent / recipe["fragment"]["path"])
            self.assertEqual(expected, [(n["classType"], n["settings"]) for n in fragment["nodes"]])
            refs = {n["ref"]: n for n in fragment["nodes"]}
            for external in fragment["externalInputs"]:
                runtime = dict(nodes[refs[external["to"]]["classType"]])
                accepted = runtime_inputs(runtime)[external["input"]][0].split(",")
                self.assertIn(external["type"], accepted)

    @unittest.skipUnless(SOURCE.exists() and FRONTEND.exists(), "pinned source checkout is absent")
    def test_exact_backend_and_frontend_contracts_and_replacement_absence(self) -> None:
        load3d = (SOURCE / "comfy_extras" / "nodes_load_3d.py").read_text(encoding="utf-8")
        gaussian = (SOURCE / "comfy_extras" / "nodes_gaussian_splat.py").read_text(encoding="utf-8")
        geometry = (SOURCE / "comfy_api" / "latest" / "_util" / "geometry_types.py").read_text(encoding="utf-8")
        preview_ext = (FRONTEND / "src" / "extensions" / "core" / "load3dPreviewExtensions.ts").read_text(encoding="utf-8")
        loader = (FRONTEND / "src" / "extensions" / "core" / "load3d" / "LoaderManager.ts").read_text(encoding="utf-8")
        splat_adapter = (FRONTEND / "src" / "extensions" / "core" / "load3d" / "SplatModelAdapter.ts").read_text(encoding="utf-8")
        point_adapter = (FRONTEND / "src" / "extensions" / "core" / "load3d" / "PointCloudModelAdapter.ts").read_text(encoding="utf-8")
        ply = (FRONTEND / "src" / "scripts" / "metadata" / "ply.ts").read_text(encoding="utf-8")

        for marker in (
            'filename = f"preview_splat_{uuid.uuid4().hex}.{model_3d.format}"',
            'filename = f"preview_pointcloud_{uuid.uuid4().hex}.{model_3d.format}"',
            "model_3d.save_to(os.path.join(folder_paths.get_temp_directory(), filename))",
            "camera_info_input if camera_info_input is not None else viewport_state.get('camera_info')",
            "model_3d_info_input if model_3d_info_input is not None else viewport_state.get('model_3d_info', [])",
        ):
            self.assertIn(marker, load3d)

        for marker in (
            'FORMAT_WRITERS = {',
            '"ply": _gaussian_ply_bytes',
            '"ksplat": _gaussian_ksplat_bytes',
            '"spz": _gaussian_spz_bytes',
            "if splat.positions.shape[0] > 1:",
            "end = _real_len(splat, 0)",
            'fmt = (model_3d.format or "").lower()',
            "_GAUSSIAN_PARSERS.get(fmt) or _GAUSSIAN_PARSERS[_detect_splat_format(data)]",
            "if len(data) % 32 == 0:",
        ):
            self.assertIn(marker, gaussian)
        self.assertIn("Supports both disk-backed (file path) and memory-backed (BytesIO) storage", geometry)

        self.assertIn("createPreview3DExtension(", preview_ext)
        self.assertIn("'PreviewGaussianSplat'", preview_ext)
        self.assertIn("'PreviewPointCloud'", preview_ext)
        self.assertIn("'temp'", preview_ext)
        self.assertIn("sceneWidget.serializeValue = async () =>", preview_ext)
        self.assertIn("load3d.setTargetSize(", preview_ext)
        self.assertIn("new SplatModelAdapter(),", loader)
        self.assertIn("new PointCloudModelAdapter()", loader)
        self.assertIn("readonly extensions = ['spz', 'splat', 'ksplat', 'ply']", splat_adapter)
        self.assertIn("splatMesh.quaternion.set(1, 0, 0, 0)", splat_adapter)
        self.assertIn("readonly extensions = ['ply']", point_adapter)
        self.assertIn("geometry.computeBoundingSphere()", point_adapter)
        self.assertIn("const hasFaces = (plyGeometry.index?.count ?? 0) > 0", point_adapter)
        self.assertIn("const hasScales", ply)
        self.assertIn("const hasRots", ply)

        replacement_text = json.dumps(catalog.load_json(REPLACEMENTS), ensure_ascii=False)
        for spec in ARTICLE_SPECS.values():
            self.assertNotIn(spec["classType"], replacement_text)

    @unittest.skipUnless(DOCS_WHEEL.exists(), "pinned docs wheel absent")
    def test_pinned_embedded_docs_routes(self) -> None:
        self.assertEqual(DOCS_WHEEL_SHA256, hashlib.sha256(DOCS_WHEEL.read_bytes()).hexdigest())
        members = {
            "comfyui_embedded_docs/docs/PreviewGaussianSplat/en.md": "Supported formats: splat, ply, spz, ksplat",
            "comfyui_embedded_docs/docs/PreviewPointCloud/en.md": "saves the point cloud to a temporary file",
            "comfyui_embedded_docs/docs/SplatToFile3D/en.md": "full spherical harmonics",
            "comfyui_embedded_docs/docs/File3DToSplat/en.md": "automatically detected from the file contents",
        }
        with zipfile.ZipFile(DOCS_WHEEL) as archive:
            for member, marker in members.items():
                self.assertIn(marker.lower(), archive.read(member).decode("utf-8").lower())

    @unittest.skipUnless(WORKFLOW_WHEEL.exists(), "workflow wheel absent")
    def test_exhaustive_workflow_census_and_official_spz_topology(self) -> None:
        self.assertEqual(WORKFLOW_WHEEL_SHA256, hashlib.sha256(WORKFLOW_WHEEL.read_bytes()).hexdigest())
        counts: Counter[str] = Counter()
        hits: list[tuple[str, dict[str, Any], dict[str, Any], list[Any]]] = []
        file_count = root_count = graph_count = 0
        targets = {spec["classType"] for spec in ARTICLE_SPECS.values()}
        with zipfile.ZipFile(WORKFLOW_WHEEL) as archive:
            for member in sorted(archive.namelist()):
                if "/templates/" not in member or not member.endswith(".json"):
                    continue
                file_count += 1
                payload = json.loads(archive.read(member).decode("utf-8"))
                if not isinstance(payload, dict):
                    continue
                if isinstance(payload.get("nodes"), list):
                    root_count += 1
                for graph in workflow_graphs(payload):
                    graph_count += 1
                    by_id = {str(n.get("id")): n for n in graph.get("nodes", []) if isinstance(n, dict)}
                    for node in graph.get("nodes", []):
                        if isinstance(node, dict) and node.get("type") in targets:
                            counts[node["type"]] += 1
                            hits.append((member, node, by_id, graph.get("links", [])))
        self.assertEqual(512, file_count)
        self.assertEqual(496, root_count)
        self.assertEqual(768, graph_count)
        self.assertEqual(Counter({"SplatToFile3D": 1}), counts)
        member, node, by_id, links = hits[0]
        self.assertTrue(member.endswith("3d_triposplat_image_to_gaussian_splat.json"))
        self.assertEqual(92, node["id"])
        self.assertEqual(["spz"], node["widgets_values"])
        incoming = next(link for link in links if link[3] == 92)
        outgoing = next(link for link in links if link[1] == 92)
        self.assertEqual("SPLAT", incoming[5])
        self.assertEqual(51, outgoing[3])
        self.assertEqual("SaveGLB", by_id[str(outgoing[3])]["type"])
        self.assertEqual("3d/ComfyUI_TripoSplat", by_id["51"]["widgets_values"][0])

    @unittest.skipUnless(SOURCE.exists(), "pinned source absent")
    def test_safe_exact_source_file_and_preview_probe(self) -> None:
        candidates = [
            Path(os.environ.get("TEMP", "")) / "nodes-wizard-comfyui-v0.32.0-venv" / "Scripts" / "python.exe",
            Path(sys.executable),
        ]
        python = next((candidate for candidate in candidates if candidate.exists()), None)
        if python is None:
            self.skipTest("no probe Python")
        result = subprocess.run(
            [str(python), "-X", "utf8", str(PROBE)],
            cwd=catalog.ROOT,
            text=True,
            capture_output=True,
            timeout=120,
            check=False,
        )
        if result.returncode != 0 and python == Path(sys.executable):
            self.skipTest(f"torch/numpy unavailable: {result.stderr}")
        self.assertEqual(0, result.returncode, result.stderr or result.stdout)
        payload = json.loads(result.stdout.strip().splitlines()[-1])

        files = payload["fileRoundTrip"]
        self.assertTrue(files["batchTwoUsesFirstCountTwo"])
        self.assertTrue(files["blankFormatDetectsPLY"])
        self.assertTrue(files["rawSplatDetectedFromThirtyTwoBytes"])
        self.assertTrue(files["emptyBytesBecomeEmptySplat"])
        self.assertTrue(files["unsupportedWriterRaises"])
        self.assertTrue(files["emptyExportRaises"])
        self.assertTrue(files["invalidContentDetectionRaises"])
        self.assertTrue(files["recognizedFormatMetadataTakesPrecedence"])
        self.assertTrue(files["formats"]["ply"]["fullSHClose"])
        self.assertEqual([1, 2, 4, 3], files["formats"]["ply"]["shShape"])
        self.assertEqual([1, 2, 1, 3], files["formats"]["ksplat"]["shShape"])
        self.assertEqual([1, 2, 1, 3], files["formats"]["spz"]["shShape"])
        for format_data in files["formats"].values():
            self.assertTrue(format_data["positionsClose"])
            self.assertTrue(format_data["scalesClose"])
            self.assertTrue(format_data["rotationsNormalized"])
            self.assertTrue(format_data["opacitiesClose"])

        preview = payload["preview"]
        self.assertTrue(preview["tempFilesExistDuringExecution"])
        self.assertTrue(preview["splatBytesPreserved"])
        self.assertTrue(preview["pointBytesPreserved"])
        self.assertTrue(preview["explicitCameraOverridesViewport"])
        self.assertTrue(preview["explicitModelInfoOverridesViewport"])
        self.assertTrue(preview["pointUsesViewportCamera"])
        self.assertTrue(preview["pointUsesViewportModelInfo"])
        self.assertEqual([True, True, True, True, True], preview["splatPassThroughValues"])
        self.assertEqual([[], None], preview["nonDictViewportDefaults"])
        self.assertEqual("PreviewUI3DAdvanced", preview["uiKind"])


if __name__ == "__main__":
    unittest.main()
