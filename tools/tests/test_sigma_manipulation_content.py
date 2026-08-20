from __future__ import annotations

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
    "core.manual-sigmas": {
        "directory": "manual-sigmas",
        "classType": "ManualSigmas",
        "fingerprint": "sha256:e9fd707c890cb622e82d75a36ca7edff15b838b9d35c0dd09edb9b36a7a89217",
        "recipe": "recipe.ltx-manual-sigma-schedule",
        "experimental": True,
        "searchAliases": ["custom noise schedule", "define sigmas"],
    },
    "core.flip-sigmas": {
        "directory": "flip-sigmas",
        "classType": "FlipSigmas",
        "fingerprint": "sha256:e297e32f8d00c87ecf8c917cb544f4cda930951f61e5fb277db4c301db235565",
        "recipe": "recipe.flip-sigma-order",
        "experimental": False,
        "searchAliases": None,
    },
    "core.set-first-sigma": {
        "directory": "set-first-sigma",
        "classType": "SetFirstSigma",
        "fingerprint": "sha256:8e42ede3ffdb6f6ad84fad932ec8c26c0924c39a0f17f9eea6bc2a6f205fdb34",
        "recipe": "recipe.override-first-sigma-lotus",
        "experimental": False,
        "searchAliases": None,
    },
    "core.split-sigmas": {
        "directory": "split-sigmas",
        "classType": "SplitSigmas",
        "fingerprint": "sha256:3d1cfa7859238d91ea55d9ede17e9774af082ea3f17a91aa5d774917a473ac49",
        "recipe": "recipe.split-sigma-schedule-two-stage",
        "experimental": False,
        "searchAliases": None,
    },
}

RECIPE_DIRECTORIES = {
    "recipe.ltx-manual-sigma-schedule": "ltx-manual-sigma-schedule",
    "recipe.flip-sigma-order": "flip-sigma-order",
    "recipe.override-first-sigma-lotus": "override-first-sigma-lotus",
    "recipe.split-sigma-schedule-two-stage": "split-sigma-schedule-two-stage",
}

EXPECTED_FRAGMENT_NODES = {
    "recipe.ltx-manual-sigma-schedule": [
        ("ManualSigmas", {"sigmas": "0.909375, 0.725, 0.421875, 0.0"}),
    ],
    "recipe.flip-sigma-order": [("FlipSigmas", {})],
    "recipe.override-first-sigma-lotus": [
        ("BasicScheduler", {"scheduler": "normal", "steps": 1, "denoise": 1.0}),
        ("SetFirstSigma", {"sigma": 10000.0}),
    ],
    "recipe.split-sigma-schedule-two-stage": [
        ("BasicScheduler", {"scheduler": "simple", "steps": 8, "denoise": 1.0}),
        ("SplitSigmas", {"step": 4}),
    ],
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
WORKFLOW_WHEEL = catalog.ROOT / ".upstream-cache" / "comfyui_workflow_templates_json-0.1.42-py3-none-any.whl"
WORKFLOW_WHEEL_SHA256 = "242982d65e1c51ca03d892bc1009bb6843f457e7dfc0c20afe6438770b7a14a3"
DOCS_WHEEL = catalog.ROOT / ".upstream-cache" / "comfyui_embedded_docs-0.5.9-py3-none-any.whl"
DOCS_WHEEL_SHA256 = "30afae432a71c96aa59421d0f37388c66ff6572b8cbeee8ff045e4d5f84f896c"
SYNTHETIC_PROBE = Path(__file__).with_name("sigma_manipulation_synthetic_probe.py")


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


def normalized_links(graph: dict[str, Any]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for link in graph.get("links", []):
        if isinstance(link, list) and len(link) >= 6:
            result.append(
                {
                    "origin_id": link[1],
                    "origin_slot": link[2],
                    "target_id": link[3],
                    "target_slot": link[4],
                    "type": link[5],
                }
            )
        elif isinstance(link, dict):
            result.append(link)
    return result


def workflow_graphs(payload: dict[str, Any]) -> Iterator[tuple[str, dict[str, Any]]]:
    yield "root", payload
    definitions = payload.get("definitions")
    subgraphs = definitions.get("subgraphs", []) if isinstance(definitions, dict) else []
    for index, subgraph in enumerate(subgraphs):
        if isinstance(subgraph, dict):
            yield f"subgraph:{index}", subgraph


class SigmaManipulationContentTests(unittest.TestCase):
    def test_articles_fragment_only_recipes_and_research_validate(self) -> None:
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
            self.assertEqual("in_review", article["editorial"]["state"])
            self.assertEqual(spec["recipe"], article["assets"][0]["id"])
            self.assertEqual([], article["runtimeIdentity"]["aliases"])
            relations = article["relations"]
            targets = relations["related"] + relations["alternatives"]
            if relations["replacedBy"] is not None:
                targets.append(relations["replacedBy"])
            self.assertTrue(set(targets).issubset(article_ids))

            body = (path.parent / article["body"]).read_text(encoding="utf-8")
            self.assertEqual(EXPECTED_HEADINGS, re.findall(r"^## (.+)$", body, re.MULTILINE))
            self.assertNotIn("\ufffd", body)
            self.assertNotRegex(body, cliche_pattern)

            research = catalog.load_json(catalog.CONTENT / "research" / "reviews" / f"{article_id}.json")
            self.assertEqual([], catalog.json_schema_errors(research, research_schema))
            self.assertEqual(spec["classType"], research["node"]["classType"])
            self.assertEqual("comfy_extras.nodes_custom_sampler", research["node"]["pythonModule"])
            self.assertEqual("fact_checked", research["state"])
            self.assertEqual("automated_assisted", research["reviewMode"])
            self.assertFalse(research["checks"]["exampleExecuted"])
            self.assertTrue(research["checks"]["exampleSchemaValidated"])
            self.assertTrue(any("человеческ" in gap.lower() for gap in research["knownGaps"]))

        for recipe_id in RECIPE_DIRECTORIES:
            path = recipe_path(recipe_id)
            recipe = catalog.load_json(path)
            self.assertEqual([], catalog.json_schema_errors(recipe, recipe_schema))
            catalog.validate_recipe(path, recipe, article_ids, errors)
            self.assertEqual(recipe_id, recipe["recipeId"])
            self.assertNotIn("workflow", recipe)
            self.assertEqual("draft", recipe["editorial"]["state"])
            body = (path.parent / recipe["body"]).read_text(encoding="utf-8")
            self.assertNotRegex(body, cliche_pattern)
            fragment = catalog.load_json(path.parent / recipe["fragment"]["path"])
            self.assertEqual([], catalog.json_schema_errors(fragment, fragment_schema))
            self.assertEqual(
                EXPECTED_FRAGMENT_NODES[recipe_id],
                [(node["classType"], node["settings"]) for node in fragment["nodes"]],
            )
        self.assertEqual([], errors)

    def test_runtime_fingerprints_flags_widgets_and_fragment_ports(self) -> None:
        nodes = catalog.object_info_nodes(catalog.load_json(FULL_INVENTORY))
        for article_id, spec in ARTICLE_SPECS.items():
            runtime = dict(nodes[spec["classType"]])
            article = catalog.load_json(article_path(spec))
            self.assertEqual("comfy_extras.nodes_custom_sampler", runtime["python_module"])
            self.assertEqual("model/sampling/sigmas", runtime["category"])
            self.assertEqual(spec["fingerprint"], catalog.schema_fingerprint(spec["classType"], runtime))
            self.assertEqual(spec["fingerprint"], article["editorial"]["schemaHash"])
            self.assertEqual(spec["experimental"], bool(runtime.get("experimental", False)))
            self.assertFalse(runtime.get("deprecated", False))
            self.assertFalse(runtime.get("api_node", False))
            self.assertFalse(runtime["is_input_list"])
            self.assertEqual(spec["searchAliases"], runtime.get("search_aliases"))

        self.assertEqual(
            ["STRING", {"default": "1, 0.5", "multiline": False}],
            nodes["ManualSigmas"]["input"]["required"]["sigmas"],
        )
        self.assertEqual(["SIGMAS"], nodes["FlipSigmas"]["output"])
        self.assertEqual(
            {"default": 136.0, "min": 0.0, "max": 20000.0, "step": 0.001, "round": False},
            nodes["SetFirstSigma"]["input"]["required"]["sigma"][1],
        )
        self.assertEqual(
            {"default": 0, "min": 0, "max": 10000},
            nodes["SplitSigmas"]["input"]["required"]["step"][1],
        )
        self.assertEqual(["SIGMAS", "SIGMAS"], nodes["SplitSigmas"]["output"])
        self.assertEqual(["high_sigmas", "low_sigmas"], nodes["SplitSigmas"]["output_name"])

        for recipe_id in RECIPE_DIRECTORIES:
            path = recipe_path(recipe_id)
            recipe = catalog.load_json(path)
            fragment = catalog.load_json(path.parent / recipe["fragment"]["path"])
            refs = {node["ref"]: node for node in fragment["nodes"]}
            for external in fragment["externalInputs"]:
                runtime = dict(nodes[refs[external["to"]]["classType"]])
                self.assertEqual(external["type"], runtime_inputs(runtime)[external["input"]][0])
            for node in fragment["nodes"]:
                inputs = runtime_inputs(dict(nodes[node["classType"]]))
                for name, value in node["settings"].items():
                    self.assertIn(name, inputs)
                    options = inputs[name][1]
                    if isinstance(value, (int, float)) and not isinstance(value, bool):
                        self.assertGreaterEqual(value, options.get("min", value))
                        self.assertLessEqual(value, options.get("max", value))
                    if inputs[name][0] == "COMBO":
                        self.assertIn(value, options["options"])
            for connection in fragment["connections"]:
                source = dict(nodes[refs[connection["from"]]["classType"]])
                target = dict(nodes[refs[connection["to"]]["classType"]])
                output_index = source["output_name"].index(connection["output"])
                self.assertEqual(source["output"][output_index], runtime_inputs(target)[connection["input"]][0])

    @unittest.skipUnless(SOURCE.exists(), "pinned ComfyUI source checkout is absent")
    def test_exact_source_edge_cases_and_replacement_absence(self) -> None:
        source = (SOURCE / "comfy_extras" / "nodes_custom_sampler.py").read_text(encoding="utf-8")
        self.assertIn('re.findall(r"[-+]?(?:\\d*\\.*\\d+)", sigmas)', source)
        self.assertIn("sigmas = torch.FloatTensor(sigmas)", source)
        self.assertIn("sigmas1 = sigmas[:step + 1]", source)
        self.assertIn("sigmas2 = sigmas[step:]", source)
        self.assertIn("if len(sigmas) == 0:", source)
        self.assertIn("sigmas = sigmas.flip(0)", source)
        self.assertIn("sigmas[0] = 0.0001", source)
        self.assertIn("sigmas = sigmas.clone()", source)
        self.assertIn("sigmas[0] = sigma", source)

        replacements_text = json.dumps(catalog.load_json(REPLACEMENTS), sort_keys=True)
        for spec in ARTICLE_SPECS.values():
            self.assertNotIn(spec["classType"], replacements_text)

    @unittest.skipUnless(DOCS_WHEEL.exists(), "pinned embedded docs wheel is absent")
    def test_pinned_embedded_docs_are_present_and_bounded(self) -> None:
        self.assertEqual(DOCS_WHEEL_SHA256, hashlib.sha256(DOCS_WHEEL.read_bytes()).hexdigest())
        members = {
            "comfyui_embedded_docs/docs/ManualSigmas/en.md": "extract all numbers from this string",
            "comfyui_embedded_docs/docs/ManualSigmas/ru.md": "Любые числа, разделенные запятыми или пробелами",
            "comfyui_embedded_docs/docs/FlipSigmas/en.md": "ensuring the first value is non-zero",
            "comfyui_embedded_docs/docs/SetFirstSigma/en.md": "only the first element has been changed",
            "comfyui_embedded_docs/docs/SplitSigmas/en.md": "dividing a sequence of sigma values into two parts",
        }
        with zipfile.ZipFile(DOCS_WHEEL) as archive:
            for member, marker in members.items():
                self.assertIn(marker, archive.read(member).decode("utf-8"))

    @unittest.skipUnless(WORKFLOW_WHEEL.exists(), "official workflow wheel is absent")
    def test_exhaustive_official_census_widgets_and_topology(self) -> None:
        self.assertEqual(WORKFLOW_WHEEL_SHA256, hashlib.sha256(WORKFLOW_WHEEL.read_bytes()).hexdigest())
        targets = {spec["classType"] for spec in ARTICLE_SPECS.values()}
        records: list[dict[str, Any]] = []
        file_count = 0
        root_graph_count = 0
        with zipfile.ZipFile(WORKFLOW_WHEEL) as archive:
            for member in sorted(archive.namelist()):
                if "/templates/" not in member or not member.endswith(".json"):
                    continue
                file_count += 1
                payload = json.loads(archive.read(member).decode("utf-8"))
                if not isinstance(payload, dict):
                    continue
                if isinstance(payload.get("nodes"), list):
                    root_graph_count += 1
                for scope, graph in workflow_graphs(payload):
                    nodes = [node for node in graph.get("nodes", []) if isinstance(node, dict)]
                    by_id = {node.get("id"): node for node in nodes}
                    links = normalized_links(graph)
                    for node in nodes:
                        if node.get("type") in targets:
                            records.append(
                                {
                                    "member": member,
                                    "scope": scope,
                                    "node": node,
                                    "by_id": by_id,
                                    "links": links,
                                }
                            )
        self.assertEqual(512, file_count)
        self.assertEqual(496, root_graph_count)
        self.assertEqual(
            {"ManualSigmas": 30, "SetFirstSigma": 5, "SplitSigmas": 4},
            dict(Counter(record["node"]["type"] for record in records)),
        )

        manual = [record for record in records if record["node"]["type"] == "ManualSigmas"]
        self.assertEqual(17, len({record["member"] for record in manual}))
        self.assertTrue(all(record["scope"].startswith("subgraph:") for record in manual))
        self.assertEqual(
            Counter(
                {
                    "0.909375, 0.725, 0.421875, 0.0": 9,
                    "1.0, 0.99375, 0.9875, 0.98125, 0.975, 0.909375, 0.725, 0.421875, 0.0": 8,
                    "0.85, 0.7250, 0.4219, 0.0": 7,
                    "1., 0.99375, 0.9875, 0.98125, 0.975, 0.909375, 0.725, 0.421875, 0.0": 6,
                }
            ),
            Counter(record["node"]["widgets_values"][0] for record in manual),
        )
        for record in manual:
            node_id = record["node"]["id"]
            targets_out = [
                record["by_id"].get(link.get("target_id"), {}).get("type")
                for link in record["links"]
                if link.get("origin_id") == node_id
            ]
            self.assertEqual(["SamplerCustomAdvanced"], targets_out)

        set_first = [record for record in records if record["node"]["type"] == "SetFirstSigma"]
        self.assertTrue(all(record["scope"].startswith("subgraph:") for record in set_first))
        self.assertEqual(Counter({999.0000000000002: 3, 10000: 2}), Counter(record["node"]["widgets_values"][0] for record in set_first))
        for record in set_first:
            node_id = record["node"]["id"]
            incoming_types = [
                record["by_id"].get(link.get("origin_id"), {}).get("type")
                for link in record["links"]
                if link.get("target_id") == node_id and link.get("type") == "SIGMAS"
            ]
            outgoing_types = [
                record["by_id"].get(link.get("target_id"), {}).get("type")
                for link in record["links"]
                if link.get("origin_id") == node_id
            ]
            self.assertEqual(["BasicScheduler"], incoming_types)
            self.assertEqual(["SamplerCustomAdvanced"], outgoing_types)

        split = [record for record in records if record["node"]["type"] == "SplitSigmas"]
        self.assertEqual(Counter({"root": 2, "subgraph": 2}), Counter(record["scope"].split(":")[0] for record in split))
        self.assertEqual(Counter({3: 2, 4: 2}), Counter(record["node"]["widgets_values"][0] for record in split))
        for record in split:
            node_id = record["node"]["id"]
            scheduler_links = [
                link
                for link in record["links"]
                if link.get("target_id") == node_id
                and record["by_id"].get(link.get("origin_id"), {}).get("type") == "BasicScheduler"
            ]
            self.assertEqual(1, len(scheduler_links))
            sampler_links = [
                link
                for link in record["links"]
                if link.get("origin_id") == node_id
                and record["by_id"].get(link.get("target_id"), {}).get("type") in {"SamplerCustom", "SamplerCustomAdvanced"}
            ]
            self.assertEqual({0, 1}, {link["origin_slot"] for link in sampler_links})
            high_id = next(link["target_id"] for link in sampler_links if link["origin_slot"] == 0)
            low_id = next(link["target_id"] for link in sampler_links if link["origin_slot"] == 1)
            self.assertTrue(
                any(
                    link.get("origin_id") == high_id
                    and link.get("target_id") == low_id
                    and link.get("type") == "LATENT"
                    for link in record["links"]
                )
            )

    @unittest.skipUnless(SOURCE.exists(), "pinned ComfyUI source checkout is absent")
    def test_safe_exact_source_synthetic_tensor_probe(self) -> None:
        result = subprocess.run(
            [sys.executable, "-X", "utf8", str(SYNTHETIC_PROBE)],
            cwd=catalog.ROOT,
            text=True,
            capture_output=True,
            timeout=60,
            check=True,
        )
        payload = json.loads(result.stdout.strip().splitlines()[-1])
        self.assertEqual([1.0, 0.5, -2.25, 3.0], payload["manual"]["parsed"])
        self.assertEqual([1.0, -3.0], payload["manual"]["exponentLike"])
        self.assertEqual("ValueError", payload["manual"]["malformedError"])
        self.assertEqual([4.0, 2.0, 0.0], payload["flip"]["input"])
        self.assertAlmostEqual(0.0001, payload["flip"]["output"][0], places=10)
        self.assertTrue(payload["flip"]["copied"])
        self.assertTrue(payload["flip"]["emptyIdentity"])
        self.assertEqual([7.5, 3.0, 0.0], payload["setFirst"]["output"])
        self.assertTrue(payload["setFirst"]["cloned"])
        self.assertEqual("IndexError", payload["setFirst"]["emptyError"])
        self.assertEqual([5.0, 4.0, 3.0], payload["split"]["step2High"])
        self.assertEqual([3.0, 2.0, 0.0], payload["split"]["step2Low"])
        self.assertTrue(payload["split"]["sharedStorage"])
        self.assertEqual([1, 5], payload["split"]["step0Lengths"])
        self.assertEqual([5, 1], payload["split"]["lastLengths"])
        self.assertEqual([5, 0], payload["split"]["pastEndLengths"])
        self.assertEqual([0, 0], payload["split"]["emptyLengths"])
        self.assertEqual([1, 1], payload["split"]["singletonLengths"])


if __name__ == "__main__":
    unittest.main()
