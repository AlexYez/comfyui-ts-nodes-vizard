from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import sys
import unittest
import zipfile
from pathlib import Path
from typing import Any, Iterator

from tools import catalog


ARTICLE_SPECS: dict[str, dict[str, Any]] = {
    "core.sampler-dpm-adaptative": {
        "directory": "sampler-dpm-adaptative",
        "classType": "SamplerDPMAdaptative",
        "fingerprint": "sha256:24acc6744a20b4fccd23e3a8da6528a33cf40c7ea5f50f3c39eb0fbce08c1d20",
        "recipe": "recipe.dpm-adaptive-custom-sampling",
    },
    "core.sampler-er-sde": {
        "directory": "sampler-er-sde",
        "classType": "SamplerER_SDE",
        "fingerprint": "sha256:0ae3ab6330f9bd9fe0bc92fe1fb5e1390a66c75cbd7440fc96034b817744d154",
        "recipe": "recipe.er-sde-custom-sampling",
    },
    "core.sampler-sa-solver": {
        "directory": "sampler-sa-solver",
        "classType": "SamplerSASolver",
        "fingerprint": "sha256:7ec45336a1cbbede4c2d5a067f5b107ec7f8d73538f009c95f987686842b21af",
        "recipe": "recipe.sa-solver-custom-sampling",
    },
    "core.sampler-seeds2": {
        "directory": "sampler-seeds2",
        "classType": "SamplerSEEDS2",
        "fingerprint": "sha256:64ec132f1a3d1f6f52de1f764c4374cdd858a8dcfdf5e8fcd793210942208781",
        "recipe": "recipe.seeds2-deterministic-exp-heun",
    },
}

RECIPE_DIRECTORIES = {
    "recipe.dpm-adaptive-custom-sampling": "dpm-adaptive-custom-sampling",
    "recipe.er-sde-custom-sampling": "er-sde-custom-sampling",
    "recipe.sa-solver-custom-sampling": "sa-solver-custom-sampling",
    "recipe.seeds2-deterministic-exp-heun": "seeds2-deterministic-exp-heun",
}

EXPECTED_SETTINGS = {
    "recipe.dpm-adaptive-custom-sampling": {
        "order": 3, "rtol": 0.05, "atol": 0.0078, "h_init": 0.05,
        "pcoeff": 0.0, "icoeff": 1.0, "dcoeff": 0.0,
        "accept_safety": 0.81, "eta": 0.0, "s_noise": 1.0,
    },
    "recipe.er-sde-custom-sampling": {"solver_type": "ER-SDE", "max_stage": 3, "eta": 1.0, "s_noise": 1.0},
    "recipe.sa-solver-custom-sampling": {
        "eta": 1.0, "sde_start_percent": 0.2, "sde_end_percent": 0.8,
        "s_noise": 1.0, "predictor_order": 3, "corrector_order": 4,
        "use_pece": False, "simple_order_2": False,
    },
    "recipe.seeds2-deterministic-exp-heun": {"solver_type": "phi_2", "eta": 0.0, "s_noise": 1.0, "r": 1.0},
}

INVENTORY = catalog.CONTENT / "runtime" / "comfyui-0.32.0.object-info.json"
SOURCE = catalog.ROOT / ".comfyui-source-0.32.0"
REPLACEMENTS = catalog.CONTENT / "runtime" / "comfyui-0.32.0.node-replacements.json"
WORKFLOW_WHEEL = catalog.ROOT / ".upstream-cache" / "comfyui_workflow_templates_json-0.1.42-py3-none-any.whl"
WORKFLOW_SHA = "242982d65e1c51ca03d892bc1009bb6843f457e7dfc0c20afe6438770b7a14a3"
DOCS_WHEEL = catalog.ROOT / ".upstream-cache" / "comfyui_embedded_docs-0.5.9-py3-none-any.whl"
DOCS_SHA = "30afae432a71c96aa59421d0f37388c66ff6572b8cbeee8ff045e4d5f84f896c"
PROBE = Path(__file__).with_name("special_sampler_synthetic_probe.py")


def article_path(spec: dict[str, Any]) -> Path:
    return catalog.CONTENT / "articles" / "core" / spec["directory"] / "manifest.json"


def recipe_path(recipe_id: str) -> Path:
    return catalog.CONTENT / "recipes" / RECIPE_DIRECTORIES[recipe_id] / "recipe.json"


def all_article_ids() -> set[str]:
    return {
        payload["articleId"]
        for path in (catalog.CONTENT / "articles").rglob("manifest.json")
        if isinstance((payload := catalog.load_json(path)), dict)
        and isinstance(payload.get("articleId"), str)
    }


def graph_records(payload: dict[str, Any]) -> Iterator[dict[str, Any]]:
    if isinstance(payload.get("nodes"), list):
        for node in payload["nodes"]:
            if isinstance(node, dict):
                yield node
    definitions = payload.get("definitions")
    subgraphs = definitions.get("subgraphs", []) if isinstance(definitions, dict) else []
    for graph in subgraphs:
        if isinstance(graph, dict):
            for node in graph.get("nodes", []):
                if isinstance(node, dict):
                    yield node


class SpecialSamplerContentTests(unittest.TestCase):
    def test_schema_honesty_cross_links_and_natural_russian(self) -> None:
        schemas = {
            key: catalog.load_json(catalog.CONTENT / "schemas" / filename)
            for key, filename in {
                "article": "article.schema.v1.json",
                "recipe": "recipe.schema.v1.json",
                "fragment": "recipe-fragment.schema.v1.json",
                "research": "article-research.schema.v1.json",
            }.items()
        }
        article_ids = all_article_ids()
        errors: list[str] = []
        texts: list[Path] = []
        for article_id, spec in ARTICLE_SPECS.items():
            path = article_path(spec)
            article = catalog.load_json(path)
            self.assertEqual([], catalog.json_schema_errors(article, schemas["article"]))
            catalog.validate_article(path, article, errors)
            self.assertEqual(article_id, article["articleId"])
            self.assertEqual(("draft", "in_review"), (article["status"], article["editorial"]["state"]))
            self.assertEqual("comfy_extras.nodes_custom_sampler", article["runtimeIdentity"]["pythonModule"])
            self.assertEqual([], article["runtimeIdentity"]["aliases"])
            self.assertFalse(article["experimental"])
            self.assertEqual(spec["fingerprint"], article["editorial"]["schemaHash"])
            self.assertEqual({spec["recipe"]}, {asset["id"] for asset in article["assets"] if asset["type"] == "recipe"})
            targets = set(article["relations"]["related"] + article["relations"]["alternatives"])
            self.assertTrue(targets.issubset(article_ids))
            body = path.parent / article["body"]
            self.assertEqual(10, len(re.findall(r"^## .+$", body.read_text(encoding="utf-8"), re.MULTILINE)))
            texts.append(body)

            research = catalog.load_json(catalog.CONTENT / "research" / "reviews" / f"{article_id}.json")
            self.assertEqual([], catalog.json_schema_errors(research, schemas["research"]))
            self.assertEqual(("fact_checked", "automated_assisted"), (research["state"], research["reviewMode"]))
            self.assertTrue(research["checks"]["exampleSchemaValidated"])
            self.assertFalse(research["checks"]["exampleExecuted"])
            self.assertTrue(research["knownGaps"])

        for recipe_id, directory in RECIPE_DIRECTORIES.items():
            path = recipe_path(recipe_id)
            recipe = catalog.load_json(path)
            self.assertEqual([], catalog.json_schema_errors(recipe, schemas["recipe"]))
            catalog.validate_recipe(path, recipe, article_ids, errors)
            self.assertEqual("in_review", recipe["editorial"]["state"])
            self.assertIn("human approval pending", recipe["editorial"]["reviewedBy"])
            self.assertNotIn("workflow", recipe)
            fragment_path = path.parent / recipe["fragment"]["path"]
            fragment = catalog.load_json(fragment_path)
            self.assertEqual([], catalog.json_schema_errors(fragment, schemas["fragment"]))
            catalog.validate_fragment(fragment_path, fragment, errors)
            algorithm = next(node for node in fragment["nodes"] if node["ref"] == "algorithm")
            self.assertEqual(EXPECTED_SETTINGS[recipe_id], algorithm["settings"])
            self.assertEqual("SamplerCustomAdvanced", next(node for node in fragment["nodes"] if node["ref"] == "sample")["classType"])
            texts.append(path.parent / recipe["body"])
        self.assertEqual([], errors)

        forbidden = (
            "важно отметить", "стоит отметить", "следует отметить", "таким образом",
            "в современном мире", "давайте", "погрузимся", "революционн",
            "является мощн", "подводя итог", "в заключение", "данная нода",
        )
        for path in texts:
            text = path.read_text(encoding="utf-8").lower()
            self.assertNotIn("\ufffd", text)
            for phrase in forbidden:
                self.assertNotIn(phrase, text, path)

    def test_runtime_fingerprints_ports_settings_and_fragment_types(self) -> None:
        inventory = catalog.load_json(INVENTORY)
        for spec in ARTICLE_SPECS.values():
            runtime = inventory[spec["classType"]]
            self.assertEqual("comfy_extras.nodes_custom_sampler", runtime["python_module"])
            self.assertEqual(spec["fingerprint"], catalog.schema_fingerprint(spec["classType"], runtime))
            self.assertFalse(runtime.get("experimental", False))
            self.assertFalse(runtime.get("deprecated", False))

        self.assertEqual(["order", "rtol", "atol", "h_init", "pcoeff", "icoeff", "dcoeff", "accept_safety", "eta", "s_noise"], inventory["SamplerDPMAdaptative"]["input_order"]["required"])
        self.assertEqual(["ER-SDE", "Reverse-time SDE", "ODE"], inventory["SamplerER_SDE"]["input"]["required"]["solver_type"][1]["options"])
        self.assertEqual((3, 1, 3), tuple(inventory["SamplerER_SDE"]["input"]["required"]["max_stage"][1][key] for key in ("default", "min", "max")))
        self.assertEqual(["model", "eta", "sde_start_percent", "sde_end_percent", "s_noise", "predictor_order", "corrector_order", "use_pece", "simple_order_2"], inventory["SamplerSASolver"]["input_order"]["required"])
        self.assertEqual(["phi_1", "phi_2"], inventory["SamplerSEEDS2"]["input"]["required"]["solver_type"][1]["options"])
        self.assertEqual((0.5, 0.01, 1.0), tuple(inventory["SamplerSEEDS2"]["input"]["required"]["r"][1][key] for key in ("default", "min", "max")))

        for recipe_id in RECIPE_DIRECTORIES:
            recipe = catalog.load_json(recipe_path(recipe_id))
            fragment = catalog.load_json(recipe_path(recipe_id).parent / recipe["fragment"]["path"])
            nodes = {node["ref"]: node for node in fragment["nodes"]}
            for external in fragment["externalInputs"]:
                runtime = inventory[nodes[external["to"]]["classType"]]
                inputs = {**runtime["input"].get("required", {}), **runtime["input"].get("optional", {})}
                self.assertEqual(external["type"], inputs[external["input"]][0])
            for link in fragment["connections"]:
                source = inventory[nodes[link["from"]]["classType"]]
                target = inventory[nodes[link["to"]]["classType"]]
                index = source["output_name"].index(link["output"])
                self.assertEqual(source["output"][index], target["input"]["required"][link["input"]][0])
            algorithm = nodes["algorithm"]
            runtime_inputs = inventory[algorithm["classType"]]["input"]["required"]
            for name, value in algorithm["settings"].items():
                self.assertIn(name, runtime_inputs)
                kind, config = runtime_inputs[name]
                if kind == "COMBO":
                    self.assertIn(value, config["options"])
                if isinstance(value, (int, float)) and not isinstance(value, bool):
                    if "min" in config:
                        self.assertGreaterEqual(value, config["min"])
                    if "max" in config:
                        self.assertLessEqual(value, config["max"])

    @unittest.skipUnless(SOURCE.exists(), "pinned ComfyUI source checkout is absent")
    def test_pinned_source_semantics_and_replacement_absence(self) -> None:
        custom = (SOURCE / "comfy_extras" / "nodes_custom_sampler.py").read_text(encoding="utf-8")
        samplers = (SOURCE / "comfy" / "samplers.py").read_text(encoding="utf-8")
        sampling = (SOURCE / "comfy" / "k_diffusion" / "sampling.py").read_text(encoding="utf-8")
        tau = (SOURCE / "comfy" / "k_diffusion" / "sa_solver.py").read_text(encoding="utf-8")
        self.assertIn('ksampler("dpm_adaptive"', custom)
        self.assertIn("if len(sigmas) <= 1:", samplers)
        self.assertIn("sigma_min = sigmas[-2]", samplers)
        self.assertIn("sample_dpm_adaptive(model, noise, sigma_min, sigmas[0]", samplers)
        self.assertIn('"ER-SDE": er_sde_noise_scaler', custom)
        self.assertIn('if solver_type == "ODE" or eta == 0:', custom)
        self.assertIn("stage_used = min(max_stage, i + 1)", sampling)
        self.assertIn("num_integration_points = 200.0", sampling)
        self.assertIn("start_sigma = model_sampling.percent_to_sigma(sde_start_percent)", custom)
        self.assertIn("end_sigma = model_sampling.percent_to_sigma(sde_end_percent)", custom)
        self.assertIn("return eta if start_sigma >= sigma >= end_sigma else 0.0", tau)
        self.assertIn("predictor_order_used = min(predictor_order, len(pred_list))", sampling)
        self.assertIn("if use_pece:", sampling)
        self.assertIn('sampler_name = "seeds_2"', custom)
        self.assertIn("inject_noise = eta > 0 and s_noise > 0", sampling)
        self.assertIn("denoised_2 = model(x_2, sigma_s_1 * s_in", sampling)
        replacements = REPLACEMENTS.read_text(encoding="utf-8")
        for spec in ARTICLE_SPECS.values():
            self.assertNotIn(spec["classType"], replacements)

    @unittest.skipUnless(DOCS_WHEEL.exists(), "pinned embedded-docs wheel is absent")
    def test_pinned_docs_and_documented_discrepancies(self) -> None:
        self.assertEqual(DOCS_SHA, hashlib.sha256(DOCS_WHEEL.read_bytes()).hexdigest())
        with zipfile.ZipFile(DOCS_WHEEL) as archive:
            docs = {}
            for spec in ARTICLE_SPECS.values():
                for locale in ("en", "ru"):
                    member = f"comfyui_embedded_docs/docs/{spec['classType']}/{locale}.md"
                    self.assertIn(member, archive.namelist())
                    docs[f"{spec['classType']}:{locale}"] = archive.read(member).decode("utf-8")
        self.assertNotIn("sigma_min", docs["SamplerDPMAdaptative:en"])
        self.assertIn("doesn't apply to ER-SDE", docs["SamplerER_SDE:en"])
        self.assertIn("Вот перевод документации", docs["SamplerSASolver:ru"])
        self.assertIn("step size scaling factor", docs["SamplerSASolver:en"])
        self.assertNotIn("two model", docs["SamplerSEEDS2:en"].lower())

    @unittest.skipUnless(WORKFLOW_WHEEL.exists(), "official workflow wheel is absent")
    def test_exhaustive_workflow_absence(self) -> None:
        self.assertEqual(WORKFLOW_SHA, hashlib.sha256(WORKFLOW_WHEEL.read_bytes()).hexdigest())
        targets = {spec["classType"] for spec in ARTICLE_SPECS.values()}
        counts = {target: 0 for target in targets}
        json_count = root_count = subgraph_count = 0
        with zipfile.ZipFile(WORKFLOW_WHEEL) as archive:
            for member in [name for name in archive.namelist() if "/templates/" in name and name.endswith(".json")]:
                json_count += 1
                payload = json.loads(archive.read(member).decode("utf-8"))
                if not isinstance(payload, dict):
                    continue
                if isinstance(payload.get("nodes"), list):
                    root_count += 1
                definitions = payload.get("definitions")
                subgraphs = definitions.get("subgraphs", []) if isinstance(definitions, dict) else []
                subgraph_count += sum(isinstance(graph, dict) for graph in subgraphs)
                for node in graph_records(payload):
                    if node.get("type") in counts:
                        counts[node["type"]] += 1
        self.assertEqual((512, 496, 272), (json_count, root_count, subgraph_count))
        self.assertEqual({target: 0 for target in targets}, counts)

    @unittest.skipUnless(SOURCE.exists(), "pinned ComfyUI source checkout is absent")
    def test_safe_exact_source_probe(self) -> None:
        candidates = [
            Path(os.environ.get("TEMP", "")) / "nodes-wizard-comfyui-v0.32.0-venv" / "Scripts" / "python.exe",
            Path(sys.executable),
        ]
        python = next((path for path in candidates if path.exists()), None)
        if python is None:
            self.skipTest("no Python interpreter")
        result = subprocess.run([str(python), str(PROBE), str(SOURCE)], cwd=catalog.ROOT, text=True, capture_output=True, timeout=120, check=False)
        if result.returncode != 0:
            self.fail(result.stderr or result.stdout)
        payload = json.loads(result.stdout.strip().splitlines()[-1])
        self.assertEqual("dpm_adaptive", payload["dpm"]["name"])
        self.assertEqual(3, payload["dpm"]["options"]["order"])
        self.assertAlmostEqual(7.3280687, payload["erSde"]["erScalerAt2"], places=5)
        self.assertAlmostEqual(2.8284271, payload["erSde"]["reverseScalerAt2"], places=5)
        self.assertEqual((0.0, 0.0), (payload["erSde"]["odeNoise"], payload["erSde"]["etaZeroNoise"]))
        self.assertEqual([0.2, 0.8], payload["saSolver"]["percentCalls"])
        self.assertEqual([0.0, 1.5, 1.5, 1.5, 0.0], payload["saSolver"]["tauSamples"])
        self.assertEqual("seeds_2", payload["seeds2"]["name"])
        self.assertEqual({"eta": 0.0, "s_noise": 1.0, "r": 1.0, "solver_type": "phi_2"}, payload["seeds2"]["options"])


if __name__ == "__main__":
    unittest.main()
