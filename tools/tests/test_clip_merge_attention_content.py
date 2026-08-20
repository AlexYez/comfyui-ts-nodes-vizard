from __future__ import annotations

import hashlib
import json
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
    "core.clip-merge-simple": {
        "directory": "clip-merge-simple",
        "classType": "CLIPMergeSimple",
        "module": "comfy_extras.nodes_model_merging",
        "fingerprint": "sha256:c6392619decb6af5d630f950f6e29a92fcc79e4a5cf76a58552753f0a9f6758c",
        "recipe": "recipe.blend-two-clip-encoders",
        "experimental": False,
        "searchAliases": [],
    },
    "core.clip-merge-add": {
        "directory": "clip-merge-add",
        "classType": "CLIPMergeAdd",
        "module": "comfy_extras.nodes_model_merging",
        "fingerprint": "sha256:a4dfb835bc8fe0717417abc5373cdc72918b90786a3773311f171dca46aa1fcc",
        "recipe": "recipe.transfer-clip-weight-delta",
        "experimental": False,
        "searchAliases": ["combine clip"],
    },
    "core.clip-merge-subtract": {
        "directory": "clip-merge-subtract",
        "classType": "CLIPMergeSubtract",
        "module": "comfy_extras.nodes_model_merging",
        "fingerprint": "sha256:9ebfc36f3cf84903af2d26a5acdbc9d35b741caa62241621dcae2d6602bed978",
        "recipe": "recipe.transfer-clip-weight-delta",
        "experimental": False,
        "searchAliases": ["clip difference", "text encoder subtract"],
    },
    "core.clip-attention-multiply": {
        "directory": "clip-attention-multiply",
        "classType": "CLIPAttentionMultiply",
        "module": "comfy_extras.nodes_attention_multiply",
        "fingerprint": "sha256:75ccff59df5d980eb2ec9e6051eb677228f7d56cb67c7e4cde95da4eb314837f",
        "recipe": "recipe.probe-clip-attention-scale",
        "experimental": True,
        "searchAliases": ["clip attention scale", "text encoder attention"],
    },
}

RECIPE_DIRECTORIES = {
    "recipe.blend-two-clip-encoders": "blend-two-clip-encoders",
    "recipe.transfer-clip-weight-delta": "transfer-clip-weight-delta",
    "recipe.probe-clip-attention-scale": "probe-clip-attention-scale",
}

EXPECTED_FRAGMENT_NODES = {
    "recipe.blend-two-clip-encoders": [
        ("CLIPMergeSimple", {"ratio": 0.7}),
    ],
    "recipe.transfer-clip-weight-delta": [
        ("CLIPMergeSubtract", {"multiplier": 1.0}),
        ("CLIPMergeAdd", {}),
    ],
    "recipe.probe-clip-attention-scale": [
        ("CLIPAttentionMultiply", {"q": 0.9, "k": 1.0, "v": 1.0, "out": 1.0}),
    ],
}

EXPECTED_HEADINGS = [
    "Что делает нода",
    "Когда использовать и когда не использовать",
    "Короткий рецепт подключения",
    "Входы, выходы и параметры",
    "Типовые связки",
    "Практический пример",
    "Частые ошибки и способы проверки",
    "Производительность и внутреннее поведение",
    "Совместимость, изменения и устаревание",
    "Связанные ноды и источники",
]

FULL_INVENTORY = catalog.CONTENT / "runtime" / "comfyui-0.32.0.object-info.json"
REPLACEMENTS = catalog.CONTENT / "runtime" / "comfyui-0.32.0.node-replacements.json"
SOURCE = catalog.ROOT / ".comfyui-source-0.32.0"
WORKFLOW_WHEEL = catalog.ROOT / ".upstream-cache" / "comfyui_workflow_templates_json-0.1.42-py3-none-any.whl"
WORKFLOW_WHEEL_SHA256 = "242982d65e1c51ca03d892bc1009bb6843f457e7dfc0c20afe6438770b7a14a3"
DOCS_WHEEL = catalog.ROOT / ".upstream-cache" / "comfyui_embedded_docs-0.5.9-py3-none-any.whl"
DOCS_WHEEL_SHA256 = "30afae432a71c96aa59421d0f37388c66ff6572b8cbeee8ff045e4d5f84f896c"
SYNTHETIC_PROBE = Path(__file__).with_name("clip_merge_attention_synthetic_probe.py")


def article_path(spec: dict[str, Any]) -> Path:
    return catalog.CONTENT / "articles" / "core" / spec["directory"] / "manifest.json"


def recipe_path(recipe_id: str) -> Path:
    return catalog.CONTENT / "recipes" / RECIPE_DIRECTORIES[recipe_id] / "recipe.json"


def all_article_ids() -> set[str]:
    result: set[str] = set()
    for path in (catalog.CONTENT / "articles").rglob("manifest.json"):
        payload = catalog.load_json(path)
        if isinstance(payload, dict) and isinstance(payload.get("articleId"), str):
            result.add(payload["articleId"])
    return result


def runtime_inputs(runtime: dict[str, Any]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for group in ("required", "optional"):
        values = runtime.get("input", {}).get(group, {})
        if isinstance(values, dict):
            result.update(values)
    return result


def workflow_nodes(payload: dict[str, Any]) -> Iterator[dict[str, Any]]:
    for node in payload.get("nodes", []):
        if isinstance(node, dict):
            yield node
    definitions = payload.get("definitions")
    subgraphs = definitions.get("subgraphs", []) if isinstance(definitions, dict) else []
    for subgraph in subgraphs:
        if not isinstance(subgraph, dict):
            continue
        for node in subgraph.get("nodes", []):
            if isinstance(node, dict):
                yield node


class ClipMergeAttentionContentTests(unittest.TestCase):
    def test_articles_recipes_and_research_records_validate(self) -> None:
        article_ids = all_article_ids()
        article_schema = catalog.load_json(catalog.CONTENT / "schemas" / "article.schema.v1.json")
        recipe_schema = catalog.load_json(catalog.CONTENT / "schemas" / "recipe.schema.v1.json")
        fragment_schema = catalog.load_json(catalog.CONTENT / "schemas" / "recipe-fragment.schema.v1.json")
        research_schema = catalog.load_json(catalog.CONTENT / "schemas" / "article-research.schema.v1.json")
        errors: list[str] = []
        cliche_pattern = re.compile(
            r"важно отметить|стоит подчеркнуть|подводя итог|в современном мире|"
            r"революционн|данная нода|является незаменим|давайте разбер|"
            r"без воды|коротко о главном|понятно и доступно|по-честному",
            re.IGNORECASE,
        )

        for article_id, spec in ARTICLE_SPECS.items():
            path = article_path(spec)
            article = catalog.load_json(path)
            self.assertEqual([], catalog.json_schema_errors(article, article_schema))
            catalog.validate_article(path, article, errors)
            self.assertEqual(article_id, article["articleId"])
            self.assertEqual("draft", article["status"])
            self.assertEqual("in_review", article["editorial"]["state"])
            self.assertEqual(spec["recipe"], article["assets"][0]["id"])
            self.assertEqual([], article["runtimeIdentity"]["aliases"])

            relations = article["relations"]
            targets = relations["related"] + relations["alternatives"]
            if relations["replacedBy"] is not None:
                targets.append(relations["replacedBy"])
            self.assertTrue(set(targets).issubset(article_ids))

            body = (path.parent / article["body"]).read_text(encoding="utf-8")
            headings = re.findall(r"^## (.+)$", body, re.MULTILINE)
            self.assertEqual(EXPECTED_HEADINGS, headings)
            self.assertNotIn("\ufffd", body)
            self.assertNotRegex(body, cliche_pattern)

            research = catalog.load_json(catalog.CONTENT / "research" / "reviews" / f"{article_id}.json")
            self.assertEqual([], catalog.json_schema_errors(research, research_schema))
            self.assertEqual(spec["classType"], research["node"]["classType"])
            self.assertEqual(spec["module"], research["node"]["pythonModule"])
            self.assertEqual("fact_checked", research["state"])
            self.assertEqual("automated_assisted", research["reviewMode"])
            self.assertFalse(research["checks"]["exampleExecuted"])
            self.assertTrue(research["checks"]["exampleSchemaValidated"])
            self.assertTrue(research["knownGaps"])
            self.assertTrue(any("человеческ" in gap.lower() for gap in research["knownGaps"]))

        for recipe_id in RECIPE_DIRECTORIES:
            path = recipe_path(recipe_id)
            recipe = catalog.load_json(path)
            self.assertEqual([], catalog.json_schema_errors(recipe, recipe_schema))
            catalog.validate_recipe(path, recipe, article_ids, errors)
            self.assertEqual(recipe_id, recipe["recipeId"])
            self.assertNotIn("workflow", recipe)
            self.assertEqual("draft", recipe["editorial"]["state"])
            body = (path.parent / recipe["body"]).read_text(encoding="utf-8")
            self.assertNotRegex(body, cliche_pattern)
            fragment = catalog.load_json(path.parent / recipe["fragment"]["path"])
            self.assertEqual([], catalog.json_schema_errors(fragment, fragment_schema))
            self.assertEqual(
                EXPECTED_FRAGMENT_NODES[recipe_id],
                [(node["classType"], node["settings"]) for node in fragment["nodes"]],
            )

        self.assertEqual([], errors)

    def test_runtime_fingerprints_flags_widgets_and_fragment_ports(self) -> None:
        nodes = catalog.object_info_nodes(catalog.load_json(FULL_INVENTORY))
        for article_id, spec in ARTICLE_SPECS.items():
            runtime = dict(nodes[spec["classType"]])
            article = catalog.load_json(article_path(spec))
            self.assertEqual(spec["module"], runtime["python_module"])
            self.assertEqual(spec["fingerprint"], catalog.schema_fingerprint(spec["classType"], runtime))
            self.assertEqual(spec["fingerprint"], article["editorial"]["schemaHash"])
            self.assertEqual(spec["experimental"], bool(runtime.get("experimental", False)))
            self.assertFalse(runtime.get("deprecated", False))
            self.assertFalse(runtime.get("api_node", False))
            self.assertFalse(runtime["is_input_list"])
            self.assertEqual(["CLIP"], runtime["output"])
            self.assertEqual([False], runtime["output_is_list"])
            self.assertEqual(spec["searchAliases"], runtime["search_aliases"])

        self.assertEqual("model/merging", nodes["CLIPMergeSimple"]["category"])
        self.assertEqual("model/merging", nodes["CLIPMergeAdd"]["category"])
        self.assertEqual("model/merging", nodes["CLIPMergeSubtract"]["category"])
        self.assertEqual("experimental/attention_experiments", nodes["CLIPAttentionMultiply"]["category"])
        self.assertEqual(
            {"default": 1.0, "min": 0.0, "max": 1.0, "step": 0.01},
            nodes["CLIPMergeSimple"]["input"]["required"]["ratio"][1],
        )
        self.assertEqual(
            {"default": 1.0, "min": -10.0, "max": 10.0, "step": 0.01},
            nodes["CLIPMergeSubtract"]["input"]["required"]["multiplier"][1],
        )
        for name in ("q", "k", "v", "out"):
            self.assertEqual(
                {"advanced": True, "default": 1.0, "min": 0.0, "max": 10.0, "step": 0.01},
                nodes["CLIPAttentionMultiply"]["input"]["required"][name][1],
            )

        for recipe_id in RECIPE_DIRECTORIES:
            path = recipe_path(recipe_id)
            recipe = catalog.load_json(path)
            fragment = catalog.load_json(path.parent / recipe["fragment"]["path"])
            refs = {node["ref"]: node for node in fragment["nodes"]}
            for external in fragment["externalInputs"]:
                runtime = dict(nodes[refs[external["to"]]["classType"]])
                self.assertEqual(external["type"], runtime_inputs(runtime)[external["input"]][0])
            for node in fragment["nodes"]:
                inputs = runtime_inputs(dict(nodes[node["classType"]]))
                for name, value in node["settings"].items():
                    self.assertIn(name, inputs)
                    options = inputs[name][1]
                    self.assertGreaterEqual(value, options.get("min", value))
                    self.assertLessEqual(value, options.get("max", value))
            for connection in fragment["connections"]:
                source = dict(nodes[refs[connection["from"]]["classType"]])
                target = dict(nodes[refs[connection["to"]]["classType"]])
                output_index = source["output_name"].index(connection["output"])
                self.assertEqual(
                    source["output"][output_index],
                    runtime_inputs(target)[connection["input"]][0],
                )

        transfer = catalog.load_json(
            recipe_path("recipe.transfer-clip-weight-delta").parent / "fragment.json"
        )
        self.assertEqual(
            [{"from": "subtract", "output": "CLIP", "to": "add", "input": "clip2"}],
            transfer["connections"],
        )

    @unittest.skipUnless(SOURCE.exists(), "pinned ComfyUI source checkout is absent")
    def test_exact_source_mappings_formulas_and_replacement_absence(self) -> None:
        merge_source = (SOURCE / "comfy_extras" / "nodes_model_merging.py").read_text(encoding="utf-8")
        attention_source = (SOURCE / "comfy_extras" / "nodes_attention_multiply.py").read_text(encoding="utf-8")
        patcher_source = (SOURCE / "comfy" / "lora.py").read_text(encoding="utf-8")
        clip_source = (SOURCE / "comfy" / "sd.py").read_text(encoding="utf-8")

        self.assertIn("m.add_patches({k: kp[k]}, 1.0 - ratio, ratio)", merge_source)
        self.assertIn("m.add_patches({k: kp[k]}, - multiplier, multiplier)", merge_source)
        self.assertIn("m.add_patches({k: kp[k]}, 1.0, 1.0)", merge_source)
        self.assertIn('"CLIPMergeSubtract": CLIPSubtract', merge_source)
        self.assertIn('"CLIPMergeAdd": CLIPAdd', merge_source)
        self.assertIn('k.endswith(".position_ids") or k.endswith(".logit_scale")', merge_source)
        for projection in ("q", "k", "v", "out"):
            self.assertIn(f'self_attn.{projection}_proj.weight', attention_source)
            self.assertIn(f'self_attn.{projection}_proj.bias', attention_source)
        self.assertIn("m.add_patches({key: (None,)}, 0.0, q)", attention_source)
        self.assertIn("weight *= strength_model", patcher_source)
        self.assertLess(patcher_source.index("weight *= strength_model"), patcher_source.index("weight += function(strength *"))
        self.assertIn("n.patcher = self.patcher.clone", clip_source)
        self.assertIn("n.tokenizer = self.tokenizer", clip_source)

        replacements_text = json.dumps(catalog.load_json(REPLACEMENTS), sort_keys=True)
        for spec in ARTICLE_SPECS.values():
            self.assertNotIn(spec["classType"], replacements_text)

    @unittest.skipUnless(DOCS_WHEEL.exists(), "pinned embedded docs wheel is absent")
    def test_pinned_embedded_docs_and_recorded_discrepancies(self) -> None:
        self.assertEqual(DOCS_WHEEL_SHA256, hashlib.sha256(DOCS_WHEEL.read_bytes()).hexdigest())
        members = {
            "comfyui_embedded_docs/docs/ClipMergeSimple/en.md": "(1.0 - ratio) * clip1 + ratio * clip2",
            "comfyui_embedded_docs/docs/ClipMergeSimple/ru.md": "ratio = 1.0",
            "comfyui_embedded_docs/docs/CLIPMergeAdd/en.md": "added patches from the secondary model",
            "comfyui_embedded_docs/docs/CLIPMergeSubtract/en.md": "control the subtraction strength",
            "comfyui_embedded_docs/docs/CLIPAttentionMultiply/en.md": "query projection weights and biases",
        }
        with zipfile.ZipFile(DOCS_WHEEL) as archive:
            for member, marker in members.items():
                self.assertIn(marker, archive.read(member).decode("utf-8"))

        simple = (article_path(ARTICLE_SPECS["core.clip-merge-simple"]).parent / "ru.md").read_text(encoding="utf-8")
        subtract = (article_path(ARTICLE_SPECS["core.clip-merge-subtract"]).parent / "ru.md").read_text(encoding="utf-8")
        self.assertIn("`ratio × clip1 + (1 − ratio) × clip2`", simple)
        self.assertIn("`multiplier × (clip1 − clip2)`", subtract)
        self.assertIn("`clip1 − multiplier × clip2`", subtract)

    @unittest.skipUnless(WORKFLOW_WHEEL.exists(), "official workflow wheel is absent")
    def test_exhaustive_official_root_and_subgraph_census_has_no_cases(self) -> None:
        self.assertEqual(WORKFLOW_WHEEL_SHA256, hashlib.sha256(WORKFLOW_WHEEL.read_bytes()).hexdigest())
        targets = {spec["classType"] for spec in ARTICLE_SPECS.values()}
        counts: Counter[str] = Counter()
        file_count = 0
        root_graph_count = 0
        with zipfile.ZipFile(WORKFLOW_WHEEL) as archive:
            for member in sorted(archive.namelist()):
                if "/templates/" not in member or not member.endswith(".json"):
                    continue
                file_count += 1
                payload = json.loads(archive.read(member).decode("utf-8"))
                if not isinstance(payload, dict):
                    continue
                if isinstance(payload.get("nodes"), list):
                    root_graph_count += 1
                for node in workflow_nodes(payload):
                    if node.get("type") in targets:
                        counts[node["type"]] += 1
        self.assertEqual(512, file_count)
        self.assertEqual(496, root_graph_count)
        self.assertEqual({}, dict(counts))

    @unittest.skipUnless(SOURCE.exists(), "pinned ComfyUI source checkout is absent")
    def test_safe_exact_source_synthetic_probe(self) -> None:
        result = subprocess.run(
            [sys.executable, "-X", "utf8", str(SYNTHETIC_PROBE)],
            cwd=catalog.ROOT,
            text=True,
            capture_output=True,
            timeout=60,
            check=True,
        )
        payload = json.loads(result.stdout.strip().splitlines()[-1])
        self.assertEqual([0.25, 0.75], payload["mergeSimple"]["coefficients"])
        self.assertEqual([8.0, 16.0], payload["mergeSimple"]["weight"])
        self.assertEqual([1.0, 1.0], payload["mergeAdd"]["coefficients"])
        self.assertEqual([12.0, 24.0], payload["mergeAdd"]["weight"])
        self.assertEqual([2.0, -2.0], payload["mergeSubtract"]["coefficients"])
        self.assertEqual([-16.0, -32.0], payload["mergeSubtract"]["weight"])
        self.assertEqual(8, payload["attentionMultiply"]["matchedKeys"])
        self.assertEqual({"q": 0.5, "k": 1.5, "v": 2.0, "out": 0.0}, payload["attentionMultiply"]["factors"])
        self.assertEqual([3.0, 6.0], payload["attentionMultiply"]["weightAtFactor1_5"])


if __name__ == "__main__":
    unittest.main()
