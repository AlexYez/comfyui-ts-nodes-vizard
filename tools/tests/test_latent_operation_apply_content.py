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
    "core.latent-apply-operation": {
        "directory": "latent-apply-operation",
        "classType": "LatentApplyOperation",
        "fingerprint": "sha256:8bfb6ce57b27e80dccd82678f23afa01e92ec54c7f3ebf6672dccf0cb30f80d0",
        "output": "LATENT",
        "required": {"samples": "LATENT", "operation": "LATENT_OPERATION"},
        "recipe": "recipe.sharpen-latent-operation",
        "docs": {
            "en": "cb0727317326211bdf6dd401fa841f9525c560473fab837c1a81fabe1338724a",
            "ru": "9983813d04240acaae6a5c5fdd05f14e630755641ff7939368bf8d4a95f068b9",
        },
    },
    "core.latent-apply-operation-cfg": {
        "directory": "latent-apply-operation-cfg",
        "classType": "LatentApplyOperationCFG",
        "fingerprint": "sha256:c3f14a7b96f1df02ea7dfc94aeb2909b55e1da062c740092a33c8ef18e33ef86",
        "output": "MODEL",
        "required": {"model": "MODEL", "operation": "LATENT_OPERATION"},
        "recipe": "recipe.ace-reinhard-pre-cfg",
        "docs": {
            "en": "5f96230e3b8eebeb94ceb3813d934c86b3fa6bce6b6baba84998b37de904c5c4",
            "ru": "ffd170d626aa6be8c8e1660fe163c3bad6901b962eb4819f4d41cad3c4ac3dd1",
        },
    },
    "core.latent-operation-tonemap-reinhard": {
        "directory": "latent-operation-tonemap-reinhard",
        "classType": "LatentOperationTonemapReinhard",
        "fingerprint": "sha256:aa04c0f573fb52160ca4dc7afe1bd2198e16b470e95fc51d2cbf4eef8b4e28a4",
        "output": "LATENT_OPERATION",
        "required": {"multiplier": "FLOAT"},
        "recipe": "recipe.ace-reinhard-pre-cfg",
        "docs": {
            "en": "1a7469962a1525104cdbad1465830923848b0b77784039e9089c16291d32688d",
            "ru": "aef7829344d2007a715aa5b79827ae279dbe2ecb2506ebc61bd651a02ed6b008",
        },
    },
    "core.latent-operation-sharpen": {
        "directory": "latent-operation-sharpen",
        "classType": "LatentOperationSharpen",
        "fingerprint": "sha256:ee12d2cb0dc12740a977f2ec2dfc70274ee6497e7ab460f53f3c3cf0eaa65015",
        "output": "LATENT_OPERATION",
        "required": {
            "sharpen_radius": "INT",
            "sigma": "FLOAT",
            "alpha": "FLOAT",
        },
        "recipe": "recipe.sharpen-latent-operation",
        "docs": {
            "en": "65c05e82b576798cde02bdc1ed5fca356ab54706112d694ee87ebcba804b5ae3",
            "ru": "d06545dad72230273ff46284b00bc023206259320c5c67f69826eba64ac5a226",
        },
    },
}

RECIPE_DIRECTORIES = {
    "recipe.ace-reinhard-pre-cfg": "ace-reinhard-pre-cfg",
    "recipe.sharpen-latent-operation": "sharpen-latent-operation",
}

FULL_INVENTORY = catalog.CONTENT / "runtime" / "comfyui-0.32.0.object-info.json"
INVENTORY_METADATA = catalog.CONTENT / "runtime" / "comfyui-0.32.0.object-info.meta.json"
REPLACEMENTS = catalog.CONTENT / "runtime" / "comfyui-0.32.0.node-replacements.json"
SOURCE = catalog.ROOT / ".comfyui-source-0.32.0"
SOURCE_COMMIT = "c2bcbecd82ec5ae66594340b395c24ef0217b238"
WORKFLOW_WHEEL = catalog.ROOT / ".upstream-cache" / "comfyui_workflow_templates_json-0.1.42-py3-none-any.whl"
WORKFLOW_WHEEL_SHA256 = "242982d65e1c51ca03d892bc1009bb6843f457e7dfc0c20afe6438770b7a14a3"
DOCS_WHEEL = catalog.ROOT / ".upstream-cache" / "comfyui_embedded_docs-0.5.9-py3-none-any.whl"
DOCS_WHEEL_SHA256 = "30afae432a71c96aa59421d0f37388c66ff6572b8cbeee8ff045e4d5f84f896c"
SYNTHETIC_PROBE = Path(__file__).with_name("latent_operation_apply_synthetic_probe.py")


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


def graph_scopes(payload: dict[str, Any]) -> Iterator[dict[str, Any]]:
    if isinstance(payload.get("nodes"), list):
        yield payload
    definitions = payload.get("definitions")
    if isinstance(definitions, dict):
        for subgraph in definitions.get("subgraphs", []):
            if isinstance(subgraph, dict):
                yield subgraph


class LatentOperationApplyContentTests(unittest.TestCase):
    def test_articles_recipes_ledgers_and_cross_links_validate(self) -> None:
        article_ids = all_article_ids()
        schemas = {
            "article": catalog.load_json(catalog.CONTENT / "schemas" / "article.schema.v1.json"),
            "recipe": catalog.load_json(catalog.CONTENT / "schemas" / "recipe.schema.v1.json"),
            "fragment": catalog.load_json(catalog.CONTENT / "schemas" / "recipe-fragment.schema.v1.json"),
            "research": catalog.load_json(catalog.CONTENT / "schemas" / "article-research.schema.v1.json"),
        }
        errors: list[str] = []

        target_class_types: list[str] = []
        target_article_ids: list[str] = []
        for article_id, spec in ARTICLE_SPECS.items():
            path = article_path(spec)
            article = catalog.load_json(path)
            self.assertEqual([], catalog.json_schema_errors(article, schemas["article"]))
            catalog.validate_article(path, article, errors)
            self.assertEqual(article_id, article["articleId"])
            self.assertEqual("draft", article["status"])
            self.assertTrue(article["experimental"])
            self.assertEqual("in_review", article["editorial"]["state"])
            self.assertIn("human approval pending", article["editorial"]["reviewedBy"])
            self.assertEqual([], article["runtimeIdentity"]["aliases"])
            self.assertEqual("comfy_extras.nodes_latent", article["runtimeIdentity"]["pythonModule"])
            self.assertEqual(spec["classType"], article["runtimeIdentity"]["classType"])
            self.assertEqual(
                {spec["recipe"]},
                {asset["id"] for asset in article["assets"] if asset["type"] == "recipe"},
            )
            relations = article["relations"]
            targets = set(relations["related"] + relations["alternatives"])
            if relations["replacedBy"] is not None:
                targets.add(relations["replacedBy"])
            self.assertTrue(targets.issubset(article_ids), (article_id, targets - article_ids))

            body = (path.parent / article["body"]).read_text(encoding="utf-8")
            self.assertEqual(10, len(re.findall(r"^## .+$", body, flags=re.MULTILINE)), article_id)
            self.assertNotIn("\ufffd", body)
            self.assertNotRegex(
                body.lower(),
                r"важно отметить|стоит отметить|следует отметить|в современном мире|"
                r"революционн|является мощн|давайте|глубже погруз|открывает новые|"
                r"может показаться|позволяет вам|подводя итог|в заключение|данная нода",
            )

            research_path = catalog.CONTENT / "research" / "reviews" / f"{article_id}.json"
            research = catalog.load_json(research_path)
            self.assertEqual([], catalog.json_schema_errors(research, schemas["research"]))
            self.assertEqual(article_id, research["articleId"])
            self.assertEqual(spec["classType"], research["node"]["classType"])
            self.assertEqual("comfy_extras.nodes_latent", research["node"]["pythonModule"])
            self.assertEqual("fact_checked", research["state"])
            self.assertEqual("automated_assisted", research["reviewMode"])
            self.assertTrue(research["checks"]["exampleSchemaValidated"])
            self.assertFalse(research["checks"]["exampleExecuted"])
            self.assertTrue(research["knownGaps"])
            self.assertTrue(any("Редактор пока" in gap for gap in research["knownGaps"]))
            target_class_types.append(spec["classType"])
            target_article_ids.append(article_id)

        self.assertEqual(len(target_class_types), len(set(target_class_types)))
        self.assertEqual(len(target_article_ids), len(set(target_article_ids)))

        for recipe_id in RECIPE_DIRECTORIES:
            path = recipe_path(recipe_id)
            recipe = catalog.load_json(path)
            self.assertEqual([], catalog.json_schema_errors(recipe, schemas["recipe"]))
            catalog.validate_recipe(path, recipe, article_ids, errors)
            self.assertEqual(recipe_id, recipe["recipeId"])
            self.assertNotIn("workflow", recipe)
            self.assertEqual("in_review", recipe["editorial"]["state"])
            self.assertIn("human approval pending", recipe["editorial"]["reviewedBy"])
            fragment_path = path.parent / recipe["fragment"]["path"]
            fragment = catalog.load_json(fragment_path)
            self.assertEqual([], catalog.json_schema_errors(fragment, schemas["fragment"]))
            catalog.validate_fragment(fragment_path, fragment, errors)
            self.assertEqual(recipe["fragment"]["id"], fragment["fragmentId"])
            self.assertTrue(fragment["nodes"])

        self.assertEqual([], errors)

    def test_exact_runtime_identity_fingerprints_flags_ports_and_fragment_types(self) -> None:
        nodes = catalog.object_info_nodes(catalog.load_json(FULL_INVENTORY))
        metadata = catalog.load_json(INVENTORY_METADATA)
        self.assertEqual(SOURCE_COMMIT, metadata["source"]["commit"])
        self.assertEqual("0.32.0", metadata["source"]["backendVersion"])
        self.assertEqual("/object_info", metadata["capture"]["endpoint"])

        for article_id, spec in ARTICLE_SPECS.items():
            runtime = nodes[spec["classType"]]
            article = catalog.load_json(article_path(spec))
            self.assertEqual("comfy_extras.nodes_latent", runtime["python_module"])
            self.assertEqual("model/latent/advanced/operations", runtime["category"])
            self.assertEqual(spec["required"], {name: value[0] for name, value in runtime["input"]["required"].items()})
            self.assertEqual([spec["output"]], runtime["output"])
            self.assertEqual([spec["output"]], runtime["output_name"])
            self.assertEqual([False], runtime["output_is_list"])
            self.assertFalse(runtime["is_input_list"])
            self.assertFalse(runtime["output_node"])
            self.assertTrue(runtime["experimental"])
            self.assertFalse(runtime["deprecated"])
            self.assertFalse(runtime["dev_only"])
            self.assertFalse(runtime["api_node"])
            self.assertEqual(spec["fingerprint"], catalog.schema_fingerprint(spec["classType"], runtime), article_id)
            self.assertEqual(spec["fingerprint"], article["editorial"]["schemaHash"])

        tonemap = nodes["LatentOperationTonemapReinhard"]["input"]["required"]["multiplier"]
        self.assertEqual(["FLOAT", {"default": 1.0, "min": 0.0, "max": 100.0, "step": 0.01}], tonemap)
        sharpen = nodes["LatentOperationSharpen"]["input"]["required"]
        self.assertEqual((9, 1, 31, 1, True), tuple(sharpen["sharpen_radius"][1][key] for key in ("default", "min", "max", "step", "advanced")))
        self.assertEqual((1.0, 0.1, 10.0, 0.1, True), tuple(sharpen["sigma"][1][key] for key in ("default", "min", "max", "step", "advanced")))
        self.assertEqual((0.1, 0.0, 5.0, 0.01, True), tuple(sharpen["alpha"][1][key] for key in ("default", "min", "max", "step", "advanced")))

        for recipe_id in RECIPE_DIRECTORIES:
            recipe = catalog.load_json(recipe_path(recipe_id))
            fragment = catalog.load_json(recipe_path(recipe_id).parent / recipe["fragment"]["path"])
            by_ref = {node["ref"]: node for node in fragment["nodes"]}
            for external in fragment["externalInputs"]:
                runtime = nodes[by_ref[external["to"]]["classType"]]
                self.assertEqual(external["type"], runtime["input"]["required"][external["input"]][0])
            for connection in fragment["connections"]:
                source_node = nodes[by_ref[connection["from"]]["classType"]]
                target_node = nodes[by_ref[connection["to"]]["classType"]]
                output_index = source_node["output_name"].index(connection["output"])
                self.assertEqual(source_node["output"][output_index], target_node["input"]["required"][connection["input"]][0])

    @unittest.skipUnless(SOURCE.exists(), "pinned ComfyUI source checkout is absent")
    def test_exact_pinned_source_formulas_and_hook_accumulation(self) -> None:
        self.assertEqual(SOURCE_COMMIT, (SOURCE / ".git" / "HEAD").read_text(encoding="utf-8").strip())
        text = (SOURCE / "comfy_extras" / "nodes_latent.py").read_text(encoding="utf-8")
        model_patcher = (SOURCE / "comfy" / "model_patcher.py").read_text(encoding="utf-8")
        post = (SOURCE / "comfy_extras" / "nodes_post_processing.py").read_text(encoding="utf-8")

        self.assertIn('node_id="LatentApplyOperation"', text)
        self.assertIn('search_aliases=["transform latent"]', text)
        self.assertIn('samples_out["samples"] = operation(latent=s1)', text)
        self.assertIn("conds_out[0] = operation(latent=(conds_out[0] - conds_out[1])) + conds_out[1]", text)
        self.assertIn("conds_out[0] = operation(latent=conds_out[0])", text)
        self.assertIn("m.set_model_sampler_pre_cfg_function(pre_cfg_function)", text)
        self.assertIn(
            'model_options["sampler_pre_cfg_function"] = model_options.get("sampler_pre_cfg_function", []) + [pre_cfg_function]',
            model_patcher,
        )
        self.assertIn(
            "self.model_options = set_model_options_pre_cfg_function(self.model_options, pre_cfg_function, disable_cfg1_optimization)",
            model_patcher,
        )
        self.assertIn("torch.linalg.vector_norm(latent, dim=(1)) + 0.0000000001", text)
        self.assertIn("top = (std * 5 + mean) * multiplier", text)
        self.assertIn("kernel *= alpha * -10", text)
        self.assertIn("'reflect'", text)
        self.assertIn("groups=channels", text)
        self.assertIn("return (g / g.sum()).to(dtype)", post)

        replacements = REPLACEMENTS.read_text(encoding="utf-8")
        for spec in ARTICLE_SPECS.values():
            self.assertNotIn(spec["classType"], replacements)

    @unittest.skipUnless(DOCS_WHEEL.exists(), "pinned embedded-docs wheel is absent")
    def test_embedded_docs_exact_hashes_and_known_omissions(self) -> None:
        self.assertEqual(DOCS_WHEEL_SHA256, hashlib.sha256(DOCS_WHEEL.read_bytes()).hexdigest())
        with zipfile.ZipFile(DOCS_WHEEL) as archive:
            for spec in ARTICLE_SPECS.values():
                for locale, digest in spec["docs"].items():
                    path = f"comfyui_embedded_docs/docs/{spec['classType']}/{locale}.md"
                    self.assertIn(path, archive.namelist())
                    data = archive.read(path)
                    self.assertEqual(digest, hashlib.sha256(data).hexdigest())
                    self.assertTrue(data.decode("utf-8").strip())
            cfg_docs = archive.read("comfyui_embedded_docs/docs/LatentApplyOperationCFG/en.md").decode("utf-8").lower()
            sharpen_docs = archive.read("comfyui_embedded_docs/docs/LatentOperationSharpen/en.md").decode("utf-8").lower()
            self.assertNotIn("len(conds_out)", cfg_docs)
            self.assertNotIn("groups=channels", sharpen_docs)
            self.assertNotIn("reflect", sharpen_docs)

    @unittest.skipUnless(WORKFLOW_WHEEL.exists(), "official workflow wheel is absent")
    def test_exhaustive_workflow_census_and_exact_ace_topology(self) -> None:
        self.assertEqual(WORKFLOW_WHEEL_SHA256, hashlib.sha256(WORKFLOW_WHEEL.read_bytes()).hexdigest())
        targets = {spec["classType"] for spec in ARTICLE_SPECS.values()}
        counts = {name: 0 for name in targets}
        ace_cases: list[dict[str, Any]] = []
        json_count = 0
        root_graph_count = 0
        subgraph_count = 0

        with zipfile.ZipFile(WORKFLOW_WHEEL) as archive:
            members = sorted(name for name in archive.namelist() if "/templates/" in name and name.endswith(".json"))
            for member in members:
                json_count += 1
                payload = json.loads(archive.read(member).decode("utf-8"))
                if not isinstance(payload, dict):
                    continue
                if isinstance(payload.get("nodes"), list):
                    root_graph_count += 1
                definitions = payload.get("definitions")
                if isinstance(definitions, dict):
                    subgraph_count += sum(isinstance(item, dict) for item in definitions.get("subgraphs", []))
                for scope in graph_scopes(payload):
                    nodes = [node for node in scope.get("nodes", []) if isinstance(node, dict)]
                    by_id = {node.get("id"): node for node in nodes}
                    for node in nodes:
                        if node.get("type") in targets:
                            counts[node["type"]] += 1
                    cfg_nodes = [node for node in nodes if node.get("type") == "LatentApplyOperationCFG"]
                    for cfg in cfg_nodes:
                        related_links = [link for link in scope.get("links", []) if isinstance(link, list) and len(link) >= 6 and (link[1] == cfg["id"] or link[3] == cfg["id"])]
                        edges = {(by_id[link[1]]["type"], by_id[link[3]]["type"], link[5]) for link in related_links}
                        tonemap = next(node for node in nodes if node.get("type") == "LatentOperationTonemapReinhard")
                        sampling = next(node for node in nodes if node.get("type") == "ModelSamplingSD3")
                        sampler = next(node for node in nodes if node.get("type") == "KSampler" and any(link[3] == node["id"] and link[1] == cfg["id"] for link in related_links))
                        ace_cases.append({"member": member, "edges": edges, "tonemap": tonemap.get("widgets_values"), "sampling": sampling.get("widgets_values"), "sampler": sampler.get("widgets_values")})

        self.assertEqual(512, json_count)
        self.assertEqual(496, root_graph_count)
        self.assertEqual(272, subgraph_count)
        self.assertEqual({"LatentApplyOperation": 0, "LatentApplyOperationCFG": 3, "LatentOperationTonemapReinhard": 3, "LatentOperationSharpen": 0}, counts)
        self.assertEqual(3, len(ace_cases))
        expected_edges = {("ModelSamplingSD3", "LatentApplyOperationCFG", "MODEL"), ("LatentOperationTonemapReinhard", "LatentApplyOperationCFG", "LATENT_OPERATION"), ("LatentApplyOperationCFG", "KSampler", "MODEL")}
        for case in ace_cases:
            self.assertEqual(expected_edges, case["edges"])
            self.assertAlmostEqual(1.0, case["tonemap"][0])
            self.assertAlmostEqual(5.0, case["sampling"][0])
            self.assertEqual((50, 5, "euler", "simple"), tuple(case["sampler"][2:6]))
        self.assertEqual([0.3, 1, 1], sorted(round(case["sampler"][6], 3) for case in ace_cases))

    @unittest.skipUnless(SOURCE.exists(), "pinned ComfyUI source checkout is absent")
    def test_safe_exact_source_tensor_and_hook_probe(self) -> None:
        candidates = [
            Path(os.environ.get("TEMP", "")) / "nodes-wizard-comfyui-v0.32.0-venv" / "Scripts" / "python.exe",
            Path(sys.executable),
        ]
        python = next((candidate for candidate in candidates if candidate.exists()), None)
        if python is None:
            self.skipTest("no Python interpreter for latent operation probe")
        result = subprocess.run(
            [str(python), str(SYNTHETIC_PROBE), str(SOURCE)],
            cwd=catalog.ROOT,
            text=True,
            capture_output=True,
            timeout=120,
            check=False,
        )
        if result.returncode != 0:
            self.fail(result.stderr or result.stdout)
        payload = json.loads(result.stdout.strip().splitlines()[-1])
        self.assertTrue(payload["apply"]["samplesReplaced"])
        self.assertTrue(payload["apply"]["metadataIdentityPreserved"])
        self.assertTrue(payload["apply"]["operationReceivedOriginalTensor"])
        self.assertTrue(payload["cfg"]["cloneReturned"])
        self.assertEqual([50.0, 10.0], payload["cfg"]["twoConditionResult"])
        self.assertEqual([14.0], payload["cfg"]["singleConditionResult"])
        self.assertEqual([4.0, 3.0, 4.0], payload["cfg"]["threeConditionResult"])
        self.assertTrue(payload["cfg"]["sameListsReturned"])
        self.assertTrue(payload["tonemap"]["directionPreserved"])
        self.assertTrue(payload["tonemap"]["normsNotIncreased"])
        self.assertFalse(payload["tonemap"]["multiplierZeroFinite"])
        self.assertFalse(payload["tonemap"]["singletonFinite"])
        self.assertTrue(payload["sharpen"]["alphaZeroIdentity"])
        self.assertEqual([1, 4, 8, 9], payload["sharpen"]["shape"])
        self.assertTrue(payload["sharpen"]["changesValues"])
        self.assertTrue(payload["sharpen"]["smallSpatialRejected"])
        self.assertTrue(payload["sharpen"]["fiveDimensionalRejected"])


if __name__ == "__main__":
    unittest.main()
