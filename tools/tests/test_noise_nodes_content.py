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


ARTICLE_SPECS: dict[str, dict[str, Any]] = {
    "core.random-noise": {
        "directory": "random-noise",
        "classType": "RandomNoise",
        "module": "comfy_extras.nodes_custom_sampler",
        "fingerprint": "sha256:1451edf7ca4cef402c40f86a32f52cfde4fa3c3bfaedb93f21bb3cc0c79d52c3",
        "experimental": False,
        "recipes": {"recipe.random-noise-custom-sampling", "recipe.add-model-scaled-noise"},
    },
    "core.disable-noise": {
        "directory": "disable-noise",
        "classType": "DisableNoise",
        "module": "comfy_extras.nodes_custom_sampler",
        "fingerprint": "sha256:f30a443d01f3075f47945cfdbbca18bb066114be10660320571ec0ec7ec303fd",
        "experimental": False,
        "recipes": {"recipe.zero-noise-custom-sampling"},
    },
    "core.add-noise": {
        "directory": "add-noise",
        "classType": "AddNoise",
        "module": "comfy_extras.nodes_custom_sampler",
        "fingerprint": "sha256:c78bb29edca7223de21574f66a137791303a72f3fd2fb1056d2e2e3a1b22926f",
        "experimental": True,
        "recipes": {"recipe.add-model-scaled-noise"},
    },
    "core.model-noise-scale": {
        "directory": "model-noise-scale",
        "classType": "ModelNoiseScale",
        "module": "comfy_extras.nodes_model_advanced",
        "fingerprint": "sha256:aabc5991d8996af3f88ac4ed83f2783325d7be392f6bb4ff3cc3e38e6466f4aa",
        "experimental": False,
        "recipes": {"recipe.hidream-o1-noise-scale"},
    },
}

RECIPE_DIRECTORIES = {
    "recipe.random-noise-custom-sampling": "random-noise-custom-sampling",
    "recipe.zero-noise-custom-sampling": "zero-noise-custom-sampling",
    "recipe.add-model-scaled-noise": "add-model-scaled-noise",
    "recipe.hidream-o1-noise-scale": "hidream-o1-noise-scale",
}

EXPECTED_FRAGMENT_NODES = {
    "recipe.random-noise-custom-sampling": [
        ("RandomNoise", {"noise_seed": 42}),
        ("SamplerCustomAdvanced", {}),
    ],
    "recipe.zero-noise-custom-sampling": [
        ("DisableNoise", {}),
        ("SamplerCustomAdvanced", {}),
    ],
    "recipe.add-model-scaled-noise": [
        ("RandomNoise", {"noise_seed": 42}),
        ("AddNoise", {}),
    ],
    "recipe.hidream-o1-noise-scale": [
        ("ModelNoiseScale", {"noise_scale": 8.0}),
        ("BasicScheduler", {"scheduler": "normal", "steps": 40, "denoise": 1.0}),
    ],
}

INVENTORY = catalog.CONTENT / "runtime" / "comfyui-0.32.0.object-info.json"
SOURCE = catalog.ROOT / ".comfyui-source-0.32.0"
REPLACEMENTS = catalog.CONTENT / "runtime" / "comfyui-0.32.0.node-replacements.json"
WORKFLOW_WHEEL = catalog.ROOT / ".upstream-cache" / "comfyui_workflow_templates_json-0.1.42-py3-none-any.whl"
WORKFLOW_SHA = "242982d65e1c51ca03d892bc1009bb6843f457e7dfc0c20afe6438770b7a14a3"
DOCS_WHEEL = catalog.ROOT / ".upstream-cache" / "comfyui_embedded_docs-0.5.9-py3-none-any.whl"
DOCS_SHA = "30afae432a71c96aa59421d0f37388c66ff6572b8cbeee8ff045e4d5f84f896c"
PROBE = Path(__file__).with_name("noise_nodes_synthetic_probe.py")


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


def normalized_link(link: Any) -> dict[str, Any]:
    if isinstance(link, list):
        return {
            "id": link[0], "origin_id": link[1], "origin_slot": link[2],
            "target_id": link[3], "target_slot": link[4], "type": link[5],
        }
    if isinstance(link, dict):
        return link
    raise AssertionError(link)


def graph_records(payload: dict[str, Any], member: str) -> Iterator[dict[str, Any]]:
    if isinstance(payload.get("nodes"), list):
        for node in payload["nodes"]:
            if isinstance(node, dict):
                yield {"member": member, "scope": "root", "node": node, "graph": payload}
    definitions = payload.get("definitions")
    subgraphs = definitions.get("subgraphs", []) if isinstance(definitions, dict) else []
    for index, graph in enumerate(subgraphs):
        if not isinstance(graph, dict):
            continue
        for node in graph.get("nodes", []):
            if isinstance(node, dict):
                yield {"member": member, "scope": f"subgraph:{index}", "node": node, "graph": graph}


class NoiseNodesContentTests(unittest.TestCase):
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
            self.assertEqual("draft", article["status"])
            self.assertEqual("in_review", article["editorial"]["state"])
            self.assertEqual(spec["module"], article["runtimeIdentity"]["pythonModule"])
            self.assertEqual([], article["runtimeIdentity"]["aliases"])
            self.assertEqual(spec["experimental"], article["experimental"])
            self.assertEqual(spec["fingerprint"], article["editorial"]["schemaHash"])
            self.assertEqual(
                spec["recipes"],
                {asset["id"] for asset in article["assets"] if asset["type"] == "recipe"},
            )
            targets = set(article["relations"]["related"] + article["relations"]["alternatives"])
            self.assertTrue(targets.issubset(article_ids))
            body = path.parent / article["body"]
            self.assertEqual(10, len(re.findall(r"^## .+$", body.read_text(encoding="utf-8"), re.MULTILINE)))
            texts.append(body)

            research = catalog.load_json(catalog.CONTENT / "research" / "reviews" / f"{article_id}.json")
            self.assertEqual([], catalog.json_schema_errors(research, schemas["research"]))
            self.assertEqual("fact_checked", research["state"])
            self.assertEqual("automated_assisted", research["reviewMode"])
            self.assertTrue(research["checks"]["exampleSchemaValidated"])
            self.assertFalse(research["checks"]["exampleExecuted"])
            self.assertTrue(research["knownGaps"])

        for recipe_id in RECIPE_DIRECTORIES:
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
            self.assertEqual(
                EXPECTED_FRAGMENT_NODES[recipe_id],
                [(node["classType"], node["settings"]) for node in fragment["nodes"]],
            )
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

    def test_runtime_contracts_fingerprints_and_fragment_types(self) -> None:
        inventory = catalog.load_json(INVENTORY)
        for spec in ARTICLE_SPECS.values():
            runtime = inventory[spec["classType"]]
            self.assertEqual(spec["module"], runtime["python_module"])
            self.assertEqual(spec["fingerprint"], catalog.schema_fingerprint(spec["classType"], runtime))
            self.assertEqual(spec["experimental"], bool(runtime.get("experimental", False)))
            self.assertFalse(runtime.get("deprecated", False))

        self.assertEqual([], inventory["DisableNoise"]["input_order"]["required"])
        self.assertEqual(["NOISE"], inventory["DisableNoise"]["output"])
        seed = inventory["RandomNoise"]["input"]["required"]["noise_seed"]
        self.assertEqual("INT", seed[0])
        self.assertEqual((0, 0, 18446744073709551615, True), tuple(seed[1][key] for key in ("default", "min", "max", "control_after_generate")))
        self.assertEqual(["model", "noise", "sigmas", "latent_image"], inventory["AddNoise"]["input_order"]["required"])
        scale = inventory["ModelNoiseScale"]["input"]["required"]["noise_scale"]
        self.assertEqual((1.0, 0.0, 64.0, 0.01), tuple(scale[1][key] for key in ("default", "min", "max", "step")))

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
                source_index = source["output_name"].index(link["output"])
                self.assertEqual(source["output"][source_index], target["input"]["required"][link["input"]][0])

    @unittest.skipUnless(SOURCE.exists(), "pinned ComfyUI source checkout is absent")
    def test_pinned_source_semantics_and_replacement_absence(self) -> None:
        custom = (SOURCE / "comfy_extras" / "nodes_custom_sampler.py").read_text(encoding="utf-8")
        sample = (SOURCE / "comfy" / "sample.py").read_text(encoding="utf-8")
        advanced = (SOURCE / "comfy_extras" / "nodes_model_advanced.py").read_text(encoding="utf-8")
        sampling = (SOURCE / "comfy" / "model_sampling.py").read_text(encoding="utf-8")
        k_sampling = (SOURCE / "comfy" / "k_diffusion" / "sampling.py").read_text(encoding="utf-8")
        supported = (SOURCE / "comfy" / "supported_models.py").read_text(encoding="utf-8")

        self.assertIn('return torch.zeros(latent_image.shape', custom)
        self.assertIn('batch_inds = input_latent["batch_index"]', custom)
        self.assertIn('return comfy.sample.prepare_noise(latent_image, self.seed, batch_inds)', custom)
        self.assertIn('if len(sigmas) == 0:', custom)
        self.assertIn('scale = torch.abs(sigmas[0] - sigmas[-1])', custom)
        self.assertIn('if torch.count_nonzero(latent_image) > 0:', custom)
        self.assertIn('noisy = torch.nan_to_num(noisy', custom)
        self.assertIn('unique_inds, inverse = np.unique(noise_inds, return_inverse=True)', sample)
        self.assertIn('generator = torch.manual_seed(seed)', sample)
        self.assertIn('ms = type(original)(m.model.model_config)', advanced)
        self.assertIn('ms.set_parameters(shift=original.shift, multiplier=original.multiplier)', advanced)
        self.assertIn('ms.set_noise_scale(noise_scale)', advanced)
        self.assertIn('sigma * (s * noise) + (1.0 - sigma) * latent_image', sampling)
        self.assertIn('getattr(model_sampling, "noise_scale", 1.0)', k_sampling)
        self.assertIn('"noise_scale": 8.0', supported)
        replacements = REPLACEMENTS.read_text(encoding="utf-8")
        for spec in ARTICLE_SPECS.values():
            self.assertNotIn(spec["classType"], replacements)

    @unittest.skipUnless(DOCS_WHEEL.exists(), "pinned embedded-docs wheel is absent")
    def test_pinned_docs_paths_and_documented_discrepancies(self) -> None:
        self.assertEqual(DOCS_SHA, hashlib.sha256(DOCS_WHEEL.read_bytes()).hexdigest())
        with zipfile.ZipFile(DOCS_WHEEL) as archive:
            docs = {}
            for spec in ARTICLE_SPECS.values():
                for locale in ("en", "ru"):
                    member = f"comfyui_embedded_docs/docs/{spec['classType']}/{locale}.md"
                    self.assertIn(member, archive.namelist())
                    docs[f"{spec['classType']}:{locale}"] = archive.read(member).decode("utf-8")
        self.assertIn("skip noise-related operations", docs["DisableNoise:en"])
        self.assertNotIn("batch_index", docs["RandomNoise:en"])
        self.assertIn("absolute difference", docs["AddNoise:en"])
        self.assertIn("dev: 7.5", docs["ModelNoiseScale:en"])
        self.assertNotIn("7.6", docs["ModelNoiseScale:en"])

    @unittest.skipUnless(WORKFLOW_WHEEL.exists(), "official workflow wheel is absent")
    def test_exhaustive_workflow_census_and_exact_cases(self) -> None:
        self.assertEqual(WORKFLOW_SHA, hashlib.sha256(WORKFLOW_WHEEL.read_bytes()).hexdigest())
        targets = {spec["classType"] for spec in ARTICLE_SPECS.values()}
        records: list[dict[str, Any]] = []
        graph_map: dict[tuple[str, str], dict[str, Any]] = {}
        json_count = root_count = subgraph_count = 0
        with zipfile.ZipFile(WORKFLOW_WHEEL) as archive:
            for member in [name for name in archive.namelist() if "/templates/" in name and name.endswith(".json")]:
                json_count += 1
                payload = json.loads(archive.read(member).decode("utf-8"))
                if not isinstance(payload, dict):
                    continue
                if isinstance(payload.get("nodes"), list):
                    root_count += 1
                subgraphs = (payload.get("definitions") or {}).get("subgraphs", [])
                subgraph_count += sum(isinstance(item, dict) for item in subgraphs)
                for record in graph_records(payload, member):
                    graph_map[(Path(member).name, record["scope"])] = record["graph"]
                    if record["node"].get("type") in targets:
                        records.append(record)
        self.assertEqual((512, 496, 272), (json_count, root_count, subgraph_count))
        self.assertEqual(
            {"RandomNoise": 79, "DisableNoise": 7, "ModelNoiseScale": 2},
            dict(Counter(record["node"]["type"] for record in records)),
        )
        split = {
            class_type: (
                sum(r["scope"] == "root" for r in records if r["node"]["type"] == class_type),
                sum(r["scope"] != "root" for r in records if r["node"]["type"] == class_type),
            )
            for class_type in targets
        }
        self.assertEqual((12, 67), split["RandomNoise"])
        self.assertEqual((2, 5), split["DisableNoise"])
        self.assertEqual((0, 0), split["AddNoise"])
        self.assertEqual((2, 0), split["ModelNoiseScale"])

        for record in [r for r in records if r["node"]["type"] in {"RandomNoise", "DisableNoise"}]:
            node = record["node"]
            nodes = {item.get("id"): item for item in record["graph"].get("nodes", []) if isinstance(item, dict)}
            outgoing = [
                link for link in map(normalized_link, record["graph"].get("links", []))
                if link.get("origin_id") == node.get("id")
            ]
            self.assertEqual(1, len(outgoing))
            self.assertEqual("NOISE", outgoing[0]["type"])
            self.assertEqual("SamplerCustomAdvanced", nodes[outgoing[0]["target_id"]]["type"])

        base = graph_map[("image_hidream_o1.json", "root")]
        dev = graph_map[("image_hidream_o1_dev.json", "root")]
        for graph, expected_widget, scheduler_widget, sampler_type in (
            (base, [8], ["normal", 40, 1], "HiDreamO1PatchSeamSmoothing"),
            (dev, [7.6], ["normal", 28, 1], "SamplerCustom"),
        ):
            nodes = {item["id"]: item for item in graph["nodes"]}
            links = {link["id"]: link for link in map(normalized_link, graph["links"])}
            self.assertEqual(expected_widget, nodes[124]["widgets_values"])
            self.assertEqual(scheduler_widget, nodes[112]["widgets_values"])
            self.assertEqual((6, 0, 124, 0, "MODEL"), tuple(links[192][key] for key in ("origin_id", "origin_slot", "target_id", "target_slot", "type")))
            self.assertEqual((124, 0, 112, 0, "MODEL"), tuple(links[182][key] for key in ("origin_id", "origin_slot", "target_id", "target_slot", "type")))
            outgoing_types = {
                nodes[link["target_id"]]["type"]
                for link in links.values()
                if link["origin_id"] == 124 and link["target_id"] in nodes
            }
            self.assertIn(sampler_type, outgoing_types)

    @unittest.skipUnless(SOURCE.exists(), "pinned ComfyUI source checkout is absent")
    def test_safe_exact_source_probe(self) -> None:
        candidates = [
            Path(os.environ.get("TEMP", "")) / "nodes-wizard-comfyui-v0.32.0-venv" / "Scripts" / "python.exe",
            Path(sys.executable),
        ]
        python = next((path for path in candidates if path.exists()), None)
        if python is None:
            self.skipTest("no Python interpreter")
        result = subprocess.run(
            [str(python), str(PROBE), str(SOURCE)],
            cwd=catalog.ROOT,
            text=True,
            capture_output=True,
            timeout=120,
            check=False,
        )
        if result.returncode != 0:
            self.fail(result.stderr or result.stdout)
        payload = json.loads(result.stdout.strip().splitlines()[-1])
        self.assertEqual([2, 3, 4, 5], payload["disable"]["shape"])
        self.assertEqual("torch.float16", payload["disable"]["dtype"])
        self.assertEqual("cpu", payload["disable"]["device"])
        self.assertTrue(payload["random"]["reproducible"])
        self.assertTrue(payload["random"]["indexedFirstTwoEqual"])
        self.assertTrue(payload["random"]["indexedThirdDiffers"])
        self.assertEqual(5.0, payload["add"]["multiSigmaScale"])
        self.assertEqual(42.0, payload["add"]["nonzeroValue"])
        self.assertEqual(4.0, payload["add"]["emptyValue"])
        self.assertTrue(payload["add"]["emptySigmasIdentity"])
        self.assertEqual(7.6, payload["modelNoiseScale"]["value"])
        self.assertEqual(3.0, payload["modelNoiseScale"]["shift"])
        self.assertEqual(1000, payload["modelNoiseScale"]["multiplier"])
        self.assertTrue(payload["modelNoiseScale"]["originalUnchanged"])


if __name__ == "__main__":
    unittest.main()
