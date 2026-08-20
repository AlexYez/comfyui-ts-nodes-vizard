from __future__ import annotations

import hashlib
import json
import unittest
import zipfile
from pathlib import Path

from tools import catalog


FRONTEND_COMMIT = "6d6af63c00f132cd25dc29307fc56bd2c094fa22"
WORKFLOW_WHEEL_SHA256 = "242982d65e1c51ca03d892bc1009bb6843f457e7dfc0c20afe6438770b7a14a3"
WORKFLOW_WHEEL = (
    catalog.ROOT
    / ".upstream-cache"
    / "comfyui_workflow_templates_json-0.1.42-py3-none-any.whl"
)
EXPECTED = {
    "MarkdownNote": {
        "article": "frontend.markdown-note",
        "recipe": "markdown-workflow-note",
        "officialWorkflow": "4125c6df-9bca-430d-8e85-7cff9cc592d4",
    },
    "Note": {
        "article": "frontend.note",
        "recipe": "plain-workflow-note",
        "officialWorkflow": "7d136772-0647-4a55-bd62-7e9c36c41a0b",
    },
    "PrimitiveNode": {
        "article": "frontend.primitive-node",
        "recipe": "shared-widget-value",
        "officialWorkflow": "88bcf757-1298-432f-885a-db5ab88cf224",
    },
    "Reroute": {
        "article": "frontend.reroute",
        "recipe": "route-with-reroute",
        "officialWorkflow": "58f78c8c-912a-4108-8626-4348be1fab82",
    },
}


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


class FrontendContentTests(unittest.TestCase):
    def test_frontend_batch_validates_independently_and_cross_links_resolve(self) -> None:
        article_schema = read_json(
            catalog.CONTENT / "schemas" / "article.schema.v1.json"
        )
        recipe_schema = read_json(
            catalog.CONTENT / "schemas" / "recipe.schema.v1.json"
        )
        fragment_schema = read_json(
            catalog.CONTENT / "schemas" / "recipe-fragment.schema.v1.json"
        )
        research_schema = read_json(
            catalog.CONTENT / "schemas" / "article-research.schema.v1.json"
        )
        article_ids = {expected["article"] for expected in EXPECTED.values()}
        recipe_ids = {
            f"recipe.{expected['recipe']}" for expected in EXPECTED.values()
        }
        errors: list[str] = []

        for expected in EXPECTED.values():
            article_path = (
                catalog.CONTENT
                / "articles"
                / "frontend"
                / expected["article"].removeprefix("frontend.")
                / "manifest.json"
            )
            article = read_json(article_path)
            catalog.validate_article(article_path, article, errors)
            errors.extend(
                catalog.json_schema_errors(
                    article, article_schema, article_path.as_posix()
                )
            )
            relations = article["relations"]
            related_ids = {
                *relations["related"],
                *relations["alternatives"],
                *([relations["replacedBy"]] if relations["replacedBy"] else []),
            }
            self.assertTrue(related_ids.issubset(article_ids))
            self.assertIn(
                f"recipe.{expected['recipe']}",
                {asset["id"] for asset in article["assets"] if asset["type"] == "recipe"},
            )
            self.assertTrue(
                {
                    asset["id"]
                    for asset in article["assets"]
                    if asset["type"] == "recipe"
                }.issubset(recipe_ids)
            )

            recipe_path = (
                catalog.CONTENT
                / "recipes"
                / expected["recipe"]
                / "recipe.json"
            )
            recipe = read_json(recipe_path)
            catalog.validate_recipe(recipe_path, recipe, article_ids, errors)
            errors.extend(
                catalog.json_schema_errors(recipe, recipe_schema, recipe_path.as_posix())
            )
            fragment_path = recipe_path.parent / recipe["fragment"]["path"]
            fragment = read_json(fragment_path)
            errors.extend(
                catalog.json_schema_errors(
                    fragment, fragment_schema, fragment_path.as_posix()
                )
            )

            record_path = (
                catalog.CONTENT
                / "research"
                / "reviews"
                / f"{expected['article']}.json"
            )
            record = read_json(record_path)
            errors.extend(
                catalog.json_schema_errors(
                    record, research_schema, record_path.as_posix()
                )
            )
            self.assertEqual(article["articleId"], record["articleId"])
            self.assertEqual(
                article["runtimeIdentity"]["classType"], record["node"]["classType"]
            )
            self.assertEqual(
                article["runtimeIdentity"]["pythonModule"],
                record["node"]["pythonModule"],
            )

        workflow_path = (
            catalog.CONTENT / "workflows" / "frontend-utilities-lab.workflow.json"
        )
        catalog.validate_workflow(workflow_path, read_json(workflow_path), errors)
        self.assertEqual([], errors)

    def test_full_frontend_inventory_has_one_draft_article_and_example_each(self) -> None:
        inventory = read_json(
            catalog.CONTENT
            / "runtime"
            / "comfyui-frontend-1.48.7.frontend-inventory.json"
        )
        inventory_types = {
            item["classType"] for item in inventory["nodes"] if not item.get("dev_only")
        }
        manifests = {
            manifest["runtimeIdentity"]["classType"]: manifest
            for path in sorted((catalog.CONTENT / "articles" / "frontend").glob("*/manifest.json"))
            for manifest in [read_json(path)]
        }

        self.assertEqual(set(EXPECTED), inventory_types)
        self.assertEqual(inventory_types, set(manifests))
        for class_type, expected in EXPECTED.items():
            with self.subTest(class_type=class_type):
                article = manifests[class_type]
                self.assertEqual(expected["article"], article["articleId"])
                self.assertEqual("draft", article["status"])
                self.assertEqual("in_review", article["editorial"]["state"])
                self.assertIn("human approval pending", article["editorial"]["reviewedBy"])
                self.assertEqual("comfyui_frontend", article["runtimeIdentity"]["pythonModule"])
                frontend_urls = [
                    source["url"]
                    for source in article["sources"]
                    if "ComfyUI_frontend" in source["url"]
                ]
                self.assertTrue(frontend_urls)
                self.assertTrue(all(FRONTEND_COMMIT in url for url in frontend_urls))

                recipe_root = catalog.CONTENT / "recipes" / expected["recipe"]
                recipe = read_json(recipe_root / "recipe.json")
                fragment = read_json(recipe_root / "fragment.json")
                self.assertEqual([expected["article"]], recipe["articleIds"])
                self.assertIn(
                    class_type,
                    {node["classType"] for node in fragment["nodes"]},
                )
                self.assertEqual("workflow.frontend-utilities-lab", recipe["workflow"]["id"])

    def test_research_records_pin_source_workflow_and_unexecuted_example(self) -> None:
        for class_type, expected in EXPECTED.items():
            with self.subTest(class_type=class_type):
                record = read_json(
                    catalog.CONTENT
                    / "research"
                    / "reviews"
                    / f"{expected['article']}.json"
                )
                self.assertEqual(class_type, record["node"]["classType"])
                self.assertEqual(FRONTEND_COMMIT, record["baseline"]["sourceCommit"])
                self.assertEqual("fact_checked", record["state"])
                self.assertEqual("automated_assisted", record["reviewMode"])
                self.assertTrue(record["checks"]["exampleSchemaValidated"])
                self.assertFalse(record["checks"]["exampleExecuted"])
                self.assertTrue(record["knownGaps"])
                self.assertIn(
                    expected["officialWorkflow"],
                    {workflow["id"] for workflow in record["evidence"]["workflows"]},
                )
                self.assertTrue(
                    all(
                        FRONTEND_COMMIT in location["url"]
                        for location in record["evidence"]["sourceLocations"]
                    )
                )

    def test_shared_workflow_contains_all_frontend_types_and_consistent_links(self) -> None:
        workflow = read_json(
            catalog.CONTENT / "workflows" / "frontend-utilities-lab.workflow.json"
        )
        nodes = {node["id"]: node for node in workflow["nodes"]}
        self.assertTrue(set(EXPECTED).issubset({node["type"] for node in nodes.values()}))
        self.assertEqual(0.4, workflow["version"])

        for link_id, origin_id, origin_slot, target_id, target_slot, _ in workflow["links"]:
            with self.subTest(link=link_id):
                self.assertIn(link_id, nodes[origin_id]["outputs"][origin_slot]["links"])
                self.assertEqual(link_id, nodes[target_id]["inputs"][target_slot]["link"])

        primitive = next(node for node in nodes.values() if node["type"] == "PrimitiveNode")
        self.assertEqual("INT", primitive["outputs"][0]["type"])
        self.assertEqual({1, 2}, set(primitive["outputs"][0]["links"]))
        reroute = next(node for node in nodes.values() if node["type"] == "Reroute")
        self.assertEqual("*", reroute["inputs"][0]["type"])
        self.assertEqual("LATENT", reroute["outputs"][0]["type"])
        self.assertNotIn("reroutes", workflow["extra"])


@unittest.skipUnless(
    WORKFLOW_WHEEL.exists(),
    "download the pinned workflow-templates-json 0.1.42 wheel to .upstream-cache",
)
class OfficialFrontendWorkflowEvidenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.archive = zipfile.ZipFile(WORKFLOW_WHEEL)
        actual = hashlib.sha256(WORKFLOW_WHEEL.read_bytes()).hexdigest()
        if actual != WORKFLOW_WHEEL_SHA256:
            raise AssertionError(f"unexpected workflow wheel SHA-256: {actual}")

    @classmethod
    def tearDownClass(cls) -> None:
        cls.archive.close()

    def load_template(self, name: str) -> dict:
        member = f"comfyui_workflow_templates_json/templates/{name}.json"
        return json.loads(self.archive.read(member))

    def test_exhaustive_official_usage_counts(self) -> None:
        node_counts = {class_type: 0 for class_type in EXPECTED}
        workflow_members = {class_type: set() for class_type in EXPECTED}
        template_members = [
            member
            for member in self.archive.namelist()
            if "/templates/" in member and member.endswith(".json")
        ]
        self.assertEqual(512, len(template_members))

        for member in template_members:
            workflow = json.loads(self.archive.read(member))
            if not isinstance(workflow, dict):
                continue
            graphs = [workflow]
            definitions = workflow.get("definitions")
            if isinstance(definitions, dict):
                subgraphs = definitions.get("subgraphs", [])
                if isinstance(subgraphs, list):
                    graphs.extend(subgraph for subgraph in subgraphs if isinstance(subgraph, dict))
            for graph in graphs:
                for node in graph.get("nodes", []):
                    class_type = node.get("type")
                    if class_type in EXPECTED:
                        node_counts[class_type] += 1
                        workflow_members[class_type].add(member)

        self.assertEqual(
            {
                "MarkdownNote": 573,
                "Note": 95,
                "PrimitiveNode": 31,
                "Reroute": 41,
            },
            node_counts,
        )
        self.assertEqual(
            {
                "MarkdownNote": 316,
                "Note": 49,
                "PrimitiveNode": 17,
                "Reroute": 18,
            },
            {
                class_type: len(members)
                for class_type, members in workflow_members.items()
            },
        )

    def test_representative_serializations_match_pinned_official_wheel(self) -> None:
        markdown = self.load_template("3d_hunyuan3d-v2.1")
        self.assertEqual("4125c6df-9bca-430d-8e85-7cff9cc592d4", markdown["id"])
        node = next(node for node in markdown["nodes"] if node["id"] == 15)
        self.assertEqual("MarkdownNote", node["type"])
        self.assertEqual([], node["inputs"])
        self.assertEqual([], node["outputs"])
        self.assertIn("checkpoints", node["widgets_values"][0])

        note = self.load_template("api_bytedance_seedream_5_0_layer_separation")
        self.assertEqual("7d136772-0647-4a55-bd62-7e9c36c41a0b", note["id"])
        node = next(node for node in note["nodes"] if node["id"] == 26)
        self.assertEqual("Note", node["type"])
        self.assertEqual("Note: Edit layers", node["title"])
        self.assertIn("Nodes2.0", node["widgets_values"][0])

        primitive = self.load_template("sdxl_simple_example")
        self.assertEqual("88bcf757-1298-432f-885a-db5ab88cf224", primitive["id"])
        node = next(node for node in primitive["nodes"] if node["id"] == 45)
        self.assertEqual("PrimitiveNode", node["type"])
        self.assertEqual({38, 41}, set(node["outputs"][0]["links"]))
        self.assertEqual({"name": "steps"}, node["outputs"][0]["widget"])
        self.assertEqual([25, "fixed"], node["widgets_values"])

        reroute = self.load_template("templates-all_in_one-image_edit_models")
        self.assertEqual("58f78c8c-912a-4108-8626-4348be1fab82", reroute["id"])
        node = next(node for node in reroute["nodes"] if node["id"] == 135)
        self.assertEqual("Reroute", node["type"])
        self.assertEqual("*", node["inputs"][0]["type"])
        self.assertEqual("IMAGE", node["outputs"][0]["type"])
        self.assertEqual(7, len(node["outputs"][0]["links"]))


if __name__ == "__main__":
    unittest.main()
