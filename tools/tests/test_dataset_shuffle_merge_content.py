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
from typing import Any

from tools import catalog


ARTICLE_SPECS = {
    "core.merge-image-lists": {
        "directory": "merge-image-lists",
        "classType": "MergeImageLists",
        "fingerprint": "sha256:9c83a6ff9cc25dfe2c84cd0e33ec932bf2e7c9182f4e011eff2e9b5a96f0600f",
        "recipe": "recipe.merge-image-lists-pass-through",
        "outputs": ["IMAGE"],
        "outputNames": ["images"],
        "outputLists": [True],
    },
    "core.shuffle-dataset": {
        "directory": "shuffle-dataset",
        "classType": "ShuffleDataset",
        "fingerprint": "sha256:24656d7a25d557541d9fa2ae5ee76f5cbf6e290223ca42b09f4174aa7835e07f",
        "recipe": "recipe.shuffle-dataset-seed-7",
        "outputs": ["IMAGE"],
        "outputNames": ["images"],
        "outputLists": [True],
    },
    "core.shuffle-image-text-dataset": {
        "directory": "shuffle-image-text-dataset",
        "classType": "ShuffleImageTextDataset",
        "fingerprint": "sha256:2807659ff2c46372278cdfcfa916f4badcdb526a5c3856c7c118516f8ea4d083",
        "recipe": "recipe.shuffle-image-text-seed-23",
        "outputs": ["IMAGE", "STRING"],
        "outputNames": ["images", "texts"],
        "outputLists": [True, True],
    },
    "core.shuffle-video-text-dataset": {
        "directory": "shuffle-video-text-dataset",
        "classType": "ShuffleVideoTextDataset",
        "fingerprint": "sha256:a46830017f6e583b723d58815861351443509fff9821235377d229f580a65854",
        "recipe": "recipe.shuffle-video-text-seed-29",
        "outputs": ["VIDEO", "STRING"],
        "outputNames": ["videos", "texts"],
        "outputLists": [True, True],
    },
}

RECIPE_DIRECTORIES = {
    "recipe.merge-image-lists-pass-through": "merge-image-lists-pass-through",
    "recipe.shuffle-dataset-seed-7": "shuffle-dataset-seed-7",
    "recipe.shuffle-image-text-seed-23": "shuffle-image-text-seed-23",
    "recipe.shuffle-video-text-seed-29": "shuffle-video-text-seed-29",
}

EXPECTED_FRAGMENT_NODES = {
    "recipe.merge-image-lists-pass-through": [("MergeImageLists", {})],
    "recipe.shuffle-dataset-seed-7": [("ShuffleDataset", {"seed": 7})],
    "recipe.shuffle-image-text-seed-23": [
        ("ShuffleImageTextDataset", {"seed": 23})
    ],
    "recipe.shuffle-video-text-seed-29": [
        ("ShuffleVideoTextDataset", {"seed": 29})
    ],
}

FULL_INVENTORY = catalog.CONTENT / "runtime" / "comfyui-0.32.0.object-info.json"
REPLACEMENTS = catalog.CONTENT / "runtime" / "comfyui-0.32.0.node-replacements.json"
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
    "MergeImageLists": {
        "en": "c155205c2744ccb03181f0da659d2c6a98f045e0fff035f707bb3d76c1bfcfeb",
        "ru": "f91c959c458374dafede182698868a38352a9fdead87e83815e38de198e34e9c",
    },
    "ShuffleDataset": {
        "en": "760f2eac561fad7d25016f0407ec67663ccb05837a31a927ddfb69f63b7be65e",
        "ru": "043b41519aa6ea17dafabf9b241134ba910029f692092ed7cf50f1512522faec",
    },
    "ShuffleImageTextDataset": {
        "en": "c2a02290c0bf389c1288feccebbf3d45a7d29b24c616dd9217085988d2142555",
        "ru": "336180438d02658a8e3a1dd4124239364c6817939ecbf794528e4effb0143508",
    },
    "ShuffleVideoTextDataset": {
        "en": "ff3d338827fedb080c1389ae541ab254274a0762a3865ba7e1f90b65d5c0a5ac",
        "ru": "65eb8117e497d773fa231bd0c3285f5d0621fa3a1117c3299d3d4b9e6bf23c06",
    },
}
SYNTHETIC_PROBE = Path(__file__).with_name(
    "dataset_shuffle_merge_synthetic_probe.py"
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


def all_article_ids() -> set[str]:
    result: set[str] = set()
    for path in (catalog.CONTENT / "articles").rglob("manifest.json"):
        payload = catalog.load_json(path)
        if isinstance(payload, dict) and isinstance(payload.get("articleId"), str):
            result.add(payload["articleId"])
    return result


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
    return "COMBO" if isinstance(value, list) else value


class DatasetShuffleMergeContentTests(unittest.TestCase):
    def test_articles_recipes_research_and_editorial_contracts(self) -> None:
        article_ids = all_article_ids()
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
                10,
                len(re.findall(r"^## .+$", body, flags=re.MULTILINE)),
                article_id,
            )
            self.assertNotIn("\ufffd", body)
            self.assertNotRegex(
                body.lower(),
                r"важно отметить|стоит отметить|следует отметить|в современном мире|"
                r"революционн|является незаменим|является мощн|\bдавайте\b|"
                r"глубже погруз|открывает новые|может показаться|позволяет вам|"
                r"подводя итог|в заключение|не просто .{0,80}, а",
            )

            research_path = (
                catalog.CONTENT / "research" / "reviews" / f"{article_id}.json"
            )
            research = catalog.load_json(research_path)
            self.assertEqual(
                [], catalog.json_schema_errors(research, schemas["research"])
            )
            self.assertEqual(article_id, research["articleId"])
            self.assertEqual(spec["classType"], research["node"]["classType"])
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
            self.assertEqual(recipe_id, recipe["recipeId"])
            self.assertNotIn("workflow", recipe)
            self.assertEqual("in_review", recipe["editorial"]["state"])
            self.assertIn("human approval pending", recipe["editorial"]["reviewedBy"])

            fragment_path = path.parent / recipe["fragment"]["path"]
            fragment = catalog.load_json(fragment_path)
            self.assertEqual(
                [], catalog.json_schema_errors(fragment, schemas["fragment"])
            )
            catalog.validate_fragment(fragment_path, fragment, errors)
            self.assertEqual([], fragment["connections"])
            self.assertEqual(
                EXPECTED_FRAGMENT_NODES[recipe_id],
                [
                    (node["classType"], node["settings"])
                    for node in fragment["nodes"]
                ],
            )

        self.assertEqual([], errors)

    def test_runtime_fingerprints_flags_ports_and_fragment_settings(self) -> None:
        runtime_nodes = catalog.object_info_nodes(catalog.load_json(FULL_INVENTORY))
        for article_id, spec in ARTICLE_SPECS.items():
            runtime = runtime_nodes[spec["classType"]]
            article = catalog.load_json(article_path(spec))
            self.assertEqual("comfy_extras.nodes_dataset", runtime["python_module"])
            self.assertTrue(runtime.get("experimental", False))
            self.assertFalse(runtime.get("deprecated", False))
            self.assertFalse(runtime.get("dev_only", False))
            self.assertFalse(runtime.get("api_node", False))
            self.assertTrue(runtime["is_input_list"])
            self.assertEqual(spec["outputs"], runtime["output"])
            self.assertEqual(spec["outputNames"], runtime["output_name"])
            self.assertEqual(spec["outputLists"], runtime["output_is_list"])
            self.assertEqual(
                spec["fingerprint"],
                catalog.schema_fingerprint(spec["classType"], runtime),
                article_id,
            )
            self.assertEqual(spec["fingerprint"], article["editorial"]["schemaHash"])

        merge = runtime_nodes["MergeImageLists"]
        self.assertEqual("Merge Image Lists (DEPRECATED)", merge["display_name"])
        self.assertEqual(["images"], merge["input_order"]["required"])
        image_text = runtime_nodes["ShuffleImageTextDataset"]
        self.assertTrue(image_text["input"]["required"]["texts"][1]["forceInput"])
        video_text = runtime_nodes["ShuffleVideoTextDataset"]
        self.assertNotIn("forceInput", video_text["input"]["required"]["texts"][1])

        for class_type in (
            "ShuffleDataset",
            "ShuffleImageTextDataset",
            "ShuffleVideoTextDataset",
        ):
            seed = runtime_nodes[class_type]["input"]["required"]["seed"]
            self.assertEqual("INT", seed[0])
            self.assertEqual(0, seed[1]["default"])
            self.assertEqual(0, seed[1]["min"])
            self.assertEqual(2**64 - 1, seed[1]["max"])

        for recipe_id in RECIPE_DIRECTORIES:
            path = recipe_path(recipe_id)
            fragment = catalog.load_json(
                path.parent / catalog.load_json(path)["fragment"]["path"]
            )
            node_by_ref = {node["ref"]: node for node in fragment["nodes"]}
            supplied = {
                ref: set(node["settings"]) for ref, node in node_by_ref.items()
            }
            for external in fragment["externalInputs"]:
                target = node_by_ref[external["to"]]
                descriptor = runtime_input_specs(
                    runtime_nodes[target["classType"]]
                )[external["input"]]
                self.assertEqual(external["type"], descriptor_type(descriptor))
                supplied[external["to"]].add(external["input"])

            for ref, node in node_by_ref.items():
                runtime = runtime_nodes[node["classType"]]
                required = set(runtime.get("input", {}).get("required", {}))
                self.assertTrue(required.issubset(supplied[ref]), (recipe_id, ref))
                for name, value in node["settings"].items():
                    descriptor = runtime_input_specs(runtime)[name]
                    self.assertEqual("INT", descriptor_type(descriptor))
                    self.assertIsInstance(value, int)
                    constraints = descriptor[1]
                    self.assertGreaterEqual(value, constraints["min"])
                    self.assertLessEqual(value, constraints["max"])

    @unittest.skipUnless(SOURCE.exists(), "pinned ComfyUI source checkout is absent")
    def test_articles_track_exact_pinned_implementations_and_replacement_state(self) -> None:
        dataset = (SOURCE / "comfy_extras" / "nodes_dataset.py").read_text(
            encoding="utf-8"
        )
        toolkit = (SOURCE / "comfy_extras" / "nodes_toolkit.py").read_text(
            encoding="utf-8"
        )

        self.assertIn("def _ensure_image_list(cls, images):", dataset)
        self.assertIn("images = cls._ensure_image_list(images)", dataset)
        self.assertIn("np.random.seed(seed % (2**32 - 1))", dataset)
        self.assertGreaterEqual(
            dataset.count("np.random.seed(seed % (2**32 - 1))"), 4
        )
        self.assertIn("indices = np.random.permutation(len(images))", dataset)
        self.assertIn("seed = seed[0]  # Extract scalar", dataset)
        self.assertIn("shuffled_images = [images[i] for i in indices]", dataset)
        self.assertIn("shuffled_texts = [texts[i] for i in indices]", dataset)
        self.assertIn("indices = np.random.permutation(len(videos))", dataset)
        self.assertIn("[videos[i] for i in indices]", dataset)
        self.assertIn("[texts[i] for i in indices]", dataset)
        self.assertIn('display_name = "Merge Image Lists (DEPRECATED)"', dataset)
        self.assertIn("is_deprecated = True  # This node is superseded by the Create List node", dataset)
        self.assertIn("return images", dataset[dataset.index("class MergeImageListsNode"):])
        self.assertIn('node_id="CreateList"', toolkit)
        self.assertIn("template_autogrow", toolkit)

        replacements_text = REPLACEMENTS.read_text(encoding="utf-8")
        for spec in ARTICLE_SPECS.values():
            self.assertNotIn(spec["classType"], replacements_text)

    @unittest.skipUnless(
        EMBEDDED_DOCS_WHEEL.exists(), "pinned embedded-docs wheel is absent"
    )
    def test_embedded_docs_hashes_and_known_gaps(self) -> None:
        self.assertEqual(
            EMBEDDED_DOCS_WHEEL_SHA256,
            hashlib.sha256(EMBEDDED_DOCS_WHEEL.read_bytes()).hexdigest(),
        )
        docs: dict[tuple[str, str], str] = {}
        with zipfile.ZipFile(EMBEDDED_DOCS_WHEEL) as archive:
            for class_type, locales in EMBEDDED_DOC_HASHES.items():
                for locale, expected_hash in locales.items():
                    payload = archive.read(
                        f"comfyui_embedded_docs/docs/{class_type}/{locale}.md"
                    )
                    self.assertEqual(expected_hash, hashlib.sha256(payload).hexdigest())
                    docs[(class_type, locale)] = payload.decode("utf-8")

        for class_type in EMBEDDED_DOC_HASHES:
            self.assertIn("AI-generated", docs[(class_type, "en")])
            self.assertNotIn("2**32", docs[(class_type, "en")])
        self.assertIn(
            "This input can accept multiple connections",
            docs[("MergeImageLists", "en")],
        )
        self.assertIn("superseded by the Create List", docs[("MergeImageLists", "en")])
        self.assertIn("`изображения`", docs[("MergeImageLists", "ru")])
        self.assertIn(
            "Значение 0 будет каждый раз создавать новый порядок",
            docs[("ShuffleDataset", "ru")],
        )
        self.assertIn(
            "must be lists of the same length",
            docs[("ShuffleImageTextDataset", "en")],
        )
        self.assertNotIn("IndexError", docs[("ShuffleImageTextDataset", "en")])
        self.assertNotIn("truncat", docs[("ShuffleImageTextDataset", "en")].lower())
        self.assertIn("`видео`", docs[("ShuffleVideoTextDataset", "ru")])
        self.assertIn("`тексты`", docs[("ShuffleVideoTextDataset", "ru")])
        self.assertNotIn("IndexError", docs[("ShuffleVideoTextDataset", "en")])

    @unittest.skipUnless(WORKFLOW_WHEEL.exists(), "official workflow wheel is absent")
    def test_exhaustive_workflow_census_has_no_target_nodes(self) -> None:
        self.assertEqual(
            WORKFLOW_WHEEL_SHA256,
            hashlib.sha256(WORKFLOW_WHEEL.read_bytes()).hexdigest(),
        )
        target_types = {spec["classType"] for spec in ARTICLE_SPECS.values()}
        occurrences: list[tuple[str, str]] = []
        root_workflows = 0
        subgraph_count = 0

        with zipfile.ZipFile(WORKFLOW_WHEEL) as archive:
            members = sorted(
                member
                for member in archive.namelist()
                if "/templates/" in member and member.endswith(".json")
            )
            self.assertEqual(512, len(members))
            for member in members:
                payload = json.loads(archive.read(member).decode("utf-8"))
                if not isinstance(payload, dict):
                    continue
                if isinstance(payload.get("nodes"), list):
                    root_workflows += 1
                    for node in payload["nodes"]:
                        if isinstance(node, dict) and node.get("type") in target_types:
                            occurrences.append((member, node["type"]))
                definitions = payload.get("definitions")
                subgraphs = (
                    definitions.get("subgraphs", [])
                    if isinstance(definitions, dict)
                    else []
                )
                for subgraph in subgraphs:
                    if not isinstance(subgraph, dict):
                        continue
                    subgraph_count += 1
                    for node in subgraph.get("nodes", []) or []:
                        if isinstance(node, dict) and node.get("type") in target_types:
                            occurrences.append((member, node["type"]))

        self.assertEqual(496, root_workflows)
        self.assertEqual(272, subgraph_count)
        self.assertEqual([], occurrences)

    @unittest.skipUnless(SOURCE.exists(), "pinned ComfyUI source checkout is absent")
    def test_exact_source_synthetic_execution_without_external_data(self) -> None:
        candidates = [
            Path(os.environ.get("TEMP", ""))
            / "nodes-wizard-comfyui-v0.32.0-venv"
            / "Scripts"
            / "python.exe",
            Path(sys.executable),
        ]
        python = next((candidate for candidate in candidates if candidate.exists()), None)
        if python is None:
            self.skipTest("no Python interpreter for dataset shuffle probe")
        result = subprocess.run(
            [str(python), str(SYNTHETIC_PROBE), str(SOURCE)],
            cwd=catalog.ROOT,
            text=True,
            capture_output=True,
            timeout=120,
            check=False,
        )
        if result.returncode != 0 and python != Path(sys.executable):
            self.fail(result.stderr or result.stdout)
        if result.returncode != 0:
            self.skipTest(f"dataset shuffle probe unavailable: {result.stderr}")
        payload = json.loads(result.stdout.strip().splitlines()[-1])

        self.assertEqual(8, payload["merge"]["flattenedCount"])
        self.assertEqual(list(range(8)), payload["merge"]["order"])
        self.assertTrue(
            all(shape == [1, 1, 1, 1] for shape in payload["merge"]["singletonBatchShapes"])
        )
        shuffle = payload["shuffleImages"]
        self.assertEqual([2, 5, 0, 6, 3, 1, 4, 7], shuffle["orderSeed7"])
        self.assertTrue(shuffle["repeatDeterministic"])
        self.assertTrue(shuffle["differentSeedChangesOrder"])
        self.assertTrue(shuffle["seedModuloCollision"])
        self.assertTrue(shuffle["globalRngReseeded"])
        self.assertTrue(shuffle["zeroSeedDeterministic"])
        image_text = payload["shuffleImageText"]
        self.assertEqual([7, 4, 5, 2, 1, 0, 6, 3], image_text["orderSeed23"])
        self.assertTrue(image_text["alignmentPreserved"])
        self.assertTrue(image_text["repeatDeterministic"])
        self.assertTrue(image_text["seedModuloCollision"])
        self.assertTrue(image_text["shortTextsRejected"])
        self.assertTrue(image_text["longTextsTruncated"])
        self.assertTrue(image_text["scalarSeedRejected"])
        self.assertTrue(image_text["outerBatchNotFlattened"])
        video_text = payload["shuffleVideoText"]
        self.assertEqual([7, 1, 6, 0, 2, 4, 3, 5], video_text["orderSeed29"])
        self.assertTrue(video_text["alignmentPreserved"])
        self.assertTrue(video_text["scalarSeedAccepted"])
        self.assertTrue(video_text["seedModuloCollision"])
        self.assertTrue(video_text["shortTextsRejected"])
        self.assertTrue(video_text["longTextsTruncated"])
        self.assertEqual([0, 0], video_text["emptyPairCounts"])


if __name__ == "__main__":
    unittest.main()
