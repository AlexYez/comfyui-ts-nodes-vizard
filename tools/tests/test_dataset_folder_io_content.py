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
    "core.load-image-data-set-from-folder": {
        "directory": "load-image-data-set-from-folder",
        "classType": "LoadImageDataSetFromFolder",
        "fingerprint": "sha256:ac605bed6d9b1efcc7f29eee3e6c7ad7fbb3862eca93a33e9f7ef9d4dc46053b",
        "deprecated": False,
        "recipe": "recipe.load-image-data-set-folder",
    },
    "core.load-image-text-data-set-from-folder": {
        "directory": "load-image-text-data-set-from-folder",
        "classType": "LoadImageTextDataSetFromFolder",
        "fingerprint": "sha256:1df84e3ef0f9d81b8ecbe3f22e29f0cac69f51374107a81ffe1e6577a141c946",
        "deprecated": False,
        "recipe": "recipe.load-image-text-data-set-folder",
    },
    "core.save-image-data-set-to-folder": {
        "directory": "save-image-data-set-to-folder",
        "classType": "SaveImageDataSetToFolder",
        "fingerprint": "sha256:bb2e065b0d23b4fe81c9dfc54161a666905a13812c869239424973101817ee0c",
        "deprecated": True,
        "recipe": "recipe.save-image-data-set-increment",
    },
    "core.save-image-text-data-set-to-folder": {
        "directory": "save-image-text-data-set-to-folder",
        "classType": "SaveImageTextDataSetToFolder",
        "fingerprint": "sha256:a17e05adc0436ec8d7cfef4a8f6c88ae730847b8d61051ef69c63833d44699d1",
        "deprecated": False,
        "recipe": "recipe.save-image-text-data-set-increment",
    },
}

RECIPE_DIRECTORIES = {
    "recipe.load-image-data-set-folder": "load-image-data-set-folder",
    "recipe.load-image-text-data-set-folder": "load-image-text-data-set-folder",
    "recipe.save-image-data-set-increment": "save-image-data-set-increment",
    "recipe.save-image-text-data-set-increment": "save-image-text-data-set-increment",
}

EXPECTED_FRAGMENT_NODES = {
    "recipe.load-image-data-set-folder": [
        ("LoadImageDataSetFromFolder", {"folder": "3d"})
    ],
    "recipe.load-image-text-data-set-folder": [
        ("LoadImageTextDataSetFromFolder", {"folder": "3d"})
    ],
    "recipe.save-image-data-set-increment": [
        (
            "SaveImageDataSetToFolder",
            {
                "folder_name": "dataset",
                "filename_prefix": "image",
                "mode": "increment",
            },
        )
    ],
    "recipe.save-image-text-data-set-increment": [
        (
            "SaveImageTextDataSetToFolder",
            {
                "folder_name": "dataset",
                "filename_prefix": "image",
                "mode": "increment",
            },
        )
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
    "LoadImageDataSetFromFolder": {
        "en": "ceed93799f195e84c3a9719cb6b518ab5e1be34db45f59a63b4138ea2262085e",
        "ru": "335faeda5f2bc4cdae65aaebb4fe0c58406e96416954c01bd8fc89cf0f429f3f",
    },
    "LoadImageTextDataSetFromFolder": {
        "en": "f0e298c51a05775bf1c847e4bbf1094d27f45add2c5f177a6467e94dd122d1c3",
        "ru": "ce82a1574eac88f8955f2be3aa6f782289c59eb0f3ec451f3c9311bc17d54baa",
    },
    "SaveImageDataSetToFolder": {
        "en": "8f0b7825cc2f2d79ebff5f0273b4dc9424015d20919a03f398e962f4a75e256e",
        "ru": "f1e46892c887b776e6e38b7b755264511925d88bb8c12b8a6c771f03e91a20d9",
    },
    "SaveImageTextDataSetToFolder": {
        "en": "fbed774d3911ddedbd4be6ba414186d70d570e3e8f6c0a65447c1fdd207bf143",
        "ru": "3516e56563b4f906e55c8fdb0b3cac871b9dc3880980814d1d398845d56a563e",
    },
}
SYNTHETIC_PROBE = Path(__file__).with_name(
    "dataset_folder_io_synthetic_probe.py"
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


class DatasetFolderIoContentTests(unittest.TestCase):
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
            self.assertEqual(spec["deprecated"], runtime.get("deprecated", False))
            self.assertFalse(runtime.get("dev_only", False))
            self.assertFalse(runtime.get("api_node", False))
            self.assertEqual(
                spec["fingerprint"],
                catalog.schema_fingerprint(spec["classType"], runtime),
                article_id,
            )
            self.assertEqual(spec["fingerprint"], article["editorial"]["schemaHash"])

        self.assertEqual(
            [True], runtime_nodes["LoadImageDataSetFromFolder"]["output_is_list"]
        )
        self.assertEqual(
            [True, True],
            runtime_nodes["LoadImageTextDataSetFromFolder"]["output_is_list"],
        )
        self.assertTrue(runtime_nodes["SaveImageDataSetToFolder"]["is_input_list"])
        self.assertTrue(
            runtime_nodes["SaveImageTextDataSetToFolder"]["is_input_list"]
        )

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
                    input_type = descriptor_type(descriptor)
                    constraints = (
                        descriptor[1]
                        if len(descriptor) > 1 and isinstance(descriptor[1], dict)
                        else {}
                    )
                    if input_type == "STRING":
                        self.assertIsInstance(value, str)
                    elif input_type == "COMBO":
                        self.assertIsInstance(value, str)
                        options = constraints.get("options", [])
                        if options:
                            self.assertIn(value, options)

    @unittest.skipUnless(SOURCE.exists(), "pinned ComfyUI source checkout is absent")
    def test_articles_track_exact_pinned_implementations_and_replacement_state(self) -> None:
        dataset = (SOURCE / "comfy_extras" / "nodes_dataset.py").read_text(
            encoding="utf-8"
        )
        folder_paths = (SOURCE / "folder_paths.py").read_text(encoding="utf-8")

        self.assertIn('valid_extensions = [".png", ".jpg", ".jpeg", ".webp"]', dataset)
        self.assertIn("for f in os.listdir(sub_input_dir)", dataset)
        self.assertIn('img = img.convert("RGB")', dataset)
        self.assertIn("return output_images", dataset)
        self.assertIn('if item.split("_")[0].isdigit():', dataset)
        self.assertIn('repeat = int(item.split("_")[0])', dataset)
        self.assertIn('captions.append("")', dataset)
        self.assertIn('caption = f.read().strip()', dataset)
        self.assertIn("if img_tensor.dim() == 4 and img_tensor.shape[0] == 1:", dataset)
        self.assertIn("img_array = np.clip(img_array * 255.0, 0, 255).astype(np.uint8)", dataset)
        self.assertIn('filename = f"{prefix}_{idx:05d}.png"', dataset)
        self.assertIn("mode=='overwrite'", dataset)
        self.assertIn("is_deprecated=True", dataset)
        self.assertIn("superseded by existing Save Image nodes", dataset)
        self.assertIn("for idx, (filename, caption) in enumerate(zip(saved_files, texts)):", dataset)
        self.assertIn('with open(caption_path, "w", encoding="utf-8") as f:', dataset)
        self.assertIn("f.write(caption)", dataset)

        self.assertIn("return os.path.commonpath((directory, target)) == directory", folder_paths)
        self.assertIn("return sorted(folders)", folder_paths)
        self.assertIn("counter = max(filter", folder_paths)

        replacements_text = REPLACEMENTS.read_text(encoding="utf-8")
        for class_type in ARTICLE_SPECS.values():
            self.assertNotIn(class_type["classType"], replacements_text)

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

        self.assertTrue(
            all(
                "AI-generated" in docs[(class_type, "en")]
                for class_type in EMBEDDED_DOC_HASHES
            )
        )
        self.assertNotIn("nested", docs[("LoadImageDataSetFromFolder", "en")].lower())
        self.assertNotIn("os.listdir", docs[("LoadImageDataSetFromFolder", "en")])
        self.assertNotIn("strip", docs[("LoadImageTextDataSetFromFolder", "en")])
        self.assertNotIn("mode", docs[("SaveImageDataSetToFolder", "en")].lower())
        self.assertNotIn("mode", docs[("SaveImageTextDataSetToFolder", "en")].lower())
        self.assertIn(
            "This input is optional",
            docs[("SaveImageTextDataSetToFolder", "en")],
        )
        self.assertIn(
            "| `texts` | Список текстовых подписей для сохранения. | STRING | Да |",
            docs[("SaveImageTextDataSetToFolder", "ru")],
        )

    @unittest.skipUnless(WORKFLOW_WHEEL.exists(), "official workflow wheel is absent")
    def test_exhaustive_workflow_census_has_no_dataset_folder_nodes(self) -> None:
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
    def test_safe_temp_directory_execution_without_external_data(self) -> None:
        candidates = [
            Path(os.environ.get("TEMP", ""))
            / "nodes-wizard-comfyui-v0.32.0-venv"
            / "Scripts"
            / "python.exe",
            Path(sys.executable),
        ]
        python = next((candidate for candidate in candidates if candidate.exists()), None)
        if python is None:
            self.skipTest("no Python interpreter for dataset folder I/O probe")
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
                f"dataset folder I/O probe dependencies unavailable: {result.stderr}"
            )
        payload = json.loads(result.stdout.strip().splitlines()[-1])
        self.assertEqual(2, payload["loadImages"]["count"])
        self.assertEqual(
            [[1, 4, 7, 3], [1, 5, 6, 3]], payload["loadImages"]["shapes"]
        )
        self.assertTrue(payload["loadImages"]["nestedIgnored"])
        self.assertTrue(payload["loadImages"]["emptyRejected"])
        self.assertEqual(7, payload["loadImageText"]["count"])
        self.assertEqual(
            {"": 3, "direct caption": 1, "nested caption": 3},
            payload["loadImageText"]["captions"],
        )
        self.assertEqual(
            ["sample_00001_00000.png", "sample_00002_00001.png"],
            payload["saveImages"]["incrementFiles"],
        )
        self.assertTrue(payload["saveImages"]["staleOverwriteFileRemains"])
        self.assertTrue(payload["saveImages"]["batchedTensorRejected"])
        self.assertEqual(3, payload["saveImageText"]["imageFiles"])
        self.assertEqual(2, payload["saveImageText"]["captionFiles"])
        self.assertTrue(payload["saveImageText"]["shortCaptionListTruncated"])
        self.assertTrue(payload["pathTraversalRejected"])


if __name__ == "__main__":
    unittest.main()
