from __future__ import annotations

import ast
import base64
import csv
import hashlib
import io
import json
import math
import re
import unittest
import zipfile
from collections import Counter
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Iterator

import torch

from tools import catalog


ARTICLE_SPECS = {
    "core.model-sampling-sd3": {
        "directory": "model-sampling-sd3",
        "classType": "ModelSamplingSD3",
        "module": "comfy_extras.nodes_model_advanced",
        "category": "model/patch/stable diffusion",
        "fingerprint": "sha256:4a4a9b9903f96ed7fcb1a5e402014fac0c167382636201a40c648e42a09e41af",
        "recipe": "recipe.hunyuan-video-sd3-shift-guider",
    },
    "core.model-sampling-aura-flow": {
        "directory": "model-sampling-aura-flow",
        "classType": "ModelSamplingAuraFlow",
        "module": "comfy_extras.nodes_model_advanced",
        "category": "model/patch",
        "fingerprint": "sha256:653af937b5cbd5bf4fdea1b4c95785f9b34b6a1a4b12340b4caff9cd0043d1d1",
        "recipe": "recipe.chroma-aura-flow-sampling-branch",
    },
    "core.model-sampling-flux": {
        "directory": "model-sampling-flux",
        "classType": "ModelSamplingFlux",
        "module": "comfy_extras.nodes_model_advanced",
        "category": "model/patch/flux",
        "fingerprint": "sha256:0fe48d5a1b5fc5b00ecf81615c929f08f7ce5159d7729549331a568461510242",
        "recipe": "recipe.flux-resolution-sampling-branch",
    },
    "core.model-sampling-ltxv": {
        "directory": "model-sampling-ltxv",
        "classType": "ModelSamplingLTXV",
        "module": "comfy_extras.nodes_lt",
        "category": "model/patch/ltxv",
        "fingerprint": "sha256:814c470ff6d2ae3e36dddb102c1c901e4fd95b9475cf45b00d95fb668a0c6d64",
        "recipe": "recipe.ltxv-shape-aware-sampling",
    },
}

RECIPE_DIRECTORIES = {
    "recipe.hunyuan-video-sd3-shift-guider": "hunyuan-video-sd3-shift-guider",
    "recipe.chroma-aura-flow-sampling-branch": "chroma-aura-flow-sampling-branch",
    "recipe.flux-resolution-sampling-branch": "flux-resolution-sampling-branch",
    "recipe.ltxv-shape-aware-sampling": "ltxv-shape-aware-sampling",
}

EXPECTED_FRAGMENT_NODES = {
    "recipe.hunyuan-video-sd3-shift-guider": [
        ("ModelSamplingSD3", {"shift": 7.0}),
        ("BasicGuider", {}),
    ],
    "recipe.chroma-aura-flow-sampling-branch": [
        ("ModelSamplingAuraFlow", {"shift": 1.0}),
        ("CFGGuider", {"cfg": 3.5}),
        ("BasicScheduler", {"scheduler": "beta", "steps": 26, "denoise": 1.0}),
    ],
    "recipe.flux-resolution-sampling-branch": [
        (
            "ModelSamplingFlux",
            {"max_shift": 1.15, "base_shift": 0.5, "width": 1024, "height": 1024},
        ),
        ("BasicGuider", {}),
        ("BasicScheduler", {"scheduler": "simple", "steps": 20, "denoise": 1.0}),
    ],
    "recipe.ltxv-shape-aware-sampling": [
        ("ModelSamplingLTXV", {"max_shift": 2.05, "base_shift": 0.95}),
        ("BasicScheduler", {"scheduler": "simple", "steps": 20, "denoise": 1.0}),
    ],
}

SOURCE = catalog.ROOT / ".comfyui-source-0.32.0"
INVENTORY = catalog.CONTENT / "runtime" / "comfyui-0.32.0.object-info.json"
REPLACEMENTS = catalog.CONTENT / "runtime" / "comfyui-0.32.0.node-replacements.json"
WORKFLOW_WHEEL = catalog.ROOT / ".upstream-cache" / "comfyui_workflow_templates_json-0.1.42-py3-none-any.whl"
WORKFLOW_SHA256 = "242982d65e1c51ca03d892bc1009bb6843f457e7dfc0c20afe6438770b7a14a3"
DOCS_WHEEL = catalog.ROOT / ".upstream-cache" / "comfyui_embedded_docs-0.5.9-py3-none-any.whl"
DOCS_SHA256 = "30afae432a71c96aa59421d0f37388c66ff6572b8cbeee8ff045e4d5f84f896c"
DOC_HASHES = {
    ("ModelSamplingSD3", "en"): "3de9a3e46047841589657d07530f7ddbc091ee0d6d26d777127cb73545735c6b",
    ("ModelSamplingSD3", "ru"): "68cdf566dab9a97deb281f9f24c8cfdce342b37fd0df1ccc3bf7daef92458e33",
    ("ModelSamplingAuraFlow", "en"): "92ea53dd43079dcac08314645db6779448bf333afdb4e6fe5a57bfb0c513f213",
    ("ModelSamplingAuraFlow", "ru"): "2358ec191f3d6baac41140f5041eb72dc73a91a5f2fc836678debe2150c4b55b",
    ("ModelSamplingFlux", "en"): "21a34bd4b1a3738fcaabf7d7a66e170ed70b31a33780d3e2f4b8d8d2d238624d",
    ("ModelSamplingFlux", "ru"): "ace516f9f828ec5ecf3c7c2fb40e42c8dd25d0623cbea1ad77253647d474999d",
    ("ModelSamplingLTXV", "en"): "e8fc5867bd96988c0e33de5c55460d8a5e12aa91a96f03ae159935613683829f",
    ("ModelSamplingLTXV", "ru"): "c63d0242c3bad05560acda2cfa2dab507d2c239aa683dbb18bcf97c585d49fd9",
}
TARGET_TYPES = {spec["classType"] for spec in ARTICLE_SPECS.values()}


def article_path(spec: dict[str, Any]) -> Path:
    return catalog.CONTENT / "articles" / "core" / spec["directory"] / "manifest.json"


def all_article_ids() -> set[str]:
    ids: set[str] = set()
    for path in (catalog.CONTENT / "articles").rglob("manifest.json"):
        payload = catalog.load_json(path)
        if isinstance(payload, dict) and isinstance(payload.get("articleId"), str):
            ids.add(payload["articleId"])
    return ids


def graph_records(payload: dict[str, Any], member: str) -> Iterator[dict[str, Any]]:
    for node in payload.get("nodes", []):
        if isinstance(node, dict):
            yield {"member": member, "workflowId": payload.get("id"), "scope": "root", "node": node}
    definitions = payload.get("definitions")
    subgraphs = definitions.get("subgraphs", []) if isinstance(definitions, dict) else []
    for subgraph in subgraphs:
        if not isinstance(subgraph, dict):
            continue
        for node in subgraph.get("nodes", []):
            if isinstance(node, dict):
                yield {
                    "member": member,
                    "workflowId": payload.get("id"),
                    "scope": "subgraph",
                    "subgraphId": subgraph.get("id"),
                    "node": node,
                }


class FlowSamplingStub:
    def __init__(self, model_config: Any = None) -> None:
        self.model_config = model_config

    def set_parameters(self, shift: float, multiplier: float = 1000) -> None:
        self.shift = shift
        self.multiplier = multiplier

    def set_noise_scale(self, value: float) -> None:
        self.noise_scale = float(value)


class FluxSamplingStub:
    def __init__(self, model_config: Any = None) -> None:
        self.model_config = model_config

    def set_parameters(self, shift: float) -> None:
        self.shift = shift


class ConstStub:
    pass


class FakePatchModel:
    def __init__(self, noise_scale: float = 1.7) -> None:
        self.model = SimpleNamespace(model_config=SimpleNamespace(sampling_settings={}))
        self.objects: dict[str, Any] = {
            "model_sampling": SimpleNamespace(noise_scale=noise_scale)
        }
        self.cloned_from: FakePatchModel | None = None

    def clone(self) -> "FakePatchModel":
        clone = FakePatchModel(self.objects["model_sampling"].noise_scale)
        clone.cloned_from = self
        return clone

    def get_model_object(self, name: str) -> Any:
        return self.objects[name]

    def add_object_patch(self, name: str, value: Any) -> None:
        self.objects[name] = value


def extract_legacy_patch_classes() -> dict[str, type]:
    path = SOURCE / "comfy_extras" / "nodes_model_advanced.py"
    tree = ast.parse(path.read_text(encoding="utf-8"))
    wanted = {"ModelSamplingSD3", "ModelSamplingAuraFlow", "ModelSamplingFlux"}
    body = [node for node in tree.body if isinstance(node, ast.ClassDef) and node.name in wanted]
    namespace: dict[str, Any] = {
        "comfy": SimpleNamespace(
            model_sampling=SimpleNamespace(
                ModelSamplingDiscreteFlow=FlowSamplingStub,
                ModelSamplingFlux=FluxSamplingStub,
                CONST=ConstStub,
            )
        ),
        "nodes": SimpleNamespace(MAX_RESOLUTION=16384),
    }
    exec(compile(ast.Module(body=body, type_ignores=[]), str(path), "exec"), namespace)
    return {name: namespace[name] for name in wanted}


def extract_ltxv_patch_class() -> type:
    path = SOURCE / "comfy_extras" / "nodes_lt.py"
    tree = ast.parse(path.read_text(encoding="utf-8"))
    class_node = next(
        node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == "ModelSamplingLTXV"
    )

    class ComfyNode:
        pass

    class NodeOutput:
        def __init__(self, *args: Any) -> None:
            self.args = args

    namespace: dict[str, Any] = {
        "io": SimpleNamespace(ComfyNode=ComfyNode, NodeOutput=NodeOutput),
        "math": math,
        "comfy": SimpleNamespace(
            model_sampling=SimpleNamespace(ModelSamplingFlux=FluxSamplingStub, CONST=ConstStub)
        ),
    }
    exec(compile(ast.Module(body=[class_node], type_ignores=[]), str(path), "exec"), namespace)
    return namespace["ModelSamplingLTXV"]


def extract_underlying_sampling_math() -> dict[str, Any]:
    path = SOURCE / "comfy" / "model_sampling.py"
    tree = ast.parse(path.read_text(encoding="utf-8"))
    wanted_functions = {"reshape_sigma", "time_snr_shift", "flux_time_shift"}
    wanted_classes = {"CONST", "ModelSamplingDiscreteFlow", "ModelSamplingFlux"}
    body = [
        node
        for node in tree.body
        if (isinstance(node, ast.FunctionDef) and node.name in wanted_functions)
        or (isinstance(node, ast.ClassDef) and node.name in wanted_classes)
    ]
    namespace: dict[str, Any] = {"torch": torch, "math": math}
    exec(compile(ast.Module(body=body, type_ignores=[]), str(path), "exec"), namespace)
    return namespace


class ModelSamplingPatchContentTests(unittest.TestCase):
    def test_articles_recipes_ledgers_and_russian_contract(self) -> None:
        article_schema = catalog.load_json(catalog.CONTENT / "schemas" / "article.schema.v1.json")
        recipe_schema = catalog.load_json(catalog.CONTENT / "schemas" / "recipe.schema.v1.json")
        fragment_schema = catalog.load_json(catalog.CONTENT / "schemas" / "recipe-fragment.schema.v1.json")
        research_schema = catalog.load_json(catalog.CONTENT / "schemas" / "article-research.schema.v1.json")
        article_ids = all_article_ids()
        article_errors: list[str] = []

        for article_id, spec in ARTICLE_SPECS.items():
            path = article_path(spec)
            matching_manifests = [
                candidate
                for candidate in (catalog.CONTENT / "articles").rglob("manifest.json")
                if catalog.load_json(candidate).get("articleId") == article_id
            ]
            self.assertEqual([path], matching_manifests, f"duplicate articleId: {article_id}")
            article = catalog.load_json(path)
            self.assertEqual([], catalog.json_schema_errors(article, article_schema))
            catalog.validate_article(path, article, article_errors)
            self.assertEqual(article_id, article["articleId"])
            self.assertEqual("draft", article["status"])
            self.assertEqual("in_review", article["editorial"]["state"])
            self.assertFalse(article["experimental"])
            self.assertEqual(spec["fingerprint"], article["editorial"]["schemaHash"])
            self.assertIn(spec["recipe"], [asset["id"] for asset in article["assets"]])

            relations = article["relations"]
            targets = list(relations["related"]) + list(relations["alternatives"])
            if relations["replacedBy"] is not None:
                targets.append(relations["replacedBy"])
            self.assertTrue(set(targets).issubset(article_ids), (article_id, set(targets) - article_ids))

            body = (path.parent / article["body"]).read_text(encoding="utf-8")
            headings = [
                item
                for item in re.findall(r"^## (.+)$", body, flags=re.MULTILINE)
                if item != "Источники"
            ]
            self.assertEqual(10, len(headings), article_id)
            self.assertIn("Редактор пока не проверил материал вручную.", body)
            self.assertNotIn("\ufffd", body)
            self.assertNotRegex(
                body.lower(),
                r"важно отметить|стоит отметить|в современном мире|революционн|"
                r"данная нода|давайте разбер|подводя итог|мощный инструмент|"
                r"не просто .{0,80}, а",
            )
            for source in article["sources"]:
                url = source["url"]
                if "github.com/Comfy-Org/ComfyUI/" in url:
                    self.assertIn("c2bcbecd82ec5ae66594340b395c24ef0217b238", url)
                if "github.com/Comfy-Org/embedded-docs/" in url:
                    self.assertIn("1d258cf6e374d60d138a2bfcd273c7e11f750ef9", url)
                if "github.com/Comfy-Org/workflow_templates/" in url:
                    self.assertIn("cca1ea5ea4560108ecc2f44dee951f41ea433062", url)

            ledger = catalog.load_json(
                catalog.CONTENT / "research" / "reviews" / f"{article_id}.json"
            )
            self.assertEqual([], catalog.json_schema_errors(ledger, research_schema))
            self.assertEqual("fact_checked", ledger["state"])
            self.assertEqual("automated_assisted", ledger["reviewMode"])
            self.assertFalse(ledger["checks"]["exampleExecuted"])
            self.assertTrue(ledger["checks"]["factsRecheckedAfterEditing"])
            self.assertTrue(
                any("Редактор пока не проверил материал вручную." in gap for gap in ledger["knownGaps"])
            )
            self.assertNotIn("approved", json.dumps(ledger, ensure_ascii=False).lower())

        self.assertEqual([], article_errors)

        recipe_errors: list[str] = []
        inventory = catalog.load_json(INVENTORY)
        for recipe_id, directory in RECIPE_DIRECTORIES.items():
            path = catalog.CONTENT / "recipes" / directory / "recipe.json"
            matching_recipes = [
                candidate
                for candidate in (catalog.CONTENT / "recipes").rglob("recipe.json")
                if catalog.load_json(candidate).get("recipeId") == recipe_id
            ]
            self.assertEqual([path], matching_recipes, f"duplicate recipeId: {recipe_id}")
            recipe = catalog.load_json(path)
            self.assertEqual([], catalog.json_schema_errors(recipe, recipe_schema))
            catalog.validate_recipe(path, recipe, article_ids, recipe_errors)
            self.assertEqual(recipe_id, recipe["recipeId"])
            self.assertEqual("draft", recipe["editorial"]["state"])
            self.assertNotIn("workflow", recipe)
            body = (path.parent / recipe["body"]).read_text(encoding="utf-8")
            self.assertIn("Редактор пока не проверил материал вручную.", body)

            fragment_path = path.parent / recipe["fragment"]["path"]
            fragment = catalog.load_json(fragment_path)
            self.assertEqual([], catalog.json_schema_errors(fragment, fragment_schema))
            catalog.validate_fragment(fragment_path, fragment, recipe_errors)
            actual_nodes = [(node["classType"], node["settings"]) for node in fragment["nodes"]]
            self.assertEqual(EXPECTED_FRAGMENT_NODES[recipe_id], actual_nodes)
            self.assertTrue(all(node["classType"] in inventory for node in fragment["nodes"]))
            refs = {node["ref"] for node in fragment["nodes"]}
            self.assertTrue(all(item["to"] in refs for item in fragment["externalInputs"]))
            self.assertTrue(all(link["from"] in refs and link["to"] in refs for link in fragment["connections"]))

        self.assertEqual([], recipe_errors)

    def test_runtime_contracts_fingerprints_flags_and_replacements(self) -> None:
        inventory = catalog.load_json(INVENTORY)
        for spec in ARTICLE_SPECS.values():
            definition = inventory[spec["classType"]]
            self.assertEqual(spec["module"], definition["python_module"])
            self.assertEqual(spec["category"], definition["category"])
            self.assertEqual(["MODEL"], definition["output"])
            self.assertEqual(["MODEL"], definition["output_name"])
            for flag in ("deprecated", "experimental", "dev_only", "api_node", "output_node"):
                self.assertFalse(definition.get(flag, False), (spec["classType"], flag))
            self.assertEqual(spec["fingerprint"], catalog.schema_fingerprint(spec["classType"], definition))

        sd3 = inventory["ModelSamplingSD3"]
        aura = inventory["ModelSamplingAuraFlow"]
        self.assertEqual(["model", "shift"], sd3["input_order"]["required"])
        self.assertEqual(["model", "shift"], aura["input_order"]["required"])
        self.assertEqual(
            {"default": 3.0, "min": 0.0, "max": 100.0, "step": 0.01},
            sd3["input"]["required"]["shift"][1],
        )
        self.assertEqual(
            {"default": 1.73, "min": 0.0, "max": 100.0, "step": 0.01},
            aura["input"]["required"]["shift"][1],
        )

        flux = inventory["ModelSamplingFlux"]
        self.assertEqual(
            ["model", "max_shift", "base_shift", "width", "height"],
            flux["input_order"]["required"],
        )
        self.assertEqual(
            {"default": 1.15, "min": 0.0, "max": 100.0, "step": 0.01, "advanced": True},
            flux["input"]["required"]["max_shift"][1],
        )
        self.assertEqual(
            {"default": 0.5, "min": 0.0, "max": 100.0, "step": 0.01, "advanced": True},
            flux["input"]["required"]["base_shift"][1],
        )
        self.assertEqual(
            {"default": 1024, "min": 16, "max": 16384, "step": 8},
            flux["input"]["required"]["width"][1],
        )
        self.assertEqual(flux["input"]["required"]["width"], flux["input"]["required"]["height"])

        ltxv = inventory["ModelSamplingLTXV"]
        self.assertEqual(["model", "max_shift", "base_shift"], ltxv["input_order"]["required"])
        self.assertEqual(["latent"], ltxv["input_order"]["optional"])
        self.assertEqual("LATENT", ltxv["input"]["optional"]["latent"][0])
        self.assertEqual(
            {"default": 2.05, "min": 0.0, "max": 100.0, "step": 0.01},
            ltxv["input"]["required"]["max_shift"][1],
        )
        self.assertEqual(
            {"default": 0.95, "min": 0.0, "max": 100.0, "step": 0.01},
            ltxv["input"]["required"]["base_shift"][1],
        )

        replacements = catalog.load_json(REPLACEMENTS)
        serialized = json.dumps(replacements, ensure_ascii=False)
        for class_type in TARGET_TYPES:
            self.assertNotIn(class_type, replacements)
            self.assertNotIn(f'"new_node_id": "{class_type}"', serialized)

    def test_exact_source_patch_and_sampling_math_probes(self) -> None:
        classes = extract_legacy_patch_classes()

        original_sd3 = FakePatchModel(noise_scale=1.7)
        patched_sd3 = classes["ModelSamplingSD3"]().patch(original_sd3, 3.0)[0]
        self.assertIsNot(original_sd3, patched_sd3)
        self.assertIs(patched_sd3.cloned_from, original_sd3)
        sd3_sampling = patched_sd3.objects["model_sampling"]
        self.assertEqual((3.0, 1000), (sd3_sampling.shift, sd3_sampling.multiplier))
        self.assertEqual(1.7, sd3_sampling.noise_scale)

        original_aura = FakePatchModel(noise_scale=0.8)
        patched_aura = classes["ModelSamplingAuraFlow"]().patch_aura(original_aura, 1.73)[0]
        aura_sampling = patched_aura.objects["model_sampling"]
        self.assertEqual((1.73, 1.0), (aura_sampling.shift, aura_sampling.multiplier))
        self.assertEqual(0.8, aura_sampling.noise_scale)

        flux_node = classes["ModelSamplingFlux"]()
        patched_1024 = flux_node.patch(FakePatchModel(), 1.15, 0.5, 1024, 1024)[0]
        patched_256 = flux_node.patch(FakePatchModel(), 1.15, 0.5, 256, 256)[0]
        patched_large = flux_node.patch(FakePatchModel(), 1.15, 0.5, 1488, 1440)[0]
        self.assertAlmostEqual(1.15, patched_1024.objects["model_sampling"].shift, places=12)
        self.assertAlmostEqual(0.5, patched_256.objects["model_sampling"].shift, places=12)
        self.assertAlmostEqual(1.8734635416666663, patched_large.objects["model_sampling"].shift, places=12)
        self.assertFalse(hasattr(patched_1024.objects["model_sampling"], "noise_scale"))

        ltxv = extract_ltxv_patch_class()
        fallback = ltxv.execute(FakePatchModel(), 2.05, 0.95, None).args[0]
        anchor = ltxv.execute(
            FakePatchModel(),
            2.05,
            0.95,
            {"samples": torch.zeros((1, 4, 4, 16, 16))},
        ).args[0]
        extrapolated = ltxv.execute(
            FakePatchModel(),
            2.05,
            0.95,
            {"samples": torch.zeros((1, 4, 5, 32, 40))},
        ).args[0]
        self.assertAlmostEqual(2.05, fallback.objects["model_sampling"].shift, places=12)
        self.assertAlmostEqual(0.95, anchor.objects["model_sampling"].shift, places=12)
        self.assertAlmostEqual(2.875, extrapolated.objects["model_sampling"].shift, places=12)
        self.assertFalse(hasattr(fallback.objects["model_sampling"], "noise_scale"))

        math_ns = extract_underlying_sampling_math()
        time_snr_shift = math_ns["time_snr_shift"]
        flux_time_shift = math_ns["flux_time_shift"]
        self.assertAlmostEqual(0.75, float(time_snr_shift(3.0, torch.tensor(0.5))), places=7)
        self.assertAlmostEqual(0.5, flux_time_shift(0.0, 1.0, 0.5), places=12)
        self.assertAlmostEqual(
            math.exp(1.15) / (math.exp(1.15) + 1.0),
            flux_time_shift(1.15, 1.0, 0.5),
            places=12,
        )

        discrete_flow = math_ns["ModelSamplingDiscreteFlow"]()
        discrete_flow.set_parameters(shift=3.0, multiplier=1000)
        self.assertEqual(1000, len(discrete_flow.sigmas))
        self.assertEqual(1.0, float(discrete_flow.sigmas[-1]))
        self.assertEqual(500.0, float(discrete_flow.timestep(torch.tensor(0.5))))
        aura_flow = math_ns["ModelSamplingDiscreteFlow"]()
        aura_flow.set_parameters(shift=3.0, multiplier=1.0)
        torch.testing.assert_close(discrete_flow.sigmas, aura_flow.sigmas)
        self.assertEqual(0.5, float(aura_flow.timestep(torch.tensor(0.5))))
        zero_shift = math_ns["ModelSamplingDiscreteFlow"]()
        zero_shift.set_parameters(shift=0.0, multiplier=1000)
        self.assertTrue(bool(torch.all(zero_shift.sigmas[:-1] == 0)))
        self.assertTrue(bool(torch.isnan(zero_shift.sigmas[-1])))

        flux_sampling = math_ns["ModelSamplingFlux"]()
        self.assertEqual(10000, len(flux_sampling.sigmas))
        self.assertEqual(1.0, float(flux_sampling.sigmas[-1]))
        self.assertGreater(float(flux_sampling.sigmas[0]), 0.0)
        self.assertAlmostEqual(
            flux_time_shift(1.15, 1.0, 0.5),
            float(flux_sampling.sigma(torch.tensor(0.5))),
            places=7,
        )
        with self.assertRaises(OverflowError):
            flux_sampling.set_parameters(shift=1000.0)
        underflow_sampling = math_ns["ModelSamplingFlux"]()
        underflow_sampling.set_parameters(shift=-1000.0)
        self.assertEqual(0.0, float(underflow_sampling.sigmas[0]))
        self.assertTrue(bool(torch.isnan(underflow_sampling.sigmas[-1])))

        const = math_ns["CONST"]()
        noise = torch.full((1, 1, 1, 1), 2.0)
        latent = torch.zeros_like(noise)
        scaled = const.noise_scaling(torch.tensor(0.25), noise, latent)
        self.assertEqual([[[[0.5]]]], scaled.tolist())
        denoised = const.calculate_denoised(
            torch.tensor(0.25), torch.full_like(noise, 2.0), torch.full_like(noise, 3.0)
        )
        self.assertEqual([[[[2.5]]]], denoised.tolist())

    def test_pinned_source_registration_and_embedded_docs(self) -> None:
        advanced = (SOURCE / "comfy_extras" / "nodes_model_advanced.py").read_text(encoding="utf-8")
        lt = (SOURCE / "comfy_extras" / "nodes_lt.py").read_text(encoding="utf-8")
        model_sampling = (SOURCE / "comfy" / "model_sampling.py").read_text(encoding="utf-8")
        for class_type in ("ModelSamplingSD3", "ModelSamplingAuraFlow", "ModelSamplingFlux"):
            self.assertIn(f'class {class_type}', advanced)
            self.assertIn(f'"{class_type}": {class_type}', advanced)
        self.assertIn("class ModelSamplingLTXV(io.ComfyNode):", lt)
        self.assertIn("            ModelSamplingLTXV,", lt)
        self.assertIn("model_sampling.set_parameters(shift=shift, multiplier=multiplier)", advanced)
        self.assertIn('if hasattr(original, "noise_scale"):', advanced)
        self.assertIn("return self.patch(model, shift, multiplier=1.0)", advanced)
        self.assertIn("shift = (width * height / (8 * 8 * 2 * 2)) * mm + b", advanced)
        self.assertIn('tokens = math.prod(latent["samples"].shape[2:])', lt)
        self.assertIn("tokens = 4096", lt)
        self.assertIn("shift = (tokens) * mm + b", lt)
        self.assertIn("return alpha * t / (1 + (alpha - 1) * t)", model_sampling)
        self.assertIn("return math.exp(mu) / (math.exp(mu) + (1 / t - 1) ** sigma)", model_sampling)
        self.assertIn("return sigma * (s * noise) + (1.0 - sigma) * latent_image", model_sampling)

        self.assertEqual(DOCS_SHA256, hashlib.sha256(DOCS_WHEEL.read_bytes()).hexdigest())
        with zipfile.ZipFile(DOCS_WHEEL) as archive:
            names = set(archive.namelist())
            for (class_type, locale), expected_hash in DOC_HASHES.items():
                path = f"comfyui_embedded_docs/docs/{class_type}/{locale}.md"
                self.assertIn(path, names)
                self.assertEqual(expected_hash, hashlib.sha256(archive.read(path)).hexdigest())
            ltxv_docs = archive.read("comfyui_embedded_docs/docs/ModelSamplingLTXV/en.md").decode("utf-8")
            self.assertIn("default token count of 4096", ltxv_docs)
            flux_docs = archive.read("comfyui_embedded_docs/docs/ModelSamplingFlux/en.md").decode("utf-8")
            self.assertIn("based on image dimensions", flux_docs)

    def test_workflow_wheel_integrity_census_widgets_and_topologies(self) -> None:
        self.assertEqual(WORKFLOW_SHA256, hashlib.sha256(WORKFLOW_WHEEL.read_bytes()).hexdigest())
        records: list[dict[str, Any]] = []
        json_members = 0
        list_members = 0
        root_graphs = 0
        subgraphs = 0
        root_nodes = 0
        subgraph_nodes = 0
        payloads: dict[str, dict[str, Any]] = {}

        with zipfile.ZipFile(WORKFLOW_WHEEL) as archive:
            self.assertIsNone(archive.testzip())
            record_name = next(name for name in archive.namelist() if name.endswith(".dist-info/RECORD"))
            rows = list(csv.reader(io.StringIO(archive.read(record_name).decode("utf-8"))))
            self.assertEqual(517, len(rows))
            checked = 0
            for name, digest, size in rows:
                if not digest:
                    self.assertEqual(record_name, name)
                    continue
                algorithm, encoded = digest.split("=", 1)
                self.assertEqual("sha256", algorithm)
                expected = base64.urlsafe_b64decode(encoded + "=" * (-len(encoded) % 4))
                data = archive.read(name)
                self.assertEqual(expected, hashlib.sha256(data).digest())
                self.assertEqual(int(size), len(data))
                checked += 1
            self.assertEqual(516, checked)

            for member in archive.namelist():
                if not member.endswith(".json") or "/templates/" not in member:
                    continue
                json_members += 1
                payload = json.loads(archive.read(member))
                if isinstance(payload, list):
                    list_members += 1
                    continue
                if not isinstance(payload, dict) or not isinstance(payload.get("nodes"), list):
                    continue
                root_graphs += 1
                root_nodes += len(payload["nodes"])
                payloads[Path(member).name] = payload
                definitions = payload.get("definitions")
                nested = definitions.get("subgraphs", []) if isinstance(definitions, dict) else []
                subgraphs += len(nested)
                subgraph_nodes += sum(
                    len(subgraph.get("nodes", [])) for subgraph in nested if isinstance(subgraph, dict)
                )
                for record in graph_records(payload, member):
                    if record["node"].get("type") in TARGET_TYPES:
                        records.append(record)

        self.assertEqual((512, 13, 496, 272), (json_members, list_members, root_graphs, subgraphs))
        self.assertEqual((4083, 4037, 8120), (root_nodes, subgraph_nodes, root_nodes + subgraph_nodes))

        expected_counts = {
            "ModelSamplingSD3": (82, 46, 36, 50, 23, Counter({0: 71, 4: 11})),
            "ModelSamplingAuraFlow": (72, 15, 57, 56, 22, Counter({0: 70, 4: 2})),
            "ModelSamplingFlux": (4, 1, 3, 4, 3, Counter({0: 4})),
            "ModelSamplingLTXV": (0, 0, 0, 0, 0, Counter()),
        }
        for class_type, expected in expected_counts.items():
            matches = [record for record in records if record["node"]["type"] == class_type]
            actual = (
                len(matches),
                sum(record["scope"] == "root" for record in matches),
                sum(record["scope"] == "subgraph" for record in matches),
                len({record["member"] for record in matches}),
                len({record["workflowId"] for record in matches}),
                Counter(record["node"].get("mode", 0) for record in matches),
            )
            self.assertEqual(expected, actual, class_type)

        sd3_widgets = Counter(
            tuple(record["node"].get("widgets_values", []))
            for record in records
            if record["node"]["type"] == "ModelSamplingSD3"
        )
        self.assertEqual(
            Counter(
                {
                    (5,): 28,
                    (8,): 19,
                    (8.000000000000002,): 13,
                    (5.000000000000001,): 9,
                    (7,): 7,
                    (3,): 3,
                    (2,): 2,
                    (6.000000000000001,): 1,
                }
            ),
            sd3_widgets,
        )
        aura_widgets = Counter(
            tuple(record["node"].get("widgets_values", []))
            for record in records
            if record["node"]["type"] == "ModelSamplingAuraFlow"
        )
        self.assertEqual(
            Counter(
                {
                    (3,): 33,
                    (3.1,): 16,
                    (3.1000000000000005,): 9,
                    (1,): 6,
                    (1.0000000000000002,): 3,
                    (3.16,): 2,
                    (7,): 1,
                    (4,): 1,
                    (6,): 1,
                }
            ),
            aura_widgets,
        )
        flux_widgets = Counter(
            tuple(record["node"].get("widgets_values", []))
            for record in records
            if record["node"]["type"] == "ModelSamplingFlux"
        )
        self.assertEqual(
            Counter({(1.15, 0.5, 1024, 1024): 2, (1.15, 0.5, 1488, 1440): 2}),
            flux_widgets,
        )

        hunyuan = payloads["hunyuan_video_text_to_video.json"]
        self.assertEqual("b07dba9f-f409-47a6-84bb-a6639b2a70da", hunyuan["id"])
        by_id = {node["id"]: node for node in hunyuan["nodes"]}
        self.assertEqual(("ModelSamplingSD3", [7]), (by_id[67]["type"], by_id[67]["widgets_values"]))
        self.assertIn([209, 12, 0, 67, 0, "MODEL"], hunyuan["links"])
        self.assertIn([195, 67, 0, 22, 0, "MODEL"], hunyuan["links"])
        self.assertIn([190, 12, 0, 17, 0, "MODEL"], hunyuan["links"])
        self.assertEqual(["simple", 20, 1], by_id[17]["widgets_values"])

        chroma = payloads["image_chroma_text_to_image.json"]
        self.assertEqual("b2d37916-fab5-425f-850d-7a64886e4d54", chroma["id"])
        by_id = {node["id"]: node for node in chroma["nodes"]}
        self.assertEqual(("ModelSamplingAuraFlow", [1]), (by_id[701]["type"], by_id[701]["widgets_values"]))
        self.assertEqual([3.5], by_id[694]["widgets_values"])
        self.assertEqual(["beta", 26, 1], by_id[734]["widgets_values"])
        self.assertIn([1370, 701, 0, 694, 0, "MODEL"], chroma["links"])
        self.assertIn([1371, 701, 0, 734, 0, "MODEL"], chroma["links"])

        flux = payloads["flux_redux_model_example.json"]
        self.assertEqual("06010f12-03bc-41ce-86bd-14f321d5a152", flux["id"])
        by_id = {node["id"]: node for node in flux["nodes"]}
        self.assertEqual(
            ("ModelSamplingFlux", [1.15, 0.5, 1024, 1024]),
            (by_id[30]["type"], by_id[30]["widgets_values"]),
        )
        self.assertIn([54, 30, 0, 22, 0, "MODEL"], flux["links"])
        self.assertIn([55, 30, 0, 17, 0, "MODEL"], flux["links"])
        self.assertIn([114, 35, 0, 30, 2, "INT"], flux["links"])
        self.assertIn([115, 34, 0, 30, 1, "INT"], flux["links"])
        self.assertEqual([1024, "fixed"], by_id[34]["widgets_values"])
        self.assertEqual([1024, "fixed"], by_id[35]["widgets_values"])
        self.assertEqual(["simple", 20, 1], by_id[17]["widgets_values"])


if __name__ == "__main__":
    unittest.main()
