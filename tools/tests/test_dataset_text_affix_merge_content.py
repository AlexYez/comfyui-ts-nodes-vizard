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
from typing import Any

from tools import catalog


ARTICLE_SPECS = {
    "core.add-text-prefix": {
        "directory": "add-text-prefix",
        "classType": "AddTextPrefix",
        "fingerprint": "sha256:011507fe0631aee062f38fd0991ca3da3144a8ae8edba592016cb1b9868d731d",
        "required": ["texts", "prefix"],
        "isInputList": False,
        "recipe": "recipe.add-text-prefix-basic",
    },
    "core.add-text-suffix": {
        "directory": "add-text-suffix",
        "classType": "AddTextSuffix",
        "fingerprint": "sha256:fd0c6f384b67e53c02e9e123b47cfc87c9cbfef64e8d2bdb71fd10064df945f3",
        "required": ["texts", "suffix"],
        "isInputList": False,
        "recipe": "recipe.add-text-suffix-basic",
    },
    "core.strip-whitespace": {
        "directory": "strip-whitespace",
        "classType": "StripWhitespace",
        "fingerprint": "sha256:3b3a0f287cf2892d6a1457b10f194d0f81fb96d98558370925f840872017cff3",
        "required": ["texts"],
        "isInputList": False,
        "recipe": "recipe.strip-whitespace-basic",
    },
    "core.merge-text-lists": {
        "directory": "merge-text-lists",
        "classType": "MergeTextLists",
        "fingerprint": "sha256:4e0814b665dbe8f92ca6762a25ad1d54e1d356f414bbfc670abc9d7a14fe99bc",
        "required": ["texts"],
        "isInputList": True,
        "recipe": "recipe.merge-text-lists-basic",
    },
}
RECIPE_DIRECTORIES = {
    "recipe.add-text-prefix-basic": "add-text-prefix-basic",
    "recipe.add-text-suffix-basic": "add-text-suffix-basic",
    "recipe.strip-whitespace-basic": "strip-whitespace-basic",
    "recipe.merge-text-lists-basic": "merge-text-lists-basic",
}
EXPECTED_FRAGMENT_NODES = {
    "recipe.add-text-prefix-basic": [("AddTextPrefix", {"prefix": "dataset: "})],
    "recipe.add-text-suffix-basic": [("AddTextSuffix", {"suffix": " [draft]"})],
    "recipe.strip-whitespace-basic": [("StripWhitespace", {})],
    "recipe.merge-text-lists-basic": [("MergeTextLists", {})],
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
    "AddTextPrefix": {
        "en": "b95c3b6b1772a92576932e15ccdb49a3d51b10f92952560b4069ca4f1743c40d",
        "ru": "85882ea3506ef16368a8a09dde05894fbd54adde7f4286b3b9e9004d98ea4fc9",
    },
    "AddTextSuffix": {
        "en": "5befc41a0da3a0aea928a4530675580ed39eb5e1fd9cd938212ef9e048dfe237",
        "ru": "fd3acfade5119a7fa4256f9f1ebdda2b9c0557989dae04c73165513b30eb06fa",
    },
    "StripWhitespace": {
        "en": "632235f3a2468828cc3098c233cdfce07368b0a3afd7dc76ea368f53a2174520",
        "ru": "b943d0302e3292df41de3a8bae9d8cce7177b7f9473b15cc9ece279bc5b1ae2e",
    },
    "MergeTextLists": {
        "en": "20de596ace15435dafa5e00be0773a0d23a71710274d8f9c5c5707f1145e00a1",
        "ru": "e29e0f531545f49948ab6d30bb850ec586e45c9f904b7208cdc3fa327b3f5116",
    },
}
SYNTHETIC_PROBE = Path(__file__).with_name(
    "dataset_text_affix_merge_synthetic_probe.py"
)


def article_path(spec: dict[str, Any]) -> Path:
    return catalog.CONTENT / "articles" / "core" / spec["directory"] / "manifest.json"


def recipe_path(recipe_id: str) -> Path:
    return catalog.CONTENT / "recipes" / RECIPE_DIRECTORIES[recipe_id] / "recipe.json"


def all_article_ids() -> list[str]:
    ids = []
    for path in (catalog.CONTENT / "articles").rglob("manifest.json"):
        payload = catalog.load_json(path)
        if isinstance(payload, dict) and isinstance(payload.get("articleId"), str):
            ids.append(payload["articleId"])
    return ids


def all_recipe_ids() -> list[str]:
    ids = []
    for path in (catalog.CONTENT / "recipes").rglob("recipe.json"):
        payload = catalog.load_json(path)
        if isinstance(payload, dict) and isinstance(payload.get("recipeId"), str):
            ids.append(payload["recipeId"])
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


class DatasetTextAffixMergeContentTests(unittest.TestCase):
    def test_articles_recipes_research_and_editorial_contracts(self) -> None:
        article_id_list = all_article_ids()
        recipe_id_list = all_recipe_ids()
        counts = Counter(article_id_list)
        recipe_counts = Counter(recipe_id_list)
        for article_id, spec in ARTICLE_SPECS.items():
            self.assertEqual(1, counts[article_id], article_id)
            self.assertEqual(1, recipe_counts[spec["recipe"]], spec["recipe"])
        article_ids = set(article_id_list)

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
            self.assertRegex(body.lower(), r"официальн")
            self.assertIn(spec["fingerprint"], body)

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
        display_names = {
            "AddTextPrefix": "Add Text Prefix (DEPRECATED)",
            "AddTextSuffix": "Add Text Suffix (DEPRECATED)",
            "StripWhitespace": "Strip Whitespace (DEPRECATED)",
            "MergeTextLists": "Merge Text Lists (DEPRECATED)",
        }
        for article_id, spec in ARTICLE_SPECS.items():
            runtime = nodes[spec["classType"]]
            article = catalog.load_json(article_path(spec))
            self.assertEqual("comfy_extras.nodes_dataset", runtime["python_module"])
            self.assertEqual("text", runtime["category"])
            self.assertTrue(runtime.get("experimental", False))
            self.assertFalse(runtime.get("deprecated", False))
            self.assertFalse(runtime.get("dev_only", False))
            self.assertFalse(runtime.get("api_node", False))
            self.assertEqual(spec["isInputList"], runtime["is_input_list"])
            self.assertEqual(["STRING"], runtime["output"])
            self.assertEqual(["texts"], runtime["output_name"])
            self.assertEqual([None], runtime["output_is_list"])
            self.assertEqual(spec["required"], runtime["input_order"]["required"])
            self.assertEqual(display_names[spec["classType"]], runtime["display_name"])
            self.assertEqual(spec["fingerprint"], catalog.schema_fingerprint(spec["classType"], runtime))
            self.assertEqual(spec["fingerprint"], article["editorial"]["schemaHash"])

            texts = runtime["input"]["required"]["texts"]
            self.assertEqual("STRING", descriptor_type(texts))
            self.assertFalse(texts[1]["multiline"])

        for class_type, name in (("AddTextPrefix", "prefix"), ("AddTextSuffix", "suffix")):
            descriptor = nodes[class_type]["input"]["required"][name]
            self.assertEqual("STRING", descriptor_type(descriptor))
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
                    self.assertEqual("STRING", descriptor_type(descriptor))
                    self.assertIsInstance(value, str)

    @unittest.skipUnless(SOURCE.exists(), "pinned ComfyUI source checkout is absent")
    def test_articles_track_exact_source_successors_and_replacement_state(self) -> None:
        dataset = (SOURCE / "comfy_extras" / "nodes_dataset.py").read_text(encoding="utf-8")
        strings = (SOURCE / "comfy_extras" / "nodes_string.py").read_text(encoding="utf-8")
        toolkit = (SOURCE / "comfy_extras" / "nodes_toolkit.py").read_text(encoding="utf-8")
        execution = (SOURCE / "execution.py").read_text(encoding="utf-8")

        base_start = dataset.index("class TextProcessingNode(io.ComfyNode):")
        base_end = dataset.index("# ========== Image Transform Nodes", base_start)
        base = dataset[base_start:base_end]
        self.assertIn("is_output_list = None", base)
        self.assertIn("is_experimental=True", base)
        self.assertIn("is_input_list=is_group", base)
        self.assertIn("return io.NodeOutput([result])", base)
        self.assertNotIn("is_deprecated=cls.is_deprecated", base)

        expected_blocks = {
            "AddTextPrefixNode": ("return prefix + text", "Concatenate Text node"),
            "AddTextSuffixNode": ("return text + suffix", "Concatenate Text node"),
            "StripWhitespaceNode": ("return text.strip()", "Trim Text node"),
            "MergeTextListsNode": ("return texts", "Create List node"),
        }
        for class_name, (operation, successor) in expected_blocks.items():
            start = dataset.index(f"class {class_name}")
            end = dataset.find("\n\nclass ", start + 1)
            if end == -1:
                end = len(dataset)
            block = dataset[start:end]
            self.assertIn("is_deprecated = True", block)
            self.assertIn(operation, block)
            self.assertIn(successor, block)
        merge_start = dataset.index("class MergeTextListsNode")
        merge_end = dataset.index("# ========== Training Dataset Nodes", merge_start)
        merge_block = dataset[merge_start:merge_end]
        self.assertIn("is_group_process = True", merge_block)
        self.assertIn("logging.info", merge_block)

        self.assertIn('node_id="StringConcatenate"', strings)
        self.assertIn("return io.NodeOutput(delimiter.join((string_a, string_b)))", strings)
        self.assertIn('node_id="StringTrim"', strings)
        self.assertIn("result = string.strip()", strings)
        self.assertIn('node_id="CreateList"', toolkit)
        self.assertIn("template_autogrow", toolkit)
        self.assertIn("is_output_list=True", toolkit)
        self.assertIn("output_list += input", toolkit)
        self.assertIn("output_is_list = [False] * len(results[0])", execution)
        self.assertIn("output.append([o[i] for o in results])", execution)

        self.assertEqual(REPLACEMENTS_SHA256, hashlib.sha256(REPLACEMENTS.read_bytes()).hexdigest())
        replacement_text = REPLACEMENTS.read_text(encoding="utf-8")
        for class_type in [spec["classType"] for spec in ARTICLE_SPECS.values()] + [
            "StringConcatenate", "StringTrim", "CreateList"
        ]:
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
            self.assertIn("deprecated", docs[(class_type, "en")].lower())
            self.assertNotIn("output_is_list", docs[(class_type, "en")])
            self.assertNotIn("устар", docs[(class_type, "ru")].lower())
        for class_type in ("AddTextPrefix", "AddTextSuffix", "StripWhitespace"):
            self.assertIn("`text`", docs[(class_type, "en")])
            self.assertNotIn("`texts`", docs[(class_type, "en")])
        self.assertIn("| `prefix` |", docs[("AddTextPrefix", "en")])
        self.assertIn("| No |", docs[("AddTextPrefix", "en")])
        self.assertIn("`префикс`", docs[("AddTextPrefix", "ru")])
        self.assertIn("| `suffix` |", docs[("AddTextSuffix", "en")])
        self.assertIn("| No |", docs[("AddTextSuffix", "en")])
        self.assertIn("`суффикс`", docs[("AddTextSuffix", "ru")])
        self.assertNotIn("U+00A0", docs[("StripWhitespace", "en")])
        self.assertIn("Multiple lists can be connected", docs[("MergeTextLists", "en")])
        self.assertIn("`тексты`", docs[("MergeTextLists", "ru")])

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
            self.skipTest("no Python interpreter for dataset text affix/merge probe")
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
            self.skipTest(f"dataset text affix/merge probe unavailable: {result.stderr}")
        payload = json.loads(result.stdout.strip().splitlines()[-1])

        self.assertEqual(["→ текст"], payload["prefix"]["output"])
        self.assertTrue(payload["prefix"]["emptyPrefixIsIdentity"])
        self.assertTrue(payload["prefix"]["listWrappedParameterUnwrapped"])
        self.assertTrue(payload["prefix"]["stringConcatenateParity"])
        self.assertEqual(["текст ←"], payload["suffix"]["output"])
        self.assertTrue(payload["suffix"]["emptySuffixIsIdentity"])
        self.assertTrue(payload["suffix"]["listWrappedParameterUnwrapped"])
        self.assertTrue(payload["suffix"]["stringConcatenateParity"])
        self.assertEqual(["текст"], payload["strip"]["output"])
        self.assertTrue(payload["strip"]["allWhitespaceBecomesEmpty"])
        self.assertTrue(payload["strip"]["internalWhitespacePreserved"])
        self.assertTrue(payload["strip"]["stringTrimBothParity"])

        text_list = payload["textList"]
        self.assertTrue(text_list["passThroughIdentity"])
        self.assertTrue(text_list["orderDuplicatesAndEmptyPreserved"])
        self.assertEqual([[]], text_list["emptyOutput"])
        self.assertEqual([["один"]], text_list["singletonOutput"])
        self.assertTrue(text_list["createListEquivalentValues"])

        contract = payload["runtimeContract"]
        self.assertEqual([[["[abc"]]], contract["mergedPrefixOutput"])
        self.assertEqual([[["abc]"]]], contract["mergedSuffixOutput"])
        self.assertEqual([[["abc"]]], contract["mergedStripOutput"])
        self.assertEqual(
            [[[['первый', '', 'первый', 'третий']]]],
            contract["mergedMergeTextListsOutput"],
        )
        self.assertEqual([["a", "b"]], contract["mergedCreateListOutput"])
        for class_type, spec in ARTICLE_SPECS.items():
            schema = contract["schemas"][spec["classType"]]
            self.assertEqual(spec["isInputList"], schema["inputIsList"])
            self.assertEqual([None], schema["outputIsList"])
            self.assertFalse(schema["runtimeDeprecated"])
            self.assertTrue(schema["sourceDeprecated"])


if __name__ == "__main__":
    unittest.main()
