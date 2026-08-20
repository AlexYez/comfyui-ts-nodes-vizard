from __future__ import annotations

import hashlib
import json
import math
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
    "core.ideogram4-scheduler": {
        "directory": "ideogram4-scheduler",
        "classType": "Ideogram4Scheduler",
        "module": "comfy_extras.nodes_ideogram4",
        "fingerprint": "sha256:77868508520a318f416104a08d57a672a88c175654495660969ef37ea0b61772",
        "recipe": "recipe.ideogram4-default-schedule",
    },
    "core.flux2-scheduler": {
        "directory": "flux2-scheduler",
        "classType": "Flux2Scheduler",
        "module": "comfy_extras.nodes_flux",
        "fingerprint": "sha256:4225c8f214597383990ad72000ec108cdb4d61af3327b15c5671869c9418df9d",
        "recipe": "recipe.flux2-klein-image-size-schedule",
    },
    "core.ltxv-scheduler": {
        "directory": "ltxv-scheduler",
        "classType": "LTXVScheduler",
        "module": "comfy_extras.nodes_lt",
        "fingerprint": "sha256:3a9ccf123d51f77df10833dd508daf46393b00eef14cc87af0289d56904372df",
        "recipe": "recipe.ltxv-empty-latent-schedule",
    },
}

RECIPE_DIRECTORIES = {
    "recipe.ideogram4-default-schedule": "ideogram4-default-schedule",
    "recipe.flux2-klein-image-size-schedule": "flux2-klein-image-size-schedule",
    "recipe.ltxv-empty-latent-schedule": "ltxv-empty-latent-schedule",
}

EXPECTED_FRAGMENT_NODES = {
    "recipe.ideogram4-default-schedule": [
        ("Ideogram4Scheduler", {"steps": 20, "width": 1024, "height": 1024, "mu": 0.0, "std": 1.75}),
    ],
    "recipe.flux2-klein-image-size-schedule": [
        ("GetImageSize", {}),
        ("Flux2Scheduler", {"steps": 4, "width": 1024, "height": 1024}),
    ],
    "recipe.ltxv-empty-latent-schedule": [
        ("EmptyLTXVLatentVideo", {"width": 768, "height": 512, "length": 97, "batch_size": 1}),
        (
            "LTXVScheduler",
            {"steps": 30, "max_shift": 2.05, "base_shift": 0.95, "stretch": True, "terminal": 0.1},
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
SYNTHETIC_PROBE = Path(__file__).with_name("model_specific_scheduler_synthetic_probe.py")


def article_path(spec: dict[str, Any]) -> Path:
    return catalog.CONTENT / "articles" / "core" / spec["directory"] / "manifest.json"


def recipe_path(recipe_id: str) -> Path:
    return catalog.CONTENT / "recipes" / RECIPE_DIRECTORIES[recipe_id] / "recipe.json"


def all_article_ids() -> set[str]:
    ids: set[str] = set()
    for path in (catalog.CONTENT / "articles").rglob("manifest.json"):
        payload = catalog.load_json(path)
        if isinstance(payload, dict) and isinstance(payload.get("articleId"), str):
            ids.add(payload["articleId"])
    return ids


def runtime_inputs(runtime: dict[str, Any]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for group in ("required", "optional"):
        values = runtime.get("input", {}).get(group, {})
        if isinstance(values, dict):
            result.update(values)
    return result


def normalized_links(graph: dict[str, Any]) -> list[dict[str, Any]]:
    links: list[dict[str, Any]] = []
    for link in graph.get("links", []):
        if isinstance(link, list) and len(link) >= 6:
            links.append(
                {
                    "origin_id": link[1],
                    "origin_slot": link[2],
                    "target_id": link[3],
                    "target_slot": link[4],
                    "type": link[5],
                }
            )
        elif isinstance(link, dict):
            links.append(link)
    return links


def workflow_graphs(payload: dict[str, Any]) -> Iterator[tuple[str, dict[str, Any]]]:
    yield "root", payload
    definitions = payload.get("definitions")
    subgraphs = definitions.get("subgraphs", []) if isinstance(definitions, dict) else []
    for index, subgraph in enumerate(subgraphs):
        if isinstance(subgraph, dict):
            yield f"subgraph:{index}", subgraph


class ModelSpecificSchedulerContentTests(unittest.TestCase):
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
            self.assertEqual(spec["module"], research["node"]["pythonModule"])
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

    def test_runtime_fingerprints_widgets_flags_and_fragment_ports(self) -> None:
        nodes = catalog.object_info_nodes(catalog.load_json(FULL_INVENTORY))
        for article_id, spec in ARTICLE_SPECS.items():
            runtime = dict(nodes[spec["classType"]])
            article = catalog.load_json(article_path(spec))
            self.assertEqual(spec["module"], runtime["python_module"])
            self.assertEqual("model/sampling/schedulers", runtime["category"])
            self.assertEqual(spec["fingerprint"], catalog.schema_fingerprint(spec["classType"], runtime))
            self.assertEqual(spec["fingerprint"], article["editorial"]["schemaHash"])
            self.assertFalse(runtime.get("experimental", False))
            self.assertFalse(runtime.get("deprecated", False))
            self.assertFalse(runtime.get("dev_only", False))
            self.assertFalse(runtime.get("api_node", False))
            self.assertFalse(runtime["is_input_list"])
            self.assertIsNone(runtime.get("search_aliases"))
            self.assertEqual(["SIGMAS"], runtime["output"])

        ideogram = nodes["Ideogram4Scheduler"]
        self.assertEqual("Ideogram 4 Scheduler", ideogram["display_name"])
        self.assertEqual({"default": 20, "min": 1, "max": 200}, ideogram["input"]["required"]["steps"][1])
        self.assertEqual(
            {"default": 1024, "min": 256, "max": 8192, "step": 16},
            ideogram["input"]["required"]["width"][1],
        )
        self.assertEqual(
            {"default": 1.75, "min": 0.1, "max": 5.0, "step": 0.05},
            ideogram["input"]["required"]["std"][1],
        )

        flux = nodes["Flux2Scheduler"]
        self.assertEqual({"default": 20, "min": 1, "max": 4096}, flux["input"]["required"]["steps"][1])
        self.assertEqual(
            {"default": 1024, "min": 16, "max": 16384, "step": 1},
            flux["input"]["required"]["height"][1],
        )

        ltx = nodes["LTXVScheduler"]
        self.assertEqual("LATENT", ltx["input"]["optional"]["latent"][0])
        self.assertEqual(
            {"tooltip": "Stretch the sigmas to be in the range [terminal, 1].", "advanced": True, "default": True},
            ltx["input"]["required"]["stretch"][1],
        )
        self.assertEqual(
            {
                "tooltip": "The terminal value of the sigmas after stretching.",
                "advanced": True,
                "default": 0.1,
                "min": 0.0,
                "max": 0.99,
                "step": 0.01,
            },
            ltx["input"]["required"]["terminal"][1],
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
    def test_exact_source_math_shapes_and_replacement_absence(self) -> None:
        ideogram = (SOURCE / "comfy_extras" / "nodes_ideogram4.py").read_text(encoding="utf-8")
        flux = (SOURCE / "comfy_extras" / "nodes_flux.py").read_text(encoding="utf-8")
        ltx = (SOURCE / "comfy_extras" / "nodes_lt.py").read_text(encoding="utf-8")
        nested = (SOURCE / "comfy" / "nested_tensor.py").read_text(encoding="utf-8")

        self.assertIn("0.5 * math.log((width * height) / (512 * 512))", ideogram)
        self.assertIn("torch.special.ndtri(u)", ideogram)
        self.assertIn("torch.linspace(0.0, 1.0, num_steps + 1, dtype=torch.float64)", ideogram)
        self.assertIn("sigmas[-1] = 0.0", ideogram)

        self.assertIn("seq_len = (width * height / (16 * 16))", flux)
        self.assertIn("get_schedule(steps, round(seq_len))", flux)
        self.assertIn("if image_seq_len > 4300:", flux)
        self.assertIn("mu = a * num_steps + b", flux)
        self.assertIn("torch.linspace(1, 0, num_steps + 1)", flux)

        self.assertIn('tokens = math.prod(latent["samples"].shape[2:])', ltx)
        self.assertIn("tokens = 4096", ltx)
        self.assertIn("sigmas = torch.linspace(1.0, 0.0, steps + 1)", ltx)
        self.assertIn("scale_factor = one_minus_z[-1] / (1.0 - terminal)", ltx)
        self.assertIn("sigmas[non_zero_mask] = stretched", ltx)
        self.assertIn("torch.zeros([batch_size, 128, ((length - 1) // 8) + 1, height // 32, width // 32]", ltx)
        self.assertIn("return self.tensors[0].shape", nested)

        replacements_text = json.dumps(catalog.load_json(REPLACEMENTS), sort_keys=True)
        for spec in ARTICLE_SPECS.values():
            self.assertNotIn(spec["classType"], replacements_text)

    @unittest.skipUnless(DOCS_WHEEL.exists(), "pinned embedded docs wheel is absent")
    def test_pinned_embedded_docs_are_present_and_bounded(self) -> None:
        self.assertEqual(DOCS_WHEEL_SHA256, hashlib.sha256(DOCS_WHEEL.read_bytes()).hexdigest())
        members = {
            "comfyui_embedded_docs/docs/Ideogram4Scheduler/en.md": "length equal to `steps + 1`",
            "comfyui_embedded_docs/docs/Ideogram4Scheduler/ru.md": "последнее значение устанавливается равным 0.0",
            "comfyui_embedded_docs/docs/Flux2Scheduler/en.md": "dimensions of the target image",
            "comfyui_embedded_docs/docs/Flux2Scheduler/ru.md": "размеров целевого изображения",
            "comfyui_embedded_docs/docs/LTXVScheduler/en.md": "default token count of 4096",
            "comfyui_embedded_docs/docs/LTXVScheduler/ru.md": "значение количества токенов по умолчанию — 4096",
        }
        with zipfile.ZipFile(DOCS_WHEEL) as archive:
            for member, marker in members.items():
                self.assertIn(marker.lower(), archive.read(member).decode("utf-8").lower())

    @unittest.skipUnless(WORKFLOW_WHEEL.exists(), "official workflow wheel is absent")
    def test_exhaustive_official_census_presets_widgets_and_topology(self) -> None:
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
                    graph_nodes = [node for node in graph.get("nodes", []) if isinstance(node, dict)]
                    by_id = {node.get("id"): node for node in graph_nodes}
                    links = normalized_links(graph)
                    for node in graph_nodes:
                        if node.get("type") in targets:
                            records.append(
                                {
                                    "member": member,
                                    "scope": scope,
                                    "node": node,
                                    "nodes": graph_nodes,
                                    "by_id": by_id,
                                    "links": links,
                                }
                            )
        self.assertEqual(512, file_count)
        self.assertEqual(496, root_graph_count)
        self.assertEqual(
            {"Flux2Scheduler": 17, "LTXVScheduler": 7, "Ideogram4Scheduler": 2},
            dict(Counter(record["node"]["type"] for record in records)),
        )

        ideogram = [record for record in records if record["node"]["type"] == "Ideogram4Scheduler"]
        self.assertEqual(2, len({record["member"] for record in ideogram}))
        self.assertTrue(all(record["scope"].startswith("subgraph:") for record in ideogram))
        self.assertEqual({(20, 1024, 1024, 0.5, 1.75)}, {tuple(record["node"]["widgets_values"]) for record in ideogram})
        expected_presets = {
            "Quality": {"num_steps": 48, "mu": 0.0, "std": 1.5, "preset_id": "V4_QUALITY_48"},
            "Default": {"num_steps": 20, "mu": 0.0, "std": 1.75, "preset_id": "V4_DEFAULT_20"},
            "Turbo": {"num_steps": 12, "mu": 0.5, "std": 1.75, "preset_id": "V4_TURBO_12"},
        }
        for record in ideogram:
            node_id = record["node"]["id"]
            incoming = [link for link in record["links"] if link.get("target_id") == node_id]
            outgoing = [link for link in record["links"] if link.get("origin_id") == node_id]
            self.assertEqual(Counter({"ComfyMathExpression": 2, "ComfyNumberConvert": 3}), Counter(record["by_id"][link["origin_id"]]["type"] for link in incoming))
            self.assertEqual(["SamplerCustomAdvanced"], [record["by_id"][link["target_id"]]["type"] for link in outgoing])
            expressions = [
                node["widgets_values"][0]
                for node in record["nodes"]
                if node.get("type") == "ComfyMathExpression"
                and node.get("widgets_values") == ["max(((a + 15) // 16) * 16, 256)"]
            ]
            self.assertEqual(2, len(expressions))
            preset_node = next(
                node
                for node in record["nodes"]
                if node.get("type") == "JsonExtractString"
                and node.get("widgets_values")
                and isinstance(node["widgets_values"][0], str)
                and '"Quality"' in node["widgets_values"][0]
            )
            self.assertEqual(expected_presets, json.loads(preset_node["widgets_values"][0]))

        flux = [record for record in records if record["node"]["type"] == "Flux2Scheduler"]
        self.assertEqual(11, len({record["member"] for record in flux}))
        self.assertEqual(Counter({"subgraph": 16, "root": 1}), Counter(record["scope"].split(":")[0] for record in flux))
        self.assertEqual(
            Counter({(20, 1024, 1024): 9, (4, 1024, 1024): 6, (20, 1248, 832): 2}),
            Counter(tuple(record["node"]["widgets_values"]) for record in flux),
        )
        for record in flux:
            node_id = record["node"]["id"]
            outgoing = [link for link in record["links"] if link.get("origin_id") == node_id]
            self.assertEqual(["SamplerCustomAdvanced"], [record["by_id"][link["target_id"]]["type"] for link in outgoing])
        flux_root = next(record for record in flux if record["scope"] == "root")
        self.assertTrue(flux_root["member"].endswith("image_flux2_klein_9b_kv_image_edit.json"))
        root_incoming = [link for link in flux_root["links"] if link.get("target_id") == flux_root["node"]["id"]]
        self.assertEqual(["GetImageSize", "GetImageSize"], [flux_root["by_id"][link["origin_id"]]["type"] for link in root_incoming])
        self.assertEqual([4, 1024, 1024], flux_root["node"]["widgets_values"])

        ltx = [record for record in records if record["node"]["type"] == "LTXVScheduler"]
        self.assertEqual(7, len({record["member"] for record in ltx}))
        self.assertEqual(Counter({"subgraph": 5, "root": 2}), Counter(record["scope"].split(":")[0] for record in ltx))
        self.assertEqual(
            Counter({(30, 2.05, 0.95, True, 0.1): 2, (20, 2.05, 0.95, True, 0.1): 4, (12, 2.05, 0.95, True, 0.1): 1}),
            Counter(tuple(record["node"]["widgets_values"]) for record in ltx),
        )
        for record in ltx:
            node_id = record["node"]["id"]
            incoming = [link for link in record["links"] if link.get("target_id") == node_id]
            outgoing = [link for link in record["links"] if link.get("origin_id") == node_id]
            self.assertEqual(1, len(incoming))
            self.assertEqual("LATENT", incoming[0]["type"])
            if record["scope"] == "root":
                self.assertIn(record["by_id"][incoming[0]["origin_id"]]["type"], {"EmptyLTXVLatentVideo", "LTXVImgToVideo"})
                self.assertEqual(["SamplerCustom"], [record["by_id"][link["target_id"]]["type"] for link in outgoing])
            else:
                self.assertEqual("LTXVConcatAVLatent", record["by_id"][incoming[0]["origin_id"]]["type"])
                self.assertEqual(["SamplerCustomAdvanced"], [record["by_id"][link["target_id"]]["type"] for link in outgoing])

    @unittest.skipUnless(SOURCE.exists(), "pinned ComfyUI source checkout is absent")
    def test_safe_exact_source_model_free_probe(self) -> None:
        candidates = [
            Path(os.environ.get("TEMP", "")) / "nodes-wizard-comfyui-v0.32.0-venv" / "Scripts" / "python.exe",
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
            self.skipTest(f"torch unavailable for probe: {result.stderr}")
        self.assertEqual(0, result.returncode, result.stderr or result.stdout)
        payload = json.loads(result.stdout.strip().splitlines()[-1])

        ideogram = payload["ideogram4"]
        self.assertEqual("torch.float32", ideogram["dtype"])
        self.assertEqual(5, len(ideogram["defaultFour"]))
        self.assertAlmostEqual(0.9998766, ideogram["defaultFour"][0], places=6)
        self.assertEqual(0.0, ideogram["defaultFour"][-1])
        self.assertTrue(ideogram["areaOrderOnly"])
        self.assertGreater(ideogram["highArea"][2], ideogram["lowArea"][2])
        self.assertEqual(2, len(ideogram["oneStep"]))

        flux = payload["flux2"]
        self.assertEqual([1.0, 0.9673840403556824, 0.9081438779830933, 0.7671999335289001, 0.0], flux["defaultFour"])
        self.assertTrue(flux["areaOrderOnly"])
        self.assertNotEqual(flux["muAt4096ForSteps4_20_200"][0], flux["muAt4096ForSteps4_20_200"][1])
        self.assertGreater(flux["muAt4300And4301For20"][0], flux["muAt4300And4301For20"][1])
        self.assertEqual(1, len(set(flux["muAboveThresholdForSteps4_20_200"])))
        self.assertEqual([True] * 5, flux["maxResolutionIsNan"])

        ltx = payload["ltxv"]
        self.assertEqual(5, len(ltx["defaultFourStretched"]))
        self.assertAlmostEqual(0.1, ltx["defaultFourStretched"][-2], places=6)
        self.assertEqual(0.0, ltx["defaultFourStretched"][-1])
        self.assertTrue(ltx["latent4096MatchesFallback"])
        self.assertNotEqual(ltx["latent768"], ltx["defaultFourStretched"])
        self.assertEqual([0.0, 0.0], ltx["terminalZero"][-2:])
        self.assertAlmostEqual(0.1, ltx["oneStepStretched"][0], places=6)
        self.assertTrue(math.isnan(ltx["oneStepZeroShift"][0]))
        self.assertEqual([True, True, True, True, False], ltx["extremeIsNan"])
        self.assertTrue(ltx["equalShiftsIgnoreLatentSize"])


if __name__ == "__main__":
    unittest.main()
