from __future__ import annotations

import hashlib
import json
import re
import unittest
import zipfile
from pathlib import Path
from typing import Any, Iterator

from tools import catalog
from tools.tests.model_execution_patch_synthetic_probe import run_probe


ARTICLE_SPECS = {
    "core.rescale-cfg": {
        "directory": "rescale-cfg",
        "classType": "RescaleCFG",
        "module": "comfy_extras.nodes_model_advanced",
        "category": "model/patch",
        "fingerprint": "sha256:1afd317ca7234700c709fa2ef2d55ebcece4eb5a6c01f6b0ae99e95a2050e78b",
        "recipe": "recipe.rescale-vprediction-cfg",
    },
    "core.model-compute-dtype": {
        "directory": "model-compute-dtype",
        "classType": "ModelComputeDtype",
        "module": "comfy_extras.nodes_model_advanced",
        "category": "advanced/debug",
        "fingerprint": "sha256:a435b6ee7bfb3a6e583c812adbbd372dc9e50099640cc70797426d68691863a5",
        "recipe": "recipe.force-model-compute-fp32",
    },
    "core.model-attention-backend": {
        "directory": "model-attention-backend",
        "classType": "ModelAttentionBackend",
        "module": "comfy_extras.nodes_model_advanced",
        "category": "model/patch",
        "fingerprint": "sha256:ec8a3bcba2a453a35961251adf73c2581c02f4c5ec7dac1c54bc3ce2f32ea3a7",
        "recipe": "recipe.force-pytorch-attention",
    },
    "core.renorm-cfg": {
        "directory": "renorm-cfg",
        "classType": "RenormCFG",
        "module": "comfy_extras.nodes_lumina2",
        "category": "model/patch",
        "fingerprint": "sha256:5b917001cc6e2e2334f8ffec4f7f946cc52b927b0e07b8080a4b026923a23a67",
        "recipe": "recipe.lumina-renorm-cfg",
    },
}

RECIPE_DIRECTORIES = {
    "recipe.rescale-vprediction-cfg": "rescale-vprediction-cfg",
    "recipe.force-model-compute-fp32": "force-model-compute-fp32",
    "recipe.force-pytorch-attention": "force-pytorch-attention",
    "recipe.lumina-renorm-cfg": "lumina-renorm-cfg",
}

EXPECTED_FRAGMENT_NODES = {
    "recipe.rescale-vprediction-cfg": [
        ("RescaleCFG", {"multiplier": 0.7}),
        ("CFGGuider", {"cfg": 7.0}),
    ],
    "recipe.force-model-compute-fp32": [
        ("ModelComputeDtype", {"dtype": "fp32"}),
        ("CFGGuider", {"cfg": 4.0}),
    ],
    "recipe.force-pytorch-attention": [
        ("ModelAttentionBackend", {"attention": "pytorch attention"}),
        ("CFGGuider", {"cfg": 4.0}),
    ],
    "recipe.lumina-renorm-cfg": [
        ("RenormCFG", {"cfg_trunc": 100.0, "renorm_cfg": 1.0}),
        ("CFGGuider", {"cfg": 4.0}),
    ],
}

ROOT = catalog.ROOT
CONTENT = catalog.CONTENT
SOURCE = ROOT / ".comfyui-source-0.32.0"
INVENTORY = CONTENT / "runtime" / "comfyui-0.32.0.object-info.json"
REPLACEMENTS = CONTENT / "runtime" / "comfyui-0.32.0.node-replacements.json"
WORKFLOW_WHEEL = ROOT / ".upstream-cache" / "comfyui_workflow_templates_json-0.1.42-py3-none-any.whl"
WORKFLOW_SHA256 = "242982d65e1c51ca03d892bc1009bb6843f457e7dfc0c20afe6438770b7a14a3"
DOCS_WHEEL = ROOT / ".upstream-cache" / "comfyui_embedded_docs-0.5.9-py3-none-any.whl"
DOCS_SHA256 = "30afae432a71c96aa59421d0f37388c66ff6572b8cbeee8ff045e4d5f84f896c"
DOC_HASHES = {
    ("ModelComputeDtype", "en"): "60c96242d1d3f5da5381ede021e88b31efc4de02751593840a0465cdddd75a99",
    ("ModelComputeDtype", "ru"): "c7ac9f49230bcd80645ce728f4cabd325f8e9bc1427b1ce84b07298a3a84a43e",
    ("RenormCFG", "en"): "2acd99c38ee49de7b540d913283105704ece21c1e0b3c3ee7cf3eacd8cc335a1",
    ("RenormCFG", "ru"): "f50571d7339c4010276e279edbb995f825a8b02157b59e676760c34d9ddbdaae",
}
TARGET_TYPES = {spec["classType"] for spec in ARTICLE_SPECS.values()}


def article_path(spec: dict[str, Any]) -> Path:
    return CONTENT / "articles" / "core" / spec["directory"] / "manifest.json"


def all_article_ids() -> set[str]:
    result: set[str] = set()
    for path in (CONTENT / "articles").rglob("manifest.json"):
        payload = catalog.load_json(path)
        if isinstance(payload, dict) and isinstance(payload.get("articleId"), str):
            result.add(payload["articleId"])
    return result


def graph_records(payload: dict[str, Any]) -> Iterator[dict[str, Any]]:
    for node in payload.get("nodes", []):
        if isinstance(node, dict):
            yield {"scope": "root", "node": node}
    definitions = payload.get("definitions")
    subgraphs = definitions.get("subgraphs", []) if isinstance(definitions, dict) else []
    for subgraph in subgraphs:
        if not isinstance(subgraph, dict):
            continue
        for node in subgraph.get("nodes", []):
            if isinstance(node, dict):
                yield {"scope": "subgraph", "subgraph": subgraph, "node": node}


class ModelExecutionPatchContentTests(unittest.TestCase):
    def test_articles_recipes_ledgers_and_russian_contract(self) -> None:
        article_schema = catalog.load_json(CONTENT / "schemas" / "article.schema.v1.json")
        recipe_schema = catalog.load_json(CONTENT / "schemas" / "recipe.schema.v1.json")
        fragment_schema = catalog.load_json(CONTENT / "schemas" / "recipe-fragment.schema.v1.json")
        research_schema = catalog.load_json(CONTENT / "schemas" / "article-research.schema.v1.json")
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
            self.assertFalse(article["experimental"])
            self.assertEqual(spec["fingerprint"], article["editorial"]["schemaHash"])
            self.assertIn(spec["recipe"], [asset["id"] for asset in article["assets"]])

            relations = article["relations"]
            targets = list(relations["related"]) + list(relations["alternatives"])
            if relations["replacedBy"] is not None:
                targets.append(relations["replacedBy"])
            self.assertTrue(set(targets).issubset(article_ids), (article_id, set(targets) - article_ids))

            body = (path.parent / article["body"]).read_text(encoding="utf-8")
            self.assertEqual(10, len(re.findall(r"^## .+$", body, flags=re.MULTILINE)), article_id)
            self.assertIn("Редактор пока не проверил материал вручную.", body)
            self.assertNotIn("\ufffd", body)
            self.assertNotRegex(
                body.lower(),
                r"важно отметить|стоит отметить|в современном мире|революционн|"
                r"данная нода|давайте разбер|подводя итог|мощный инструмент|"
                r"не просто .{0,80}, а",
            )

            ledger = catalog.load_json(CONTENT / "research" / "reviews" / f"{article_id}.json")
            self.assertEqual([], catalog.json_schema_errors(ledger, research_schema))
            self.assertEqual("fact_checked", ledger["state"])
            self.assertEqual("automated_assisted", ledger["reviewMode"])
            self.assertFalse(ledger["checks"]["exampleExecuted"])
            self.assertTrue(ledger["checks"]["factsRecheckedAfterEditing"])
            self.assertTrue(any("Редактор пока" in gap for gap in ledger["knownGaps"]))

        self.assertEqual([], article_errors)

        inventory = catalog.load_json(INVENTORY)
        recipe_errors: list[str] = []
        for recipe_id, directory in RECIPE_DIRECTORIES.items():
            path = CONTENT / "recipes" / directory / "recipe.json"
            recipe = catalog.load_json(path)
            self.assertEqual([], catalog.json_schema_errors(recipe, recipe_schema))
            catalog.validate_recipe(path, recipe, article_ids, recipe_errors)
            self.assertEqual(recipe_id, recipe["recipeId"])
            self.assertEqual("in_review", recipe["editorial"]["state"])
            self.assertNotIn("workflow", recipe)
            body = (path.parent / recipe["body"]).read_text(encoding="utf-8")
            self.assertIn("Редактор пока не проверил материал вручную.", body)

            fragment_path = path.parent / recipe["fragment"]["path"]
            fragment = catalog.load_json(fragment_path)
            self.assertEqual([], catalog.json_schema_errors(fragment, fragment_schema))
            catalog.validate_fragment(fragment_path, fragment, recipe_errors)
            actual = [(node["classType"], node["settings"]) for node in fragment["nodes"]]
            self.assertEqual(EXPECTED_FRAGMENT_NODES[recipe_id], actual)
            self.assertTrue(all(node["classType"] in inventory for node in fragment["nodes"]))
            refs = {node["ref"] for node in fragment["nodes"]}
            self.assertTrue(all(item["to"] in refs for item in fragment["externalInputs"]))
            self.assertTrue(all(link["from"] in refs and link["to"] in refs for link in fragment["connections"]))

        self.assertEqual([], recipe_errors)

    def test_runtime_contracts_fingerprints_and_replacements(self) -> None:
        inventory = catalog.load_json(INVENTORY)
        for spec in ARTICLE_SPECS.values():
            definition = inventory[spec["classType"]]
            self.assertEqual(spec["module"], definition["python_module"])
            self.assertEqual(spec["category"], definition["category"])
            self.assertEqual(["MODEL"], definition["output"])
            self.assertEqual(["MODEL"], definition["output_name"])
            self.assertEqual(spec["fingerprint"], catalog.schema_fingerprint(spec["classType"], definition))
            for flag in ("deprecated", "experimental", "dev_only", "api_node", "output_node"):
                self.assertFalse(definition.get(flag, False), (spec["classType"], flag))

        rescale = inventory["RescaleCFG"]
        self.assertEqual(["model", "multiplier"], rescale["input_order"]["required"])
        self.assertEqual(
            {"default": 0.7, "min": 0.0, "max": 1.0, "step": 0.01},
            rescale["input"]["required"]["multiplier"][1],
        )

        dtype = inventory["ModelComputeDtype"]
        self.assertEqual(["model", "dtype"], dtype["input_order"]["required"])
        self.assertEqual(
            [["default", "fp32", "fp16", "bf16"], {"advanced": True}],
            dtype["input"]["required"]["dtype"],
        )
        self.assertEqual(["model precision", "change dtype"], dtype["search_aliases"])

        attention = inventory["ModelAttentionBackend"]
        self.assertEqual(["model", "attention"], attention["input_order"]["required"])
        self.assertEqual(
            [["pytorch attention", "comfy kitchen attention"]],
            attention["input"]["required"]["attention"],
        )

        renorm = inventory["RenormCFG"]
        self.assertEqual(
            ["model", "cfg_trunc", "renorm_cfg"],
            renorm["input_order"]["required"],
        )
        self.assertEqual(100, renorm["input"]["required"]["cfg_trunc"][1]["default"])
        self.assertEqual(1.0, renorm["input"]["required"]["renorm_cfg"][1]["default"])
        self.assertTrue(renorm["input"]["required"]["cfg_trunc"][1]["advanced"])
        self.assertTrue(renorm["input"]["required"]["renorm_cfg"][1]["advanced"])

        replacements = catalog.load_json(REPLACEMENTS)
        serialized = json.dumps(replacements, ensure_ascii=False)
        for class_type in TARGET_TYPES:
            self.assertNotIn(class_type, replacements)
            self.assertNotIn(f'"new_node_id": "{class_type}"', serialized)

    def test_exact_source_probe_and_source_contracts(self) -> None:
        result = run_probe(SOURCE)
        self.assertTrue(result["rescaleCFG"]["affineMultiplier"])
        self.assertFalse(result["rescaleCFG"]["sigmaZeroFinite"])
        self.assertFalse(result["rescaleCFG"]["constantFinite"])
        self.assertEqual(
            {"default": "None", "fp32": "torch.float32", "fp16": "torch.float16", "bf16": "torch.bfloat16"},
            result["computeDtype"],
        )
        self.assertEqual(["pytorch", "comfy_kitchen_int8"], result["attention"]["registered"])
        self.assertTrue(result["attention"]["unknownFallsBack"])
        self.assertEqual(["pytorch attention"], result["attention"]["unavailableOptions"])
        self.assertTrue(result["renormCFG"]["cfgBranchVerified"])
        self.assertTrue(result["renormCFG"]["truncationBoundaryUsesConditional"])
        self.assertTrue(result["renormCFG"]["batchTwoRejected"])
        self.assertFalse(result["renormCFG"]["zeroNormFinite"])

        advanced = (SOURCE / "comfy_extras" / "nodes_model_advanced.py").read_text(encoding="utf-8")
        lumina = (SOURCE / "comfy_extras" / "nodes_lumina2.py").read_text(encoding="utf-8")
        patcher = (SOURCE / "comfy" / "model_patcher.py").read_text(encoding="utf-8")
        helper = (SOURCE / "node_helpers.py").read_text(encoding="utf-8")
        for class_type in ("RescaleCFG", "ModelComputeDtype", "ModelAttentionBackend"):
            self.assertIn(f"class {class_type}", advanced)
            self.assertIn(f'"{class_type}": {class_type}', advanced)
        self.assertIn("class RenormCFG(io.ComfyNode):", lumina)
        self.assertIn("RenormCFG,", lumina)
        self.assertIn("torch.std(cond, dim=(1,2,3), keepdim=True)", advanced)
        self.assertIn("#rescale cfg has to be done on v-pred model output", advanced)
        self.assertIn("def VALIDATE_INPUTS(s, attention):\n        return True", advanced)
        self.assertIn("get_attention_function(attention_name, None)", advanced)
        self.assertIn("if new_pos_norm >= max_new_norm:", lumina)
        self.assertIn("if timestep[0] < cfg_trunc:", lumina)
        self.assertIn('self.force_cast_weights = True', patcher)
        self.assertIn('self.patches_uuid = uuid.uuid4()', patcher)
        self.assertIn('if string == "bf16":', helper)
        self.assertIn("return torch.bfloat16", helper)

    def test_pinned_embedded_docs_presence_absence_and_hashes(self) -> None:
        self.assertEqual(DOCS_SHA256, hashlib.sha256(DOCS_WHEEL.read_bytes()).hexdigest())
        with zipfile.ZipFile(DOCS_WHEEL) as archive:
            names = set(archive.namelist())
            for (class_type, locale), expected_hash in DOC_HASHES.items():
                path = f"comfyui_embedded_docs/docs/{class_type}/{locale}.md"
                self.assertIn(path, names)
                self.assertEqual(expected_hash, hashlib.sha256(archive.read(path)).hexdigest())
            for class_type in ("RescaleCFG", "ModelAttentionBackend"):
                self.assertNotIn(f"comfyui_embedded_docs/docs/{class_type}/en.md", names)
                self.assertNotIn(f"comfyui_embedded_docs/docs/{class_type}/ru.md", names)

    def test_workflow_wheel_census_and_lumina_adjacent_case(self) -> None:
        self.assertEqual(WORKFLOW_SHA256, hashlib.sha256(WORKFLOW_WHEEL.read_bytes()).hexdigest())
        json_members = 0
        root_graphs = 0
        subgraphs = 0
        target_records: list[tuple[str, str]] = []
        lumina: dict[str, Any] | None = None

        with zipfile.ZipFile(WORKFLOW_WHEEL) as archive:
            for member in archive.namelist():
                if not member.endswith(".json"):
                    continue
                json_members += 1
                payload = json.loads(archive.read(member))
                if isinstance(payload, dict) and isinstance(payload.get("nodes"), list):
                    root_graphs += 1
                if isinstance(payload, dict):
                    definitions = payload.get("definitions")
                    if isinstance(definitions, dict):
                        subgraphs += len(definitions.get("subgraphs", []))
                    for record in graph_records(payload):
                        class_type = record["node"].get("type")
                        if class_type in TARGET_TYPES:
                            target_records.append((member, class_type))
                if member.endswith("/image_netayume_lumina_t2i.json"):
                    lumina = payload

        self.assertEqual(512, json_members)
        self.assertEqual(496, root_graphs)
        self.assertEqual(272, subgraphs)
        self.assertEqual([], target_records)
        self.assertIsNotNone(lumina)
        assert lumina is not None
        self.assertEqual("9ae6082b-c7f4-433c-9971-7a8f65a3ea65", lumina["id"])
        subgraph = next(
            item for item in lumina["definitions"]["subgraphs"]
            if item["id"] == "3649d32d-3c81-4249-9e89-a1fe12609f65"
        )
        nodes = {node["id"]: node for node in subgraph["nodes"]}
        self.assertEqual("ModelSamplingAuraFlow", nodes[32]["type"])
        self.assertEqual([4], nodes[32]["widgets_values"])
        self.assertEqual("KSampler", nodes[33]["type"])
        self.assertEqual([0, "randomize", 30, 4, "res_multistep", "simple", 1], nodes[33]["widgets_values"])
        self.assertNotIn("RenormCFG", {node.get("type") for node in subgraph["nodes"]})
        links = {
            (link["origin_id"], link["target_id"], link["type"])
            for link in subgraph["links"]
        }
        self.assertIn((34, 32, "MODEL"), links)
        self.assertIn((32, 33, "MODEL"), links)


if __name__ == "__main__":
    unittest.main()
