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
    "core.comfy-switch-node": {
        "directory": "comfy-switch-node", "classType": "ComfySwitchNode", "category": "utilities/logic", "experimental": True,
        "fingerprint": "sha256:5b1b6bfa1169b017578109479557bd7f550d587fea84e9be5dd9883f8ff95d1d", "recipe": "recipe.primitive-string-switch",
        "docs": {"en": "984de1ce69c4f445e3eb7ec06513f1b5f4ac44b9ab6dadfe665f3a36bd53fd05", "ru": "0b4e30967d5966b2e6516bf36942ef594df31266d19248ab2c3e996f6c8c2a42"},
    },
    "core.custom-combo": {
        "directory": "custom-combo", "classType": "CustomCombo", "category": "utilities", "experimental": True,
        "fingerprint": "sha256:a72d13e60317055d6ef853111400f9812b9accb89bcc9a18b974ca952cf90b91", "recipe": "recipe.custom-combo-json-key",
        "docs": {"en": "560ea9f41b0875e646159c30270e87fe1175d7e05562cdf0771004f1a3502d47", "ru": "323c04e48d10cf8cad0c539a216bba88b01982b6b8c1e0b675989aef4960238f"},
    },
    "core.comfy-not-node": {
        "directory": "comfy-not-node", "classType": "ComfyNotNode", "category": "utilities/logic", "experimental": False,
        "fingerprint": "sha256:18bb5ae1583dafa6a042f27e7596da3af73b0b67459730dc4a2315bba71f0f83", "recipe": "recipe.logic-truthiness-gates",
        "docs": {"en": "fe3a52d421e5216e26548cf333bdf5b890e3b76e936e9c6e8c585946da9db749", "ru": "c4de5ccdb7e37432ebefe0a4ed890a9976ca6373d396cadc8226b05e9f8a4411"},
    },
    "core.comfy-and-node": {
        "directory": "comfy-and-node", "classType": "ComfyAndNode", "category": "utilities/logic", "experimental": False,
        "fingerprint": "sha256:85cd91a84a4dd0b24b61ad7097f7c56af5cc474d0cf1838b28c26c42c00f4f60", "recipe": "recipe.logic-truthiness-gates",
        "docs": {"en": "43ca3531b180bdcf6625a85c0179f44e8e258b1c0b4329b44d5e021e414b9868", "ru": "95162c3df5e94519848abeedb7cf2bd587aaf236fbeb3f939a91f98efb857b7a"},
    },
    "core.comfy-or-node": {
        "directory": "comfy-or-node", "classType": "ComfyOrNode", "category": "utilities/logic", "experimental": False,
        "fingerprint": "sha256:12beabb411fb027b05f7a8b6faa7f29c0366a6f7b217df488ff8ca922b443733", "recipe": "recipe.logic-truthiness-gates",
        "docs": {"en": "e258c2f5d3798b8595730bc353b3c8ce819164cd7e16212e2b13a2063a15aa77", "ru": "bb39eb07bb73b45751eaa803ff4de3a4454baf7ea5b04c5b6fa950024eb57eaf"},
    },
}

RECIPE_DIRS = {
    "recipe.primitive-string-switch": "primitive-string-switch",
    "recipe.custom-combo-json-key": "custom-combo-json-key",
    "recipe.logic-truthiness-gates": "logic-truthiness-gates",
}
FULL_INVENTORY = catalog.CONTENT / "runtime" / "comfyui-0.32.0.object-info.json"
INVENTORY_METADATA = catalog.CONTENT / "runtime" / "comfyui-0.32.0.object-info.meta.json"
REPLACEMENTS = catalog.CONTENT / "runtime" / "comfyui-0.32.0.node-replacements.json"
SOURCE = catalog.ROOT / ".comfyui-source-0.32.0"
FRONTEND = catalog.ROOT / ".frontend-source-1.48.7"
SOURCE_COMMIT = "c2bcbecd82ec5ae66594340b395c24ef0217b238"
FRONTEND_COMMIT = "6d6af63c00f132cd25dc29307fc56bd2c094fa22"
WORKFLOW_WHEEL = catalog.ROOT / ".upstream-cache" / "comfyui_workflow_templates_json-0.1.42-py3-none-any.whl"
WORKFLOW_WHEEL_SHA256 = "242982d65e1c51ca03d892bc1009bb6843f457e7dfc0c20afe6438770b7a14a3"
DOCS_WHEEL = catalog.ROOT / ".upstream-cache" / "comfyui_embedded_docs-0.5.9-py3-none-any.whl"
DOCS_WHEEL_SHA256 = "30afae432a71c96aa59421d0f37388c66ff6572b8cbeee8ff045e4d5f84f896c"
PROBE = Path(__file__).with_name("logic_nodes_synthetic_probe.py")


def article_path(spec: dict[str, Any]) -> Path:
    return catalog.CONTENT / "articles" / "core" / spec["directory"] / "manifest.json"


def recipe_path(recipe_id: str) -> Path:
    return catalog.CONTENT / "recipes" / RECIPE_DIRS[recipe_id] / "recipe.json"


def all_article_ids() -> set[str]:
    return {catalog.load_json(path)["articleId"] for path in (catalog.CONTENT / "articles").rglob("manifest.json")}


def graph_scopes(payload: dict[str, Any]) -> Iterator[tuple[str, dict[str, Any]]]:
    if isinstance(payload.get("nodes"), list):
        yield "root", payload
    definitions = payload.get("definitions")
    if isinstance(definitions, dict):
        for subgraph in definitions.get("subgraphs", []):
            if isinstance(subgraph, dict):
                yield "subgraph", subgraph


def link_fields(link: Any) -> tuple[Any, int, Any, int, Any] | None:
    if isinstance(link, list) and len(link) >= 6:
        return link[1], link[2], link[3], link[4], link[5]
    if isinstance(link, dict):
        return link.get("origin_id"), link.get("origin_slot", 0), link.get("target_id"), link.get("target_slot", 0), link.get("type")
    return None


class LogicNodesContentTests(unittest.TestCase):
    def test_articles_recipes_ledgers_honesty_and_cross_links(self) -> None:
        article_ids = all_article_ids()
        schemas = {
            "article": catalog.load_json(catalog.CONTENT / "schemas" / "article.schema.v1.json"),
            "recipe": catalog.load_json(catalog.CONTENT / "schemas" / "recipe.schema.v1.json"),
            "fragment": catalog.load_json(catalog.CONTENT / "schemas" / "recipe-fragment.schema.v1.json"),
            "research": catalog.load_json(catalog.CONTENT / "schemas" / "article-research.schema.v1.json"),
        }
        errors: list[str] = []
        for article_id, spec in ARTICLE_SPECS.items():
            path = article_path(spec)
            article = catalog.load_json(path)
            self.assertEqual([], catalog.json_schema_errors(article, schemas["article"]))
            catalog.validate_article(path, article, errors)
            self.assertEqual(article_id, article["articleId"])
            self.assertEqual("draft", article["status"])
            self.assertEqual(spec["experimental"], article["experimental"])
            self.assertEqual("in_review", article["editorial"]["state"])
            self.assertIn("human approval pending", article["editorial"]["reviewedBy"])
            self.assertEqual([], article["runtimeIdentity"]["aliases"])
            self.assertEqual({spec["recipe"]}, {asset["id"] for asset in article["assets"] if asset["type"] == "recipe"})
            relation_targets = set(article["relations"]["related"] + article["relations"]["alternatives"])
            self.assertTrue(relation_targets.issubset(article_ids), (article_id, relation_targets - article_ids))
            body = (path.parent / article["body"]).read_text(encoding="utf-8")
            self.assertEqual(10, len(re.findall(r"^## .+$", body, flags=re.MULTILINE)), article_id)
            self.assertNotIn("\ufffd", body)
            self.assertNotRegex(body.lower(), r"важно отметить|стоит отметить|следует отметить|в современном мире|революционн|является мощн|давайте|глубже погруз|открывает новые|может показаться|позволяет вам|подводя итог|в заключение|данная нода")

            research = catalog.load_json(catalog.CONTENT / "research" / "reviews" / f"{article_id}.json")
            self.assertEqual([], catalog.json_schema_errors(research, schemas["research"]))
            self.assertEqual("fact_checked", research["state"])
            self.assertEqual("automated_assisted", research["reviewMode"])
            self.assertTrue(research["checks"]["exampleSchemaValidated"])
            self.assertFalse(research["checks"]["exampleExecuted"])
            self.assertTrue(any("Редактор пока" in item for item in research["knownGaps"]))

        for recipe_id in RECIPE_DIRS:
            path = recipe_path(recipe_id)
            recipe = catalog.load_json(path)
            self.assertEqual([], catalog.json_schema_errors(recipe, schemas["recipe"]))
            catalog.validate_recipe(path, recipe, article_ids, errors)
            self.assertNotIn("workflow", recipe)
            self.assertEqual("in_review", recipe["editorial"]["state"])
            self.assertIn("human approval pending", recipe["editorial"]["reviewedBy"])
            fragment_path = path.parent / recipe["fragment"]["path"]
            fragment = catalog.load_json(fragment_path)
            self.assertEqual([], catalog.json_schema_errors(fragment, schemas["fragment"]))
            catalog.validate_fragment(fragment_path, fragment, errors)
        self.assertEqual([], errors)

    def test_exact_runtime_fingerprints_dynamic_contracts_and_fragment_types(self) -> None:
        nodes = catalog.object_info_nodes(catalog.load_json(FULL_INVENTORY))
        metadata = catalog.load_json(INVENTORY_METADATA)
        self.assertEqual(SOURCE_COMMIT, metadata["source"]["commit"])
        for article_id, spec in ARTICLE_SPECS.items():
            runtime = nodes[spec["classType"]]
            article = catalog.load_json(article_path(spec))
            self.assertEqual("comfy_extras.nodes_logic", runtime["python_module"])
            self.assertEqual(spec["category"], runtime["category"])
            self.assertEqual(spec["experimental"], runtime["experimental"])
            self.assertFalse(runtime["deprecated"])
            self.assertFalse(runtime["dev_only"])
            self.assertFalse(runtime["api_node"])
            self.assertFalse(runtime["output_node"])
            self.assertFalse(runtime["is_input_list"])
            self.assertEqual(spec["fingerprint"], catalog.schema_fingerprint(spec["classType"], runtime), article_id)
            self.assertEqual(spec["fingerprint"], article["editorial"]["schemaHash"])

        switch = nodes["ComfySwitchNode"]
        self.assertEqual("BOOLEAN", switch["input"]["required"]["switch"][0])
        for name in ("on_false", "on_true"):
            descriptor = switch["input"]["required"][name]
            self.assertEqual("COMFY_MATCHTYPE_V3", descriptor[0])
            self.assertTrue(descriptor[1]["lazy"])
            self.assertEqual({"template_id": "switch", "allowed_types": "*"}, descriptor[1]["template"])
        self.assertEqual(["COMFY_MATCHTYPE_V3"], switch["output"])
        self.assertEqual(["switch"], switch["output_matchtypes"])

        combo = nodes["CustomCombo"]
        self.assertEqual(["STRING", "INT"], combo["output"])
        self.assertEqual(["STRING", "INDEX"], combo["output_name"])
        self.assertEqual(["COMBO", {"multiselect": False, "options": []}], combo["input"]["required"]["choice"])
        self.assertEqual(["BOOLEAN"], nodes["ComfyNotNode"]["output"])
        self.assertEqual("*", nodes["ComfyNotNode"]["input"]["required"]["value"][0])
        for class_type in ("ComfyAndNode", "ComfyOrNode"):
            descriptor = nodes[class_type]["input"]["required"]["values"]
            self.assertEqual("COMFY_AUTOGROW_V3", descriptor[0])
            self.assertEqual(("value", 1, 10), (descriptor[1]["template"]["prefix"], descriptor[1]["template"]["min"], descriptor[1]["template"]["max"]))
            self.assertEqual("*", descriptor[1]["template"]["input"]["required"]["value"][0])

        for recipe_id in RECIPE_DIRS:
            recipe = catalog.load_json(recipe_path(recipe_id))
            fragment = catalog.load_json(recipe_path(recipe_id).parent / recipe["fragment"]["path"])
            by_ref = {node["ref"]: node for node in fragment["nodes"]}
            for connection in fragment["connections"]:
                source = nodes[by_ref[connection["from"]]["classType"]]
                target = nodes[by_ref[connection["to"]]["classType"]]
                source_type = source["output"][source["output_name"].index(connection["output"])]
                input_name = connection["input"]
                if "." in input_name:
                    base, child = input_name.split(".", 1)
                    descriptor = target["input"]["required"][base]
                    self.assertTrue(child.startswith(descriptor[1]["template"]["prefix"]))
                    target_type = descriptor[1]["template"]["input"]["required"]["value"][0]
                else:
                    descriptor = target["input"]["required"][input_name]
                    target_type = descriptor[0]
                compatible = source_type == target_type or target_type == "*" or source_type in str(target_type).split(",")
                if target_type == "COMFY_MATCHTYPE_V3":
                    compatible = descriptor[1]["template"]["allowed_types"] == "*"
                self.assertTrue(compatible, (recipe_id, source_type, target_type))

    @unittest.skipUnless(SOURCE.exists(), "pinned ComfyUI source checkout is absent")
    def test_exact_backend_and_frontend_source_contracts(self) -> None:
        self.assertEqual(SOURCE_COMMIT, (SOURCE / ".git" / "HEAD").read_text(encoding="utf-8").strip())
        source = (SOURCE / "comfy_extras" / "nodes_logic.py").read_text(encoding="utf-8")
        self.assertIn("return io.NodeOutput(not value)", source)
        self.assertIn("return io.NodeOutput(all(values.values()))", source)
        self.assertIn("return io.NodeOutput(any(values.values()))", source)
        self.assertIn('io.MatchType.Input("on_false", template=template, lazy=True)', source)
        self.assertIn('io.MatchType.Input("on_true", template=template, lazy=True)', source)
        self.assertIn('return ["on_true"]', source)
        self.assertIn('return ["on_false"]', source)
        self.assertIn("return io.NodeOutput(on_true if switch else on_false)", source)
        self.assertIn("accept_all_inputs=True", source)
        self.assertIn("def validate_inputs(cls, choice: io.Combo.Type, index: int = 0, **kwargs) -> bool", source)
        self.assertIn("return io.NodeOutput(choice, index)", source)

        if FRONTEND.exists():
            self.assertEqual(FRONTEND_COMMIT, (FRONTEND / ".git" / "HEAD").read_text(encoding="utf-8").strip())
            frontend = (FRONTEND / "src" / "extensions" / "core" / "customWidgets.ts").read_text(encoding="utf-8")
            self.assertIn("function onCustomComboCreated", frontend)
            self.assertIn("w.name.startsWith('option') && w.value", frontend)
            self.assertIn("comboWidget.value = values[0] ?? ''", frontend)
            self.assertIn("widgets.slice(2).findIndex((w) => w.value === comboWidget.value)", frontend)
            self.assertIn("if (nodeData?.name === 'CustomCombo')", frontend)

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
    def test_exhaustive_census_switch_and_custom_combo_cases(self) -> None:
        self.assertEqual(WORKFLOW_WHEEL_SHA256, hashlib.sha256(WORKFLOW_WHEEL.read_bytes()).hexdigest())
        targets = {spec["classType"] for spec in ARTICLE_SPECS.values()}
        counts = {name: Counter() for name in targets}
        switch_values: Counter[bool] = Counter()
        combo_widgets: list[list[Any]] = []
        basic_edges: list[tuple[str, str, str, Any]] = []
        combo_to_json = 0
        json_count = root_count = subgraph_count = 0
        with zipfile.ZipFile(WORKFLOW_WHEEL) as archive:
            for member in sorted(name for name in archive.namelist() if "/templates/" in name and name.endswith(".json")):
                json_count += 1
                payload = json.loads(archive.read(member).decode("utf-8"))
                if not isinstance(payload, dict):
                    continue
                if isinstance(payload.get("nodes"), list):
                    root_count += 1
                definitions = payload.get("definitions")
                if isinstance(definitions, dict):
                    subgraph_count += sum(isinstance(item, dict) for item in definitions.get("subgraphs", []))
                for scope_kind, scope in graph_scopes(payload):
                    nodes = [node for node in scope.get("nodes", []) if isinstance(node, dict)]
                    by_id = {node.get("id"): node for node in nodes}
                    for node in nodes:
                        node_type = node.get("type")
                        if node_type not in targets:
                            continue
                        counts[node_type][scope_kind] += 1
                        counts[node_type][f"mode:{node.get('mode', 0)}"] += 1
                        if node_type == "ComfySwitchNode" and node.get("widgets_values"):
                            switch_values[bool(node["widgets_values"][0])] += 1
                        if node_type == "CustomCombo":
                            combo_widgets.append(node.get("widgets_values", []))
                    for raw_link in scope.get("links", []):
                        fields = link_fields(raw_link)
                        if fields is None:
                            continue
                        origin_id, _, target_id, target_slot, link_type = fields
                        source = by_id.get(origin_id, {})
                        target = by_id.get(target_id, {})
                        target_inputs = target.get("inputs", [])
                        input_name = target_inputs[target_slot].get("name") if isinstance(target_inputs, list) and isinstance(target_slot, int) and target_slot < len(target_inputs) and isinstance(target_inputs[target_slot], dict) else str(target_slot)
                        if member.endswith("basic_switch_node.json") and source.get("type") in {"PrimitiveString", "PrimitiveStringMultiline", "PrimitiveBoolean"} and target.get("type") == "ComfySwitchNode":
                            basic_edges.append((source["type"], target["type"], input_name, source.get("widgets_values")))
                        if source.get("type") == "CustomCombo" and target.get("type") == "JsonExtractString" and input_name == "key" and link_type == "STRING":
                            combo_to_json += 1

        self.assertEqual((512, 496, 272), (json_count, root_count, subgraph_count))
        self.assertEqual((13, 173, 186), (counts["ComfySwitchNode"]["root"], counts["ComfySwitchNode"]["subgraph"], counts["ComfySwitchNode"]["mode:0"]))
        self.assertEqual(Counter({False: 176, True: 10}), switch_values)
        self.assertEqual((0, 22, 22), (counts["CustomCombo"]["root"], counts["CustomCombo"]["subgraph"], counts["CustomCombo"]["mode:0"]))
        for class_type in ("ComfyNotNode", "ComfyAndNode", "ComfyOrNode"):
            self.assertEqual(0, sum(counts[class_type].values()), class_type)
        self.assertIn(["Music", 0, "Music", "Instrument", "SFX", "One-shot", ""], combo_widgets)
        self.assertIn(["Default", 1, "Quality", "Default", "Turbo", ""], combo_widgets)
        # Two Stable Audio templates and two Ideogram 4 templates use the
        # same exact CustomCombo STRING -> JsonExtractString.key topology.
        self.assertEqual(4, combo_to_json)
        self.assertEqual(2, sum(1 for edge in basic_edges if edge[:3] == ("PrimitiveString", "ComfySwitchNode", "on_true") and edge[3] == ["true"]))
        self.assertEqual(2, sum(1 for edge in basic_edges if edge[:3] == ("PrimitiveString", "ComfySwitchNode", "on_false") and edge[3] == ["false"]))
        self.assertEqual(2, sum(1 for edge in basic_edges if edge[:3] == ("PrimitiveBoolean", "ComfySwitchNode", "switch") and edge[3] == [True]))

    @unittest.skipUnless(SOURCE.exists(), "pinned ComfyUI source checkout is absent")
    def test_safe_exact_source_truthiness_lazy_and_combo_probe(self) -> None:
        candidates = [Path(os.environ.get("TEMP", "")) / "nodes-wizard-comfyui-v0.32.0-venv" / "Scripts" / "python.exe", Path(sys.executable)]
        python = next((candidate for candidate in candidates if candidate.exists()), None)
        if python is None:
            self.skipTest("no Python interpreter for logic probe")
        result = subprocess.run([str(python), "-X", "utf8", str(PROBE), str(SOURCE)], cwd=catalog.ROOT, text=True, capture_output=True, timeout=60, check=False)
        if result.returncode != 0:
            self.fail(result.stderr or result.stdout)
        payload = json.loads(result.stdout.strip().splitlines()[-1])
        self.assertTrue(payload["switch"]["trueIdentity"])
        self.assertTrue(payload["switch"]["falseIdentity"])
        self.assertTrue(payload["switch"]["unselectedMissingIgnored"])
        self.assertEqual(["SFX", 2], payload["combo"]["selected"])
        self.assertEqual(0, payload["combo"]["defaultIndex"])
        self.assertTrue(payload["combo"]["validationAcceptedDynamicOptions"])
        self.assertEqual({"empty_list": True, "empty_string": True, "false": True, "nonempty_string": False, "one": False, "true": False, "zero": True}, payload["not"])
        self.assertEqual(["first"], payload["and"]["shortCircuitCalls"])
        self.assertEqual(["first"], payload["or"]["shortCircuitCalls"])
        self.assertTrue(payload["and"]["emptyDirect"])
        self.assertFalse(payload["or"]["emptyDirect"])
        self.assertEqual({"and", "not", "or"}, set(payload["multiElementTensorErrors"]))


if __name__ == "__main__":
    unittest.main()
