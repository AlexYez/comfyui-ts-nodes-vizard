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
    "core.adjust-brightness": {
        "directory": "adjust-brightness",
        "classType": "AdjustBrightness",
        "fingerprint": "sha256:69b588094c1b63ebdb12f68fd73f310f14a03ea2b576abefd387f625c895acef",
        "recipe": "recipe.adjust-brightness-neutral",
        "inputList": False,
        "outputList": [False],
    },
    "core.adjust-contrast": {
        "directory": "adjust-contrast",
        "classType": "AdjustContrast",
        "fingerprint": "sha256:8293bf3f405fa0c14e759e5b880f58df9b0c4ebd442bed6ed4e08443160addb0",
        "recipe": "recipe.adjust-contrast-neutral",
        "inputList": False,
        "outputList": [False],
    },
    "core.normalize-images": {
        "directory": "normalize-images",
        "classType": "NormalizeImages",
        "fingerprint": "sha256:085c249e4e520cf1f10164e7ab8bd702e92e35fb67054c53d4d498f4c1b7d51b",
        "recipe": "recipe.normalize-images-minus-one-one",
        "inputList": False,
        "outputList": [False],
    },
    "core.image-deduplication": {
        "directory": "image-deduplication",
        "classType": "ImageDeduplication",
        "fingerprint": "sha256:14048d7e3858364ff1884b9d8a10783c73fd43e3fda420355515d8a368bf861f",
        "recipe": "recipe.deduplicate-images-default-threshold",
        "inputList": True,
        "outputList": [True],
    },
}

RECIPE_DIRECTORIES = {
    "recipe.adjust-brightness-neutral": "adjust-brightness-neutral",
    "recipe.adjust-contrast-neutral": "adjust-contrast-neutral",
    "recipe.normalize-images-minus-one-one": "normalize-images-minus-one-one",
    "recipe.deduplicate-images-default-threshold": "deduplicate-images-default-threshold",
}

EXPECTED_FRAGMENT_NODES = {
    "recipe.adjust-brightness-neutral": [
        ("AdjustBrightness", {"factor": 1.0})
    ],
    "recipe.adjust-contrast-neutral": [
        ("AdjustContrast", {"factor": 1.0})
    ],
    "recipe.normalize-images-minus-one-one": [
        ("NormalizeImages", {"mean": 0.5, "std": 0.5})
    ],
    "recipe.deduplicate-images-default-threshold": [
        ("ImageDeduplication", {"similarity_threshold": 0.95})
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
    "AdjustBrightness": {
        "en": "521f768404c865b7bcbc03eb9a8e00229feeb8395ef55170eaf040de84760648",
        "ru": "b95df6b0739af11651092c81bf78c46bc18b18879a17fbc9119facdf49c9742c",
    },
    "AdjustContrast": {
        "en": "50aff3a9052c7f792cd3dee900ebe01c8c9827df904be6b0ced1776073881647",
        "ru": "b40c0c12da63465953ce3cc42d5964698d2d6f046d849968679cc280dcf18706",
    },
    "NormalizeImages": {
        "en": "b7b21e81a12d2ed2604962d9b8765bbd2a971d487d8378bfc25d37913e326dce",
        "ru": "f72da964c874de7dbf1667d7444998b6ec5d7194dbc3fd486e2befb4171c5117",
    },
    "ImageDeduplication": {
        "en": "913d66854380b73bab08be1ffd102d7916d1eb05bcf22fab89021b0a1dedea01",
        "ru": "f93ef2a3a23838b8eb92025f71a53b2d23d433ca352fcb09f99d1589541028b8",
    },
}
SYNTHETIC_PROBE = Path(__file__).with_name(
    "dataset_adjust_dedup_synthetic_probe.py"
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


class DatasetAdjustDedupContentTests(unittest.TestCase):
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
            self.assertTrue(research["knownGaps"])

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
            self.assertEqual(spec["inputList"], runtime["is_input_list"])
            self.assertEqual(spec["outputList"], runtime["output_is_list"])
            self.assertEqual(["IMAGE"], runtime["output"])
            self.assertEqual(["images"], runtime["output_name"])
            self.assertEqual(
                spec["fingerprint"],
                catalog.schema_fingerprint(spec["classType"], runtime),
                article_id,
            )
            self.assertEqual(spec["fingerprint"], article["editorial"]["schemaHash"])

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
                    self.assertEqual("FLOAT", descriptor_type(descriptor))
                    self.assertIsInstance(value, float)
                    constraints = descriptor[1]
                    self.assertGreaterEqual(value, constraints["min"])
                    self.assertLessEqual(value, constraints["max"])

    @unittest.skipUnless(SOURCE.exists(), "pinned ComfyUI source checkout is absent")
    def test_articles_track_exact_pinned_implementations_and_replacement_state(self) -> None:
        dataset = (SOURCE / "comfy_extras" / "nodes_dataset.py").read_text(
            encoding="utf-8"
        )

        self.assertIn("return (image - mean) / std", dataset)
        self.assertIn("return (image * factor).clamp(0.0, 1.0)", dataset)
        self.assertIn(
            "return ((image - 0.5) * factor + 0.5).clamp(0.0, 1.0)",
            dataset,
        )
        self.assertGreaterEqual(dataset.count("per_frame_process = False"), 3)
        self.assertIn("def _ensure_image_list(cls, images):", dataset)
        self.assertIn("images = cls._ensure_image_list(images)", dataset)
        self.assertIn('img.resize((8, 8), Image.Resampling.LANCZOS).convert("L")', dataset)
        self.assertIn('hash_bits = "".join("1" if p > avg else "0" for p in pixels)', dataset)
        self.assertIn("similarity = 1.0 - (distance / 64.0)", dataset)
        self.assertIn("if similarity >= similarity_threshold:", dataset)
        self.assertIn("for j in keep_indices:", dataset)
        self.assertIn("keep_indices.append(i)", dataset)

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

        for class_type in ("AdjustBrightness", "AdjustContrast", "NormalizeImages"):
            self.assertIn("| `image` |", docs[(class_type, "en")])
            self.assertNotIn("| `images` |", docs[(class_type, "en")])
        self.assertNotIn("0.5", docs[("AdjustContrast", "en")].split("## Inputs")[0])
        self.assertNotIn("clamp", docs[("AdjustContrast", "en")].lower())
        self.assertNotIn("clamp", docs[("NormalizeImages", "en")].lower())
        self.assertNotIn("torch.mean", docs[("NormalizeImages", "en")])
        dedup = docs[("ImageDeduplication", "en")]
        self.assertIn("above this threshold", dedup)
        self.assertNotIn("8x8", dedup.lower())
        self.assertNotIn("hamming", dedup.lower())
        self.assertNotIn(">=", dedup)

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
            self.skipTest("no Python interpreter for dataset adjustment probe")
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
            self.skipTest(
                f"dataset adjustment probe dependencies unavailable: {result.stderr}"
            )
        payload = json.loads(result.stdout.strip().splitlines()[-1])
        self.assertEqual([2, 2, 2, 3], payload["brightness"]["shape"])
        self.assertEqual(0.0, payload["brightness"]["min"])
        self.assertEqual(1.0, payload["brightness"]["max"])
        self.assertTrue(payload["brightness"]["factorZeroIsBlack"])
        self.assertEqual(0.5, payload["contrast"]["factorZeroValue"])
        self.assertEqual([2, 2, 2, 3], payload["contrast"]["shape"])
        self.assertEqual(-1.5, payload["normalize"]["min"])
        self.assertEqual(1.5, payload["normalize"]["max"])
        self.assertTrue(payload["normalize"]["notClamped"])
        dedup = payload["deduplication"]
        self.assertEqual(3, dedup["exactThresholdKept"])
        self.assertEqual(1, dedup["inclusiveOneBitBoundaryKept"])
        self.assertEqual(2, dedup["aboveOneBitBoundaryKept"])
        self.assertEqual(2, dedup["defaultThresholdKept"])
        self.assertEqual(1, dedup["solidColorsKept"])
        self.assertEqual(1, dedup["zeroThresholdKept"])
        self.assertEqual(0, dedup["emptyKept"])
        self.assertEqual(3, dedup["flattenedItems"])
        self.assertTrue(dedup["invalid3dRejected"])
        self.assertEqual(0.984375, dedup["oneBitSimilarity"])


if __name__ == "__main__":
    unittest.main()
