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
from typing import Any

from tools import catalog


ARTICLE_SPECS = {
    "core.make-training-dataset": {
        "directory": "make-training-dataset",
        "classType": "MakeTrainingDataset",
        "fingerprint": "sha256:0a13b38b6eac0734e86473bf9bc2c1572f020c9ea25aca914cdee7ecef30dab1",
        "recipe": "recipe.make-training-dataset-basic",
        "isInputList": True,
        "outputNode": False,
        "outputs": ["LATENT", "CONDITIONING"],
        "outputNames": ["latents", "conditioning"],
        "outputLists": [True, True],
        "required": ["images", "vae", "clip"],
        "optional": ["texts"],
    },
    "core.save-training-dataset": {
        "directory": "save-training-dataset",
        "classType": "SaveTrainingDataset",
        "fingerprint": "sha256:9ef540ad0a95b8804bcebd4cfde93cb40b82be5a4872a8051c7eb4348d141bfc",
        "recipe": "recipe.save-training-dataset-basic",
        "isInputList": True,
        "outputNode": True,
        "outputs": [],
        "outputNames": [],
        "outputLists": [],
        "required": ["latents", "conditioning", "folder_name", "shard_size"],
        "optional": [],
    },
    "core.load-training-dataset": {
        "directory": "load-training-dataset",
        "classType": "LoadTrainingDataset",
        "fingerprint": "sha256:bbcd14ef24bf0157948739d4f0b9caefb79cc9075bb6d102a78590bee92e6df3",
        "recipe": "recipe.load-training-dataset-basic",
        "isInputList": False,
        "outputNode": False,
        "outputs": ["LATENT", "CONDITIONING"],
        "outputNames": ["latents", "conditioning"],
        "outputLists": [True, True],
        "required": ["folder_name"],
        "optional": [],
    },
    "core.resolution-bucket": {
        "directory": "resolution-bucket",
        "classType": "ResolutionBucket",
        "fingerprint": "sha256:80b24b07bf2a73904e5dd4c0a338e9a75eba6a2a5cf336e4fcc4586872ce25b1",
        "recipe": "recipe.resolution-bucket-basic",
        "isInputList": True,
        "outputNode": False,
        "outputs": ["LATENT", "CONDITIONING"],
        "outputNames": ["latents", "conditioning"],
        "outputLists": [True, True],
        "required": ["latents", "conditioning"],
        "optional": [],
    },
}

RECIPE_DIRECTORIES = {
    "recipe.make-training-dataset-basic": "make-training-dataset-basic",
    "recipe.save-training-dataset-basic": "save-training-dataset-basic",
    "recipe.load-training-dataset-basic": "load-training-dataset-basic",
    "recipe.resolution-bucket-basic": "resolution-bucket-basic",
}

EXPECTED_FRAGMENT_NODES = {
    "recipe.make-training-dataset-basic": [("MakeTrainingDataset", {})],
    "recipe.save-training-dataset-basic": [
        (
            "SaveTrainingDataset",
            {
                "folder_name": "nodes_wizard_training_example",
                "shard_size": 1000,
            },
        )
    ],
    "recipe.load-training-dataset-basic": [
        ("LoadTrainingDataset", {"folder_name": "SELECT_SAVED_DATASET"})
    ],
    "recipe.resolution-bucket-basic": [("ResolutionBucket", {})],
}

FULL_INVENTORY = catalog.CONTENT / "runtime" / "comfyui-0.32.0.object-info.json"
REPLACEMENTS = (
    catalog.CONTENT / "runtime" / "comfyui-0.32.0.node-replacements.json"
)
REPLACEMENTS_SHA256 = (
    "4d9e22176cbddd8c309707d434f011854cd768f92146586bf9e17c01e93ae5b6"
)
SOURCE = catalog.ROOT / ".comfyui-source-0.32.0"
WORKFLOW_WHEEL = (
    catalog.ROOT
    / ".upstream-cache"
    / "comfyui_workflow_templates_json-0.1.42-py3-none-any.whl"
)
WORKFLOW_WHEEL_SHA256 = (
    "242982d65e1c51ca03d892bc1009bb6843f457e7dfc0c20afe6438770b7a14a3"
)
EMBEDDED_DOCS_WHEEL = (
    catalog.ROOT
    / ".upstream-cache"
    / "comfyui_embedded_docs-0.5.9-py3-none-any.whl"
)
EMBEDDED_DOCS_WHEEL_SHA256 = (
    "30afae432a71c96aa59421d0f37388c66ff6572b8cbeee8ff045e4d5f84f896c"
)
EMBEDDED_DOC_HASHES = {
    "MakeTrainingDataset": {
        "en": "d699d0082ff690a9ee826565451457ebd27ccf0546e299e333de1f5811a6293f",
        "ru": "5761646e78011a5bfdba1199e01ea5b4731ae282f6556535aaa9fc21059e9f8b",
    },
    "SaveTrainingDataset": {
        "en": "c0b8ad582437ecf2b28ea346d2c75d53fb45a017fe69600b9df230c2814fb05d",
        "ru": "ea89633df8a995608aa9758aeef7b1d893f47ea4de8f2a9e9cb72841a7ebfeef",
    },
    "LoadTrainingDataset": {
        "en": "a9a2468c2a60fc5dd9f005856428c9a43d8dc4ae00bdb23129faf8bdc6b22bd2",
        "ru": "2dd3de246f25283ec281cb68eb2485ad46320dfa00f20c0e6c2f4ba84d47e823",
    },
    "ResolutionBucket": {
        "en": "2e6cb9353c83e46a02f20a57474d5ad36418cb3687cda299a8d2bd08420699fe",
        "ru": "d2a1a73a787a50b0b509d627069247b0beecc49833e6fac418c56dbd00374ccf",
    },
}
SYNTHETIC_PROBE = Path(__file__).with_name(
    "dataset_training_pipeline_synthetic_probe.py"
)


def article_path(spec: dict[str, Any]) -> Path:
    return (
        catalog.CONTENT
        / "articles"
        / "core"
        / spec["directory"]
        / "manifest.json"
    )


def recipe_path(recipe_id: str) -> Path:
    return (
        catalog.CONTENT
        / "recipes"
        / RECIPE_DIRECTORIES[recipe_id]
        / "recipe.json"
    )


def all_ids(root: Path, filename: str, field: str) -> list[str]:
    values: list[str] = []
    for path in root.rglob(filename):
        payload = catalog.load_json(path)
        if isinstance(payload, dict) and isinstance(payload.get(field), str):
            values.append(payload[field])
    return values


def runtime_input_specs(runtime: dict[str, Any]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for group in ("required", "optional"):
        values = runtime.get("input", {}).get(group, {})
        if isinstance(values, dict):
            result.update(values)
    return result


def descriptor_type(descriptor: Any) -> Any:
    if not isinstance(descriptor, list) or not descriptor:
        return None
    value = descriptor[0]
    return "COMBO" if isinstance(value, list) or value == "COMBO" else value


class DatasetTrainingPipelineContentTests(unittest.TestCase):
    def test_articles_recipes_research_and_editorial_contracts(self) -> None:
        article_id_list = all_ids(
            catalog.CONTENT / "articles", "manifest.json", "articleId"
        )
        recipe_id_list = all_ids(
            catalog.CONTENT / "recipes", "recipe.json", "recipeId"
        )
        article_counts = Counter(article_id_list)
        recipe_counts = Counter(recipe_id_list)
        for article_id, spec in ARTICLE_SPECS.items():
            self.assertEqual(1, article_counts[article_id], article_id)
            self.assertEqual(1, recipe_counts[spec["recipe"]], spec["recipe"])
        article_ids = set(article_id_list)

        schemas = {
            "article": catalog.load_json(
                catalog.CONTENT / "schemas" / "article.schema.v1.json"
            ),
            "recipe": catalog.load_json(
                catalog.CONTENT / "schemas" / "recipe.schema.v1.json"
            ),
            "fragment": catalog.load_json(
                catalog.CONTENT / "schemas" / "recipe-fragment.schema.v1.json"
            ),
            "research": catalog.load_json(
                catalog.CONTENT / "schemas" / "article-research.schema.v1.json"
            ),
        }
        banned = re.compile(
            r"важно отметить|стоит отметить|следует отметить|в современном мире|"
            r"революционн|является незаменим|является мощн|\bдавайте\b|"
            r"глубже погруз|открывает новые|может показаться|позволяет вам|"
            r"подводя итог|в заключение|не просто .{0,80}, а",
            flags=re.IGNORECASE,
        )
        errors: list[str] = []

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
            self.assertEqual(
                {spec["recipe"]},
                {
                    asset["id"]
                    for asset in article["assets"]
                    if asset["type"] == "recipe"
                },
            )
            relations = article["relations"]
            targets = set(relations["related"] + relations["alternatives"])
            if relations["replacedBy"] is not None:
                targets.add(relations["replacedBy"])
            self.assertTrue(targets.issubset(article_ids), (article_id, targets))

            body = (path.parent / article["body"]).read_text(encoding="utf-8")
            self.assertEqual(
                10, len(re.findall(r"^## .+$", body, flags=re.MULTILINE)), article_id
            )
            self.assertNotIn("\ufffd", body)
            self.assertIsNone(banned.search(body), article_id)
            self.assertIn(spec["fingerprint"], body)
            self.assertRegex(body.lower(), r"официальн")

            research = catalog.load_json(
                catalog.CONTENT / "research" / "reviews" / f"{article_id}.json"
            )
            self.assertEqual([], catalog.json_schema_errors(research, schemas["research"]))
            self.assertEqual("fact_checked", research["state"])
            self.assertEqual("automated_assisted", research["reviewMode"])
            self.assertFalse(research["checks"]["exampleExecuted"])
            self.assertTrue(research["checks"]["russianEdited"])
            self.assertTrue(research["checks"]["factsRecheckedAfterEditing"])
            self.assertIn(
                "Статья ожидает человеческого утверждения.", research["knownGaps"]
            )

        for recipe_id in RECIPE_DIRECTORIES:
            path = recipe_path(recipe_id)
            recipe = catalog.load_json(path)
            self.assertEqual([], catalog.json_schema_errors(recipe, schemas["recipe"]))
            catalog.validate_recipe(path, recipe, article_ids, errors)
            self.assertNotIn("workflow", recipe)
            self.assertEqual("in_review", recipe["editorial"]["state"])
            self.assertIn("human approval pending", recipe["editorial"]["reviewedBy"])
            fragment_path = path.parent / recipe["fragment"]["path"]
            fragment = catalog.load_json(fragment_path)
            self.assertEqual([], catalog.json_schema_errors(fragment, schemas["fragment"]))
            catalog.validate_fragment(fragment_path, fragment, errors)
            self.assertEqual([], fragment["connections"])
            self.assertEqual(
                EXPECTED_FRAGMENT_NODES[recipe_id],
                [(node["classType"], node["settings"]) for node in fragment["nodes"]],
            )

        self.assertEqual([], errors)

    def test_runtime_fingerprints_flags_ports_and_fail_closed_fragments(self) -> None:
        nodes = catalog.object_info_nodes(catalog.load_json(FULL_INVENTORY))
        for article_id, spec in ARTICLE_SPECS.items():
            runtime = nodes[spec["classType"]]
            article = catalog.load_json(article_path(spec))
            self.assertEqual("comfy_extras.nodes_dataset", runtime["python_module"])
            self.assertEqual("model/training", runtime["category"])
            self.assertTrue(runtime.get("experimental", False))
            self.assertFalse(runtime.get("deprecated", False))
            self.assertFalse(runtime.get("dev_only", False))
            self.assertFalse(runtime.get("api_node", False))
            self.assertEqual(spec["isInputList"], runtime["is_input_list"])
            self.assertEqual(spec["outputNode"], runtime["output_node"])
            self.assertEqual(spec["outputs"], runtime["output"])
            self.assertEqual(spec["outputNames"], runtime["output_name"])
            self.assertEqual(spec["outputLists"], runtime["output_is_list"])
            self.assertEqual(spec["required"], runtime["input_order"]["required"])
            self.assertEqual(
                spec["optional"], runtime["input_order"].get("optional", [])
            )
            self.assertEqual(
                spec["fingerprint"],
                catalog.schema_fingerprint(spec["classType"], runtime),
                article_id,
            )
            self.assertEqual(spec["fingerprint"], article["editorial"]["schemaHash"])

        make = nodes["MakeTrainingDataset"]
        self.assertEqual("IMAGE", descriptor_type(make["input"]["required"]["images"]))
        self.assertEqual("VAE", descriptor_type(make["input"]["required"]["vae"]))
        self.assertEqual("CLIP", descriptor_type(make["input"]["required"]["clip"]))
        texts = make["input"]["optional"]["texts"]
        self.assertEqual("STRING", descriptor_type(texts))
        self.assertTrue(texts[1]["forceInput"])
        self.assertFalse(texts[1]["multiline"])

        save = nodes["SaveTrainingDataset"]
        folder = save["input"]["required"]["folder_name"]
        shard_size = save["input"]["required"]["shard_size"]
        self.assertEqual("STRING", descriptor_type(folder))
        self.assertEqual("training_dataset", folder[1]["default"])
        self.assertEqual("INT", descriptor_type(shard_size))
        self.assertEqual(
            {"default": 1000, "min": 1, "max": 100000, "advanced": True},
            {key: shard_size[1][key] for key in ("default", "min", "max", "advanced")},
        )

        load = nodes["LoadTrainingDataset"]
        load_folder = load["input"]["required"]["folder_name"]
        self.assertEqual("COMBO", descriptor_type(load_folder))
        self.assertEqual([], load_folder[1]["options"])
        self.assertNotIn("default", load_folder[1])

        for recipe_id in RECIPE_DIRECTORIES:
            path = recipe_path(recipe_id)
            recipe = catalog.load_json(path)
            fragment = catalog.load_json(path.parent / recipe["fragment"]["path"])
            node_by_ref = {node["ref"]: node for node in fragment["nodes"]}
            supplied = {ref: set(node["settings"]) for ref, node in node_by_ref.items()}
            for external in fragment["externalInputs"]:
                target = node_by_ref[external["to"]]
                descriptor = runtime_input_specs(nodes[target["classType"]])[
                    external["input"]
                ]
                self.assertEqual(external["type"], descriptor_type(descriptor))
                supplied[external["to"]].add(external["input"])

            for ref, node in node_by_ref.items():
                runtime = nodes[node["classType"]]
                self.assertTrue(
                    set(runtime["input"]["required"]).issubset(supplied[ref]),
                    (recipe_id, ref),
                )

        load_path = recipe_path("recipe.load-training-dataset-basic")
        load_recipe = catalog.load_json(load_path)
        load_fragment = catalog.load_json(
            load_path.parent / load_recipe["fragment"]["path"]
        )
        self.assertEqual(
            "SELECT_SAVED_DATASET",
            load_fragment["nodes"][0]["settings"]["folder_name"],
        )
        self.assertNotIn(
            "SELECT_SAVED_DATASET", load["input"]["required"]["folder_name"][1]["options"]
        )
        self.assertTrue(
            any("Ручной выбор" in item for item in load_recipe["requirements"])
        )
        self.assertIn(
            "Placeholder должен блокировать исполнение",
            (load_path.parent / load_recipe["body"]).read_text(encoding="utf-8"),
        )

    @unittest.skipUnless(SOURCE.exists(), "pinned ComfyUI source checkout is absent")
    def test_exact_pinned_source_path_format_rounding_and_replacements(self) -> None:
        dataset = (SOURCE / "comfy_extras" / "nodes_dataset.py").read_text(
            encoding="utf-8"
        )

        self.assertIn("def secure_subfolder_path(base_dir, folder_name):", dataset)
        self.assertIn("target = os.path.abspath(os.path.join(base_dir, folder_name))", dataset)
        self.assertIn("folder_paths.is_within_directory(base_dir, target)", dataset)
        self.assertIn("followlinks=True", dataset)
        self.assertIn('"metadata.json" in filenames', dataset)
        self.assertIn('any(f.endswith(".safetensors") for f in filenames)', dataset)
        self.assertIn('root = folder_paths.get_folder_paths("datasets")[0]', dataset)
        self.assertIn('roots = folder_paths.get_folder_paths("datasets")', dataset)
        self.assertIn("for root in roots:", dataset)

        resolution_start = dataset.index("class ResolutionBucket(io.ComfyNode):")
        make_start = dataset.index("class MakeTrainingDataset(io.ComfyNode):")
        save_start = dataset.index("class SaveTrainingDataset(io.ComfyNode):")
        load_start = dataset.index("class LoadTrainingDataset(io.ComfyNode):")
        extension_start = dataset.index("# ========== Extension Setup", load_start)
        resolution = dataset[resolution_start:make_start]
        make = dataset[make_start:save_start]
        save = dataset[save_start:load_start]
        load = dataset[load_start:extension_start]

        self.assertIn("if len(latents) != len(conditioning):", resolution)
        self.assertIn('samples = latent_dict["samples"]', resolution)
        self.assertIn("flat_conditions.append(cond[i])", resolution)
        self.assertIn("h, w = latent.shape[-2], latent.shape[-1]", resolution)
        self.assertIn("stacked_latents = torch.stack", resolution)
        self.assertIn('output_latents.append({"samples": stacked_latents})', resolution)
        self.assertNotIn("round(", resolution)
        self.assertNotIn("interpolate", resolution)

        self.assertIn("vae = vae[0]", make)
        self.assertIn("clip = clip[0]", make)
        self.assertIn('texts = [""]', make)
        self.assertIn("texts = texts * num_images", make)
        self.assertIn("vae.encode(img_tensor[:, :, :, :3])", make)
        self.assertIn('clip.tokenize("")', make)

        self.assertIn("folder_name = folder_name[0]", save)
        self.assertIn("shard_size = shard_size[0]", save)
        self.assertIn("output_dir = get_dataset_save_dir(folder_name)", save)
        self.assertIn("(num_samples + shard_size - 1) // shard_size", save)
        self.assertIn('shard_filename = f"shard_{shard_idx:04d}.pkl"', save)
        self.assertIn('"num_samples": num_samples', save)
        self.assertIn('"num_shards": num_shards', save)
        self.assertIn('"shard_size": shard_size', save)
        self.assertNotIn("tempfile", save)
        self.assertNotIn("os.replace", save)
        self.assertNotIn("os.remove", save)

        self.assertIn('if f.startswith("shard_") and f.endswith(".pkl")', load)
        self.assertIn("shard_files = sorted(", load)
        self.assertIn("torch.load(f, weights_only=True)", load)
        self.assertIn('all_latents.extend(shard_data["latents"])', load)
        self.assertIn('all_conditioning.extend(shard_data["conditioning"])', load)
        self.assertNotIn("metadata.json", load)

        self.assertEqual(
            REPLACEMENTS_SHA256, hashlib.sha256(REPLACEMENTS.read_bytes()).hexdigest()
        )
        replacement_text = REPLACEMENTS.read_text(encoding="utf-8")
        for spec in ARTICLE_SPECS.values():
            self.assertNotIn(spec["classType"], replacement_text)

    @unittest.skipUnless(
        EMBEDDED_DOCS_WHEEL.exists(), "pinned embedded-docs wheel is absent"
    )
    def test_embedded_docs_case_sensitive_members_hashes_and_gaps(self) -> None:
        self.assertEqual(
            EMBEDDED_DOCS_WHEEL_SHA256,
            hashlib.sha256(EMBEDDED_DOCS_WHEEL.read_bytes()).hexdigest(),
        )
        docs: dict[tuple[str, str], str] = {}
        with zipfile.ZipFile(EMBEDDED_DOCS_WHEEL) as archive:
            names = archive.namelist()
            for class_type, locales in EMBEDDED_DOC_HASHES.items():
                exact = [
                    name
                    for name in names
                    if re.search(rf"/{re.escape(class_type)}/(?:en|ru)\.md$", name)
                ]
                insensitive = [
                    name
                    for name in names
                    if re.search(
                        rf"/{re.escape(class_type)}/(?:en|ru)\.md$",
                        name,
                        flags=re.IGNORECASE,
                    )
                ]
                self.assertEqual(2, len(exact))
                self.assertEqual(exact, insensitive)
                for locale, expected_hash in locales.items():
                    member = f"comfyui_embedded_docs/docs/{class_type}/{locale}.md"
                    payload = archive.read(member)
                    self.assertEqual(expected_hash, hashlib.sha256(payload).hexdigest())
                    docs[(class_type, locale)] = payload.decode("utf-8")

        for class_type in EMBEDDED_DOC_HASHES:
            self.assertIn("AI-generated", docs[(class_type, "en")])
            self.assertNotIn("experimental", docs[(class_type, "en")].lower())
        self.assertIn("length n", docs[("MakeTrainingDataset", "en")])
        self.assertNotIn(":3", docs[("MakeTrainingDataset", "en")])
        self.assertIn("output directory", docs[("SaveTrainingDataset", "en")])
        self.assertIn("| STRING | No |", docs[("SaveTrainingDataset", "en")])
        self.assertNotIn("shard_0000.pkl", docs[("SaveTrainingDataset", "en")])
        self.assertIn("output directory", docs[("LoadTrainingDataset", "en")])
        self.assertIn("(default: \"training_dataset\")", docs[("LoadTrainingDataset", "en")])
        self.assertNotIn("weights_only", docs[("LoadTrainingDataset", "en")])
        self.assertIn("same height and width", docs[("ResolutionBucket", "en")])
        self.assertNotIn("round", docs[("ResolutionBucket", "en")].lower())
        self.assertIn("`изображения`", docs[("MakeTrainingDataset", "ru")])
        self.assertIn("выходном каталоге", docs[("SaveTrainingDataset", "ru")])

    @unittest.skipUnless(WORKFLOW_WHEEL.exists(), "official workflow wheel is absent")
    def test_exhaustive_workflow_census_has_no_case_sensitive_targets(self) -> None:
        self.assertEqual(
            WORKFLOW_WHEEL_SHA256,
            hashlib.sha256(WORKFLOW_WHEEL.read_bytes()).hexdigest(),
        )
        targets = {spec["classType"] for spec in ARTICLE_SPECS.values()}
        raw_hits: list[tuple[str, str]] = []
        type_hits: list[tuple[str, str, str]] = []
        root_workflows = root_nodes = subgraphs_count = subgraph_nodes = 0

        with zipfile.ZipFile(WORKFLOW_WHEEL) as archive:
            members = sorted(
                name
                for name in archive.namelist()
                if "/templates/" in name and name.endswith(".json")
            )
            self.assertEqual(512, len(members))
            for member in members:
                raw = archive.read(member).decode("utf-8")
                for target in targets:
                    if target in raw:
                        raw_hits.append((member, target))
                payload = json.loads(raw)
                if not isinstance(payload, dict):
                    continue
                nodes = payload.get("nodes")
                if isinstance(nodes, list):
                    root_workflows += 1
                    root_nodes += len(nodes)
                    type_hits.extend(
                        ("root", member, node["type"])
                        for node in nodes
                        if isinstance(node, dict) and node.get("type") in targets
                    )
                definitions = payload.get("definitions")
                subgraphs = (
                    definitions.get("subgraphs", [])
                    if isinstance(definitions, dict)
                    else []
                )
                for subgraph in subgraphs:
                    if not isinstance(subgraph, dict):
                        continue
                    subgraphs_count += 1
                    nodes = subgraph.get("nodes", []) or []
                    subgraph_nodes += len(nodes)
                    type_hits.extend(
                        ("subgraph", member, node["type"])
                        for node in nodes
                        if isinstance(node, dict) and node.get("type") in targets
                    )

        self.assertEqual(
            (496, 4083, 272, 4037, 8120),
            (
                root_workflows,
                root_nodes,
                subgraphs_count,
                subgraph_nodes,
                root_nodes + subgraph_nodes,
            ),
        )
        self.assertEqual([], raw_hits)
        self.assertEqual([], type_hits)

    @unittest.skipUnless(SOURCE.exists(), "pinned ComfyUI source checkout is absent")
    def test_exact_source_synthetic_execution_in_tempdir_not_fragment(self) -> None:
        candidates = [
            Path(os.environ.get("TEMP", ""))
            / "nodes-wizard-comfyui-v0.32.0-venv"
            / "Scripts"
            / "python.exe",
            Path(sys.executable),
        ]
        python = next((candidate for candidate in candidates if candidate.exists()), None)
        if python is None:
            self.skipTest("no Python interpreter for dataset training probe")
        env = os.environ.copy()
        env["PYTHONIOENCODING"] = "utf-8"
        result = subprocess.run(
            [str(python), str(SYNTHETIC_PROBE), str(SOURCE)],
            cwd=catalog.ROOT,
            env=env,
            text=True,
            encoding="utf-8",
            capture_output=True,
            timeout=120,
            check=False,
        )
        if result.returncode != 0 and python != Path(sys.executable):
            self.fail(result.stderr or result.stdout)
        if result.returncode != 0:
            self.skipTest(f"dataset training probe unavailable: {result.stderr}")
        payload = json.loads(result.stdout.strip().splitlines()[-1])

        made = payload["make"]
        self.assertEqual(
            [[1, 2, 4, 5], [1, 2, 6, 7], [1, 2, 3, 2]],
            made["latentShapes"],
        )
        self.assertEqual([["caption"], ["caption"], ["caption"]], made["singleCaptionRepeated"])
        self.assertEqual([[""], [""]], made["emptyCaptionsRepeated"])
        self.assertEqual([1, 1], made["batchedOuterItemCounts"])
        self.assertTrue(made["vaeReceivesFirstThreeChannels"])
        self.assertTrue(made["textMismatchRejected"])
        self.assertTrue(made["emptyImagesRejected"])

        bucket = payload["bucket"]
        self.assertEqual(
            [[3, 1, 4, 6], [1, 1, 8, 6], [1, 1, 5, 6]],
            bucket["bucketShapes"],
        )
        self.assertEqual(
            [
                ["condition-0", "condition-1", "condition-3"],
                ["condition-2"],
                ["condition-4"],
            ],
            bucket["bucketConditions"],
        )
        self.assertEqual([0, 0], bucket["emptyOutputs"])
        for key in (
            "extraLatentFieldsDropped",
            "firstSeenBucketOrder",
            "innerConditionExtraIgnored",
            "innerConditionShortRejected",
            "noResolutionRounding",
            "sameResolutionIncompatibleShapeRejected",
        ):
            self.assertTrue(bucket[key], key)

        saved = payload["save"]
        self.assertEqual(
            {"num_samples": 5, "num_shards": 3, "shard_size": 2},
            saved["ceilingShardMetadata"],
        )
        self.assertEqual(
            {"num_samples": 0, "num_shards": 0, "shard_size": 2},
            saved["emptyMetadata"],
        )
        self.assertEqual(
            ["shard_0000.pkl", "shard_0001.pkl", "shard_0002.pkl"],
            saved["staleShardFilesRemain"],
        )
        self.assertEqual(
            {"absolute": True, "parent": True, "root": True},
            saved["traversalRejected"],
        )
        self.assertTrue(saved["nestedFolderListed"])

        loaded = payload["load"]
        self.assertEqual([0, 1, 2, 3, 4], loaded["sortedInitialIds"])
        self.assertEqual([99, 2, 3, 4], loaded["staleOverwriteIds"])
        self.assertEqual([2, 1], loaded["mismatchedShardListsAccepted"])
        self.assertTrue(loaded["emptyMetadataDatasetRejected"])
        self.assertTrue(loaded["ignoresMetadataCounts"])

        for class_type, spec in ARTICLE_SPECS.items():
            schema = payload["schemas"][spec["classType"]]
            self.assertEqual(spec["isInputList"], schema["inputIsList"])
            self.assertEqual(spec["outputLists"], schema["outputIsList"])
            self.assertEqual(spec["outputNode"], schema["outputNode"])
            self.assertTrue(schema["experimental"])
            self.assertFalse(schema["deprecated"])
            self.assertFalse(schema["devOnly"])
            self.assertFalse(schema["apiNode"])


if __name__ == "__main__":
    unittest.main()
