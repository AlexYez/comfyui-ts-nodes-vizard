from __future__ import annotations

import ast
import hashlib
import json
import re
import unittest
import zipfile
from collections import Counter
from pathlib import Path
from typing import Any, Iterator

from tools import catalog
from tools.tests.mediapipe_face_synthetic_probe import run_probe


SOURCE = catalog.ROOT / ".comfyui-source-0.32.0"
FRONTEND_SOURCE = catalog.ROOT / ".frontend-source-1.48.7"
INVENTORY = catalog.CONTENT / "runtime" / "comfyui-0.32.0.object-info.json"
REPLACEMENTS = catalog.CONTENT / "runtime" / "comfyui-0.32.0.node-replacements.json"
WORKFLOW_WHEEL = (
    catalog.ROOT
    / ".upstream-cache"
    / "comfyui_workflow_templates_json-0.1.42-py3-none-any.whl"
)
WORKFLOW_SHA256 = "242982d65e1c51ca03d892bc1009bb6843f457e7dfc0c20afe6438770b7a14a3"
DOCS_WHEEL = (
    catalog.ROOT / ".upstream-cache" / "comfyui_embedded_docs-0.5.9-py3-none-any.whl"
)
DOCS_SHA256 = "30afae432a71c96aa59421d0f37388c66ff6572b8cbeee8ff045e4d5f84f896c"

ARTICLE_SPECS = {
    "core.load-mediapipe-face-landmarker": {
        "directory": "load-mediapipe-face-landmarker",
        "classType": "LoadMediaPipeFaceLandmarker",
        "fingerprint": "sha256:e9ed899b1ca1ed271949c456eb55ed900f1d4ebc20d3a7571c0a0b4eec8ffe7b",
        "displayName": "Load Face Detection Model (MediaPipe)",
        "category": "model/loaders",
        "assets": {
            "recipe.mediapipe-face-mask",
            "recipe.mediapipe-face-mesh-overlay",
        },
        "related": {
            "core.mediapipe-face-landmarker",
            "core.load-image",
        },
    },
    "core.mediapipe-face-landmarker": {
        "directory": "mediapipe-face-landmarker",
        "classType": "MediaPipeFaceLandmarker",
        "fingerprint": "sha256:3bcfa604e2efa139f9bd533be03c588536ca365a64a467adfd3a1147c735bd03",
        "displayName": "Detect Face Landmarks (MediaPipe)",
        "category": "image/detection",
        "assets": {
            "recipe.mediapipe-face-mask",
            "recipe.mediapipe-face-mesh-overlay",
        },
        "related": {
            "core.load-mediapipe-face-landmarker",
            "core.mediapipe-face-mesh-visualize",
            "core.mediapipe-face-mask",
            "core.primitive-bounding-box",
        },
    },
    "core.mediapipe-face-mesh-visualize": {
        "directory": "mediapipe-face-mesh-visualize",
        "classType": "MediaPipeFaceMeshVisualize",
        "fingerprint": "sha256:7dc943ffe89e82631f7b8c6ac0d18db08d37f21ce97e0b72ea663a3a5fdebfcc",
        "displayName": "Visualize Face Landmarks (MediaPipe)",
        "category": "image/detection",
        "assets": {"recipe.mediapipe-face-mesh-overlay"},
        "related": {
            "core.mediapipe-face-landmarker",
            "core.mediapipe-face-mask",
            "core.preview-image",
        },
    },
    "core.mediapipe-face-mask": {
        "directory": "mediapipe-face-mask",
        "classType": "MediaPipeFaceMask",
        "fingerprint": "sha256:c3f5e5aaaaeb54283aed1aaac89e5839e393158e3629882458e41fbe11f8f38f",
        "displayName": "Draw Face Mask (MediaPipe)",
        "category": "image/detection",
        "assets": {"recipe.mediapipe-face-mask"},
        "related": {
            "core.mediapipe-face-landmarker",
            "core.mediapipe-face-mesh-visualize",
            "core.mask-preview",
        },
    },
}
TARGET_TYPES = {spec["classType"] for spec in ARTICLE_SPECS.values()}
DISPLAY_NAMES = {spec["displayName"] for spec in ARTICLE_SPECS.values()}

RECIPE_SPECS = {
    "recipe.mediapipe-face-mask": {
        "directory": "mediapipe-face-mask",
        "articles": {
            "core.load-mediapipe-face-landmarker",
            "core.mediapipe-face-landmarker",
            "core.mediapipe-face-mask",
        },
        "nodes": {
            "LoadMediaPipeFaceLandmarker": {
                "model_name": "mediapipe_face_fp32.safetensors"
            },
            "MediaPipeFaceLandmarker": {
                "detector_variant": "full",
                "num_faces": 0,
                "min_confidence": 0.5,
                "missing_frame_fallback": "empty",
            },
            "MediaPipeFaceMask": {
                "regions": {
                    "regions": "custom",
                    "face_oval": True,
                    "lips": False,
                    "left_eye": False,
                    "right_eye": False,
                    "irises": False,
                }
            },
        },
        "sink": "MediaPipeFaceMask",
        "sinkInput": "face_landmarks",
        "fragmentId": "fragment.mediapipe-face-mask",
    },
    "recipe.mediapipe-face-mesh-overlay": {
        "directory": "mediapipe-face-mesh-overlay",
        "articles": {
            "core.load-mediapipe-face-landmarker",
            "core.mediapipe-face-landmarker",
            "core.mediapipe-face-mesh-visualize",
        },
        "nodes": {
            "LoadMediaPipeFaceLandmarker": {
                "model_name": "mediapipe_face_fp32.safetensors"
            },
            "MediaPipeFaceLandmarker": {
                "detector_variant": "short",
                "num_faces": 1,
                "min_confidence": 0.5,
                "missing_frame_fallback": "empty",
            },
            "MediaPipeFaceMeshVisualize": {
                "connections": {"connections": "all"},
                "color": "#00ff00",
                "thickness": 1,
                "point_size": 2,
            },
        },
        "sink": "MediaPipeFaceMeshVisualize",
        "sinkInput": "face_landmarks",
        "fragmentId": "fragment.mediapipe-face-mesh-overlay",
    },
}

EXPECTED_H2 = [
    "Что делает нода",
    "Место в графе",
    "Входы",
    "Выходы",
    "Как работает внутри",
    "Настройки",
    "Пример подключения",
    "Частые ошибки",
    "Ограничения и производительность",
    "Совместимость и источники",
]

DOC_PAGE_HASHES = {
    "comfyui_embedded_docs/docs/LoadMediaPipeFaceLandmarker/en.md": "485c299a01489caf53e1cba73c9826fa319c62e456fcda7e3135ebb225f822d3",
    "comfyui_embedded_docs/docs/LoadMediaPipeFaceLandmarker/ru.md": "9840653a02744243a2c20f544f834c5b9c7cc05ae5566cb6f3efbc4ef09fefe6",
    "comfyui_embedded_docs/docs/MediaPipeFaceLandmarker/en.md": "f313a4bd86e8adebb56ab1471e93c9ed524c353fe33e57f55c7d640ce8ec9442",
    "comfyui_embedded_docs/docs/MediaPipeFaceLandmarker/ru.md": "8e8f1a8a1dcf5f65d5404b683797ea24c9c85aa74f009fea3244126b55ce205e",
    "comfyui_embedded_docs/docs/MediaPipeFaceMeshVisualize/en.md": "8b0efa38d879d570abfe579fa9e3cddeb73e671bd5c645bea64a1d51ec043be4",
    "comfyui_embedded_docs/docs/MediaPipeFaceMeshVisualize/ru.md": "9c55eadc780f28cebbd2b08394cb43f8ba5c73b9e69823b4f9b310e03ab80d11",
    "comfyui_embedded_docs/docs/MediaPipeFaceMask/en.md": "9e2a182285338bfba5340814bfcb94aaf7142ab032ef6cd936f68a23741a28b9",
    "comfyui_embedded_docs/docs/MediaPipeFaceMask/ru.md": "af6cff6a5d2775d5c3c83965a28ea4ef049789ee8831c34109f5d10b7861a0d1",
}

SOURCE_HASHES = {
    "comfy_extras/nodes_mediapipe.py": "1e32e31716a5c083d201c0dfed053f62e39d5933895fc002fd89ad01cef6a716",
    "comfy_extras/mediapipe/face_landmarker.py": "691842a8028cc8b2836335eaccc3c823376f93b79a7944ae588fb2ef1437d32d",
    "comfy_extras/mediapipe/face_geometry.py": "3a6cd2cca64207f060cc1f044fc9b45db9c76c9fc2caa4bd3ddf5c0cb3b27c69",
    "folder_paths.py": "a8dae8d0b09c2caafbb7cc2f627d81bd9c299ff1de9c8698e2e32760dde1dc66",
    "comfy/utils.py": "339031b402739116941030f8c570a61a35a3e6e072e67eee96c084e125107803",
    "blueprints/Image Face Detection (Mediapipe).json": "49b84dbeac30207a4250d88fc483ff874f01844fce0876f0e48060a018323de7",
    "blueprints/Video Face Detection (Mediapipe).json": "8dc7a8556541b2b280e159fe1f7e52eb57d89c94dfb8d0fdd9c3393ec67cc8c3",
}

BASELINE = {
    "comfyui": "0.32.0",
    "frontend": "1.48.7",
    "sourceCommit": "c2bcbecd82ec5ae66594340b395c24ef0217b238",
    "embeddedDocs": "0.5.9",
    "workflowTemplatesJson": "0.1.42",
}


def _walk_strings(value: Any) -> Iterator[str]:
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for key, nested in value.items():
            yield from _walk_strings(key)
            yield from _walk_strings(nested)
    elif isinstance(value, list):
        for nested in value:
            yield from _walk_strings(nested)


def _pending_human_review(value: Any) -> bool:
    text = json.dumps(value, ensure_ascii=False).lower()
    return (
        ("human" in text and "pending" in text)
        or "редактор пока не проверил" in text
        or ("человек" in text and any(word in text for word in ("ожида", "не выполн")))
    )


def _article_path(spec: dict[str, Any]) -> Path:
    return catalog.CONTENT / "articles" / "core" / spec["directory"] / "manifest.json"


def _recipe_path(spec: dict[str, Any]) -> Path:
    return catalog.CONTENT / "recipes" / spec["directory"] / "recipe.json"


def _manifest_counter(field: str, root: Path, filename: str) -> Counter[str]:
    result: Counter[str] = Counter()
    for path in root.rglob(filename):
        payload = catalog.load_json(path)
        if isinstance(payload, dict) and isinstance(payload.get(field), str):
            result[payload[field]] += 1
    return result


def _runtime_inputs(runtime: dict[str, Any]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for group in ("required", "optional"):
        values = runtime.get("input", {}).get(group, {})
        if isinstance(values, dict):
            result.update(values)
    return result


def _subgraphs(payload: dict[str, Any]) -> list[dict[str, Any]]:
    definitions = payload.get("definitions")
    values = definitions.get("subgraphs", []) if isinstance(definitions, dict) else []
    if isinstance(values, dict):
        values = list(values.values())
    return [item for item in values if isinstance(item, dict)]


def _normalized_links(graph: dict[str, Any]) -> set[tuple[Any, ...]]:
    result: set[tuple[Any, ...]] = set()
    for link in graph.get("links", []):
        if isinstance(link, list) and len(link) >= 6:
            result.add(tuple(link[:6]))
        elif isinstance(link, dict):
            result.add(
                tuple(
                    link.get(key)
                    for key in (
                        "id",
                        "origin_id",
                        "origin_slot",
                        "target_id",
                        "target_slot",
                        "type",
                    )
                )
            )
    return result


def _node_by_type(graph: dict[str, Any], class_type: str) -> dict[str, Any]:
    matches = [
        node
        for node in graph.get("nodes", [])
        if isinstance(node, dict) and node.get("type") == class_type
    ]
    if len(matches) != 1:
        raise AssertionError(f"expected one {class_type}, got {len(matches)}")
    return matches[0]


class MediaPipeFaceContentTests(unittest.TestCase):
    def test_articles_recipes_ledgers_and_exact_fragment_contract(self) -> None:
        article_schema = catalog.load_json(
            catalog.CONTENT / "schemas" / "article.schema.v1.json"
        )
        recipe_schema = catalog.load_json(
            catalog.CONTENT / "schemas" / "recipe.schema.v1.json"
        )
        fragment_schema = catalog.load_json(
            catalog.CONTENT / "schemas" / "recipe-fragment.schema.v1.json"
        )
        research_schema = catalog.load_json(
            catalog.CONTENT / "schemas" / "article-research.schema.v1.json"
        )
        article_counts = _manifest_counter(
            "articleId", catalog.CONTENT / "articles", "manifest.json"
        )
        recipe_counts = _manifest_counter(
            "recipeId", catalog.CONTENT / "recipes", "recipe.json"
        )
        all_article_ids = set(article_counts)
        all_recipe_ids = set(recipe_counts)
        runtime = catalog.object_info_nodes(catalog.load_json(INVENTORY))
        article_errors: list[str] = []
        recipe_errors: list[str] = []

        for article_id, spec in ARTICLE_SPECS.items():
            self.assertEqual(1, article_counts[article_id], article_id)
            path = _article_path(spec)
            article = catalog.load_json(path)
            self.assertEqual([], catalog.json_schema_errors(article, article_schema), article_id)
            catalog.validate_article(path, article, article_errors)
            self.assertEqual(article_id, article["articleId"])
            self.assertEqual("draft", article["status"])
            self.assertEqual("in_review", article["editorial"]["state"])
            self.assertFalse(article["experimental"])
            self.assertEqual(spec["fingerprint"], article["editorial"]["schemaHash"])
            self.assertEqual(
                {
                    "classType": spec["classType"],
                    "pythonModule": "comfy_extras.nodes_mediapipe",
                    "packageId": "comfy-core",
                    "origin": "backend",
                    "aliases": [],
                },
                article["runtimeIdentity"],
            )
            self.assertTrue(_pending_human_review(article["editorial"]["reviewedBy"]))
            asset_ids = {item["id"] for item in article["assets"]}
            self.assertTrue(spec["assets"].issubset(asset_ids), (article_id, asset_ids))
            self.assertTrue(asset_ids.issubset(all_recipe_ids))

            relation_targets = set(
                article["relations"]["related"] + article["relations"]["alternatives"]
            )
            if article["relations"]["replacedBy"] is not None:
                relation_targets.add(article["relations"]["replacedBy"])
            self.assertTrue(relation_targets.issubset(all_article_ids))
            self.assertEqual(spec["related"], set(article["relations"]["related"]))
            self.assertEqual([], article["relations"]["alternatives"])
            self.assertIsNone(article["relations"]["replacedBy"])

            body = (path.parent / article["body"]).read_text(encoding="utf-8")
            self.assertEqual(
                EXPECTED_H2,
                re.findall(r"^## (.+)$", body, flags=re.MULTILINE),
                article_id,
            )
            self.assertIn("Редактор пока не проверил материал вручную.", body)
            self.assertIn(spec["classType"], body)
            self.assertNotIn("\ufffd", body)

            ledger_path = catalog.CONTENT / "research" / "reviews" / f"{article_id}.json"
            ledger = catalog.load_json(ledger_path)
            self.assertEqual([], catalog.json_schema_errors(ledger, research_schema), article_id)
            self.assertEqual(article_id, ledger["articleId"])
            self.assertEqual(spec["classType"], ledger["node"]["classType"])
            self.assertEqual("comfy_extras.nodes_mediapipe", ledger["node"]["pythonModule"])
            self.assertEqual("backend", ledger["node"]["origin"])
            self.assertEqual(BASELINE, ledger["baseline"])
            self.assertEqual("fact_checked", ledger["state"])
            self.assertEqual("automated_assisted", ledger["reviewMode"])
            for check in (
                "implementationRead",
                "runtimeCompared",
                "officialCasesInspected",
                "exampleSchemaValidated",
                "russianEdited",
                "factsRecheckedAfterEditing",
            ):
                self.assertTrue(ledger["checks"][check], (article_id, check))
            self.assertFalse(ledger["checks"]["exampleExecuted"])
            self.assertTrue(_pending_human_review(ledger["knownGaps"]))
            self.assertGreaterEqual(
                {item["locale"] for item in ledger["evidence"]["embeddedDocs"]},
                {"en", "ru"},
            )
            self.assertTrue(ledger["evidence"]["sourceLocations"])
            workflow_text = json.dumps(
                ledger["evidence"]["workflows"], ensure_ascii=False
            )
            for marker in ("512", "496", "272"):
                self.assertIn(marker, workflow_text, (article_id, marker))
            self.assertRegex(
                workflow_text,
                r"(?i)(?:zero|нул\w*|0)\s+(?:direct|прям\w*)[^.]*"
                r"(?:raw|сыр\w*)[^.]*"
                r"(?:recursive\s+scalar|скаляр\w*)\s+(?:occurrences|вхожд\w*)",
                (article_id, "zero direct/raw/recursive-scalar occurrences"),
            )

        for recipe_id, spec in RECIPE_SPECS.items():
            self.assertEqual(1, recipe_counts[recipe_id], recipe_id)
            path = _recipe_path(spec)
            recipe = catalog.load_json(path)
            self.assertEqual([], catalog.json_schema_errors(recipe, recipe_schema), recipe_id)
            catalog.validate_recipe(path, recipe, all_article_ids, recipe_errors)
            self.assertEqual(recipe_id, recipe["recipeId"])
            self.assertEqual(spec["articles"], set(recipe["articleIds"]))
            self.assertEqual("draft", recipe["editorial"]["state"])
            self.assertTrue(_pending_human_review(recipe["editorial"]["reviewedBy"]))
            self.assertNotIn("workflow", recipe)
            self.assertEqual(
                {
                    "id": spec["fragmentId"],
                    "path": "fragment.json",
                    "format": "nodes-wizard-fragment/1.0",
                },
                recipe["fragment"],
            )
            recipe_body = (path.parent / recipe["body"]).read_text(encoding="utf-8")
            self.assertNotIn("\ufffd", recipe_body)

            fragment_path = path.parent / recipe["fragment"]["path"]
            fragment = catalog.load_json(fragment_path)
            self.assertEqual([], catalog.json_schema_errors(fragment, fragment_schema), recipe_id)
            catalog.validate_fragment(fragment_path, fragment, recipe_errors)
            self.assertEqual(spec["fragmentId"], fragment["fragmentId"])
            nodes = {node["classType"]: node for node in fragment["nodes"]}
            self.assertEqual(set(spec["nodes"]), set(nodes))
            self.assertEqual(len(nodes), len(fragment["nodes"]))
            for class_type, expected_settings in spec["nodes"].items():
                self.assertEqual(expected_settings, nodes[class_type]["settings"])

            detector_ref = nodes["MediaPipeFaceLandmarker"]["ref"]
            loader_ref = nodes["LoadMediaPipeFaceLandmarker"]["ref"]
            sink_ref = nodes[spec["sink"]]["ref"]
            self.assertEqual(
                [("IMAGE", detector_ref, "image")],
                [
                    (item["type"], item["to"], item["input"])
                    for item in fragment["externalInputs"]
                ],
            )
            self.assertEqual(
                {
                    (loader_ref, "FACE_DETECTION_MODEL", detector_ref, "face_detection_model"),
                    (detector_ref, "face_landmarks", sink_ref, spec["sinkInput"]),
                },
                {
                    (item["from"], item["output"], item["to"], item["input"])
                    for item in fragment["connections"]
                },
            )
            self.assertNotIn("FACE_LANDMARKER", json.dumps(fragment))
            if spec["sink"] == "MediaPipeFaceMeshVisualize":
                self.assertFalse(
                    any(item["to"] == sink_ref and item["input"] == "image" for item in fragment["externalInputs"])
                )

            for external in fragment["externalInputs"]:
                target = next(node for node in fragment["nodes"] if node["ref"] == external["to"])
                self.assertEqual(
                    external["type"],
                    _runtime_inputs(dict(runtime[target["classType"]]))[external["input"]][0],
                )
            for edge in fragment["connections"]:
                source_node = next(node for node in fragment["nodes"] if node["ref"] == edge["from"])
                target_node = next(node for node in fragment["nodes"] if node["ref"] == edge["to"])
                source_runtime = dict(runtime[source_node["classType"]])
                target_runtime = dict(runtime[target_node["classType"]])
                output_index = source_runtime["output_name"].index(edge["output"])
                self.assertEqual(
                    source_runtime["output"][output_index],
                    _runtime_inputs(target_runtime)[edge["input"]][0],
                )

        self.assertEqual([], article_errors)
        self.assertEqual([], recipe_errors)

    def test_runtime_fingerprints_flags_ports_and_dynamic_objects(self) -> None:
        runtime = catalog.object_info_nodes(catalog.load_json(INVENTORY))
        expected_aliases = {
            "LoadMediaPipeFaceLandmarker": [
                "face", "facial", "mediapipe", "face landmark", "face mesh", "blazeface", "face detection"
            ],
            "MediaPipeFaceLandmarker": [
                "face", "facial", "mediapipe", "face landmark", "face mesh", "blazeface", "face detection"
            ],
            "MediaPipeFaceMeshVisualize": [
                "face", "facial", "mediapipe", "face landmark", "face mesh", "blazeface", "face detection", "visualize"
            ],
            "MediaPipeFaceMask": [
                "face", "facial", "mediapipe", "face mask", "blazeface", "face detection", "visualize"
            ],
        }
        for spec in ARTICLE_SPECS.values():
            class_type = spec["classType"]
            definition = dict(runtime[class_type])
            self.assertEqual("comfy_extras.nodes_mediapipe", definition["python_module"])
            self.assertEqual(spec["displayName"], definition["display_name"])
            self.assertEqual(spec["category"], definition["category"])
            self.assertEqual(expected_aliases[class_type], definition["search_aliases"])
            self.assertEqual(spec["fingerprint"], catalog.schema_fingerprint(class_type, definition))
            for flag in (
                "deprecated", "experimental", "dev_only", "api_node", "output_node",
                "has_intermediate_output", "is_input_list",
            ):
                self.assertFalse(definition[flag], (class_type, flag))

        loader = dict(runtime["LoadMediaPipeFaceLandmarker"])
        self.assertEqual(["model_name"], loader["input_order"]["required"])
        self.assertEqual(
            ["COMBO", {"tooltip": "Face detection model from models/detection/.", "multiselect": False, "options": []}],
            loader["input"]["required"]["model_name"],
        )
        self.assertEqual(["FACE_DETECTION_MODEL"], loader["output"])
        self.assertEqual(["FACE_DETECTION_MODEL"], loader["output_name"])

        detector = dict(runtime["MediaPipeFaceLandmarker"])
        self.assertEqual(
            ["face_detection_model", "image", "detector_variant", "num_faces", "min_confidence", "missing_frame_fallback"],
            detector["input_order"]["required"],
        )
        required = detector["input"]["required"]
        self.assertEqual("FACE_DETECTION_MODEL", required["face_detection_model"][0])
        self.assertEqual("IMAGE", required["image"][0])
        self.assertEqual(["short", "full", "both"], required["detector_variant"][1]["options"])
        self.assertEqual("short", required["detector_variant"][1]["default"])
        self.assertEqual(
            {"default": 1, "min": 0, "max": 16, "step": 1},
            {key: required["num_faces"][1][key] for key in ("default", "min", "max", "step")},
        )
        self.assertEqual(
            {"advanced": True, "default": 0.5, "min": 0.0, "max": 1.0, "step": 0.01},
            {key: required["min_confidence"][1][key] for key in ("advanced", "default", "min", "max", "step")},
        )
        self.assertEqual(
            ["empty", "previous", "interpolate"],
            required["missing_frame_fallback"][1]["options"],
        )
        self.assertEqual("empty", required["missing_frame_fallback"][1]["default"])
        self.assertEqual(["FACE_LANDMARKS", "BOUNDING_BOX"], detector["output"])
        self.assertEqual(["face_landmarks", "bboxes"], detector["output_name"])
        self.assertNotIn("FACE_LANDMARKER", json.dumps(detector))

        visualize = dict(runtime["MediaPipeFaceMeshVisualize"])
        self.assertEqual(
            ["face_landmarks", "connections", "color", "thickness", "point_size"],
            visualize["input_order"]["required"],
        )
        self.assertEqual(["image"], visualize["input_order"]["optional"])
        self.assertEqual("IMAGE", visualize["input"]["optional"]["image"][0])
        connection_descriptor = visualize["input"]["required"]["connections"]
        self.assertEqual("COMFY_DYNAMICCOMBO_V3", connection_descriptor[0])
        options = connection_descriptor[1]["options"]
        self.assertEqual(["all", "fill", "custom"], [item["key"] for item in options])
        custom_inputs = options[2]["inputs"]["required"]
        self.assertEqual(
            ["face_oval", "lips", "left_eye", "right_eye", "left_eyebrow", "right_eyebrow", "irises", "nose", "tesselation"],
            list(custom_inputs),
        )
        self.assertEqual(
            [True, True, True, True, True, True, True, True, False],
            [descriptor[1]["default"] for descriptor in custom_inputs.values()],
        )
        self.assertEqual(["COLOR", {"default": "#00ff00", "socketless": True}], visualize["input"]["required"]["color"])
        self.assertEqual(["IMAGE"], visualize["output"])

        mask = dict(runtime["MediaPipeFaceMask"])
        region_descriptor = mask["input"]["required"]["regions"]
        self.assertEqual("COMFY_DYNAMICCOMBO_V3", region_descriptor[0])
        region_options = region_descriptor[1]["options"]
        self.assertEqual(["all", "custom"], [item["key"] for item in region_options])
        region_inputs = region_options[1]["inputs"]["required"]
        self.assertEqual(
            ["face_oval", "lips", "left_eye", "right_eye", "irises"],
            list(region_inputs),
        )
        self.assertEqual(
            [True, False, False, False, False],
            [descriptor[1]["default"] for descriptor in region_inputs.values()],
        )
        self.assertEqual(["MASK"], mask["output"])

        replacement_strings = set(_walk_strings(catalog.load_json(REPLACEMENTS)))
        self.assertTrue(TARGET_TYPES.isdisjoint(replacement_strings))

    def test_pinned_source_docs_hashes_and_documented_discrepancies(self) -> None:
        self.assertEqual(
            "c2bcbecd82ec5ae66594340b395c24ef0217b238",
            (SOURCE / ".git" / "HEAD").read_text(encoding="ascii").strip(),
        )
        for relative, expected_hash in SOURCE_HASHES.items():
            self.assertEqual(
                expected_hash,
                hashlib.sha256((SOURCE / relative).read_bytes()).hexdigest(),
                relative,
            )

        nodes_path = SOURCE / "comfy_extras" / "nodes_mediapipe.py"
        nodes_source = nodes_path.read_text(encoding="utf-8")
        landmarker_source = (
            SOURCE / "comfy_extras" / "mediapipe" / "face_landmarker.py"
        ).read_text(encoding="utf-8")
        geometry_source = (
            SOURCE / "comfy_extras" / "mediapipe" / "face_geometry.py"
        ).read_text(encoding="utf-8")
        tree = ast.parse(nodes_source)
        ranges = {
            node.name: (node.lineno, node.end_lineno)
            for node in tree.body
            if isinstance(node, (ast.ClassDef, ast.FunctionDef))
        }
        self.assertEqual((198, 220), ranges["LoadMediaPipeFaceLandmarker"])
        self.assertEqual((227, 311), ranges["MediaPipeFaceLandmarker"])
        self.assertEqual((329, 397), ranges["MediaPipeFaceMeshVisualize"])
        self.assertEqual((442, 498), ranges["MediaPipeFaceMask"])
        loader_node = next(
            node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == "LoadMediaPipeFaceLandmarker"
        )
        loader_text = ast.get_source_segment(nodes_source, loader_node) or ""
        self.assertIn('get_full_path_or_raise("detection", model_name)', loader_text)
        self.assertIn("safe_load=True", loader_text)
        self.assertNotIn("http", loader_text.lower())
        self.assertNotIn("download", loader_text.lower())
        self.assertIn("chunk = 16", nodes_source)
        self.assertIn("short_res[bi] if len(short_res[bi]) >= len(full_res[bi])", nodes_source)
        self.assertIn("_fill_missing_frames(frames, missing_frame_fallback)", nodes_source)
        self.assertIn('base["all"] = base["contours"] | base["irises"] | base["nose"]', nodes_source)
        self.assertIn("NUM_LANDMARKS = 478", landmarker_source)
        self.assertIn('"bbox_xyxy": np.array([mn[0], mn[1], mx[0], mx[1]]', landmarker_source)
        self.assertIn("presence float (raw logit)", landmarker_source)
        self.assertIn("np.linalg.svd", geometry_source)
        self.assertIn("Procrustes denominator collapsed", geometry_source)

        folder_paths = (SOURCE / "folder_paths.py").read_text(encoding="utf-8")
        utils = (SOURCE / "comfy" / "utils.py").read_text(encoding="utf-8")
        self.assertIn('folder_names_and_paths["detection"]', folder_paths)
        self.assertIn('filename = os.path.relpath(os.path.join("/", filename), "/")', folder_paths)
        self.assertIn("safetensors.safe_open", utils)
        self.assertIn("weights_only=True", utils)

        frontend_scan = (
            FRONTEND_SOURCE / "src" / "platform" / "missingModel" / "missingModelScan.ts"
        ).read_text(encoding="utf-8")
        frontend_download = (
            FRONTEND_SOURCE / "src" / "platform" / "missingModel" / "missingModelDownload.ts"
        ).read_text(encoding="utf-8")
        self.assertIn("properties.models", frontend_scan)
        self.assertIn("https://huggingface.co/", frontend_download)
        self.assertIn(".safetensors", frontend_download)

        self.assertEqual(DOCS_SHA256, hashlib.sha256(DOCS_WHEEL.read_bytes()).hexdigest())
        with zipfile.ZipFile(DOCS_WHEEL) as archive:
            self.assertIsNone(archive.testzip())
            pages: dict[str, str] = {}
            for member, expected_hash in DOC_PAGE_HASHES.items():
                raw = archive.read(member)
                self.assertEqual(expected_hash, hashlib.sha256(raw).hexdigest(), member)
                pages[member] = raw.decode("utf-8")
            for class_type in TARGET_TYPES:
                members = [
                    name
                    for name in archive.namelist()
                    if name.startswith(f"comfyui_embedded_docs/docs/{class_type}/")
                    and name.endswith(".md")
                ]
                self.assertEqual(12, len(members), class_type)

        detector_en = pages["comfyui_embedded_docs/docs/MediaPipeFaceLandmarker/en.md"]
        visualize_en = pages["comfyui_embedded_docs/docs/MediaPipeFaceMeshVisualize/en.md"]
        mask_en = pages["comfyui_embedded_docs/docs/MediaPipeFaceMask/en.md"]
        self.assertIn("468 facial landmarks", detector_en)
        self.assertNotIn("478 facial landmarks", detector_en)
        self.assertIn("draws the full mesh", visualize_en)
        self.assertIn("left_iris", visualize_en)
        self.assertIn("right_iris", visualize_en)
        self.assertIn("`eyes`", mask_en)
        self.assertIn("Default: True", mask_en)
        self.assertNotIn("left_eye", mask_en)
        self.assertNotIn("right_eye", mask_en)
        for member, text in pages.items():
            marker = "AI-generated" if member.endswith("/en.md") else "создана с помощью ИИ"
            self.assertIn(marker, text)

    def test_workflow_wheel_exhaustive_zero_census_and_indices(self) -> None:
        self.assertEqual(WORKFLOW_SHA256, hashlib.sha256(WORKFLOW_WHEEL.read_bytes()).hexdigest())
        json_count = 0
        root_count = 0
        subgraph_count = 0
        root_node_count = 0
        subgraph_node_count = 0
        raw_occurrences: Counter[str] = Counter()
        exact_scalar_occurrences: Counter[str] = Counter()
        substring_scalar_occurrences: Counter[str] = Counter()
        direct: list[tuple[str, str, Any]] = []
        generic_mediapipe: list[tuple[str, str]] = []

        with zipfile.ZipFile(WORKFLOW_WHEEL) as archive:
            self.assertIsNone(archive.testzip())
            for member in archive.namelist():
                if not member.endswith(".json"):
                    continue
                json_count += 1
                raw = archive.read(member)
                payload = json.loads(raw)
                for class_type in TARGET_TYPES:
                    raw_occurrences[class_type] += raw.count(class_type.encode("utf-8"))
                for scalar in _walk_strings(payload):
                    for class_type in TARGET_TYPES:
                        if scalar == class_type:
                            exact_scalar_occurrences[class_type] += 1
                        if class_type in scalar:
                            substring_scalar_occurrences[class_type] += 1
                    if "mediapipe" in scalar.lower():
                        generic_mediapipe.append((member, scalar))
                if not isinstance(payload, dict):
                    continue
                subgraphs = _subgraphs(payload)
                subgraph_count += len(subgraphs)
                subgraph_node_count += sum(len(graph.get("nodes", [])) for graph in subgraphs)
                root_graphs = (
                    [("root", payload)]
                    if isinstance(payload.get("nodes"), list)
                    else []
                )
                if root_graphs:
                    root_count += 1
                    root_node_count += len(payload["nodes"])
                for scope, graph in root_graphs + [("subgraph", item) for item in subgraphs]:
                    for node in graph.get("nodes", []):
                        if isinstance(node, dict) and node.get("type") in TARGET_TYPES:
                            direct.append((member, scope, node.get("id")))

            english_index = json.loads(
                archive.read("comfyui_workflow_templates_json/templates/index.json")
            )
            russian_index = json.loads(
                archive.read("comfyui_workflow_templates_json/templates/index.ru.json")
            )

        self.assertEqual((512, 496, 272), (json_count, root_count, subgraph_count))
        self.assertEqual((4083, 4037, 8120), (
            root_node_count, subgraph_node_count, root_node_count + subgraph_node_count
        ))
        self.assertEqual([], direct)
        self.assertTrue(all(value == 0 for value in raw_occurrences.values()))
        self.assertTrue(all(value == 0 for value in exact_scalar_occurrences.values()))
        self.assertTrue(all(value == 0 for value in substring_scalar_occurrences.values()))
        self.assertEqual([], generic_mediapipe)
        for index in (english_index, russian_index):
            serialized = json.dumps(index, ensure_ascii=False)
            self.assertNotIn("mediapipe", serialized.lower())
            for needle in TARGET_TYPES | DISPLAY_NAMES:
                self.assertNotIn(needle, serialized)

    def test_exact_source_blueprints_outside_wheel(self) -> None:
        cases = [
            (
                SOURCE / "blueprints" / "Image Face Detection (Mediapipe).json",
                "6062babb-b649-4a71-be9e-20ebce567744",
                74,
            ),
            (
                SOURCE / "blueprints" / "Video Face Detection (Mediapipe).json",
                "ca14b151-8f5e-4386-aab7-d2ec84eaf43c",
                157,
            ),
        ]
        model_metadata = [
            {
                "name": "mediapipe_face_fp32.safetensors",
                "url": "https://huggingface.co/Comfy-Org/mediapipe/resolve/main/detection/mediapipe_face_fp32.safetensors",
                "directory": "detection",
            }
        ]
        runtime = catalog.object_info_nodes(catalog.load_json(INVENTORY))

        for path, expected_uuid, stale_link_id in cases:
            payload = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(1, len(payload["nodes"]))
            self.assertEqual(expected_uuid, payload["nodes"][0]["type"])
            subgraphs = _subgraphs(payload)
            self.assertEqual(1, len(subgraphs))
            graph = subgraphs[0]
            self.assertEqual(expected_uuid, graph["id"])
            self.assertEqual(1, graph["version"])

            loader = _node_by_type(graph, "LoadMediaPipeFaceLandmarker")
            detector = _node_by_type(graph, "MediaPipeFaceLandmarker")
            mask = _node_by_type(graph, "MediaPipeFaceMask")
            self.assertEqual((2, 0, ["mediapipe_face_fp32.safetensors"]), (loader["id"], loader["mode"], loader["widgets_values"]))
            self.assertEqual((11, 0, ["full", 0, 0.5, "empty"]), (detector["id"], detector["mode"], detector["widgets_values"]))
            self.assertEqual((20, 0, ["custom", True, False, False, False, False]), (mask["id"], mask["mode"], mask["widgets_values"]))
            self.assertEqual(model_metadata, loader["properties"]["models"])
            self.assertNotIn("hash", loader["properties"]["models"][0])
            self.assertNotIn("hash_type", loader["properties"]["models"][0])
            self.assertFalse(any(node.get("type") == "MediaPipeFaceMeshVisualize" for node in graph["nodes"]))

            stale_inputs = [
                item
                for item in detector["inputs"]
                if item.get("type") == "FACE_LANDMARKER"
            ]
            self.assertEqual(1, len(stale_inputs))
            self.assertEqual(stale_link_id, stale_inputs[0]["link"])
            self.assertNotIn(
                "face_landmarker",
                runtime["MediaPipeFaceLandmarker"]["input"]["required"],
            )
            links = _normalized_links(graph)
            self.assertTrue(
                {
                    (66, 2, 0, 11, 0, "FACE_DETECTION_MODEL"),
                    (46, 11, 0, 20, 0, "FACE_LANDMARKS"),
                }.issubset(links)
            )
            stale_link = next(link for link in links if link[0] == stale_link_id)
            self.assertEqual((-10, 11, 6, "FACE_LANDMARKER"), (stale_link[1], stale_link[3], stale_link[4], stale_link[5]))

            if expected_uuid.startswith("6062"):
                self.assertTrue(
                    {
                        (60, -10, 0, 11, 1, "IMAGE"),
                        (44, 11, 0, -20, 0, "FACE_LANDMARKS"),
                        (25, 11, 1, -20, 1, "BOUNDING_BOX"),
                        (83, 20, 0, -20, 2, "MASK"),
                    }.issubset(links)
                )
            else:
                video_components = _node_by_type(graph, "GetVideoComponents")
                video_slice = _node_by_type(graph, "Video Slice")
                video_switch = _node_by_type(graph, "ComfySwitchNode")
                self.assertEqual(160, video_components["id"])
                self.assertNotIn("widgets_values", video_components)
                self.assertEqual((164, [0, 0, False]), (video_slice["id"], video_slice["widgets_values"]))
                self.assertEqual((165, [False]), (video_switch["id"], video_switch["widgets_values"]))
                self.assertTrue(
                    {
                        (149, 160, 0, 11, 1, "IMAGE"),
                        (150, -10, 0, 164, 0, "VIDEO"),
                        (151, 164, 0, 165, 1, "VIDEO"),
                        (152, 165, 0, 160, 0, "VIDEO"),
                        (153, -10, 0, 165, 0, "VIDEO"),
                        (83, 20, 0, -20, 0, "MASK"),
                        (166, 11, 1, -20, 1, "BOUNDING_BOX"),
                        (167, 11, 0, -20, 2, "FACE_LANDMARKS"),
                    }.issubset(links)
                )

    def test_exact_source_model_free_probe(self) -> None:
        result = run_probe(SOURCE)
        self.assertFalse(result["workflowExampleExecuted"])
        self.assertFalse(result["networkUsed"])
        self.assertFalse(result["weightsLoaded"])
        self.assertFalse(result["gpuUsed"])
        self.assertEqual(
            [["detection", "mediapipe_face_fp32.safetensors"]],
            [list(item) for item in result["loader"]["folderCalls"]],
        )
        self.assertTrue(result["loader"]["safeLoad"])
        self.assertTrue(result["loader"]["wrapperReceivedExactState"])

        fallback = result["fallback"]
        self.assertTrue(fallback["previousLeadingEmpty"])
        self.assertTrue(fallback["previousFilledTrailing"])
        self.assertTrue(fallback["previousCopyIndependent"])
        self.assertEqual(10.0, fallback["interpolatedFirstX"])
        self.assertEqual([1, 1, 1, 1], fallback["endpointCounts"])
        self.assertEqual(1, fallback["mismatchedCount"])

        detector = result["detector"]
        self.assertTrue(detector["inputUnchanged"])
        self.assertEqual([16, 2], detector["shortChunks"])
        self.assertEqual([16, 2], detector["fullChunks"])
        self.assertEqual([0], detector["forwardedNumFaces"])
        self.assertEqual([0.5], detector["forwardedThresholds"])
        self.assertEqual([1.0, 2.0, 1.0], detector["chosenVariantCodes"])
        self.assertEqual((18, 18), (detector["frameCount"], detector["bboxFrameCount"]))
        self.assertEqual(
            {"x": 5.0, "y": 5.0, "width": 6.0, "height": 6.0, "label": "face", "score": 0.75},
            detector["firstBBox"],
        )
        self.assertTrue(detector["allMatricesFinite4x4"])

        for key in (
            "invalidColorFallsBackGreen",
            "allOmitsTessellation",
            "customDrawsTessellation",
            "customEmptyStillDrawsPoints",
            "fillIgnoresPointDrawing",
            "extraExternalFrameUnchanged",
        ):
            self.assertTrue(result["visualize"][key], key)
        self.assertEqual([2, 20, 20, 3], result["visualize"]["blackCanvasShape"])
        self.assertEqual([3, 20, 20, 3], result["visualize"]["externalBatchShape"])

        self.assertEqual([2, 20, 20], result["mask"]["shape"])
        self.assertEqual([0.0, 1.0], result["mask"]["binaryValues"])
        for key in ("emptyFrameZero", "customNoneZero", "lipsSmallerThanAll", "multipleFacesUnion"):
            self.assertTrue(result["mask"][key], key)

        self.assertEqual([4, 4], result["geometry"]["shape"])
        self.assertTrue(result["geometry"]["finite"])
        self.assertEqual([0.0, 0.0, 0.0, 1.0], result["geometry"]["homogeneousBottomRow"])
        self.assertTrue(result["geometry"]["degenerateRaised"])


if __name__ == "__main__":
    unittest.main()
