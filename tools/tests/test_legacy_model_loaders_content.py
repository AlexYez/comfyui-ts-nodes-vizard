from __future__ import annotations

import hashlib
import json
import re
import unittest
import zipfile
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterator

from tools import catalog


ARTICLE_SPECS = {
    "core.checkpoint-loader": ("checkpoint-loader", "CheckpointLoader", "nodes", "sha256:193530a019f679cf024f7836b81d31681103aae9fd7f831771259cd60db80de2"),
    "core.diffusers-loader": ("diffusers-loader", "DiffusersLoader", "nodes", "sha256:a90490221d7b07d7d10e653d3dd0a2a32a98bae24a6c89ae711b8c81f01b99c1"),
    "core.lora-loader-model-only": ("lora-loader-model-only", "LoraLoaderModelOnly", "nodes", "sha256:d9adbd111c3acfde4dc505245572c7b15e7c7e4dbdb347a819fa8b4f3f79d3c4"),
    "core.hypernetwork-loader": ("hypernetwork-loader", "HypernetworkLoader", "comfy_extras.nodes_hypernetwork", "sha256:e489e0e984d0aae1aefb499e80a1c9ac519d5180e5091a8f7c82059bbc904c9e"),
}
RECIPE_DIRS = ("legacy-checkpoint-with-config", "legacy-diffusers-directory", "z-image-model-only-lora", "apply-hypernetwork")
INVENTORY = catalog.CONTENT / "runtime" / "comfyui-0.32.0.object-info.json"
REPLACEMENTS = catalog.CONTENT / "runtime" / "comfyui-0.32.0.node-replacements.json"
SOURCE = catalog.ROOT / ".comfyui-source-0.32.0"
WORKFLOW_WHEEL = catalog.ROOT / ".upstream-cache" / "comfyui_workflow_templates_json-0.1.42-py3-none-any.whl"


def records(payload: dict[str, Any]) -> Iterator[tuple[str, dict[str, Any]]]:
    for node in payload.get("nodes", []):
        if isinstance(node, dict):
            yield "root", node
    definitions = payload.get("definitions")
    if isinstance(definitions, dict):
        for subgraph in definitions.get("subgraphs", []):
            if isinstance(subgraph, dict):
                for node in subgraph.get("nodes", []):
                    if isinstance(node, dict):
                        yield "subgraph", node


class LegacyModelLoadersContentTests(unittest.TestCase):
    def test_schema_identity_honesty_and_natural_russian(self) -> None:
        article_schema = catalog.load_json(catalog.CONTENT / "schemas" / "article.schema.v1.json")
        recipe_schema = catalog.load_json(catalog.CONTENT / "schemas" / "recipe.schema.v1.json")
        fragment_schema = catalog.load_json(catalog.CONTENT / "schemas" / "recipe-fragment.schema.v1.json")
        research_schema = catalog.load_json(catalog.CONTENT / "schemas" / "article-research.schema.v1.json")
        inventory = catalog.load_json(INVENTORY)
        article_ids = {catalog.load_json(path)["articleId"] for path in (catalog.CONTENT / "articles").rglob("manifest.json")}
        errors: list[str] = []
        texts: list[Path] = []
        for article_id, (directory, class_type, module, fingerprint) in ARTICLE_SPECS.items():
            path = catalog.CONTENT / "articles" / "core" / directory / "manifest.json"
            article = catalog.load_json(path)
            self.assertEqual([], catalog.json_schema_errors(article, article_schema))
            catalog.validate_article(path, article, errors)
            self.assertEqual((article_id, "draft", "in_review"), (article["articleId"], article["status"], article["editorial"]["state"]))
            self.assertEqual(module, article["runtimeIdentity"]["pythonModule"])
            self.assertEqual(fingerprint, article["editorial"]["schemaHash"])
            self.assertEqual(fingerprint, catalog.schema_fingerprint(class_type, inventory[class_type]))
            for relation in article["relations"]["related"] + article["relations"]["alternatives"]:
                self.assertIn(relation, article_ids)
            body = path.parent / "ru.md"
            self.assertEqual(10, len(re.findall(r"^## ", body.read_text(encoding="utf-8"), re.MULTILINE)))
            texts.append(body)
            research = catalog.load_json(catalog.CONTENT / "research" / "reviews" / f"{article_id}.json")
            self.assertEqual([], catalog.json_schema_errors(research, research_schema))
            self.assertEqual(("fact_checked", "automated_assisted", False), (research["state"], research["reviewMode"], research["checks"]["exampleExecuted"]))
            self.assertTrue(research["knownGaps"])

        for directory in RECIPE_DIRS:
            path = catalog.CONTENT / "recipes" / directory / "recipe.json"
            recipe = catalog.load_json(path)
            self.assertEqual([], catalog.json_schema_errors(recipe, recipe_schema))
            catalog.validate_recipe(path, recipe, article_ids, errors)
            self.assertNotIn("workflow", recipe)
            fragment_path = path.parent / "fragment.json"
            fragment = catalog.load_json(fragment_path)
            self.assertEqual([], catalog.json_schema_errors(fragment, fragment_schema))
            catalog.validate_fragment(fragment_path, fragment, errors)
            texts.append(path.parent / "ru.md")
        self.assertEqual([], errors)

        forbidden = ("важно отметить", "стоит отметить", "таким образом", "в современном мире", "давайте", "погрузимся", "революционный")
        for path in texts:
            text = path.read_text(encoding="utf-8").lower()
            self.assertNotIn("\ufffd", text)
            for phrase in forbidden:
                self.assertNotIn(phrase, text, path)

    def test_runtime_and_replacement_contracts(self) -> None:
        inventory = catalog.load_json(INVENTORY)
        self.assertTrue(inventory["CheckpointLoader"]["deprecated"])
        self.assertTrue(inventory["DiffusersLoader"]["deprecated"])
        self.assertEqual(["MODEL", "CLIP", "VAE"], inventory["CheckpointLoader"]["output"])
        self.assertEqual(["MODEL", "CLIP", "VAE"], inventory["DiffusersLoader"]["output"])
        self.assertEqual((-100.0, 100.0, 0.01), tuple(inventory["LoraLoaderModelOnly"]["input"]["required"]["strength_model"][1][key] for key in ("min", "max", "step")))
        self.assertEqual((-10.0, 10.0, 0.01), tuple(inventory["HypernetworkLoader"]["input"]["required"]["strength"][1][key] for key in ("min", "max", "step")))
        replacements = catalog.load_json(REPLACEMENTS)
        self.assertNotIn("CheckpointLoader", replacements)
        self.assertNotIn("DiffusersLoader", replacements)

        zimage = catalog.load_json(catalog.CONTENT / "recipes" / "z-image-model-only-lora" / "fragment.json")
        self.assertEqual(["UNETLoader", "LoraLoaderModelOnly"], [node["classType"] for node in zimage["nodes"]])
        self.assertEqual({("MODEL", "model")}, {(link["output"], link["input"]) for link in zimage["connections"]})
        hyper = catalog.load_json(catalog.CONTENT / "recipes" / "apply-hypernetwork" / "fragment.json")
        self.assertEqual([{"id": "base_model", "type": "MODEL", "to": "hypernetwork", "input": "model"}], hyper["externalInputs"])

    @unittest.skipUnless(SOURCE.exists(), "pinned ComfyUI source checkout is absent")
    def test_pinned_source_semantics(self) -> None:
        nodes = (SOURCE / "nodes.py").read_text(encoding="utf-8")
        sd = (SOURCE / "comfy" / "sd.py").read_text(encoding="utf-8")
        diffusers = (SOURCE / "comfy" / "diffusers_load.py").read_text(encoding="utf-8")
        hyper = (SOURCE / "comfy_extras" / "nodes_hypernetwork.py").read_text(encoding="utf-8")

        checkpoint_function = sd[sd.index("def load_checkpoint("):sd.index("def load_checkpoint_guess_config(")]
        self.assertLess(checkpoint_function.index("load_checkpoint_guess_config"), checkpoint_function.index("open(config_path"))
        self.assertIn('model_config_params["parameterization"] == "v"', checkpoint_function)
        self.assertIn('clip_config.get("params", {}).get("layer_idx", None)', checkpoint_function)
        self.assertIn('if "model_index.json" in files', nodes)
        self.assertIn("if model_path not in self._model_paths()", nodes)
        self.assertIn('first_file(os.path.join(model_path, "unet")', diffusers)
        self.assertIn('first_file(os.path.join(model_path, "text_encoder_2")', diffusers)
        self.assertIn("comfy.sd.load_clip(text_encoder_paths", diffusers)
        self.assertIn("self.load_lora(model, None, lora_name, strength_model, 0)", nodes)
        self.assertIn("k = k + hn[0](k) * self.strength", hyper)
        self.assertIn("v = v + hn[1](v) * self.strength", hyper)
        self.assertIn("set_model_attn1_patch(patch)", hyper)
        self.assertIn("set_model_attn2_patch(patch)", hyper)
        self.assertIn("if patch is not None", hyper)

    @unittest.skipUnless(WORKFLOW_WHEEL.exists(), "official workflow wheel is absent")
    def test_exhaustive_workflow_census_and_lora_case(self) -> None:
        self.assertEqual("242982d65e1c51ca03d892bc1009bb6843f457e7dfc0c20afe6438770b7a14a3", hashlib.sha256(WORKFLOW_WHEEL.read_bytes()).hexdigest())
        targets = {spec[1] for spec in ARTICLE_SPECS.values()}
        counts: Counter[tuple[str, str]] = Counter()
        files: dict[str, set[str]] = defaultdict(set)
        workflows: dict[str, dict[str, Any]] = {}
        parsed = root_graphs = 0
        with zipfile.ZipFile(WORKFLOW_WHEEL) as archive:
            for member in sorted(name for name in archive.namelist() if name.endswith(".json")):
                payload = json.loads(archive.read(member).decode("utf-8"))
                parsed += 1
                if not isinstance(payload, dict):
                    continue
                if isinstance(payload.get("nodes"), list):
                    root_graphs += 1
                workflows[member] = payload
                for scope, node in records(payload):
                    class_type = node.get("type")
                    if class_type in targets:
                        counts[(class_type, scope)] += 1
                        files[class_type].add(member)
        self.assertEqual((512, 496), (parsed, root_graphs))
        for class_type in ("CheckpointLoader", "DiffusersLoader", "HypernetworkLoader"):
            self.assertEqual((0, 0, 0), (counts[(class_type, "root")], counts[(class_type, "subgraph")], len(files[class_type])))
        self.assertEqual((17, 126, 75), (counts[("LoraLoaderModelOnly", "root")], counts[("LoraLoaderModelOnly", "subgraph")], len(files["LoraLoaderModelOnly"])))

        case = next(payload for name, payload in workflows.items() if name.endswith("/basic_switch_node.json"))
        nodes = {node["id"]: node for node in case["nodes"]}
        self.assertEqual(["z_image_turbo_bf16.safetensors", "default"], nodes[60]["widgets_values"])
        self.assertEqual(["pixel_art_style_z_image_turbo.safetensors", 1], nodes[62]["widgets_values"])
        self.assertIn([60, 60, 0, 62, 0, "MODEL"], case["links"])
        self.assertIn([59, 62, 0, 61, 1, "MODEL"], case["links"])


if __name__ == "__main__":
    unittest.main()
