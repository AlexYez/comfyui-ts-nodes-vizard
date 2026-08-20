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
    "core.sampler-euler-ancestral-cfgpp": {
        "directory": "sampler-euler-ancestral-cfgpp",
        "classType": "SamplerEulerAncestralCFGPP",
        "category": "model/sampling/samplers",
        "outputs": ["SAMPLER"],
        "outputNames": ["SAMPLER"],
        "fingerprint": "sha256:0d30a28ea0e7511338e9513c91229ce2231abb0bff1bacb50e6bcd23b18a9106",
        "recipe": "recipe.euler-ancestral-cfgpp-custom-sampling",
    },
    "core.sampler-lms": {
        "directory": "sampler-lms",
        "classType": "SamplerLMS",
        "category": "model/sampling/samplers",
        "outputs": ["SAMPLER"],
        "outputNames": ["SAMPLER"],
        "fingerprint": "sha256:44295909a84dc4cde3e40622ae64e8fa0ee17a51f6f1807887a8141e4b019723",
        "recipe": "recipe.lms-custom-sampling",
    },
    "core.extend-intermediate-sigmas": {
        "directory": "extend-intermediate-sigmas",
        "classType": "ExtendIntermediateSigmas",
        "category": "model/sampling/sigmas",
        "outputs": ["SIGMAS"],
        "outputNames": ["SIGMAS"],
        "fingerprint": "sha256:f226c3915144d78011f73d2d3698430b426eb6cc82557fe213b395bd928aa019",
        "recipe": "recipe.extend-intermediate-sigmas",
    },
    "core.sampling-percent-to-sigma": {
        "directory": "sampling-percent-to-sigma",
        "classType": "SamplingPercentToSigma",
        "category": "model/sampling/sigmas",
        "outputs": ["FLOAT"],
        "outputNames": ["sigma_value"],
        "fingerprint": "sha256:c402c3898e82e2e8f5f3972052ee828e5514d641308cb50f1a386022b0745cda",
        "recipe": "recipe.sampling-percent-to-sigma",
    },
}

RECIPE_DIRECTORIES = {
    "recipe.euler-ancestral-cfgpp-custom-sampling": "euler-ancestral-cfgpp-custom-sampling",
    "recipe.lms-custom-sampling": "lms-custom-sampling",
    "recipe.extend-intermediate-sigmas": "extend-intermediate-sigmas",
    "recipe.sampling-percent-to-sigma": "sampling-percent-to-sigma",
}

EXPECTED_FRAGMENT_NODES = {
    "recipe.euler-ancestral-cfgpp-custom-sampling": [
        ("SamplerEulerAncestralCFGPP", {"eta": 1.0, "s_noise": 1.0}),
        ("SamplerCustomAdvanced", {}),
    ],
    "recipe.lms-custom-sampling": [
        ("SamplerLMS", {"order": 4}),
        ("SamplerCustomAdvanced", {}),
    ],
    "recipe.extend-intermediate-sigmas": [
        (
            "ExtendIntermediateSigmas",
            {"steps": 2, "start_at_sigma": -1.0, "end_at_sigma": 12.0, "spacing": "linear"},
        ),
        ("SamplerCustomAdvanced", {}),
    ],
    "recipe.sampling-percent-to-sigma": [
        ("SamplingPercentToSigma", {"sampling_percent": 0.25, "return_actual_sigma": False}),
        ("SetFirstSigma", {}),
        ("SamplerCustomAdvanced", {}),
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
    ("SamplerEulerAncestralCFGPP", "en"): "1dfe2c256b7b9f0803872fdaee2f4d030feb863c7c6744d624e816a130ffd323",
    ("SamplerEulerAncestralCFGPP", "ru"): "8603b4535f14f3e5de3e537c4daf4e8e5abaeda157a2e7e1dc6d7ab4643fa78a",
    ("SamplerLMS", "en"): "230d1c167f0fefc14fe9fd15e5b4707fae995dee9f59839e611e94b403c4627e",
    ("SamplerLMS", "ru"): "f2ccdb8c69ba8e6742a9613a032858ddc9cff2152caf1477ab96a4968c694cf4",
    ("ExtendIntermediateSigmas", "en"): "67a8be7e38a7bfdac3eed3d221089b9f85b044609c895cd7ab8bd9459a8cd5fe",
    ("ExtendIntermediateSigmas", "ru"): "1b60b1f001c91de2ea505f579065e64d440364f0b94139bfed579224bef56cab",
    ("SamplingPercentToSigma", "en"): "ff3e7990f514ae5a0db569e5734bd74e1b818996a1834476251afc8b71a3b320",
    ("SamplingPercentToSigma", "ru"): "4f3b967fc5f338da8d3d428e2c93ced83474a1b91df6e722017a6a292b8a36f9",
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


def extract_node_classes(*names: str) -> tuple[dict[str, type], list[tuple[str, dict[str, Any]]]]:
    path = SOURCE / "comfy_extras" / "nodes_custom_sampler.py"
    tree = ast.parse(path.read_text(encoding="utf-8"))
    classes = [
        node for node in tree.body if isinstance(node, ast.ClassDef) and node.name in set(names)
    ]

    class ComfyNode:
        pass

    class NodeOutput:
        def __init__(self, *args: Any) -> None:
            self.args = args

    calls: list[tuple[str, dict[str, Any]]] = []

    def ksampler(name: str, options: dict[str, Any]) -> dict[str, Any]:
        calls.append((name, options.copy()))
        return {"name": name, "options": options.copy()}

    namespace: dict[str, Any] = {
        "io": SimpleNamespace(ComfyNode=ComfyNode, NodeOutput=NodeOutput),
        "torch": torch,
        "math": math,
        "comfy": SimpleNamespace(samplers=SimpleNamespace(ksampler=ksampler)),
    }
    exec(compile(ast.Module(body=classes, type_ignores=[]), str(path), "exec"), namespace)
    return {name: namespace[name] for name in names}, calls


def extract_ancestral_step() -> Any:
    path = SOURCE / "comfy" / "k_diffusion" / "sampling.py"
    tree = ast.parse(path.read_text(encoding="utf-8"))
    node = next(
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name == "get_ancestral_step"
    )
    namespace: dict[str, Any] = {}
    exec(compile(ast.Module(body=[node], type_ignores=[]), str(path), "exec"), namespace)
    return namespace["get_ancestral_step"]


def extract_sample_lms_terminal_branch() -> tuple[Any, list[tuple[int, Any]]]:
    path = SOURCE / "comfy" / "k_diffusion" / "sampling.py"
    tree = ast.parse(path.read_text(encoding="utf-8"))
    node = next(
        node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == "sample_lms"
    )
    coefficient_calls: list[tuple[int, Any]] = []

    def coefficient(order: int, sigmas: Any, index: int, history: int) -> float:
        coefficient_calls.append((order, (sigmas, index, history)))
        raise AssertionError("terminal LMS branch must not request quadrature coefficients")

    namespace: dict[str, Any] = {
        "torch": torch,
        "trange": lambda length, disable=None: range(length),
        "to_d": lambda x, sigma, denoised: x - denoised,
        "linear_multistep_coeff": coefficient,
    }
    exec(compile(ast.Module(body=[node], type_ignores=[]), str(path), "exec"), namespace)
    return namespace["sample_lms"], coefficient_calls


class SamplerSigmaUtilityContentTests(unittest.TestCase):
    def test_articles_recipes_ledgers_and_russian_contract(self) -> None:
        article_schema = catalog.load_json(catalog.CONTENT / "schemas" / "article.schema.v1.json")
        recipe_schema = catalog.load_json(catalog.CONTENT / "schemas" / "recipe.schema.v1.json")
        fragment_schema = catalog.load_json(catalog.CONTENT / "schemas" / "recipe-fragment.schema.v1.json")
        research_schema = catalog.load_json(catalog.CONTENT / "schemas" / "article-research.schema.v1.json")
        article_ids = all_article_ids()
        article_errors: list[str] = []

        for article_id, spec in ARTICLE_SPECS.items():
            path = article_path(spec)
            article = catalog.load_json(path)
            self.assertEqual([], catalog.json_schema_errors(article, article_schema))
            catalog.validate_article(path, article, article_errors)
            self.assertEqual(article_id, article["articleId"])
            self.assertEqual("draft", article["status"])
            self.assertEqual("in_review", article["editorial"]["state"])
            self.assertEqual(spec["fingerprint"], article["editorial"]["schemaHash"])
            self.assertFalse(article["experimental"])
            self.assertIn(spec["recipe"], [asset["id"] for asset in article["assets"]])

            relations = article["relations"]
            targets = list(relations["related"]) + list(relations["alternatives"])
            if relations["replacedBy"] is not None:
                targets.append(relations["replacedBy"])
            self.assertTrue(set(targets).issubset(article_ids), (article_id, set(targets) - article_ids))

            body = (path.parent / article["body"]).read_text(encoding="utf-8")
            semantic_h2 = [
                heading
                for heading in re.findall(r"^## (.+)$", body, flags=re.MULTILINE)
                if heading != "Источники"
            ]
            self.assertEqual(10, len(semantic_h2), article_id)
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

            ledger_path = catalog.CONTENT / "research" / "reviews" / f"{article_id}.json"
            ledger = catalog.load_json(ledger_path)
            self.assertEqual([], catalog.json_schema_errors(ledger, research_schema))
            self.assertEqual("fact_checked", ledger["state"])
            self.assertEqual("automated_assisted", ledger["reviewMode"])
            self.assertFalse(ledger["checks"]["exampleExecuted"])
            self.assertTrue(ledger["checks"]["factsRecheckedAfterEditing"])
            self.assertTrue(ledger["knownGaps"])
            self.assertTrue(
                any("Редактор пока не проверил материал вручную." in gap for gap in ledger["knownGaps"])
            )
            self.assertNotIn("approved", json.dumps(ledger, ensure_ascii=False).lower())

        self.assertEqual([], article_errors)

        recipe_errors: list[str] = []
        inventory = catalog.load_json(INVENTORY)
        for recipe_id, directory in RECIPE_DIRECTORIES.items():
            path = catalog.CONTENT / "recipes" / directory / "recipe.json"
            recipe = catalog.load_json(path)
            self.assertEqual([], catalog.json_schema_errors(recipe, recipe_schema))
            catalog.validate_recipe(path, recipe, article_ids, recipe_errors)
            self.assertEqual(recipe_id, recipe["recipeId"])
            self.assertEqual("draft", recipe["editorial"]["state"])
            self.assertNotIn("workflow", recipe)
            recipe_body = (path.parent / recipe["body"]).read_text(encoding="utf-8")
            self.assertIn("Редактор пока не проверил материал вручную.", recipe_body)

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
            self.assertEqual("comfy_extras.nodes_custom_sampler", definition["python_module"])
            self.assertEqual(spec["category"], definition["category"])
            self.assertEqual(spec["outputs"], definition["output"])
            self.assertEqual(spec["outputNames"], definition["output_name"])
            for flag in ("deprecated", "experimental", "dev_only", "api_node", "output_node"):
                self.assertFalse(definition.get(flag, False), (spec["classType"], flag))
            self.assertEqual(spec["fingerprint"], catalog.schema_fingerprint(spec["classType"], definition))

        euler = inventory["SamplerEulerAncestralCFGPP"]
        self.assertEqual(["eta", "s_noise"], euler["input_order"]["required"])
        self.assertEqual("SamplerEulerAncestralCFG++", euler["display_name"])
        self.assertEqual(
            {"default": 1.0, "min": 0.0, "max": 1.0, "step": 0.01, "round": False},
            euler["input"]["required"]["eta"][1],
        )
        self.assertEqual(
            {"default": 1.0, "min": 0.0, "max": 10.0, "step": 0.01, "round": False},
            euler["input"]["required"]["s_noise"][1],
        )

        lms = inventory["SamplerLMS"]
        self.assertEqual(["order"], lms["input_order"]["required"])
        self.assertEqual(
            {"advanced": True, "default": 4, "min": 1, "max": 100},
            lms["input"]["required"]["order"][1],
        )

        extend = inventory["ExtendIntermediateSigmas"]
        self.assertEqual(
            ["sigmas", "steps", "start_at_sigma", "end_at_sigma", "spacing"],
            extend["input_order"]["required"],
        )
        self.assertEqual(["interpolate sigmas"], extend["search_aliases"])
        self.assertEqual(
            ["linear", "cosine", "sine"],
            extend["input"]["required"]["spacing"][1]["options"],
        )
        self.assertNotIn("default", extend["input"]["required"]["spacing"][1])

        percent = inventory["SamplingPercentToSigma"]
        self.assertEqual(
            ["model", "sampling_percent", "return_actual_sigma"],
            percent["input_order"]["required"],
        )
        self.assertEqual(
            {"default": 0.0, "min": 0.0, "max": 1.0, "step": 0.0001},
            percent["input"]["required"]["sampling_percent"][1],
        )
        endpoint = percent["input"]["required"]["return_actual_sigma"][1]
        self.assertFalse(endpoint["default"])
        self.assertIn("only affects results at 0.0 and 1.0", endpoint["tooltip"])

        replacements = catalog.load_json(REPLACEMENTS)
        serialized = json.dumps(replacements, ensure_ascii=False)
        for class_type in TARGET_TYPES:
            self.assertNotIn(class_type, replacements)
            self.assertNotIn(f'"new_node_id": "{class_type}"', serialized)

    def test_exact_source_probes_without_models(self) -> None:
        classes, sampler_calls = extract_node_classes(
            "SamplerEulerAncestralCFGPP",
            "SamplerLMS",
            "ExtendIntermediateSigmas",
            "SamplingPercentToSigma",
            "SetFirstSigma",
        )

        euler = classes["SamplerEulerAncestralCFGPP"].execute(0.7, 1.25).args[0]
        lms = classes["SamplerLMS"].execute(7).args[0]
        self.assertEqual(
            [
                ("euler_ancestral_cfg_pp", {"eta": 0.7, "s_noise": 1.25}),
                ("lms", {"order": 7}),
            ],
            sampler_calls,
        )
        self.assertEqual("euler_ancestral_cfg_pp", euler["name"])
        self.assertEqual("lms", lms["name"])

        ancestral_step = extract_ancestral_step()
        self.assertEqual((0.5, 0.0), ancestral_step(1.0, 0.5, eta=0.0))
        sigma_down, sigma_up = ancestral_step(1.0, 0.5, eta=1.0)
        self.assertAlmostEqual(0.25, sigma_down, places=12)
        self.assertAlmostEqual(math.sqrt(3) / 4, sigma_up, places=12)

        sample_lms, coefficient_calls = extract_sample_lms_terminal_branch()
        model_calls: list[tuple[torch.Tensor, torch.Tensor]] = []

        def terminal_model(x: torch.Tensor, sigma: torch.Tensor, **_extra: Any) -> torch.Tensor:
            model_calls.append((x.clone(), sigma.clone()))
            return torch.full_like(x, 2.0)

        terminal = sample_lms(
            terminal_model,
            torch.ones(1),
            torch.tensor([1.0, 0.0]),
            disable=True,
            order=7,
        )
        self.assertEqual([2.0], terminal.tolist())
        self.assertEqual(1, len(model_calls))
        self.assertEqual([1.0], model_calls[0][1].tolist())
        self.assertEqual([], coefficient_calls)

        extend = classes["ExtendIntermediateSigmas"]
        source = torch.tensor([20.0, 10.0, 0.0], dtype=torch.float64)
        linear = extend.execute(source, 3, -1.0, 12.0, "linear").args[0]
        torch.testing.assert_close(
            linear,
            torch.tensor([20.0, 16.666666, 13.333334, 10.0, 0.0]),
            rtol=1e-5,
            atol=1e-5,
        )
        cosine = extend.execute(source, 3, -1.0, 12.0, "cosine").args[0]
        torch.testing.assert_close(
            cosine,
            torch.tensor([20.0, 15.0, 11.339746, 10.0, 0.0]),
            rtol=1e-5,
            atol=1e-5,
        )
        sine = extend.execute(source, 3, -1.0, 12.0, "sine").args[0]
        torch.testing.assert_close(
            sine,
            torch.tensor([20.0, 18.660254, 15.0, 10.0, 0.0]),
            rtol=1e-5,
            atol=1e-5,
        )
        bounded = extend.execute(source, 3, 15.0, 5.0, "linear").args[0]
        torch.testing.assert_close(
            bounded,
            torch.tensor([20.0, 10.0, 6.666667, 3.333334, 0.0]),
            rtol=1e-5,
            atol=1e-5,
        )
        unchanged = extend.execute(source, 1, -1.0, 0.0, "linear").args[0]
        torch.testing.assert_close(unchanged, source.float())
        self.assertEqual(torch.float32, unchanged.dtype)
        self.assertEqual("cpu", unchanged.device.type)
        empty = extend.execute(torch.empty(0, dtype=torch.float64), 2, -1.0, 12.0, "linear").args[0]
        self.assertEqual([], empty.tolist())
        self.assertEqual(torch.float32, empty.dtype)

        class FakeSampling:
            def __init__(self) -> None:
                self.sigma_max = torch.tensor(14.5)
                self.sigma_min = torch.tensor(0.03)
                self.calls: list[float] = []

            def percent_to_sigma(self, value: float) -> float:
                self.calls.append(value)
                return {0.0: 999999999.9, 0.25: 3.25, 1.0: 0.0}[value]

        sampling = FakeSampling()

        class FakeModel:
            def get_model_object(self, key: str) -> FakeSampling:
                self.key = key
                return sampling

        model = FakeModel()
        convert = classes["SamplingPercentToSigma"]
        self.assertEqual(999999999.9, convert.execute(model, 0.0, False).args[0])
        self.assertEqual(14.5, convert.execute(model, 0.0, True).args[0])
        self.assertEqual(3.25, convert.execute(model, 0.25, False).args[0])
        self.assertEqual(3.25, convert.execute(model, 0.25, True).args[0])
        self.assertEqual(0.0, convert.execute(model, 1.0, False).args[0])
        self.assertAlmostEqual(0.03, convert.execute(model, 1.0, True).args[0], places=6)
        self.assertEqual("model_sampling", model.key)
        self.assertEqual([0.0, 0.0, 0.25, 0.25, 1.0, 1.0], sampling.calls)

        schedule = torch.tensor([9.0, 5.0, 0.0])
        replaced = classes["SetFirstSigma"].execute(schedule, 3.25).args[0]
        self.assertEqual([3.25, 5.0, 0.0], replaced.tolist())
        self.assertEqual([9.0, 5.0, 0.0], schedule.tolist())

    def test_pinned_source_registration_algorithms_and_embedded_docs(self) -> None:
        custom = (SOURCE / "comfy_extras" / "nodes_custom_sampler.py").read_text(encoding="utf-8")
        sampling = (SOURCE / "comfy" / "k_diffusion" / "sampling.py").read_text(encoding="utf-8")
        model_sampling = (SOURCE / "comfy" / "model_sampling.py").read_text(encoding="utf-8")
        for class_type in TARGET_TYPES:
            self.assertIn(f"class {class_type}(io.ComfyNode):", custom)
            self.assertIn(f"            {class_type},", custom)
        self.assertIn('"euler_ancestral_cfg_pp",\n            {"eta": eta, "s_noise": s_noise}', custom)
        self.assertIn('comfy.samplers.ksampler("lms", {"order": order})', custom)
        self.assertIn('x = torch.linspace(0, 1, steps + 1, device=sigmas.device)[1:-1]', custom)
        self.assertIn('if end_at_sigma <= sigma_current <= start_at_sigma:', custom)
        self.assertIn('extended_sigmas = torch.FloatTensor(extended_sigmas)', custom)
        self.assertIn('sigma_val = model_sampling.percent_to_sigma(sampling_percent)', custom)
        self.assertIn('if sampling_percent == 0.0:', custom)
        self.assertIn('elif sampling_percent == 1.0:', custom)

        self.assertIn('disable_cfg1_optimization=True', sampling)
        self.assertIn('s_noise = s_noise * getattr(model_sampling, "noise_scale", 1.0)', sampling)
        self.assertIn('d = to_d(x, sigmas[i], alpha_s * uncond_denoised)', sampling)
        self.assertIn('if eta > 0 and s_noise > 0:', sampling)
        self.assertIn('ds.append(d)', sampling)
        self.assertIn('cur_order = min(i + 1, order)', sampling)
        self.assertIn('linear_multistep_coeff(cur_order, sigmas_cpu, i, j)', sampling)
        self.assertGreaterEqual(sampling.count('if sigmas[i + 1] == 0:'), 2)

        self.assertGreaterEqual(model_sampling.count('return 999999999.9'), 3)
        self.assertIn('return time_snr_shift(self.shift, 1.0 - percent)', model_sampling)
        self.assertIn('return flux_time_shift(self.shift, 1.0, 1.0 - percent)', model_sampling)

        self.assertEqual(DOCS_SHA256, hashlib.sha256(DOCS_WHEEL.read_bytes()).hexdigest())
        with zipfile.ZipFile(DOCS_WHEEL) as archive:
            names = set(archive.namelist())
            for (class_type, locale), expected_hash in DOC_HASHES.items():
                path = f"comfyui_embedded_docs/docs/{class_type}/{locale}.md"
                self.assertIn(path, names)
                self.assertEqual(expected_hash, hashlib.sha256(archive.read(path)).hexdigest())
            lms_docs = archive.read("comfyui_embedded_docs/docs/SamplerLMS/en.md").decode("utf-8")
            self.assertIn("Least Mean Squares", lms_docs)
            extend_docs = archive.read("comfyui_embedded_docs/docs/ExtendIntermediateSigmas/en.md").decode("utf-8")
            self.assertIn("Number of intermediate steps", extend_docs)

    def test_workflow_wheel_integrity_zero_census_and_adjacent_topology(self) -> None:
        self.assertEqual(WORKFLOW_SHA256, hashlib.sha256(WORKFLOW_WHEEL.read_bytes()).hexdigest())
        records: list[dict[str, Any]] = []
        all_nodes: list[dict[str, Any]] = []
        root_graphs = 0
        subgraphs = 0
        root_nodes = 0
        subgraph_nodes = 0
        json_members = 0
        target_payload: dict[str, Any] | None = None

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
                if not isinstance(payload, dict) or not isinstance(payload.get("nodes"), list):
                    continue
                root_graphs += 1
                root_nodes += len(payload["nodes"])
                if Path(member).name == "template_image_speech_to_video.json":
                    target_payload = payload
                definitions = payload.get("definitions")
                nested = definitions.get("subgraphs", []) if isinstance(definitions, dict) else []
                subgraphs += len(nested)
                subgraph_nodes += sum(
                    len(subgraph.get("nodes", [])) for subgraph in nested if isinstance(subgraph, dict)
                )
                for record in graph_records(payload, member):
                    all_nodes.append(record["node"])
                    if record["node"].get("type") in TARGET_TYPES:
                        records.append(record)

        self.assertEqual((512, 496, 272), (json_members, root_graphs, subgraphs))
        self.assertEqual((4083, 4037, 8120), (root_nodes, subgraph_nodes, root_nodes + subgraph_nodes))
        self.assertEqual([], records)
        for class_type in TARGET_TYPES:
            self.assertEqual(0, sum(node.get("type") == class_type for node in all_nodes), class_type)

        sampler_choices = Counter(
            node.get("widgets_values", [None])[0]
            for node in all_nodes
            if node.get("type") == "KSamplerSelect" and node.get("widgets_values")
        )
        self.assertEqual(97, sum(sampler_choices.values()))
        self.assertEqual(1, sampler_choices["euler_ancestral_cfg_pp"])
        self.assertEqual(0, sampler_choices["lms"])

        self.assertIsNotNone(target_payload)
        assert target_payload is not None
        self.assertEqual("dffbe35f-f46a-4e69-8de9-e6e510257dfd", target_payload["id"])
        subgraph = next(
            item
            for item in target_payload["definitions"]["subgraphs"]
            if item["id"] == "98fb87e2-23b5-4ecb-aacc-365912414a12"
        )
        by_id = {node["id"]: node for node in subgraph["nodes"]}
        self.assertEqual("KSamplerSelect", by_id[298]["type"])
        self.assertEqual(["euler_ancestral_cfg_pp"], by_id[298]["widgets_values"])
        self.assertEqual("SamplerCustomAdvanced", by_id[291]["type"])
        link = next(item for item in subgraph["links"] if item["id"] == 652)
        self.assertEqual(
            {"id": 652, "origin_id": 298, "origin_slot": 0, "target_id": 291, "target_slot": 2, "type": "SAMPLER"},
            link,
        )


if __name__ == "__main__":
    unittest.main()
