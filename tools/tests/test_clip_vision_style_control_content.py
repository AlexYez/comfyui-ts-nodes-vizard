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
    "core.clip-vision-encode": {
        "directory": "clip-vision-encode",
        "classType": "CLIPVisionEncode",
        "fingerprint": "sha256:ae56e78e6e900e2901eaacfe37d5f25b80161d8b46a4b769e413ddcb7b87517c",
        "recipe": "recipe.encode-clip-vision-reference",
    },
    "core.style-model-apply": {
        "directory": "style-model-apply",
        "classType": "StyleModelApply",
        "fingerprint": "sha256:bb7470a38daad2f08eb32839b624331a9523483a216d707a353300b99a25bcf6",
        "recipe": "recipe.apply-style-model-reference",
    },
    "core.unclip-conditioning": {
        "directory": "unclip-conditioning",
        "classType": "unCLIPConditioning",
        "fingerprint": "sha256:253ff654e5ed2a6fd5ef99894e4657a0268830299a49bddedec8a4c1770a567b",
        "recipe": "recipe.add-unclip-reference",
    },
    "core.control-net-apply": {
        "directory": "control-net-apply",
        "classType": "ControlNetApply",
        "fingerprint": "sha256:a49e7bf116a33c0e9e68cf79730ab39e24656431d92b90bb99fecd4aa258285e",
        "recipe": "recipe.inspect-legacy-controlnet-apply",
    },
}

RECIPE_DIRECTORIES = {
    "recipe.encode-clip-vision-reference": "encode-clip-vision-reference",
    "recipe.apply-style-model-reference": "apply-style-model-reference",
    "recipe.add-unclip-reference": "add-unclip-reference",
    "recipe.inspect-legacy-controlnet-apply": "inspect-legacy-controlnet-apply",
}

EXPECTED_FRAGMENT_NODES = {
    "recipe.encode-clip-vision-reference": [
        ("CLIPVisionEncode", {"crop": "center"}),
    ],
    "recipe.apply-style-model-reference": [
        ("CLIPVisionLoader", {"clip_name": "sigclip_vision_patch14_384.safetensors"}),
        ("CLIPVisionEncode", {"crop": "center"}),
        ("StyleModelLoader", {"style_model_name": "flux1-redux-dev.safetensors"}),
        ("StyleModelApply", {"strength": 1.0, "strength_type": "multiply"}),
    ],
    "recipe.add-unclip-reference": [
        ("CLIPVisionEncode", {"crop": "center"}),
        ("unCLIPConditioning", {"strength": 0.75, "noise_augmentation": 0.0}),
    ],
    "recipe.inspect-legacy-controlnet-apply": [
        ("ControlNetApply", {"strength": 1.0}),
    ],
}

FULL_INVENTORY = catalog.CONTENT / "runtime" / "comfyui-0.32.0.object-info.json"
REPLACEMENTS = catalog.CONTENT / "runtime" / "comfyui-0.32.0.node-replacements.json"
SOURCE = catalog.ROOT / ".comfyui-source-0.32.0"
WORKFLOW_WHEEL = (
    catalog.ROOT
    / ".upstream-cache"
    / "comfyui_workflow_templates_json-0.1.42-py3-none-any.whl"
)
DOCS_WHEEL = (
    catalog.ROOT
    / ".upstream-cache"
    / "comfyui_embedded_docs-0.5.9-py3-none-any.whl"
)
PROBE = Path(__file__).with_name("clip_vision_style_control_synthetic_probe.py")


def article_path(spec: dict[str, str]) -> Path:
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


def workflow_node_records(payload: dict[str, Any], member: str) -> Iterator[dict[str, Any]]:
    for node in payload.get("nodes", []):
        if isinstance(node, dict):
            yield {"member": member, "scope": "root", "node": node, "graph": payload}
    definitions = payload.get("definitions")
    subgraphs = definitions.get("subgraphs", []) if isinstance(definitions, dict) else []
    for index, subgraph in enumerate(subgraphs):
        if not isinstance(subgraph, dict):
            continue
        for node in subgraph.get("nodes", []):
            if isinstance(node, dict):
                yield {
                    "member": member,
                    "scope": f"subgraph:{index}",
                    "node": node,
                    "graph": subgraph,
                }


def normalized_link(link: Any) -> dict[str, Any]:
    if isinstance(link, list):
        return {
            "origin_id": link[1],
            "origin_slot": link[2],
            "target_id": link[3],
            "target_slot": link[4],
            "type": link[5],
        }
    if isinstance(link, dict):
        return link
    raise AssertionError(f"unsupported workflow link: {link!r}")


class ClipVisionStyleControlContentTests(unittest.TestCase):
    def test_articles_and_fragment_only_recipes_validate(self) -> None:
        article_ids = all_article_ids()
        article_schema = catalog.load_json(
            catalog.CONTENT / "schemas" / "article.schema.v1.json"
        )
        recipe_schema = catalog.load_json(
            catalog.CONTENT / "schemas" / "recipe.schema.v1.json"
        )
        fragment_schema = catalog.load_json(
            catalog.CONTENT / "schemas" / "recipe-fragment.schema.v1.json"
        )
        research_schema = catalog.load_json(
            catalog.CONTENT / "schemas" / "article-research.schema.v1.json"
        )
        errors: list[str] = []
        cliche_pattern = re.compile(
            r"без воды|коротко о главном|понятно и доступно|по-честному|"
            r"идеальн|мощн|революцион|уникальн|в современном мире|"
            r"давайте разбер|важно отметить|стоит подчеркнуть|подводя итог|"
            r"устали от|знакомо\?|успейте|не просто.+а|является незаменим|данная нода",
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
            self.assertEqual(spec["fingerprint"], article["editorial"]["schemaHash"])
            targets = article["relations"]["related"] + article["relations"]["alternatives"]
            if article["relations"]["replacedBy"] is not None:
                targets.append(article["relations"]["replacedBy"])
            self.assertTrue(set(targets).issubset(article_ids))

            body = (path.parent / article["body"]).read_text(encoding="utf-8")
            self.assertEqual(10, len(re.findall(r"^## .+$", body, re.MULTILINE)))
            self.assertNotIn("\ufffd", body)
            self.assertIsNone(cliche_pattern.search(body))

            research_path = (
                catalog.CONTENT / "research" / "reviews" / f"{article_id}.json"
            )
            research = catalog.load_json(research_path)
            self.assertEqual([], catalog.json_schema_errors(research, research_schema))
            self.assertEqual("fact_checked", research["state"])
            self.assertEqual("automated_assisted", research["reviewMode"])
            self.assertFalse(research["checks"]["exampleExecuted"])
            self.assertTrue(research["knownGaps"])

        for recipe_id in RECIPE_DIRECTORIES:
            path = recipe_path(recipe_id)
            recipe = catalog.load_json(path)
            self.assertEqual([], catalog.json_schema_errors(recipe, recipe_schema))
            catalog.validate_recipe(path, recipe, article_ids, errors)
            self.assertEqual(recipe_id, recipe["recipeId"])
            self.assertNotIn("workflow", recipe)
            self.assertEqual("draft", recipe["editorial"]["state"])
            fragment = catalog.load_json(path.parent / recipe["fragment"]["path"])
            self.assertEqual([], catalog.json_schema_errors(fragment, fragment_schema))
            actual = [(node["classType"], node["settings"]) for node in fragment["nodes"]]
            self.assertEqual(EXPECTED_FRAGMENT_NODES[recipe_id], actual)

        self.assertEqual([], errors)

    def test_runtime_contracts_and_fingerprints_are_exact(self) -> None:
        inventory = catalog.load_json(FULL_INVENTORY)
        expected = {
            "CLIPVisionEncode": {
                "required": ["clip_vision", "image", "crop"],
                "output": ["CLIP_VISION_OUTPUT"],
                "deprecated": False,
            },
            "StyleModelApply": {
                "required": ["conditioning", "style_model", "clip_vision_output", "strength", "strength_type"],
                "output": ["CONDITIONING"],
                "deprecated": False,
            },
            "unCLIPConditioning": {
                "required": ["conditioning", "clip_vision_output", "strength", "noise_augmentation"],
                "output": ["CONDITIONING"],
                "deprecated": False,
            },
            "ControlNetApply": {
                "required": ["conditioning", "control_net", "image", "strength"],
                "output": ["CONDITIONING"],
                "deprecated": True,
            },
        }
        for spec in ARTICLE_SPECS.values():
            class_type = spec["classType"]
            runtime = inventory[class_type]
            self.assertEqual("nodes", runtime["python_module"])
            self.assertEqual(expected[class_type]["required"], runtime["input_order"]["required"])
            self.assertEqual(expected[class_type]["output"], runtime["output"])
            self.assertEqual(
                expected[class_type]["deprecated"], bool(runtime.get("deprecated", False))
            )
            self.assertEqual(spec["fingerprint"], catalog.schema_fingerprint(class_type, runtime))

        self.assertEqual([["center", "none"]], inventory["CLIPVisionEncode"]["input"]["required"]["crop"])
        self.assertEqual([0.0, 10.0, 0.001], [
            inventory["StyleModelApply"]["input"]["required"]["strength"][1][key]
            for key in ("min", "max", "step")
        ])
        self.assertEqual(
            [["multiply", "attn_bias"]],
            inventory["StyleModelApply"]["input"]["required"]["strength_type"],
        )
        self.assertEqual([-10.0, 10.0, 0.01], [
            inventory["unCLIPConditioning"]["input"]["required"]["strength"][1][key]
            for key in ("min", "max", "step")
        ])

        advanced = inventory["ControlNetApplyAdvanced"]
        self.assertEqual(
            ["positive", "negative", "control_net", "image", "strength", "start_percent", "end_percent"],
            advanced["input_order"]["required"],
        )
        self.assertEqual(["vae"], advanced["input_order"]["optional"])
        self.assertEqual(["CONDITIONING", "CONDITIONING"], advanced["output"])

    def test_fragments_use_real_ports_and_connection_types(self) -> None:
        inventory = catalog.load_json(FULL_INVENTORY)
        for recipe_id in RECIPE_DIRECTORIES:
            recipe = catalog.load_json(recipe_path(recipe_id))
            fragment = catalog.load_json(recipe_path(recipe_id).parent / recipe["fragment"]["path"])
            nodes = {node["ref"]: node for node in fragment["nodes"]}
            for external in fragment["externalInputs"]:
                runtime = inventory[nodes[external["to"]]["classType"]]
                descriptor = runtime["input"]["required"][external["input"]]
                runtime_type = "COMBO" if isinstance(descriptor[0], list) else descriptor[0]
                self.assertEqual(external["type"], runtime_type)
            for connection in fragment["connections"]:
                source = inventory[nodes[connection["from"]]["classType"]]
                target = inventory[nodes[connection["to"]]["classType"]]
                source_index = source["output_name"].index(connection["output"])
                source_type = source["output"][source_index]
                descriptor = target["input"]["required"][connection["input"]]
                target_type = "COMBO" if isinstance(descriptor[0], list) else descriptor[0]
                self.assertEqual(source_type, target_type)

    def test_full_official_workflow_census_and_topology(self) -> None:
        self.assertEqual(
            "242982d65e1c51ca03d892bc1009bb6843f457e7dfc0c20afe6438770b7a14a3",
            hashlib.sha256(WORKFLOW_WHEEL.read_bytes()).hexdigest(),
        )
        targets = {
            "CLIPVisionEncode",
            "StyleModelApply",
            "unCLIPConditioning",
            "ControlNetApply",
            "ControlNetApplyAdvanced",
        }
        records: list[dict[str, Any]] = []
        with zipfile.ZipFile(WORKFLOW_WHEEL) as archive:
            members = [
                name
                for name in archive.namelist()
                if name.startswith("comfyui_workflow_templates_json/templates/")
                and name.endswith(".json")
            ]
            self.assertEqual(512, len(members))
            root_graphs = 0
            for member in members:
                try:
                    payload = json.loads(archive.read(member))
                except (json.JSONDecodeError, UnicodeDecodeError):
                    continue
                if not isinstance(payload, dict):
                    continue
                if isinstance(payload.get("nodes"), list):
                    root_graphs += 1
                for record in workflow_node_records(payload, member):
                    if record["node"].get("type") in targets:
                        records.append(record)
        self.assertEqual(496, root_graphs)

        counts = Counter(record["node"]["type"] for record in records)
        self.assertEqual(
            {
                "CLIPVisionEncode": 42,
                "StyleModelApply": 2,
                "unCLIPConditioning": 2,
                "ControlNetApplyAdvanced": 5,
            },
            dict(counts),
        )
        clip = [record for record in records if record["node"]["type"] == "CLIPVisionEncode"]
        self.assertEqual(23, sum(record["scope"] == "root" for record in clip))
        self.assertEqual(19, sum(record["scope"] != "root" for record in clip))
        self.assertEqual(
            Counter({("center",): 13, ("none",): 29}),
            Counter(tuple(record["node"].get("widgets_values", [])) for record in clip),
        )
        self.assertEqual(24, len({record["member"] for record in clip}))

        style = [record for record in records if record["node"]["type"] == "StyleModelApply"]
        self.assertTrue(all(record["scope"] == "root" for record in style))
        self.assertEqual({"flux_redux_model_example.json"}, {Path(record["member"]).name for record in style})
        self.assertTrue(all(record["node"]["widgets_values"] == [1, "multiply"] for record in style))

        unclip = [record for record in records if record["node"]["type"] == "unCLIPConditioning"]
        self.assertEqual({"sdxl_revision_text_prompts.json"}, {Path(record["member"]).name for record in unclip})
        self.assertTrue(all(record["node"]["widgets_values"] == [0.75, 0] for record in unclip))

        advanced = [record for record in records if record["node"]["type"] == "ControlNetApplyAdvanced"]
        self.assertEqual(3, sum(record["scope"] == "root" for record in advanced))
        self.assertEqual(2, sum(record["scope"] != "root" for record in advanced))
        self.assertEqual([0.66, 0.7, 1.0, 1.0, 1.0], sorted(round(float(record["node"]["widgets_values"][0]), 2) for record in advanced))
        self.assertTrue(all(record["node"]["widgets_values"][1:] == [0, 1] for record in advanced))

        for record in style + unclip + advanced:
            graph = record["graph"]
            node = record["node"]
            by_id = {item.get("id"): item for item in graph.get("nodes", []) if isinstance(item, dict)}
            links = [normalized_link(link) for link in graph.get("links", [])]
            outgoing = [
                by_id.get(link.get("target_id"), {}).get("type")
                for link in links
                if link.get("origin_id") == node.get("id")
            ]
            if node["type"] == "StyleModelApply":
                self.assertTrue(any(value in {"StyleModelApply", "BasicGuider"} for value in outgoing))
            elif node["type"] == "unCLIPConditioning":
                self.assertTrue(any(value in {"unCLIPConditioning", "KSampler"} for value in outgoing))
            else:
                self.assertEqual(2, outgoing.count("KSampler"))

    def test_docs_source_and_replacement_claims_are_pinned(self) -> None:
        self.assertEqual(
            "30afae432a71c96aa59421d0f37388c66ff6572b8cbeee8ff045e4d5f84f896c",
            hashlib.sha256(DOCS_WHEEL.read_bytes()).hexdigest(),
        )
        docs = {
            "comfyui_embedded_docs/docs/ClipVisionEncode/en.md": "CLIP_VISION_OUTPUT",
            "comfyui_embedded_docs/docs/StyleModelApply/en.md": "style_model",
            "comfyui_embedded_docs/docs/UnclipConditioning/en.md": "noise_augmentation",
            "comfyui_embedded_docs/docs/ControlnetApply/en.md": "start_percent",
        }
        with zipfile.ZipFile(DOCS_WHEEL) as archive:
            for member, marker in docs.items():
                self.assertIn(marker, archive.read(member).decode("utf-8"))

        replacements = catalog.load_json(REPLACEMENTS)
        self.assertNotIn("ControlNetApply", replacements)
        self.assertEqual("ControlNetLoader", replacements["T2IAdapterLoader"][0]["new_node_id"])

        nodes_source = (SOURCE / "nodes.py").read_text(encoding="utf-8")
        self.assertIn("class ControlNetApply:", nodes_source)
        self.assertIn("DEPRECATED = True", nodes_source)
        self.assertIn("n[1]['control_apply_to_uncond'] = True", nodes_source)
        self.assertIn("d['control_apply_to_uncond'] = False", nodes_source)
        self.assertIn("cond = style_model.get_cond(clip_vision_output).flatten", nodes_source)
        self.assertIn('"unclip_conditioning": [{"clip_vision_output": clip_vision_output', nodes_source)

    def test_exact_source_synthetic_probe(self) -> None:
        result = subprocess.run(
            [sys.executable, str(PROBE)],
            cwd=catalog.ROOT,
            check=True,
            capture_output=True,
            text=True,
        )
        payload = json.loads(result.stdout)
        self.assertEqual([True, False], payload["clipVisionEncode"]["cropFlags"])
        self.assertEqual([1, 5, 4], payload["styleModelApply"]["multiplyShape"])
        self.assertTrue(payload["styleModelApply"]["zeroMultiplyStillAppendsTokens"])
        self.assertTrue(payload["styleModelApply"]["batchMismatchRaises"])
        self.assertEqual(2, payload["unCLIPConditioning"]["appendCount"])
        self.assertTrue(payload["unCLIPConditioning"]["zeroStrengthIdentity"])
        self.assertEqual([2, 3, 5, 7], payload["controlNetApply"]["hintShape"])
        self.assertTrue(payload["controlNetApply"]["legacyApplyToUncond"])
        self.assertFalse(payload["controlNetApply"]["advancedApplyToUncond"])


if __name__ == "__main__":
    unittest.main()
