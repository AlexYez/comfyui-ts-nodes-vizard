from __future__ import annotations

import hashlib
import json
import re
import unittest
import zipfile
from collections import Counter
from pathlib import Path
from typing import Any, Iterator

from tools import catalog
from tools.tests.model_scheduler_synthetic_probe import run_probe


ARTICLE_SPECS = {
    "core.sd-turbo-scheduler": {
        "directory": "sd-turbo-scheduler",
        "classType": "SDTurboScheduler",
        "module": "comfy_extras.nodes_custom_sampler",
        "fingerprint": "sha256:00c82a397be62412fed35aba3218bd010445a93d31ed828861a533b5ccf5751d",
        "recipe": "recipe.sdxl-turbo-custom-sampling",
    },
    "core.align-your-steps-scheduler": {
        "directory": "align-your-steps-scheduler",
        "classType": "AlignYourStepsScheduler",
        "module": "comfy_extras.nodes_align_your_steps",
        "fingerprint": "sha256:ac84ba52e97e75b0c5c6ab1d730d14b4650dd86d79fa9a470002696b6c2e770a",
        "recipe": "recipe.ays-sdxl-ten-step-sampling",
    },
    "core.gits-scheduler": {
        "directory": "gits-scheduler",
        "classType": "GITSScheduler",
        "module": "comfy_extras.nodes_gits",
        "fingerprint": "sha256:bb12e75f30f05bd4294356734f698ce8440d2ecd30fcb4784619625f9cc4bcc2",
        "recipe": "recipe.gits-ten-step-sampling",
    },
    "core.optimal-steps-scheduler": {
        "directory": "optimal-steps-scheduler",
        "classType": "OptimalStepsScheduler",
        "module": "comfy_extras.nodes_optimalsteps",
        "fingerprint": "sha256:38a77f9c4b39b6a6babaa6d114a1de6dd3d922512ed9c86b57acd89b29a88598",
        "recipe": "recipe.optimal-wan-twenty-step-sampling",
    },
}

RECIPE_DIRECTORIES = {
    "recipe.sdxl-turbo-custom-sampling": "sdxl-turbo-custom-sampling",
    "recipe.ays-sdxl-ten-step-sampling": "ays-sdxl-ten-step-sampling",
    "recipe.gits-ten-step-sampling": "gits-ten-step-sampling",
    "recipe.optimal-wan-twenty-step-sampling": "optimal-wan-twenty-step-sampling",
}

EXPECTED_SETTINGS = {
    "recipe.sdxl-turbo-custom-sampling": ("SDTurboScheduler", {"steps": 1, "denoise": 1.0}),
    "recipe.ays-sdxl-ten-step-sampling": (
        "AlignYourStepsScheduler",
        {"model_type": "SDXL", "steps": 10, "denoise": 1.0},
    ),
    "recipe.gits-ten-step-sampling": (
        "GITSScheduler",
        {"coeff": 1.2, "steps": 10, "denoise": 1.0},
    ),
    "recipe.optimal-wan-twenty-step-sampling": (
        "OptimalStepsScheduler",
        {"model_type": "Wan", "steps": 20, "denoise": 1.0},
    ),
}

SOURCE = catalog.ROOT / ".comfyui-source-0.32.0"
INVENTORY = catalog.CONTENT / "runtime" / "comfyui-0.32.0.object-info.json"
REPLACEMENTS = catalog.CONTENT / "runtime" / "comfyui-0.32.0.node-replacements.json"
WORKFLOW_WHEEL = catalog.ROOT / ".upstream-cache" / "comfyui_workflow_templates_json-0.1.42-py3-none-any.whl"
WORKFLOW_SHA256 = "242982d65e1c51ca03d892bc1009bb6843f457e7dfc0c20afe6438770b7a14a3"
DOCS_WHEEL = catalog.ROOT / ".upstream-cache" / "comfyui_embedded_docs-0.5.9-py3-none-any.whl"
DOCS_SHA256 = "30afae432a71c96aa59421d0f37388c66ff6572b8cbeee8ff045e4d5f84f896c"
TARGET_TYPES = {spec["classType"] for spec in ARTICLE_SPECS.values()}


def _all_article_ids() -> set[str]:
    ids: set[str] = set()
    for path in (catalog.CONTENT / "articles").rglob("manifest.json"):
        payload = catalog.load_json(path)
        if isinstance(payload, dict) and isinstance(payload.get("articleId"), str):
            ids.add(payload["articleId"])
    return ids


def _graph_records(payload: dict[str, Any], member: str) -> Iterator[dict[str, Any]]:
    for node in payload.get("nodes", []):
        if isinstance(node, dict):
            yield {"member": member, "scope": "root", "node": node}
    definitions = payload.get("definitions")
    subgraphs = definitions.get("subgraphs", []) if isinstance(definitions, dict) else []
    for subgraph in subgraphs:
        if not isinstance(subgraph, dict):
            continue
        for node in subgraph.get("nodes", []):
            if isinstance(node, dict):
                yield {"member": member, "scope": "subgraph", "node": node}


class ModelSchedulerContentTests(unittest.TestCase):
    def test_articles_recipes_research_and_russian_contract(self) -> None:
        article_schema = catalog.load_json(catalog.CONTENT / "schemas" / "article.schema.v1.json")
        recipe_schema = catalog.load_json(catalog.CONTENT / "schemas" / "recipe.schema.v1.json")
        fragment_schema = catalog.load_json(catalog.CONTENT / "schemas" / "recipe-fragment.schema.v1.json")
        research_schema = catalog.load_json(catalog.CONTENT / "schemas" / "article-research.schema.v1.json")
        article_ids = _all_article_ids()
        errors: list[str] = []

        for article_id, spec in ARTICLE_SPECS.items():
            path = catalog.CONTENT / "articles" / "core" / spec["directory"] / "manifest.json"
            article = catalog.load_json(path)
            self.assertEqual([], catalog.json_schema_errors(article, article_schema))
            catalog.validate_article(path, article, errors)
            self.assertEqual(article_id, article["articleId"])
            self.assertEqual("draft", article["status"])
            self.assertEqual("in_review", article["editorial"]["state"])
            self.assertEqual(spec["fingerprint"], article["editorial"]["schemaHash"])
            self.assertIn(spec["recipe"], [asset["id"] for asset in article["assets"]])
            self.assertFalse(article["experimental"])

            relations = article["relations"]
            targets = list(relations["related"]) + list(relations["alternatives"])
            if relations["replacedBy"] is not None:
                targets.append(relations["replacedBy"])
            self.assertTrue(set(targets).issubset(article_ids), (article_id, set(targets) - article_ids))

            body = (path.parent / article["body"]).read_text(encoding="utf-8")
            headings = [
                heading
                for heading in re.findall(r"^## (.+)$", body, flags=re.MULTILINE)
                if heading != "Источники"
            ]
            self.assertEqual(10, len(headings), (article_id, headings))
            self.assertIn("Редактор пока не проверил материал вручную", body)
            self.assertNotIn("\ufffd", body)
            self.assertNotRegex(
                body.lower(),
                r"важно отметить|стоит отметить|в современном мире|революционн|"
                r"данная нода|давайте разбер|подводя итог|мощный инструмент|"
                r"не просто .{0,80}, а",
            )

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
            self.assertEqual("in_review", recipe["editorial"]["state"])
            self.assertNotIn("workflow", recipe)

            fragment_path = path.parent / recipe["fragment"]["path"]
            fragment = catalog.load_json(fragment_path)
            self.assertEqual([], catalog.json_schema_errors(fragment, fragment_schema))
            catalog.validate_fragment(fragment_path, fragment, recipe_errors)
            expected_type, expected_settings = EXPECTED_SETTINGS[recipe_id]
            schedule = next(node for node in fragment["nodes"] if node["classType"] == expected_type)
            self.assertEqual(expected_settings, schedule["settings"])
            self.assertTrue(
                any(
                    link["from"] == schedule["ref"]
                    and link["output"] == "SIGMAS"
                    and link["input"] == "sigmas"
                    for link in fragment["connections"]
                )
            )

        self.assertEqual([], recipe_errors)

    def test_runtime_identity_ports_constraints_and_replacements(self) -> None:
        inventory = catalog.load_json(INVENTORY)
        expected_orders = {
            "SDTurboScheduler": ["model", "steps", "denoise"],
            "AlignYourStepsScheduler": ["model_type", "steps", "denoise"],
            "GITSScheduler": ["coeff", "steps", "denoise"],
            "OptimalStepsScheduler": ["model_type", "steps", "denoise"],
        }
        for spec in ARTICLE_SPECS.values():
            definition = inventory[spec["classType"]]
            self.assertEqual(spec["module"], definition["python_module"])
            self.assertEqual("model/sampling/schedulers", definition["category"])
            self.assertEqual(expected_orders[spec["classType"]], definition["input_order"]["required"])
            self.assertEqual(["SIGMAS"], definition["output"])
            self.assertFalse(definition.get("experimental", False))
            self.assertFalse(definition.get("deprecated", False))
            self.assertFalse(definition.get("api_node", False))
            self.assertEqual(spec["fingerprint"], catalog.schema_fingerprint(spec["classType"], definition))

        self.assertEqual((1, 1, 10), tuple(inventory["SDTurboScheduler"]["input"]["required"]["steps"][1][key] for key in ("default", "min", "max")))
        self.assertEqual(["SD1", "SDXL", "SVD"], inventory["AlignYourStepsScheduler"]["input"]["required"]["model_type"][1]["options"])
        self.assertEqual((1.2, 0.8, 1.5, 0.05, True), tuple(inventory["GITSScheduler"]["input"]["required"]["coeff"][1][key] for key in ("default", "min", "max", "step", "advanced")))
        self.assertEqual((10, 2, 1000), tuple(inventory["GITSScheduler"]["input"]["required"]["steps"][1][key] for key in ("default", "min", "max")))
        self.assertEqual(["FLUX", "Wan", "Chroma"], inventory["OptimalStepsScheduler"]["input"]["required"]["model_type"][1]["options"])
        self.assertEqual((20, 3, 1000), tuple(inventory["OptimalStepsScheduler"]["input"]["required"]["steps"][1][key] for key in ("default", "min", "max")))

        replacements = catalog.load_json(REPLACEMENTS)
        serialized = json.dumps(replacements, ensure_ascii=False)
        for class_type in TARGET_TYPES:
            self.assertNotIn(class_type, replacements)
            self.assertNotIn(f'"new_node_id": "{class_type}"', serialized)

    def test_exact_source_probe_without_models(self) -> None:
        result = run_probe(SOURCE)
        self.assertEqual([11, 21, 41], result["optimal"]["nativeLengths"])
        self.assertEqual(13, result["ays"]["interpolatedLength"])
        self.assertEqual(22, result["gits"]["interpolatedLength"])
        self.assertTrue(result["gits"]["missingCoeffRejected"])
        self.assertEqual([0.0], result["sdTurbo"]["denoise0"])

    def test_pinned_source_and_embedded_docs(self) -> None:
        custom = (SOURCE / "comfy_extras" / "nodes_custom_sampler.py").read_text(encoding="utf-8")
        ays = (SOURCE / "comfy_extras" / "nodes_align_your_steps.py").read_text(encoding="utf-8")
        gits = (SOURCE / "comfy_extras" / "nodes_gits.py").read_text(encoding="utf-8")
        optimal = (SOURCE / "comfy_extras" / "nodes_optimalsteps.py").read_text(encoding="utf-8")
        self.assertIn("start_step = 10 - int(10 * denoise)", custom)
        self.assertIn("torch.flip(torch.arange(1, 11) * 100 - 1", custom)
        self.assertIn('"SDXL":[14.6146412293, 6.3184485287', ays)
        self.assertIn("total_steps = round(steps * denoise)", ays)
        self.assertIn("NOISE_LEVELS[round(coeff, 2)][steps-2][:]", gits)
        self.assertIn("if steps <= 20:", gits)
        self.assertIn('"Wan":[1.0, 0.997, 0.995', optimal)
        self.assertIn("if (steps + 1) != len(sigmas):", optimal)

        self.assertEqual(DOCS_SHA256, hashlib.sha256(DOCS_WHEEL.read_bytes()).hexdigest())
        with zipfile.ZipFile(DOCS_WHEEL) as archive:
            names = set(archive.namelist())
            docs_directories = {
                "SDTurboScheduler": "SdTurboScheduler",
                "AlignYourStepsScheduler": "AlignYourStepsScheduler",
                "GITSScheduler": "GITSScheduler",
                "OptimalStepsScheduler": "OptimalStepsScheduler",
            }
            for class_type in TARGET_TYPES:
                for locale in ("en", "ru"):
                    self.assertIn(
                        f"comfyui_embedded_docs/docs/{docs_directories[class_type]}/{locale}.md",
                        names,
                    )

    def test_workflow_wheel_census_and_exact_sdxl_turbo_case(self) -> None:
        self.assertEqual(WORKFLOW_SHA256, hashlib.sha256(WORKFLOW_WHEEL.read_bytes()).hexdigest())
        records: list[dict[str, Any]] = []
        root_graphs = 0
        subgraphs = 0
        json_members = 0
        turbo_payload: dict[str, Any] | None = None

        with zipfile.ZipFile(WORKFLOW_WHEEL) as archive:
            self.assertIsNone(archive.testzip())
            for member in archive.namelist():
                if not member.endswith(".json") or "/templates/" not in member:
                    continue
                json_members += 1
                payload = json.loads(archive.read(member))
                if not isinstance(payload, dict) or not isinstance(payload.get("nodes"), list):
                    continue
                root_graphs += 1
                definitions = payload.get("definitions")
                if isinstance(definitions, dict) and isinstance(definitions.get("subgraphs"), list):
                    subgraphs += len(definitions["subgraphs"])
                if Path(member).name == "sdxlturbo_example.json":
                    turbo_payload = payload
                for record in _graph_records(payload, member):
                    if record["node"].get("type") in TARGET_TYPES:
                        records.append(record)

        self.assertEqual((512, 496, 272), (json_members, root_graphs, subgraphs))
        expected = {
            "SDTurboScheduler": Counter({"root": 1}),
            "AlignYourStepsScheduler": Counter(),
            "GITSScheduler": Counter(),
            "OptimalStepsScheduler": Counter(),
        }
        for class_type, scopes in expected.items():
            actual = Counter(record["scope"] for record in records if record["node"]["type"] == class_type)
            self.assertEqual(scopes, actual, class_type)

        self.assertIsNotNone(turbo_payload)
        assert turbo_payload is not None
        self.assertEqual("bf11bf13-0fba-4b6b-9a8d-1680bf10cb09", turbo_payload["id"])
        by_id = {node["id"]: node for node in turbo_payload["nodes"]}
        links = {link[0]: link for link in turbo_payload["links"]}
        self.assertEqual(("CheckpointLoaderSimple", ["sd_xl_turbo_1.0_fp16.safetensors"]), (by_id[20]["type"], by_id[20]["widgets_values"]))
        self.assertEqual(("KSamplerSelect", ["euler_ancestral"]), (by_id[14]["type"], by_id[14]["widgets_values"]))
        self.assertEqual(("SDTurboScheduler", [1, 1]), (by_id[22]["type"], by_id[22]["widgets_values"]))
        self.assertEqual(("SamplerCustom", [True, 0, "fixed", 1]), (by_id[13]["type"], by_id[13]["widgets_values"]))
        self.assertEqual([45, 20, 0, 22, 0, "MODEL"], links[45])
        self.assertEqual([49, 22, 0, 13, 4, "SIGMAS"], links[49])
        self.assertEqual([18, 14, 0, 13, 3, "SAMPLER"], links[18])


if __name__ == "__main__":
    unittest.main()
