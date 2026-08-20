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
    "core.k-sampler-select": {
        "directory": "k-sampler-select",
        "classType": "KSamplerSelect",
        "fingerprint": "sha256:1cf63ffb17570a2a1a94fd1d14d3febdb657ceeb697edc3937ba7790d112757d",
        "recipes": {"recipe.sdxl-turbo-custom-sampling", "recipe.advanced-euler-custom-sampling"},
    },
    "core.sampler-custom": {
        "directory": "sampler-custom",
        "classType": "SamplerCustom",
        "fingerprint": "sha256:a80c24090fff119326d4b20ffafb967d5d70627e85b0aa43d01fa797b43952c8",
        "recipes": {"recipe.sdxl-turbo-custom-sampling"},
    },
    "core.sampler-custom-advanced": {
        "directory": "sampler-custom-advanced",
        "classType": "SamplerCustomAdvanced",
        "fingerprint": "sha256:1a7f7ffc08dfa29c73cecd79dec3427bb19a910bdfc489a41a9aeaea49eea244",
        "recipes": {"recipe.advanced-euler-custom-sampling", "recipe.ltx-euler-ancestral-zero-eta"},
    },
    "core.sampler-euler-ancestral": {
        "directory": "sampler-euler-ancestral",
        "classType": "SamplerEulerAncestral",
        "fingerprint": "sha256:c02514b231b787d00ef8fe519bde53f3a1c662a7d31f072c64ec50d42808ab0b",
        "recipes": {"recipe.ltx-euler-ancestral-zero-eta"},
    },
}

RECIPE_DIRECTORIES = {
    "recipe.sdxl-turbo-custom-sampling": "sdxl-turbo-custom-sampling",
    "recipe.advanced-euler-custom-sampling": "advanced-euler-custom-sampling",
    "recipe.ltx-euler-ancestral-zero-eta": "ltx-euler-ancestral-zero-eta",
}

EXPECTED_FRAGMENT_NODES = {
    "recipe.sdxl-turbo-custom-sampling": [
        ("KSamplerSelect", {"sampler_name": "euler_ancestral"}),
        ("SDTurboScheduler", {"steps": 1, "denoise": 1.0}),
        ("SamplerCustom", {"add_noise": True, "noise_seed": 0, "cfg": 1.0}),
    ],
    "recipe.advanced-euler-custom-sampling": [
        ("KSamplerSelect", {"sampler_name": "euler"}),
        ("SamplerCustomAdvanced", {}),
    ],
    "recipe.ltx-euler-ancestral-zero-eta": [
        ("SamplerEulerAncestral", {"eta": 0.0, "s_noise": 1.0}),
        ("SamplerCustomAdvanced", {}),
    ],
}

INVENTORY = catalog.CONTENT / "runtime" / "comfyui-0.32.0.object-info.json"
SOURCE = catalog.ROOT / ".comfyui-source-0.32.0"
REPLACEMENTS = catalog.CONTENT / "runtime" / "comfyui-0.32.0.node-replacements.json"
WORKFLOW_WHEEL = catalog.ROOT / ".upstream-cache" / "comfyui_workflow_templates_json-0.1.42-py3-none-any.whl"
WORKFLOW_SHA = "242982d65e1c51ca03d892bc1009bb6843f457e7dfc0c20afe6438770b7a14a3"
DOCS_WHEEL = catalog.ROOT / ".upstream-cache" / "comfyui_embedded_docs-0.5.9-py3-none-any.whl"
DOCS_SHA = "30afae432a71c96aa59421d0f37388c66ff6572b8cbeee8ff045e4d5f84f896c"
PROBE = Path(__file__).with_name("sampler_custom_synthetic_probe.py")


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


class CustomSamplerContentTests(unittest.TestCase):
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
            self.assertEqual(spec["recipes"], {a["id"] for a in article["assets"] if a["type"] == "recipe"})
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
            self.assertEqual(EXPECTED_FRAGMENT_NODES[recipe_id], [(n["classType"], n["settings"]) for n in fragment["nodes"]])
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
            self.assertEqual("comfy_extras.nodes_custom_sampler", runtime["python_module"])
            self.assertEqual(spec["fingerprint"], catalog.schema_fingerprint(spec["classType"], runtime))
            self.assertFalse(runtime.get("experimental", False))
            self.assertFalse(runtime.get("deprecated", False))
        options = inventory["KSamplerSelect"]["input"]["required"]["sampler_name"][1]["options"]
        self.assertEqual(44, len(options))
        self.assertTrue({"euler", "euler_ancestral", "ddim", "uni_pc", "uni_pc_bh2"}.issubset(options))
        self.assertEqual(
            ["model", "add_noise", "noise_seed", "cfg", "positive", "negative", "sampler", "sigmas", "latent_image"],
            inventory["SamplerCustom"]["input_order"]["required"],
        )
        self.assertEqual(["noise", "guider", "sampler", "sigmas", "latent_image"], inventory["SamplerCustomAdvanced"]["input_order"]["required"])
        for name in ("eta", "s_noise"):
            config = inventory["SamplerEulerAncestral"]["input"]["required"][name]
            self.assertEqual("FLOAT", config[0])
            self.assertEqual((1.0, 0.0, 100.0, 0.01, True), tuple(config[1][key] for key in ("default", "min", "max", "step", "advanced")))

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
        samplers = (SOURCE / "comfy" / "samplers.py").read_text(encoding="utf-8")
        sampling = (SOURCE / "comfy" / "k_diffusion" / "sampling.py").read_text(encoding="utf-8")
        self.assertIn("options=comfy.samplers.SAMPLER_NAMES", custom)
        self.assertIn("comfy.samplers.sampler_object(sampler_name)", custom)
        self.assertIn("noise = Noise_EmptyNoise().generate_noise(latent)", custom)
        self.assertIn("noise = Noise_RandomNoise(noise_seed).generate_noise(latent)", custom)
        self.assertIn("noise_mask=noise_mask", custom)
        self.assertIn('out.pop("downscale_ratio_spacial", None)', custom)
        self.assertIn("x0_out = model.model.process_latent_out(x0.cpu())", custom)
        self.assertIn("noise.generate_noise(latent)", custom)
        self.assertIn("samples.to(comfy.model_management.intermediate_device())", custom)
        self.assertIn('ksampler("euler_ancestral", {"eta": eta, "s_noise": s_noise})', custom)
        self.assertIn('elif name == "ddim":', samplers)
        self.assertIn('if name == "uni_pc":', samplers)
        self.assertIn('elif name == "uni_pc_bh2":', samplers)
        self.assertIn("get_ancestral_step(sigmas[i], sigmas[i + 1], eta=eta)", sampling)
        self.assertIn("* s_noise * sigma_up", sampling)
        self.assertIn("isinstance(model.inner_model.inner_model.model_sampling, comfy.model_sampling.CONST)", sampling)
        replacements = REPLACEMENTS.read_text(encoding="utf-8")
        for spec in ARTICLE_SPECS.values():
            self.assertNotIn(spec["classType"], replacements)

    @unittest.skipUnless(DOCS_WHEEL.exists(), "pinned embedded-docs wheel is absent")
    def test_pinned_docs_and_discrepancies(self) -> None:
        self.assertEqual(DOCS_SHA, hashlib.sha256(DOCS_WHEEL.read_bytes()).hexdigest())
        with zipfile.ZipFile(DOCS_WHEEL) as archive:
            docs = {}
            for spec in ARTICLE_SPECS.values():
                for locale in ("en", "ru"):
                    member = f"comfyui_embedded_docs/docs/{spec['classType']}/{locale}.md"
                    self.assertIn(member, archive.namelist())
                    docs[f"{spec['classType']}:{locale}"] = archive.read(member).decode("utf-8")
        self.assertNotIn("SIGMAS", docs["KSamplerSelect:en"])
        self.assertIn("configuration", docs["SamplerCustom:en"])
        self.assertNotIn("noise_mask", docs["SamplerCustom:ru"])
        self.assertIn("downscale_ratio_spacial", docs["SamplerCustomAdvanced:en"])
        self.assertNotIn("downscale_ratio_spacial", docs["SamplerCustomAdvanced:ru"])
        self.assertIn("step size and stochasticity", docs["SamplerEulerAncestral:en"])
        self.assertNotIn("CONST", docs["SamplerEulerAncestral:en"])

    @unittest.skipUnless(WORKFLOW_WHEEL.exists(), "official workflow wheel is absent")
    def test_exhaustive_workflow_census_and_exact_cases(self) -> None:
        self.assertEqual(WORKFLOW_SHA, hashlib.sha256(WORKFLOW_WHEEL.read_bytes()).hexdigest())
        targets = {spec["classType"] for spec in ARTICLE_SPECS.values()}
        records: list[dict[str, Any]] = []
        graph_map: dict[tuple[str, str], dict[str, Any]] = {}
        json_count = root_count = subgraph_count = 0
        with zipfile.ZipFile(WORKFLOW_WHEEL) as archive:
            for member in [n for n in archive.namelist() if "/templates/" in n and n.endswith(".json")]:
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
            {"KSamplerSelect": 97, "SamplerCustom": 21, "SamplerCustomAdvanced": 87, "SamplerEulerAncestral": 3},
            dict(Counter(r["node"]["type"] for r in records)),
        )
        split = {
            class_type: (
                sum(r["scope"] == "root" for r in records if r["node"]["type"] == class_type),
                sum(r["scope"] != "root" for r in records if r["node"]["type"] == class_type),
            ) for class_type in targets
        }
        self.assertEqual((16, 81), split["KSamplerSelect"])
        self.assertEqual((5, 16), split["SamplerCustom"])
        self.assertEqual((14, 73), split["SamplerCustomAdvanced"])
        self.assertEqual((0, 3), split["SamplerEulerAncestral"])
        modes = {class_type: Counter(r["node"].get("mode", 0) for r in records if r["node"]["type"] == class_type) for class_type in targets}
        self.assertEqual({0: 93, 4: 4}, dict(modes["KSamplerSelect"]))
        self.assertEqual({0: 21}, dict(modes["SamplerCustom"]))
        self.assertEqual({0: 81, 4: 6}, dict(modes["SamplerCustomAdvanced"]))
        self.assertEqual({0: 3}, dict(modes["SamplerEulerAncestral"]))
        choices = Counter(tuple(r["node"].get("widgets_values", [])) for r in records if r["node"]["type"] == "KSamplerSelect")
        self.assertEqual(66, choices[("euler",)])
        self.assertEqual(15, choices[("euler_ancestral",)])
        for record in [r for r in records if r["node"]["type"] == "SamplerEulerAncestral"]:
            self.assertEqual([0, 1], record["node"]["widgets_values"])
            links = [normalized_link(link) for link in record["graph"].get("links", [])]
            outgoing = [link for link in links if link["origin_id"] == record["node"]["id"]]
            nodes = {n["id"]: n for n in record["graph"]["nodes"]}
            self.assertEqual(1, len(outgoing))
            self.assertEqual("SamplerCustomAdvanced", nodes[outgoing[0]["target_id"]]["type"])

        turbo = graph_map[("sdxlturbo_example.json", "root")]
        turbo_nodes = {node["id"]: node for node in turbo["nodes"]}
        turbo_links = {link["id"]: link for link in map(normalized_link, turbo["links"])}
        self.assertEqual(["euler_ancestral"], turbo_nodes[14]["widgets_values"])
        self.assertEqual([True, 0, "fixed", 1], turbo_nodes[13]["widgets_values"])
        self.assertEqual((14, 0, 13, 3, "SAMPLER"), tuple(turbo_links[18][key] for key in ("origin_id", "origin_slot", "target_id", "target_slot", "type")))
        self.assertEqual((22, 0, 13, 4, "SIGMAS"), tuple(turbo_links[49][key] for key in ("origin_id", "origin_slot", "target_id", "target_slot", "type")))

        ltx = graph_map[("template_ltx2_3_style_transition.json", "subgraph:0")]
        ltx_nodes = {node["id"]: node for node in ltx["nodes"]}
        ltx_links = {link["id"]: link for link in map(normalized_link, ltx["links"])}
        self.assertEqual([0, 1], ltx_nodes[117]["widgets_values"])
        expected = {
            246: (100, 0, 120, 0, "NOISE"),
            247: (116, 0, 120, 1, "GUIDER"),
            248: (117, 0, 120, 2, "SAMPLER"),
            249: (118, 0, 120, 3, "SIGMAS"),
            250: (119, 0, 120, 4, "LATENT"),
            204: (120, 1, 121, 0, "LATENT"),
        }
        for link_id, signature in expected.items():
            self.assertEqual(signature, tuple(ltx_links[link_id][key] for key in ("origin_id", "origin_slot", "target_id", "target_slot", "type")))

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
        self.assertEqual(["euler"], payload["factory"]["samplerObjectCalls"])
        self.assertEqual("euler_ancestral", payload["factory"]["ksamplerCalls"][0][0])
        self.assertEqual(42, payload["custom"]["randomSeed"])
        self.assertEqual(99, payload["custom"]["zeroNoiseSeedStillForwarded"])
        self.assertTrue(payload["custom"]["maskForwarded"])
        self.assertEqual((4.0, 107.0), (payload["custom"]["outputValue"], payload["custom"]["x0Value"]))
        self.assertEqual(77, payload["advanced"]["noiseSeed"])
        self.assertTrue(payload["advanced"]["maskForwarded"])
        self.assertEqual((5.0, 109.0), (payload["advanced"]["outputValue"], payload["advanced"]["x0Value"]))


if __name__ == "__main__":
    unittest.main()
