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
    "core.create-hook-lora": {
        "directory": "create-hook-lora",
        "classType": "CreateHookLora",
        "fingerprint": "sha256:7f9226377c7e021fc3ddf555a2890d5e1c11e2a20a85b6201c05992a211f7dd0",
        "required": ["lora_name", "strength_model", "strength_clip"],
        "recipe": "recipe.create-lora-weight-hook",
    },
    "core.create-hook-lora-model-only": {
        "directory": "create-hook-lora-model-only",
        "classType": "CreateHookLoraModelOnly",
        "fingerprint": "sha256:cfd15155abbaf60b3bf32a43765fcd384bf19930d03f1b25c208e86c1e4c76d5",
        "required": ["lora_name", "strength_model"],
        "recipe": "recipe.create-model-only-lora-hook",
    },
    "core.create-hook-model-as-lora": {
        "directory": "create-hook-model-as-lora",
        "classType": "CreateHookModelAsLora",
        "fingerprint": "sha256:3554cf6abc0e86d8f58a7c020cc02e1f84333bf34b604e94a1c961457be855ad",
        "required": ["ckpt_name", "strength_model", "strength_clip"],
        "recipe": "recipe.checkpoint-as-lora-hook",
    },
    "core.create-hook-model-as-lora-model-only": {
        "directory": "create-hook-model-as-lora-model-only",
        "classType": "CreateHookModelAsLoraModelOnly",
        "fingerprint": "sha256:3ca4854dfbe90e3af752ff675e72fb8d028cdf390855c6b6bea950eea4fbb81b",
        "required": ["ckpt_name", "strength_model"],
        "recipe": "recipe.checkpoint-as-lora-model-only-hook",
    },
}

RECIPE_DIRECTORIES = {
    "recipe.create-lora-weight-hook": "create-lora-weight-hook",
    "recipe.create-model-only-lora-hook": "create-model-only-lora-hook",
    "recipe.checkpoint-as-lora-hook": "checkpoint-as-lora-hook",
    "recipe.checkpoint-as-lora-model-only-hook": "checkpoint-as-lora-model-only-hook",
}

ROOT = catalog.ROOT
CONTENT = catalog.CONTENT
SOURCE = ROOT / ".comfyui-source-0.32.0"
INVENTORY = CONTENT / "runtime" / "comfyui-0.32.0.object-info.json"
REPLACEMENTS = CONTENT / "runtime" / "comfyui-0.32.0.node-replacements.json"
DOCS_WHEEL = ROOT / ".upstream-cache" / "comfyui_embedded_docs-0.5.9-py3-none-any.whl"
WORKFLOW_WHEEL = ROOT / ".upstream-cache" / "comfyui_workflow_templates_json-0.1.42-py3-none-any.whl"
PROBE = ROOT / "tools" / "tests" / "hook_weight_creation_synthetic_probe.py"
TARGET_TYPES = {spec["classType"] for spec in ARTICLE_SPECS.values()}

DOCS_SHA256 = "30afae432a71c96aa59421d0f37388c66ff6572b8cbeee8ff045e4d5f84f896c"
WORKFLOW_SHA256 = "242982d65e1c51ca03d892bc1009bb6843f457e7dfc0c20afe6438770b7a14a3"
DOC_HASHES = {
    ("CreateHookLora", "en"): "e4af54cdd03262e24cd9a7cb20a419019067465c2ce0170d4a86bcdadb10cf27",
    ("CreateHookLora", "ru"): "029a9a66a6e188988a10cbde06136a262e9e771f2d83099a421d148dcb6928ef",
    ("CreateHookLoraModelOnly", "en"): "b95a14f8c89308f25ce241dd87bf2a368b869e1b6ffa228d04b1a190dbd55e71",
    ("CreateHookLoraModelOnly", "ru"): "a57b20d617649445cfc3310d5938dea3b82d1a8faaf7a1165549d1fd8586a0f9",
    ("CreateHookModelAsLora", "en"): "974f6519c5409bdd4ffda938e650cd11fa9389e83d015bfed82a9d5a082285d2",
    ("CreateHookModelAsLora", "ru"): "c59415a9e864303d665264fad4974b8341f12c69c7dac7b334a70ba8382e5e75",
    ("CreateHookModelAsLoraModelOnly", "en"): "5324233f52698cb7e43bfbdabdcc2ea641df69a3b0c7f97568e52360fdde9798",
    ("CreateHookModelAsLoraModelOnly", "ru"): "afb22ab3b940856939ab88425d805f1822399bc89672f2546d8f1c43866d6fc2",
}


def all_article_ids() -> set[str]:
    ids: set[str] = set()
    for path in (CONTENT / "articles").rglob("manifest.json"):
        payload = catalog.load_json(path)
        if isinstance(payload, dict) and isinstance(payload.get("articleId"), str):
            ids.add(payload["articleId"])
    return ids


def workflow_scopes(payload: dict[str, Any]) -> Iterator[tuple[str, dict[str, Any]]]:
    if isinstance(payload.get("nodes"), list):
        yield "root", payload
    definitions = payload.get("definitions")
    subgraphs = definitions.get("subgraphs", []) if isinstance(definitions, dict) else []
    for graph in subgraphs:
        if isinstance(graph, dict) and isinstance(graph.get("nodes"), list):
            yield "subgraph", graph


def input_descriptor(definition: dict[str, Any], name: str) -> list[Any] | None:
    for section in ("required", "optional", "hidden"):
        descriptor = definition.get("input", {}).get(section, {}).get(name)
        if isinstance(descriptor, list):
            return descriptor
    return None


class HookWeightCreationContentTests(unittest.TestCase):
    def test_articles_recipes_ledgers_and_natural_russian(self) -> None:
        required_paths = [SOURCE, INVENTORY, REPLACEMENTS, DOCS_WHEEL, WORKFLOW_WHEEL, PROBE]
        for path in required_paths:
            self.assertTrue(path.exists(), f"pinned evidence is missing: {path}")

        article_schema = catalog.load_json(CONTENT / "schemas" / "article.schema.v1.json")
        recipe_schema = catalog.load_json(CONTENT / "schemas" / "recipe.schema.v1.json")
        fragment_schema = catalog.load_json(CONTENT / "schemas" / "recipe-fragment.schema.v1.json")
        research_schema = catalog.load_json(CONTENT / "schemas" / "article-research.schema.v1.json")
        article_ids = all_article_ids()
        article_errors: list[str] = []
        recipe_errors: list[str] = []
        cliches = re.compile(
            r"важно отметить|стоит отметить|в современном мире|революционн|данная нода|"
            r"давайте разбер|подводя итог|мощный инструмент|не просто .{0,80}, а",
            flags=re.IGNORECASE,
        )
        ordinary_english = re.compile(
            r"\b(?:official case|source-derived|root workflows?|metadata entries|input block|widgets?)\b",
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
            self.assertEqual(spec["classType"], article["runtimeIdentity"]["classType"])
            self.assertEqual([], article["runtimeIdentity"]["aliases"])
            self.assertNotIn("approved", json.dumps(article, ensure_ascii=False).lower())

            relations = article["relations"]
            targets = list(relations["related"]) + list(relations["alternatives"])
            if relations["replacedBy"] is not None:
                targets.append(relations["replacedBy"])
            self.assertTrue(set(targets).issubset(article_ids), (article_id, targets))

            body = (path.parent / article["body"]).read_text(encoding="utf-8")
            self.assertEqual(10, len(re.findall(r"^## .+$", body, flags=re.MULTILINE)), article_id)
            self.assertRegex(
                body,
                r"(?:Редактор пока не проверил материал вручную|человеческое утверждение пока не выполнено)\.",
            )
            self.assertNotIn("\ufffd", body)
            self.assertNotRegex(body, cliches)
            prose = re.sub(r"`[^`]+`|https?://\S+", "", body)
            self.assertNotRegex(prose, ordinary_english)

            ledger = catalog.load_json(CONTENT / "research" / "reviews" / f"{article_id}.json")
            self.assertEqual([], catalog.json_schema_errors(ledger, research_schema), article_id)
            self.assertEqual("fact_checked", ledger["state"])
            self.assertEqual("automated_assisted", ledger["reviewMode"])
            self.assertFalse(ledger["checks"]["exampleExecuted"])
            self.assertTrue(ledger["checks"]["russianEdited"])
            self.assertTrue(ledger["checks"]["factsRecheckedAfterEditing"])
            self.assertTrue(
                any(
                    "Редактор пока" in gap
                    or ("Человеческое" in gap and "утверждение" in gap)
                    for gap in ledger["knownGaps"]
                )
            )
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
            self.assertTrue(
                "Редактор пока не проверил материал вручную." in body
                or "человеческое утверждение пока не выполнено" in body
            )
            self.assertNotRegex(body, cliches)
            prose = re.sub(r"`[^`]+`|https?://\S+", "", body)
            self.assertNotRegex(prose, ordinary_english)

            fragment_path = path.parent / recipe["fragment"]["path"]
            fragment = catalog.load_json(fragment_path)
            self.assertEqual([], catalog.json_schema_errors(fragment, fragment_schema), recipe_id)
            catalog.validate_fragment(fragment_path, fragment, recipe_errors)

        self.assertEqual([], recipe_errors)

    def test_runtime_fingerprints_ports_flags_and_replacements(self) -> None:
        inventory = catalog.load_json(INVENTORY)
        seen_article_ids: Counter[str] = Counter()
        seen_class_types: Counter[str] = Counter()
        for path in (CONTENT / "articles").rglob("manifest.json"):
            article = catalog.load_json(path)
            seen_article_ids[article["articleId"]] += 1
            class_type = article.get("runtimeIdentity", {}).get("classType")
            if isinstance(class_type, str):
                seen_class_types[class_type] += 1

        for article_id, spec in ARTICLE_SPECS.items():
            definition = inventory[spec["classType"]]
            self.assertEqual(1, seen_article_ids[article_id])
            self.assertEqual(1, seen_class_types[spec["classType"]])
            self.assertEqual("comfy_extras.nodes_hooks", definition["python_module"])
            self.assertEqual("advanced/hooks/create", definition["category"])
            self.assertEqual(spec["required"], definition["input_order"]["required"])
            self.assertEqual(["prev_hooks"], definition["input_order"]["optional"])
            self.assertEqual(["HOOKS"], definition["output"])
            self.assertEqual(["HOOKS"], definition["output_name"])
            self.assertEqual([False], definition["output_is_list"])
            self.assertEqual(["HOOKS"], definition["input"]["optional"]["prev_hooks"])
            self.assertTrue(definition["experimental"])
            self.assertFalse(definition["output_node"])
            self.assertFalse(definition["is_input_list"])
            for flag in ("deprecated", "dev_only", "api_node"):
                self.assertFalse(definition.get(flag, False), (spec["classType"], flag))
            self.assertEqual(spec["fingerprint"], catalog.schema_fingerprint(spec["classType"], definition))

            filename_key = "lora_name" if spec["classType"].startswith("CreateHookLora") else "ckpt_name"
            self.assertEqual([[]], definition["input"]["required"][filename_key])
            for name in ("strength_model", "strength_clip"):
                if name not in spec["required"]:
                    continue
                self.assertEqual(
                    ["FLOAT", {"default": 1.0, "min": -20.0, "max": 20.0, "step": 0.01}],
                    definition["input"]["required"][name],
                )

        replacements = catalog.load_json(REPLACEMENTS)
        replacement_ids: set[str] = set()

        def collect_replacement_ids(value: Any) -> None:
            if isinstance(value, dict):
                for key, item in value.items():
                    if key in {"old_node_id", "new_node_id"} and isinstance(item, str):
                        replacement_ids.add(item)
                    collect_replacement_ids(item)
            elif isinstance(value, list):
                for item in value:
                    collect_replacement_ids(item)

        collect_replacement_ids(replacements)
        for class_type in TARGET_TYPES:
            self.assertNotIn(class_type, replacement_ids)

    def test_fragments_are_typed_complete_and_fail_closed(self) -> None:
        inventory = catalog.load_json(INVENTORY)
        fragments = {
            recipe_id: catalog.load_json(CONTENT / "recipes" / directory / "fragment.json")
            for recipe_id, directory in RECIPE_DIRECTORIES.items()
        }
        expected_nodes = {
            "recipe.create-lora-weight-hook": ["CreateHookLora", "SetClipHooks", "CLIPTextEncode", "ConditioningSetProperties"],
            "recipe.create-model-only-lora-hook": ["CreateHookLoraModelOnly", "ConditioningSetProperties"],
            "recipe.checkpoint-as-lora-hook": ["CreateHookModelAsLora", "SetClipHooks", "CLIPTextEncode", "ConditioningSetProperties"],
            "recipe.checkpoint-as-lora-model-only-hook": ["CreateHookModelAsLoraModelOnly", "ConditioningSetProperties"],
        }

        for recipe_id, fragment in fragments.items():
            self.assertEqual(expected_nodes[recipe_id], [node["classType"] for node in fragment["nodes"]])
            refs = {node["ref"]: node for node in fragment["nodes"]}
            supplied: dict[str, set[str]] = {ref: set() for ref in refs}

            for external in fragment["externalInputs"]:
                self.assertIn(external["to"], refs)
                definition = inventory[refs[external["to"]]["classType"]]
                descriptor = input_descriptor(definition, external["input"])
                self.assertIsNotNone(descriptor, external)
                self.assertEqual(external["type"], descriptor[0], external)
                supplied[external["to"]].add(external["input"])

            for connection in fragment["connections"]:
                self.assertIn(connection["from"], refs)
                self.assertIn(connection["to"], refs)
                source_def = inventory[refs[connection["from"]]["classType"]]
                dest_def = inventory[refs[connection["to"]]["classType"]]
                self.assertIn(connection["output"], source_def["output_name"])
                output_index = source_def["output_name"].index(connection["output"])
                output_type = source_def["output"][output_index]
                descriptor = input_descriptor(dest_def, connection["input"])
                self.assertIsNotNone(descriptor, connection)
                self.assertEqual(output_type, descriptor[0], connection)
                supplied[connection["to"]].add(connection["input"])

            for ref, node in refs.items():
                definition = inventory[node["classType"]]
                settings = node["settings"]
                self.assertTrue(set(settings).isdisjoint(supplied[ref]), (recipe_id, ref))
                for name, value in settings.items():
                    descriptor = input_descriptor(definition, name)
                    self.assertIsNotNone(descriptor, (recipe_id, ref, name))
                    kind = descriptor[0]
                    options = descriptor[1] if len(descriptor) > 1 and isinstance(descriptor[1], dict) else {}
                    if kind == "FLOAT":
                        self.assertIsInstance(value, (int, float))
                        self.assertGreaterEqual(value, options["min"])
                        self.assertLessEqual(value, options["max"])
                    elif kind == "BOOLEAN":
                        self.assertIsInstance(value, bool)
                    elif isinstance(kind, list):
                        if kind:
                            self.assertIn(value, kind)
                        else:
                            self.assertIsInstance(value, str)
                            self.assertTrue(value.startswith("SELECT_"), value)
                    elif kind == "STRING":
                        self.assertIsInstance(value, str)
                required = set(definition["input_order"].get("required", []))
                self.assertTrue(required.issubset(set(settings) | supplied[ref]), (recipe_id, ref, required, settings, supplied[ref]))

        full_lora = fragments["recipe.create-lora-weight-hook"]
        self.assertEqual("SELECT_LORA_FILE", full_lora["nodes"][0]["settings"]["lora_name"])
        self.assertEqual(
            {"apply_to_conds": False, "schedule_clip": False},
            full_lora["nodes"][1]["settings"],
        )
        full_checkpoint = fragments["recipe.checkpoint-as-lora-hook"]
        self.assertEqual("SELECT_CHECKPOINT", full_checkpoint["nodes"][0]["settings"]["ckpt_name"])
        for fragment in fragments.values():
            for node in fragment["nodes"]:
                if node["classType"] == "ConditioningSetProperties":
                    self.assertEqual({"strength": 1.0, "set_cond_area": "default"}, node["settings"])

    def test_pinned_source_hashes_registration_and_exact_branches(self) -> None:
        expected_hashes = {
            SOURCE / "comfy_extras" / "nodes_hooks.py": "06218a53653b8b856fa9296d18ffce3d0fd05706a9b731112e44bc82f432e375",
            SOURCE / "comfy" / "hooks.py": "d9364d1e9d6f1b9cd6a0f09767a9ec8007b0577f9e2d245c403b4d325f909c65",
            SOURCE / "comfy" / "lora.py": "4efd82adbd4e70f8fc29a9bf1cf2827ca211e7a15297187236b7b3119acd8d03",
            SOURCE / "comfy" / "model_patcher.py": "0a0e1991b4bea80dc6f5785ba7d6b2d76929c976a6c156a08387a0567c9ebf04",
            SOURCE / "comfy" / "sd.py": "51e72a263e8bd77812aefcebcf3cfaf9fda57150d763897b6d8b4890d7fee207",
        }
        for path, digest in expected_hashes.items():
            self.assertTrue(path.exists(), path)
            self.assertEqual(digest, hashlib.sha256(path.read_bytes()).hexdigest(), path)

        nodes = (SOURCE / "comfy_extras" / "nodes_hooks.py").read_text(encoding="utf-8")
        for marker in (
            "class CreateHookLora:",
            "if strength_model == 0 and strength_clip == 0:",
            "comfy.utils.load_torch_file(lora_path, safe_load=True)",
            "self.loaded_lora = (lora_path, lora)",
            "return self.create_hook(lora_name=lora_name, strength_model=strength_model, strength_clip=0, prev_hooks=prev_hooks)",
            "class CreateHookModelAsLora:",
            "load_checkpoint_guess_config(ckpt_path, output_vae=True, output_clip=True",
            "weights_clip = comfy.hooks.get_patch_weights_from_model(out[1].patcher if out[1] else out[1])",
            "self.loaded_weights = (ckpt_path, weights_model, weights_clip)",
            "return self.create_hook(ckpt_name=ckpt_name, strength_model=strength_model, strength_clip=0.0, prev_hooks=prev_hooks)",
            "    CreateHookLora,",
            "    CreateHookLoraModelOnly,",
            "    CreateHookModelAsLora,",
            "    CreateHookModelAsLoraModelOnly,",
        ):
            self.assertIn(marker, nodes)

        hooks = (SOURCE / "comfy" / "hooks.py").read_text(encoding="utf-8")
        for marker in (
            "def create_hook_lora(lora: dict[str, torch.Tensor], strength_model: float, strength_clip: float):",
            "hook.weights = lora",
            "patches_model[key] = (\"model_as_lora\", (weights_model[key],))",
            "patches_clip[key] = (\"model_as_lora\", (weights_clip[key],))",
            "hook.need_weight_init = False",
            "if key.startswith(\"model_sampling\"):",
            "c.weights = self.weights",
            "c.weights_clip = self.weights_clip",
        ):
            self.assertIn(marker, hooks)

        lora = (SOURCE / "comfy" / "lora.py").read_text(encoding="utf-8")
        for marker in (
            'elif patch_type == "set":',
            "weight.copy_(v[0])",
            'elif patch_type == "model_as_lora":',
            "comfy.model_management.cast_to_device(original_weights[key][0][0]",
            "weight += function(strength * comfy.model_management.cast_to_device(diff_weight",
        ):
            self.assertIn(marker, lora)

        patcher = (SOURCE / "comfy" / "model_patcher.py").read_text(encoding="utf-8")
        for marker in (
            "def add_hook_patches(self, hook: comfy.hooks.WeightHook, patches, strength_patch=1.0, strength_model=1.0):",
            "if key in model_sd:",
            "current_patches.append((strength_patch, patches[k], strength_model, offset, function))",
            "new_patch[0] *= hook.strength",
        ):
            self.assertIn(marker, patcher)

        sd = (SOURCE / "comfy" / "sd.py").read_text(encoding="utf-8")
        self.assertIn("trying to load it as a diffusion model only", sd)
        self.assertIn("return (diffusion_model, None, VAE(sd={}), None)", sd)

    def test_embedded_docs_integrity_exact_members_and_known_gaps(self) -> None:
        self.assertTrue(DOCS_WHEEL.exists(), DOCS_WHEEL)
        self.assertEqual(DOCS_SHA256, hashlib.sha256(DOCS_WHEEL.read_bytes()).hexdigest())
        with zipfile.ZipFile(DOCS_WHEEL) as archive:
            self.assertIsNone(archive.testzip())
            names = set(archive.namelist())
            for (class_type, locale), digest in DOC_HASHES.items():
                name = f"comfyui_embedded_docs/docs/{class_type}/{locale}.md"
                self.assertIn(name, names)
                data = archive.read(name)
                self.assertEqual(digest, hashlib.sha256(data).hexdigest(), name)
                text = data.decode("utf-8")
                self.assertIn(class_type.replace("CreateHook", "Create Hook").replace("ModelOnly", "Model Only")[:6], text)

            lora_en = archive.read("comfyui_embedded_docs/docs/CreateHookLora/en.md").decode("utf-8")
            self.assertIn("If both `strength_model` and `strength_clip` are set to 0", lora_en)
            self.assertIn("caches the last loaded LoRA file", lora_en)
            model_as_en = archive.read("comfyui_embedded_docs/docs/CreateHookModelAsLora/en.md").decode("utf-8")
            self.assertIn("caches loaded weights", model_as_en)
            self.assertNotIn("model_sampling", model_as_en)
            self.assertNotIn("output_vae", model_as_en)

    def test_workflow_wheel_integrity_and_full_zero_census(self) -> None:
        self.assertTrue(WORKFLOW_WHEEL.exists(), WORKFLOW_WHEEL)
        self.assertEqual(WORKFLOW_SHA256, hashlib.sha256(WORKFLOW_WHEEL.read_bytes()).hexdigest())
        exact_counts: Counter[str] = Counter()
        insensitive_counts: Counter[str] = Counter()
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
                self.assertEqual(expected, actual, name)
                self.assertEqual(int(size), len(data), name)
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
                        node_type = node.get("type")
                        if node_type in TARGET_TYPES:
                            exact_counts[node_type] += 1
                        if isinstance(node_type, str):
                            for target in TARGET_TYPES:
                                if node_type.casefold() == target.casefold():
                                    insensitive_counts[target] += 1

        self.assertEqual((512, 496, 272, 8120), (json_count, root_count, subgraph_count, node_count))
        self.assertEqual(Counter(), exact_counts)
        self.assertEqual(Counter(), insensitive_counts)
        self.assertEqual(Counter(), raw_counts)

    def test_safe_exact_source_model_free_probe(self) -> None:
        self.assertTrue(PROBE.exists(), PROBE)
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

        lora = payload["lora"]
        self.assertTrue(lora["safeLoad"])
        self.assertTrue(lora["sameFileLoadedOnce"])
        self.assertEqual(1, lora["loadCalls"])
        self.assertTrue(lora["cachedPayloadIdentity"])
        self.assertTrue(lora["zeroReturnsPriorIdentity"])
        self.assertTrue(lora["zeroDoesNotResolveNewPath"])
        self.assertTrue(lora["modelOnlyZeroReturnsPriorIdentity"])
        self.assertEqual(0, lora["modelOnlyZeroLoadDelta"])
        self.assertEqual([0.8, 0.4], lora["firstStrengths"])
        self.assertEqual([0.2, -0.3], lora["secondStrengths"])
        self.assertTrue(lora["priorPreserved"])

        model = payload["modelAsLora"]
        self.assertTrue(model["loaderRequestedVaeAndClip"])
        self.assertTrue(model["sameCheckpointLoadedOnce"])
        self.assertTrue(model["changedPathReloaded"])
        self.assertTrue(model["zeroStillLoaded"])
        self.assertTrue(model["modelOnlyZeroStillLoads"])
        self.assertTrue(model["samplingKeysRemoved"])
        self.assertEqual(["diffusion.weight"], model["modelKeys"])
        self.assertEqual(["clip.weight"], model["clipKeys"])
        self.assertEqual("model_as_lora", model["patchType"])
        self.assertFalse(model["needWeightInit"])
        self.assertEqual(0.0, model["modelOnlyClipStrength"])
        self.assertTrue(model["modelOnlyStillStoresClipPatches"])
        self.assertTrue(model["targetTensorSharedAcrossCalls"])
        self.assertTrue(model["clipMayBeAbsent"])
        self.assertTrue(model["vaeNotCached"])
        self.assertEqual([0.0, 0.0], model["zeroStrengths"])
        self.assertEqual([1.0, 0.5], model["secondStrengths"])

        formula = payload["modelAsLoraFormula"]
        self.assertEqual([1.0, 3.0], formula["strength0"])
        self.assertEqual([3.0, 2.0], formula["strengthHalf"])
        self.assertEqual([5.0, 1.0], formula["strength1"])
        self.assertEqual([-3.0, 5.0], formula["strengthNegative"])
        self.assertEqual([15.0, 11.0], formula["keepsExistingPatch"])
        self.assertEqual([5.0, 5.0], formula["broadcastShape"])
        self.assertEqual("RuntimeError", formula["incompatibleShapeError"])

        raw = payload["rawLoraPatchSemantics"]
        self.assertEqual([1.0, 3.0], raw["diffStrength0"])
        self.assertEqual([-1.0, 4.0], raw["diffStrengthNegative"])
        self.assertEqual([9.0, 8.0], raw["setStrength0"])
        self.assertEqual([11.0, 7.0], raw["setThenDiff"])
        self.assertEqual([9.0, 8.0], raw["diffThenSet"])

        registration = payload["exactRegistration"]
        self.assertEqual([False, False], registration["loadLoraLogMissingFlags"])
        self.assertTrue(registration["missingTargetKeyFiltered"])
        self.assertEqual(["base.weight"], registration["registeredKeys"])
        self.assertEqual([True, True], registration["priorThenNew"])
        self.assertTrue(registration["cloneSharesWeightDictionary"])
        self.assertTrue(registration["duplicateHookRefRemoved"])
        self.assertEqual([0.8, 0.15], registration["combinedStrengths"])
        self.assertEqual(0.15, registration["effectiveTargetStrength"])
        self.assertEqual([9.0, 8.0], registration["zeroSetStillApplies"])


if __name__ == "__main__":
    unittest.main()
