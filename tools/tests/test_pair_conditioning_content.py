from __future__ import annotations

import base64
import csv
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


ARTICLE_SPECS = {
    "core.pair-conditioning-combine": {
        "directory": "pair-conditioning-combine",
        "classType": "PairConditioningCombine",
        "displayName": "Cond Pair Combine",
        "fingerprint": "sha256:10738f1a17047975e28da0ac6fae4bd71e1be1b1e53957bc4636d63c0c5449ca",
        "recipe": "recipe.combine-conditioning-pairs",
        "required": ["positive_A", "negative_A", "positive_B", "negative_B"],
        "optional": [],
    },
    "core.pair-conditioning-set-properties": {
        "directory": "pair-conditioning-set-properties",
        "classType": "PairConditioningSetProperties",
        "displayName": "Cond Pair Set Props",
        "fingerprint": "sha256:e6fc1942015a4d36842ee03e2902e7bfc6782de43a9ecd7a3faa2512ca998197",
        "recipe": "recipe.set-properties-on-conditioning-pair",
        "required": ["positive_NEW", "negative_NEW", "strength", "set_cond_area"],
        "optional": ["mask", "hooks", "timesteps"],
    },
    "core.pair-conditioning-set-properties-and-combine": {
        "directory": "pair-conditioning-set-properties-and-combine",
        "classType": "PairConditioningSetPropertiesAndCombine",
        "displayName": "Cond Pair Set Props Combine",
        "fingerprint": "sha256:f43fb5cc32d59b74f91f39395db0fe7730f29f8bb0ba42a101e9b2ae2d143e74",
        "recipe": "recipe.combine-conditioning-pair-with-properties",
        "required": [
            "positive",
            "negative",
            "positive_NEW",
            "negative_NEW",
            "strength",
            "set_cond_area",
        ],
        "optional": ["mask", "hooks", "timesteps"],
    },
    "core.pair-conditioning-set-default-combine": {
        "directory": "pair-conditioning-set-default-combine",
        "classType": "PairConditioningSetDefaultCombine",
        "displayName": "Cond Pair Set Default Combine",
        "fingerprint": "sha256:883d72b1598c394198f41c8c77c2d208d8d4c50c6f6e10252cc402a5c592ee3d",
        "recipe": "recipe.add-default-conditioning-pair",
        "required": ["positive", "negative", "positive_DEFAULT", "negative_DEFAULT"],
        "optional": ["hooks"],
    },
}

RECIPE_DIRECTORIES = {
    "recipe.combine-conditioning-pairs": "combine-conditioning-pairs",
    "recipe.set-properties-on-conditioning-pair": "set-properties-on-conditioning-pair",
    "recipe.combine-conditioning-pair-with-properties": "combine-conditioning-pair-with-properties",
    "recipe.add-default-conditioning-pair": "add-default-conditioning-pair",
}

FRAGMENT_SPECS = {
    "recipe.combine-conditioning-pairs": {
        "classType": "PairConditioningCombine",
        "ref": "combine_pair",
        "externalInputs": [
            ("positive_a", "CONDITIONING", "positive_A"),
            ("negative_a", "CONDITIONING", "negative_A"),
            ("positive_b", "CONDITIONING", "positive_B"),
            ("negative_b", "CONDITIONING", "negative_B"),
        ],
        "settings": {},
    },
    "recipe.set-properties-on-conditioning-pair": {
        "classType": "PairConditioningSetProperties",
        "ref": "set_pair_props",
        "externalInputs": [
            ("positive", "CONDITIONING", "positive_NEW"),
            ("negative", "CONDITIONING", "negative_NEW"),
            ("mask", "MASK", "mask"),
            ("hooks", "HOOKS", "hooks"),
            ("timesteps", "TIMESTEPS_RANGE", "timesteps"),
        ],
        "settings": {"strength": 0.65, "set_cond_area": "mask bounds"},
    },
    "recipe.combine-conditioning-pair-with-properties": {
        "classType": "PairConditioningSetPropertiesAndCombine",
        "ref": "combine_pair_props",
        "externalInputs": [
            ("positive_base", "CONDITIONING", "positive"),
            ("negative_base", "CONDITIONING", "negative"),
            ("positive_new", "CONDITIONING", "positive_NEW"),
            ("negative_new", "CONDITIONING", "negative_NEW"),
            ("mask", "MASK", "mask"),
            ("hooks", "HOOKS", "hooks"),
            ("timesteps", "TIMESTEPS_RANGE", "timesteps"),
        ],
        "settings": {"strength": 0.25, "set_cond_area": "default"},
    },
    "recipe.add-default-conditioning-pair": {
        "classType": "PairConditioningSetDefaultCombine",
        "ref": "set_pair_default",
        "externalInputs": [
            ("positive", "CONDITIONING", "positive"),
            ("negative", "CONDITIONING", "negative"),
            ("positive_default", "CONDITIONING", "positive_DEFAULT"),
            ("negative_default", "CONDITIONING", "negative_DEFAULT"),
            ("hooks", "HOOKS", "hooks"),
        ],
        "settings": {},
    },
}

ROOT = catalog.ROOT
CONTENT = catalog.CONTENT
SOURCE = ROOT / ".comfyui-source-0.32.0"
INVENTORY = CONTENT / "runtime" / "comfyui-0.32.0.object-info.json"
REPLACEMENTS = CONTENT / "runtime" / "comfyui-0.32.0.node-replacements.json"
DOCS_WHEEL = ROOT / ".upstream-cache" / "comfyui_embedded_docs-0.5.9-py3-none-any.whl"
WORKFLOW_WHEEL = ROOT / ".upstream-cache" / "comfyui_workflow_templates_json-0.1.42-py3-none-any.whl"
PROBE = ROOT / "tools" / "tests" / "pair_conditioning_synthetic_probe.py"
TARGET_TYPES = {spec["classType"] for spec in ARTICLE_SPECS.values()}

DOCS_SHA256 = "30afae432a71c96aa59421d0f37388c66ff6572b8cbeee8ff045e4d5f84f896c"
WORKFLOW_SHA256 = "242982d65e1c51ca03d892bc1009bb6843f457e7dfc0c20afe6438770b7a14a3"
DOC_HASHES = {
    ("PairConditioningCombine", "en"): "60a56f7379c8a5bce447385214a965b2c6e1eeeb27554cb1c78c945cf117cfff",
    ("PairConditioningCombine", "ru"): "b6c409918b6c11d823c4076576b98520c779be88d27543f2f515579a2e6c8621",
    ("PairConditioningSetDefaultAndCombine", "en"): "91fea2f69e04ad6739fb9a584039891f89be625e292b48d220f2bf4bc266ab87",
    ("PairConditioningSetDefaultAndCombine", "ru"): "c98dc4ee2617b9a42f52ff9789e77b096ba0267c5023cc06b980e900611d934d",
    ("PairConditioningSetProperties", "en"): "4b08da12bf0ce5eede66f8f719513e1771290b0a31979388be288641dbc9df94",
    ("PairConditioningSetProperties", "ru"): "994da9c5cd47c9714570166a5716e7f415e734268657124020765fbdf05994f9",
    ("PairConditioningSetPropertiesAndCombine", "en"): "3cd96610d2abab710c0253638b89c6b0417ee46e6b48e51543ee7b491e87751d",
    ("PairConditioningSetPropertiesAndCombine", "ru"): "07625c1a736087c6710dcc6f933404d1c82e64d5b259bdd983375db6e9b949e8",
}


def all_article_ids() -> set[str]:
    result: set[str] = set()
    for path in (CONTENT / "articles").rglob("manifest.json"):
        value = catalog.load_json(path)
        if isinstance(value, dict) and isinstance(value.get("articleId"), str):
            result.add(value["articleId"])
    return result


def workflow_scopes(payload: dict[str, Any]) -> Iterator[tuple[str, dict[str, Any]]]:
    if isinstance(payload.get("nodes"), list):
        yield "root", payload
    definitions = payload.get("definitions")
    subgraphs = definitions.get("subgraphs", []) if isinstance(definitions, dict) else []
    for subgraph in subgraphs:
        if isinstance(subgraph, dict) and isinstance(subgraph.get("nodes"), list):
            yield "subgraph", subgraph


def prose_without_code_or_urls(text: str) -> str:
    text = re.sub(r"`[^`]*`", "", text)
    text = re.sub(r"https?://[^)\s]+", "", text)
    return text


class PairConditioningContentTests(unittest.TestCase):
    def test_articles_recipes_ledgers_and_natural_russian(self) -> None:
        article_schema = catalog.load_json(CONTENT / "schemas" / "article.schema.v1.json")
        recipe_schema = catalog.load_json(CONTENT / "schemas" / "recipe.schema.v1.json")
        fragment_schema = catalog.load_json(CONTENT / "schemas" / "recipe-fragment.schema.v1.json")
        research_schema = catalog.load_json(CONTENT / "schemas" / "article-research.schema.v1.json")
        article_ids = all_article_ids()
        article_errors: list[str] = []
        recipe_errors: list[str] = []
        cliches = re.compile(
            r"важно отметить|стоит отметить|в современном мире|революционн|"
            r"данная нода|давайте разбер|подводя итог|мощный инструмент|не просто .{0,80}, а",
            flags=re.IGNORECASE,
        )
        ordinary_english = re.compile(
            r"\b(?:official|source-derived|runtime|frontend|workflow|input|output|metadata entries|"
            r"feature maps?|model family|files?|branches?|fallback|widgets?)\b",
            flags=re.IGNORECASE,
        )

        for article_id, spec in ARTICLE_SPECS.items():
            path = CONTENT / "articles" / "core" / spec["directory"] / "manifest.json"
            article = catalog.load_json(path)
            self.assertEqual([], catalog.json_schema_errors(article, article_schema), article_id)
            catalog.validate_article(path, article, article_errors)
            self.assertEqual(article_id, article["articleId"])
            self.assertEqual("ru", article["locale"])
            self.assertEqual(
                {
                    "classType": spec["classType"],
                    "pythonModule": "comfy_extras.nodes_hooks",
                    "packageId": "comfy-core",
                    "origin": "backend",
                    "aliases": [],
                },
                article["runtimeIdentity"],
            )
            self.assertEqual("draft", article["status"])
            self.assertEqual("in_review", article["editorial"]["state"])
            self.assertTrue(article["experimental"])
            self.assertEqual(spec["fingerprint"], article["editorial"]["schemaHash"])
            self.assertIn("human approval pending", article["editorial"]["reviewedBy"])
            self.assertIn(spec["recipe"], [asset["id"] for asset in article["assets"]])
            self.assertNotIn("approved", json.dumps(article).lower())

            relations = article["relations"]
            targets = list(relations["related"]) + list(relations["alternatives"])
            if relations["replacedBy"] is not None:
                targets.append(relations["replacedBy"])
            self.assertTrue(set(targets).issubset(article_ids), (article_id, targets))

            body = (path.parent / article["body"]).read_text(encoding="utf-8")
            self.assertEqual(10, len(re.findall(r"^## .+$", body, flags=re.MULTILINE)), article_id)
            self.assertIn("Редактор пока не проверил материал вручную.", body)
            self.assertNotIn("\ufffd", body)
            self.assertNotRegex(body, cliches)
            self.assertNotRegex(prose_without_code_or_urls(body), ordinary_english)

            ledger = catalog.load_json(CONTENT / "research" / "reviews" / f"{article_id}.json")
            self.assertEqual([], catalog.json_schema_errors(ledger, research_schema), article_id)
            self.assertEqual("fact_checked", ledger["state"])
            self.assertEqual("automated_assisted", ledger["reviewMode"])
            self.assertEqual(
                {
                    "classType": spec["classType"],
                    "pythonModule": "comfy_extras.nodes_hooks",
                    "origin": "backend",
                },
                ledger["node"],
            )
            self.assertTrue(ledger["checks"]["implementationRead"])
            self.assertTrue(ledger["checks"]["runtimeCompared"])
            self.assertTrue(ledger["checks"]["officialCasesInspected"])
            self.assertTrue(ledger["checks"]["exampleSchemaValidated"])
            self.assertFalse(ledger["checks"]["exampleExecuted"])
            self.assertTrue(ledger["checks"]["russianEdited"])
            self.assertTrue(ledger["checks"]["factsRecheckedAfterEditing"])
            self.assertTrue(any("Редактор пока" in gap for gap in ledger["knownGaps"]))

        self.assertEqual([], article_errors)

        for recipe_id, directory in RECIPE_DIRECTORIES.items():
            path = CONTENT / "recipes" / directory / "recipe.json"
            recipe = catalog.load_json(path)
            self.assertEqual([], catalog.json_schema_errors(recipe, recipe_schema), recipe_id)
            catalog.validate_recipe(path, recipe, article_ids, recipe_errors)
            self.assertEqual(recipe_id, recipe["recipeId"])
            self.assertEqual("ru", recipe["locale"])
            expected_article = next(
                article_id for article_id, spec in ARTICLE_SPECS.items() if spec["recipe"] == recipe_id
            )
            self.assertEqual([expected_article], recipe["articleIds"])
            self.assertEqual("in_review", recipe["editorial"]["state"])
            self.assertIn("human approval pending", recipe["editorial"]["reviewedBy"])
            self.assertNotIn("workflow", recipe)
            self.assertNotIn("approved", json.dumps(recipe).lower())
            body = (path.parent / recipe["body"]).read_text(encoding="utf-8")
            self.assertIn("Редактор пока не проверил материал вручную.", body)
            self.assertNotRegex(body, cliches)
            self.assertNotRegex(prose_without_code_or_urls(body), ordinary_english)

            fragment_path = path.parent / recipe["fragment"]["path"]
            fragment = catalog.load_json(fragment_path)
            self.assertEqual(recipe["fragment"]["id"], fragment["fragmentId"])
            self.assertEqual("nodes-wizard-fragment/1.0", recipe["fragment"]["format"])
            self.assertEqual([], catalog.json_schema_errors(fragment, fragment_schema), recipe_id)
            catalog.validate_fragment(fragment_path, fragment, recipe_errors)

        self.assertEqual([], recipe_errors)

    def test_runtime_fingerprints_ports_fragments_and_replacements(self) -> None:
        inventory = catalog.load_json(INVENTORY)
        for spec in ARTICLE_SPECS.values():
            definition = inventory[spec["classType"]]
            self.assertEqual(spec["classType"], definition["name"])
            self.assertEqual(spec["displayName"], definition["display_name"])
            self.assertEqual("", definition["description"])
            self.assertEqual("comfy_extras.nodes_hooks", definition["python_module"])
            self.assertEqual("advanced/hooks/cond pair", definition["category"])
            self.assertEqual(spec["fingerprint"], catalog.schema_fingerprint(spec["classType"], definition))
            self.assertEqual(spec["required"], definition["input_order"].get("required", []))
            self.assertEqual(spec["optional"], definition["input_order"].get("optional", []))
            self.assertEqual(["CONDITIONING", "CONDITIONING"], definition["output"])
            self.assertEqual(["positive", "negative"], definition["output_name"])
            self.assertEqual([False, False], definition["output_is_list"])
            self.assertTrue(definition["experimental"])
            self.assertFalse(definition["output_node"])
            self.assertFalse(definition["has_intermediate_output"])
            self.assertEqual([], definition["search_aliases"])
            for flag in ("deprecated", "dev_only", "api_node", "is_input_list"):
                self.assertFalse(definition.get(flag, False), (spec["classType"], flag))

        for class_type in ("PairConditioningSetProperties", "PairConditioningSetPropertiesAndCombine"):
            definition = inventory[class_type]
            self.assertEqual(
                ["FLOAT", {"default": 1.0, "min": 0.0, "max": 10.0, "step": 0.01}],
                definition["input"]["required"]["strength"],
            )
            self.assertEqual([["default", "mask bounds"]], definition["input"]["required"]["set_cond_area"])
            self.assertEqual(["MASK"], definition["input"]["optional"]["mask"])
            self.assertEqual(["HOOKS"], definition["input"]["optional"]["hooks"])
            self.assertEqual(["TIMESTEPS_RANGE"], definition["input"]["optional"]["timesteps"])

        fragments = {
            recipe_id: catalog.load_json(CONTENT / "recipes" / directory / "fragment.json")
            for recipe_id, directory in RECIPE_DIRECTORIES.items()
        }
        for recipe_id, fragment in fragments.items():
            fragment_spec = FRAGMENT_SPECS[recipe_id]
            self.assertEqual(1, len(fragment["nodes"]), recipe_id)
            node = fragment["nodes"][0]
            class_type = fragment_spec["classType"]
            self.assertEqual(class_type, node["classType"])
            self.assertEqual(fragment_spec["ref"], node["ref"])
            self.assertEqual(fragment_spec["settings"], node["settings"])
            self.assertEqual([], fragment["connections"])
            self.assertEqual(
                fragment_spec["externalInputs"],
                [(item["id"], item["type"], item["input"]) for item in fragment["externalInputs"]],
                recipe_id,
            )
            self.assertTrue(all(item["to"] == node["ref"] for item in fragment["externalInputs"]), recipe_id)
            definition = inventory[class_type]
            allowed_inputs = {
                **definition["input"].get("required", {}),
                **definition["input"].get("optional", {}),
            }
            provided = {item["input"] for item in fragment["externalInputs"]} | set(node.get("settings", {}))
            self.assertTrue(set(definition["input_order"].get("required", [])).issubset(provided), recipe_id)
            self.assertTrue(set(node.get("settings", {})).issubset(allowed_inputs), recipe_id)
            for item in fragment["externalInputs"]:
                self.assertIn(item["input"], allowed_inputs, (recipe_id, item))
                descriptor = allowed_inputs[item["input"]]
                self.assertIsInstance(descriptor[0], str, (recipe_id, item))
                self.assertEqual(descriptor[0], item["type"], (recipe_id, item))

            for key, value in node.get("settings", {}).items():
                descriptor = allowed_inputs[key]
                if isinstance(descriptor[0], list):
                    self.assertIn(value, descriptor[0], (recipe_id, key, value))
                elif descriptor[0] in {"FLOAT", "INT"}:
                    constraints = descriptor[1]
                    self.assertGreaterEqual(value, constraints.get("min", value), (recipe_id, key))
                    self.assertLessEqual(value, constraints.get("max", value), (recipe_id, key))

        replacements = catalog.load_json(REPLACEMENTS)
        serialized = json.dumps(replacements, ensure_ascii=False)
        for class_type in TARGET_TYPES:
            self.assertNotIn(class_type, replacements)
            self.assertNotIn(f'"new_node_id": "{class_type}"', serialized)

    def test_pinned_sources_are_present_exact_and_cover_semantics(self) -> None:
        expected_hashes = {
            SOURCE / "comfy_extras" / "nodes_hooks.py": "06218a53653b8b856fa9296d18ffce3d0fd05706a9b731112e44bc82f432e375",
            SOURCE / "comfy" / "hooks.py": "d9364d1e9d6f1b9cd6a0f09767a9ec8007b0577f9e2d245c403b4d325f909c65",
            SOURCE / "comfy" / "samplers.py": "aabb644b0f864cd18110e64a9216701b8cbebec7a54c425477ae36a821a99e8e",
            SOURCE / "node_helpers.py": "6e9e963b1538bdec3370721cfb16c02aa88a2891dafbbd9dd007c190f68ca935",
        }
        for path, digest in expected_hashes.items():
            self.assertTrue(path.is_file(), f"pinned evidence is absent: {path}")
            self.assertEqual(digest, hashlib.sha256(path.read_bytes()).hexdigest(), path)

        nodes = (SOURCE / "comfy_extras" / "nodes_hooks.py").read_text(encoding="utf-8")
        for marker in (
            "class PairConditioningSetProperties:",
            "NodeId = 'PairConditioningSetProperties'",
            "NodeName = 'Cond Pair Set Props'",
            'FUNCTION = "set_properties"',
            "class PairConditioningSetPropertiesAndCombine:",
            "NodeId = 'PairConditioningSetPropertiesAndCombine'",
            "NodeName = 'Cond Pair Set Props Combine'",
            "class PairConditioningCombine:",
            "NodeId = 'PairConditioningCombine'",
            "NodeName = 'Cond Pair Combine'",
            'FUNCTION = "combine"',
            "class PairConditioningSetDefaultAndCombine:",
            "NodeId = 'PairConditioningSetDefaultCombine'",
            "NodeName = 'Cond Pair Set Default Combine'",
            'FUNCTION = "set_default_and_combine"',
            "conds=[positive_NEW, negative_NEW]",
            "conds=[positive, negative], new_conds=[positive_NEW, negative_NEW]",
            "conds=[positive_A, negative_A], new_conds=[positive_B, negative_B]",
            "conds=[positive, negative], new_conds=[positive_DEFAULT, negative_DEFAULT]",
        ):
            self.assertIn(marker, nodes)

        hooks = (SOURCE / "comfy" / "hooks.py").read_text(encoding="utf-8")
        for marker in (
            "n = [t[0], t[1].copy()]",
            "new_hooks = hooks_tuple[0].clone_and_combine(hooks_tuple[1])",
            "if len(mask.shape) < 3:",
            "mask = mask.unsqueeze(0)",
            "'set_area_to_bounds': set_area_to_bounds",
            "'mask_strength': strength",
            '"start_percent": timestep_range[0]',
            "combined_conds.append(combine_conditioning([c, masked_c]))",
            "new_c = conditioning_set_values(new_c, {'default': True})",
            "combined_conds.append(combine_conditioning([c, new_c]))",
        ):
            self.assertIn(marker, hooks)

        samplers = (SOURCE / "comfy" / "samplers.py").read_text(encoding="utf-8")
        for marker in (
            "def finalize_default_conds(",
            "default_mults.append(torch.ones_like(x_in))",
            "curr_default_mult -= cond_obj.mult",
            "default_mults[i] -= cond_obj.mult",
            "torch.nn.functional.relu(mult, inplace=True)",
            "if torch.max(mult) == 0.0:",
            "p = p._replace(mult=mult)",
            "if 'default' in x:",
            "mask = mask * mask_strength",
            "mult = mask * strength",
            'if modified.get("set_area_to_bounds", False):',
            "bounds = torch.max(torch.abs(mask),dim=0).values.unsqueeze(0)",
            "timestep_start = s.percent_to_sigma(x['start_percent'])",
            "timestep_end = s.percent_to_sigma(x['end_percent'])",
        ):
            self.assertIn(marker, samplers)

    def test_documented_edge_cases_are_regression_guarded(self) -> None:
        props = (
            CONTENT / "articles" / "core" / "pair-conditioning-set-properties" / "ru.md"
        ).read_text(encoding="utf-8")
        props_combine = (
            CONTENT / "articles" / "core" / "pair-conditioning-set-properties-and-combine" / "ru.md"
        ).read_text(encoding="utf-8")
        default = (
            CONTENT / "articles" / "core" / "pair-conditioning-set-default-combine" / "ru.md"
        ).read_text(encoding="utf-8")
        for body in (props, props_combine):
            self.assertIn("перезаписываются", body)
            self.assertIn("`HOOKS`", body)
            self.assertIn("без проверки порядка", body)
            self.assertIn("ключ `strength`", body.lower())
            self.assertIn("только `mask_strength`", body)
        self.assertIn("R = ReLU(1 − Σ Mᵢ)", default)
        self.assertIn("наличие ключа `default`", default)
        self.assertIn("`default: false`", default)
        self.assertIn("масочный множитель запасной записи заменяется", default)

    def test_embedded_docs_are_pinned_and_discrepancies_are_guarded(self) -> None:
        self.assertTrue(DOCS_WHEEL.is_file(), f"pinned evidence is absent: {DOCS_WHEEL}")
        self.assertEqual(DOCS_SHA256, hashlib.sha256(DOCS_WHEEL.read_bytes()).hexdigest())
        with zipfile.ZipFile(DOCS_WHEEL) as archive:
            self.assertIsNone(archive.testzip())
            names = set(archive.namelist())
            for (directory, locale), digest in DOC_HASHES.items():
                member = f"comfyui_embedded_docs/docs/{directory}/{locale}.md"
                self.assertIn(member, names)
                self.assertEqual(digest, hashlib.sha256(archive.read(member)).hexdigest(), member)

            self.assertFalse(
                any(name.startswith("comfyui_embedded_docs/docs/PairConditioningSetDefaultCombine/") for name in names)
            )
            props_en = archive.read(
                "comfyui_embedded_docs/docs/PairConditioningSetProperties/en.md"
            ).decode("utf-8")
            self.assertIn("strength multiplier applied to the conditioning", props_en)
            combine_en = archive.read(
                "comfyui_embedded_docs/docs/PairConditioningSetPropertiesAndCombine/en.md"
            ).decode("utf-8")
            self.assertIn("blend multiple conditioning sources", combine_en)
            default_en = archive.read(
                "comfyui_embedded_docs/docs/PairConditioningSetDefaultAndCombine/en.md"
            ).decode("utf-8")
            self.assertIn("default counterparts", default_en)
            self.assertNotIn("remaining", default_en.lower())

    def test_workflow_wheel_integrity_and_full_zero_census(self) -> None:
        self.assertTrue(WORKFLOW_WHEEL.is_file(), f"pinned evidence is absent: {WORKFLOW_WHEEL}")
        self.assertEqual(WORKFLOW_SHA256, hashlib.sha256(WORKFLOW_WHEEL.read_bytes()).hexdigest())
        exact_counts: Counter[str] = Counter()
        insensitive_counts: Counter[str] = Counter()
        scope_counts: Counter[tuple[str, str]] = Counter()
        raw_counts: Counter[str] = Counter()
        json_count = root_count = subgraph_count = node_count = 0

        with zipfile.ZipFile(WORKFLOW_WHEEL) as archive:
            self.assertIsNone(archive.testzip())
            self.assertEqual(517, len(archive.namelist()))
            record_name = next(name for name in archive.namelist() if name.endswith(".dist-info/RECORD"))
            verified = unhashed = 0
            for name, digest_spec, size in csv.reader(archive.read(record_name).decode("utf-8").splitlines()):
                self.assertIn(name, archive.namelist())
                if not digest_spec:
                    unhashed += 1
                    continue
                algorithm, expected = digest_spec.split("=", 1)
                data = archive.read(name)
                actual = base64.urlsafe_b64encode(hashlib.new(algorithm, data).digest()).decode("ascii").rstrip("=")
                self.assertEqual(expected, actual)
                self.assertEqual(int(size), len(data))
                verified += 1
            self.assertEqual((516, 1), (verified, unhashed))

            for member in archive.namelist():
                data = archive.read(member)
                for class_type in TARGET_TYPES:
                    raw_counts[class_type] += data.count(class_type.encode("utf-8"))
                if not member.endswith(".json"):
                    continue
                json_count += 1
                payload = json.loads(data.decode("utf-8"))
                if not isinstance(payload, dict):
                    continue
                if isinstance(payload.get("nodes"), list):
                    root_count += 1
                for scope, graph in workflow_scopes(payload):
                    if scope == "subgraph":
                        subgraph_count += 1
                    nodes = [node for node in graph.get("nodes", []) if isinstance(node, dict)]
                    node_count += len(nodes)
                    for node in nodes:
                        class_type = node.get("type")
                        if class_type in TARGET_TYPES:
                            exact_counts[class_type] += 1
                            scope_counts[(class_type, scope)] += 1
                        if isinstance(class_type, str):
                            for target in TARGET_TYPES:
                                if class_type.casefold() == target.casefold():
                                    insensitive_counts[target] += 1

        self.assertEqual((512, 496, 272, 8120), (json_count, root_count, subgraph_count, node_count))
        self.assertEqual(Counter(), exact_counts)
        self.assertEqual(Counter(), insensitive_counts)
        self.assertEqual(Counter(), scope_counts)
        self.assertEqual(Counter(), raw_counts)

    def test_exact_source_synthetic_probe(self) -> None:
        self.assertTrue(PROBE.is_file(), f"probe is absent: {PROBE}")
        result = subprocess.run(
            [sys.executable, "-X", "utf8", str(PROBE)],
            cwd=ROOT,
            text=True,
            capture_output=True,
            timeout=60,
            check=False,
            env={**os.environ, "PYTHONUTF8": "1"},
        )
        self.assertEqual(0, result.returncode, result.stderr or result.stdout)
        payload = json.loads(result.stdout.strip().splitlines()[-1])

        self.assertEqual(["pos-a", "pos-b", "pos-b-2"], payload["combine"]["positiveOrder"])
        self.assertEqual(["neg-a", "neg-b"], payload["combine"]["negativeOrder"])
        self.assertTrue(payload["combine"]["newOutputLists"])
        self.assertTrue(payload["combine"]["entriesPreserved"])
        self.assertTrue(payload["combine"]["inputsUnchanged"])

        self.assertEqual(
            {
                "areaIgnoredWithoutMask": True,
                "negativeListIdentity": True,
                "positiveListIdentity": True,
                "strengthIgnoredWithoutMask": True,
            },
            payload["noOptionalProperties"],
        )

        props = payload["properties"]
        self.assertTrue(props["embeddingIdentity"])
        self.assertTrue(props["metadataCopied"])
        self.assertTrue(props["sourceMetadataUnchanged"])
        self.assertEqual([1, 2, 2], props["maskShape"])
        self.assertTrue(props["maskSharesStorage"])
        self.assertTrue(props["negativeMaskSharesStorage"])
        self.assertFalse(props["maskSharedAcrossPair"])
        self.assertEqual(0.6, props["maskStrength"])
        self.assertTrue(props["bounds"])
        self.assertEqual([0.2, 0.8], props["timesteps"])
        self.assertEqual(["old", "new"], props["combinedHookLabels"])
        self.assertTrue(props["hookCacheShared"])
        self.assertEqual(1, props["cloneCalls"])

        merged = payload["propertiesAndCombine"]
        self.assertEqual(["base-pos", "added-pos"], merged["positiveOrder"])
        self.assertEqual(["base-neg", "added-neg"], merged["negativeOrder"])
        self.assertTrue(merged["baseEntryIdentity"])
        self.assertTrue(merged["newEmbeddingIdentity"])
        self.assertTrue(merged["baseMetadataUnchanged"])
        self.assertTrue(merged["newMetadataUnchanged"])
        self.assertEqual(0.25, merged["newMaskStrength"])
        self.assertFalse(merged["newBounds"])
        self.assertEqual([0.1, 0.9], merged["newTimesteps"])
        self.assertEqual(["merge-old", "merge-new"], merged["hookLabels"])
        self.assertTrue(merged["hookCacheShared"])
        self.assertEqual(1, merged["hookCloneCalls"])
        self.assertTrue(merged["hookSourcesUnchanged"])

        default = payload["defaultCombine"]
        self.assertEqual(["base-pos", "default-pos"], default["positiveOrder"])
        self.assertEqual(["base-neg", "default-neg"], default["negativeOrder"])
        self.assertTrue(default["baseEntryIdentity"])
        self.assertEqual([True, True], default["defaultFlags"])
        self.assertTrue(default["existingFalseOverwritten"])
        self.assertEqual(["inherited", "default"], default["hookLabels"])
        self.assertTrue(default["hookCacheShared"])
        self.assertTrue(default["sourceDefaultsUnchanged"])

        self.assertTrue(payload["emptyHooks"]["attachedDespiteFalsy"])
        self.assertTrue(payload["emptyHooks"]["metadataCopied"])

        overwrite = payload["overwriteSemantics"]
        self.assertTrue(overwrite["sourceUnchanged"])
        self.assertTrue(overwrite["maskReplaced"])
        self.assertEqual(0.4, overwrite["maskStrength"])
        self.assertTrue(overwrite["bounds"])
        self.assertEqual([0.25, 0.75], overwrite["timesteps"])
        self.assertEqual(7.0, overwrite["generalStrengthPreserved"])
        self.assertEqual([0.9, 0.1], overwrite["reversedRangePreserved"])

        sampler_mask = payload["samplerMask"]
        self.assertTrue(sampler_mask["maskStrengthApplied"])
        self.assertTrue(sampler_mask["generalStrengthMultiplied"])
        self.assertEqual([10, 11, 3, 4], sampler_mask["boundsUnionUsesAbsoluteMask"])
        self.assertTrue(sampler_mask["defaultLeavesAreaUnset"])
        self.assertEqual([8, 8, 0, 0], sampler_mask["emptyBoundsArea"])

        converted = payload["timestepConversion"]
        self.assertEqual([0.9, 0.1], converted["percentCalls"])
        self.assertAlmostEqual(0.1, converted["sigmaRange"][0])
        self.assertAlmostEqual(0.9, converted["sigmaRange"][1])
        self.assertTrue(converted["reversedRangeInactive"])

        residual = payload["defaultResidual"]
        self.assertTrue(residual["maskedResidualExact"])
        self.assertTrue(residual["ownMaskMultiplierReplaced"])
        self.assertTrue(residual["fullCoverageSkipsDefault"])
        self.assertTrue(residual["overlapClampedToZero"])
        self.assertTrue(residual["overlapOutsideMaskRemainsOne"])
        self.assertEqual([1, 2, 4, 4], residual["areaInputShape"])
        self.assertEqual([1, 2, 8, 8], residual["areaMultiplierShape"])


if __name__ == "__main__":
    unittest.main()
