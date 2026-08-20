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


ARTICLE_SPECS = {
    "core.latent-add": {
        "directory": "latent-add",
        "classType": "LatentAdd",
        "fingerprint": "sha256:eb3369898f0102e22324b521c62b621c3f39f0ef907d4bd6f668ff731f1cf8dc",
        "recipe": "recipe.add-two-latents",
    },
    "core.latent-subtract": {
        "directory": "latent-subtract",
        "classType": "LatentSubtract",
        "fingerprint": "sha256:f19dda02deea19b2407e58fb362641478aebb1dc4003a7d639d7fb4b907cb3d4",
        "recipe": "recipe.subtract-two-latents",
    },
    "core.latent-multiply": {
        "directory": "latent-multiply",
        "classType": "LatentMultiply",
        "fingerprint": "sha256:6fe77e6287c1c873568f619b767145204ef71bd1d69841d6e690a7060d4a2e22",
        "recipe": "recipe.scale-latent-half",
    },
    "core.latent-interpolate": {
        "directory": "latent-interpolate",
        "classType": "LatentInterpolate",
        "fingerprint": "sha256:637bcd16e9ec8b085cbaacd121cf9b39a07210498dedaf0afe60d26bc511e8ce",
        "recipe": "recipe.interpolate-latents-midpoint",
    },
}

RECIPE_DIRECTORIES = {
    "recipe.add-two-latents": "add-two-latents",
    "recipe.subtract-two-latents": "subtract-two-latents",
    "recipe.scale-latent-half": "scale-latent-half",
    "recipe.interpolate-latents-midpoint": "interpolate-latents-midpoint",
}

EXPECTED_FRAGMENT_NODES = {
    "recipe.add-two-latents": [("LatentAdd", {})],
    "recipe.subtract-two-latents": [("LatentSubtract", {})],
    "recipe.scale-latent-half": [("LatentMultiply", {"multiplier": 0.5})],
    "recipe.interpolate-latents-midpoint": [("LatentInterpolate", {"ratio": 0.5})],
}

FULL_INVENTORY = catalog.CONTENT / "runtime" / "comfyui-0.32.0.object-info.json"
SOURCE = catalog.ROOT / ".comfyui-source-0.32.0"
WORKFLOW_WHEEL = catalog.ROOT / ".upstream-cache" / "comfyui_workflow_templates_json-0.1.42-py3-none-any.whl"
WORKFLOW_WHEEL_SHA256 = "242982d65e1c51ca03d892bc1009bb6843f457e7dfc0c20afe6438770b7a14a3"
DOCS_WHEEL = catalog.ROOT / ".upstream-cache" / "comfyui_embedded_docs-0.5.9-py3-none-any.whl"
DOCS_WHEEL_SHA256 = "30afae432a71c96aa59421d0f37388c66ff6572b8cbeee8ff045e4d5f84f896c"
SYNTHETIC_PROBE = Path(__file__).with_name("latent_arithmetic_synthetic_probe.py")


def article_path(spec: dict[str, str]) -> Path:
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


def runtime_inputs(runtime: dict[str, Any]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for group in ("required", "optional"):
        values = runtime.get("input", {}).get(group, {})
        if isinstance(values, dict):
            result.update(values)
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


class LatentArithmeticContentTests(unittest.TestCase):
    def test_articles_and_fragment_only_recipes_validate(self) -> None:
        article_ids = all_article_ids()
        article_schema = catalog.load_json(catalog.CONTENT / "schemas" / "article.schema.v1.json")
        recipe_schema = catalog.load_json(catalog.CONTENT / "schemas" / "recipe.schema.v1.json")
        fragment_schema = catalog.load_json(catalog.CONTENT / "schemas" / "recipe-fragment.schema.v1.json")
        errors: list[str] = []

        for article_id, spec in ARTICLE_SPECS.items():
            path = article_path(spec)
            article = catalog.load_json(path)
            self.assertEqual([], catalog.json_schema_errors(article, article_schema))
            catalog.validate_article(path, article, errors)
            self.assertEqual(article_id, article["articleId"])
            self.assertEqual("draft", article["status"])
            self.assertEqual("in_review", article["editorial"]["state"])
            self.assertEqual(spec["recipe"], article["assets"][0]["id"])
            relations = article["relations"]
            targets = relations["related"] + relations["alternatives"]
            if relations["replacedBy"] is not None:
                targets.append(relations["replacedBy"])
            self.assertTrue(set(targets).issubset(article_ids))

            body = (path.parent / article["body"]).read_text(encoding="utf-8")
            self.assertEqual(10, len(re.findall(r"^## .+$", body, re.MULTILINE)))
            self.assertNotIn("\ufffd", body)
            self.assertNotRegex(
                body.lower(),
                r"важно отметить|стоит подчеркнуть|подводя итог|в современном мире|революционн|данная нода|является незаменим|давайте разбер",
            )

        for recipe_id in RECIPE_DIRECTORIES:
            path = recipe_path(recipe_id)
            recipe = catalog.load_json(path)
            self.assertEqual([], catalog.json_schema_errors(recipe, recipe_schema))
            catalog.validate_recipe(path, recipe, article_ids, errors)
            self.assertEqual(recipe_id, recipe["recipeId"])
            self.assertNotIn("workflow", recipe)
            self.assertEqual("draft", recipe["editorial"]["state"])
            fragment = catalog.load_json(path.parent / recipe["fragment"]["path"])
            self.assertEqual([], catalog.json_schema_errors(fragment, fragment_schema))
            recipe_body = (path.parent / recipe["body"]).read_text(encoding="utf-8")
            prose_without_code = re.sub(
                r"`[^`]+`|https?://\S+", "", recipe_body
            ).casefold()
            for untranslated in (
                " workflow",
                " fragment",
                " runtime",
                " pinned",
                " batch",
                " broadcasting",
                " center crop",
                " bilinear resize",
                " repeat",
                " truncate",
                " source-derived",
            ):
                self.assertNotIn(untranslated, prose_without_code, recipe_id)
            self.assertEqual(
                EXPECTED_FRAGMENT_NODES[recipe_id],
                [(node["classType"], node["settings"]) for node in fragment["nodes"]],
            )

        self.assertEqual([], errors)

    def test_research_records_are_honest(self) -> None:
        schema = catalog.load_json(catalog.CONTENT / "schemas" / "article-research.schema.v1.json")
        for article_id, spec in ARTICLE_SPECS.items():
            record = catalog.load_json(catalog.CONTENT / "research" / "reviews" / f"{article_id}.json")
            self.assertEqual([], catalog.json_schema_errors(record, schema))
            self.assertEqual(spec["classType"], record["node"]["classType"])
            self.assertEqual("comfy_extras.nodes_latent", record["node"]["pythonModule"])
            self.assertEqual("fact_checked", record["state"])
            self.assertEqual("automated_assisted", record["reviewMode"])
            self.assertFalse(record["checks"]["exampleExecuted"])
            self.assertTrue(record["checks"]["exampleSchemaValidated"])
            self.assertTrue(record["knownGaps"])

    def test_runtime_fingerprints_ports_settings_and_fragment_contracts(self) -> None:
        nodes = catalog.object_info_nodes(catalog.load_json(FULL_INVENTORY))
        for article_id, spec in ARTICLE_SPECS.items():
            runtime = nodes[spec["classType"]]
            article = catalog.load_json(article_path(spec))
            self.assertEqual("comfy_extras.nodes_latent", runtime["python_module"])
            self.assertEqual(spec["fingerprint"], catalog.schema_fingerprint(spec["classType"], runtime))
            self.assertEqual(spec["fingerprint"], article["editorial"]["schemaHash"])
            self.assertFalse(runtime["is_input_list"])
            self.assertEqual([False], runtime["output_is_list"])
            self.assertFalse(runtime.get("deprecated", False))
            self.assertFalse(runtime.get("experimental", False))

        self.assertEqual(
            {"default": 1.0, "min": -10.0, "max": 10.0, "step": 0.01},
            nodes["LatentMultiply"]["input"]["required"]["multiplier"][1],
        )
        self.assertEqual(
            {"default": 1.0, "min": 0.0, "max": 1.0, "step": 0.01},
            nodes["LatentInterpolate"]["input"]["required"]["ratio"][1],
        )

        for recipe_id in RECIPE_DIRECTORIES:
            path = recipe_path(recipe_id)
            recipe = catalog.load_json(path)
            fragment = catalog.load_json(path.parent / recipe["fragment"]["path"])
            refs = {node["ref"]: node for node in fragment["nodes"]}
            for external in fragment["externalInputs"]:
                runtime = nodes[refs[external["to"]]["classType"]]
                descriptor = runtime_inputs(runtime)[external["input"]]
                self.assertEqual(external["type"], descriptor[0])
            for node in fragment["nodes"]:
                inputs = runtime_inputs(nodes[node["classType"]])
                for name, value in node["settings"].items():
                    options = inputs[name][1]
                    self.assertGreaterEqual(value, options.get("min", value))
                    self.assertLessEqual(value, options.get("max", value))

    @unittest.skipUnless(SOURCE.exists(), "pinned ComfyUI source checkout is absent")
    def test_articles_track_exact_pinned_source_and_replacements(self) -> None:
        source = (SOURCE / "comfy_extras" / "nodes_latent.py").read_text(encoding="utf-8")
        utils = (SOURCE / "comfy" / "utils.py").read_text(encoding="utf-8")
        replacements = (SOURCE / "comfy_extras" / "nodes_replacements.py").read_text(encoding="utf-8")

        self.assertIn('samples_out["samples"] = s1 + s2', source)
        self.assertIn('samples_out["samples"] = s1 - s2', source)
        self.assertIn('samples_out["samples"] = s1 * multiplier', source)
        self.assertIn("s2 = reshape_latent_to(s1.shape, s2)", source)
        self.assertIn("m1 = torch.linalg.vector_norm(s1, dim=(1))", source)
        self.assertIn("m2 = torch.linalg.vector_norm(s2, dim=(1))", source)
        self.assertNotIn("vector_norm(s1, dim=(1), keepdim=True)", source)
        self.assertIn("t = (s1 * ratio + s2 * (1.0 - ratio))", source)
        self.assertIn("st * (m1 * ratio + m2 * (1.0 - ratio))", source)
        self.assertIn("torch.nan_to_num", source)
        self.assertIn("math.ceil(batch_size / tensor.shape[dim])", utils)

        for spec in ARTICLE_SPECS.values():
            self.assertNotIn(spec["classType"], replacements)

    @unittest.skipUnless(DOCS_WHEEL.exists(), "pinned embedded docs wheel is absent")
    def test_embedded_docs_ratio_discrepancy_is_recorded(self) -> None:
        self.assertEqual(DOCS_WHEEL_SHA256, hashlib.sha256(DOCS_WHEEL.read_bytes()).hexdigest())
        with zipfile.ZipFile(DOCS_WHEEL) as archive:
            english = archive.read("comfyui_embedded_docs/docs/LatentInterpolate/en.md").decode("utf-8")
            russian = archive.read("comfyui_embedded_docs/docs/LatentInterpolate/ru.md").decode("utf-8")
        self.assertIn("A ratio of 0 produces a copy of the first set", english)
        self.assertIn("while a ratio of 1 produces a copy of the second set", english)
        self.assertIn("Коэффициент 0 создает копию первого набора", russian)
        article = (article_path(ARTICLE_SPECS["core.latent-interpolate"]).parent / "ru.md").read_text(encoding="utf-8")
        self.assertIn("`samples1` при `ratio = 1`", article)
        self.assertIn("подготовленные `samples2` — при `ratio = 0`", article)
        self.assertIn("при batch 1", article)

    @unittest.skipUnless(WORKFLOW_WHEEL.exists(), "official workflow wheel is absent")
    def test_exhaustive_official_root_and_subgraph_census(self) -> None:
        self.assertEqual(WORKFLOW_WHEEL_SHA256, hashlib.sha256(WORKFLOW_WHEEL.read_bytes()).hexdigest())
        targets = {spec["classType"] for spec in ARTICLE_SPECS.values()}
        counts: Counter[str] = Counter()
        file_count = 0
        with zipfile.ZipFile(WORKFLOW_WHEEL) as archive:
            for member in sorted(archive.namelist()):
                if "/templates/" not in member or not member.endswith(".json"):
                    continue
                file_count += 1
                payload = json.loads(archive.read(member).decode("utf-8"))
                if not isinstance(payload, dict):
                    continue
                for node in workflow_nodes(payload):
                    if node.get("type") in targets:
                        counts[node["type"]] += 1
        self.assertEqual(512, file_count)
        self.assertEqual({}, dict(counts))

    @unittest.skipUnless(SOURCE.exists(), "pinned ComfyUI source checkout is absent")
    def test_safe_exact_source_synthetic_tensor_execution(self) -> None:
        candidates = [
            Path(os.environ.get("TEMP", "")) / "nodes-wizard-comfyui-v0.32.0-venv" / "Scripts" / "python.exe",
            Path(sys.executable),
        ]
        python = next((candidate for candidate in candidates if candidate.exists()), None)
        if python is None:
            self.skipTest("no Python interpreter for synthetic probe")
        result = subprocess.run(
            [str(python), "-X", "utf8", str(SYNTHETIC_PROBE), str(SOURCE)],
            cwd=catalog.ROOT,
            text=True,
            capture_output=True,
            timeout=60,
            check=False,
        )
        if result.returncode != 0:
            self.skipTest(f"synthetic probe dependencies unavailable: {result.stderr}")
        payload = json.loads(result.stdout.strip().splitlines()[-1])
        self.assertEqual([3, 4, 2, 2], payload["add"]["shape"])
        self.assertEqual([10.0, 36.0, 42.0], payload["add"]["firstChannelOrigin"])
        self.assertEqual([-10.0, -4.0, 22.0], payload["subtract"]["firstChannelOrigin"])
        self.assertEqual([0.0, 4.0], payload["interpolate"]["ratioZero"])
        self.assertEqual([3.0, 0.0], payload["interpolate"]["ratioOne"])
        self.assertEqual(0, payload["interpolate"]["oppositeMidpointNonzero"])
        self.assertIn("size of tensor a (4)", payload["interpolate"]["batchTwoError"])
        self.assertFalse(payload["interpolate"]["batchFourRatioOneIdentity"])
        self.assertTrue(payload["interpolate"]["metadataFromFirst"])
        self.assertEqual([2, 4, 2, 2], payload["broadcast"]["channelOneToFourShape"])


if __name__ == "__main__":
    unittest.main()
