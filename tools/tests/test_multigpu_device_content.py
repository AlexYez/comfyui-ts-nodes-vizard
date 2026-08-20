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
from tools.tests.multigpu_device_synthetic_probe import run_probe


SOURCE = catalog.ROOT / ".comfyui-source-0.32.0"
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
    "core.multigpu-work-units": {
        "directory": "multigpu-work-units",
        "classType": "MultiGPU_WorkUnits",
        "fingerprint": "sha256:40bf0932ad255a6085ec723c3013db294d9edf2883365b0d0347f351221539ea",
        "displayName": "MultiGPU CFG Split",
        "input": "model",
        "inputType": "MODEL",
        "output": "MODEL",
        "asset": "recipe.multigpu-cfg-split",
    },
    "core.select-model-device": {
        "directory": "select-model-device",
        "classType": "SelectModelDevice",
        "fingerprint": "sha256:5aff18a14cb2f9f6e37646632f13a6e087c12f0314ed9979e5cc90eabc146227",
        "displayName": "Select Model Device",
        "input": "model",
        "inputType": "MODEL",
        "output": "MODEL",
        "asset": "recipe.multigpu-cfg-split",
    },
    "core.select-clip-device": {
        "directory": "select-clip-device",
        "classType": "SelectCLIPDevice",
        "fingerprint": "sha256:fb99fbc2ad455a81ba9499c53d7a9f743780e6b5668834ff83397414211e4d3a",
        "displayName": "Select CLIP Device",
        "input": "clip",
        "inputType": "CLIP",
        "output": "CLIP",
        "asset": "recipe.select-clip-device",
    },
    "core.select-vae-device": {
        "directory": "select-vae-device",
        "classType": "SelectVAEDevice",
        "fingerprint": "sha256:20a2a0c9f63e53884a53d56d17f28557b678453a7015e334a73f2cb24b19886e",
        "displayName": "Select VAE Device",
        "input": "vae",
        "inputType": "VAE",
        "output": "VAE",
        "asset": "recipe.select-vae-device",
    },
}
TARGET_TYPES = {spec["classType"] for spec in ARTICLE_SPECS.values()}
DISPLAY_NAMES = {spec["displayName"] for spec in ARTICLE_SPECS.values()}

RECIPE_SPECS = {
    "recipe.multigpu-cfg-split": {
        "directory": "multigpu-cfg-split",
        "articles": {"core.multigpu-work-units", "core.select-model-device"},
        "external": [("model", "MODEL", "select_model", "model")],
        "nodes": {
            "select_model": ("SelectModelDevice", {"device": "gpu:0"}),
            "split": ("MultiGPU_WorkUnits", {"max_gpus": 2}),
        },
        "connections": [("select_model", "MODEL", "split", "model")],
    },
    "recipe.select-clip-device": {
        "directory": "select-clip-device",
        "articles": {"core.select-clip-device"},
        "external": [("clip", "CLIP", "select_clip", "clip")],
        "nodes": {
            "select_clip": ("SelectCLIPDevice", {"device": "gpu:1"}),
        },
        "connections": [],
    },
    "recipe.select-vae-device": {
        "directory": "select-vae-device",
        "articles": {"core.select-vae-device"},
        "external": [("vae", "VAE", "select_vae", "vae")],
        "nodes": {
            "select_vae": ("SelectVAEDevice", {"device": "gpu:1"}),
        },
        "connections": [],
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
    "comfyui_embedded_docs/docs/MultiGPU_WorkUnits/en.md": "c08011627a9cdaebb7a7b27312af74a2b73912cbee7c695b66ba42d71df12807",
    "comfyui_embedded_docs/docs/MultiGPU_WorkUnits/ru.md": "aeb1b8ac151cef7de279b0d18b8573af8ed9be5ac981597fea73783c6ac61be1",
    "comfyui_embedded_docs/docs/SelectModelDevice/en.md": "32568246a508ea99e541d94e5c2c81d90763242de3f24a190f66ec02a142babf",
    "comfyui_embedded_docs/docs/SelectModelDevice/ru.md": "f47fdc08471394a3b83241dbe4f24f8da4e44690e172d315d84cb366ca511333",
    "comfyui_embedded_docs/docs/SelectCLIPDevice/en.md": "8ca0f385a10768381180049549bbd42e02f3cf216a2deb6372f2421f8793d3c0",
    "comfyui_embedded_docs/docs/SelectCLIPDevice/ru.md": "b960652ef263e7427ce69f9f807b94547bee589a399b5b59dc65c36d34973d39",
    "comfyui_embedded_docs/docs/SelectVAEDevice/en.md": "8254a38eebcc0332a19681c8b3a25d57195aa91cac6b0abaef5945a05c0499f2",
    "comfyui_embedded_docs/docs/SelectVAEDevice/ru.md": "2284b163637f153907d49b7998360dcedbbf55cf289ea3b62a58b8b5ac378157",
}

BASELINE = {
    "comfyui": "0.32.0",
    "frontend": "1.48.7",
    "sourceCommit": "c2bcbecd82ec5ae66594340b395c24ef0217b238",
    "embeddedDocs": "0.5.9",
    "workflowTemplatesJson": "0.1.42",
}


def _article_path(spec: dict[str, Any]) -> Path:
    return catalog.CONTENT / "articles" / "core" / spec["directory"] / "manifest.json"


def _recipe_path(spec: dict[str, Any]) -> Path:
    return catalog.CONTENT / "recipes" / spec["directory"] / "recipe.json"


def _all_article_ids() -> set[str]:
    result: set[str] = set()
    for path in (catalog.CONTENT / "articles").rglob("manifest.json"):
        payload = catalog.load_json(path)
        if isinstance(payload, dict) and isinstance(payload.get("articleId"), str):
            result.add(payload["articleId"])
    return result


def _all_recipe_ids() -> set[str]:
    result: set[str] = set()
    for path in (catalog.CONTENT / "recipes").rglob("recipe.json"):
        payload = catalog.load_json(path)
        if isinstance(payload, dict) and isinstance(payload.get("recipeId"), str):
            result.add(payload["recipeId"])
    return result


def _pending_human_review(value: Any) -> bool:
    text = json.dumps(value, ensure_ascii=False).lower()
    return ("human" in text and "pending" in text) or (
        "редактор" in text and "не проверил" in text
    ) or ("человеч" in text and any(word in text for word in ("ожида", "не выполн")))


def _walk_strings(value: Any) -> Iterator[str]:
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for nested in value.values():
            yield from _walk_strings(nested)
    elif isinstance(value, list):
        for nested in value:
            yield from _walk_strings(nested)


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
    return [value for value in values if isinstance(value, dict)]


def _normalized_links(graph: dict[str, Any]) -> list[tuple[Any, ...]]:
    result: list[tuple[Any, ...]] = []
    for link in graph.get("links", []):
        if isinstance(link, list) and len(link) >= 6:
            result.append(tuple(link[:6]))
        elif isinstance(link, dict):
            result.append(
                tuple(
                    link.get(name)
                    for name in (
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


def _index_entries(payload: list[Any]) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    for category in payload:
        if isinstance(category, dict):
            entries.extend(
                entry
                for entry in category.get("templates", [])
                if isinstance(entry, dict)
            )
    return entries


class MultiGPUDeviceContentTests(unittest.TestCase):
    def test_articles_recipes_ledgers_and_crosslinks(self) -> None:
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
        article_ids = _all_article_ids()
        recipe_ids = _all_recipe_ids()
        article_errors: list[str] = []
        recipe_errors: list[str] = []

        for article_id, spec in ARTICLE_SPECS.items():
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
                    "pythonModule": "comfy_extras.nodes_multigpu",
                    "packageId": "comfy-core",
                    "origin": "backend",
                    "aliases": [],
                },
                article["runtimeIdentity"],
            )
            self.assertTrue(_pending_human_review(article["editorial"]["reviewedBy"]))
            self.assertIn(spec["asset"], {asset["id"] for asset in article["assets"]})
            self.assertIn(spec["asset"], recipe_ids)

            relation_targets = set(
                article["relations"]["related"] + article["relations"]["alternatives"]
            )
            if article["relations"]["replacedBy"] is not None:
                relation_targets.add(article["relations"]["replacedBy"])
            self.assertTrue(
                relation_targets.issubset(article_ids),
                (article_id, relation_targets - article_ids),
            )

            body = (path.parent / article["body"]).read_text(encoding="utf-8")
            self.assertEqual(
                EXPECTED_H2,
                re.findall(r"^## (.+)$", body, flags=re.MULTILINE),
                article_id,
            )
            self.assertIn("Редактор пока не проверил материал вручную.", body)
            self.assertNotIn("\ufffd", body)

            ledger_path = catalog.CONTENT / "research" / "reviews" / f"{article_id}.json"
            ledger = catalog.load_json(ledger_path)
            self.assertEqual([], catalog.json_schema_errors(ledger, research_schema), article_id)
            self.assertEqual(article_id, ledger["articleId"])
            self.assertEqual(spec["classType"], ledger["node"]["classType"])
            self.assertEqual("comfy_extras.nodes_multigpu", ledger["node"]["pythonModule"])
            self.assertEqual("backend", ledger["node"]["origin"])
            self.assertEqual("fact_checked", ledger["state"])
            self.assertEqual("automated_assisted", ledger["reviewMode"])
            self.assertEqual(BASELINE, ledger["baseline"])
            for check in (
                "implementationRead",
                "runtimeCompared",
                "officialCasesInspected",
                "exampleSchemaValidated",
                "russianEdited",
                "factsRecheckedAfterEditing",
            ):
                self.assertTrue(ledger["checks"][check], f"{article_id}: {check}")
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
            for marker in ("512", "496", "272", "0", spec["classType"]):
                self.assertIn(marker, workflow_text, (article_id, marker))

        runtime = catalog.object_info_nodes(catalog.load_json(INVENTORY))
        for recipe_id, spec in RECIPE_SPECS.items():
            path = _recipe_path(spec)
            recipe = catalog.load_json(path)
            self.assertEqual([], catalog.json_schema_errors(recipe, recipe_schema), recipe_id)
            catalog.validate_recipe(path, recipe, article_ids, recipe_errors)
            self.assertEqual(recipe_id, recipe["recipeId"])
            self.assertEqual(spec["articles"], set(recipe["articleIds"]))
            self.assertEqual("in_review", recipe["editorial"]["state"])
            self.assertNotIn("workflow", recipe)
            self.assertTrue(_pending_human_review(recipe["editorial"]["reviewedBy"]))
            recipe_body = (path.parent / recipe["body"]).read_text(encoding="utf-8")
            self.assertIn("Редактор пока не проверил материал вручную.", recipe_body)

            fragment_path = path.parent / recipe["fragment"]["path"]
            fragment = catalog.load_json(fragment_path)
            self.assertEqual(
                [], catalog.json_schema_errors(fragment, fragment_schema), recipe_id
            )
            catalog.validate_fragment(fragment_path, fragment, recipe_errors)
            nodes = {node["ref"]: node for node in fragment["nodes"]}
            self.assertEqual(set(spec["nodes"]), set(nodes))
            for ref, (class_type, settings) in spec["nodes"].items():
                self.assertEqual(class_type, nodes[ref]["classType"])
                self.assertEqual(settings, nodes[ref]["settings"])

            actual_external = [
                (item["id"], item["type"], item["to"], item["input"])
                for item in fragment["externalInputs"]
            ]
            self.assertEqual(spec["external"], actual_external)
            actual_connections = [
                (item["from"], item["output"], item["to"], item["input"])
                for item in fragment["connections"]
            ]
            self.assertEqual(spec["connections"], actual_connections)

            for _, external_type, target_ref, input_name in actual_external:
                target = dict(runtime[nodes[target_ref]["classType"]])
                self.assertEqual(external_type, _runtime_inputs(target)[input_name][0])
            for source_ref, output_name, target_ref, input_name in actual_connections:
                source = dict(runtime[nodes[source_ref]["classType"]])
                target = dict(runtime[nodes[target_ref]["classType"]])
                output_index = source["output_name"].index(output_name)
                self.assertEqual(
                    source["output"][output_index],
                    _runtime_inputs(target)[input_name][0],
                )

        self.assertEqual([], article_errors)
        self.assertEqual([], recipe_errors)

    def test_runtime_fingerprints_flags_dynamic_snapshot_and_replacements(self) -> None:
        runtime = catalog.object_info_nodes(catalog.load_json(INVENTORY))
        for spec in ARTICLE_SPECS.values():
            class_type = spec["classType"]
            definition = dict(runtime[class_type])
            self.assertEqual("comfy_extras.nodes_multigpu", definition["python_module"])
            self.assertEqual("advanced/multigpu", definition["category"])
            self.assertEqual(spec["displayName"], definition["display_name"])
            self.assertEqual(None, definition["search_aliases"])
            self.assertEqual(
                [spec["input"], "max_gpus" if class_type == "MultiGPU_WorkUnits" else "device"],
                definition["input_order"]["required"],
            )
            self.assertEqual(spec["inputType"], definition["input"]["required"][spec["input"]][0])
            self.assertEqual([spec["output"]], definition["output"])
            self.assertEqual([spec["output"]], definition["output_name"])
            self.assertEqual([False], definition["output_is_list"])
            self.assertEqual([None], definition["output_tooltips"])
            for flag in (
                "deprecated",
                "experimental",
                "dev_only",
                "api_node",
                "output_node",
                "has_intermediate_output",
                "is_input_list",
            ):
                self.assertFalse(definition[flag], (class_type, flag))
            self.assertEqual(
                spec["fingerprint"], catalog.schema_fingerprint(class_type, definition)
            )

        work_units = dict(runtime["MultiGPU_WorkUnits"])
        self.assertEqual(
            ["INT", {"default": 2, "min": 1, "step": 1}],
            work_units["input"]["required"]["max_gpus"],
        )
        self.assertNotIn("max", work_units["input"]["required"]["max_gpus"][1])
        self.assertEqual(
            ["COMBO", {"multiselect": False, "options": ["default", "cpu"]}],
            runtime["SelectModelDevice"]["input"]["required"]["device"],
        )
        self.assertEqual(
            ["COMBO", {"multiselect": False, "options": ["default", "cpu"]}],
            runtime["SelectCLIPDevice"]["input"]["required"]["device"],
        )
        self.assertEqual(
            ["COMBO", {"multiselect": False, "options": ["default"]}],
            runtime["SelectVAEDevice"]["input"]["required"]["device"],
        )

        replacement_strings = set(_walk_strings(catalog.load_json(REPLACEMENTS)))
        self.assertTrue(TARGET_TYPES.isdisjoint(replacement_strings))

    def test_pinned_source_and_embedded_docs_discrepancies(self) -> None:
        self.assertEqual(
            "c2bcbecd82ec5ae66594340b395c24ef0217b238",
            (SOURCE / ".git" / "HEAD").read_text(encoding="ascii").strip(),
        )
        nodes = (SOURCE / "comfy_extras" / "nodes_multigpu.py").read_text(
            encoding="utf-8"
        )
        multigpu = (SOURCE / "comfy" / "multigpu.py").read_text(encoding="utf-8")
        management = (SOURCE / "comfy" / "model_management.py").read_text(
            encoding="utf-8"
        )
        patcher = (SOURCE / "comfy" / "model_patcher.py").read_text(encoding="utf-8")
        samplers = (SOURCE / "comfy" / "samplers.py").read_text(encoding="utf-8")

        for class_type in TARGET_TYPES:
            self.assertIn(f'node_id="{class_type}"', nodes)
        self.assertIn(
            "create_multigpu_deepclones(model, max_gpus, reuse_loaded=True)", nodes
        )
        self.assertIn("full_extra_devices[:max_gpus-1]", multigpu)
        self.assertIn("allowed_devices.add(model.load_device)", multigpu)
        self.assertIn("if not getattr(lm, \"is_multigpu_base_clone\", False)", multigpu)
        self.assertIn("cached_patcher_init is not initialized", patcher)
        self.assertIn("conds_per_device = max(1, math.ceil(total_conds / len(devices)))", samplers)
        self.assertIn(".to(output_device).chunk(batch_chunks)", samplers)
        self.assertIn("TODO: non-NVIDIA support", samplers)
        self.assertIn('options = ["default", "cpu"]', management)
        self.assertIn("if len(devices) > 1:", management)
        self.assertIn('options.append(f"gpu:{i}")', management)
        self.assertIn('return [o for o in get_gpu_device_options() if o != "cpu"]', management)
        self.assertNotIn('"gpu:7"', management)

        nodes_tree = ast.parse(nodes)
        class_text: dict[str, str] = {}
        for node in nodes_tree.body:
            if isinstance(node, ast.ClassDef) and node.name in {
                "SelectCLIPDeviceNode",
                "SelectVAEDeviceNode",
            }:
                class_text[node.name] = ast.get_source_segment(nodes, node) or ""
        self.assertNotIn("cond_stage_model =", class_text["SelectCLIPDeviceNode"])
        self.assertIn(
            "vae.first_stage_model = vae.patcher.model",
            class_text["SelectVAEDeviceNode"],
        )

        self.assertEqual(DOCS_SHA256, hashlib.sha256(DOCS_WHEEL.read_bytes()).hexdigest())
        with zipfile.ZipFile(DOCS_WHEEL) as archive:
            self.assertIsNone(archive.testzip())
            pages: dict[str, str] = {}
            for member, expected_hash in DOC_PAGE_HASHES.items():
                raw = archive.read(member)
                self.assertEqual(expected_hash, hashlib.sha256(raw).hexdigest(), member)
                pages[member] = raw.decode("utf-8")
            bundled_multigpu_json = [
                name
                for name in archive.namelist()
                if "/docs/MultiGPU_WorkUnits/" in name and name.endswith(".json")
            ]
        self.assertEqual([], bundled_multigpu_json)

        for member, text in pages.items():
            marker = "AI-generated" if member.endswith("/en.md") else "создана с помощью ИИ"
            self.assertIn(marker, text)
        multigpu_en = pages["comfyui_embedded_docs/docs/MultiGPU_WorkUnits/en.md"]
        multigpu_ru = pages["comfyui_embedded_docs/docs/MultiGPU_WorkUnits/ru.md"]
        self.assertIn("1.95x", multigpu_en)
        self.assertIn("Ampere+", multigpu_en)
        self.assertIn("CFG в workflow должно быть больше 1", multigpu_ru)
        self.assertNotIn("1.95x", nodes + multigpu + samplers)
        self.assertNotIn("Ampere+", nodes + multigpu + samplers)
        for class_type in ("SelectModelDevice", "SelectCLIPDevice", "SelectVAEDevice"):
            self.assertIn(
                '"gpu:7"',
                pages[f"comfyui_embedded_docs/docs/{class_type}/en.md"],
            )
        self.assertIn(
            "`устройство`",
            pages["comfyui_embedded_docs/docs/SelectVAEDevice/ru.md"],
        )
        self.assertNotIn(
            "cached_patcher_init",
            pages["comfyui_embedded_docs/docs/SelectCLIPDevice/en.md"],
        )

    def test_workflow_wheel_exhaustive_zero_census_and_index_titles(self) -> None:
        self.assertEqual(
            WORKFLOW_SHA256, hashlib.sha256(WORKFLOW_WHEEL.read_bytes()).hexdigest()
        )
        json_count = 0
        root_count = 0
        subgraph_count = 0
        root_node_count = 0
        subgraph_node_count = 0
        raw_occurrences: Counter[str] = Counter()
        exact_scalar_occurrences: Counter[str] = Counter()
        substring_scalar_occurrences: Counter[str] = Counter()
        direct: list[dict[str, Any]] = []
        generic_multigpu: list[tuple[str, str]] = []

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
                    if "multigpu" in scalar.lower():
                        generic_multigpu.append((member, scalar))
                if not isinstance(payload, dict) or not isinstance(payload.get("nodes"), list):
                    continue

                root_count += 1
                root_node_count += len(payload["nodes"])
                graphs = [("root", payload)] + [
                    ("subgraph", graph) for graph in _subgraphs(payload)
                ]
                subgraph_count += len(graphs) - 1
                subgraph_node_count += sum(
                    len(graph.get("nodes", [])) for _, graph in graphs[1:]
                )
                for scope, graph in graphs:
                    nodes_by_id = {
                        node.get("id"): node
                        for node in graph.get("nodes", [])
                        if isinstance(node, dict)
                    }
                    links = _normalized_links(graph)
                    for node in nodes_by_id.values():
                        if node.get("type") not in TARGET_TYPES:
                            continue
                        incoming = [link for link in links if link[3] == node.get("id")]
                        outgoing = [link for link in links if link[1] == node.get("id")]
                        direct.append(
                            {
                                "member": member,
                                "workflowUuid": payload.get("id"),
                                "scope": scope,
                                "graphUuid": graph.get("id"),
                                "type": node.get("type"),
                                "mode": node.get("mode"),
                                "widgets": node.get("widgets_values"),
                                "properties": node.get("properties"),
                                "incoming": incoming,
                                "outgoing": outgoing,
                            }
                        )

            english_index = json.loads(
                archive.read("comfyui_workflow_templates_json/templates/index.json")
            )
            russian_index = json.loads(
                archive.read("comfyui_workflow_templates_json/templates/index.ru.json")
            )

        self.assertEqual((512, 496, 272), (json_count, root_count, subgraph_count))
        self.assertEqual((4083, 4037, 8120), (
            root_node_count,
            subgraph_node_count,
            root_node_count + subgraph_node_count,
        ))
        self.assertEqual([], direct)
        self.assertEqual(Counter(), raw_occurrences)
        self.assertEqual(Counter(), exact_scalar_occurrences)
        self.assertEqual(Counter(), substring_scalar_occurrences)
        self.assertEqual(38, len(generic_multigpu))
        self.assertEqual(19, len({member for member, _ in generic_multigpu}))
        self.assertEqual(
            {"LTXVSequenceParallelMultiGPUPatcher"},
            {value for _, value in generic_multigpu},
        )

        for index in (english_index, russian_index):
            entries = _index_entries(index)
            self.assertEqual(496, len(entries))
            self.assertEqual(496, len({entry["name"] for entry in entries}))
            serialized = json.dumps(entries, ensure_ascii=False)
            for needle in TARGET_TYPES | DISPLAY_NAMES:
                self.assertNotIn(needle, serialized)

    def test_exact_source_model_free_probe(self) -> None:
        result = run_probe(SOURCE)
        self.assertFalse(result["workflowExampleExecuted"])
        self.assertIn("no hardware query", result["hardware"])
        self.assertEqual(["default", "cpu"], result["deviceOptions"]["oneDevice"])
        self.assertEqual(["default"], result["deviceOptions"]["oneDeviceVAE"])
        self.assertEqual(
            ["default", "cpu", "gpu:0", "gpu:1", "gpu:2"],
            result["deviceOptions"]["threeDevices"],
        )
        self.assertEqual(
            ["default", "gpu:0", "gpu:1", "gpu:2"],
            result["deviceOptions"]["threeDevicesVAE"],
        )
        self.assertEqual(
            {
                "default": None,
                "cpu": "cpu",
                "gpu:1": "cuda:1",
                "gpu:9": None,
                "gpu:bad": None,
            },
            result["deviceOptions"]["resolved"],
        )

        work_units = result["workUnits"]
        self.assertTrue(work_units["inputUnchanged"])
        self.assertEqual("cuda:1", work_units["primary"])
        self.assertEqual(["cuda:0"], work_units["maxTwoExtras"])
        self.assertEqual(["cuda:1"], work_units["prunedToTwoExtras"])
        self.assertEqual([], work_units["prunedToOneExtras"])
        self.assertTrue(work_units["reusedEligibleLoadedModel"])
        self.assertTrue(work_units["rejectedUnflaggedLoadedModel"])
        self.assertTrue(work_units["missingFactoryRaised"])

        model = result["selectModel"]
        self.assertEqual(
            {
                "load": "cuda:1",
                "offload": "cpu",
                "freshModel": True,
                "computeDtype": "torch.float32",
            },
            model["gpu"],
        )
        self.assertEqual({"load": "cuda:0", "offload": "cpu"}, model["default"])
        self.assertEqual(
            {"load": "cpu", "offload": "cpu", "inputRoutingUnchanged": True},
            model["cpu"],
        )
        self.assertEqual([], model["collisionExtras"])
        self.assertEqual("cuda:0", model["missingFactoryLoad"])
        self.assertEqual("cuda:0", model["dynamicCpuMissingFactoryLoad"])
        self.assertEqual(
            {
                "clonedWrapper": True,
                "sameModel": True,
                "load": "cuda:0",
            },
            model["unavailable"],
        )

        clip = result["selectCLIP"]
        self.assertEqual("cuda:1", clip["gpuLoad"])
        self.assertEqual("cuda:0", clip["defaultLoad"])
        self.assertEqual("cpu", clip["cpuLoad"])
        self.assertEqual("cuda:0", clip["unavailableLoad"])
        self.assertEqual("cuda:0", clip["missingFactoryLoad"])
        self.assertTrue(clip["freshPatcherModel"])
        self.assertFalse(clip["wrapperPointsToPatcherModel"])
        self.assertTrue(clip["wrapperStillPointsToInputModel"])

        vae = result["selectVAE"]
        self.assertEqual(
            {
                "load": "cuda:1",
                "offload": "cpu",
                "wrapperDevice": "cuda:1",
                "modelSynchronized": True,
            },
            vae["gpu"],
        )
        self.assertEqual(
            {
                "load": "cuda:0",
                "offload": "cpu",
                "wrapperDevice": "cuda:0",
                "modelSynchronized": True,
            },
            vae["default"],
        )
        self.assertEqual(
            {"load": "cuda:0", "offload": "cuda:1", "wrapperDevice": "cuda:0"},
            vae["cpuRejected"],
        )
        self.assertEqual("cuda:0", vae["unavailableLoad"])
        self.assertEqual("cuda:0", vae["missingFactoryLoad"])
        self.assertTrue(vae["inputUnchanged"])


if __name__ == "__main__":
    unittest.main()
