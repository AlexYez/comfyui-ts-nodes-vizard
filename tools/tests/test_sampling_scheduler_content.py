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
    "core.basic-scheduler": {
        "directory": "basic-scheduler",
        "classType": "BasicScheduler",
        "fingerprint": "sha256:88acf55a1ad2bb3b9b026e229d682802d497b1aa86c2056469d1121d0b7ea74b",
        "recipe": "recipe.basic-scheduler-custom-sampling",
    },
    "core.karras-scheduler": {
        "directory": "karras-scheduler",
        "classType": "KarrasScheduler",
        "fingerprint": "sha256:89cf58b3f938a9d01c17acc6504ae2ed07a4efd6f26ed7f3d7ef545db74b1379",
        "recipe": "recipe.karras-sigmas-to-custom-sampler",
    },
    "core.exponential-scheduler": {
        "directory": "exponential-scheduler",
        "classType": "ExponentialScheduler",
        "fingerprint": "sha256:eafdebde2e05bde824770e22f00715c459b8d755f4cf1ab760b6a1835de69051",
        "recipe": "recipe.exponential-sigmas-to-custom-sampler",
    },
    "core.polyexponential-scheduler": {
        "directory": "polyexponential-scheduler",
        "classType": "PolyexponentialScheduler",
        "fingerprint": "sha256:3b8c84eb1395ad641b2b26051bd63004eb2b31e1be8dc5907d17b4d0aab1fcd9",
        "recipe": "recipe.polyexponential-sigmas-to-custom-sampler",
    },
}

RECIPE_DIRECTORIES = {
    "recipe.basic-scheduler-custom-sampling": "basic-scheduler-custom-sampling",
    "recipe.karras-sigmas-to-custom-sampler": "karras-sigmas-to-custom-sampler",
    "recipe.exponential-sigmas-to-custom-sampler": "exponential-sigmas-to-custom-sampler",
    "recipe.polyexponential-sigmas-to-custom-sampler": "polyexponential-sigmas-to-custom-sampler",
}

EXPECTED_SCHEDULE_SETTINGS = {
    "recipe.basic-scheduler-custom-sampling": {"scheduler": "simple", "steps": 20, "denoise": 1.0},
    "recipe.karras-sigmas-to-custom-sampler": {
        "steps": 20,
        "sigma_max": 14.614642,
        "sigma_min": 0.0291675,
        "rho": 7.0,
    },
    "recipe.exponential-sigmas-to-custom-sampler": {
        "steps": 20,
        "sigma_max": 14.614642,
        "sigma_min": 0.0291675,
    },
    "recipe.polyexponential-sigmas-to-custom-sampler": {
        "steps": 20,
        "sigma_max": 14.614642,
        "sigma_min": 0.0291675,
        "rho": 1.0,
    },
}

SOURCE = catalog.ROOT / ".comfyui-source-0.32.0"
INVENTORY = catalog.CONTENT / "runtime" / "comfyui-0.32.0.object-info.json"
REPLACEMENTS = catalog.CONTENT / "runtime" / "comfyui-0.32.0.node-replacements.json"
WORKFLOW_WHEEL = catalog.ROOT / ".upstream-cache" / "comfyui_workflow_templates_json-0.1.42-py3-none-any.whl"
WORKFLOW_SHA256 = "242982d65e1c51ca03d892bc1009bb6843f457e7dfc0c20afe6438770b7a14a3"
DOCS_WHEEL = catalog.ROOT / ".upstream-cache" / "comfyui_embedded_docs-0.5.9-py3-none-any.whl"
DOCS_SHA256 = "30afae432a71c96aa59421d0f37388c66ff6572b8cbeee8ff045e4d5f84f896c"
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


def extract_sigma_functions() -> dict[str, Any]:
    path = SOURCE / "comfy" / "k_diffusion" / "sampling.py"
    tree = ast.parse(path.read_text(encoding="utf-8"))
    wanted = {
        "append_zero",
        "get_sigmas_karras",
        "get_sigmas_exponential",
        "get_sigmas_polyexponential",
    }
    body = [node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name in wanted]
    namespace: dict[str, Any] = {"math": math, "torch": torch}
    exec(compile(ast.Module(body=body, type_ignores=[]), str(path), "exec"), namespace)
    return namespace


def extract_basic_scheduler(calculate_sigmas: Any) -> type:
    path = SOURCE / "comfy_extras" / "nodes_custom_sampler.py"
    tree = ast.parse(path.read_text(encoding="utf-8"))
    class_node = next(node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == "BasicScheduler")

    class ComfyNode:
        pass

    class NodeOutput:
        def __init__(self, *args: Any) -> None:
            self.args = args

    namespace: dict[str, Any] = {
        "io": SimpleNamespace(ComfyNode=ComfyNode, NodeOutput=NodeOutput),
        "comfy": SimpleNamespace(
            samplers=SimpleNamespace(calculate_sigmas=calculate_sigmas, SCHEDULER_NAMES=[])
        ),
        "torch": torch,
    }
    exec(compile(ast.Module(body=[class_node], type_ignores=[]), str(path), "exec"), namespace)
    return namespace["BasicScheduler"]


class SamplingSchedulerContentTests(unittest.TestCase):
    def test_articles_recipes_ledgers_and_russian_contract(self) -> None:
        article_schema = catalog.load_json(catalog.CONTENT / "schemas" / "article.schema.v1.json")
        recipe_schema = catalog.load_json(catalog.CONTENT / "schemas" / "recipe.schema.v1.json")
        fragment_schema = catalog.load_json(catalog.CONTENT / "schemas" / "recipe-fragment.schema.v1.json")
        research_schema = catalog.load_json(catalog.CONTENT / "schemas" / "article-research.schema.v1.json")
        article_ids = all_article_ids()
        errors: list[str] = []

        for article_id, spec in ARTICLE_SPECS.items():
            path = article_path(spec)
            article = catalog.load_json(path)
            self.assertEqual([], catalog.json_schema_errors(article, article_schema))
            catalog.validate_article(path, article, errors)
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
            semantic_h2 = [heading for heading in re.findall(r"^## (.+)$", body, flags=re.MULTILINE) if heading != "Источники"]
            self.assertEqual(10, len(semantic_h2), article_id)
            self.assertNotIn("\ufffd", body)
            self.assertIn("Редактор пока не проверил материал вручную", body)
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

            ledger = catalog.load_json(catalog.CONTENT / "research" / "reviews" / f"{article_id}.json")
            self.assertEqual([], catalog.json_schema_errors(ledger, research_schema))
            self.assertEqual("fact_checked", ledger["state"])
            self.assertEqual("automated_assisted", ledger["reviewMode"])
            self.assertFalse(ledger["checks"]["exampleExecuted"])
            self.assertTrue(ledger["checks"]["factsRecheckedAfterEditing"])
            self.assertTrue(ledger["knownGaps"])

        self.assertEqual([], errors)

        recipe_errors: list[str] = []
        for recipe_id, directory in RECIPE_DIRECTORIES.items():
            path = catalog.CONTENT / "recipes" / directory / "recipe.json"
            recipe = catalog.load_json(path)
            self.assertEqual([], catalog.json_schema_errors(recipe, recipe_schema))
            catalog.validate_recipe(path, recipe, article_ids, recipe_errors)
            self.assertEqual(recipe_id, recipe["recipeId"])
            self.assertEqual("draft", recipe["editorial"]["state"])
            self.assertNotIn("workflow", recipe)

            fragment_path = path.parent / recipe["fragment"]["path"]
            fragment = catalog.load_json(fragment_path)
            self.assertEqual([], catalog.json_schema_errors(fragment, fragment_schema))
            catalog.validate_fragment(fragment_path, fragment, recipe_errors)
            self.assertEqual(EXPECTED_SCHEDULE_SETTINGS[recipe_id], fragment["nodes"][0]["settings"])
            self.assertEqual("SamplerCustomAdvanced", fragment["nodes"][1]["classType"])
            self.assertEqual(
                [{"from": "schedule", "output": "SIGMAS", "to": "sample", "input": "sigmas"}],
                fragment["connections"],
            )
            refs = {node["ref"] for node in fragment["nodes"]}
            self.assertTrue(all(item["to"] in refs for item in fragment["externalInputs"]))

        self.assertEqual([], recipe_errors)

    def test_runtime_contracts_fingerprints_flags_and_replacements(self) -> None:
        inventory = catalog.load_json(INVENTORY)
        for spec in ARTICLE_SPECS.values():
            definition = inventory[spec["classType"]]
            self.assertEqual("comfy_extras.nodes_custom_sampler", definition["python_module"])
            self.assertEqual("model/sampling/schedulers", definition["category"])
            self.assertFalse(definition.get("deprecated", False))
            self.assertFalse(definition.get("experimental", False))
            self.assertFalse(definition.get("api_node", False))
            self.assertEqual(["SIGMAS"], definition["output"])
            self.assertEqual(spec["fingerprint"], catalog.schema_fingerprint(spec["classType"], definition))

        basic = inventory["BasicScheduler"]
        self.assertEqual(["model", "scheduler", "steps", "denoise"], basic["input_order"]["required"])
        self.assertEqual("COMBO", basic["input"]["required"]["scheduler"][0])
        self.assertEqual(
            ["simple", "sgm_uniform", "karras", "exponential", "ddim_uniform", "beta", "normal", "linear_quadratic", "kl_optimal"],
            basic["input"]["required"]["scheduler"][1]["options"],
        )
        self.assertEqual(
            {"default": 20, "min": 1, "max": 10000},
            basic["input"]["required"]["steps"][1],
        )
        self.assertEqual(
            {"default": 1.0, "min": 0.0, "max": 1.0, "step": 0.01},
            basic["input"]["required"]["denoise"][1],
        )

        for class_type in ("KarrasScheduler", "ExponentialScheduler", "PolyexponentialScheduler"):
            required = inventory[class_type]["input"]["required"]
            self.assertEqual((20, 1, 10000), tuple(required["steps"][1][key] for key in ("default", "min", "max")))
            for key in ("sigma_max", "sigma_min"):
                self.assertEqual((0.0, 5000.0, 0.01, False, True), tuple(required[key][1][name] for name in ("min", "max", "step", "round", "advanced")))
            self.assertNotIn("model", required)
            self.assertNotIn("denoise", required)
        self.assertEqual(7.0, inventory["KarrasScheduler"]["input"]["required"]["rho"][1]["default"])
        self.assertEqual(1.0, inventory["PolyexponentialScheduler"]["input"]["required"]["rho"][1]["default"])

        replacements = catalog.load_json(REPLACEMENTS)
        serialized = json.dumps(replacements, ensure_ascii=False)
        for class_type in TARGET_TYPES:
            self.assertNotIn(class_type, replacements)
            self.assertNotIn(f'"new_node_id": "{class_type}"', serialized)

    def test_exact_source_scheduler_probe_without_models(self) -> None:
        functions = extract_sigma_functions()
        karras = functions["get_sigmas_karras"]
        exponential = functions["get_sigmas_exponential"]
        polyexponential = functions["get_sigmas_polyexponential"]

        actual_karras = karras(4, 0.0291675, 14.614642, 7.0)
        torch.testing.assert_close(
            actual_karras,
            torch.tensor([14.6146430969, 3.1686093807, 0.4469206631, 0.0291674994, 0.0]),
        )
        actual_exponential = exponential(4, 0.0291675, 14.614642)
        torch.testing.assert_close(
            actual_exponential,
            torch.tensor([14.6146430969, 1.8400310278, 0.2316659987, 0.0291675013, 0.0]),
        )
        actual_poly = polyexponential(4, 0.0291675, 14.614642, 2.0)
        torch.testing.assert_close(
            actual_poly,
            torch.tensor([14.6146402359, 0.4622210264, 0.0581951588, 0.0291675013, 0.0]),
        )
        for sigmas in (actual_karras, actual_exponential, actual_poly):
            self.assertEqual((5,), tuple(sigmas.shape))
            self.assertEqual(torch.float32, sigmas.dtype)
            self.assertEqual("cpu", sigmas.device.type)
            self.assertEqual(0.0, float(sigmas[-1]))
            self.assertTrue(bool(torch.all(sigmas[:-2] > sigmas[1:-1])))

        poly_rho_one = polyexponential(20, 0.0291675, 14.614642, 1.0)
        exp_twenty = exponential(20, 0.0291675, 14.614642)
        torch.testing.assert_close(poly_rho_one, exp_twenty, rtol=1e-5, atol=1e-6)
        self.assertFalse(torch.equal(poly_rho_one, exp_twenty))
        self.assertEqual([1.0, 1.0, 1.0, 1.0, 0.0], polyexponential(4, 0.1, 1.0, 0.0).tolist())
        with self.assertRaises(ZeroDivisionError):
            karras(4, 0.1, 1.0, 0.0)
        unstable = karras(4, 0.0291675, 14.614642, 0.1)
        self.assertEqual(0.0, float(unstable[-2]), "small positive rho can lose sigma_min in float32")
        nan_schedule = karras(4, 0.0291675, 14.614642, 0.01)
        self.assertTrue(bool(torch.isnan(nan_schedule[:-1]).all()))
        with self.assertRaises(OverflowError):
            karras(4, 0.0291675, 5000.0, 0.01)
        with self.assertRaises(ValueError):
            exponential(4, 0.0, 1.0)
        with self.assertRaises(ValueError):
            polyexponential(4, 0.0, 1.0, 1.0)
        self.assertTrue(bool(torch.all(exponential(4, 1.0, 0.1)[:-2] < exponential(4, 1.0, 0.1)[1:-1])))
        self.assertEqual([14.614643096923828, 0.0], exponential(1, 0.0291675, 14.614642).tolist())

        calls: list[tuple[Any, str, int]] = []

        def calculate_sigmas(model_sampling: Any, scheduler: str, steps: int) -> torch.Tensor:
            calls.append((model_sampling, scheduler, steps))
            return torch.arange(steps + 1, dtype=torch.float32)

        basic = extract_basic_scheduler(calculate_sigmas)

        class FakeModel:
            def get_model_object(self, key: str) -> tuple[str, str]:
                return ("model_sampling", key)

        calls.clear()
        full = basic.execute(FakeModel(), "simple", 4, 1.0).args[0]
        self.assertEqual([0.0, 1.0, 2.0, 3.0, 4.0], full.tolist())
        self.assertEqual([(("model_sampling", "model_sampling"), "simple", 4)], calls)
        calls.clear()
        partial = basic.execute(FakeModel(), "simple", 4, 0.5).args[0]
        self.assertEqual([4.0, 5.0, 6.0, 7.0, 8.0], partial.tolist())
        self.assertEqual([(("model_sampling", "model_sampling"), "simple", 8)], calls)
        calls.clear()
        empty = basic.execute(FakeModel(), "simple", 4, 0.0).args[0]
        self.assertEqual([], empty.tolist())
        self.assertEqual([], calls)

        samplers_path = SOURCE / "comfy" / "samplers.py"
        samplers_tree = ast.parse(samplers_path.read_text(encoding="utf-8"))
        kl_node = next(
            node
            for node in samplers_tree.body
            if isinstance(node, ast.FunctionDef) and node.name == "kl_optimal_scheduler"
        )
        kl_namespace: dict[str, Any] = {"math": math, "torch": torch}
        exec(compile(ast.Module(body=[kl_node], type_ignores=[]), str(samplers_path), "exec"), kl_namespace)
        one_step_kl = kl_namespace["kl_optimal_scheduler"](1, 0.0291675, 14.614642)
        self.assertTrue(bool(torch.isnan(one_step_kl[0])))
        self.assertEqual(0.0, float(one_step_kl[1]))
        kl_basic = extract_basic_scheduler(
            lambda _model_sampling, scheduler, steps: kl_namespace["kl_optimal_scheduler"](
                steps, 0.0291675, 14.614642
            )
            if scheduler == "kl_optimal"
            else torch.empty(0)
        )
        one_total_step = kl_basic.execute(FakeModel(), "kl_optimal", 1, 1.0).args[0]
        self.assertTrue(bool(torch.isnan(one_total_step[0])))
        self.assertEqual(0.0, float(one_total_step[1]))
        two_total_steps = kl_basic.execute(FakeModel(), "kl_optimal", 1, 0.5).args[0]
        self.assertTrue(bool(torch.isfinite(two_total_steps).all()))
        self.assertEqual(2, len(two_total_steps))

    def test_pinned_source_registration_and_embedded_docs(self) -> None:
        custom = (SOURCE / "comfy_extras" / "nodes_custom_sampler.py").read_text(encoding="utf-8")
        sampling = (SOURCE / "comfy" / "k_diffusion" / "sampling.py").read_text(encoding="utf-8")
        samplers = (SOURCE / "comfy" / "samplers.py").read_text(encoding="utf-8")
        for class_type in TARGET_TYPES:
            self.assertIn(f"class {class_type}(io.ComfyNode):", custom)
            self.assertIn(f"            {class_type},", custom)
        self.assertIn('if denoise <= 0.0:\n                return io.NodeOutput(torch.FloatTensor([]))', custom)
        self.assertIn('sigmas = sigmas[-(steps + 1):]', custom)
        self.assertIn('ramp = torch.linspace(0, 1, n, device=device)', sampling)
        self.assertIn('torch.linspace(math.log(sigma_max), math.log(sigma_min), n, device=device).exp()', sampling)
        self.assertIn('ramp = torch.linspace(1, 0, n, device=device) ** rho', sampling)
        self.assertIn('return append_zero(sigmas)', sampling)
        self.assertIn('"linear_quadratic": SchedulerHandler(linear_quadratic_schedule)', samplers)
        self.assertIn('"kl_optimal": SchedulerHandler(kl_optimal_scheduler, use_ms=False)', samplers)

        self.assertEqual(DOCS_SHA256, hashlib.sha256(DOCS_WHEEL.read_bytes()).hexdigest())
        with zipfile.ZipFile(DOCS_WHEEL) as archive:
            names = set(archive.namelist())
            for class_type in TARGET_TYPES:
                for locale in ("en", "ru"):
                    path = f"comfyui_embedded_docs/docs/{class_type}/{locale}.md"
                    self.assertIn(path, names)
                self.assertIn("AI-generated", archive.read(f"comfyui_embedded_docs/docs/{class_type}/en.md").decode("utf-8"))

    def test_workflow_wheel_integrity_exhaustive_census_and_topology(self) -> None:
        self.assertEqual(WORKFLOW_SHA256, hashlib.sha256(WORKFLOW_WHEEL.read_bytes()).hexdigest())
        records: list[dict[str, Any]] = []
        root_graphs = 0
        subgraphs = 0
        json_members = 0
        payloads_by_basename: dict[str, dict[str, Any]] = {}

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
                payloads_by_basename[Path(member).name] = payload
                definitions = payload.get("definitions")
                if isinstance(definitions, dict) and isinstance(definitions.get("subgraphs"), list):
                    subgraphs += len(definitions["subgraphs"])
                for record in graph_records(payload, member):
                    if record["node"].get("type") in TARGET_TYPES:
                        records.append(record)

        self.assertEqual((512, 496, 272), (json_members, root_graphs, subgraphs))
        expected = {
            "BasicScheduler": (46, 13, 33, 38, 24, Counter({0: 44, 4: 2})),
            "KarrasScheduler": (0, 0, 0, 0, 0, Counter()),
            "ExponentialScheduler": (0, 0, 0, 0, 0, Counter()),
            "PolyexponentialScheduler": (0, 0, 0, 0, 0, Counter()),
        }
        for class_type, values in expected.items():
            matches = [record for record in records if record["node"]["type"] == class_type]
            actual = (
                len(matches),
                sum(record["scope"] == "root" for record in matches),
                sum(record["scope"] == "subgraph" for record in matches),
                len({record["member"] for record in matches}),
                len({record["workflowId"] for record in matches}),
                Counter(record["node"].get("mode", 0) for record in matches),
            )
            self.assertEqual(values, actual, class_type)

        basic_records = [record for record in records if record["node"]["type"] == "BasicScheduler"]
        self.assertEqual(
            Counter(
                {
                    ("simple", 20, 1): 15,
                    ("normal", 1, 1): 5,
                    ("normal", 28, 1): 2,
                    ("simple", 25, 1): 2,
                    ("beta", 26, 1): 1,
                    ("normal", 40, 1): 1,
                    ("simple", 8, 1): 3,
                    ("simple", 4, 1): 3,
                    ("simple", 30, 1): 2,
                    ("simple", 6, 1): 9,
                    ("normal", 6, 1): 2,
                    ("simple", 48, 1): 1,
                }
            ),
            Counter(tuple(record["node"]["widgets_values"]) for record in basic_records),
        )
        self.assertEqual(Counter({"simple": 35, "normal": 10, "beta": 1}), Counter(record["node"]["widgets_values"][0] for record in basic_records))
        self.assertTrue(all(record["node"]["widgets_values"][2] == 1 for record in basic_records))
        self.assertTrue(
            all(
                any(item.get("name") == "model" and item.get("link") is not None for item in record["node"].get("inputs", []))
                for record in basic_records
            )
        )
        self.assertTrue(all((record["node"].get("outputs") or [{}])[0].get("links") for record in basic_records))
        self.assertEqual(
            Counter({False: 35, True: 11}),
            Counter(
                any(item.get("name") == "steps" and item.get("link") is not None for item in record["node"].get("inputs", []))
                for record in basic_records
            ),
        )

        flux = payloads_by_basename["flux_redux_model_example.json"]
        by_id = {node["id"]: node for node in flux["nodes"]}
        links = {link[0]: link for link in flux["links"]}
        self.assertEqual("ModelSamplingFlux", by_id[30]["type"])
        self.assertEqual("BasicScheduler", by_id[17]["type"])
        self.assertEqual(["simple", 20, 1], by_id[17]["widgets_values"])
        self.assertEqual("SamplerCustomAdvanced", by_id[13]["type"])
        self.assertEqual([55, 30, 0, 17, 0, "MODEL"], links[55])
        self.assertEqual([20, 17, 0, 13, 3, "SIGMAS"], links[20])
        self.assertEqual([54, 30, 0, 22, 0, "MODEL"], links[54])
        self.assertEqual([30, 22, 0, 13, 1, "GUIDER"], links[30])


if __name__ == "__main__":
    unittest.main()
