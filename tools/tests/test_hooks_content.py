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
    "core.combine-hooks-2": {
        "directory": "combine-hooks-2",
        "classType": "CombineHooks2",
        "fingerprint": "sha256:1e7aff0fb2d6078b39ad7e3c731d7a146e3e4212ec0dca8f3d3f42cabc6eb0f3",
        "recipe": "recipe.combine-two-hooks-for-conditioning",
        "required": [],
        "optional": ["hooks_A", "hooks_B"],
    },
    "core.combine-hooks-4": {
        "directory": "combine-hooks-4",
        "classType": "CombineHooks4",
        "fingerprint": "sha256:cec8c77933c98049a5e432b52bb0f3a3e331042a22efceb193db98f4b8e306f5",
        "recipe": "recipe.combine-four-hooks-for-clip",
        "required": [],
        "optional": ["hooks_A", "hooks_B", "hooks_C", "hooks_D"],
    },
    "core.combine-hooks-8": {
        "directory": "combine-hooks-8",
        "classType": "CombineHooks8",
        "fingerprint": "sha256:22d366fdf45a48bf4555818c628583f5bf0ecbba9d5b82d62c1b074859a5182e",
        "recipe": "recipe.combine-eight-hooks-for-conditioning",
        "required": [],
        "optional": [f"hooks_{letter}" for letter in "ABCDEFGH"],
    },
    "core.set-clip-hooks": {
        "directory": "set-clip-hooks",
        "classType": "SetClipHooks",
        "fingerprint": "sha256:9513bcb4337571aaea644b50bda53076b0b0f1db7807e6ea8266db473f853b2a",
        "recipe": "recipe.set-clip-hooks-scheduled-prompt",
        "required": ["clip", "apply_to_conds", "schedule_clip"],
        "optional": ["hooks"],
    },
}

RECIPE_DIRECTORIES = {
    "recipe.combine-two-hooks-for-conditioning": "combine-two-hooks-for-conditioning",
    "recipe.combine-four-hooks-for-clip": "combine-four-hooks-for-clip",
    "recipe.combine-eight-hooks-for-conditioning": "combine-eight-hooks-for-conditioning",
    "recipe.set-clip-hooks-scheduled-prompt": "set-clip-hooks-scheduled-prompt",
}

ROOT = catalog.ROOT
CONTENT = catalog.CONTENT
SOURCE = ROOT / ".comfyui-source-0.32.0"
INVENTORY = CONTENT / "runtime" / "comfyui-0.32.0.object-info.json"
REPLACEMENTS = CONTENT / "runtime" / "comfyui-0.32.0.node-replacements.json"
DOCS_WHEEL = ROOT / ".upstream-cache" / "comfyui_embedded_docs-0.5.9-py3-none-any.whl"
WORKFLOW_WHEEL = ROOT / ".upstream-cache" / "comfyui_workflow_templates_json-0.1.42-py3-none-any.whl"
PROBE = ROOT / "tools" / "tests" / "hooks_synthetic_probe.py"
TARGET_TYPES = {spec["classType"] for spec in ARTICLE_SPECS.values()}

DOCS_SHA256 = "30afae432a71c96aa59421d0f37388c66ff6572b8cbeee8ff045e4d5f84f896c"
WORKFLOW_SHA256 = "242982d65e1c51ca03d892bc1009bb6843f457e7dfc0c20afe6438770b7a14a3"
SET_CLIP_DOC_HASHES = {
    "en": "471416e745b8f19a01c2bb3ae46c83aa40ff57722b0f918b763ab149a971f242",
    "ru": "30bb693a720faa1be4d9831b04c82417c83cb40c3f8c45c770ed6a99343494cc",
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


class HooksContentTests(unittest.TestCase):
    def test_articles_recipes_ledgers_and_editorial_contract(self) -> None:
        article_schema = catalog.load_json(CONTENT / "schemas" / "article.schema.v1.json")
        recipe_schema = catalog.load_json(CONTENT / "schemas" / "recipe.schema.v1.json")
        fragment_schema = catalog.load_json(CONTENT / "schemas" / "recipe-fragment.schema.v1.json")
        research_schema = catalog.load_json(CONTENT / "schemas" / "article-research.schema.v1.json")
        article_ids = all_article_ids()
        article_errors: list[str] = []
        recipe_errors: list[str] = []
        cliches = re.compile(
            r"важно отметить|стоит отметить|в современном мире|революционн|"
            r"данная нода|давайте разбер|подводя итог|мощный инструмент|"
            r"не просто .{0,80}, а",
            flags=re.IGNORECASE,
        )

        for article_id, spec in ARTICLE_SPECS.items():
            path = CONTENT / "articles" / "core" / spec["directory"] / "manifest.json"
            article = catalog.load_json(path)
            self.assertEqual([], catalog.json_schema_errors(article, article_schema), article_id)
            catalog.validate_article(path, article, article_errors)
            self.assertEqual(article_id, article["articleId"])
            self.assertEqual("draft", article["status"])
            self.assertEqual("in_review", article["editorial"]["state"])
            self.assertTrue(article["experimental"])
            self.assertEqual(spec["fingerprint"], article["editorial"]["schemaHash"])
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
            self.assertNotIn("первый wins", body)
            self.assertNotIn("нoded", body)

            ledger = catalog.load_json(CONTENT / "research" / "reviews" / f"{article_id}.json")
            self.assertEqual([], catalog.json_schema_errors(ledger, research_schema), article_id)
            self.assertEqual("fact_checked", ledger["state"])
            self.assertEqual("automated_assisted", ledger["reviewMode"])
            self.assertFalse(ledger["checks"]["exampleExecuted"])
            self.assertTrue(ledger["checks"]["russianEdited"])
            self.assertTrue(ledger["checks"]["factsRecheckedAfterEditing"])
            self.assertTrue(any("Редактор пока" in gap for gap in ledger["knownGaps"]))
            self.assertNotIn("human_approved", json.dumps(ledger).lower())

        self.assertEqual([], article_errors)

        for recipe_id, directory in RECIPE_DIRECTORIES.items():
            path = CONTENT / "recipes" / directory / "recipe.json"
            recipe = catalog.load_json(path)
            self.assertEqual([], catalog.json_schema_errors(recipe, recipe_schema), recipe_id)
            catalog.validate_recipe(path, recipe, article_ids, recipe_errors)
            self.assertEqual(recipe_id, recipe["recipeId"])
            self.assertEqual("in_review", recipe["editorial"]["state"])
            self.assertNotIn("workflow", recipe)
            self.assertNotIn("approved", json.dumps(recipe).lower())
            body = (path.parent / recipe["body"]).read_text(encoding="utf-8")
            self.assertIn("Редактор пока не проверил материал вручную.", body)
            self.assertNotRegex(body, cliches)

            fragment_path = path.parent / recipe["fragment"]["path"]
            fragment = catalog.load_json(fragment_path)
            self.assertEqual([], catalog.json_schema_errors(fragment, fragment_schema), recipe_id)
            catalog.validate_fragment(fragment_path, fragment, recipe_errors)

        self.assertEqual([], recipe_errors)

    def test_runtime_contracts_fingerprints_fragments_and_replacements(self) -> None:
        inventory = catalog.load_json(INVENTORY)
        for spec in ARTICLE_SPECS.values():
            definition = inventory[spec["classType"]]
            self.assertEqual("comfy_extras.nodes_hooks", definition["python_module"])
            self.assertEqual(spec["fingerprint"], catalog.schema_fingerprint(spec["classType"], definition))
            self.assertEqual("advanced/hooks/clip" if spec["classType"] == "SetClipHooks" else "advanced/hooks/combine", definition["category"])
            self.assertEqual(spec["required"], definition["input_order"].get("required", []))
            self.assertEqual(spec["optional"], definition["input_order"].get("optional", []))
            self.assertTrue(definition["experimental"])
            self.assertFalse(definition["output_node"])
            for flag in ("deprecated", "dev_only", "api_node", "is_input_list"):
                self.assertFalse(definition.get(flag, False), (spec["classType"], flag))

        for class_type in ("CombineHooks2", "CombineHooks4", "CombineHooks8"):
            definition = inventory[class_type]
            self.assertEqual(["HOOKS"], definition["output"])
            self.assertEqual(["HOOKS"], definition["output_name"])
            for name in definition["input_order"]["optional"]:
                self.assertEqual(["HOOKS"], definition["input"]["optional"][name])
        self.assertEqual(["merge hooks"], inventory["CombineHooks2"]["search_aliases"])
        self.assertEqual([], inventory["CombineHooks4"]["search_aliases"])
        self.assertEqual([], inventory["CombineHooks8"]["search_aliases"])

        set_clip = inventory["SetClipHooks"]
        self.assertEqual(["CLIP"], set_clip["output"])
        self.assertEqual(["CLIP"], set_clip["output_name"])
        self.assertEqual(["CLIP"], set_clip["input"]["required"]["clip"])
        self.assertEqual(
            ["BOOLEAN", {"default": True, "advanced": True}],
            set_clip["input"]["required"]["apply_to_conds"],
        )
        self.assertEqual(
            ["BOOLEAN", {"default": False, "advanced": True}],
            set_clip["input"]["required"]["schedule_clip"],
        )
        self.assertEqual(["HOOKS"], set_clip["input"]["optional"]["hooks"])

        fragments = {
            directory: catalog.load_json(CONTENT / "recipes" / directory / "fragment.json")
            for directory in RECIPE_DIRECTORIES.values()
        }
        self.assertEqual(
            ["CombineHooks2", "ConditioningSetProperties"],
            [node["classType"] for node in fragments["combine-two-hooks-for-conditioning"]["nodes"]],
        )
        self.assertEqual(
            ["hooks_A", "hooks_B", "cond_NEW"],
            [item["input"] for item in fragments["combine-two-hooks-for-conditioning"]["externalInputs"]],
        )
        self.assertEqual(
            ["CombineHooks4", "SetClipHooks", "CLIPTextEncode"],
            [node["classType"] for node in fragments["combine-four-hooks-for-clip"]["nodes"]],
        )
        self.assertEqual(
            {"apply_to_conds": True, "schedule_clip": False},
            fragments["combine-four-hooks-for-clip"]["nodes"][1]["settings"],
        )
        eight = fragments["combine-eight-hooks-for-conditioning"]
        self.assertEqual([f"hooks_{letter}" for letter in "ABCDEFGH"], [item["input"] for item in eight["externalInputs"][:8]])
        scheduled = fragments["set-clip-hooks-scheduled-prompt"]
        self.assertEqual(["SetClipHooks", "CLIPTextEncode"], [node["classType"] for node in scheduled["nodes"]])
        self.assertEqual({"apply_to_conds": True, "schedule_clip": True}, scheduled["nodes"][0]["settings"])
        self.assertTrue(
            all(node["classType"] in inventory for fragment in fragments.values() for node in fragment["nodes"])
        )

        replacements = catalog.load_json(REPLACEMENTS)
        serialized = json.dumps(replacements, ensure_ascii=False)
        for class_type in TARGET_TYPES:
            self.assertNotIn(class_type, replacements)
            self.assertNotIn(f'"new_node_id": "{class_type}"', serialized)

    @unittest.skipUnless(SOURCE.exists(), "pinned source checkout is absent")
    def test_pinned_source_hashes_registration_and_branch_contracts(self) -> None:
        expected_hashes = {
            SOURCE / "comfy_extras" / "nodes_hooks.py": "06218a53653b8b856fa9296d18ffce3d0fd05706a9b731112e44bc82f432e375",
            SOURCE / "comfy" / "hooks.py": "d9364d1e9d6f1b9cd6a0f09767a9ec8007b0577f9e2d245c403b4d325f909c65",
            SOURCE / "comfy" / "sd.py": "51e72a263e8bd77812aefcebcf3cfaf9fda57150d763897b6d8b4890d7fee207",
            SOURCE / "comfy" / "model_patcher.py": "0a0e1991b4bea80dc6f5785ba7d6b2d76929c976a6c156a08387a0567c9ebf04",
            SOURCE / "nodes.py": "ffb2b5c999f47b720dbd81767c8fa4234255d939ba8dbb80ee64da9721c383ad",
        }
        for path, digest in expected_hashes.items():
            self.assertEqual(digest, hashlib.sha256(path.read_bytes()).hexdigest(), path)

        nodes = (SOURCE / "comfy_extras" / "nodes_hooks.py").read_text(encoding="utf-8")
        for marker in (
            "class SetClipHooks:",
            "clip = clip.clone(disable_dynamic=True)",
            "clip.apply_hooks_to_conds = hooks",
            "clip.patcher.forced_hooks = hooks.clone()",
            "clip.patcher.forced_hooks.set_keyframes_on_hooks(None)",
            "register_all_hook_patches(hooks, comfy.hooks.create_target_dict(comfy.hooks.EnumWeightTarget.Clip))",
            "NodeId = 'CombineHooks2'",
            "NodeId = 'CombineHooks4'",
            "NodeId = 'CombineHooks8'",
            "candidates = [hooks_A, hooks_B]",
            "candidates = [hooks_A, hooks_B, hooks_C, hooks_D]",
            "candidates = [hooks_A, hooks_B, hooks_C, hooks_D, hooks_E, hooks_F, hooks_G, hooks_H]",
            "    CombineHooks,",
            "    CombineHooksFour,",
            "    CombineHooksEight,",
            "    SetClipHooks,",
            "NODE_CLASS_MAPPINGS[node.NodeId] = node",
        ):
            self.assertIn(marker, nodes)

        hooks = (SOURCE / "comfy" / "hooks.py").read_text(encoding="utf-8")
        for marker in (
            "return self.__class__ == other.__class__ and self.hook_ref == other.hook_ref",
            "if len(actual) == 0:",
            "elif len(actual) == 1:",
            "return actual[0]",
            "final_hook = final_hook.clone_and_combine(hook)",
            "for hook in self.get_type(EnumHookType.Weight):",
            "boundaries_set.add(0.0)",
        ):
            self.assertIn(marker, hooks)

        clip = (SOURCE / "comfy" / "sd.py").read_text(encoding="utf-8")
        for marker in (
            "n.apply_hooks_to_conds = self.apply_hooks_to_conds",
            "if self.apply_hooks_to_conds:",
            'pooled_dict["hooks"] = self.apply_hooks_to_conds',
            "scheduled_keyframes = all_hooks.get_hooks_for_clip_schedule()",
            'pooled_dict["clip_start_percent"] = t_range[0]',
            'pooled_dict["clip_end_percent"] = t_range[1]',
        ):
            self.assertIn(marker, clip)

        nodes_core = (SOURCE / "nodes.py").read_text(encoding="utf-8")
        self.assertIn("return (clip.encode_from_tokens_scheduled(tokens), )", nodes_core)

    @unittest.skipUnless(DOCS_WHEEL.exists(), "pinned embedded docs wheel is absent")
    def test_embedded_docs_hashes_exact_absence_and_set_clip_gaps(self) -> None:
        self.assertEqual(DOCS_SHA256, hashlib.sha256(DOCS_WHEEL.read_bytes()).hexdigest())
        expected_locales = {"ar", "en", "es", "fa", "fr", "ja", "ko", "pt-BR", "ru", "tr", "zh", "zh-TW"}
        with zipfile.ZipFile(DOCS_WHEEL) as archive:
            names = set(archive.namelist())
            for class_type in ("CombineHooks2", "CombineHooks4", "CombineHooks8"):
                prefix = f"comfyui_embedded_docs/docs/{class_type}/"
                self.assertFalse(any(name.startswith(prefix) for name in names), class_type)
                self.assertEqual(0, sum(archive.read(name).count(class_type.encode()) for name in names))

            set_clip_locales = {
                Path(name).stem
                for name in names
                if name.startswith("comfyui_embedded_docs/docs/SetClipHooks/") and name.endswith(".md")
            }
            self.assertEqual(expected_locales, set_clip_locales)
            for locale, digest in SET_CLIP_DOC_HASHES.items():
                member = f"comfyui_embedded_docs/docs/SetClipHooks/{locale}.md"
                self.assertEqual(digest, hashlib.sha256(archive.read(member)).hexdigest())

            en = archive.read("comfyui_embedded_docs/docs/SetClipHooks/en.md").decode("utf-8")
            self.assertIn("creates a cloned copy", en)
            self.assertNotIn("without hooks", en.lower())
            ru = archive.read("comfyui_embedded_docs/docs/SetClipHooks/ru.md").decode("utf-8")
            self.assertIn("`клип`", ru)
            self.assertNotIn("`apply_to_conds`", ru)

    @unittest.skipUnless(WORKFLOW_WHEEL.exists(), "pinned workflow wheel is absent")
    def test_workflow_wheel_integrity_and_full_zero_census(self) -> None:
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

    @unittest.skipUnless(SOURCE.exists() and PROBE.exists(), "pinned source or probe is absent")
    def test_safe_exact_source_model_free_probe(self) -> None:
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

        combine = payload["combine"]
        self.assertTrue(combine["noneIsNone"])
        self.assertTrue(combine["oneReturnsInputIdentity"])
        self.assertTrue(combine["oneEmptyGroupReturnsInputIdentity"])
        self.assertTrue(combine["twoCreatesNewGroup"])
        self.assertTrue(combine["sameRefDifferentClassesRetained"])
        self.assertEqual(["A", "shared", "B"], combine["twoOrderAndDedup"])
        self.assertEqual(["A", "shared"], combine["inputAUnchanged"])
        self.assertEqual(["shared", "B"], combine["inputBUnchanged"])
        self.assertEqual(["A", "C", "D"], combine["fourSparseOrder"])
        self.assertEqual(["A", "D", "H"], combine["eightSparseOrder"])

        set_clip = payload["setClip"]
        self.assertTrue(set_clip["noHooksReturnsInputIdentity"])
        self.assertEqual([], set_clip["noHooksCloneCalls"])
        self.assertEqual([True], set_clip["clonedDisableDynamic"])
        self.assertTrue(set_clip["applyToCondsUsesOriginalGroup"])
        self.assertTrue(set_clip["registrationUsesOriginalGroup"])
        self.assertEqual("clip", set_clip["registrationTarget"])
        self.assertFalse(set_clip["unscheduledUseClipSchedule"])
        self.assertEqual([0, 0], set_clip["unscheduledForcedKeyframeCounts"])
        self.assertEqual([2, 0], set_clip["sourceKeyframeCountsUnchanged"])
        self.assertEqual([True, True], set_clip["scheduledForcedSharesKeyframeGroups"])
        self.assertEqual([True, True], set_clip["unscheduledForcedSeparatesKeyframeGroups"])
        self.assertTrue(set_clip["applyFalseDoesNotClearInheritedHooks"])
        self.assertEqual([True], set_clip["emptyHooksStillClones"])
        self.assertTrue(set_clip["emptyHooksGroupIsFalsy"])
        self.assertEqual([], set_clip["emptyHooksSchedule"])
        self.assertEqual([], set_clip["nonWeightSchedule"])
        self.assertEqual(
            [[[0.0, 1.0], [["static-weight", None]]]],
            set_clip["staticWeightSchedule"],
        )
        self.assertEqual(
            [[[0.0, 1.0], [["same-strength", 0.75]]]],
            set_clip["sameStrengthDoesNotAddBoundary"],
        )
        self.assertEqual(
            [
                [[0.0, 0.25], [["delayed-first", None]]],
                [[0.25, 1.0], [["delayed-first", 0.4]]],
            ],
            set_clip["delayedFirstKeyframeSchedule"],
        )
        self.assertEqual(
            [
                [[0.0, 0.5], [["weight", 0.25]]],
                [[0.5, 1.0], [["weight", 1.0]]],
            ],
            set_clip["keyframedWeightSchedule"],
        )


if __name__ == "__main__":
    unittest.main()
