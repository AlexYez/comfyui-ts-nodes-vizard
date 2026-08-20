from __future__ import annotations

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
    "core.split-sigmas-denoise": {
        "directory": "split-sigmas-denoise",
        "classType": "SplitSigmasDenoise",
        "fingerprint": "sha256:163749d9313dd450617727969204c5da4c5049ea382d728ef180589fb9733940",
        "recipe": "recipe.split-sigmas-denoise-half",
        "category": "model/sampling/sigmas",
    },
    "core.vp-scheduler": {
        "directory": "vp-scheduler",
        "classType": "VPScheduler",
        "fingerprint": "sha256:de35233a496e3f12d6ad62a3f5292415654bd3b1d9283f6a2f44073b13a48e3c",
        "recipe": "recipe.vp-sigma-schedule-four-step",
        "category": "model/sampling/schedulers",
    },
    "core.beta-sampling-scheduler": {
        "directory": "beta-sampling-scheduler",
        "classType": "BetaSamplingScheduler",
        "fingerprint": "sha256:b4fdc61480a09739cdee3e672ae8e878600231a644d7c9cad2401b0efb07db15",
        "recipe": "recipe.chroma-beta-sigma-schedule",
        "category": "model/sampling/schedulers",
    },
    "core.laplace-scheduler": {
        "directory": "laplace-scheduler",
        "classType": "LaplaceScheduler",
        "fingerprint": "sha256:c8608fd60ebaa2e13e9da8947490a2f427f1fb362d37ad7aef4b5a9f423d1f9a",
        "recipe": "recipe.inspect-laplace-sigma-schedule",
        "category": "model/sampling/schedulers",
    },
}

RECIPE_DIRECTORIES = {
    "recipe.split-sigmas-denoise-half": "split-sigmas-denoise-half",
    "recipe.vp-sigma-schedule-four-step": "vp-sigma-schedule-four-step",
    "recipe.chroma-beta-sigma-schedule": "chroma-beta-sigma-schedule",
    "recipe.inspect-laplace-sigma-schedule": "inspect-laplace-sigma-schedule",
}

EXPECTED_FRAGMENT_NODES = {
    "recipe.split-sigmas-denoise-half": [
        ("SplitSigmasDenoise", {"denoise": 0.5}),
    ],
    "recipe.vp-sigma-schedule-four-step": [
        ("VPScheduler", {"steps": 4, "beta_d": 19.9, "beta_min": 0.1, "eps_s": 0.001}),
    ],
    "recipe.chroma-beta-sigma-schedule": [
        ("ModelSamplingAuraFlow", {"shift": 1.0}),
        ("BetaSamplingScheduler", {"steps": 30, "alpha": 0.4, "beta": 0.4}),
    ],
    "recipe.inspect-laplace-sigma-schedule": [
        (
            "LaplaceScheduler",
            {"steps": 5, "sigma_max": 14.614642, "sigma_min": 0.0291675, "mu": 0.0, "beta": 0.5},
        ),
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
SYNTHETIC_PROBE = Path(__file__).with_name("scheduler_split_denoise_synthetic_probe.py")


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


def normalized_links(graph: dict[str, Any]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for link in graph.get("links", []):
        if isinstance(link, list) and len(link) >= 6:
            result.append(
                {
                    "origin_id": link[1],
                    "origin_slot": link[2],
                    "target_id": link[3],
                    "target_slot": link[4],
                    "type": link[5],
                }
            )
        elif isinstance(link, dict):
            result.append(link)
    return result


def workflow_graphs(payload: dict[str, Any]) -> Iterator[tuple[str, dict[str, Any]]]:
    yield "root", payload
    definitions = payload.get("definitions")
    subgraphs = definitions.get("subgraphs", []) if isinstance(definitions, dict) else []
    for index, subgraph in enumerate(subgraphs):
        if isinstance(subgraph, dict):
            yield f"subgraph:{index}", subgraph


class SchedulerSplitDenoiseContentTests(unittest.TestCase):
    def test_articles_fragment_only_recipes_and_research_validate(self) -> None:
        article_ids = all_article_ids()
        article_schema = catalog.load_json(catalog.CONTENT / "schemas" / "article.schema.v1.json")
        recipe_schema = catalog.load_json(catalog.CONTENT / "schemas" / "recipe.schema.v1.json")
        fragment_schema = catalog.load_json(catalog.CONTENT / "schemas" / "recipe-fragment.schema.v1.json")
        research_schema = catalog.load_json(catalog.CONTENT / "schemas" / "article-research.schema.v1.json")
        errors: list[str] = []
        cliche_pattern = re.compile(
            r"без воды|коротко о главном|понятно и доступно|по-честному|"
            r"идеальн|революционн|уникальная возможность|в современном мире|"
            r"давайте разбер|важно отметить|стоит подчеркнуть|подводя итог|"
            r"данная нода|является незаменим|устали от|знакомо\?|успейте",
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
            self.assertEqual(EXPECTED_HEADINGS, re.findall(r"^## (.+)$", body, re.MULTILINE))
            self.assertNotIn("\ufffd", body)
            self.assertNotRegex(body, cliche_pattern)

            research = catalog.load_json(catalog.CONTENT / "research" / "reviews" / f"{article_id}.json")
            self.assertEqual([], catalog.json_schema_errors(research, research_schema))
            self.assertEqual(spec["classType"], research["node"]["classType"])
            self.assertEqual("comfy_extras.nodes_custom_sampler", research["node"]["pythonModule"])
            self.assertEqual("fact_checked", research["state"])
            self.assertEqual("automated_assisted", research["reviewMode"])
            self.assertFalse(research["checks"]["exampleExecuted"])
            self.assertTrue(research["checks"]["exampleSchemaValidated"])
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
            self.assertNotIn("\ufffd", body)
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
            self.assertEqual("comfy_extras.nodes_custom_sampler", runtime["python_module"])
            self.assertEqual(spec["category"], runtime["category"])
            self.assertEqual(spec["fingerprint"], catalog.schema_fingerprint(spec["classType"], runtime))
            self.assertEqual(spec["fingerprint"], article["editorial"]["schemaHash"])
            self.assertFalse(runtime.get("experimental", False))
            self.assertFalse(runtime.get("deprecated", False))
            self.assertFalse(runtime.get("api_node", False))
            self.assertFalse(runtime["is_input_list"])
            self.assertIsNone(runtime.get("search_aliases"))

        self.assertEqual(
            {"default": 1.0, "min": 0.0, "max": 1.0, "step": 0.01},
            nodes["SplitSigmasDenoise"]["input"]["required"]["denoise"][1],
        )
        self.assertEqual(["SIGMAS", "SIGMAS"], nodes["SplitSigmasDenoise"]["output"])
        self.assertEqual(["high_sigmas", "low_sigmas"], nodes["SplitSigmasDenoise"]["output_name"])
        self.assertEqual(
            {"default": 19.9, "min": 0.0, "max": 5000.0, "step": 0.01, "round": False, "advanced": True},
            nodes["VPScheduler"]["input"]["required"]["beta_d"][1],
        )
        self.assertEqual(
            {"default": 0.001, "min": 0.0, "max": 1.0, "step": 0.0001, "round": False, "advanced": True},
            nodes["VPScheduler"]["input"]["required"]["eps_s"][1],
        )
        self.assertEqual("MODEL", nodes["BetaSamplingScheduler"]["input"]["required"]["model"][0])
        self.assertEqual(
            {"default": 0.6, "min": 0.0, "max": 50.0, "step": 0.01, "round": False, "advanced": True},
            nodes["BetaSamplingScheduler"]["input"]["required"]["alpha"][1],
        )
        self.assertEqual(
            {"default": 14.614642, "min": 0.0, "max": 5000.0, "step": 0.01, "round": False, "advanced": True},
            nodes["LaplaceScheduler"]["input"]["required"]["sigma_max"][1],
        )
        self.assertEqual(
            {"default": 0.0, "min": -10.0, "max": 10.0, "step": 0.1, "round": False, "advanced": True},
            nodes["LaplaceScheduler"]["input"]["required"]["mu"][1],
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
                    if isinstance(value, (int, float)) and not isinstance(value, bool):
                        self.assertGreaterEqual(value, options.get("min", value))
                        self.assertLessEqual(value, options.get("max", value))
            for connection in fragment["connections"]:
                source = dict(nodes[refs[connection["from"]]["classType"]])
                target = dict(nodes[refs[connection["to"]]["classType"]])
                output_index = source["output_name"].index(connection["output"])
                self.assertEqual(source["output"][output_index], runtime_inputs(target)[connection["input"]][0])

    @unittest.skipUnless(SOURCE.exists(), "pinned ComfyUI source checkout is absent")
    def test_exact_source_formulas_boundaries_and_replacement_absence(self) -> None:
        custom = (SOURCE / "comfy_extras" / "nodes_custom_sampler.py").read_text(encoding="utf-8")
        k_sampling = (SOURCE / "comfy" / "k_diffusion" / "sampling.py").read_text(encoding="utf-8")
        samplers = (SOURCE / "comfy" / "samplers.py").read_text(encoding="utf-8")
        self.assertIn("total_steps = round(steps * denoise)", custom)
        self.assertIn("sigmas1 = sigmas[:-(total_steps)]", custom)
        self.assertIn("sigmas2 = sigmas[-(total_steps + 1):]", custom)
        self.assertIn("get_sigmas_vp(n=steps, beta_d=beta_d, beta_min=beta_min, eps_s=eps_s)", custom)
        self.assertIn("beta_scheduler(model.get_model_object(\"model_sampling\"), steps, alpha=alpha, beta=beta)", custom)
        self.assertIn("get_sigmas_laplace(n=steps, sigma_min=sigma_min, sigma_max=sigma_max, mu=mu, beta=beta)", custom)

        self.assertIn("t = torch.linspace(1, eps_s, n, device=device)", k_sampling)
        self.assertIn("torch.special.expm1(beta_d * t ** 2 / 2 + beta_min * t)", k_sampling)
        self.assertIn("return append_zero(sigmas)", k_sampling)
        laplace_function = k_sampling.split("def get_sigmas_laplace", 1)[1].split("def to_d", 1)[0]
        self.assertIn("torch.linspace(0, 1, n", laplace_function)
        self.assertIn("clamp(torch.exp(lmb))", laplace_function)
        self.assertNotIn("append_zero", laplace_function)

        self.assertIn("scipy.stats.beta.ppf(ts, alpha, beta)", samplers)
        self.assertIn("numpy.rint", samplers)
        self.assertIn("if t != last_t:", samplers)
        self.assertIn("sigs += [0.0]", samplers)
        self.assertIn("total_steps = len(sigmas) - 1", samplers)
        self.assertIn("inverse_noise_scaling(sigmas[-1]", samplers)

        replacements_text = json.dumps(catalog.load_json(REPLACEMENTS), sort_keys=True)
        for spec in ARTICLE_SPECS.values():
            self.assertNotIn(spec["classType"], replacements_text)

    @unittest.skipUnless(DOCS_WHEEL.exists(), "pinned embedded docs wheel is absent")
    def test_pinned_embedded_docs_are_present_and_bounded(self) -> None:
        self.assertEqual(DOCS_WHEEL_SHA256, hashlib.sha256(DOCS_WHEEL.read_bytes()).hexdigest())
        members = {
            "comfyui_embedded_docs/docs/SplitSigmasDenoise/en.md": "multiplying the total steps by the denoise factor",
            "comfyui_embedded_docs/docs/SplitSigmasDenoise/ru.md": "точка разделения определяется умножением",
            "comfyui_embedded_docs/docs/VpScheduler/en.md": "Variance Preserving (VP)",
            "comfyui_embedded_docs/docs/VpScheduler/ru.md": "сохранением дисперсии (VP)",
            "comfyui_embedded_docs/docs/BetaSamplingScheduler/en.md": "beta scheduling algorithm",
            "comfyui_embedded_docs/docs/BetaSamplingScheduler/ru.md": "параметров alpha и beta",
            "comfyui_embedded_docs/docs/LaplaceScheduler/en.md": "gradually decrease from a maximum to minimum value",
            "comfyui_embedded_docs/docs/LaplaceScheduler/ru.md": "постепенно уменьшаются от максимального до минимального",
        }
        with zipfile.ZipFile(DOCS_WHEEL) as archive:
            for member, marker in members.items():
                self.assertIn(marker, archive.read(member).decode("utf-8"))

    @unittest.skipUnless(WORKFLOW_WHEEL.exists(), "official workflow wheel is absent")
    def test_exhaustive_official_census_widgets_and_topology(self) -> None:
        self.assertEqual(WORKFLOW_WHEEL_SHA256, hashlib.sha256(WORKFLOW_WHEEL.read_bytes()).hexdigest())
        targets = {spec["classType"] for spec in ARTICLE_SPECS.values()}
        records: list[dict[str, Any]] = []
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
                for scope, graph in workflow_graphs(payload):
                    nodes = [node for node in graph.get("nodes", []) if isinstance(node, dict)]
                    by_id = {node.get("id"): node for node in nodes}
                    links = normalized_links(graph)
                    for node in nodes:
                        if node.get("type") in targets:
                            records.append(
                                {
                                    "member": member,
                                    "scope": scope,
                                    "node": node,
                                    "by_id": by_id,
                                    "links": links,
                                }
                            )
        self.assertEqual(512, file_count)
        self.assertEqual(496, root_graph_count)
        self.assertEqual({"BetaSamplingScheduler": 1}, dict(Counter(record["node"]["type"] for record in records)))

        record = records[0]
        self.assertTrue(record["member"].endswith("image_chroma1_radiance_text_to_image.json"))
        self.assertEqual("subgraph:0", record["scope"])
        self.assertEqual([30, 0.4, 0.4], record["node"]["widgets_values"])
        self.assertEqual(0, record["node"]["mode"])
        by_id = record["by_id"]
        links = record["links"]
        beta_id = record["node"]["id"]
        incoming = [link for link in links if link.get("target_id") == beta_id]
        outgoing = [link for link in links if link.get("origin_id") == beta_id]
        self.assertEqual(["ModelSamplingAuraFlow"], [by_id[link["origin_id"]]["type"] for link in incoming])
        self.assertEqual(["SamplerCustomAdvanced"], [by_id[link["target_id"]]["type"] for link in outgoing])
        sampling_id = incoming[0]["origin_id"]
        sampler_id = outgoing[0]["target_id"]
        self.assertEqual([1], by_id[sampling_id]["widgets_values"])
        self.assertEqual("SIGMAS", outgoing[0]["type"])
        self.assertEqual(3, outgoing[0]["target_slot"])
        model_targets = {
            by_id[link["target_id"]]["type"]
            for link in links
            if link.get("origin_id") == sampling_id and link.get("type") == "MODEL"
        }
        self.assertEqual({"CFGGuider", "BetaSamplingScheduler"}, model_targets)
        cfg = next(node for node in by_id.values() if node.get("type") == "CFGGuider")
        sampler_select = next(node for node in by_id.values() if node.get("type") == "KSamplerSelect")
        self.assertEqual([3.5], cfg["widgets_values"])
        self.assertEqual(["euler"], sampler_select["widgets_values"])
        sampler_inputs = {
            link["type"]
            for link in links
            if link.get("target_id") == sampler_id
        }
        self.assertEqual({"NOISE", "GUIDER", "SAMPLER", "SIGMAS", "LATENT"}, sampler_inputs)

    @unittest.skipUnless(SOURCE.exists(), "pinned ComfyUI source checkout is absent")
    def test_safe_exact_source_synthetic_tensor_probe(self) -> None:
        candidates = [
            Path(os.environ.get("TEMP", ""))
            / "nodes-wizard-comfyui-v0.32.0-venv"
            / "Scripts"
            / "python.exe",
            Path(sys.executable),
        ]
        python = next((candidate for candidate in candidates if candidate.exists()), None)
        if python is None:
            self.skipTest("no Python interpreter for exact-source probe")
        result = subprocess.run(
            [str(python), "-X", "utf8", str(SYNTHETIC_PROBE)],
            cwd=catalog.ROOT,
            text=True,
            capture_output=True,
            timeout=120,
            check=False,
        )
        if result.returncode != 0 and python == Path(sys.executable):
            self.skipTest(f"torch/numpy/scipy unavailable for probe: {result.stderr}")
        self.assertEqual(0, result.returncode, result.stderr or result.stdout)
        payload = json.loads(result.stdout.strip().splitlines()[-1])

        split = payload["splitDenoise"]
        self.assertEqual([5.0, 4.0, 3.0], split["halfHigh"])
        self.assertEqual([3.0, 2.0, 0.0], split["halfLow"])
        self.assertEqual([0, 1], split["zeroLengths"])
        self.assertEqual([1, 5], split["fullLengths"])
        self.assertEqual([0, 0], split["emptyLengths"])
        self.assertEqual([0, 1], split["singletonLengths"])
        self.assertEqual([6.0, 5.0, 4.0, 3.0], split["bankersHalfHigh"])
        self.assertTrue(split["sharedStorage"])

        vp = payload["vp"]
        self.assertEqual(5, len(vp["default"]))
        self.assertAlmostEqual(152.1669769, vp["default"][0], places=5)
        self.assertEqual(0.0, vp["default"][-1])
        self.assertEqual(2, len(vp["oneStep"]))
        self.assertEqual([0.0, 0.0], vp["epsZero"][-2:])
        self.assertEqual(1, len(set(vp["epsOne"][:-1])))
        self.assertEqual([0.0] * 5, vp["zeroBeta"])
        self.assertEqual([True, True, True, False, False], vp["overflowIsInf"])

        beta = payload["beta"]
        self.assertEqual([5.0, 4.0, 3.0, 1.0, 0.0], beta["fourSteps"])
        self.assertEqual([5.0, 4.0, 3.0, 2.0, 1.0, 0.0, 0.0], beta["twentyRequested"])
        self.assertEqual([5.0, 0.0], beta["oneStep"])
        self.assertEqual("ValueError", beta["alphaZeroError"])
        self.assertEqual("ValueError", beta["betaZeroError"])

        laplace = payload["laplace"]
        self.assertEqual(5, len(laplace["default"]))
        self.assertAlmostEqual(14.614642, laplace["default"][0], places=5)
        self.assertAlmostEqual(1.0, laplace["default"][2], places=6)
        self.assertAlmostEqual(0.0291675, laplace["default"][-1], places=7)
        self.assertNotEqual(0.0, laplace["default"][-1])
        self.assertEqual([14.614642143249512], laplace["oneStep"])
        self.assertEqual([1.0] * 5, laplace["betaZero"])
        self.assertEqual([2.0] * 5, laplace["reversedBounds"])


if __name__ == "__main__":
    unittest.main()
