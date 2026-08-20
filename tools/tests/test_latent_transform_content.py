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
    "core.latent-blend": {
        "directory": "latent-blend",
        "classType": "LatentBlend",
        "fingerprint": "sha256:ee52b8e747be6889e59c0d99f59acd0c996e1d7002e4d2ca6d7d6f798c534913",
        "category": "experimental",
        "recipe": "recipe.blend-latents-quarter-first",
        "required": {
            "samples1": ["LATENT"],
            "samples2": ["LATENT"],
            "blend_factor": [
                "FLOAT",
                {"default": 0.5, "min": 0, "max": 1, "step": 0.01},
            ],
        },
    },
    "core.latent-rotate": {
        "directory": "latent-rotate",
        "classType": "LatentRotate",
        "fingerprint": "sha256:942e7b51ae76ec655c25e9a1538560768509c037e96086f5e0202b08b56730c2",
        "category": "model/latent/transform",
        "recipe": "recipe.rotate-latent-90-clockwise",
        "required": {
            "samples": ["LATENT"],
            "rotation": [["none", "90 degrees", "180 degrees", "270 degrees"]],
        },
    },
    "core.latent-flip": {
        "directory": "latent-flip",
        "classType": "LatentFlip",
        "fingerprint": "sha256:4c3075656bc7eabaf03f63a878b81f40efa11ea7c948d458d3ac5e479c50347f",
        "category": "model/latent/transform",
        "recipe": "recipe.flip-latent-left-right",
        "required": {
            "samples": ["LATENT"],
            "flip_method": [
                ["x-axis: vertically", "y-axis: horizontally"]
            ],
        },
    },
    "core.latent-crop": {
        "directory": "latent-crop",
        "classType": "LatentCrop",
        "fingerprint": "sha256:633326c63d70b83caa8225f7a1f1aad401bf6a3b859fef9e8e18c5f49b049950",
        "category": "model/latent/transform",
        "recipe": "recipe.crop-latent-512-offset",
        "required": {
            "samples": ["LATENT"],
            "width": [
                "INT",
                {"default": 512, "min": 64, "max": 16384, "step": 8},
            ],
            "height": [
                "INT",
                {"default": 512, "min": 64, "max": 16384, "step": 8},
            ],
            "x": [
                "INT",
                {"default": 0, "min": 0, "max": 16384, "step": 8},
            ],
            "y": [
                "INT",
                {"default": 0, "min": 0, "max": 16384, "step": 8},
            ],
        },
    },
}

RECIPE_DIRECTORIES = {
    "recipe.blend-latents-quarter-first": "blend-latents-quarter-first",
    "recipe.rotate-latent-90-clockwise": "rotate-latent-90-clockwise",
    "recipe.flip-latent-left-right": "flip-latent-left-right",
    "recipe.crop-latent-512-offset": "crop-latent-512-offset",
}

EXPECTED_FRAGMENT_NODES = {
    "recipe.blend-latents-quarter-first": [
        ("LatentBlend", {"blend_factor": 0.25})
    ],
    "recipe.rotate-latent-90-clockwise": [
        ("LatentRotate", {"rotation": "90 degrees"})
    ],
    "recipe.flip-latent-left-right": [
        ("LatentFlip", {"flip_method": "y-axis: horizontally"})
    ],
    "recipe.crop-latent-512-offset": [
        (
            "LatentCrop",
            {"width": 512, "height": 512, "x": 64, "y": 64},
        )
    ],
}

FULL_INVENTORY = catalog.CONTENT / "runtime" / "comfyui-0.32.0.object-info.json"
INVENTORY_METADATA = (
    catalog.CONTENT / "runtime" / "comfyui-0.32.0.object-info.meta.json"
)
REPLACEMENTS = (
    catalog.CONTENT / "runtime" / "comfyui-0.32.0.node-replacements.json"
)
SOURCE = catalog.ROOT / ".comfyui-source-0.32.0"
SOURCE_COMMIT = "c2bcbecd82ec5ae66594340b395c24ef0217b238"
WORKFLOW_WHEEL = (
    catalog.ROOT
    / ".upstream-cache"
    / "comfyui_workflow_templates_json-0.1.42-py3-none-any.whl"
)
WORKFLOW_WHEEL_SHA256 = (
    "242982d65e1c51ca03d892bc1009bb6843f457e7dfc0c20afe6438770b7a14a3"
)
DOCS_WHEEL = (
    catalog.ROOT
    / ".upstream-cache"
    / "comfyui_embedded_docs-0.5.9-py3-none-any.whl"
)
DOCS_WHEEL_SHA256 = (
    "30afae432a71c96aa59421d0f37388c66ff6572b8cbeee8ff045e4d5f84f896c"
)
SYNTHETIC_PROBE = Path(__file__).with_name("latent_transform_synthetic_probe.py")


def article_path(spec: dict[str, Any]) -> Path:
    return (
        catalog.CONTENT
        / "articles"
        / "core"
        / spec["directory"]
        / "manifest.json"
    )


def recipe_path(recipe_id: str) -> Path:
    return catalog.CONTENT / "recipes" / RECIPE_DIRECTORIES[recipe_id] / "recipe.json"


def all_article_ids() -> set[str]:
    result: set[str] = set()
    for path in (catalog.CONTENT / "articles").rglob("manifest.json"):
        payload = catalog.load_json(path)
        if isinstance(payload, dict) and isinstance(payload.get("articleId"), str):
            result.add(payload["articleId"])
    return result


def workflow_nodes(payload: dict[str, Any]) -> Iterator[dict[str, Any]]:
    for node in payload.get("nodes", []):
        if isinstance(node, dict):
            yield node
    definitions = payload.get("definitions")
    subgraphs = definitions.get("subgraphs", []) if isinstance(definitions, dict) else []
    for subgraph in subgraphs:
        if not isinstance(subgraph, dict):
            continue
        for node in subgraph.get("nodes", []):
            if isinstance(node, dict):
                yield node


class LatentTransformContentTests(unittest.TestCase):
    def test_articles_recipes_research_and_cross_links_validate(self) -> None:
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
            self.assertFalse(article["experimental"])
            self.assertEqual("in_review", article["editorial"]["state"])
            self.assertIn("human approval pending", article["editorial"]["reviewedBy"])
            self.assertEqual([], article["runtimeIdentity"]["aliases"])
            self.assertEqual("nodes", article["runtimeIdentity"]["pythonModule"])
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
                r"важно отметить|стоит отметить|следует отметить|"
                r"в современном мире|революционн|является мощн|"
                r"\bдавайте\b|глубже погруз|открывает новые|"
                r"может показаться|позволяет вам|подводя итог|"
                r"в заключение|данная нода|не просто .{0,80},? а ",
            )

            research = catalog.load_json(
                catalog.CONTENT / "research" / "reviews" / f"{article_id}.json"
            )
            self.assertEqual([], catalog.json_schema_errors(research, schemas["research"]))
            self.assertEqual(article_id, research["articleId"])
            self.assertEqual(spec["classType"], research["node"]["classType"])
            self.assertEqual("nodes", research["node"]["pythonModule"])
            self.assertEqual("fact_checked", research["state"])
            self.assertEqual("automated_assisted", research["reviewMode"])
            self.assertEqual("0.32.0", research["baseline"]["comfyui"])
            self.assertEqual("1.48.7", research["baseline"]["frontend"])
            self.assertEqual("0.5.9", research["baseline"]["embeddedDocs"])
            self.assertEqual("0.1.42", research["baseline"]["workflowTemplatesJson"])
            self.assertTrue(research["checks"]["exampleSchemaValidated"])
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
            self.assertEqual([], catalog.json_schema_errors(fragment, schemas["fragment"]))
            catalog.validate_fragment(fragment_path, fragment, errors)
            self.assertEqual(recipe["fragment"]["id"], fragment["fragmentId"])
            self.assertEqual([], fragment["connections"])
            self.assertEqual(
                EXPECTED_FRAGMENT_NODES[recipe_id],
                [
                    (node["classType"], node["settings"])
                    for node in fragment["nodes"]
                ],
            )
            self.assertTrue(
                all(item["type"] == "LATENT" for item in fragment["externalInputs"])
            )

        self.assertEqual([], errors)

    def test_exact_runtime_identity_fingerprints_flags_ports_and_settings(self) -> None:
        nodes = catalog.object_info_nodes(catalog.load_json(FULL_INVENTORY))
        metadata = catalog.load_json(INVENTORY_METADATA)
        self.assertEqual(SOURCE_COMMIT, metadata["source"]["commit"])
        self.assertEqual("0.32.0", metadata["source"]["backendVersion"])
        self.assertEqual("/object_info", metadata["capture"]["endpoint"])

        for article_id, spec in ARTICLE_SPECS.items():
            runtime = nodes[spec["classType"]]
            article = catalog.load_json(article_path(spec))
            self.assertEqual("nodes", runtime["python_module"])
            self.assertEqual(spec["category"], runtime["category"])
            self.assertEqual(spec["required"], runtime["input"]["required"])
            self.assertEqual(["LATENT"], runtime["output"])
            self.assertEqual(["LATENT"], runtime["output_name"])
            self.assertEqual([False], runtime["output_is_list"])
            self.assertFalse(runtime["is_input_list"])
            self.assertFalse(runtime["output_node"])
            self.assertFalse(runtime.get("deprecated", False))
            self.assertFalse(runtime.get("experimental", False))
            self.assertFalse(runtime.get("dev_only", False))
            self.assertFalse(runtime.get("api_node", False))
            self.assertEqual(
                spec["fingerprint"],
                catalog.schema_fingerprint(spec["classType"], runtime),
                article_id,
            )
            self.assertEqual(spec["fingerprint"], article["editorial"]["schemaHash"])

        # The category label does not create the runtime status flag.
        self.assertEqual("experimental", nodes["LatentBlend"]["category"])
        self.assertNotIn("experimental", nodes["LatentBlend"])

        for recipe_id in RECIPE_DIRECTORIES:
            recipe = catalog.load_json(recipe_path(recipe_id))
            fragment = catalog.load_json(
                recipe_path(recipe_id).parent / recipe["fragment"]["path"]
            )
            node = fragment["nodes"][0]
            runtime = nodes[node["classType"]]
            supplied = set(node["settings"])
            supplied.update(item["input"] for item in fragment["externalInputs"])
            self.assertTrue(
                set(runtime["input"]["required"]).issubset(supplied), recipe_id
            )
            for external in fragment["externalInputs"]:
                self.assertEqual(
                    external["type"],
                    runtime["input"]["required"][external["input"]][0],
                )
            for name, value in node["settings"].items():
                descriptor = runtime["input"]["required"][name]
                if isinstance(descriptor[0], list):
                    self.assertIn(value, descriptor[0])
                elif descriptor[0] in ("INT", "FLOAT"):
                    self.assertGreaterEqual(value, descriptor[1]["min"])
                    self.assertLessEqual(value, descriptor[1]["max"])

    @unittest.skipUnless(SOURCE.exists(), "pinned ComfyUI source checkout is absent")
    def test_exact_pinned_source_and_experimental_flag_mechanism(self) -> None:
        self.assertEqual(
            SOURCE_COMMIT,
            (SOURCE / ".git" / "HEAD").read_text(encoding="utf-8").strip(),
        )
        source = (SOURCE / "nodes.py").read_text(encoding="utf-8")
        server = (SOURCE / "server.py").read_text(encoding="utf-8")

        rotate = source.split("class LatentRotate:", 1)[1].split(
            "class LatentFlip:", 1
        )[0]
        flip = source.split("class LatentFlip:", 1)[1].split(
            "class LatentComposite:", 1
        )[0]
        blend = source.split("class LatentBlend:", 1)[1].split(
            "class LatentCrop:", 1
        )[0]
        crop = source.split("class LatentCrop:", 1)[1].split(
            "class SetLatentNoiseMask:", 1
        )[0]

        self.assertIn('CATEGORY = "experimental"', blend)
        self.assertNotIn("EXPERIMENTAL", blend)
        self.assertIn(
            'if getattr(obj_class, "EXPERIMENTAL", False):', server
        )
        self.assertIn("info['experimental'] = True", server)
        self.assertIn("info['category'] = obj_class.CATEGORY", server)
        self.assertIn(
            "samples1 * blend_factor + samples_blended * (1 - blend_factor)",
            blend,
        )
        self.assertIn(
            "common_upscale(samples2, samples1.shape[3], samples1.shape[2], 'bicubic', crop='center')",
            blend,
        )
        self.assertIn("samples_out = samples1.copy()", blend)

        self.assertIn(
            '(["none", "90 degrees", "180 degrees", "270 degrees"],)',
            rotate,
        )
        self.assertIn(
            'torch.rot90(samples["samples"], k=rotate_by, dims=[3, 2])', rotate
        )
        self.assertIn(
            '(["x-axis: vertically", "y-axis: horizontally"],)', flip
        )
        self.assertIn('torch.flip(samples["samples"], dims=[2])', flip)
        self.assertIn('torch.flip(samples["samples"], dims=[3])', flip)

        self.assertIn("x =  x // 8", crop)
        self.assertIn("y = y // 8", crop)
        self.assertIn("new_height = height // 8", crop)
        self.assertIn("new_width = width // 8", crop)
        self.assertIn("samples[:,:,y:to_y, x:to_x]", crop)
        self.assertIn("samples.shape[3] - 8", crop)
        self.assertIn("samples.shape[2] - 8", crop)

        replacements_text = REPLACEMENTS.read_text(encoding="utf-8")
        for spec in ARTICLE_SPECS.values():
            self.assertNotIn(spec["classType"], replacements_text)

    @unittest.skipUnless(DOCS_WHEEL.exists(), "pinned embedded-docs wheel is absent")
    def test_embedded_docs_hash_paths_and_documented_gaps(self) -> None:
        self.assertEqual(
            DOCS_WHEEL_SHA256,
            hashlib.sha256(DOCS_WHEEL.read_bytes()).hexdigest(),
        )
        docs: dict[tuple[str, str], str] = {}
        with zipfile.ZipFile(DOCS_WHEEL) as archive:
            for spec in ARTICLE_SPECS.values():
                for locale in ("en", "ru"):
                    path = (
                        f"comfyui_embedded_docs/docs/{spec['classType']}/{locale}.md"
                    )
                    self.assertIn(path, archive.namelist())
                    docs[(spec["classType"], locale)] = archive.read(path).decode(
                        "utf-8"
                    )

        self.assertTrue(
            all(
                "This documentation was AI-generated" in docs[(spec["classType"], "en")]
                for spec in ARTICLE_SPECS.values()
            )
        )
        blend = docs[("LatentBlend", "en")].lower()
        self.assertIn("inverse", blend)
        self.assertIn("bicubic", blend)
        self.assertNotIn("noise_mask", blend)
        self.assertNotIn("batch", blend)
        self.assertNotIn("experimental", blend)

        rotate = docs[("LatentRotate", "en")].lower()
        self.assertNotIn("clockwise", rotate)
        self.assertNotIn("noise_mask", rotate)
        flip = docs[("LatentFlip", "en")].lower()
        self.assertIn("x-axis: vertically", flip)
        self.assertIn("y-axis: horizontally", flip)
        self.assertNotIn("dims=[", flip)
        crop = docs[("LatentCrop", "en")].lower()
        self.assertNotIn("// 8", crop)
        self.assertNotIn("noise_mask", crop)
        self.assertNotIn("storage", crop)

    @unittest.skipUnless(WORKFLOW_WHEEL.exists(), "official workflow wheel is absent")
    def test_exhaustive_512_json_root_and_subgraph_census_has_no_targets(self) -> None:
        self.assertEqual(
            WORKFLOW_WHEEL_SHA256,
            hashlib.sha256(WORKFLOW_WHEEL.read_bytes()).hexdigest(),
        )
        target_types = {spec["classType"] for spec in ARTICLE_SPECS.values()}
        json_count = 0
        workflow_count = 0
        index_count = 0
        subgraph_count = 0
        hits: list[tuple[str, Any]] = []

        with zipfile.ZipFile(WORKFLOW_WHEEL) as archive:
            members = sorted(
                member
                for member in archive.namelist()
                if "/templates/" in member and member.endswith(".json")
            )
            for member in members:
                json_count += 1
                payload = json.loads(archive.read(member).decode("utf-8"))
                if not isinstance(payload, dict):
                    index_count += 1
                    continue
                workflow_count += 1
                definitions = payload.get("definitions")
                subgraphs = (
                    definitions.get("subgraphs", [])
                    if isinstance(definitions, dict)
                    else []
                )
                subgraph_count += sum(isinstance(item, dict) for item in subgraphs)
                for node in workflow_nodes(payload):
                    if node.get("type") in target_types:
                        hits.append((member, node))

        self.assertEqual(512, json_count)
        self.assertEqual(499, workflow_count)
        self.assertEqual(13, index_count)
        self.assertEqual(272, subgraph_count)
        self.assertEqual([], hits)

    @unittest.skipUnless(SOURCE.exists(), "pinned ComfyUI source checkout is absent")
    def test_safe_exact_source_tensor_execution_without_models(self) -> None:
        candidates = [
            Path(os.environ.get("TEMP", ""))
            / "nodes-wizard-comfyui-v0.32.0-venv"
            / "Scripts"
            / "python.exe",
            Path(sys.executable),
        ]
        python = next((candidate for candidate in candidates if candidate.exists()), None)
        if python is None:
            self.skipTest("no Python interpreter for latent transform probe")
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
            self.skipTest(f"latent transform probe unavailable: {result.stderr}")
        payload = json.loads(result.stdout.strip().splitlines()[-1])

        self.assertEqual(
            [[4.0, 1.0], [5.0, 2.0], [6.0, 3.0]],
            payload["rotate"]["90 degrees"]["matrix"],
        )
        self.assertEqual(
            [1, 1, 3, 2], payload["rotate"]["90 degrees"]["shape"]
        )
        self.assertTrue(payload["rotate"]["90 degrees"]["metadataUnchanged"])
        self.assertEqual(
            [[4.0, 5.0, 6.0], [1.0, 2.0, 3.0]],
            payload["flip"]["vertical"],
        )
        self.assertEqual(
            [[3.0, 2.0, 1.0], [6.0, 5.0, 4.0]],
            payload["flip"]["horizontal"],
        )
        self.assertEqual(
            {"0.0": 10.0, "0.25": 8.0, "0.5": 6.0, "1.0": 2.0},
            payload["blend"]["values"],
        )
        self.assertEqual([2, 4, 4, 6], payload["blend"]["spatialResizeShape"])
        self.assertEqual([2, 4, 4, 6], payload["blend"]["batchBroadcastShape"])
        self.assertTrue(payload["blend"]["incompatibleBatchRejected"])
        self.assertTrue(payload["blend"]["metadataFromFirst"])
        self.assertEqual([1, 1, 8, 8], payload["crop"]["shape"])
        self.assertEqual(18.0, payload["crop"]["originValue"])
        self.assertEqual([1, 1, 8, 8], payload["crop"]["edgeShape"])
        self.assertEqual(72.0, payload["crop"]["edgeOriginValue"])
        self.assertEqual([1, 1, 2, 2], payload["crop"]["smallInputShape"])
        self.assertEqual(28.0, payload["crop"]["smallInputOriginValue"])
        self.assertTrue(payload["crop"]["sharesStorage"])
        self.assertTrue(payload["crop"]["metadataUnchanged"])


if __name__ == "__main__":
    unittest.main()
