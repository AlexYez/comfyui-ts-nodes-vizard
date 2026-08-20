from __future__ import annotations

import base64
import csv
import hashlib
import io
import json
import re
import unittest
import zipfile
from pathlib import Path

from tools import catalog
from tools.tests.model_saver_synthetic_probe import run_probe


SOURCE = catalog.ROOT / ".comfyui-source-0.32.0"
INVENTORY = catalog.CONTENT / "runtime" / "comfyui-0.32.0.object-info.json"
REPLACEMENTS = catalog.CONTENT / "runtime" / "comfyui-0.32.0.node-replacements.json"
WORKFLOW_WHEEL = catalog.ROOT / ".upstream-cache" / "comfyui_workflow_templates_json-0.1.42-py3-none-any.whl"
WORKFLOW_SHA256 = "242982d65e1c51ca03d892bc1009bb6843f457e7dfc0c20afe6438770b7a14a3"
DOCS_WHEEL = catalog.ROOT / ".upstream-cache" / "comfyui_embedded_docs-0.5.9-py3-none-any.whl"
DOCS_SHA256 = "30afae432a71c96aa59421d0f37388c66ff6572b8cbeee8ff045e4d5f84f896c"

ARTICLE_SPECS = {
    "core.checkpoint-save": {
        "directory": "checkpoint-save",
        "classType": "CheckpointSave",
        "fingerprint": "sha256:871a9ebfff7c803bfd46924839e2f4ece21f6fc245cf760282f2bb045d1aeccd",
        "recipe": "recipe.checkpoint-save-export",
        "recipeDirectory": "checkpoint-save-export",
        "required": ["model", "clip", "vae", "filename_prefix"],
        "external": {"model": "MODEL", "clip": "CLIP", "vae": "VAE"},
        "prefix": "checkpoints/wizard-merged",
        "default": "checkpoints/ComfyUI",
    },
    "core.clip-save": {
        "directory": "clip-save",
        "classType": "CLIPSave",
        "fingerprint": "sha256:bcb4b8813dd25bf03829902202d071627eda7417dfe5a18d94e7914f7c9eb12e",
        "recipe": "recipe.clip-save-export",
        "recipeDirectory": "clip-save-export",
        "required": ["clip", "filename_prefix"],
        "external": {"clip": "CLIP"},
        "prefix": "clip/wizard-encoder",
        "default": "clip/ComfyUI",
    },
    "core.vae-save": {
        "directory": "vae-save",
        "classType": "VAESave",
        "fingerprint": "sha256:e5a29dc13db67771a7c802fd28188c4f36fe5006c6e01b3237e93a898c5cec77",
        "recipe": "recipe.vae-save-export",
        "recipeDirectory": "vae-save-export",
        "required": ["vae", "filename_prefix"],
        "external": {"vae": "VAE"},
        "prefix": "vae/wizard-vae",
        "default": "vae/ComfyUI_vae",
    },
    "core.model-save": {
        "directory": "model-save",
        "classType": "ModelSave",
        "fingerprint": "sha256:72ab14234c202d2295bcf27311f564ff53f3905fd2626b855cec673a584a49f1",
        "recipe": "recipe.model-save-export",
        "recipeDirectory": "model-save-export",
        "required": ["model", "filename_prefix"],
        "external": {"model": "MODEL"},
        "prefix": "diffusion_models/wizard-model",
        "default": "diffusion_models/ComfyUI",
    },
}
TARGET_TYPES = {spec["classType"] for spec in ARTICLE_SPECS.values()}
EXPECTED_H2 = [
    "Что делает нода",
    "Место в графе",
    "Входы",
    "Выходы",
    "Как работает внутри",
    "Настройки",
    "Пример подключения",
    "Частые ошибки",
    "Ограничения и производительность",
    "Совместимость и источники",
]


def _all_article_ids() -> set[str]:
    result: set[str] = set()
    for path in (catalog.CONTENT / "articles").rglob("manifest.json"):
        payload = catalog.load_json(path)
        if isinstance(payload, dict) and isinstance(payload.get("articleId"), str):
            result.add(payload["articleId"])
    return result


class ModelSaverContentTests(unittest.TestCase):
    def test_batch_article_recipe_and_runtime_identities_are_unique(self) -> None:
        article_ids: dict[str, list[Path]] = {}
        runtime_ids: dict[tuple[str, str, str], list[Path]] = {}
        recipe_ids: dict[str, list[Path]] = {}
        for path in (catalog.CONTENT / "articles").rglob("manifest.json"):
            payload = catalog.load_json(path)
            if not isinstance(payload, dict):
                continue
            article_id = payload.get("articleId")
            if isinstance(article_id, str):
                article_ids.setdefault(article_id, []).append(path)
            identity = payload.get("runtimeIdentity")
            if isinstance(identity, dict):
                key = (
                    str(identity.get("packageId")),
                    str(identity.get("pythonModule")),
                    str(identity.get("classType")),
                )
                runtime_ids.setdefault(key, []).append(path)
        for path in (catalog.CONTENT / "recipes").rglob("recipe.json"):
            payload = catalog.load_json(path)
            if isinstance(payload, dict) and isinstance(payload.get("recipeId"), str):
                recipe_ids.setdefault(payload["recipeId"], []).append(path)

        for article_id, spec in ARTICLE_SPECS.items():
            self.assertEqual(1, len(article_ids.get(article_id, [])), article_id)
            identity = ("comfy-core", "comfy_extras.nodes_model_merging", spec["classType"])
            self.assertEqual(1, len(runtime_ids.get(identity, [])), identity)
            self.assertEqual(1, len(recipe_ids.get(spec["recipe"], [])), spec["recipe"])

    def test_articles_recipes_ledgers_and_russian_contract(self) -> None:
        article_schema = catalog.load_json(catalog.CONTENT / "schemas" / "article.schema.v1.json")
        recipe_schema = catalog.load_json(catalog.CONTENT / "schemas" / "recipe.schema.v1.json")
        fragment_schema = catalog.load_json(catalog.CONTENT / "schemas" / "recipe-fragment.schema.v1.json")
        research_schema = catalog.load_json(catalog.CONTENT / "schemas" / "article-research.schema.v1.json")
        article_ids = _all_article_ids()
        article_errors: list[str] = []
        recipe_errors: list[str] = []

        for article_id, spec in ARTICLE_SPECS.items():
            article_path = catalog.CONTENT / "articles" / "core" / spec["directory"] / "manifest.json"
            article = catalog.load_json(article_path)
            self.assertEqual([], catalog.json_schema_errors(article, article_schema), article_id)
            catalog.validate_article(article_path, article, article_errors)
            self.assertEqual(article_id, article["articleId"])
            self.assertEqual("draft", article["status"])
            self.assertEqual("in_review", article["editorial"]["state"])
            self.assertFalse(article["experimental"])
            self.assertEqual(spec["fingerprint"], article["editorial"]["schemaHash"])
            self.assertEqual([], article["runtimeIdentity"]["aliases"])
            self.assertEqual("comfy_extras.nodes_model_merging", article["runtimeIdentity"]["pythonModule"])
            self.assertIn(spec["recipe"], [asset["id"] for asset in article["assets"]])
            relations = set(article["relations"]["related"] + article["relations"]["alternatives"])
            if article["relations"]["replacedBy"]:
                relations.add(article["relations"]["replacedBy"])
            self.assertTrue(relations.issubset(article_ids), (article_id, relations - article_ids))

            body = (article_path.parent / article["body"]).read_text(encoding="utf-8")
            headings = re.findall(r"^## (.+)$", body, flags=re.MULTILINE)
            self.assertEqual(EXPECTED_H2, headings, article_id)
            self.assertIn("Редактор пока не проверил материал вручную.", body)
            self.assertNotIn("\ufffd", body)
            self.assertNotRegex(
                body.lower(),
                r"важно отметить|стоит отметить|в современном мире|революционн|"
                r"данная нода|давайте разбер|подводя итог|мощный инструмент|"
                r"не просто .{0,80}, а",
            )

            ledger_path = catalog.CONTENT / "research" / "reviews" / f"{article_id}.json"
            ledger = catalog.load_json(ledger_path)
            self.assertEqual([], catalog.json_schema_errors(ledger, research_schema), article_id)
            self.assertEqual("fact_checked", ledger["state"])
            self.assertEqual("automated_assisted", ledger["reviewMode"])
            self.assertTrue(ledger["checks"]["exampleSchemaValidated"])
            self.assertFalse(ledger["checks"]["exampleExecuted"])
            self.assertTrue(ledger["checks"]["factsRecheckedAfterEditing"])
            self.assertIn("Редактор пока не проверил материал вручную.", ledger["knownGaps"])

            recipe_path = catalog.CONTENT / "recipes" / spec["recipeDirectory"] / "recipe.json"
            recipe = catalog.load_json(recipe_path)
            self.assertEqual([], catalog.json_schema_errors(recipe, recipe_schema), spec["recipe"])
            catalog.validate_recipe(recipe_path, recipe, article_ids, recipe_errors)
            self.assertEqual(spec["recipe"], recipe["recipeId"])
            self.assertEqual("in_review", recipe["editorial"]["state"])
            self.assertNotIn("workflow", recipe)
            recipe_body = (recipe_path.parent / recipe["body"]).read_text(encoding="utf-8")
            self.assertIn("Редактор пока не проверил материал вручную.", recipe_body)

            fragment_path = recipe_path.parent / recipe["fragment"]["path"]
            fragment = catalog.load_json(fragment_path)
            self.assertEqual([], catalog.json_schema_errors(fragment, fragment_schema), spec["recipe"])
            catalog.validate_fragment(fragment_path, fragment, recipe_errors)
            self.assertEqual([], fragment["connections"])
            self.assertEqual(1, len(fragment["nodes"]))
            node = fragment["nodes"][0]
            self.assertEqual(spec["classType"], node["classType"])
            self.assertEqual({"filename_prefix": spec["prefix"]}, node["settings"])
            external = {entry["input"]: entry["type"] for entry in fragment["externalInputs"]}
            self.assertEqual(spec["external"], external)

        self.assertEqual([], article_errors)
        self.assertEqual([], recipe_errors)

    def test_runtime_fingerprints_flags_inputs_outputs_and_replacements(self) -> None:
        inventory = catalog.load_json(INVENTORY)
        replacements = catalog.load_json(REPLACEMENTS)
        replacement_text = json.dumps(replacements, ensure_ascii=False)
        for spec in ARTICLE_SPECS.values():
            class_type = spec["classType"]
            definition = inventory[class_type]
            self.assertEqual("comfy_extras.nodes_model_merging", definition["python_module"])
            self.assertEqual("model/merging", definition["category"])
            self.assertEqual(spec["required"], definition["input_order"]["required"])
            self.assertEqual(["prompt", "extra_pnginfo"], definition["input_order"]["hidden"])
            self.assertEqual(spec["default"], definition["input"]["required"]["filename_prefix"][1]["default"])
            self.assertEqual([], definition["output"])
            self.assertEqual([], definition["output_name"])
            self.assertEqual([], definition["output_is_list"])
            self.assertTrue(definition["output_node"])
            for flag in ("deprecated", "experimental", "dev_only", "api_node"):
                self.assertFalse(definition.get(flag, False), (class_type, flag))
            self.assertEqual(spec["fingerprint"], catalog.schema_fingerprint(class_type, definition))
            self.assertNotIn(class_type, replacements)
            self.assertNotIn(class_type, replacement_text)

        self.assertEqual(["save model", "export checkpoint", "merge save"], inventory["CheckpointSave"]["search_aliases"])
        self.assertEqual(["export model", "checkpoint save"], inventory["ModelSave"]["search_aliases"])
        self.assertEqual([], inventory["CLIPSave"]["search_aliases"])
        self.assertEqual([], inventory["VAESave"]["search_aliases"])

    def test_pinned_source_save_contract_and_docs_discrepancies(self) -> None:
        self.assertEqual(
            "c2bcbecd82ec5ae66594340b395c24ef0217b238",
            (SOURCE / ".git" / "HEAD").read_text(encoding="ascii").strip(),
        )
        merging = (SOURCE / "comfy_extras" / "nodes_model_merging.py").read_text(encoding="utf-8")
        folder_paths = (SOURCE / "folder_paths.py").read_text(encoding="utf-8")
        sd = (SOURCE / "comfy" / "sd.py").read_text(encoding="utf-8")
        utils = (SOURCE / "comfy" / "utils.py").read_text(encoding="utf-8")

        for class_type in TARGET_TYPES:
            self.assertIn(f'class {class_type}:', merging)
            self.assertIn(f'"{class_type}": {class_type}', merging)
        self.assertIn('f"{filename}_{counter:05}_.safetensors"', merging)
        self.assertIn('"stable-diffusion-v3-medium" #TODO: other SD3 variants', merging)
        self.assertIn('metadata["modelspec.predict_key"] = "epsilon"', merging)
        self.assertIn('metadata["modelspec.predict_key"] = "v"', merging)
        self.assertIn('extra_keys["edm_vpred.sigma_max"]', merging)
        self.assertIn('extra_keys["v_pred"] = torch.tensor([])', merging)
        self.assertIn('extra_keys["ztsnr"] = torch.tensor([])', merging)
        self.assertIn('for prefix in ["clip_l.", "clip_g.", "clip_h.", "t5xxl."', merging)
        self.assertIn('replace_prefix["transformer."] = ""', merging)
        self.assertIn('metadata["format"] = "pt"', merging)
        self.assertIn('comfy.utils.save_torch_file(vae.get_sd()', merging)
        self.assertIn('save_checkpoint(model, filename_prefix=filename_prefix', merging)

        self.assertIn("os.path.realpath(directory)", folder_paths)
        self.assertIn("os.path.commonpath((directory, target)) == directory", folder_paths)
        self.assertIn("os.listdir(full_output_folder)", folder_paths)
        self.assertNotIn("threading.Lock", folder_paths)
        self.assertIn("clip.state_dict_for_saving()", sd)
        self.assertIn("vae_sd = vae.get_sd()", sd)
        self.assertIn("model.state_dict_for_saving(clip_sd, vae_sd, clip_vision_sd)", sd)
        self.assertIn("if not t.is_contiguous():", sd)
        self.assertIn("safetensors.torch.save_file", utils)

        self.assertEqual(DOCS_SHA256, hashlib.sha256(DOCS_WHEEL.read_bytes()).hexdigest())
        expected_hashes = {
            "comfyui_embedded_docs/docs/CheckpointSave/en.md": "9ac9ded7fd6dffbdc007e083ae219ff0e020cc5f84d524196127135bcef2d6fc",
            "comfyui_embedded_docs/docs/CheckpointSave/ru.md": "1f8a7eb54f04b4abcea5d6f4163e44dd3f6787e215b2547e101324981873fb72",
            "comfyui_embedded_docs/docs/ModelSave/en.md": "9710ad4b0f62b59ad5d04ba8b6386a5ef9a7560a3591c9b8d4ded954a681ede4",
            "comfyui_embedded_docs/docs/ModelSave/ru.md": "5781f576c8dba2ebbb56e5773854ef74612acdeb4c44514a204b0a0f968a0252",
        }
        with zipfile.ZipFile(DOCS_WHEEL) as archive:
            self.assertIsNone(archive.testzip())
            names = set(archive.namelist())
            for path, expected_hash in expected_hashes.items():
                self.assertIn(path, names)
                self.assertEqual(expected_hash, hashlib.sha256(archive.read(path)).hexdigest())
                text = archive.read(path).decode("utf-8").lower()
                self.assertRegex(text, r"ai[- ]generated|создана с помощью ии")
            for absent in ("CLIPSave", "VAESave"):
                self.assertFalse(any(f"/docs/{absent}/" in name for name in names))
            checkpoint_en = archive.read("comfyui_embedded_docs/docs/CheckpointSave/en.md").decode("utf-8")
            self.assertIn("output/checkpoints/", checkpoint_en)
            model_ru = archive.read("comfyui_embedded_docs/docs/ModelSave/ru.md").decode("utf-8")
            self.assertIn("Вот перевод", model_ru)

    def test_workflow_wheel_integrity_and_exhaustive_zero_census(self) -> None:
        self.assertEqual(WORKFLOW_SHA256, hashlib.sha256(WORKFLOW_WHEEL.read_bytes()).hexdigest())
        json_members = 0
        root_graphs = 0
        subgraphs = 0
        exact_hits: list[tuple[str, str, str]] = []
        scalar_hits: list[tuple[str, str]] = []
        raw_hits: list[tuple[str, str]] = []
        with zipfile.ZipFile(WORKFLOW_WHEEL) as archive:
            self.assertIsNone(archive.testzip())
            self.assertEqual(517, len(archive.namelist()))
            record_name = next(name for name in archive.namelist() if name.endswith(".dist-info/RECORD"))
            rows = list(csv.reader(io.StringIO(archive.read(record_name).decode("utf-8"))))
            self.assertEqual(517, len(rows))
            verified = 0
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
                verified += 1
            self.assertEqual(516, verified)

            def scalars(value: object):
                if isinstance(value, dict):
                    for child in value.values():
                        yield from scalars(child)
                elif isinstance(value, list):
                    for child in value:
                        yield from scalars(child)
                else:
                    yield value

            for name in archive.namelist():
                if not name.endswith(".json") or "/templates/" not in name:
                    continue
                json_members += 1
                data = archive.read(name)
                payload = json.loads(data)
                values = list(scalars(payload))
                for class_type in TARGET_TYPES:
                    if class_type.encode() in data:
                        raw_hits.append((name, class_type))
                    if class_type in values:
                        scalar_hits.append((name, class_type))
                if not isinstance(payload, dict) or not isinstance(payload.get("nodes"), list):
                    continue
                root_graphs += 1
                graphs = [("root", payload)]
                definitions = payload.get("definitions", {})
                if isinstance(definitions, dict) and isinstance(definitions.get("subgraphs"), list):
                    subgraphs += len(definitions["subgraphs"])
                    graphs.extend((f"subgraph[{index}]", graph) for index, graph in enumerate(definitions["subgraphs"]))
                for location, graph in graphs:
                    if not isinstance(graph, dict):
                        continue
                    for node in graph.get("nodes", []):
                        if isinstance(node, dict) and node.get("type") in TARGET_TYPES:
                            exact_hits.append((name, location, node["type"]))

        self.assertEqual(512, json_members)
        self.assertEqual(496, root_graphs)
        self.assertEqual(272, subgraphs)
        self.assertEqual([], exact_hits)
        self.assertEqual([], scalar_hits)
        self.assertEqual([], raw_hits)

    def test_exact_source_temp_directory_probe(self) -> None:
        result = run_probe(SOURCE)
        self.assertFalse(result["workflowExampleExecuted"])
        self.assertEqual([1, 1], result["path"]["unreservedCounters"])
        self.assertEqual(5, result["path"]["existingCounterNext"])
        self.assertTrue(result["path"]["traversalRejected"])
        self.assertEqual(
            [
                "clip/test_clip_l_00001_.safetensors",
                "clip/test_clip_g_00001_.safetensors",
                "clip/test_00001_.safetensors",
            ],
            result["clip"]["files"],
        )
        self.assertEqual(
            [["encoder.weight"], ["text_projection"], ["custom.bias", "shared.weight"]],
            result["clip"]["keys"],
        )
        self.assertEqual(2, result["vae"]["getSdCalls"])
        checkpoint = result["checkpoint"]
        self.assertTrue(checkpoint["clip"])
        self.assertTrue(checkpoint["vae"])
        self.assertEqual("stable-diffusion-xl-v1-edit", checkpoint["metadata"]["modelspec.architecture"])
        self.assertEqual("v", checkpoint["metadata"]["modelspec.predict_key"])
        self.assertEqual(
            ["edm_vpred.sigma_max", "edm_vpred.sigma_min", "v_pred", "ztsnr"],
            checkpoint["extraKeys"],
        )
        model_only = result["modelOnlyMetadataDisabled"]
        self.assertFalse(model_only["clip"])
        self.assertFalse(model_only["vae"])
        self.assertEqual({"modelspec.predict_key": "epsilon"}, model_only["metadata"])


if __name__ == "__main__":
    unittest.main()
