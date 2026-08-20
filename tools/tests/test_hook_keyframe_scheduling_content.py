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
    "core.set-hook-keyframes": {
        "directory": "set-hook-keyframes",
        "classType": "SetHookKeyframes",
        "fingerprint": "sha256:625e44cc89e11ae8671c4519cd996d37a099c5f1f82e7062415f4481f8c42109",
        "required": ["hooks"],
        "optional": ["hook_kf"],
        "recipe": "recipe.two-stage-hook-keyframes",
    },
    "core.create-hook-keyframe": {
        "directory": "create-hook-keyframe",
        "classType": "CreateHookKeyframe",
        "fingerprint": "sha256:eb3af671e525c593499573e62b8510cfce5c1e7ecd7fafe2b21ecefa482cad92",
        "required": ["strength_mult", "start_percent"],
        "optional": ["prev_hook_kf"],
        "recipe": "recipe.two-stage-hook-keyframes",
    },
    "core.create-hook-keyframes-interpolated": {
        "directory": "create-hook-keyframes-interpolated",
        "classType": "CreateHookKeyframesInterpolated",
        "fingerprint": "sha256:c9faffe5f1dad2d8f4ba54051ea481dcf078ba99428ff61565571c797375abd8",
        "required": ["strength_start", "strength_end", "interpolation", "start_percent", "end_percent", "keyframes_count", "print_keyframes"],
        "optional": ["prev_hook_kf"],
        "recipe": "recipe.interpolate-hook-strength",
    },
    "core.create-hook-keyframes-from-floats": {
        "directory": "create-hook-keyframes-from-floats",
        "classType": "CreateHookKeyframesFromFloats",
        "fingerprint": "sha256:f08a03b39714b8c60e3350b2dab9212724204b540018856dffdf46ac10898fd0",
        "required": ["floats_strength", "start_percent", "end_percent", "print_keyframes"],
        "optional": ["prev_hook_kf"],
        "recipe": "recipe.hook-strengths-from-floats",
    },
}

RECIPE_DIRECTORIES = {
    "recipe.two-stage-hook-keyframes": "two-stage-hook-keyframes",
    "recipe.interpolate-hook-strength": "interpolate-hook-strength",
    "recipe.hook-strengths-from-floats": "hook-strengths-from-floats",
}

ROOT = catalog.ROOT
CONTENT = catalog.CONTENT
SOURCE = ROOT / ".comfyui-source-0.32.0"
INVENTORY = CONTENT / "runtime" / "comfyui-0.32.0.object-info.json"
REPLACEMENTS = CONTENT / "runtime" / "comfyui-0.32.0.node-replacements.json"
DOCS_WHEEL = ROOT / ".upstream-cache" / "comfyui_embedded_docs-0.5.9-py3-none-any.whl"
WORKFLOW_WHEEL = ROOT / ".upstream-cache" / "comfyui_workflow_templates_json-0.1.42-py3-none-any.whl"
PROBE = ROOT / "tools" / "tests" / "hook_keyframe_scheduling_synthetic_probe.py"
TARGET_TYPES = {spec["classType"] for spec in ARTICLE_SPECS.values()}
DOCS_SHA256 = "30afae432a71c96aa59421d0f37388c66ff6572b8cbeee8ff045e4d5f84f896c"
WORKFLOW_SHA256 = "242982d65e1c51ca03d892bc1009bb6843f457e7dfc0c20afe6438770b7a14a3"
DOC_HASHES = {
    ("SetHookKeyframes", "en"): "33164aec0850ee1819c6aadcc16f04d42784618ec5419c46a67a4e88dc516a6e",
    ("SetHookKeyframes", "ru"): "dad1fa97dd743760744f7e163ef554c5c80344383da345c735675bffafc5046b",
    ("CreateHookKeyframe", "en"): "c29b27f41cd47f9faf9c2502c44c71a0ae28dbf95dbb37526102955eb7eada84",
    ("CreateHookKeyframe", "ru"): "b5a5a4875af29f280ad2f68b8a6ae746bfb30489b2878c279805a6f011158818",
    ("CreateHookKeyframesInterpolated", "en"): "2107b9772a2e3e2071e3013b720ae4d28d007193183440ca9b3d320379be92b6",
    ("CreateHookKeyframesInterpolated", "ru"): "a9a26796bc585bcb57d28afb1fce3f24ddc6b1c42acfab07328f33216340ad63",
    ("CreateHookKeyframesFromFloats", "en"): "5f6005e0a19c680c44cd5c77757df699d5443d09afe345536c015a4c9d3193d7",
    ("CreateHookKeyframesFromFloats", "ru"): "29e2d55f79412baffcc556a864644e1516acecaa6f61782cffd868650dcb9848",
}


def all_article_ids() -> set[str]:
    result: set[str] = set()
    for path in (CONTENT / "articles").rglob("manifest.json"):
        payload = catalog.load_json(path)
        if isinstance(payload, dict) and isinstance(payload.get("articleId"), str):
            result.add(payload["articleId"])
    return result


def workflow_scopes(payload: dict[str, Any]) -> Iterator[dict[str, Any]]:
    if isinstance(payload.get("nodes"), list):
        yield payload
    definitions = payload.get("definitions")
    subgraphs = definitions.get("subgraphs", []) if isinstance(definitions, dict) else []
    for graph in subgraphs:
        if isinstance(graph, dict) and isinstance(graph.get("nodes"), list):
            yield graph


def descriptor(definition: dict[str, Any], name: str) -> list[Any] | None:
    for section in ("required", "optional", "hidden"):
        item = definition.get("input", {}).get(section, {}).get(name)
        if isinstance(item, list):
            return item
    return None


class HookKeyframeSchedulingContentTests(unittest.TestCase):
    def test_articles_recipes_ledgers_and_language(self) -> None:
        for path in (SOURCE, INVENTORY, REPLACEMENTS, DOCS_WHEEL, WORKFLOW_WHEEL, PROBE):
            self.assertTrue(path.exists(), f"pinned evidence is missing: {path}")

        schemas = {
            "article": catalog.load_json(CONTENT / "schemas" / "article.schema.v1.json"),
            "recipe": catalog.load_json(CONTENT / "schemas" / "recipe.schema.v1.json"),
            "fragment": catalog.load_json(CONTENT / "schemas" / "recipe-fragment.schema.v1.json"),
            "research": catalog.load_json(CONTENT / "schemas" / "article-research.schema.v1.json"),
        }
        ids = all_article_ids()
        article_errors: list[str] = []
        recipe_errors: list[str] = []
        cliches = re.compile(
            r"важно отметить|стоит отметить|в современном мире|революционн|данная нода|"
            r"давайте разбер|подводя итог|мощный инструмент|не просто .{0,80}, а",
            re.IGNORECASE,
        )
        ordinary_english = re.compile(
            r"\b(?:official case|source-derived|root workflows?|metadata entries|input block|widgets?)\b",
            re.IGNORECASE,
        )

        for article_id, spec in ARTICLE_SPECS.items():
            path = CONTENT / "articles" / "core" / spec["directory"] / "manifest.json"
            article = catalog.load_json(path)
            self.assertEqual([], catalog.json_schema_errors(article, schemas["article"]), article_id)
            catalog.validate_article(path, article, article_errors)
            self.assertEqual(article_id, article["articleId"])
            self.assertEqual("draft", article["status"])
            self.assertEqual("in_review", article["editorial"]["state"])
            self.assertTrue(article["experimental"])
            self.assertEqual(spec["classType"], article["runtimeIdentity"]["classType"])
            self.assertEqual(spec["fingerprint"], article["editorial"]["schemaHash"])
            self.assertIn(spec["recipe"], [asset["id"] for asset in article["assets"]])
            self.assertNotIn("approved", json.dumps(article, ensure_ascii=False).lower())

            targets = article["relations"]["related"] + article["relations"]["alternatives"]
            if article["relations"]["replacedBy"] is not None:
                targets.append(article["relations"]["replacedBy"])
            self.assertTrue(set(targets).issubset(ids), (article_id, targets))

            body = (path.parent / article["body"]).read_text(encoding="utf-8")
            self.assertEqual(10, len(re.findall(r"^## .+$", body, re.MULTILINE)), article_id)
            self.assertIn("Редактор пока не проверил материал вручную.", body)
            self.assertNotIn("\ufffd", body)
            self.assertNotRegex(body, cliches)
            prose = re.sub(r"`[^`]+`|https?://\S+", "", body)
            self.assertNotRegex(prose, ordinary_english)

            ledger = catalog.load_json(CONTENT / "research" / "reviews" / f"{article_id}.json")
            self.assertEqual([], catalog.json_schema_errors(ledger, schemas["research"]), article_id)
            self.assertEqual("fact_checked", ledger["state"])
            self.assertEqual("automated_assisted", ledger["reviewMode"])
            self.assertFalse(ledger["checks"]["exampleExecuted"])
            self.assertTrue(ledger["checks"]["russianEdited"])
            self.assertTrue(ledger["checks"]["factsRecheckedAfterEditing"])
            self.assertTrue(any("Редактор пока" in gap for gap in ledger["knownGaps"]))

        self.assertEqual([], article_errors)

        for recipe_id, directory in RECIPE_DIRECTORIES.items():
            path = CONTENT / "recipes" / directory / "recipe.json"
            recipe = catalog.load_json(path)
            self.assertEqual([], catalog.json_schema_errors(recipe, schemas["recipe"]), recipe_id)
            catalog.validate_recipe(path, recipe, ids, recipe_errors)
            self.assertEqual(recipe_id, recipe["recipeId"])
            self.assertEqual("in_review", recipe["editorial"]["state"])
            self.assertNotIn("workflow", recipe)
            self.assertNotIn("approved", json.dumps(recipe).lower())
            body = (path.parent / recipe["body"]).read_text(encoding="utf-8")
            self.assertIn("Редактор пока не проверил материал вручную.", body)
            self.assertNotRegex(body, cliches)

            fragment_path = path.parent / recipe["fragment"]["path"]
            fragment = catalog.load_json(fragment_path)
            self.assertEqual([], catalog.json_schema_errors(fragment, schemas["fragment"]), recipe_id)
            catalog.validate_fragment(fragment_path, fragment, recipe_errors)

        self.assertEqual([], recipe_errors)

    def test_runtime_fingerprints_ports_constraints_and_replacements(self) -> None:
        inventory = catalog.load_json(INVENTORY)
        article_ids: Counter[str] = Counter()
        class_types: Counter[str] = Counter()
        for path in (CONTENT / "articles").rglob("manifest.json"):
            article = catalog.load_json(path)
            article_ids[article["articleId"]] += 1
            class_type = article.get("runtimeIdentity", {}).get("classType")
            if isinstance(class_type, str):
                class_types[class_type] += 1

        for article_id, spec in ARTICLE_SPECS.items():
            definition = inventory[spec["classType"]]
            self.assertEqual(1, article_ids[article_id])
            self.assertEqual(1, class_types[spec["classType"]])
            self.assertEqual("comfy_extras.nodes_hooks", definition["python_module"])
            self.assertEqual("advanced/hooks/scheduling", definition["category"])
            self.assertEqual(spec["required"], definition["input_order"]["required"])
            self.assertEqual(spec["optional"], definition["input_order"]["optional"])
            self.assertTrue(definition["experimental"])
            self.assertFalse(definition["output_node"])
            self.assertFalse(definition["is_input_list"])
            for flag in ("deprecated", "dev_only", "api_node"):
                self.assertFalse(definition.get(flag, False))
            self.assertEqual(spec["fingerprint"], catalog.schema_fingerprint(spec["classType"], definition))

        setter = inventory["SetHookKeyframes"]
        self.assertEqual(["HOOKS"], setter["input"]["required"]["hooks"])
        self.assertEqual(["HOOK_KEYFRAMES"], setter["input"]["optional"]["hook_kf"])
        self.assertEqual(["HOOKS"], setter["output"])
        self.assertEqual(["HOOKS"], setter["output_name"])

        single = inventory["CreateHookKeyframe"]
        self.assertEqual(["FLOAT", {"default": 1.0, "min": -20.0, "max": 20.0, "step": 0.01}], single["input"]["required"]["strength_mult"])
        self.assertEqual(["FLOAT", {"default": 0.0, "min": 0.0, "max": 1.0, "step": 0.001}], single["input"]["required"]["start_percent"])
        self.assertEqual(["HOOK_KEYFRAMES"], single["output"])
        self.assertEqual(["HOOK_KF"], single["output_name"])

        interp = inventory["CreateHookKeyframesInterpolated"]
        self.assertEqual([["linear", "ease_in", "ease_out", "ease_in_out"]], interp["input"]["required"]["interpolation"])
        self.assertEqual(["INT", {"default": 5, "min": 2, "max": 100, "step": 1}], interp["input"]["required"]["keyframes_count"])
        for name in ("strength_start", "strength_end"):
            self.assertEqual(["FLOAT", {"default": 1.0, "min": 0.0, "max": 10.0, "step": 0.001}], interp["input"]["required"][name])

        floats = inventory["CreateHookKeyframesFromFloats"]
        self.assertEqual(["FLOATS", {"default": -1, "min": -1, "step": 0.001, "forceInput": True}], floats["input"]["required"]["floats_strength"])
        self.assertEqual(["HOOK_KEYFRAMES"], floats["input"]["optional"]["prev_hook_kf"])
        self.assertEqual(
            [],
            [class_type for class_type, definition in inventory.items() if "FLOATS" in definition.get("output", [])],
            "clean ComfyUI 0.32.0 must not silently gain a core FLOATS producer",
        )

        replacements = catalog.load_json(REPLACEMENTS)
        serialized = json.dumps(replacements, ensure_ascii=False)
        for class_type in TARGET_TYPES:
            self.assertNotIn(class_type, replacements)
            self.assertNotIn(f'"new_node_id": "{class_type}"', serialized)

    def test_fragments_are_typed_complete_and_use_exact_settings(self) -> None:
        inventory = catalog.load_json(INVENTORY)
        fragments = {
            recipe_id: catalog.load_json(CONTENT / "recipes" / directory / "fragment.json")
            for recipe_id, directory in RECIPE_DIRECTORIES.items()
        }
        expected_nodes = {
            "recipe.two-stage-hook-keyframes": ["CreateHookKeyframe", "CreateHookKeyframe", "SetHookKeyframes"],
            "recipe.interpolate-hook-strength": ["CreateHookKeyframesInterpolated", "SetHookKeyframes"],
            "recipe.hook-strengths-from-floats": ["CreateHookKeyframesFromFloats", "SetHookKeyframes"],
        }

        for recipe_id, fragment in fragments.items():
            self.assertEqual(expected_nodes[recipe_id], [node["classType"] for node in fragment["nodes"]])
            refs = {node["ref"]: node for node in fragment["nodes"]}
            supplied = {ref: set() for ref in refs}
            for external in fragment["externalInputs"]:
                definition = inventory[refs[external["to"]]["classType"]]
                item = descriptor(definition, external["input"])
                self.assertIsNotNone(item, external)
                self.assertEqual(external["type"], item[0])
                supplied[external["to"]].add(external["input"])
            for connection in fragment["connections"]:
                source = inventory[refs[connection["from"]]["classType"]]
                dest = inventory[refs[connection["to"]]["classType"]]
                self.assertIn(connection["output"], source["output_name"])
                index = source["output_name"].index(connection["output"])
                item = descriptor(dest, connection["input"])
                self.assertIsNotNone(item, connection)
                self.assertEqual(source["output"][index], item[0])
                supplied[connection["to"]].add(connection["input"])
            for ref, node in refs.items():
                definition = inventory[node["classType"]]
                for name, value in node["settings"].items():
                    item = descriptor(definition, name)
                    self.assertIsNotNone(item, (recipe_id, ref, name))
                    kind = item[0]
                    options = item[1] if len(item) > 1 and isinstance(item[1], dict) else {}
                    if kind in ("FLOAT", "INT"):
                        self.assertIsInstance(value, (int, float))
                        self.assertGreaterEqual(value, options["min"])
                        self.assertLessEqual(value, options["max"])
                    elif kind == "BOOLEAN":
                        self.assertIsInstance(value, bool)
                    elif isinstance(kind, list):
                        self.assertIn(value, kind)
                required = set(definition["input_order"].get("required", []))
                self.assertTrue(required.issubset(set(node["settings"]) | supplied[ref]), (recipe_id, ref))

        two = fragments["recipe.two-stage-hook-keyframes"]
        self.assertEqual({"strength_mult": 1.0, "start_percent": 0.0}, two["nodes"][0]["settings"])
        self.assertEqual({"strength_mult": 0.0, "start_percent": 0.5}, two["nodes"][1]["settings"])
        self.assertEqual({}, two["nodes"][2]["settings"])
        curve = fragments["recipe.interpolate-hook-strength"]["nodes"][0]["settings"]
        self.assertEqual("ease_out", curve["interpolation"])
        self.assertEqual((1.0, 0.0, 5), (curve["strength_start"], curve["strength_end"], curve["keyframes_count"]))
        floats = fragments["recipe.hook-strengths-from-floats"]
        self.assertEqual(
            [("strengths", "FLOATS", "floats_strength"), ("hooks", "HOOKS", "hooks")],
            [(item["id"], item["type"], item["input"]) for item in floats["externalInputs"]],
        )

    def test_pinned_source_hashes_and_branch_markers(self) -> None:
        expected = {
            SOURCE / "comfy_extras" / "nodes_hooks.py": "06218a53653b8b856fa9296d18ffce3d0fd05706a9b731112e44bc82f432e375",
            SOURCE / "comfy" / "hooks.py": "d9364d1e9d6f1b9cd6a0f09767a9ec8007b0577f9e2d245c403b4d325f909c65",
        }
        for path, digest in expected.items():
            self.assertEqual(digest, hashlib.sha256(path.read_bytes()).hexdigest(), path)

        nodes = (SOURCE / "comfy_extras" / "nodes_hooks.py").read_text(encoding="utf-8")
        for marker in (
            "class SetHookKeyframes:",
            "if hook_kf is not None:",
            "hooks.set_keyframes_on_hooks(hook_kf=hook_kf)",
            "class CreateHookKeyframe:",
            "HookKeyframe(strength=strength_mult, start_percent=start_percent)",
            "class CreateHookKeyframesInterpolated:",
            "method=comfy.hooks.InterpolationMethod.LINEAR",
            "method=interpolation",
            "guarantee_steps = 1",
            "class CreateHookKeyframesFromFloats:",
            "if type(floats_strength) in (float, int):",
            "floats_strength = [float(floats_strength)]",
            "elif isinstance(floats_strength, Iterable):",
            "    SetHookKeyframes,",
            "    CreateHookKeyframe,",
            "    CreateHookKeyframesInterpolated,",
            "    CreateHookKeyframesFromFloats,",
        ):
            self.assertIn(marker, nodes)

        hooks = (SOURCE / "comfy" / "hooks.py").read_text(encoding="utf-8")
        for marker in (
            "hook_kf = hook_kf.clone()",
            "hook.hook_keyframe = hook_kf",
            "self.keyframes = get_sorted_list_via_attr(self.keyframes, \"start_percent\")",
            "self._current_keyframe = self.keyframes[0]",
            "keyframe.start_t = model.model_sampling.percent_to_sigma(keyframe.start_percent)",
            "if self.start_t > max_sigma:",
            "if self._current_used_steps >= self._current_keyframe.get_effective_guarantee_steps(max_sigma):",
            "for i in range(self._current_index+1, len(self.keyframes)):",
            "elif keyframe.start_percent == prev_keyframe.start_percent:",
            "prev_keyframe = keyframe",
            '_LIST = [LINEAR, EASE_IN, EASE_OUT, EASE_IN_OUT]',
            "weights = diff * np.power(index, 2) + num_from",
            "weights = diff * (1 - np.power(1 - index, 2)) + num_from",
            "weights = diff * ((1 - np.cos(index * np.pi)) / 2) + num_from",
        ):
            self.assertIn(marker, hooks)

    def test_embedded_docs_hashes_and_interpolation_discrepancy(self) -> None:
        self.assertEqual(DOCS_SHA256, hashlib.sha256(DOCS_WHEEL.read_bytes()).hexdigest())
        with zipfile.ZipFile(DOCS_WHEEL) as archive:
            self.assertIsNone(archive.testzip())
            for (class_type, locale), digest in DOC_HASHES.items():
                name = f"comfyui_embedded_docs/docs/{class_type}/{locale}.md"
                data = archive.read(name)
                self.assertEqual(digest, hashlib.sha256(data).hexdigest(), name)

            interp_en = archive.read("comfyui_embedded_docs/docs/CreateHookKeyframesInterpolated/en.md").decode("utf-8")
            for unsupported in ("EASE_OUT_IN", "SINE", "CUBIC", "QUARTIC", "QUINTIC", "EXPO", "CIRC", "BACK", "BOUNCE", "ELASTIC"):
                self.assertIn(unsupported, interp_en)
            inventory = catalog.load_json(INVENTORY)
            choices = inventory["CreateHookKeyframesInterpolated"]["input"]["required"]["interpolation"][0]
            self.assertEqual(["linear", "ease_in", "ease_out", "ease_in_out"], choices)
            self.assertTrue(all(item.lower() not in choices for item in ("SINE", "CUBIC", "BOUNCE")))

            floats_en = archive.read("comfyui_embedded_docs/docs/CreateHookKeyframesFromFloats/en.md").decode("utf-8")
            self.assertIn("single float value or list of float values", floats_en)
            self.assertIn("first keyframe is guaranteed to have at least one step", floats_en)

    def test_workflow_wheel_integrity_and_zero_census(self) -> None:
        self.assertEqual(WORKFLOW_SHA256, hashlib.sha256(WORKFLOW_WHEEL.read_bytes()).hexdigest())
        exact: Counter[str] = Counter()
        insensitive: Counter[str] = Counter()
        raw: Counter[str] = Counter()
        json_count = root_count = subgraph_count = node_count = 0
        with zipfile.ZipFile(WORKFLOW_WHEEL) as archive:
            self.assertIsNone(archive.testzip())
            self.assertEqual(517, len(archive.namelist()))
            record = next(name for name in archive.namelist() if name.endswith(".dist-info/RECORD"))
            verified = unhashed = 0
            for name, digest_spec, size in csv.reader(archive.read(record).decode("utf-8").splitlines()):
                if not digest_spec:
                    unhashed += 1
                    continue
                algorithm, expected = digest_spec.split("=", 1)
                data = archive.read(name)
                actual = base64.urlsafe_b64encode(hashlib.new(algorithm, data).digest()).decode("ascii").rstrip("=")
                self.assertEqual(expected, actual, name)
                self.assertEqual(int(size), len(data), name)
                verified += 1
            self.assertEqual((516, 1), (verified, unhashed))

            for member in archive.namelist():
                data = archive.read(member)
                for target in TARGET_TYPES:
                    raw[target] += data.count(target.encode())
                if not member.endswith(".json"):
                    continue
                json_count += 1
                payload = json.loads(data.decode("utf-8"))
                if not isinstance(payload, dict):
                    continue
                if isinstance(payload.get("nodes"), list):
                    root_count += 1
                graphs = list(workflow_scopes(payload))
                subgraph_count += max(0, len(graphs) - (1 if isinstance(payload.get("nodes"), list) else 0))
                for graph in graphs:
                    nodes = [node for node in graph.get("nodes", []) if isinstance(node, dict)]
                    node_count += len(nodes)
                    for node in nodes:
                        node_type = node.get("type")
                        if node_type in TARGET_TYPES:
                            exact[node_type] += 1
                        if isinstance(node_type, str):
                            for target in TARGET_TYPES:
                                if node_type.casefold() == target.casefold():
                                    insensitive[target] += 1

        self.assertEqual((512, 496, 272, 8120), (json_count, root_count, subgraph_count, node_count))
        self.assertEqual(Counter(), exact)
        self.assertEqual(Counter(), insensitive)
        self.assertEqual(Counter(), raw)

    def test_safe_exact_source_probe(self) -> None:
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

        setter = payload["set"]
        for key in ("noneReturnsInputIdentity", "providedCreatesClone", "inputHooksUnchanged", "outputHooksAreClones", "outputHooksShareOneSchedule", "scheduleWasCloned", "emptyStillClonesHooks"):
            self.assertTrue(setter[key], key)
        self.assertEqual([], setter["emptyClearsSchedule"])
        self.assertEqual(1.0, setter["emptyStrengthDefaultsToOne"])
        self.assertEqual(setter["sourceBeforeMutation"], setter["outputAfterSourceMutation"])

        single = payload["single"]
        self.assertTrue(single["outputIsClone"])
        self.assertEqual([[0.8, 8.0, 1]], single["previousUnchanged"])
        self.assertEqual([[0.2, -2.0, 1], [0.8, 8.0, 1]], single["sortedOutput"])
        self.assertEqual([[0.8, 8.0, 1], [0.8, 3.0, 1]], single["equalPercentStable"])

        interp = payload["interpolated"]
        self.assertEqual(["linear", "ease_in", "ease_out", "ease_in_out"], interp["allowedMethods"])
        self.assertEqual([[0.0, 1.0, 1], [0.25, 1.5, 0], [0.5, 2.0, 0], [0.75, 2.5, 0], [1.0, 3.0, 0]], interp["linear"])
        self.assertEqual(0.25, interp["ease"]["ease_in"][1][1])
        self.assertEqual(0.75, interp["ease"]["ease_out"][1][1])
        self.assertEqual(0.5, interp["ease"]["ease_in_out"][1][1])
        self.assertAlmostEqual(3.0, interp["descendingSorted"][0][1])
        self.assertEqual(0, interp["descendingSorted"][0][2])
        self.assertAlmostEqual(1.0, interp["descendingSorted"][-1][1])
        self.assertEqual(1, interp["descendingSorted"][-1][2])

        floats = payload["fromFloats"]
        self.assertEqual([0.2, 0.4, 0.8], [row[1] for row in floats["listed"]])
        self.assertAlmostEqual(0.1, floats["listed"][0][0], places=6)
        self.assertAlmostEqual(0.9, floats["listed"][-1][0], places=6)
        self.assertAlmostEqual(0.3, floats["scalarUsesStart"][0][0], places=6)
        self.assertEqual(0.6, floats["scalarUsesStart"][0][1])
        self.assertTrue(floats["emptyIsClone"])
        self.assertEqual([[0.4, 4.0, 1]], floats["emptyReturnsClonedPrevious"])
        self.assertEqual([3.0, 2.0, 1.0], [row[1] for row in floats["descendingSorted"]])


if __name__ == "__main__":
    unittest.main()
