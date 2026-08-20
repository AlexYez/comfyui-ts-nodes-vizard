from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import sys
import unittest
import zipfile
from pathlib import Path
from typing import Any

from tools import catalog


ARTICLE_SPECS = {
    "core.text-to-lowercase": {
        "directory": "text-to-lowercase",
        "classType": "TextToLowercase",
        "fingerprint": "sha256:1a945d2dbe351d8451ed4355ad5a9e46835bddb61af38a68028eb27703e73873",
        "recipe": "recipe.text-to-lowercase-basic",
        "required": ["texts"],
        "sourceDeprecated": True,
    },
    "core.text-to-uppercase": {
        "directory": "text-to-uppercase",
        "classType": "TextToUppercase",
        "fingerprint": "sha256:86a8e2fdd26c62bebbe03426b56891294975d1a932e876388c1524022d6d1b71",
        "recipe": "recipe.text-to-uppercase-basic",
        "required": ["texts"],
        "sourceDeprecated": True,
    },
    "core.truncate-text": {
        "directory": "truncate-text",
        "classType": "TruncateText",
        "fingerprint": "sha256:bd4844a4be24f00a93dde9fe283bf4cac29dab3ee43c5b367e0dc388f360f175",
        "recipe": "recipe.truncate-text-77",
        "required": ["texts", "max_length"],
        "sourceDeprecated": False,
    },
    "core.replace-text": {
        "directory": "replace-text",
        "classType": "ReplaceText",
        "fingerprint": "sha256:6984fddec80d7fac480bed86b95d0600a03a8b03e178a501e80bd6c6ff48527f",
        "recipe": "recipe.replace-text-literal",
        "required": ["texts", "find", "replace"],
        "sourceDeprecated": True,
    },
}

RECIPE_DIRECTORIES = {
    "recipe.text-to-lowercase-basic": "text-to-lowercase-basic",
    "recipe.text-to-uppercase-basic": "text-to-uppercase-basic",
    "recipe.truncate-text-77": "truncate-text-77",
    "recipe.replace-text-literal": "replace-text-literal",
}

EXPECTED_FRAGMENT_NODES = {
    "recipe.text-to-lowercase-basic": [("TextToLowercase", {})],
    "recipe.text-to-uppercase-basic": [("TextToUppercase", {})],
    "recipe.truncate-text-77": [("TruncateText", {"max_length": 77})],
    "recipe.replace-text-literal": [("ReplaceText", {})],
}

FULL_INVENTORY = catalog.CONTENT / "runtime" / "comfyui-0.32.0.object-info.json"
REPLACEMENTS = catalog.CONTENT / "runtime" / "comfyui-0.32.0.node-replacements.json"
REPLACEMENTS_SHA256 = "4d9e22176cbddd8c309707d434f011854cd768f92146586bf9e17c01e93ae5b6"
SOURCE = catalog.ROOT / ".comfyui-source-0.32.0"
WORKFLOW_WHEEL = (
    catalog.ROOT
    / ".upstream-cache"
    / "comfyui_workflow_templates_json-0.1.42-py3-none-any.whl"
)
WORKFLOW_WHEEL_SHA256 = "242982d65e1c51ca03d892bc1009bb6843f457e7dfc0c20afe6438770b7a14a3"
EMBEDDED_DOCS_WHEEL = (
    catalog.ROOT
    / ".upstream-cache"
    / "comfyui_embedded_docs-0.5.9-py3-none-any.whl"
)
EMBEDDED_DOCS_WHEEL_SHA256 = "30afae432a71c96aa59421d0f37388c66ff6572b8cbeee8ff045e4d5f84f896c"
EMBEDDED_DOC_HASHES = {
    "TextToLowercase": {
        "en": "fb9b329d738653d307b36cdee3c4faa6e9fd9faf925618e9e76158083538747d",
        "ru": "a58f269e511ca2e9163554fc88f15097b04800c2c03e786164ea9adc3cf65137",
    },
    "TextToUppercase": {
        "en": "127c4778471baa89f8d217629531c999e72b152c3fb9c9c910d2c0aface471f7",
        "ru": "64d1499f1b9858b508baa97d4e21f72d57b3249bb0e969c64d8a7b7f2a9fd9fa",
    },
    "TruncateText": {
        "en": "585058e2b861fb12a36045efa9dfdbc44b90fbc544333381d9bae968519e8f7c",
        "ru": "130f7f6c3e2d1753b0a0bf275c659339a5ef05c148e7f8acb99c66db98bda7bd",
    },
    "ReplaceText": {
        "en": "5f4588e1160efcee7b5481b2d63090a8c1440adc7c372d798f8e55d5c1b733d3",
        "ru": "36fb2d688b877772ba3ea9e47a412dd65d9c3df90398345e5cd784f2f44eb48c",
    },
}
SYNTHETIC_PROBE = Path(__file__).with_name("dataset_text_transform_synthetic_probe.py")


def article_path(spec: dict[str, Any]) -> Path:
    return catalog.CONTENT / "articles" / "core" / spec["directory"] / "manifest.json"


def recipe_path(recipe_id: str) -> Path:
    return catalog.CONTENT / "recipes" / RECIPE_DIRECTORIES[recipe_id] / "recipe.json"


def all_article_ids() -> set[str]:
    ids = set()
    for path in (catalog.CONTENT / "articles").rglob("manifest.json"):
        payload = catalog.load_json(path)
        if isinstance(payload, dict) and isinstance(payload.get("articleId"), str):
            ids.add(payload["articleId"])
    return ids


def runtime_input_specs(runtime: dict[str, Any]) -> dict[str, Any]:
    result = {}
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


class DatasetTextTransformContentTests(unittest.TestCase):
    def test_articles_recipes_research_and_editorial_contracts(self) -> None:
        article_ids = all_article_ids()
        schemas = {
            "article": catalog.load_json(catalog.CONTENT / "schemas" / "article.schema.v1.json"),
            "recipe": catalog.load_json(catalog.CONTENT / "schemas" / "recipe.schema.v1.json"),
            "fragment": catalog.load_json(catalog.CONTENT / "schemas" / "recipe-fragment.schema.v1.json"),
            "research": catalog.load_json(catalog.CONTENT / "schemas" / "article-research.schema.v1.json"),
        }
        banned = re.compile(
            r"важно отметить|стоит отметить|следует отметить|в современном мире|"
            r"революционн|является незаменим|является мощн|\bдавайте\b|"
            r"глубже погруз|открывает новые|может показаться|позволяет вам|"
            r"подводя итог|в заключение|не просто .{0,80}, а",
            flags=re.IGNORECASE,
        )
        errors: list[str] = []
        for article_id, spec in ARTICLE_SPECS.items():
            path = article_path(spec)
            article = catalog.load_json(path)
            self.assertEqual([], catalog.json_schema_errors(article, schemas["article"]))
            catalog.validate_article(path, article, errors)
            self.assertEqual(article_id, article["articleId"])
            self.assertEqual("draft", article["status"])
            self.assertTrue(article["experimental"])
            self.assertEqual("in_review", article["editorial"]["state"])
            self.assertIn("human approval pending", article["editorial"]["reviewedBy"])
            self.assertEqual([], article["runtimeIdentity"]["aliases"])
            self.assertEqual(
                {spec["recipe"]},
                {asset["id"] for asset in article["assets"] if asset["type"] == "recipe"},
            )
            relations = article["relations"]
            targets = set(relations["related"] + relations["alternatives"])
            if relations["replacedBy"]:
                targets.add(relations["replacedBy"])
            self.assertTrue(targets.issubset(article_ids), (article_id, targets))
            body = (path.parent / article["body"]).read_text(encoding="utf-8")
            self.assertEqual(10, len(re.findall(r"^## .+$", body, flags=re.MULTILINE)))
            self.assertNotIn("\ufffd", body)
            self.assertIsNone(banned.search(body), article_id)

            research = catalog.load_json(
                catalog.CONTENT / "research" / "reviews" / f"{article_id}.json"
            )
            self.assertEqual([], catalog.json_schema_errors(research, schemas["research"]))
            self.assertEqual("fact_checked", research["state"])
            self.assertEqual("automated_assisted", research["reviewMode"])
            self.assertFalse(research["checks"]["exampleExecuted"])
            self.assertTrue(research["checks"]["russianEdited"])
            self.assertTrue(research["checks"]["factsRecheckedAfterEditing"])
            self.assertIn("Статья ожидает человеческого утверждения.", research["knownGaps"])

        for recipe_id in RECIPE_DIRECTORIES:
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
            self.assertEqual([], fragment["connections"])
            self.assertEqual(
                EXPECTED_FRAGMENT_NODES[recipe_id],
                [(node["classType"], node["settings"]) for node in fragment["nodes"]],
            )
        self.assertEqual([], errors)

    def test_runtime_fingerprints_flags_ports_and_fragment_settings(self) -> None:
        nodes = catalog.object_info_nodes(catalog.load_json(FULL_INVENTORY))
        for article_id, spec in ARTICLE_SPECS.items():
            runtime = nodes[spec["classType"]]
            article = catalog.load_json(article_path(spec))
            self.assertEqual("comfy_extras.nodes_dataset", runtime["python_module"])
            self.assertTrue(runtime.get("experimental", False))
            self.assertFalse(runtime.get("deprecated", False))
            self.assertFalse(runtime.get("dev_only", False))
            self.assertFalse(runtime.get("api_node", False))
            self.assertFalse(runtime["is_input_list"])
            self.assertEqual(["STRING"], runtime["output"])
            self.assertEqual(["texts"], runtime["output_name"])
            self.assertEqual([None], runtime["output_is_list"])
            self.assertEqual(spec["required"], runtime["input_order"]["required"])
            self.assertEqual(spec["fingerprint"], catalog.schema_fingerprint(spec["classType"], runtime))
            self.assertEqual(spec["fingerprint"], article["editorial"]["schemaHash"])

        for class_type in ARTICLE_SPECS.values():
            text = nodes[class_type["classType"]]["input"]["required"]["texts"]
            self.assertEqual("STRING", descriptor_type(text))
            self.assertFalse(text[1]["multiline"])
        max_length = nodes["TruncateText"]["input"]["required"]["max_length"]
        self.assertEqual({"default": 77, "min": 1, "max": 10000}, {
            key: max_length[1][key] for key in ("default", "min", "max")
        })
        for name in ("find", "replace"):
            descriptor = nodes["ReplaceText"]["input"]["required"][name]
            self.assertEqual("", descriptor[1]["default"])
            self.assertFalse(descriptor[1]["multiline"])

        for recipe_id in RECIPE_DIRECTORIES:
            path = recipe_path(recipe_id)
            fragment = catalog.load_json(path.parent / catalog.load_json(path)["fragment"]["path"])
            node_by_ref = {node["ref"]: node for node in fragment["nodes"]}
            supplied = {ref: set(node["settings"]) for ref, node in node_by_ref.items()}
            for external in fragment["externalInputs"]:
                target = node_by_ref[external["to"]]
                descriptor = runtime_input_specs(nodes[target["classType"]])[external["input"]]
                self.assertEqual(external["type"], descriptor_type(descriptor))
                supplied[external["to"]].add(external["input"])
            for ref, node in node_by_ref.items():
                runtime = nodes[node["classType"]]
                self.assertTrue(set(runtime["input"]["required"]).issubset(supplied[ref]))
                for name, value in node["settings"].items():
                    descriptor = runtime_input_specs(runtime)[name]
                    self.assertEqual("INT", descriptor_type(descriptor))
                    self.assertGreaterEqual(value, descriptor[1]["min"])
                    self.assertLessEqual(value, descriptor[1]["max"])

    @unittest.skipUnless(SOURCE.exists(), "pinned ComfyUI source checkout is absent")
    def test_articles_track_exact_source_successors_and_replacement_state(self) -> None:
        dataset = (SOURCE / "comfy_extras" / "nodes_dataset.py").read_text(encoding="utf-8")
        strings = (SOURCE / "comfy_extras" / "nodes_string.py").read_text(encoding="utf-8")
        execution = (SOURCE / "execution.py").read_text(encoding="utf-8")
        self.assertIn("class TextProcessingNode(io.ComfyNode):", dataset)
        self.assertIn("is_output_list = None", dataset)
        self.assertIn("is_experimental=True", dataset)
        self.assertNotIn("is_deprecated=cls.is_deprecated", dataset[dataset.index("class TextProcessingNode"):dataset.index("# ========== Image Transform Nodes")])
        self.assertIn("return io.NodeOutput([result])", dataset)
        self.assertIn("return text.lower()", dataset)
        self.assertIn("return text.upper()", dataset)
        self.assertIn("return text[:max_length]", dataset)
        self.assertIn("return text.replace(find, replace)", dataset)
        deprecated_targets = {
            "TextToLowercaseNode": "Convert Text Case node",
            "TextToUppercaseNode": "Convert Text Case node",
            "ReplaceTextNode": "other Replace Text node",
        }
        for class_name, successor in deprecated_targets.items():
            start = dataset.index(f"class {class_name}")
            end = dataset.index("\n\nclass ", start + 1)
            self.assertIn("is_deprecated = True", dataset[start:end])
            self.assertIn(successor, dataset[start:end])
        start = dataset.index("class TruncateTextNode")
        end = dataset.index("\n\nclass ", start + 1)
        self.assertNotIn("is_deprecated = True", dataset[start:end])
        self.assertIn('node_id="CaseConverter"', strings)
        self.assertIn('node_id="StringReplace"', strings)
        self.assertIn("result = string.lower()", strings)
        self.assertIn("result = string.upper()", strings)
        self.assertIn("return io.NodeOutput(string.replace(find, replace))", strings)
        self.assertIn("output_is_list = [False] * len(results[0])", execution)
        self.assertIn("output.append([o[i] for o in results])", execution)

        self.assertEqual(REPLACEMENTS_SHA256, hashlib.sha256(REPLACEMENTS.read_bytes()).hexdigest())
        replacement_text = REPLACEMENTS.read_text(encoding="utf-8")
        for class_type in [spec["classType"] for spec in ARTICLE_SPECS.values()] + ["CaseConverter", "StringReplace"]:
            self.assertNotIn(class_type, replacement_text)

    @unittest.skipUnless(EMBEDDED_DOCS_WHEEL.exists(), "pinned embedded-docs wheel is absent")
    def test_embedded_docs_case_sensitive_members_hashes_and_gaps(self) -> None:
        self.assertEqual(EMBEDDED_DOCS_WHEEL_SHA256, hashlib.sha256(EMBEDDED_DOCS_WHEEL.read_bytes()).hexdigest())
        docs = {}
        with zipfile.ZipFile(EMBEDDED_DOCS_WHEEL) as archive:
            names = archive.namelist()
            for class_type, locales in EMBEDDED_DOC_HASHES.items():
                exact = [name for name in names if re.search(rf"/{re.escape(class_type)}/(?:en|ru)\.md$", name)]
                insensitive = [name for name in names if re.search(rf"/{re.escape(class_type)}/(?:en|ru)\.md$", name, flags=re.IGNORECASE)]
                self.assertEqual(2, len(exact))
                self.assertEqual(exact, insensitive)
                for locale, expected_hash in locales.items():
                    member = f"comfyui_embedded_docs/docs/{class_type}/{locale}.md"
                    payload = archive.read(member)
                    self.assertEqual(expected_hash, hashlib.sha256(payload).hexdigest())
                    docs[(class_type, locale)] = payload.decode("utf-8")

        for class_type in EMBEDDED_DOC_HASHES:
            self.assertIn("AI-generated", docs[(class_type, "en")])
            self.assertNotIn("`texts`", docs[(class_type, "en")])
            self.assertNotIn("output_is_list", docs[(class_type, "en")])
        self.assertIn("deprecated", docs[("TextToLowercase", "en")].lower())
        self.assertNotIn("устар", docs[("TextToLowercase", "ru")].lower())
        self.assertIn("deprecated", docs[("TextToUppercase", "en")].lower())
        self.assertIn("Вот перевод документации", docs[("TextToUppercase", "ru")])
        self.assertNotIn("code point", docs[("TruncateText", "en")].lower())
        self.assertNotIn("token", docs[("TruncateText", "en")].lower())
        self.assertIn("all text inputs", docs[("ReplaceText", "en")])
        self.assertNotIn("empty", docs[("ReplaceText", "en")].lower().replace("empty string", ""))
        self.assertNotIn("устар", docs[("ReplaceText", "ru")].lower())

    @unittest.skipUnless(WORKFLOW_WHEEL.exists(), "official workflow wheel is absent")
    def test_exhaustive_workflow_census_has_no_case_sensitive_targets(self) -> None:
        self.assertEqual(WORKFLOW_WHEEL_SHA256, hashlib.sha256(WORKFLOW_WHEEL.read_bytes()).hexdigest())
        targets = {spec["classType"] for spec in ARTICLE_SPECS.values()}
        raw_hits = []
        type_hits = []
        root_workflows = root_nodes = subgraphs_count = subgraph_nodes = 0
        with zipfile.ZipFile(WORKFLOW_WHEEL) as archive:
            members = sorted(name for name in archive.namelist() if "/templates/" in name and name.endswith(".json"))
            self.assertEqual(512, len(members))
            for member in members:
                raw = archive.read(member).decode("utf-8")
                for target in targets:
                    if target in raw:
                        raw_hits.append((member, target))
                payload = json.loads(raw)
                if not isinstance(payload, dict):
                    continue
                nodes = payload.get("nodes")
                if isinstance(nodes, list):
                    root_workflows += 1
                    root_nodes += len(nodes)
                    type_hits.extend(("root", member, node["type"]) for node in nodes if isinstance(node, dict) and node.get("type") in targets)
                definitions = payload.get("definitions")
                subgraphs = definitions.get("subgraphs", []) if isinstance(definitions, dict) else []
                for subgraph in subgraphs:
                    if not isinstance(subgraph, dict):
                        continue
                    subgraphs_count += 1
                    nodes = subgraph.get("nodes", []) or []
                    subgraph_nodes += len(nodes)
                    type_hits.extend(("subgraph", member, node["type"]) for node in nodes if isinstance(node, dict) and node.get("type") in targets)
        self.assertEqual((496, 4083, 272, 4037, 8120), (root_workflows, root_nodes, subgraphs_count, subgraph_nodes, root_nodes + subgraph_nodes))
        self.assertEqual([], raw_hits)
        self.assertEqual([], type_hits)

    @unittest.skipUnless(SOURCE.exists(), "pinned ComfyUI source checkout is absent")
    def test_exact_source_synthetic_execution_without_external_data(self) -> None:
        candidates = [
            Path(os.environ.get("TEMP", "")) / "nodes-wizard-comfyui-v0.32.0-venv" / "Scripts" / "python.exe",
            Path(sys.executable),
        ]
        python = next((candidate for candidate in candidates if candidate.exists()), None)
        if python is None:
            self.skipTest("no Python interpreter for dataset text probe")
        env = os.environ.copy()
        env["PYTHONIOENCODING"] = "utf-8"
        result = subprocess.run(
            [str(python), str(SYNTHETIC_PROBE), str(SOURCE)],
            cwd=catalog.ROOT,
            env=env,
            text=True,
            encoding="utf-8",
            capture_output=True,
            timeout=120,
            check=False,
        )
        if result.returncode != 0 and python != Path(sys.executable):
            self.fail(result.stderr or result.stdout)
        if result.returncode != 0:
            self.skipTest(f"dataset text probe unavailable: {result.stderr}")
        payload = json.loads(result.stdout.strip().splitlines()[-1])
        case = payload["caseConversion"]
        self.assertEqual(["привет i̇ σ ß"], case["lowerOutput"])
        self.assertEqual(["STRASSE I ΣΣ"], case["upperOutput"])
        self.assertEqual({"lowercase": True, "uppercase": True}, case["caseConverterParity"])
        replace = payload["replace"]
        self.assertEqual(["bb"], replace["nonOverlapping"])
        self.assertEqual(["-a-b-c-"], replace["emptyFind"])
        self.assertEqual(["AbA"], replace["caseSensitive"])
        self.assertEqual([" two "], replace["deleteMatches"])
        self.assertTrue(replace["listWrappedParametersUnwrapped"] == ["A-A"])
        self.assertTrue(replace["stringReplaceParity"])
        truncate = payload["truncate"]
        self.assertEqual(["A😀é"], truncate["maxLength4"])
        self.assertTrue(truncate["unicodeCodePointSlice"])
        contract = payload["runtimeContract"]
        self.assertEqual([[['abc']]], contract["mergedLowerOutput"])
        self.assertEqual("AttributeError", contract["directChainingFailsFromNestedOutput"])
        for class_type, spec in ARTICLE_SPECS.items():
            schema = contract["schemas"][spec["classType"]]
            self.assertFalse(schema["inputIsList"])
            self.assertEqual([None], schema["outputIsList"])
            self.assertFalse(schema["runtimeDeprecated"])
            self.assertEqual(spec["sourceDeprecated"], schema["sourceDeprecated"])


if __name__ == "__main__":
    unittest.main()
