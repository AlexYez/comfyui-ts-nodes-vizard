from __future__ import annotations

import hashlib
import json
import re
import unittest
import zipfile
from collections import Counter
from pathlib import Path
from typing import Any, Iterator

from tools import catalog


ARTICLE_SPECS = {
    "core.conditioning-multiply": {
        "directory": "conditioning-multiply",
        "classType": "ConditioningMultiply",
        "pythonModule": "nodes",
        "fingerprint": "sha256:dec958019ee16798fd8eb352c7afdd0e9aca965df6076be4d0d8f55bfee0499b",
        "recipe": "recipe.scale-conditioning-values",
        "experimental": False,
    },
    "core.conditioning-zero-out": {
        "directory": "conditioning-zero-out",
        "classType": "ConditioningZeroOut",
        "pythonModule": "nodes",
        "fingerprint": "sha256:ea5c74502d918aa30500e8cfbd66f680ddd20bc99c2fce334c9d30e950f5c034",
        "recipe": "recipe.zero-negative-conditioning",
        "experimental": False,
    },
    "core.conditioning-set-area-strength": {
        "directory": "conditioning-set-area-strength",
        "classType": "ConditioningSetAreaStrength",
        "pythonModule": "nodes",
        "fingerprint": "sha256:6cf077c451de6fbb202a9342de4956594b3cc88b16044d6560974989a9178659",
        "recipe": "recipe.set-conditioning-strength",
        "experimental": False,
    },
    "core.conditioning-set-default-combine": {
        "directory": "conditioning-set-default-combine",
        "classType": "ConditioningSetDefaultCombine",
        "pythonModule": "comfy_extras.nodes_hooks",
        "fingerprint": "sha256:6d4e9d5bf2edf122742493e6e734acf956112e8b3f9e2f3db03fb89d751fe92e",
        "recipe": "recipe.default-fallback-conditioning",
        "experimental": True,
    },
}

RECIPE_DIRECTORIES = {
    "recipe.scale-conditioning-values": "scale-conditioning-values",
    "recipe.zero-negative-conditioning": "zero-negative-conditioning",
    "recipe.set-conditioning-strength": "set-conditioning-strength",
    "recipe.default-fallback-conditioning": "default-fallback-conditioning",
}

EXPECTED_FRAGMENT_NODES = {
    "recipe.scale-conditioning-values": [
        ("ConditioningMultiply", {"multiplier": 0.5}),
    ],
    "recipe.zero-negative-conditioning": [
        ("CLIPTextEncode", {"text": "3d stylized style, a person smiling"}),
        ("ConditioningZeroOut", {}),
        (
            "KSampler",
            {
                "seed": 12673005598788,
                "steps": 4,
                "cfg": 1.0,
                "sampler_name": "res_multistep",
                "scheduler": "simple",
                "denoise": 1.0,
            },
        ),
    ],
    "recipe.set-conditioning-strength": [
        ("ConditioningSetAreaStrength", {"strength": 0.6}),
    ],
    "recipe.default-fallback-conditioning": [
        ("ConditioningSetDefaultCombine", {}),
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


def workflow_node_records(
    payload: dict[str, Any], member: str
) -> Iterator[dict[str, Any]]:
    workflow_id = payload.get("id")
    for node in payload.get("nodes", []):
        if isinstance(node, dict):
            yield {
                "member": member,
                "workflowId": workflow_id,
                "scope": "root",
                "node": node,
            }

    definitions = payload.get("definitions")
    subgraphs = definitions.get("subgraphs", []) if isinstance(definitions, dict) else []
    for subgraph_index, subgraph in enumerate(subgraphs):
        if not isinstance(subgraph, dict):
            continue
        for node in subgraph.get("nodes", []):
            if isinstance(node, dict):
                yield {
                    "member": member,
                    "workflowId": workflow_id,
                    "scope": "subgraph",
                    "subgraphIndex": subgraph_index,
                    "subgraphId": subgraph.get("id"),
                    "node": node,
                }


def load_official_workflows() -> tuple[dict[str, Any], list[dict[str, Any]]]:
    workflows: dict[str, Any] = {}
    records: list[dict[str, Any]] = []
    with zipfile.ZipFile(WORKFLOW_WHEEL) as archive:
        members = sorted(
            member
            for member in archive.namelist()
            if "/templates/" in member and member.endswith(".json")
        )
        for member in members:
            payload = json.loads(archive.read(member).decode("utf-8"))
            workflows[member] = payload
            if isinstance(payload, dict):
                records.extend(workflow_node_records(payload, member))
    return workflows, records


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


class ConditioningUtilityContentTests(unittest.TestCase):
    def test_articles_recipes_and_research_are_structurally_valid(self) -> None:
        article_ids = all_article_ids()
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
        errors: list[str] = []

        for article_id, spec in ARTICLE_SPECS.items():
            path = article_path(spec)
            article = catalog.load_json(path)
            self.assertEqual([], catalog.json_schema_errors(article, article_schema))
            catalog.validate_article(path, article, errors)
            self.assertEqual(article_id, article["articleId"])
            self.assertEqual("draft", article["status"])
            self.assertEqual("in_review", article["editorial"]["state"])
            self.assertIn(
                "human approval pending", article["editorial"]["reviewedBy"]
            )
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
                r"революционн|является незаменим|является мощн|давайте|глубже погруз|"
                r"открывает новые|может показаться|позволяет вам",
            )

            record_path = (
                catalog.CONTENT / "research" / "reviews" / f"{article_id}.json"
            )
            record = catalog.load_json(record_path)
            self.assertEqual([], catalog.json_schema_errors(record, research_schema))
            self.assertEqual(article_id, record["articleId"])
            self.assertEqual(spec["classType"], record["node"]["classType"])
            self.assertEqual(spec["pythonModule"], record["node"]["pythonModule"])
            self.assertEqual("fact_checked", record["state"])
            self.assertEqual("automated_assisted", record["reviewMode"])
            self.assertFalse(record["checks"]["exampleExecuted"])
            self.assertTrue(record["checks"]["officialCasesInspected"])
            self.assertTrue(record["knownGaps"])
            self.assertNotEqual("human_approved", record["state"])

        for recipe_id in RECIPE_DIRECTORIES:
            path = recipe_path(recipe_id)
            recipe = catalog.load_json(path)
            self.assertEqual([], catalog.json_schema_errors(recipe, recipe_schema))
            catalog.validate_recipe(path, recipe, article_ids, errors)
            self.assertEqual(recipe_id, recipe["recipeId"])
            self.assertNotIn("workflow", recipe)
            self.assertEqual("in_review", recipe["editorial"]["state"])
            fragment_path = path.parent / recipe["fragment"]["path"]
            fragment = catalog.load_json(fragment_path)
            self.assertEqual([], catalog.json_schema_errors(fragment, fragment_schema))
            catalog.validate_fragment(fragment_path, fragment, errors)
            self.assertEqual(
                EXPECTED_FRAGMENT_NODES[recipe_id],
                [
                    (node["classType"], node["settings"])
                    for node in fragment["nodes"]
                ],
            )

        self.assertEqual([], errors)

    def test_runtime_identity_fingerprints_and_fragment_ports_match_inventory(self) -> None:
        runtime_nodes = catalog.object_info_nodes(catalog.load_json(FULL_INVENTORY))
        for article_id, spec in ARTICLE_SPECS.items():
            article = catalog.load_json(article_path(spec))
            runtime = runtime_nodes[spec["classType"]]
            self.assertEqual(spec["classType"], article["runtimeIdentity"]["classType"])
            self.assertEqual(runtime["python_module"], spec["pythonModule"])
            self.assertEqual(spec["pythonModule"], article["runtimeIdentity"]["pythonModule"])
            self.assertEqual(
                spec["fingerprint"],
                catalog.schema_fingerprint(spec["classType"], runtime),
                article_id,
            )
            self.assertEqual(spec["fingerprint"], article["editorial"]["schemaHash"])
            self.assertEqual(spec["experimental"], bool(runtime.get("experimental", False)))

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
                input_descriptor = runtime_input_specs(target_runtime)[connection["input"]]
                self.assertEqual(output_type, descriptor_type(input_descriptor))
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
    def test_articles_track_exact_pinned_implementations(self) -> None:
        nodes_source = (SOURCE / "nodes.py").read_text(encoding="utf-8")
        node_helpers_source = (SOURCE / "node_helpers.py").read_text(encoding="utf-8")
        hooks_source = (SOURCE / "comfy" / "hooks.py").read_text(encoding="utf-8")
        nodes_hooks_source = (
            SOURCE / "comfy_extras" / "nodes_hooks.py"
        ).read_text(encoding="utf-8")
        samplers_source = (SOURCE / "comfy" / "samplers.py").read_text(
            encoding="utf-8"
        )

        self.assertIn("values[\"pooled_output\"] = pooled_output * multiplier", nodes_source)
        self.assertIn("t[0] * multiplier", nodes_source)
        self.assertIn('conditioning_set_values(conditioning, {"strength": strength})', nodes_source)
        self.assertIn('d["conditioning_lyrics"] = torch.zeros_like(conditioning_lyrics)', nodes_source)
        self.assertIn("n = [torch.zeros_like(t[0]), d]", nodes_source)
        self.assertIn("n = [t[0], t[1].copy()]", node_helpers_source)

        self.assertIn("class ConditioningSetDefaultAndCombine:", nodes_hooks_source)
        self.assertIn("NodeId = 'ConditioningSetDefaultCombine'", nodes_hooks_source)
        self.assertIn("EXPERIMENTAL = True", nodes_hooks_source)
        self.assertIn("new_c = conditioning_set_values(new_c, {'default': True})", hooks_source)
        self.assertIn("combine_conditioning([c, new_c])", hooks_source)
        self.assertIn("torch.nn.functional.relu(mult, inplace=True)", samplers_source)
        self.assertIn("p = p._replace(mult=mult)", samplers_source)

    @unittest.skipUnless(
        EMBEDDED_DOCS_WHEEL.exists(), "pinned embedded-docs wheel is absent"
    )
    def test_embedded_docs_paths_and_documented_discrepancies(self) -> None:
        self.assertEqual(
            EMBEDDED_DOCS_WHEEL_SHA256,
            hashlib.sha256(EMBEDDED_DOCS_WHEEL.read_bytes()).hexdigest(),
        )
        with zipfile.ZipFile(EMBEDDED_DOCS_WHEEL) as archive:
            multiply = archive.read(
                "comfyui_embedded_docs/docs/ConditioningMultiply/en.md"
            ).decode("utf-8")
            zero = archive.read(
                "comfyui_embedded_docs/docs/ConditioningZeroOut/en.md"
            ).decode("utf-8")
            strength = archive.read(
                "comfyui_embedded_docs/docs/ConditioningSetAreaStrength/en.md"
            ).decode("utf-8")
            default = archive.read(
                "comfyui_embedded_docs/docs/ConditioningSetDefaultAndCombine/en.md"
            ).decode("utf-8")
            self.assertIn("both the main conditioning tensor and the pooled output", multiply)
            self.assertIn("zeroes out the 'pooled_output'", zero)
            self.assertNotIn("conditioning_lyrics", zero)
            self.assertNotIn("main conditioning tensor", zero)
            self.assertIn("modify the strength attribute", strength)
            self.assertNotIn("spatial multiplier", strength)
            self.assertIn("fallback or base", default)
            self.assertNotIn("ReLU", default)
            self.assertNotIn(
                "comfyui_embedded_docs/docs/ConditioningSetDefaultCombine/en.md",
                archive.namelist(),
            )

    @unittest.skipUnless(WORKFLOW_WHEEL.exists(), "official workflow wheel is absent")
    def test_exhaustive_workflow_usage_and_zero_out_topology(self) -> None:
        self.assertEqual(
            WORKFLOW_WHEEL_SHA256,
            hashlib.sha256(WORKFLOW_WHEEL.read_bytes()).hexdigest(),
        )
        workflows, records = load_official_workflows()
        self.assertEqual(512, len(workflows))

        target_types = {spec["classType"] for spec in ARTICLE_SPECS.values()}
        target_records = [
            record for record in records if record["node"].get("type") in target_types
        ]
        counts = Counter(record["node"]["type"] for record in target_records)
        self.assertEqual({"ConditioningZeroOut": 53}, dict(counts))

        zero_records = [
            record
            for record in target_records
            if record["node"]["type"] == "ConditioningZeroOut"
        ]
        self.assertEqual(47, len({record["member"] for record in zero_records}))
        self.assertEqual(
            Counter({"subgraph": 36, "root": 17}),
            Counter(record["scope"] for record in zero_records),
        )
        self.assertTrue(all(record["node"].get("widgets_values") == [] for record in zero_records))

        member = next(
            name for name in workflows if name.endswith("/basic_switch_node.json")
        )
        workflow = workflows[member]
        self.assertEqual("30235234-3bb4-42cc-9e1c-33ad1bba0192", workflow["id"])
        subgraph = workflow["definitions"]["subgraphs"][0]
        nodes = {node["id"]: node for node in subgraph["nodes"]}
        links = {link["id"]: link for link in subgraph["links"]}
        self.assertEqual("CLIPTextEncode", nodes[56]["type"])
        self.assertEqual("ConditioningZeroOut", nodes[54]["type"])
        self.assertEqual("KSampler", nodes[58]["type"])
        self.assertEqual(["3d stylized style, a person smiling"], nodes[56]["widgets_values"])
        self.assertEqual([], nodes[54]["widgets_values"])
        self.assertEqual(
            [12673005598788, "randomize", 4, 1, "res_multistep", "simple", 1],
            nodes[58]["widgets_values"],
        )
        self.assertEqual((56, 54, "CONDITIONING"), (
            links[38]["origin_id"], links[38]["target_id"], links[38]["type"]
        ))
        self.assertEqual((54, 58, "CONDITIONING"), (
            links[44]["origin_id"], links[44]["target_id"], links[44]["type"]
        ))
        self.assertEqual("negative", nodes[58]["inputs"][2]["name"])
        self.assertEqual(44, nodes[58]["inputs"][2]["link"])

        recipe = catalog.load_json(recipe_path("recipe.zero-negative-conditioning"))
        fragment = catalog.load_json(
            recipe_path("recipe.zero-negative-conditioning").parent
            / recipe["fragment"]["path"]
        )
        fragment_nodes = {node["classType"]: node for node in fragment["nodes"]}
        self.assertEqual(
            nodes[56]["widgets_values"][0],
            fragment_nodes["CLIPTextEncode"]["settings"]["text"],
        )
        expected_sampler = {
            "seed": nodes[58]["widgets_values"][0],
            "steps": nodes[58]["widgets_values"][2],
            "cfg": nodes[58]["widgets_values"][3],
            "sampler_name": nodes[58]["widgets_values"][4],
            "scheduler": nodes[58]["widgets_values"][5],
            "denoise": nodes[58]["widgets_values"][6],
        }
        self.assertEqual(expected_sampler, fragment_nodes["KSampler"]["settings"])
        self.assertEqual(
            [
                {
                    "from": "negative_source",
                    "output": "CONDITIONING",
                    "to": "zero",
                    "input": "conditioning",
                },
                {
                    "from": "zero",
                    "output": "CONDITIONING",
                    "to": "sample",
                    "input": "negative",
                },
            ],
            fragment["connections"],
        )


if __name__ == "__main__":
    unittest.main()
