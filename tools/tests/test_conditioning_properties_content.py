from __future__ import annotations

import hashlib
import json
import re
import unittest
import zipfile
from pathlib import Path
from typing import Any

from tools import catalog


ARTICLE_SPECS = {
    "core.conditioning-set-properties": {
        "directory": "conditioning-set-properties",
        "classType": "ConditioningSetProperties",
        "pythonModule": "comfy_extras.nodes_hooks",
        "fingerprint": "sha256:f36bfc979e497bf98459df6c2d2f89155744e0ad0957792b265a616de6354340",
        "recipe": "recipe.mask-conditioning-properties",
        "experimental": True,
    },
    "core.conditioning-set-properties-and-combine": {
        "directory": "conditioning-set-properties-and-combine",
        "classType": "ConditioningSetPropertiesAndCombine",
        "pythonModule": "comfy_extras.nodes_hooks",
        "fingerprint": "sha256:aa185e3625a58bec21e54bda4801772a4707a8d1ecfdf372b9d8636cb48c1989",
        "recipe": "recipe.combine-masked-conditioning-properties",
        "experimental": True,
    },
    "core.conditioning-timesteps-range": {
        "directory": "conditioning-timesteps-range",
        "classType": "ConditioningTimestepsRange",
        "pythonModule": "comfy_extras.nodes_hooks",
        "fingerprint": "sha256:aa979ba16798fd25d7376ccb7c623e0f1bd4388cee46e70fd403df67bc8b360c",
        "recipe": "recipe.scheduled-conditioning-properties",
        "experimental": True,
    },
    "core.conditioning-set-area-percentage-video": {
        "directory": "conditioning-set-area-percentage-video",
        "classType": "ConditioningSetAreaPercentageVideo",
        "pythonModule": "comfy_extras.nodes_video_model",
        "fingerprint": "sha256:aa81b7e3bbb6ad7e5a3b95af31a262138522241744655cf30b2f54cc2ac25ab5",
        "recipe": "recipe.video-percentage-conditioning-area",
        "experimental": False,
    },
}

RECIPE_DIRECTORIES = {
    "recipe.mask-conditioning-properties": "mask-conditioning-properties",
    "recipe.combine-masked-conditioning-properties": "combine-masked-conditioning-properties",
    "recipe.scheduled-conditioning-properties": "scheduled-conditioning-properties",
    "recipe.video-percentage-conditioning-area": "video-percentage-conditioning-area",
}

EXPECTED_FRAGMENT_NODES = {
    "recipe.mask-conditioning-properties": [
        (
            "ConditioningSetProperties",
            {"strength": 0.8, "set_cond_area": "mask bounds"},
        ),
    ],
    "recipe.combine-masked-conditioning-properties": [
        (
            "ConditioningSetPropertiesAndCombine",
            {"strength": 0.65, "set_cond_area": "mask bounds"},
        ),
    ],
    "recipe.scheduled-conditioning-properties": [
        (
            "ConditioningTimestepsRange",
            {"start_percent": 0.2, "end_percent": 0.75},
        ),
        (
            "ConditioningSetProperties",
            {"strength": 1.0, "set_cond_area": "default"},
        ),
    ],
    "recipe.video-percentage-conditioning-area": [
        (
            "ConditioningSetAreaPercentageVideo",
            {
                "width": 0.5,
                "height": 0.6,
                "temporal": 0.4,
                "x": 0.25,
                "y": 0.2,
                "z": 0.1,
                "strength": 0.9,
            },
        ),
    ],
}

FULL_INVENTORY = catalog.CONTENT / "runtime" / "comfyui-0.32.0.object-info.json"
SOURCE = catalog.ROOT / ".comfyui-source-0.32.0"
WORKFLOW_WHEEL = (
    catalog.ROOT
    / ".upstream-cache"
    / "comfyui_workflow_templates_json-0.1.42-py3-none-any.whl"
)
WORKFLOW_WHEEL_SHA256 = (
    "242982d65e1c51ca03d892bc1009bb6843f457e7dfc0c20afe6438770b7a14a3"
)
EMBEDDED_DOCS_WHEEL = (
    catalog.ROOT
    / ".upstream-cache"
    / "comfyui_embedded_docs-0.5.9-py3-none-any.whl"
)
EMBEDDED_DOCS_WHEEL_SHA256 = (
    "30afae432a71c96aa59421d0f37388c66ff6572b8cbeee8ff045e4d5f84f896c"
)


def article_path(spec: dict[str, Any]) -> Path:
    return (
        catalog.CONTENT
        / "articles"
        / "core"
        / spec["directory"]
        / "manifest.json"
    )


def recipe_path(recipe_id: str) -> Path:
    return catalog.CONTENT / "recipes" / RECIPE_DIRECTORIES[recipe_id] / "recipe.json"


def all_article_ids() -> set[str]:
    result: set[str] = set()
    for path in (catalog.CONTENT / "articles").rglob("manifest.json"):
        payload = catalog.load_json(path)
        if isinstance(payload, dict) and isinstance(payload.get("articleId"), str):
            result.add(payload["articleId"])
    return result


def runtime_input_specs(runtime: dict[str, Any]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for group in ("required", "optional"):
        values = runtime.get("input", {}).get(group, {})
        if isinstance(values, dict):
            result.update(values)
    return result


def descriptor_type(descriptor: Any) -> Any:
    if not isinstance(descriptor, list) or not descriptor:
        return None
    value = descriptor[0]
    return "COMBO" if isinstance(value, list) else value


class ConditioningPropertiesContentTests(unittest.TestCase):
    def test_articles_recipes_research_and_cross_links_validate(self) -> None:
        article_ids = all_article_ids()
        schemas = {
            "article": catalog.load_json(
                catalog.CONTENT / "schemas" / "article.schema.v1.json"
            ),
            "recipe": catalog.load_json(
                catalog.CONTENT / "schemas" / "recipe.schema.v1.json"
            ),
            "fragment": catalog.load_json(
                catalog.CONTENT / "schemas" / "recipe-fragment.schema.v1.json"
            ),
            "research": catalog.load_json(
                catalog.CONTENT / "schemas" / "article-research.schema.v1.json"
            ),
        }
        errors: list[str] = []

        for article_id, spec in ARTICLE_SPECS.items():
            path = article_path(spec)
            article = catalog.load_json(path)
            self.assertEqual([], catalog.json_schema_errors(article, schemas["article"]))
            catalog.validate_article(path, article, errors)
            self.assertEqual(article_id, article["articleId"])
            self.assertEqual("draft", article["status"])
            self.assertEqual("in_review", article["editorial"]["state"])
            self.assertIn("human approval pending", article["editorial"]["reviewedBy"])
            self.assertEqual(spec["experimental"], article["experimental"])
            self.assertEqual(
                {spec["recipe"]},
                {
                    asset["id"]
                    for asset in article["assets"]
                    if asset["type"] == "recipe"
                },
            )

            relations = article["relations"]
            targets = set(relations["related"] + relations["alternatives"])
            if relations["replacedBy"] is not None:
                targets.add(relations["replacedBy"])
            self.assertTrue(targets.issubset(article_ids), (article_id, targets))

            body = (path.parent / article["body"]).read_text(encoding="utf-8")
            self.assertEqual(
                10,
                len(re.findall(r"^## .+$", body, flags=re.MULTILINE)),
                article_id,
            )
            self.assertNotIn("\ufffd", body)
            self.assertNotRegex(
                body.lower(),
                r"важно отметить|стоит отметить|следует отметить|в современном мире|"
                r"революционн|является незаменим|является мощн|\bдавайте\b|глубже погруз|"
                r"открывает новые|может показаться|позволяет вам|подводя итог",
            )

            record_path = (
                catalog.CONTENT / "research" / "reviews" / f"{article_id}.json"
            )
            record = catalog.load_json(record_path)
            self.assertEqual([], catalog.json_schema_errors(record, schemas["research"]))
            self.assertEqual(article_id, record["articleId"])
            self.assertEqual(spec["classType"], record["node"]["classType"])
            self.assertEqual(spec["pythonModule"], record["node"]["pythonModule"])
            self.assertEqual("fact_checked", record["state"])
            self.assertEqual("automated_assisted", record["reviewMode"])
            self.assertFalse(record["checks"]["exampleExecuted"])
            self.assertTrue(record["checks"]["officialCasesInspected"])
            self.assertTrue(record["knownGaps"])

        for recipe_id in RECIPE_DIRECTORIES:
            path = recipe_path(recipe_id)
            recipe = catalog.load_json(path)
            self.assertEqual([], catalog.json_schema_errors(recipe, schemas["recipe"]))
            catalog.validate_recipe(path, recipe, article_ids, errors)
            self.assertEqual(recipe_id, recipe["recipeId"])
            self.assertNotIn("workflow", recipe)
            self.assertEqual("in_review", recipe["editorial"]["state"])
            fragment_path = path.parent / recipe["fragment"]["path"]
            fragment = catalog.load_json(fragment_path)
            self.assertEqual([], catalog.json_schema_errors(fragment, schemas["fragment"]))
            catalog.validate_fragment(fragment_path, fragment, errors)
            self.assertEqual(
                EXPECTED_FRAGMENT_NODES[recipe_id],
                [
                    (node["classType"], node["settings"])
                    for node in fragment["nodes"]
                ],
            )

        self.assertEqual([], errors)

    def test_runtime_fingerprints_ports_settings_and_required_inputs(self) -> None:
        runtime_nodes = catalog.object_info_nodes(catalog.load_json(FULL_INVENTORY))

        for article_id, spec in ARTICLE_SPECS.items():
            article = catalog.load_json(article_path(spec))
            runtime = runtime_nodes[spec["classType"]]
            self.assertEqual(spec["pythonModule"], runtime["python_module"])
            self.assertEqual(spec["pythonModule"], article["runtimeIdentity"]["pythonModule"])
            self.assertEqual(
                spec["fingerprint"],
                catalog.schema_fingerprint(spec["classType"], runtime),
                article_id,
            )
            self.assertEqual(spec["fingerprint"], article["editorial"]["schemaHash"])
            self.assertEqual(spec["experimental"], bool(runtime.get("experimental", False)))

        range_runtime = runtime_nodes["ConditioningTimestepsRange"]
        self.assertEqual(
            ["TIMESTEPS_RANGE", "BEFORE_RANGE", "AFTER_RANGE"],
            range_runtime["output_name"],
        )
        self.assertEqual(["TIMESTEPS_RANGE"] * 3, range_runtime["output"])
        properties_runtime = runtime_nodes["ConditioningSetProperties"]
        self.assertEqual(
            {"mask": ["MASK"], "hooks": ["HOOKS"], "timesteps": ["TIMESTEPS_RANGE"]},
            properties_runtime["input"]["optional"],
        )

        for recipe_id in RECIPE_DIRECTORIES:
            path = recipe_path(recipe_id)
            recipe = catalog.load_json(path)
            fragment = catalog.load_json(path.parent / recipe["fragment"]["path"])
            node_by_ref = {node["ref"]: node for node in fragment["nodes"]}
            supplied: dict[str, set[str]] = {
                ref: set(node["settings"]) for ref, node in node_by_ref.items()
            }

            for external in fragment["externalInputs"]:
                target = node_by_ref[external["to"]]
                descriptor = runtime_input_specs(runtime_nodes[target["classType"]])[
                    external["input"]
                ]
                self.assertEqual(external["type"], descriptor_type(descriptor))
                supplied[external["to"]].add(external["input"])

            for connection in fragment["connections"]:
                origin = node_by_ref[connection["from"]]
                target = node_by_ref[connection["to"]]
                origin_runtime = runtime_nodes[origin["classType"]]
                target_runtime = runtime_nodes[target["classType"]]
                output_index = origin_runtime["output_name"].index(connection["output"])
                output_type = origin_runtime["output"][output_index]
                target_descriptor = runtime_input_specs(target_runtime)[connection["input"]]
                self.assertEqual(output_type, descriptor_type(target_descriptor))
                supplied[connection["to"]].add(connection["input"])

            for ref, node in node_by_ref.items():
                runtime = runtime_nodes[node["classType"]]
                specs = runtime_input_specs(runtime)
                required = set(runtime.get("input", {}).get("required", {}))
                self.assertTrue(required.issubset(supplied[ref]), (recipe_id, ref))
                for name, value in node["settings"].items():
                    descriptor = specs[name]
                    input_type = descriptor[0]
                    constraints = (
                        descriptor[1]
                        if len(descriptor) > 1 and isinstance(descriptor[1], dict)
                        else {}
                    )
                    if isinstance(input_type, list):
                        self.assertIn(value, input_type, (recipe_id, ref, name))
                    elif input_type == "INT":
                        self.assertIsInstance(value, int)
                        self.assertNotIsInstance(value, bool)
                    elif input_type == "FLOAT":
                        self.assertIsInstance(value, (int, float))
                        self.assertNotIsInstance(value, bool)
                    elif input_type == "STRING":
                        self.assertIsInstance(value, str)
                    if "min" in constraints:
                        self.assertGreaterEqual(value, constraints["min"])
                    if "max" in constraints:
                        self.assertLessEqual(value, constraints["max"])

    @unittest.skipUnless(SOURCE.exists(), "pinned ComfyUI source checkout is absent")
    def test_articles_track_exact_pinned_source_semantics(self) -> None:
        nodes_hooks = (
            SOURCE / "comfy_extras" / "nodes_hooks.py"
        ).read_text(encoding="utf-8")
        hooks = (SOURCE / "comfy" / "hooks.py").read_text(encoding="utf-8")
        video = (
            SOURCE / "comfy_extras" / "nodes_video_model.py"
        ).read_text(encoding="utf-8")
        samplers = (SOURCE / "comfy" / "samplers.py").read_text(encoding="utf-8")
        nodes = (SOURCE / "nodes.py").read_text(encoding="utf-8")

        self.assertIn("class ConditioningSetProperties:", nodes_hooks)
        self.assertIn("class ConditioningSetPropertiesAndCombine:", nodes_hooks)
        self.assertIn("class ConditioningTimestepsRange:", nodes_hooks)
        self.assertIn("EXPERIMENTAL = True", nodes_hooks)
        self.assertIn(
            "return ((start_percent, end_percent), (0.0, start_percent), (end_percent, 1.0))",
            nodes_hooks,
        )
        self.assertIn("c = set_hooks_for_conditioning(c, hooks", hooks)
        self.assertIn("c = set_mask_for_conditioning(cond=c, mask=mask", hooks)
        self.assertIn("c = set_timesteps_for_conditioning(cond=c", hooks)
        self.assertIn("combined_conds.append(combine_conditioning([c, masked_c]))", hooks)
        self.assertIn("'mask_strength': strength", hooks)
        self.assertIn("'set_area_to_bounds': set_area_to_bounds", hooks)
        self.assertIn('"start_percent": timestep_range[0]', hooks)
        self.assertIn('"end_percent": timestep_range[1]', hooks)

        self.assertIn(
            '{"area": ("percentage", temporal, height, width, z, y, x)',
            video,
        )
        self.assertIn("max(1, round(a[d] * dims[d]))", samplers)
        self.assertIn("round(a[d + a_len] * dims[d])", samplers)
        self.assertIn("area[i] = min(input_x.shape[i + 2]", samplers)
        self.assertIn(
            'conditioning_set_values(conditioning, {"start_percent": start, "end_percent": end})',
            nodes,
        )

    @unittest.skipUnless(
        EMBEDDED_DOCS_WHEEL.exists(), "pinned embedded-docs wheel is absent"
    )
    def test_embedded_docs_paths_and_known_omissions(self) -> None:
        self.assertEqual(
            EMBEDDED_DOCS_WHEEL_SHA256,
            hashlib.sha256(EMBEDDED_DOCS_WHEEL.read_bytes()).hexdigest(),
        )
        paths = {
            class_type: f"comfyui_embedded_docs/docs/{class_type}/en.md"
            for class_type in (
                "ConditioningSetProperties",
                "ConditioningSetPropertiesAndCombine",
                "ConditioningTimestepsRange",
                "ConditioningSetAreaPercentageVideo",
            )
        }
        with zipfile.ZipFile(EMBEDDED_DOCS_WHEEL) as archive:
            docs = {
                class_type: archive.read(path).decode("utf-8")
                for class_type, path in paths.items()
            }
        self.assertTrue(all("This documentation was AI-generated" in text for text in docs.values()))
        self.assertIn("Controls the intensity", docs["ConditioningSetProperties"])
        self.assertNotIn("mask_strength", docs["ConditioningSetProperties"])
        self.assertIn(
            "applying properties from a new conditioning input to an existing conditioning input",
            docs["ConditioningSetPropertiesAndCombine"],
        )
        self.assertNotIn("cond +", docs["ConditioningSetPropertiesAndCombine"])
        self.assertIn("three distinct timestep ranges", docs["ConditioningTimestepsRange"])
        self.assertNotIn("start_percent <= end_percent", docs["ConditioningTimestepsRange"])
        self.assertIn("temporal duration", docs["ConditioningSetAreaPercentageVideo"])
        self.assertNotIn("round", docs["ConditioningSetAreaPercentageVideo"])

    @unittest.skipUnless(WORKFLOW_WHEEL.exists(), "official workflow wheel is absent")
    def test_exhaustive_official_workflow_scan_has_no_target_nodes(self) -> None:
        self.assertEqual(
            WORKFLOW_WHEEL_SHA256,
            hashlib.sha256(WORKFLOW_WHEEL.read_bytes()).hexdigest(),
        )
        target_types = {spec["classType"] for spec in ARTICLE_SPECS.values()}
        occurrences: list[tuple[str, str, str]] = []
        with zipfile.ZipFile(WORKFLOW_WHEEL) as archive:
            members = sorted(
                member
                for member in archive.namelist()
                if "/templates/" in member and member.endswith(".json")
            )
            self.assertEqual(512, len(members))
            for member in members:
                payload = json.loads(archive.read(member).decode("utf-8"))
                if not isinstance(payload, dict):
                    continue
                graphs: list[tuple[str, dict[str, Any]]] = [("root", payload)]
                definitions = payload.get("definitions")
                if isinstance(definitions, dict):
                    graphs.extend(
                        (f"subgraph:{index}", subgraph)
                        for index, subgraph in enumerate(definitions.get("subgraphs", []))
                        if isinstance(subgraph, dict)
                    )
                for scope, graph in graphs:
                    for node in graph.get("nodes", []):
                        if isinstance(node, dict) and node.get("type") in target_types:
                            occurrences.append((member, scope, node["type"]))
        self.assertEqual([], occurrences)


if __name__ == "__main__":
    unittest.main()
