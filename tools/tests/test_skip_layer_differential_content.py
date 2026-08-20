from __future__ import annotations

import ast
import hashlib
import json
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
    "core.skip-layer-guidance-dit": {
        "directory": "skip-layer-guidance-dit",
        "classType": "SkipLayerGuidanceDiT",
        "module": "comfy_extras.nodes_slg",
        "fingerprint": "sha256:517c17fc845775855aafce528a4483011f11e6a13fa057e6177a358ec808354e",
        "recipe": "recipe.skip-layer-guidance-dit-wan",
    },
    "core.skip-layer-guidance-dit-simple": {
        "directory": "skip-layer-guidance-dit-simple",
        "classType": "SkipLayerGuidanceDiTSimple",
        "module": "comfy_extras.nodes_slg",
        "fingerprint": "sha256:d67fd781f6a8b675040a3f81ae1f53e3b0c3f53c827feacfe2c571c850765148",
        "recipe": "recipe.skip-layer-guidance-dit-simple-wan",
    },
    "core.skip-layer-guidance-sd3": {
        "directory": "skip-layer-guidance-sd3",
        "classType": "SkipLayerGuidanceSD3",
        "module": "comfy_extras.nodes_sd3",
        "fingerprint": "sha256:1ec2296cddaf0b1af19cabf4341fab23974bdd65e67589273c697abe280c2ee9",
        "recipe": "recipe.skip-layer-guidance-sd3-source",
    },
    "core.differential-diffusion": {
        "directory": "differential-diffusion",
        "classType": "DifferentialDiffusion",
        "module": "comfy_extras.nodes_differential_diffusion",
        "fingerprint": "sha256:99e5950eb9d8e119e5bcf78dc7167fcbdfd2f2d92d7c03730757fad9368cbb66",
        "recipe": "recipe.differential-diffusion-flux-fill",
    },
}

RECIPE_SPECS = {
    "recipe.skip-layer-guidance-dit-wan": {
        "directory": "skip-layer-guidance-dit-wan",
        "article": "core.skip-layer-guidance-dit",
        "classType": "SkipLayerGuidanceDiT",
        "settings": {
            "double_layers": "9,10",
            "single_layers": "9,10",
            "scale": 3.0,
            "start_percent": 0.01,
            "end_percent": 0.8,
            "rescaling_scale": 0.0,
        },
    },
    "recipe.skip-layer-guidance-dit-simple-wan": {
        "directory": "skip-layer-guidance-dit-simple-wan",
        "article": "core.skip-layer-guidance-dit-simple",
        "classType": "SkipLayerGuidanceDiTSimple",
        "settings": {
            "double_layers": "9",
            "single_layers": "",
            "start_percent": 0.0,
            "end_percent": 1.0,
        },
    },
    "recipe.skip-layer-guidance-sd3-source": {
        "directory": "skip-layer-guidance-sd3-source",
        "article": "core.skip-layer-guidance-sd3",
        "classType": "SkipLayerGuidanceSD3",
        "settings": {
            "layers": "7, 8, 9",
            "scale": 3.0,
            "start_percent": 0.01,
            "end_percent": 0.15,
        },
    },
    "recipe.differential-diffusion-flux-fill": {
        "directory": "differential-diffusion-flux-fill",
        "article": "core.differential-diffusion",
        "classType": "DifferentialDiffusion",
        "settings": {"strength": 1.0},
    },
}

EXPECTED_HEADINGS = [
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

EXPECTED_RUNTIME = {
    "SkipLayerGuidanceDiT": {
        "module": "comfy_extras.nodes_slg",
        "category": "advanced/guidance",
        "description": "Generic version of SkipLayerGuidance node that can be used on every DiT model.",
        "display_name": None,
        "search_aliases": None,
        "input": {
            "required": {
                "model": ["MODEL", {}],
                "double_layers": [
                    "STRING",
                    {"advanced": True, "default": "7, 8, 9", "multiline": False},
                ],
                "single_layers": [
                    "STRING",
                    {"advanced": True, "default": "7, 8, 9", "multiline": False},
                ],
                "scale": [
                    "FLOAT",
                    {"default": 3.0, "min": 0.0, "max": 10.0, "step": 0.1},
                ],
                "start_percent": [
                    "FLOAT",
                    {
                        "advanced": True,
                        "default": 0.01,
                        "min": 0.0,
                        "max": 1.0,
                        "step": 0.001,
                    },
                ],
                "end_percent": [
                    "FLOAT",
                    {
                        "advanced": True,
                        "default": 0.15,
                        "min": 0.0,
                        "max": 1.0,
                        "step": 0.001,
                    },
                ],
                "rescaling_scale": [
                    "FLOAT",
                    {"default": 0.0, "min": 0.0, "max": 10.0, "step": 0.01},
                ],
            }
        },
        "input_order": {
            "required": [
                "model",
                "double_layers",
                "single_layers",
                "scale",
                "start_percent",
                "end_percent",
                "rescaling_scale",
            ]
        },
    },
    "SkipLayerGuidanceDiTSimple": {
        "module": "comfy_extras.nodes_slg",
        "category": "advanced/guidance",
        "description": "Simple version of the SkipLayerGuidanceDiT node that only modifies the uncond pass.",
        "display_name": None,
        "search_aliases": None,
        "input": {
            "required": {
                "model": ["MODEL", {}],
                "double_layers": [
                    "STRING",
                    {"advanced": True, "default": "7, 8, 9", "multiline": False},
                ],
                "single_layers": [
                    "STRING",
                    {"advanced": True, "default": "7, 8, 9", "multiline": False},
                ],
                "start_percent": [
                    "FLOAT",
                    {
                        "advanced": True,
                        "default": 0.0,
                        "min": 0.0,
                        "max": 1.0,
                        "step": 0.001,
                    },
                ],
                "end_percent": [
                    "FLOAT",
                    {
                        "advanced": True,
                        "default": 1.0,
                        "min": 0.0,
                        "max": 1.0,
                        "step": 0.001,
                    },
                ],
            }
        },
        "input_order": {
            "required": [
                "model",
                "double_layers",
                "single_layers",
                "start_percent",
                "end_percent",
            ]
        },
    },
    "SkipLayerGuidanceSD3": {
        "module": "comfy_extras.nodes_sd3",
        "category": "advanced/guidance",
        "description": "Generic version of SkipLayerGuidance node that can be used on every DiT model.",
        "display_name": None,
        "search_aliases": None,
        "input": {
            "required": {
                "model": ["MODEL", {}],
                "layers": [
                    "STRING",
                    {"advanced": True, "default": "7, 8, 9", "multiline": False},
                ],
                "scale": [
                    "FLOAT",
                    {"default": 3.0, "min": 0.0, "max": 10.0, "step": 0.1},
                ],
                "start_percent": [
                    "FLOAT",
                    {
                        "advanced": True,
                        "default": 0.01,
                        "min": 0.0,
                        "max": 1.0,
                        "step": 0.001,
                    },
                ],
                "end_percent": [
                    "FLOAT",
                    {
                        "advanced": True,
                        "default": 0.15,
                        "min": 0.0,
                        "max": 1.0,
                        "step": 0.001,
                    },
                ],
            }
        },
        "input_order": {
            "required": ["model", "layers", "scale", "start_percent", "end_percent"]
        },
    },
    "DifferentialDiffusion": {
        "module": "comfy_extras.nodes_differential_diffusion",
        "category": "experimental",
        "description": "",
        "display_name": "Differential Diffusion",
        "search_aliases": ["inpaint gradient", "variable denoise strength"],
        "input": {
            "required": {"model": ["MODEL", {}]},
            "optional": {
                "strength": [
                    "FLOAT",
                    {"default": 1.0, "min": 0.0, "max": 1.0, "step": 0.01},
                ]
            },
        },
        "input_order": {"required": ["model"], "optional": ["strength"]},
    },
}

DOC_PAGE_HASHES = {
    "comfyui_embedded_docs/docs/SkipLayerGuidanceDiT/en.md": "f2cdc1daaee6b2ce0b739b5f2b6c23134d5fc5c7b3c836201fefcfc419615adc",
    "comfyui_embedded_docs/docs/SkipLayerGuidanceDiT/ru.md": "05f9c64738899dca5e57a41a90351982a985c7c069148736d6fed7b292466040",
    "comfyui_embedded_docs/docs/SkipLayerGuidanceDiTSimple/en.md": "0428655c42390e74711ab1beac56b535fbc286cf5a9ff85145025f875f410f8a",
    "comfyui_embedded_docs/docs/SkipLayerGuidanceDiTSimple/ru.md": "0b638be8ee673f2f04de2cd8249b292b0cbcb2e8e584b52578818960caadfc2b",
    "comfyui_embedded_docs/docs/SkipLayerGuidanceSD3/en.md": "7a9753e752f0c8fb248b70a4b38cdab8c5fa5c9296a495e7388a9e6b0619ae51",
    "comfyui_embedded_docs/docs/SkipLayerGuidanceSD3/ru.md": "292bd3c50b4428961aad8f196b6e840763dffb703fb08dae583f44b341466b2c",
    "comfyui_embedded_docs/docs/DifferentialDiffusion/en.md": "478a845a8e4287c6978b003b6b5ea40928235cd1fefdfff785e6f482a877f507",
    "comfyui_embedded_docs/docs/DifferentialDiffusion/ru.md": "50527761228607b65645a3810b18442996c0dd15e9a258c4bfb448ce8c41dff0",
}

FULL_INVENTORY = catalog.CONTENT / "runtime" / "comfyui-0.32.0.object-info.json"
REPLACEMENTS = catalog.CONTENT / "runtime" / "comfyui-0.32.0.node-replacements.json"
SOURCE = catalog.ROOT / ".comfyui-source-0.32.0"
WORKFLOW_WHEEL = (
    catalog.ROOT
    / ".upstream-cache"
    / "comfyui_workflow_templates_json-0.1.42-py3-none-any.whl"
)
WORKFLOW_WHEEL_SHA256 = "242982d65e1c51ca03d892bc1009bb6843f457e7dfc0c20afe6438770b7a14a3"
DOCS_WHEEL = (
    catalog.ROOT / ".upstream-cache" / "comfyui_embedded_docs-0.5.9-py3-none-any.whl"
)
DOCS_WHEEL_SHA256 = "30afae432a71c96aa59421d0f37388c66ff6572b8cbeee8ff045e4d5f84f896c"
PROBE = Path(__file__).with_name("skip_layer_differential_synthetic_probe.py")
TARGET_TYPES = {
    "SkipLayerGuidanceDiT",
    "SkipLayerGuidanceDiTSimple",
    "SkipLayerGuidanceSD3",
    "DifferentialDiffusion",
}


def article_path(spec: dict[str, Any]) -> Path:
    return catalog.CONTENT / "articles" / "core" / spec["directory"] / "manifest.json"


def recipe_path(spec: dict[str, Any]) -> Path:
    return catalog.CONTENT / "recipes" / spec["directory"] / "recipe.json"


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
        inputs = runtime.get("input", {}).get(group, {})
        if isinstance(inputs, dict):
            result.update(inputs)
    return result


def human_approval_pending(texts: list[str]) -> bool:
    text = " ".join(texts).lower()
    return ("human" in text and "pending" in text) or (
        "человеческ" in text
        and any(marker in text for marker in ("ожида", "не выполн", "не получ"))
    )


def walk_strings(value: Any) -> Iterator[str]:
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for nested in value.values():
            yield from walk_strings(nested)
    elif isinstance(value, list):
        for nested in value:
            yield from walk_strings(nested)


def normalized_links(graph: dict[str, Any]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for link in graph.get("links", []):
        if isinstance(link, list) and len(link) >= 6:
            result.append(
                {
                    "id": link[0],
                    "origin_id": link[1],
                    "origin_slot": link[2],
                    "target_id": link[3],
                    "target_slot": link[4],
                    "type": link[5],
                }
            )
        elif isinstance(link, dict):
            result.append(
                {
                    key: link.get(key)
                    for key in (
                        "id",
                        "origin_id",
                        "origin_slot",
                        "target_id",
                        "target_slot",
                        "type",
                    )
                }
            )
    return result


def workflow_graphs(payload: dict[str, Any]) -> Iterator[tuple[str, int | None, dict[str, Any]]]:
    yield "root", None, payload
    definitions = payload.get("definitions")
    subgraphs = definitions.get("subgraphs", []) if isinstance(definitions, dict) else []
    if isinstance(subgraphs, dict):
        subgraphs = list(subgraphs.values())
    for index, subgraph in enumerate(subgraphs):
        if isinstance(subgraph, dict):
            yield "subgraph", index, subgraph


def node_map(graph: dict[str, Any]) -> dict[Any, dict[str, Any]]:
    return {node.get("id"): node for node in graph.get("nodes", []) if isinstance(node, dict)}


def adjacency(record: dict[str, Any]) -> tuple[list[tuple[Any, ...]], list[tuple[Any, ...]]]:
    graph = record["graph"]
    target = record["node"]
    nodes = node_map(graph)
    incoming: list[tuple[Any, ...]] = []
    outgoing: list[tuple[Any, ...]] = []
    for link in normalized_links(graph):
        if link["target_id"] == target["id"]:
            source = nodes[link["origin_id"]]
            incoming.append(
                (
                    link["id"],
                    source["id"],
                    source["type"],
                    link["origin_slot"],
                    link["target_slot"],
                    link["type"],
                )
            )
        if link["origin_id"] == target["id"]:
            destination = nodes[link["target_id"]]
            outgoing.append(
                (
                    link["id"],
                    destination["id"],
                    destination["type"],
                    link["origin_slot"],
                    link["target_slot"],
                    link["type"],
                )
            )
    return sorted(incoming), sorted(outgoing)


class SkipLayerDifferentialContentTests(unittest.TestCase):
    def test_articles_fragment_recipes_and_research_contracts(self) -> None:
        article_schema = catalog.load_json(catalog.CONTENT / "schemas" / "article.schema.v1.json")
        recipe_schema = catalog.load_json(catalog.CONTENT / "schemas" / "recipe.schema.v1.json")
        fragment_schema = catalog.load_json(
            catalog.CONTENT / "schemas" / "recipe-fragment.schema.v1.json"
        )
        research_schema = catalog.load_json(
            catalog.CONTENT / "schemas" / "article-research.schema.v1.json"
        )
        article_ids = all_article_ids()
        errors: list[str] = []

        for article_id, spec in ARTICLE_SPECS.items():
            path = article_path(spec)
            article = catalog.load_json(path)
            self.assertEqual([], catalog.json_schema_errors(article, article_schema))
            catalog.validate_article(path, article, errors)
            self.assertEqual(article_id, article["articleId"])
            self.assertEqual("draft", article["status"])
            self.assertEqual("in_review", article["editorial"]["state"])
            self.assertEqual(spec["classType"], article["runtimeIdentity"]["classType"])
            self.assertEqual(spec["module"], article["runtimeIdentity"]["pythonModule"])
            self.assertEqual("backend", article["runtimeIdentity"]["origin"])
            self.assertEqual([], article["runtimeIdentity"]["aliases"])
            self.assertEqual(spec["fingerprint"], article["editorial"]["schemaHash"])
            self.assertIn(spec["recipe"], {asset["id"] for asset in article["assets"]})
            self.assertTrue(
                human_approval_pending([str(article["editorial"].get("reviewedBy", ""))])
            )

            relation_targets = (
                article["relations"]["related"] + article["relations"]["alternatives"]
            )
            if article["relations"]["replacedBy"] is not None:
                relation_targets.append(article["relations"]["replacedBy"])
            self.assertTrue(set(relation_targets).issubset(article_ids))

            body = (path.parent / article["body"]).read_text(encoding="utf-8")
            self.assertEqual(EXPECTED_HEADINGS, re.findall(r"^## (.+)$", body, re.MULTILINE))
            self.assertNotIn("\ufffd", body)

            research_path = (
                catalog.CONTENT / "research" / "reviews" / f"{article_id}.json"
            )
            research = catalog.load_json(research_path)
            self.assertEqual([], catalog.json_schema_errors(research, research_schema))
            self.assertEqual(article_id, research["articleId"])
            self.assertEqual(spec["classType"], research["node"]["classType"])
            self.assertEqual(spec["module"], research["node"]["pythonModule"])
            self.assertEqual("backend", research["node"]["origin"])
            self.assertEqual("fact_checked", research["state"])
            self.assertEqual("automated_assisted", research["reviewMode"])
            self.assertEqual(
                {
                    "comfyui": "0.32.0",
                    "frontend": "1.48.7",
                    "sourceCommit": "c2bcbecd82ec5ae66594340b395c24ef0217b238",
                    "embeddedDocs": "0.5.9",
                    "workflowTemplatesJson": "0.1.42",
                },
                research["baseline"],
            )
            checks = research["checks"]
            for check in (
                "implementationRead",
                "runtimeCompared",
                "officialCasesInspected",
                "exampleSchemaValidated",
                "russianEdited",
                "factsRecheckedAfterEditing",
            ):
                self.assertTrue(checks[check], f"{article_id}: {check}")
            self.assertFalse(checks["exampleExecuted"])
            self.assertTrue(human_approval_pending([str(gap) for gap in research["knownGaps"]]))
            self.assertGreaterEqual(
                {item["locale"] for item in research["evidence"]["embeddedDocs"]},
                {"en", "ru"},
            )
            self.assertTrue(research["evidence"]["sourceLocations"])
            self.assertTrue(research["evidence"]["workflows"])
            if spec["classType"] == "SkipLayerGuidanceSD3":
                gap_text = " ".join(research["knownGaps"]).lower()
                self.assertRegex(gap_text, r"workflow|шаблон|официальн")
                self.assertRegex(
                    gap_text,
                    r"не найден|нет прям|отсутств|has no direct|absent|missing",
                )

        runtime_nodes = catalog.object_info_nodes(catalog.load_json(FULL_INVENTORY))
        for recipe_id, spec in RECIPE_SPECS.items():
            path = recipe_path(spec)
            recipe = catalog.load_json(path)
            self.assertEqual([], catalog.json_schema_errors(recipe, recipe_schema))
            catalog.validate_recipe(path, recipe, article_ids, errors)
            self.assertEqual(recipe_id, recipe["recipeId"])
            self.assertNotIn("workflow", recipe)
            self.assertEqual("in_review", recipe["editorial"]["state"])
            self.assertIn(spec["article"], recipe["articleIds"])
            self.assertTrue(
                human_approval_pending([str(recipe["editorial"].get("reviewedBy", ""))])
            )
            recipe_body = (path.parent / recipe["body"]).read_text(encoding="utf-8")
            self.assertNotIn("\ufffd", recipe_body)

            fragment = catalog.load_json(path.parent / recipe["fragment"]["path"])
            self.assertEqual([], catalog.json_schema_errors(fragment, fragment_schema))
            target_nodes = [
                node for node in fragment["nodes"] if node["classType"] == spec["classType"]
            ]
            self.assertEqual(1, len(target_nodes), recipe_id)
            actual_settings = target_nodes[0]["settings"]
            self.assertEqual(set(spec["settings"]), set(actual_settings))
            for name, expected in spec["settings"].items():
                actual = actual_settings[name]
                if isinstance(expected, float):
                    self.assertAlmostEqual(expected, actual, places=12)
                else:
                    self.assertEqual(expected, actual)

            refs = {node["ref"]: node for node in fragment["nodes"]}
            for external in fragment["externalInputs"]:
                target_runtime = dict(runtime_nodes[refs[external["to"]]["classType"]])
                self.assertEqual(
                    external["type"],
                    runtime_inputs(target_runtime)[external["input"]][0],
                )
            for node in fragment["nodes"]:
                inputs = runtime_inputs(dict(runtime_nodes[node["classType"]]))
                for name, value in node["settings"].items():
                    self.assertIn(name, inputs)
                    options = inputs[name][1]
                    if isinstance(value, (int, float)) and not isinstance(value, bool):
                        self.assertGreaterEqual(value, options.get("min", value))
                        self.assertLessEqual(value, options.get("max", value))
            for connection in fragment["connections"]:
                source = dict(runtime_nodes[refs[connection["from"]]["classType"]])
                target = dict(runtime_nodes[refs[connection["to"]]["classType"]])
                output_index = source["output_name"].index(connection["output"])
                self.assertEqual(
                    source["output"][output_index],
                    runtime_inputs(target)[connection["input"]][0],
                )

        self.assertEqual([], errors)

    def test_exact_runtime_descriptors_flags_fingerprints_and_replacements(self) -> None:
        nodes = catalog.object_info_nodes(catalog.load_json(FULL_INVENTORY))
        fingerprints = {
            spec["classType"]: spec["fingerprint"] for spec in ARTICLE_SPECS.values()
        }
        for class_type, expected in EXPECTED_RUNTIME.items():
            runtime = dict(nodes[class_type])
            self.assertEqual(expected["module"], runtime["python_module"])
            self.assertEqual(expected["category"], runtime["category"])
            self.assertEqual(expected["description"], runtime["description"])
            self.assertEqual(expected["display_name"], runtime["display_name"])
            self.assertEqual(expected["search_aliases"], runtime["search_aliases"])
            self.assertEqual(expected["input"], runtime["input"])
            self.assertEqual(expected["input_order"], runtime["input_order"])
            self.assertEqual(["MODEL"], runtime["output"])
            self.assertEqual(["MODEL"], runtime["output_name"])
            self.assertEqual([False], runtime["output_is_list"])
            self.assertEqual([None], runtime["output_tooltips"])
            self.assertTrue(runtime["experimental"])
            for flag in (
                "deprecated",
                "dev_only",
                "api_node",
                "output_node",
                "has_intermediate_output",
                "is_input_list",
            ):
                self.assertFalse(runtime[flag], f"{class_type}: {flag}")
            self.assertEqual(
                fingerprints[class_type], catalog.schema_fingerprint(class_type, runtime)
            )

        replacements = catalog.load_json(REPLACEMENTS)
        self.assertTrue(TARGET_TYPES.isdisjoint(replacements))
        replacement_ids = {
            value
            for entries in replacements.values()
            for entry in entries
            for key, value in entry.items()
            if key in {"old_node_id", "new_node_id"} and isinstance(value, str)
        }
        self.assertTrue(TARGET_TYPES.isdisjoint(replacement_ids))

    @unittest.skipUnless(DOCS_WHEEL.exists(), "pinned embedded docs wheel is absent")
    def test_embedded_docs_exact_hashes_and_known_discrepancies(self) -> None:
        self.assertEqual(DOCS_WHEEL_SHA256, hashlib.sha256(DOCS_WHEEL.read_bytes()).hexdigest())
        with zipfile.ZipFile(DOCS_WHEEL) as archive:
            self.assertIsNone(archive.testzip())
            pages: dict[str, str] = {}
            for member, expected_hash in DOC_PAGE_HASHES.items():
                raw = archive.read(member)
                self.assertEqual(expected_hash, hashlib.sha256(raw).hexdigest(), member)
                pages[member] = raw.decode("utf-8")

        for member, text in pages.items():
            marker = "AI-generated" if member.endswith("/en.md") else "создана с помощью ИИ"
            self.assertIn(marker, text)
        simple_en = pages[
            "comfyui_embedded_docs/docs/SkipLayerGuidanceDiTSimple/en.md"
        ]
        simple_ru = pages[
            "comfyui_embedded_docs/docs/SkipLayerGuidanceDiTSimple/ru.md"
        ]
        self.assertIn("only applied when both", simple_en)
        self.assertIn("| No |", simple_en)
        self.assertIn("только в том случае, если оба", simple_ru)
        self.assertIn("`двойные_слои`", simple_ru)
        self.assertIn(
            "Вот перевод документации на русский язык:",
            pages["comfyui_embedded_docs/docs/SkipLayerGuidanceSD3/ru.md"],
        )
        self.assertIn(
            "Вот перевод документации на русский язык:",
            pages["comfyui_embedded_docs/docs/DifferentialDiffusion/ru.md"],
        )
        self.assertIn(
            "blending strength",
            pages["comfyui_embedded_docs/docs/DifferentialDiffusion/en.md"],
        )
        self.assertIn(
            "negative conditioning process",
            pages["comfyui_embedded_docs/docs/SkipLayerGuidanceSD3/en.md"],
        )

    @unittest.skipUnless(WORKFLOW_WHEEL.exists(), "pinned workflow wheel is absent")
    def test_exhaustive_workflow_census_topology_widgets_and_titles(self) -> None:
        self.assertEqual(
            WORKFLOW_WHEEL_SHA256, hashlib.sha256(WORKFLOW_WHEEL.read_bytes()).hexdigest()
        )
        json_count = 0
        root_count = 0
        subgraph_count = 0
        direct: list[dict[str, Any]] = []
        exact_scalars: Counter[str] = Counter()
        raw_substrings: Counter[str] = Counter()

        with zipfile.ZipFile(WORKFLOW_WHEEL) as archive:
            self.assertIsNone(archive.testzip())
            for archive_path in archive.namelist():
                if not archive_path.endswith(".json"):
                    continue
                json_count += 1
                raw = archive.read(archive_path)
                text = raw.decode("utf-8")
                for class_type in TARGET_TYPES:
                    raw_substrings[class_type] += text.count(class_type)
                payload = json.loads(raw)
                for scalar in walk_strings(payload):
                    if scalar in TARGET_TYPES:
                        exact_scalars[scalar] += 1
                if not isinstance(payload, dict) or not isinstance(payload.get("nodes"), list):
                    continue
                root_count += 1
                for scope, graph_index, graph in workflow_graphs(payload):
                    if scope == "subgraph":
                        subgraph_count += 1
                    for node in graph.get("nodes", []):
                        if isinstance(node, dict) and node.get("type") in TARGET_TYPES:
                            direct.append(
                                {
                                    "member": archive_path.rsplit("/", 1)[-1],
                                    "workflow": payload,
                                    "scope": scope,
                                    "graphIndex": graph_index,
                                    "graph": graph,
                                    "node": node,
                                }
                            )

            english_index = json.loads(
                archive.read("comfyui_workflow_templates_json/templates/index.json")
            )
            russian_index = json.loads(
                archive.read("comfyui_workflow_templates_json/templates/index.ru.json")
            )

        self.assertEqual((512, 496, 272), (json_count, root_count, subgraph_count))
        self.assertEqual(
            Counter(
                {
                    "SkipLayerGuidanceDiT": 4,
                    "SkipLayerGuidanceDiTSimple": 2,
                    "DifferentialDiffusion": 8,
                }
            ),
            exact_scalars,
        )
        self.assertEqual(6, raw_substrings["SkipLayerGuidanceDiT"])
        self.assertEqual(2, raw_substrings["SkipLayerGuidanceDiTSimple"])
        self.assertEqual(0, raw_substrings["SkipLayerGuidanceSD3"])
        self.assertEqual(8, raw_substrings["DifferentialDiffusion"])
        self.assertEqual(
            Counter(
                {
                    "SkipLayerGuidanceDiT": 2,
                    "SkipLayerGuidanceDiTSimple": 1,
                    "DifferentialDiffusion": 4,
                }
            ),
            Counter(record["node"]["type"] for record in direct),
        )
        self.assertEqual(
            Counter({("root", "SkipLayerGuidanceDiT"): 2, ("subgraph", "SkipLayerGuidanceDiTSimple"): 1, ("root", "DifferentialDiffusion"): 1, ("subgraph", "DifferentialDiffusion"): 3}),
            Counter((record["scope"], record["node"]["type"]) for record in direct),
        )
        self.assertTrue(all(record["node"]["mode"] == 0 for record in direct))

        records = {
            (
                record["member"],
                record["scope"],
                record["graph"].get("id"),
                record["node"]["id"],
            ): record
            for record in direct
        }
        expected_records = {
            (
                "wan2.1_fun_control.json",
                "root",
                "e7533930-2792-43a9-b4b5-ded4617d8a43",
                65,
            ): {
                "root": "e7533930-2792-43a9-b4b5-ded4617d8a43",
                "name": None,
                "type": "SkipLayerGuidanceDiT",
                "order": 7,
                "flags": {"collapsed": False},
                "widgets": ["9,10", "9,10", 3, 0.01, 0.8000000000000002, 0],
                "version": "0.3.27",
                "incoming": [(146, 37, "UNETLoader", 0, 0, "MODEL")],
                "outgoing": [(132, 67, "ModelSamplingSD3", 0, 0, "MODEL")],
                "neighbors": {
                    37: ["wan2.1_fun_control_1.3B_bf16.safetensors", "default"],
                    67: [5.000000000000001],
                },
            },
            (
                "wan2.1_fun_inp.json",
                "root",
                "e7533930-2792-43a9-b4b5-ded4617d8a43",
                65,
            ): {
                "root": "e7533930-2792-43a9-b4b5-ded4617d8a43",
                "name": None,
                "type": "SkipLayerGuidanceDiT",
                "order": 9,
                "flags": {"collapsed": False},
                "widgets": ["9,10", "9,10", 3, 0.01, 0.8000000000000002, 0],
                "version": "0.3.27",
                "incoming": [(146, 37, "UNETLoader", 0, 0, "MODEL")],
                "outgoing": [(132, 67, "ModelSamplingSD3", 0, 0, "MODEL")],
                "neighbors": {
                    37: ["wan2.1_fun_inp_1.3B_bf16.safetensors", "default"],
                    67: [5.000000000000001],
                },
            },
            (
                "video_wan_dancer.json",
                "subgraph",
                "f7467834-35a6-42fe-b525-7f17383beb4f",
                645,
            ): {
                "root": "a92ccb88-3a14-4114-9b6b-fa8952839d39",
                "name": "Image to Video (Wan Dancer)",
                "type": "SkipLayerGuidanceDiTSimple",
                "order": 34,
                "flags": {},
                "widgets": ["9", "", 0, 1],
                "version": "0.13.0",
                "incoming": [(1244, 643, "ModelSamplingSD3", 0, 0, "MODEL")],
                "outgoing": [
                    (1271, 653, "BasicScheduler", 0, 0, "MODEL"),
                    (1272, 657, "CFGGuider", 0, 0, "MODEL"),
                ],
                "neighbors": {643: [5], 653: ["simple", 48, 1], 657: [1]},
            },
            (
                "flux_fill_inpaint_example.json",
                "subgraph",
                "42bcb419-1e9f-48eb-a6d6-c22e0625db3a",
                39,
            ): {
                "root": "551d82b0-b1fb-483a-a5ea-564bdb813625",
                "name": "Flux.1 Fill Dev Image Inpainting",
                "type": "DifferentialDiffusion",
                "order": 4,
                "flags": {},
                "widgets": [1],
                "version": "0.3.64",
                "incoming": [(85, 31, "UNETLoader", 0, 0, "MODEL")],
                "outgoing": [(86, 3, "KSampler", 0, 0, "MODEL")],
                "neighbors": {
                    31: ["flux1-fill-dev.safetensors", "default"],
                    3: [190664687740330, "randomize", 20, 1, "euler", "normal", 1],
                },
            },
            (
                "flux_fill_outpaint_example.json",
                "root",
                "aff23af9-e8f4-41f8-8e4c-0854e355b753",
                39,
            ): {
                "root": "aff23af9-e8f4-41f8-8e4c-0854e355b753",
                "name": None,
                "type": "DifferentialDiffusion",
                "order": 6,
                "flags": {},
                "widgets": [1],
                "version": "0.3.64",
                "incoming": [(85, 31, "UNETLoader", 0, 0, "MODEL")],
                "outgoing": [(86, 3, "KSampler", 0, 0, "MODEL")],
                "neighbors": {
                    31: ["flux1-fill-dev.safetensors", "default"],
                    3: [164211176398261, "randomize", 20, 1, "euler", "normal", 1],
                },
            },
            (
                "image_flux.1_fill_dev_OneReward.json",
                "subgraph",
                "cb0eaf1c-704f-477d-8893-79665db14ed1",
                39,
            ): {
                "root": "e7c6bb1e-fcbe-44c9-a614-9d1972a25fb8",
                "name": "OneReward Image Inpainting",
                "type": "DifferentialDiffusion",
                "order": 5,
                "flags": {},
                "widgets": [1],
                "version": "0.3.59",
                "incoming": [(196, 100, "LoraLoaderModelOnly", 0, 0, "MODEL")],
                "outgoing": [(86, 3, "KSampler", 0, 0, "MODEL")],
                "neighbors": {
                    100: ["removal_timestep_alpha-2-1740.safetensors", 1],
                    3: [75154916226486, "randomize", 20, 1, "euler", "normal", 1],
                },
            },
            (
                "image_flux.1_fill_dev_OneReward.json",
                "subgraph",
                "b8560576-5524-4495-baa5-2cb40da12e9e",
                63,
            ): {
                "root": "e7c6bb1e-fcbe-44c9-a614-9d1972a25fb8",
                "name": "OneReward Image Outpainting",
                "type": "DifferentialDiffusion",
                "order": 3,
                "flags": {},
                "widgets": [1],
                "version": "0.3.59",
                "incoming": [(126, 64, "UNETLoader", 0, 0, "MODEL")],
                "outgoing": [(119, 58, "KSampler", 0, 0, "MODEL")],
                "neighbors": {
                    64: [
                        "flux.1-fill-dev-OneReward-transformer_fp8.safetensors",
                        "default",
                    ],
                    58: [220433686186430, "randomize", 20, 1, "euler", "normal", 1],
                },
            },
        }
        self.assertEqual(set(expected_records), set(records))
        for key, expected in expected_records.items():
            record = records[key]
            node = record["node"]
            self.assertEqual(expected["root"], record["workflow"].get("id"))
            self.assertEqual(0.4, record["workflow"].get("version"))
            self.assertEqual(expected["name"], record["graph"].get("name"))
            self.assertEqual(expected["type"], node["type"])
            self.assertEqual(expected["order"], node["order"])
            self.assertEqual(expected["flags"], node["flags"])
            self.assertEqual(expected["widgets"], node["widgets_values"])
            self.assertEqual("comfy-core", node["properties"]["cnr_id"])
            self.assertEqual(expected["version"], node["properties"]["ver"])
            self.assertEqual(node["type"], node["properties"]["Node name for S&R"])
            self.assertEqual(
                (expected["incoming"], expected["outgoing"]), adjacency(record)
            )
            nodes = node_map(record["graph"])
            for node_id, widgets in expected["neighbors"].items():
                self.assertEqual(widgets, nodes[node_id].get("widgets_values"))

        dit_records = [record for record in direct if record["node"]["type"] == "SkipLayerGuidanceDiT"]
        self.assertEqual(2, len(dit_records))
        self.assertEqual(
            {"e7533930-2792-43a9-b4b5-ded4617d8a43"},
            {record["graph"].get("id") for record in dit_records},
            "two distinct files deliberately reuse one serialized root UUID",
        )

        def title_map(index: list[dict[str, Any]]) -> dict[str, str]:
            return {
                template["name"]: template["title"]
                for category in index
                for template in category.get("templates", [])
                if isinstance(template, dict)
            }

        en_titles = title_map(english_index)
        ru_titles = title_map(russian_index)
        expected_titles = {
            "flux_fill_inpaint_example": ("Flux.1 Inpaint", "Flux.1 Inpaint"),
            "flux_fill_outpaint_example": ("Flux.1 Outpaint", "Flux.1 Outpaint"),
            "image_flux.1_fill_dev_OneReward": (
                "Flux.1 Dev OneReward",
                "Flux.1 Dev OneReward",
            ),
            "video_wan_dancer": (
                "Wan Dancer: Music to Dance",
                "Wan Dancer: Музыка в танец",
            ),
            "wan2.1_fun_control": ("Wan 2.1 ControlNet", "Wan 2.1 ControlNet"),
            "wan2.1_fun_inp": ("Wan 2.1 Inpainting", "Wan 2.1 инпейнтинг"),
        }
        for name, (english, russian) in expected_titles.items():
            self.assertEqual(english, en_titles[name])
            self.assertEqual(russian, ru_titles[name])

    @unittest.skipUnless(SOURCE.exists(), "pinned ComfyUI source checkout is absent")
    def test_exact_source_ast_contract_and_documented_discrepancies(self) -> None:
        source_files = {
            "nodes_slg.py": SOURCE / "comfy_extras" / "nodes_slg.py",
            "nodes_sd3.py": SOURCE / "comfy_extras" / "nodes_sd3.py",
            "nodes_differential_diffusion.py": SOURCE
            / "comfy_extras"
            / "nodes_differential_diffusion.py",
            "model_patcher.py": SOURCE / "comfy" / "model_patcher.py",
        }
        expected_classes = {
            "nodes_slg.py": {"SkipLayerGuidanceDiT", "SkipLayerGuidanceDiTSimple"},
            "nodes_sd3.py": {"SkipLayerGuidanceSD3"},
            "nodes_differential_diffusion.py": {"DifferentialDiffusion"},
        }
        for name, classes in expected_classes.items():
            tree = ast.parse(source_files[name].read_text(encoding="utf-8"))
            found = {node.name for node in tree.body if isinstance(node, ast.ClassDef)}
            self.assertTrue(classes.issubset(found))

        slg = source_files["nodes_slg.py"].read_text(encoding="utf-8")
        sd3 = source_files["nodes_sd3.py"].read_text(encoding="utf-8")
        differential = source_files["nodes_differential_diffusion.py"].read_text(
            encoding="utf-8"
        )
        patcher = source_files["model_patcher.py"].read_text(encoding="utf-8")
        self.assertIn("re.findall(r'\\d+', double_layers)", slg)
        self.assertIn("if len(double_layers) == 0 and len(single_layers) == 0:", slg)
        self.assertIn("sigma_ >= sigma_end and sigma_ <= sigma_start", slg)
        self.assertIn("if scale > 0", slg)
        self.assertIn('calc_cond_batch(model, [cond], x, sigma, model_options)', slg)
        self.assertIn("if rescaling_scale != 0:", slg)
        self.assertIn("if sigma_ >= sigma_end and sigma_ <= sigma_start and uncond is not None:", slg)
        self.assertIn(
            "return SkipLayerGuidanceDiT().execute(model=model, scale=scale, start_percent=start_percent, end_percent=end_percent, double_layers=layers)",
            sd3,
        )
        self.assertIn("binary_mask = (denoise_mask >= threshold)", differential)
        self.assertIn("if strength and strength < 1:", differential)
        self.assertIn("return binary_mask", differential)
        self.assertIn(
            'model_options["sampler_post_cfg_function"] = model_options.get("sampler_post_cfg_function", []) + [post_cfg_function]',
            patcher,
        )
        self.assertIn(
            'self.model_options["sampler_calc_cond_batch_function"] = sampler_calc_cond_batch_function',
            patcher,
        )
        self.assertIn(
            'self.model_options["denoise_mask_function"] = denoise_mask_function',
            patcher,
        )
        self.assertIn('to["patches_replace"][name][block] = patch', patcher)

    @unittest.skipUnless(SOURCE.exists(), "pinned ComfyUI source checkout is absent")
    def test_safe_exact_source_ast_probe_without_model_weights(self) -> None:
        completed = subprocess.run(
            [sys.executable, str(PROBE), str(SOURCE)],
            cwd=catalog.ROOT,
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=120,
        )
        if completed.returncode != 0:
            self.fail(completed.stderr or completed.stdout)
        result = json.loads(completed.stdout.strip().splitlines()[-1])
        self.assertEqual(
            [
                "DifferentialDiffusion",
                "SkipLayerGuidanceDiT",
                "SkipLayerGuidanceDiTSimple",
                "SkipLayerGuidanceSD3",
            ],
            result["sourceDefinitions"]["classes"],
        )

        dit = result["dit"]
        self.assertTrue(dit["emptyReturnsIdentity"])
        self.assertEqual({"double": [1, 2, 3, 4, 5], "single": [7]}, dit["parsedKeys"])
        self.assertEqual([1, 2], dit["inclusiveCallCounts"])
        self.assertEqual(2, dit["outsideCallCount"])
        self.assertEqual([4.0, 8.0, 13.0, 21.0], dit["upperResult"])
        self.assertEqual(dit["upperResult"], dit["lowerResult"])
        self.assertTrue(dit["outsideIsIdentity"])
        self.assertTrue(dit["scaleZeroBypasses"])
        self.assertTrue(dit["reversedWindowBypasses"])
        self.assertAlmostEqual(dit["conditionalStd"], dit["rescaledStd"], places=5)
        self.assertTrue(dit["replacementOverwritesSameKey"])
        self.assertTrue(dit["replacementLeavesOriginalNestedMap"])
        self.assertTrue(dit["replacementPreservesOtherNamespaces"])
        self.assertEqual(3, dit["postHookCountAfterTwo"])
        self.assertTrue(dit["preexistingPostHookPreserved"])

        simple = result["simple"]
        self.assertTrue(simple["emptyReturnsIdentity"])
        self.assertEqual([["cond", None], [None, "uncond"]], simple["upperPatterns"])
        self.assertEqual(
            [
                {"double": [], "single": []},
                {"double": [3], "single": []},
            ],
            simple["upperPatchKeys"],
        )
        self.assertEqual([11.0, 22.0], simple["upperResult"])
        self.assertEqual(2, simple["lowerCallCount"])
        self.assertEqual([["cond", "uncond"]], simple["outsidePatterns"])
        self.assertEqual([["cond", "uncond"]], simple["reversedPatterns"])
        self.assertEqual([["cond", None]], simple["cfgOnePatterns"])
        self.assertEqual([{"double": [], "single": []}], simple["cfgOnePatchKeys"])
        self.assertEqual([11.0, -100.0], simple["cfgOneResult"])
        self.assertTrue(simple["calcHookIsSingletonOverwrite"])

        self.assertEqual(
            {"double": [4, 6], "single": []},
            result["sd3"]["delegatedPatchKeys"],
        )
        differential = result["differential"]
        self.assertEqual([0.0, 1.0, 1.0], differential["binaryAtHalfway"])
        self.assertEqual(differential["binaryAtHalfway"], differential["strengthZero"])
        self.assertEqual([0.125, 0.75, 0.875], differential["halfBlend"])
        self.assertEqual([0.0, 0.0, 0.0], differential["upperBoundary"])
        self.assertEqual([1.0, 1.0, 1.0], differential["lowerBoundary"])
        self.assertEqual([0.0, 1.0, 1.0], differential["terminalSigmaAdjustment"])
        self.assertEqual(
            [0.1875, 0.625, 0.8125], differential["quarterBlendAfterOverwrite"]
        )
        self.assertTrue(differential["maskHookIsSingletonOverwrite"])
        self.assertTrue(differential["originalMaskHookPreserved"])
        self.assertEqual(
            {"postHooks": 1, "calcHookCallable": True, "maskHookCallable": True},
            result["combined"],
        )


if __name__ == "__main__":
    unittest.main()
