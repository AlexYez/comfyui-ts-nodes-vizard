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
    "core.save-glb": {
        "directory": "save-glb",
        "classType": "SaveGLB",
        "experimental": False,
        "fingerprint": "sha256:4474c1f85e14392be1eabb1001bcae0c1fb9a2b78ea09754d11afa584a5c302a",
        "recipe": "recipe.save-glb-official-spz",
    },
    "core.save-3d-advanced": {
        "directory": "save-3d-advanced",
        "classType": "Save3DAdvanced",
        "experimental": True,
        "fingerprint": "sha256:9fd5832dfd489f2549aef43574b13f09f2e91dcd72ae3dd0bdb8a847845d9fdb",
        "recipe": "recipe.save-3d-advanced-source",
    },
    "core.save-gaussian-splat": {
        "directory": "save-gaussian-splat",
        "classType": "SaveGaussianSplat",
        "experimental": True,
        "fingerprint": "sha256:cae4d85aa5258b1274bdc5a5823eaeb03c3db588b20c6176271a240f9c124df0",
        "recipe": "recipe.save-gaussian-splat-source",
    },
    "core.save-point-cloud": {
        "directory": "save-point-cloud",
        "classType": "SavePointCloud",
        "experimental": True,
        "fingerprint": "sha256:42942d8ac3ab81716b586d8a2da9b0121a8fc17bb07f581ad4237a54d4ef02a0",
        "recipe": "recipe.save-point-cloud-source",
    },
}

RECIPE_DIRECTORIES = {
    "recipe.save-glb-official-spz": "save-glb-official-spz",
    "recipe.save-3d-advanced-source": "save-3d-advanced-source",
    "recipe.save-gaussian-splat-source": "save-gaussian-splat-source",
    "recipe.save-point-cloud-source": "save-point-cloud-source",
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
PROBE = Path(__file__).with_name("save_3d_synthetic_probe.py")


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


class Save3DContentTests(unittest.TestCase):
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
            self.assertEqual([], article["runtimeIdentity"]["aliases"])
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
            self.assertEqual("comfy_extras.nodes_save_3d", research["node"]["pythonModule"])
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

    def test_runtime_fingerprints_flags_ports_and_recipe_settings(self) -> None:
        nodes = catalog.object_info_nodes(catalog.load_json(FULL_INVENTORY))
        for spec in ARTICLE_SPECS.values():
            runtime = dict(nodes[spec["classType"]])
            article = catalog.load_json(article_path(spec))
            self.assertEqual("comfy_extras.nodes_save_3d", runtime["python_module"])
            self.assertEqual("3d", runtime["category"])
            self.assertEqual(spec["experimental"], runtime["experimental"])
            self.assertTrue(runtime["output_node"])
            self.assertEqual(spec["fingerprint"], catalog.schema_fingerprint(spec["classType"], runtime))
            self.assertEqual(spec["fingerprint"], article["editorial"]["schemaHash"])
            for flag in ("deprecated", "dev_only", "api_node", "is_input_list"):
                self.assertFalse(runtime[flag])

        save_glb = nodes["SaveGLB"]
        self.assertEqual(["mesh", "filename_prefix"], save_glb["input_order"]["required"])
        self.assertEqual(["prompt", "extra_pnginfo"], save_glb["input_order"]["hidden"])
        self.assertEqual([], save_glb["output"])
        self.assertEqual("3d/ComfyUI", save_glb["input"]["required"]["filename_prefix"][1]["default"])
        mesh_types = save_glb["input"]["required"]["mesh"][0].split(",")
        for accepted in ("MESH", "FILE_3D_GLB", "FILE_3D_SPZ", "FILE_3D_POINT_CLOUD_ANY", "FILE_3D"):
            self.assertIn(accepted, mesh_types)

        advanced = nodes["Save3DAdvanced"]
        self.assertEqual(
            ["model_3d", "filename_prefix", "viewport_state", "width", "height"],
            advanced["input_order"]["required"],
        )
        self.assertEqual(["model_3d_info", "camera_info"], advanced["input_order"]["optional"])
        self.assertEqual(
            ["FILE_3D", "LOAD3D_MODEL_INFO", "LOAD3D_CAMERA", "INT", "INT"],
            advanced["output"],
        )

        gaussian = nodes["SaveGaussianSplat"]
        self.assertEqual(
            "FILE_3D_SPLAT_ANY,FILE_3D_PLY,FILE_3D_SPLAT,FILE_3D_SPZ,FILE_3D_KSPLAT",
            gaussian["input"]["required"]["model_3d"][0],
        )
        self.assertEqual("FILE_3D_SPLAT_ANY", gaussian["output"][0])

        point = nodes["SavePointCloud"]
        self.assertEqual(
            "FILE_3D_POINT_CLOUD_ANY,FILE_3D_PLY",
            point["input"]["required"]["model_3d"][0],
        )
        self.assertEqual("FILE_3D_POINT_CLOUD_ANY", point["output"][0])

        expected_nodes = {
            "recipe.save-glb-official-spz": [
                ("SplatToFile3D", {"format": "spz"}),
                ("SaveGLB", {"filename_prefix": "3d/ComfyUI_TripoSplat"}),
            ],
            "recipe.save-3d-advanced-source": [
                ("Save3DAdvanced", {"filename_prefix": "3d/ComfyUI", "width": 1024, "height": 1024})
            ],
            "recipe.save-gaussian-splat-source": [
                ("SaveGaussianSplat", {"filename_prefix": "3d/ComfyUI", "width": 1024, "height": 1024})
            ],
            "recipe.save-point-cloud-source": [
                ("SavePointCloud", {"filename_prefix": "3d/ComfyUI", "width": 1024, "height": 1024})
            ],
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
    def test_exact_backend_frontend_and_replacement_contracts(self) -> None:
        backend = (SOURCE / "comfy_extras" / "nodes_save_3d.py").read_text(encoding="utf-8")
        geometry = (SOURCE / "comfy_api" / "latest" / "_util" / "geometry_types.py").read_text(encoding="utf-8")
        folder_paths = (SOURCE / "folder_paths.py").read_text(encoding="utf-8")
        save_mesh = (FRONTEND / "src" / "extensions" / "core" / "saveMesh.ts").read_text(encoding="utf-8")
        load3d = (FRONTEND / "src" / "extensions" / "core" / "load3d.ts").read_text(encoding="utf-8")
        preview_ext = (FRONTEND / "src" / "extensions" / "core" / "load3dPreviewExtensions.ts").read_text(encoding="utf-8")
        point_adapter = (FRONTEND / "src" / "extensions" / "core" / "load3d" / "PointCloudModelAdapter.ts").read_text(encoding="utf-8")

        for marker in (
            "if isinstance(mesh, Types.File3D):",
            'ext = mesh.format or "glb"',
            "mesh.save_to(os.path.join(full_output_folder, f))",
            "for i in range(mesh.vertices.shape[0]):",
            "SaveGLB: skipping empty mesh at batch index",
            'metadata["prompt"] = json.dumps(cls.hidden.prompt)',
            'return IO.NodeOutput(ui={"3d": results})',
            "def _save_file3d_to_output",
            "camera_info_input if camera_info_input is not None else viewport_state.get('camera_info')",
            "model_3d_info_input if model_3d_info_input is not None else viewport_state.get('model_3d_info', [])",
            "class Save3DAdvanced",
            "class SaveGaussianSplat",
            "class SavePointCloud",
        ):
            self.assertIn(marker, backend)

        self.assertIn("Supports both disk-backed (file path) and memory-backed (BytesIO) storage", geometry)
        self.assertIn("shutil.copy2(self._source, dest)", geometry)
        self.assertIn("Saving image outside the output folder is not allowed", folder_paths)

        self.assertIn("nodeData.input.required.image = ['PREVIEW_3D']", save_mesh)
        self.assertIn("const fileInfo = (output as SaveMeshOutput)['3d']?.[0]", save_mesh)
        self.assertIn("if (load3d.isSplatModel()) return []", save_mesh)
        self.assertIn("persistThumbnail(filename, blob)", save_mesh)

        self.assertIn("createPreview3DAdvancedExtension(", load3d)
        self.assertIn("'Save3DAdvanced'", load3d)
        self.assertIn("sceneWidget.serializeValue = async () =>", load3d)
        self.assertIn("load3d.setTargetSize(", load3d)

        self.assertIn("'SaveGaussianSplat'", preview_ext)
        self.assertIn("'SavePointCloud'", preview_ext)
        self.assertIn("'output'", preview_ext)
        self.assertIn("const modelTransform = result[2]?.[0]", preview_ext)

        self.assertIn("const hasFaces = (plyGeometry.index?.count ?? 0) > 0", point_adapter)
        self.assertIn("geometry.computeBoundingSphere()", point_adapter)

        replacement_text = json.dumps(catalog.load_json(REPLACEMENTS), ensure_ascii=False)
        for spec in ARTICLE_SPECS.values():
            self.assertNotIn(spec["classType"], replacement_text)

    @unittest.skipUnless(DOCS_WHEEL.exists(), "pinned docs wheel absent")
    def test_pinned_embedded_docs_routes(self) -> None:
        self.assertEqual(DOCS_WHEEL_SHA256, hashlib.sha256(DOCS_WHEEL.read_bytes()).hexdigest())
        members = {
            "comfyui_embedded_docs/docs/SaveGLB/en.md": "mesh data or 3D files",
            "comfyui_embedded_docs/docs/Save3DAdvanced/en.md": "passes through the 3D model",
            "comfyui_embedded_docs/docs/SaveGaussianSplat/en.md": "A gaussian splat 3D file.",
            "comfyui_embedded_docs/docs/SavePointCloud/en.md": "Point cloud file (.ply)",
        }
        with zipfile.ZipFile(DOCS_WHEEL) as archive:
            for member, marker in members.items():
                self.assertIn(marker.lower(), archive.read(member).decode("utf-8").lower())
                self.assertIn(member.replace("/en.md", "/ru.md"), archive.namelist())

    @unittest.skipUnless(WORKFLOW_WHEEL.exists(), "workflow wheel absent")
    def test_exhaustive_workflow_census_and_official_save_glb_topology(self) -> None:
        self.assertEqual(WORKFLOW_WHEEL_SHA256, hashlib.sha256(WORKFLOW_WHEEL.read_bytes()).hexdigest())
        counts: Counter[str] = Counter()
        incoming_types: Counter[str] = Counter()
        member_names: set[str] = set()
        official_case: tuple[dict[str, Any], dict[str, Any], list[Any]] | None = None
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
                    nodes = [n for n in graph.get("nodes", []) if isinstance(n, dict)]
                    by_id = {str(n.get("id")): n for n in nodes}
                    for node in nodes:
                        if node.get("type") not in targets:
                            continue
                        counts[node["type"]] += 1
                        member_names.add(member)
                        incoming = [
                            link for link in graph.get("links", [])
                            if isinstance(link, list) and len(link) >= 6 and str(link[3]) == str(node.get("id"))
                        ]
                        for link in incoming:
                            incoming_types[str(link[5])] += 1
                            source = by_id.get(str(link[1]))
                            if (
                                node.get("type") == "SaveGLB"
                                and source
                                and source.get("type") == "SplatToFile3D"
                            ):
                                official_case = (node, source, link)

        self.assertEqual(512, file_count)
        self.assertEqual(496, root_count)
        self.assertEqual(768, graph_count)
        self.assertEqual(Counter({"SaveGLB": 39}), counts)
        self.assertEqual(
            Counter({"FILE_3D_GLB": 18, "MESH": 7, "FILE_3D_OBJ": 6, "FILE_3D_FBX": 5, "FILE_3D": 3}),
            incoming_types,
        )
        self.assertEqual(31, len(member_names))
        self.assertIsNotNone(official_case)
        save, source, link = official_case or ({}, {}, [])
        self.assertEqual(51, save["id"])
        self.assertEqual("3d/ComfyUI_TripoSplat", save["widgets_values"][0])
        self.assertEqual(92, source["id"])
        self.assertEqual(["spz"], source["widgets_values"])
        self.assertEqual("FILE_3D", link[5])

    @unittest.skipUnless(SOURCE.exists(), "pinned source absent")
    def test_safe_exact_source_save_probe(self) -> None:
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

        save_glb = payload["saveGLB"]
        self.assertEqual(1, save_glb["meshResultCount"])
        self.assertTrue(save_glb["emptyBatchItemSkipped"])
        self.assertEqual("probe_mesh_00001_.glb", save_glb["meshFilename"])
        self.assertTrue(save_glb["meshIsGLB"])
        self.assertTrue(save_glb["meshHasUV"])
        self.assertTrue(save_glb["meshHasColor"])
        self.assertTrue(save_glb["meshUsesUnlit"])
        self.assertEqual({"7": {"class_type": "Probe"}}, json.loads(save_glb["meshMetadata"]["prompt"]))
        self.assertEqual({"nodes": []}, json.loads(save_glb["meshMetadata"]["workflow"]))
        self.assertTrue(save_glb["fileBytesPreserved"])
        self.assertTrue(save_glb["fileExtensionPreserved"])
        self.assertEqual("probe_file_00001_.spz", save_glb["fileFilename"])
        self.assertTrue(save_glb["blankFormatFallsBackToGLBName"])
        self.assertTrue(save_glb["blankFormatBytesStillPreserved"])
        self.assertTrue(save_glb["invalidFaceRaises"])

        advanced = payload["advanced"]
        for class_name in ("Save3DAdvanced", "SaveGaussianSplat", "SavePointCloud"):
            item = advanced[class_name]
            self.assertTrue(item["saved"])
            self.assertTrue(item["bytesPreserved"])
            self.assertTrue(item["sameObjectPassedThrough"])
            self.assertTrue(item["uiMatchesOutputs"])
            self.assertEqual("PreviewUI3DAdvanced", item["uiKind"])
        self.assertEqual([800, 600], advanced["Save3DAdvanced"]["dimensions"])
        self.assertEqual({"source": "explicit"}, advanced["Save3DAdvanced"]["cameraInfo"])
        self.assertEqual([{"source": "explicit"}], advanced["Save3DAdvanced"]["modelInfo"])
        self.assertEqual({"source": "viewport"}, advanced["SaveGaussianSplat"]["cameraInfo"])
        self.assertEqual([{"source": "viewport"}], advanced["SaveGaussianSplat"]["modelInfo"])
        self.assertEqual([1, 4096], advanced["SavePointCloud"]["dimensions"])
        self.assertIsNone(advanced["SavePointCloud"]["cameraInfo"])
        self.assertEqual([], advanced["SavePointCloud"]["modelInfo"])


if __name__ == "__main__":
    unittest.main()
