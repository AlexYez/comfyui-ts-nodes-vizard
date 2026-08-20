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


ARTICLE_SPECS: dict[str, dict[str, Any]] = {
    "core.primitive-string": {
        "directory": "primitive-string", "classType": "PrimitiveString",
        "fingerprint": "sha256:63ffa81d728a78e6ac9ced6518cd55270f407781cb16bffd2d66503e17014f0c",
        "type": "STRING", "recipe": "recipe.primitive-string-switch",
        "docs": {"en": "a79eff0c54431dbf18e96c373769778f23840df086edc8a3468c8bc8b246b490", "ru": "bd58f78567fde82e2e86a45c5742ba2d90afd20f533d037fb419b0de3b492081"},
    },
    "core.primitive-string-multiline": {
        "directory": "primitive-string-multiline", "classType": "PrimitiveStringMultiline",
        "fingerprint": "sha256:9a6ec20643aa2220dd3c925efe92ef9c66474b446724e1abc82e1d491c5d8ae9",
        "type": "STRING", "recipe": "recipe.multiline-string-to-number",
        "docs": {"en": "7ed4d3a5833a99b2af5e28210d3246c79cc0ca8f7d80c98ebec3f38ff4cee830", "ru": "14b8cafadf77c2e66ac55b4332d1965b07d157b2f5903d437cd6a3b7e848307d"},
    },
    "core.primitive-int": {
        "directory": "primitive-int", "classType": "PrimitiveInt",
        "fingerprint": "sha256:2665bc22715b98cc1c6dd1b7da2ff886603f7e0b666f75414e14c7b2535eb6ba",
        "type": "INT", "recipe": "recipe.primitive-numbers-preview",
        "docs": {"en": "55505acb9f590f00ffaef3518b7876baceeb0afb885ccc9d3e77b8067fea960f", "ru": "e7cc64d3ff0bd6f4b3e690d8f26267ae5dc8ecf4a2d26bae9d05565a3ceb6d52"},
    },
    "core.primitive-float": {
        "directory": "primitive-float", "classType": "PrimitiveFloat",
        "fingerprint": "sha256:684a812dc1c975c2b1eafad91ef5a5530f04dbb324a231e80f4df04f0583f1f5",
        "type": "FLOAT", "recipe": "recipe.primitive-numbers-preview",
        "docs": {"en": "424e7d14a408c7287cf4ae40c804d6f41f3e3418ae5160d5c3c4e6cc16fcbe0a", "ru": "d3b2a59ee978fc983f074c856d6d9e2b02c3d1edfd2832c8fae97a695df3d226"},
    },
    "core.primitive-boolean": {
        "directory": "primitive-boolean", "classType": "PrimitiveBoolean",
        "fingerprint": "sha256:0cff14696f31d1d7e843306790e8a25a2a9f00dd6c24ec915d1e4f64c5bb0a96",
        "type": "BOOLEAN", "recipe": "recipe.primitive-string-switch",
        "docs": {"en": "601b25ea7aa8244d8cd3c4a5f02830c6f24c811214d5856eae3e385781ff2097", "ru": "2a1b5bee739d639be86e726a965b0fc6cdc171b938a47eff6f808c0976eeb108"},
    },
}

RECIPE_DIRS = {
    "recipe.primitive-string-switch": "primitive-string-switch",
    "recipe.multiline-string-to-number": "multiline-string-to-number",
    "recipe.primitive-numbers-preview": "primitive-numbers-preview",
}
FULL_INVENTORY = catalog.CONTENT / "runtime" / "comfyui-0.32.0.object-info.json"
INVENTORY_METADATA = catalog.CONTENT / "runtime" / "comfyui-0.32.0.object-info.meta.json"
REPLACEMENTS = catalog.CONTENT / "runtime" / "comfyui-0.32.0.node-replacements.json"
SOURCE = catalog.ROOT / ".comfyui-source-0.32.0"
SOURCE_COMMIT = "c2bcbecd82ec5ae66594340b395c24ef0217b238"
WORKFLOW_WHEEL = catalog.ROOT / ".upstream-cache" / "comfyui_workflow_templates_json-0.1.42-py3-none-any.whl"
WORKFLOW_WHEEL_SHA256 = "242982d65e1c51ca03d892bc1009bb6843f457e7dfc0c20afe6438770b7a14a3"
DOCS_WHEEL = catalog.ROOT / ".upstream-cache" / "comfyui_embedded_docs-0.5.9-py3-none-any.whl"
DOCS_WHEEL_SHA256 = "30afae432a71c96aa59421d0f37388c66ff6572b8cbeee8ff045e4d5f84f896c"
PROBE = Path(__file__).with_name("primitive_nodes_synthetic_probe.py")


def article_path(spec: dict[str, Any]) -> Path:
    return catalog.CONTENT / "articles" / "core" / spec["directory"] / "manifest.json"


def recipe_path(recipe_id: str) -> Path:
    return catalog.CONTENT / "recipes" / RECIPE_DIRS[recipe_id] / "recipe.json"


def all_article_ids() -> set[str]:
    result: set[str] = set()
    for path in (catalog.CONTENT / "articles").rglob("manifest.json"):
        payload = catalog.load_json(path)
        if isinstance(payload, dict) and isinstance(payload.get("articleId"), str):
            result.add(payload["articleId"])
    return result


def graph_scopes(payload: dict[str, Any]) -> Iterator[tuple[str, dict[str, Any]]]:
    if isinstance(payload.get("nodes"), list):
        yield "root", payload
    definitions = payload.get("definitions")
    if isinstance(definitions, dict):
        for subgraph in definitions.get("subgraphs", []):
            if isinstance(subgraph, dict):
                yield "subgraph", subgraph


class PrimitiveNodesContentTests(unittest.TestCase):
    def test_articles_recipes_ledgers_honesty_and_uniqueness(self) -> None:
        article_ids = all_article_ids()
        schemas = {
            "article": catalog.load_json(catalog.CONTENT / "schemas" / "article.schema.v1.json"),
            "recipe": catalog.load_json(catalog.CONTENT / "schemas" / "recipe.schema.v1.json"),
            "fragment": catalog.load_json(catalog.CONTENT / "schemas" / "recipe-fragment.schema.v1.json"),
            "research": catalog.load_json(catalog.CONTENT / "schemas" / "article-research.schema.v1.json"),
        }
        errors: list[str] = []
        class_counts: Counter[str] = Counter()
        article_counts: Counter[str] = Counter()
        for path in (catalog.CONTENT / "articles").rglob("manifest.json"):
            payload = catalog.load_json(path)
            article_counts[payload["articleId"]] += 1
            class_counts[payload["runtimeIdentity"]["classType"]] += 1

        for article_id, spec in ARTICLE_SPECS.items():
            path = article_path(spec)
            article = catalog.load_json(path)
            self.assertEqual([], catalog.json_schema_errors(article, schemas["article"]))
            catalog.validate_article(path, article, errors)
            self.assertEqual(article_id, article["articleId"])
            self.assertEqual(1, article_counts[article_id])
            self.assertEqual(1, class_counts[spec["classType"]])
            self.assertEqual("draft", article["status"])
            self.assertFalse(article["experimental"])
            self.assertEqual("in_review", article["editorial"]["state"])
            self.assertIn("human approval pending", article["editorial"]["reviewedBy"])
            self.assertEqual([], article["runtimeIdentity"]["aliases"])
            self.assertEqual("comfy_extras.nodes_primitive", article["runtimeIdentity"]["pythonModule"])
            self.assertEqual({spec["recipe"]}, {asset["id"] for asset in article["assets"] if asset["type"] == "recipe"})
            relation_targets = set(article["relations"]["related"] + article["relations"]["alternatives"])
            self.assertTrue(relation_targets.issubset(article_ids))

            body = (path.parent / article["body"]).read_text(encoding="utf-8")
            self.assertEqual(10, len(re.findall(r"^## .+$", body, flags=re.MULTILINE)), article_id)
            self.assertNotIn("\ufffd", body)
            self.assertNotRegex(body.lower(), r"важно отметить|стоит отметить|следует отметить|в современном мире|революционн|является мощн|давайте|глубже погруз|открывает новые|может показаться|позволяет вам|подводя итог|в заключение|данная нода")

            research = catalog.load_json(catalog.CONTENT / "research" / "reviews" / f"{article_id}.json")
            self.assertEqual([], catalog.json_schema_errors(research, schemas["research"]))
            self.assertEqual(article_id, research["articleId"])
            self.assertEqual(spec["classType"], research["node"]["classType"])
            self.assertEqual("fact_checked", research["state"])
            self.assertEqual("automated_assisted", research["reviewMode"])
            self.assertTrue(research["checks"]["exampleSchemaValidated"])
            self.assertFalse(research["checks"]["exampleExecuted"])
            self.assertTrue(any("Редактор пока" in item for item in research["knownGaps"]))

        recipe_counts: Counter[str] = Counter()
        for path in (catalog.CONTENT / "recipes").rglob("recipe.json"):
            recipe_counts[catalog.load_json(path)["recipeId"]] += 1
        for recipe_id in RECIPE_DIRS:
            path = recipe_path(recipe_id)
            recipe = catalog.load_json(path)
            self.assertEqual(1, recipe_counts[recipe_id])
            self.assertEqual([], catalog.json_schema_errors(recipe, schemas["recipe"]))
            catalog.validate_recipe(path, recipe, article_ids, errors)
            self.assertNotIn("workflow", recipe)
            self.assertEqual("in_review", recipe["editorial"]["state"])
            self.assertIn("human approval pending", recipe["editorial"]["reviewedBy"])
            fragment_path = path.parent / recipe["fragment"]["path"]
            fragment = catalog.load_json(fragment_path)
            self.assertEqual([], catalog.json_schema_errors(fragment, schemas["fragment"]))
            catalog.validate_fragment(fragment_path, fragment, errors)
            self.assertEqual(recipe["fragment"]["id"], fragment["fragmentId"])
        self.assertEqual([], errors)

    def test_exact_runtime_fingerprints_schema_and_fragment_types(self) -> None:
        nodes = catalog.object_info_nodes(catalog.load_json(FULL_INVENTORY))
        metadata = catalog.load_json(INVENTORY_METADATA)
        self.assertEqual(SOURCE_COMMIT, metadata["source"]["commit"])
        self.assertEqual("0.32.0", metadata["source"]["backendVersion"])
        for article_id, spec in ARTICLE_SPECS.items():
            runtime = nodes[spec["classType"]]
            article = catalog.load_json(article_path(spec))
            self.assertEqual("comfy_extras.nodes_primitive", runtime["python_module"])
            self.assertEqual("utilities/primitive", runtime["category"])
            self.assertEqual([spec["type"]], runtime["output"])
            self.assertEqual([spec["type"]], runtime["output_name"])
            self.assertEqual(spec["type"], runtime["input"]["required"]["value"][0])
            self.assertEqual([False], runtime["output_is_list"])
            self.assertFalse(runtime["is_input_list"])
            for flag in ("output_node", "experimental", "deprecated", "dev_only", "api_node"):
                self.assertFalse(runtime[flag], (article_id, flag))
            self.assertEqual(spec["fingerprint"], catalog.schema_fingerprint(spec["classType"], runtime))
            self.assertEqual(spec["fingerprint"], article["editorial"]["schemaHash"])

        self.assertEqual({"multiline": False}, nodes["PrimitiveString"]["input"]["required"]["value"][1])
        self.assertEqual({"multiline": True}, nodes["PrimitiveStringMultiline"]["input"]["required"]["value"][1])
        self.assertEqual("Basics", nodes["PrimitiveStringMultiline"]["essentials_category"])
        self.assertIsNone(nodes["PrimitiveString"]["essentials_category"])
        self.assertEqual({"min": -9223372036854775807, "max": 9223372036854775807, "control_after_generate": "fixed"}, nodes["PrimitiveInt"]["input"]["required"]["value"][1])
        self.assertEqual({"min": -9223372036854775807, "max": 9223372036854775807, "step": 0.1}, nodes["PrimitiveFloat"]["input"]["required"]["value"][1])
        self.assertEqual({}, nodes["PrimitiveBoolean"]["input"]["required"]["value"][1])

        for recipe_id in RECIPE_DIRS:
            recipe = catalog.load_json(recipe_path(recipe_id))
            fragment = catalog.load_json(recipe_path(recipe_id).parent / recipe["fragment"]["path"])
            by_ref = {item["ref"]: item for item in fragment["nodes"]}
            for connection in fragment["connections"]:
                source = nodes[by_ref[connection["from"]]["classType"]]
                target = nodes[by_ref[connection["to"]]["classType"]]
                output_index = source["output_name"].index(connection["output"])
                source_type = source["output"][output_index]
                target_descriptor = target["input"]["required"][connection["input"]]
                target_type = target_descriptor[0]
                compatible = source_type == target_type or target_type == "*" or source_type in str(target_type).split(",")
                if target_type == "COMFY_MATCHTYPE_V3":
                    compatible = target_descriptor[1]["template"]["allowed_types"] == "*"
                self.assertTrue(compatible, (recipe_id, source_type, target_type))

    @unittest.skipUnless(SOURCE.exists(), "pinned ComfyUI source checkout is absent")
    def test_exact_pinned_source_contract(self) -> None:
        self.assertEqual(SOURCE_COMMIT, (SOURCE / ".git" / "HEAD").read_text(encoding="utf-8").strip())
        source = (SOURCE / "comfy_extras" / "nodes_primitive.py").read_text(encoding="utf-8")
        self.assertIn('node_id="PrimitiveString"', source)
        self.assertIn('search_aliases=["text", "string", "text box", "prompt"]', source)
        self.assertIn('node_id="PrimitiveStringMultiline"', source)
        self.assertIn('io.String.Input("value", multiline=True)', source)
        self.assertIn('essentials_category="Basics"', source)
        self.assertIn('node_id="PrimitiveInt"', source)
        self.assertIn('min=-sys.maxsize, max=sys.maxsize, control_after_generate=io.ControlAfterGenerate.fixed', source)
        self.assertIn('node_id="PrimitiveFloat"', source)
        self.assertIn('min=-sys.maxsize, max=sys.maxsize, step=0.1', source)
        self.assertIn('node_id="PrimitiveBoolean"', source)
        self.assertEqual(5, source.count("return io.NodeOutput(value)"))
        replacements = REPLACEMENTS.read_text(encoding="utf-8")
        for spec in ARTICLE_SPECS.values():
            self.assertNotIn(spec["classType"], replacements)

    @unittest.skipUnless(DOCS_WHEEL.exists(), "pinned embedded-docs wheel is absent")
    def test_exact_embedded_docs_hashes(self) -> None:
        self.assertEqual(DOCS_WHEEL_SHA256, hashlib.sha256(DOCS_WHEEL.read_bytes()).hexdigest())
        with zipfile.ZipFile(DOCS_WHEEL) as archive:
            for spec in ARTICLE_SPECS.values():
                for locale, digest in spec["docs"].items():
                    path = f"comfyui_embedded_docs/docs/{spec['classType']}/{locale}.md"
                    self.assertIn(path, archive.namelist())
                    self.assertEqual(digest, hashlib.sha256(archive.read(path)).hexdigest())

    @unittest.skipUnless(WORKFLOW_WHEEL.exists(), "official workflow wheel is absent")
    def test_exhaustive_census_and_exact_representative_topologies(self) -> None:
        self.assertEqual(WORKFLOW_WHEEL_SHA256, hashlib.sha256(WORKFLOW_WHEEL.read_bytes()).hexdigest())
        targets = {spec["classType"] for spec in ARTICLE_SPECS.values()}
        counts = {name: Counter() for name in targets}
        boolean_values: Counter[bool] = Counter()
        json_count = root_graph_count = subgraph_count = 0
        switch_edges: list[tuple[str, str, str, Any]] = []
        conversion_edges: list[tuple[str, str, str, Any]] = []
        with zipfile.ZipFile(WORKFLOW_WHEEL) as archive:
            members = sorted(name for name in archive.namelist() if "/templates/" in name and name.endswith(".json"))
            for member in members:
                json_count += 1
                payload = json.loads(archive.read(member).decode("utf-8"))
                if not isinstance(payload, dict):
                    continue
                if isinstance(payload.get("nodes"), list):
                    root_graph_count += 1
                definitions = payload.get("definitions")
                if isinstance(definitions, dict):
                    subgraph_count += sum(isinstance(item, dict) for item in definitions.get("subgraphs", []))
                for scope_kind, scope in graph_scopes(payload):
                    node_list = [node for node in scope.get("nodes", []) if isinstance(node, dict)]
                    by_id = {node.get("id"): node for node in node_list}
                    for node in node_list:
                        node_type = node.get("type")
                        if node_type in targets:
                            counts[node_type][scope_kind] += 1
                            counts[node_type][f"mode:{node.get('mode', 0)}"] += 1
                            if node_type == "PrimitiveBoolean" and node.get("widgets_values"):
                                boolean_values[bool(node["widgets_values"][0])] += 1
                    for link in scope.get("links", []):
                        if not (isinstance(link, list) and len(link) >= 6):
                            continue
                        source_node = by_id.get(link[1], {})
                        target_node = by_id.get(link[3], {})
                        source_type = source_node.get("type")
                        if source_type not in targets:
                            continue
                        inputs = target_node.get("inputs", [])
                        input_name = inputs[link[4]].get("name") if isinstance(inputs, list) and isinstance(link[4], int) and link[4] < len(inputs) and isinstance(inputs[link[4]], dict) else str(link[4])
                        record = (source_type, target_node.get("type"), input_name, source_node.get("widgets_values"))
                        if member.endswith("basic_switch_node.json"):
                            switch_edges.append(record)
                        if member.endswith("basic_datatype_conversion.json"):
                            conversion_edges.append(record)

        self.assertEqual((512, 496, 272), (json_count, root_graph_count, subgraph_count))
        expected = {
            "PrimitiveString": {"root": 4, "subgraph": 0, "mode:0": 4},
            "PrimitiveStringMultiline": {"root": 44, "subgraph": 37, "mode:0": 81},
            "PrimitiveInt": {"root": 27, "subgraph": 203, "mode:0": 226, "mode:4": 4},
            "PrimitiveFloat": {"root": 4, "subgraph": 128, "mode:0": 130, "mode:4": 2},
            "PrimitiveBoolean": {"root": 7, "subgraph": 78, "mode:0": 85},
        }
        for node_type, values in expected.items():
            for key, value in values.items():
                self.assertEqual(value, counts[node_type][key], (node_type, key))
        self.assertEqual(Counter({True: 44, False: 41}), boolean_values)
        self.assertEqual(2, sum(1 for edge in switch_edges if edge[:3] == ("PrimitiveString", "ComfySwitchNode", "on_true") and edge[3] == ["true"]))
        self.assertEqual(2, sum(1 for edge in switch_edges if edge[:3] == ("PrimitiveString", "ComfySwitchNode", "on_false") and edge[3] == ["false"]))
        self.assertEqual(2, sum(1 for edge in switch_edges if edge[:3] == ("PrimitiveBoolean", "ComfySwitchNode", "switch") and edge[3] == [True]))
        self.assertIn(("PrimitiveStringMultiline", "ComfyNumberConvert", "value", ["1"]), conversion_edges)
        self.assertIn(("PrimitiveInt", "PreviewAny", "source", [0, "fixed"]), conversion_edges)
        self.assertIn(("PrimitiveInt", "ComfyMathExpression", "values.a", [0, "fixed"]), conversion_edges)
        self.assertIn(("PrimitiveFloat", "PreviewAny", "source", [1.5]), conversion_edges)
        self.assertIn(("PrimitiveFloat", "ComfyMathExpression", "values.a", [1.5]), conversion_edges)

    @unittest.skipUnless(SOURCE.exists(), "pinned ComfyUI source checkout is absent")
    def test_safe_exact_source_pass_through_probe(self) -> None:
        candidates = [Path(os.environ.get("TEMP", "")) / "nodes-wizard-comfyui-v0.32.0-venv" / "Scripts" / "python.exe", Path(sys.executable)]
        python = next((candidate for candidate in candidates if candidate.exists()), None)
        if python is None:
            self.skipTest("no Python interpreter for primitive probe")
        result = subprocess.run(
            [str(python), "-X", "utf8", str(PROBE), str(SOURCE)],
            cwd=catalog.ROOT,
            text=True,
            encoding="utf-8",
            capture_output=True,
            timeout=60,
            check=False,
        )
        if result.returncode != 0:
            self.fail(result.stderr or result.stdout)
        payload = json.loads(result.stdout.strip().splitlines()[-1])
        self.assertTrue(payload["string"]["sameObjects"])
        self.assertEqual("Привет, ComfyUI 🧙", payload["string"]["values"][2])
        self.assertTrue(payload["multiline"]["sameObjects"])
        self.assertTrue(payload["multiline"]["newlinesPreserved"])
        self.assertEqual([0, -17, -sys.maxsize, sys.maxsize], payload["integer"]["values"])
        self.assertEqual(["int"] * 4, payload["integer"]["types"])
        self.assertTrue(payload["float"]["negativeZeroPreserved"])
        self.assertEqual([True, False], payload["boolean"]["values"])
        self.assertEqual(["bool", "bool"], payload["boolean"]["types"])


if __name__ == "__main__":
    unittest.main()
