from __future__ import annotations

import base64
import csv
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
    "core.load-3d": {
        "directory": "load-3d",
        "classType": "Load3D",
        "fingerprint": "sha256:d12c8a98b5c7b7e5054e4c7905032ac5c7f13e604b1b0ae7bf464ba6931a46d4",
        "outputNode": False,
        "recipe": "recipe.load-3d-render-passes",
    },
    "core.load-3d-advanced": {
        "directory": "load-3d-advanced",
        "classType": "Load3DAdvanced",
        "fingerprint": "sha256:f99a6a4f8ac0adfb5a94e3f333016f58e73eac54fc60e21cad45fd0641f9a492",
        "outputNode": False,
        "recipe": "recipe.load-3d-advanced-state",
    },
    "core.preview-3d": {
        "directory": "preview-3d",
        "classType": "Preview3D",
        "fingerprint": "sha256:0aa642e7ab751be5a8f4a764592433bf0e87c71b1ed00ccfa60ed31585acc190",
        "outputNode": True,
        "recipe": "recipe.preview-3d-string-result",
    },
    "core.preview-3d-advanced": {
        "directory": "preview-3d-advanced",
        "classType": "Preview3DAdvanced",
        "fingerprint": "sha256:83609406f3a8a1b6d13b5a1f4b0f814887c6eda5e84c35416063ac8b948870d8",
        "outputNode": True,
        "recipe": "recipe.preview-3d-advanced-pass-through",
    },
}

RECIPE_DIRECTORIES = {
    "recipe.load-3d-render-passes": "load-3d-render-passes",
    "recipe.load-3d-advanced-state": "load-3d-advanced-state",
    "recipe.preview-3d-string-result": "preview-3d-string-result",
    "recipe.preview-3d-advanced-pass-through": "preview-3d-advanced-pass-through",
}

INVENTORY = catalog.CONTENT / "runtime" / "comfyui-0.32.0.object-info.json"
REPLACEMENTS = catalog.CONTENT / "runtime" / "comfyui-0.32.0.node-replacements.json"
SOURCE = catalog.ROOT / ".comfyui-source-0.32.0"
FRONTEND = catalog.ROOT / ".frontend-source-1.48.7"
WORKFLOW_WHEEL = (
    catalog.ROOT
    / ".upstream-cache"
    / "comfyui_workflow_templates_json-0.1.42-py3-none-any.whl"
)
WORKFLOW_WHEEL_SHA256 = "242982d65e1c51ca03d892bc1009bb6843f457e7dfc0c20afe6438770b7a14a3"
DOCS_WHEEL = (
    catalog.ROOT
    / ".upstream-cache"
    / "comfyui_embedded_docs-0.5.9-py3-none-any.whl"
)
DOCS_WHEEL_SHA256 = "30afae432a71c96aa59421d0f37388c66ff6572b8cbeee8ff045e4d5f84f896c"
PROBE = Path(__file__).with_name("load3d_synthetic_probe.py")


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


def workflow_scopes(payload: dict[str, Any]) -> Iterator[tuple[str, dict[str, Any]]]:
    if isinstance(payload.get("nodes"), list):
        yield "root", payload
    definitions = payload.get("definitions")
    subgraphs = definitions.get("subgraphs", []) if isinstance(definitions, dict) else []
    for subgraph in subgraphs:
        if isinstance(subgraph, dict):
            yield "subgraph", subgraph


class Load3DContentTests(unittest.TestCase):
    def test_articles_recipes_research_and_natural_russian(self) -> None:
        article_ids = all_article_ids()
        article_schema = catalog.load_json(catalog.CONTENT / "schemas" / "article.schema.v1.json")
        recipe_schema = catalog.load_json(catalog.CONTENT / "schemas" / "recipe.schema.v1.json")
        fragment_schema = catalog.load_json(
            catalog.CONTENT / "schemas" / "recipe-fragment.schema.v1.json"
        )
        research_schema = catalog.load_json(
            catalog.CONTENT / "schemas" / "article-research.schema.v1.json"
        )
        errors: list[str] = []
        cliches = re.compile(
            r"важно отметить|стоит отметить|в современном мире|революционн|"
            r"является незаменим|данная нода|давайте разбер|подводя итог|"
            r"мощный инструмент|без воды|коротко о главном|понятно и доступно",
            re.IGNORECASE,
        )

        for article_id, spec in ARTICLE_SPECS.items():
            path = article_path(spec)
            article = catalog.load_json(path)
            self.assertEqual([], catalog.json_schema_errors(article, article_schema), article_id)
            catalog.validate_article(path, article, errors)
            self.assertEqual(article_id, article["articleId"])
            self.assertEqual("draft", article["status"])
            self.assertTrue(article["experimental"])
            self.assertEqual("in_review", article["editorial"]["state"])
            self.assertEqual(spec["recipe"], article["assets"][0]["id"])
            self.assertEqual([], article["runtimeIdentity"]["aliases"])

            relations = article["relations"]
            targets = relations["related"] + relations["alternatives"]
            if relations["replacedBy"] is not None:
                targets.append(relations["replacedBy"])
            self.assertTrue(set(targets).issubset(article_ids), article_id)

            body = (path.parent / article["body"]).read_text(encoding="utf-8")
            self.assertEqual(10, len(re.findall(r"^## .+$", body, flags=re.MULTILINE)), article_id)
            self.assertNotIn("\ufffd", body)
            self.assertNotRegex(body, cliches)
            self.assertIn("Редактор пока не проверил материал вручную.", body)

            record = catalog.load_json(
                catalog.CONTENT / "research" / "reviews" / f"{article_id}.json"
            )
            self.assertEqual([], catalog.json_schema_errors(record, research_schema), article_id)
            self.assertEqual("fact_checked", record["state"])
            self.assertEqual("automated_assisted", record["reviewMode"])
            self.assertFalse(record["checks"]["exampleExecuted"])
            self.assertTrue(record["checks"]["exampleSchemaValidated"])
            self.assertTrue(record["checks"]["russianEdited"])
            self.assertTrue(record["checks"]["factsRecheckedAfterEditing"])
            self.assertTrue(
                any("Редактор пока" in gap for gap in record["knownGaps"]),
                article_id,
            )

        self.assertEqual([], errors)

        for recipe_id in RECIPE_DIRECTORIES:
            path = recipe_path(recipe_id)
            recipe = catalog.load_json(path)
            self.assertEqual([], catalog.json_schema_errors(recipe, recipe_schema), recipe_id)
            catalog.validate_recipe(path, recipe, article_ids, errors)
            self.assertEqual("draft", recipe["editorial"]["state"])
            self.assertNotIn("workflow", recipe)
            fragment = catalog.load_json(path.parent / recipe["fragment"]["path"])
            self.assertEqual([], catalog.json_schema_errors(fragment, fragment_schema), recipe_id)
            compiled = catalog.compile_recipe(path, recipe)
            self.assertIn("fragmentData", compiled)
            self.assertNotIn("workflowData", compiled)
            body = (path.parent / recipe["body"]).read_text(encoding="utf-8")
            self.assertNotRegex(body, cliches)
            self.assertIn("Редактор пока не проверил материал вручную.", body)
        self.assertEqual([], errors)

    def test_runtime_fingerprints_flags_ports_and_fragment_types(self) -> None:
        nodes = catalog.object_info_nodes(catalog.load_json(INVENTORY))
        for spec in ARTICLE_SPECS.values():
            runtime = dict(nodes[spec["classType"]])
            article = catalog.load_json(article_path(spec))
            self.assertEqual("comfy_extras.nodes_load_3d", runtime["python_module"])
            self.assertEqual("3d", runtime["category"])
            self.assertTrue(runtime["experimental"])
            self.assertEqual(spec["outputNode"], runtime["output_node"])
            for flag in ("deprecated", "dev_only", "api_node", "is_input_list"):
                self.assertFalse(runtime[flag])
            self.assertEqual(
                spec["fingerprint"],
                catalog.schema_fingerprint(spec["classType"], runtime),
            )
            self.assertEqual(spec["fingerprint"], article["editorial"]["schemaHash"])

        load = nodes["Load3D"]
        self.assertEqual(["model_file", "image", "width", "height"], load["input_order"]["required"])
        self.assertEqual(
            ["IMAGE", "MASK", "STRING", "IMAGE", "LOAD3D_CAMERA", "VIDEO", "FILE_3D", "LOAD3D_MODEL_INFO"],
            load["output"],
        )
        self.assertEqual(
            ["image", "mask", "mesh_path", "normal", "camera_info", "recording_video", "model_3d", "model_3d_info"],
            load["output_name"],
        )
        self.assertEqual((1024, 1, 4096, 1), tuple(load["input"]["required"]["width"][1][key] for key in ("default", "min", "max", "step")))

        load_advanced = nodes["Load3DAdvanced"]
        self.assertEqual(
            ["model_file", "viewport_state", "width", "height"],
            load_advanced["input_order"]["required"],
        )
        self.assertEqual(
            ["FILE_3D", "LOAD3D_MODEL_INFO", "LOAD3D_CAMERA", "INT", "INT"],
            load_advanced["output"],
        )

        preview = nodes["Preview3D"]
        self.assertEqual([], preview["output"])
        self.assertEqual(["model_file"], preview["input_order"]["required"])
        self.assertEqual(["camera_info", "bg_image"], preview["input_order"]["optional"])
        self.assertEqual(
            "STRING,FILE_3D_GLB,FILE_3D_GLTF,FILE_3D_FBX,FILE_3D_OBJ,FILE_3D_STL,FILE_3D_USDZ,FILE_3D",
            preview["input"]["required"]["model_file"][0],
        )

        preview_advanced = nodes["Preview3DAdvanced"]
        self.assertEqual(
            ["model_3d", "viewport_state", "width", "height"],
            preview_advanced["input_order"]["required"],
        )
        self.assertEqual(["model_3d_info", "camera_info"], preview_advanced["input_order"]["optional"])
        self.assertEqual(load_advanced["output"], preview_advanced["output"])

        fragment = catalog.load_json(
            catalog.CONTENT / "recipes" / "load-3d-render-passes" / "fragment.json"
        )
        self.assertEqual(
            ["Load3D", "PreviewImage", "MaskToImage", "PreviewImage", "PreviewImage"],
            [node["classType"] for node in fragment["nodes"]],
        )
        self.assertIn(
            {"from": "load3d", "output": "mask", "to": "mask-to-image", "input": "mask"},
            fragment["connections"],
        )
        self.assertIn(
            {"from": "mask-to-image", "output": "IMAGE", "to": "mask", "input": "images"},
            fragment["connections"],
        )

        string_fragment = catalog.load_json(
            catalog.CONTENT / "recipes" / "preview-3d-string-result" / "fragment.json"
        )
        self.assertEqual("STRING", string_fragment["externalInputs"][0]["type"])
        advanced_fragment = catalog.load_json(
            catalog.CONTENT / "recipes" / "preview-3d-advanced-pass-through" / "fragment.json"
        )
        self.assertEqual("FILE_3D", advanced_fragment["externalInputs"][0]["type"])

        for directory in RECIPE_DIRECTORIES.values():
            fragment = catalog.load_json(
                catalog.CONTENT / "recipes" / directory / "fragment.json"
            )
            refs = {node["ref"]: node for node in fragment["nodes"]}
            for node in fragment["nodes"]:
                runtime_inputs = nodes[node["classType"]].get("input", {})
                valid_settings = {
                    name
                    for group in ("required", "optional")
                    for name in runtime_inputs.get(group, {})
                }
                self.assertTrue(set(node["settings"]).issubset(valid_settings), node)
            for external in fragment["externalInputs"]:
                target = refs[external["to"]]
                definition = nodes[target["classType"]]
                inputs = {
                    **definition.get("input", {}).get("required", {}),
                    **definition.get("input", {}).get("optional", {}),
                }
                self.assertIn(external["input"], inputs)
                self.assertIn(external["type"], inputs[external["input"]][0].split(","))
            for edge in fragment["connections"]:
                source = refs[edge["from"]]
                target = refs[edge["to"]]
                source_definition = nodes[source["classType"]]
                target_definition = nodes[target["classType"]]
                output_index = source_definition["output_name"].index(edge["output"])
                output_type = source_definition["output"][output_index]
                target_inputs = {
                    **target_definition.get("input", {}).get("required", {}),
                    **target_definition.get("input", {}).get("optional", {}),
                }
                self.assertIn(edge["input"], target_inputs)
                self.assertIn(output_type, target_inputs[edge["input"]][0].split(","), edge)

    @unittest.skipUnless(SOURCE.exists() and FRONTEND.exists(), "pinned source checkouts are absent")
    def test_pinned_backend_frontend_contracts_and_replacements(self) -> None:
        expected_hashes = {
            SOURCE / "comfy_extras" / "nodes_load_3d.py": "ebffbd0d70c6b7beb9ad3ece705e75b3f0bd19102f4d2ab0d8adcdfedfca6b17",
            SOURCE / "comfy_api" / "latest" / "_ui.py": "ef5fb612305207d1673eda16172a82407e6657b958f85ad14d0d0272b0745d38",
            SOURCE / "comfy_api" / "latest" / "_util" / "geometry_types.py": "eac581734bdec2d99f95f5752ce0d65e1160ee18e86bee2b62a4182945999122",
            FRONTEND / "src" / "extensions" / "core" / "load3d.ts": "755e98ed816a467c1b5853c3c9253b9b960045f7d6b5f2ddd761eeaf7853ce10",
            FRONTEND / "src" / "extensions" / "core" / "load3dAdvanced.ts": "e2ac0816f23b4455d8301b469f4ff74c50840698d1cd073d3b0155cca95fafbb",
            FRONTEND / "src" / "extensions" / "core" / "load3dLazy.ts": "c60bd9d2bec59463df202d4b93842d0a9419799f684e3a5fa7ae70dab1abdb41",
            FRONTEND / "src" / "extensions" / "core" / "load3d" / "nodeTypes.ts": "93e316faed5e872e0348f2fd900925983d325ce9922e408d727c63affd0feff2",
            FRONTEND / "src" / "extensions" / "core" / "load3d" / "RecordingManager.ts": "ff2ce3a6d91bc467d965a3173f857595a750007a7d49faa189f93e8e5c012308",
        }
        for path, expected in expected_hashes.items():
            self.assertEqual(expected, hashlib.sha256(path.read_bytes()).hexdigest(), path)

        backend = (SOURCE / "comfy_extras" / "nodes_load_3d.py").read_text(encoding="utf-8")
        for marker in (
            "if image['recording'] != \"\"",
            "InputImpl.VideoFromFile(recording_video_path)",
            "IO.NodeOutput(output_image, output_mask, mesh_path, normal_image, image['camera_info'], video, file_3d, model_3d_info)",
            'filename = f"preview3d_{uuid.uuid4().hex}.{model_file.format}"',
            "model_file.save_to(os.path.join(folder_paths.get_output_directory(), filename))",
            'filename = f"preview3d_advanced_{uuid.uuid4().hex}.{model_3d.format}"',
            "model_3d.save_to(os.path.join(folder_paths.get_temp_directory(), filename))",
            "camera_info_input if camera_info_input is not None else viewport_state.get('camera_info')",
            "model_3d_info_input if model_3d_info_input is not None else viewport_state.get('model_3d_info', [])",
            "MESH_EXTENSIONS = {'.gltf', '.glb', '.obj', '.fbx', '.stl'}",
        ):
            self.assertIn(marker, backend)

        frontend = (FRONTEND / "src" / "extensions" / "core" / "load3d.ts").read_text(encoding="utf-8")
        advanced = (FRONTEND / "src" / "extensions" / "core" / "load3dAdvanced.ts").read_text(encoding="utf-8")
        lazy = (FRONTEND / "src" / "extensions" / "core" / "load3dLazy.ts").read_text(encoding="utf-8")
        node_types = (FRONTEND / "src" / "extensions" / "core" / "load3d" / "nodeTypes.ts").read_text(encoding="utf-8")
        utils = (FRONTEND / "src" / "extensions" / "core" / "load3d" / "Load3dUtils.ts").read_text(encoding="utf-8")
        recording = (FRONTEND / "src" / "extensions" / "core" / "load3d" / "RecordingManager.ts").read_text(encoding="utf-8")
        self.assertIn("await currentLoad3d.captureScene(", frontend)
        self.assertIn("image: `threed/${data.name} [temp]`", frontend)
        self.assertIn("node.properties['Last Time Model File']", frontend)
        self.assertIn("capture its generation", frontend)
        self.assertIn("createPreview3DAdvancedExtension(", frontend)
        self.assertIn("'temp'", frontend)
        self.assertIn("nodeData.input.required.viewport_state = ['LOAD_3D_ADVANCED', {}]", advanced)
        self.assertIn("registerExtension", lazy)
        self.assertIn("Load3DAdvanced", node_types)
        self.assertNotIn("Preview3DAdvanced", node_types)
        self.assertIn("static readonly MAX_UPLOAD_SIZE_MB = 100", utils)
        self.assertIn("mimeType: 'video/webm;codecs=vp9'", recording)
        self.assertIn("new Blob(this.recordedChunks, { type: 'video/webm' })", recording)
        self.assertIn("filename: string = 'scene-recording.mp4'", recording)

        replacements = catalog.load_json(REPLACEMENTS)
        self.assertEqual("Load3D", replacements["Load3DAnimation"][0]["new_node_id"])
        self.assertEqual("Preview3D", replacements["Preview3DAnimation"][0]["new_node_id"])
        self.assertNotIn("Load3DAdvanced", replacements)
        self.assertNotIn("Preview3DAdvanced", replacements)

    @unittest.skipUnless(DOCS_WHEEL.exists(), "pinned embedded docs wheel is absent")
    def test_pinned_embedded_docs_hashes_and_known_gaps(self) -> None:
        self.assertEqual(DOCS_WHEEL_SHA256, hashlib.sha256(DOCS_WHEEL.read_bytes()).hexdigest())
        expected = {
            "Load3D": {
                "en": "8118cc26d576a18496a883269e6b94f758a5d39846f0fab4e1df69536aaba011",
                "ru": "9fc909cb78659f4995d123c5e609b1ccad41544e8d5d64a1209e4d93fc58f9c1",
            },
            "Load3DAdvanced": {
                "en": "6e1efc825f9183c42d397f3b37134772eef980fecce80af73411a78a171eaa8b",
                "ru": "84107c6a427a2b01fd9ed5c8641463fac6913810156effd33518d0ac8abc67d0",
            },
            "Preview3D": {
                "en": "db81f27c0464074303119db9c8553f3d15f86507c55a1f64ef136d84048b85f7",
                "ru": "bd1524edc4b8590f1ff707aea4b1c1e96b961aed78822d8dcad855059ed45313",
            },
            "Preview3DAdvanced": {
                "en": "d19b7655b7552960fdcf9cbd4f951353897449fdbbbf7c11167b8b54c8a77ba6",
                "ru": "28d1e796742bf6bbbd6b6d03379e966cc3b474441f69605c871c375d232d80fc",
            },
        }
        with zipfile.ZipFile(DOCS_WHEEL) as archive:
            for class_type, locales in expected.items():
                for locale, digest in locales.items():
                    member = f"comfyui_embedded_docs/docs/{class_type}/{locale}.md"
                    self.assertEqual(digest, hashlib.sha256(archive.read(member)).hexdigest())
            load_docs = archive.read("comfyui_embedded_docs/docs/Load3D/en.md").decode("utf-8")
            preview_docs = archive.read("comfyui_embedded_docs/docs/Preview3D/en.md").decode("utf-8")
            self.assertIn("lineart", load_docs.lower())
            self.assertNotIn("model_3d_info", load_docs)
            self.assertIn("LOAD3D_CAMERA", preview_docs)

    @unittest.skipUnless(WORKFLOW_WHEEL.exists(), "pinned workflow wheel is absent")
    def test_workflow_wheel_integrity_full_census_and_topology(self) -> None:
        self.assertEqual(
            WORKFLOW_WHEEL_SHA256,
            hashlib.sha256(WORKFLOW_WHEEL.read_bytes()).hexdigest(),
        )
        targets = {spec["classType"] for spec in ARTICLE_SPECS.values()}
        counts: Counter[str] = Counter()
        scopes: Counter[tuple[str, str]] = Counter()
        modes: dict[str, Counter[int]] = defaultdict(Counter)
        files: dict[str, set[str]] = defaultdict(set)
        workflow_ids: dict[str, set[str]] = defaultdict(set)
        widget_lengths: dict[str, Counter[int]] = defaultdict(Counter)
        preview_incoming_types: Counter[str] = Counter()
        load_outgoing: list[list[Any]] = []
        json_count = root_count = subgraph_count = node_count = 0

        with zipfile.ZipFile(WORKFLOW_WHEEL) as archive:
            self.assertIsNone(archive.testzip())
            record_name = next(name for name in archive.namelist() if name.endswith(".dist-info/RECORD"))
            verified = unhashed = 0
            for name, digest_spec, size in csv.reader(
                archive.read(record_name).decode("utf-8").splitlines()
            ):
                if not digest_spec:
                    unhashed += 1
                    continue
                algorithm, expected = digest_spec.split("=", 1)
                payload = archive.read(name)
                actual = base64.urlsafe_b64encode(hashlib.new(algorithm, payload).digest()).decode("ascii").rstrip("=")
                self.assertEqual(expected, actual)
                self.assertEqual(int(size), len(payload))
                verified += 1
            self.assertEqual((516, 1), (verified, unhashed))

            for member in sorted(archive.namelist()):
                if not member.endswith(".json"):
                    continue
                json_count += 1
                payload = json.loads(archive.read(member).decode("utf-8"))
                if not isinstance(payload, dict):
                    continue
                if isinstance(payload.get("nodes"), list):
                    root_count += 1
                for scope, graph in workflow_scopes(payload):
                    if scope == "subgraph":
                        subgraph_count += 1
                    nodes = [node for node in graph.get("nodes", []) if isinstance(node, dict)]
                    node_count += len(nodes)
                    by_id = {str(node.get("id")): node for node in nodes}
                    links = [link for link in graph.get("links", []) if isinstance(link, list)]
                    for node in nodes:
                        class_type = node.get("type")
                        if class_type not in targets:
                            continue
                        counts[class_type] += 1
                        scopes[(class_type, scope)] += 1
                        modes[class_type][node.get("mode", 0)] += 1
                        files[class_type].add(member)
                        workflow_ids[class_type].add(str(payload.get("id")))
                        widgets = node.get("widgets_values")
                        widget_lengths[class_type][len(widgets) if isinstance(widgets, list) else -1] += 1
                        node_id = node.get("id")
                        if class_type == "Preview3D":
                            incoming = [link for link in links if link[3] == node_id]
                            for link in incoming:
                                preview_incoming_types[str(link[5])] += 1
                            self.assertEqual([], node.get("outputs", []))
                        elif class_type == "Load3D":
                            outgoing = [link for link in links if link[1] == node_id]
                            load_outgoing.extend(outgoing)
                            for link in outgoing:
                                self.assertIn(str(link[3]), by_id)

        self.assertEqual((512, 496, 272, 8120), (json_count, root_count, subgraph_count, node_count))
        self.assertEqual(Counter({"Preview3D": 24, "Load3D": 4}), counts)
        self.assertEqual(4, scopes[("Load3D", "root")])
        self.assertEqual(24, scopes[("Preview3D", "root")])
        self.assertFalse(any(scope == "subgraph" for _, scope in scopes))
        self.assertEqual((4, 17), (len(files["Load3D"]), len(files["Preview3D"])))
        self.assertEqual((4, 9), (len(workflow_ids["Load3D"]), len(workflow_ids["Preview3D"])))
        self.assertEqual(Counter({0: 4}), modes["Load3D"])
        self.assertEqual(Counter({0: 18, 4: 6}), modes["Preview3D"])
        self.assertEqual(Counter({7: 4}), widget_lengths["Load3D"])
        self.assertEqual(Counter({2: 24}), widget_lengths["Preview3D"])
        self.assertEqual(Counter({"STRING": 23}), preview_incoming_types)
        self.assertEqual(4, len(load_outgoing))
        self.assertTrue(all(link[2] == 6 and link[5] == "FILE_3D" for link in load_outgoing))

    @unittest.skipUnless(SOURCE.exists(), "pinned source checkout is absent")
    def test_safe_exact_source_temp_file_probe(self) -> None:
        result = subprocess.run(
            [sys.executable, "-X", "utf8", str(PROBE)],
            cwd=catalog.ROOT,
            text=True,
            capture_output=True,
            timeout=60,
            check=False,
            env={**os.environ, "PYTHONUTF8": "1"},
        )
        self.assertEqual(0, result.returncode, result.stderr or result.stdout)
        payload = json.loads(result.stdout.strip().splitlines()[-1])

        load = payload["load3d"]
        self.assertTrue(load["fileBytesPreserved"])
        self.assertEqual([True, ""], load["noneFileAndPath"])
        self.assertTrue(load["validAccepted"])
        self.assertTrue(load["noneAccepted"])
        self.assertIn("Invalid 3D model file", load["missingRejected"])
        self.assertEqual("image:scene.png", load["values"][0])
        self.assertEqual("mask:mask.png", load["values"][1])
        self.assertEqual("image:normal.png", load["values"][3])
        self.assertEqual("glb", load["values"][6])

        advanced = payload["load3dAdvanced"]
        self.assertTrue(advanced["fileBytesPreserved"])
        self.assertEqual([True, [], None, 1, 4096], advanced["noneAndInvalidViewport"])
        self.assertEqual([800, 600], advanced["values"][2:])

        preview = payload["preview3d"]
        self.assertTrue(preview["outputExists"])
        self.assertTrue(preview["outputBytesPreserved"])
        self.assertTrue(preview["stringBranchCreatesNoFile"])
        self.assertEqual("service/result.glb", preview["stringResult"][0])

        preview_advanced = payload["preview3dAdvanced"]
        self.assertTrue(preview_advanced["tempExists"])
        self.assertTrue(preview_advanced["tempBytesPreserved"])
        self.assertEqual([{"source": "explicit"}, []], preview_advanced["explicitCameraAndEmptyModelInfo"])
        self.assertEqual([[], None], preview_advanced["invalidViewportDefaults"])
        self.assertEqual([True, [], {"source": "explicit"}, 1280, 720], preview_advanced["passThrough"])


if __name__ == "__main__":
    unittest.main()
