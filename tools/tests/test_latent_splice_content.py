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
    "core.latent-concat": {
        "directory": "latent-concat",
        "classType": "LatentConcat",
        "fingerprint": "sha256:85c9a8c4013f3ef5d36323a7ceef80db842a132324e2a2c26ff74458b01bbae2",
        "recipes": {"recipe.duplicate-first-video-latent-frame"},
    },
    "core.latent-cut": {
        "directory": "latent-cut",
        "classType": "LatentCut",
        "fingerprint": "sha256:816fad03ac717bf798aeaf0a76bccc7044bad162abccbf8cbaa5e32f323a0afa",
        "recipes": {
            "recipe.duplicate-first-video-latent-frame",
            "recipe.layered-latent-to-batch",
        },
    },
    "core.latent-cut-to-batch": {
        "directory": "latent-cut-to-batch",
        "classType": "LatentCutToBatch",
        "fingerprint": "sha256:1dd8d886315b53750ae51647af144b132d6ce8b31219d888950b032ebb6e3508",
        "recipes": {"recipe.layered-latent-to-batch"},
    },
    "core.replace-video-latent-frames": {
        "directory": "replace-video-latent-frames",
        "classType": "ReplaceVideoLatentFrames",
        "fingerprint": "sha256:fe4fdb7752cdced02b19586cf98ea0e4c7d7425e3f5289d856d6c59c8a2fd4e8",
        "recipes": {"recipe.replace-video-latent-start"},
    },
}

RECIPE_DIRECTORIES = {
    "recipe.duplicate-first-video-latent-frame": "duplicate-first-video-latent-frame",
    "recipe.layered-latent-to-batch": "layered-latent-to-batch",
    "recipe.replace-video-latent-start": "replace-video-latent-start",
}

EXPECTED_FRAGMENT_NODES = {
    "recipe.duplicate-first-video-latent-frame": [
        ("LatentCut", {"dim": "t", "index": 0, "amount": 1}),
        ("LatentConcat", {"dim": "t"}),
    ],
    "recipe.layered-latent-to-batch": [
        ("LatentCut", {"dim": "t", "index": 1, "amount": 16384}),
        ("LatentCutToBatch", {"dim": "t", "slice_size": 1}),
    ],
    "recipe.replace-video-latent-start": [
        ("ReplaceVideoLatentFrames", {"index": 0}),
    ],
}

FULL_INVENTORY = catalog.CONTENT / "runtime" / "comfyui-0.32.0.object-info.json"
SOURCE = catalog.ROOT / ".comfyui-source-0.32.0"
SOURCE_COMMIT = "c2bcbecd82ec5ae66594340b395c24ef0217b238"
REPLACEMENTS = catalog.CONTENT / "runtime" / "comfyui-0.32.0.node-replacements.json"
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
PROBE = Path(__file__).with_name("latent_splice_synthetic_probe.py")


def article_path(spec: dict[str, Any]) -> Path:
    return catalog.CONTENT / "articles" / "core" / spec["directory"] / "manifest.json"


def recipe_path(recipe_id: str) -> Path:
    return catalog.CONTENT / "recipes" / RECIPE_DIRECTORIES[recipe_id] / "recipe.json"


def all_article_ids() -> set[str]:
    result: set[str] = set()
    for path in (catalog.CONTENT / "articles").rglob("manifest.json"):
        value = catalog.load_json(path)
        if isinstance(value, dict) and isinstance(value.get("articleId"), str):
            result.add(value["articleId"])
    return result


def normalized_link(link: Any) -> dict[str, Any]:
    if isinstance(link, list):
        return {
            "id": link[0],
            "origin_id": link[1],
            "origin_slot": link[2],
            "target_id": link[3],
            "target_slot": link[4],
            "type": link[5],
        }
    if isinstance(link, dict):
        return link
    raise AssertionError(f"unsupported workflow link: {link!r}")


def workflow_records(payload: dict[str, Any], member: str) -> Iterator[dict[str, Any]]:
    if isinstance(payload.get("nodes"), list):
        for node in payload["nodes"]:
            if isinstance(node, dict):
                yield {"member": member, "scope": "root", "node": node, "graph": payload}
    definitions = payload.get("definitions")
    subgraphs = definitions.get("subgraphs", []) if isinstance(definitions, dict) else []
    for index, subgraph in enumerate(subgraphs):
        if not isinstance(subgraph, dict):
            continue
        for node in subgraph.get("nodes", []):
            if isinstance(node, dict):
                yield {
                    "member": member,
                    "scope": f"subgraph:{index}",
                    "node": node,
                    "graph": subgraph,
                }


class LatentSpliceContentTests(unittest.TestCase):
    def test_articles_recipes_fragments_and_research_validate(self) -> None:
        article_ids = all_article_ids()
        schemas = {
            name: catalog.load_json(catalog.CONTENT / "schemas" / filename)
            for name, filename in {
                "article": "article.schema.v1.json",
                "recipe": "recipe.schema.v1.json",
                "fragment": "recipe-fragment.schema.v1.json",
                "research": "article-research.schema.v1.json",
            }.items()
        }
        errors: list[str] = []
        cliche = re.compile(
            r"важно отметить|стоит отметить|следует отметить|в современном мире|"
            r"революционн|является мощн|\bдавайте\b|глубже погруз|"
            r"подводя итог|в заключение|данная нода|не просто .{0,80},? а ",
            re.IGNORECASE,
        )

        for article_id, spec in ARTICLE_SPECS.items():
            path = article_path(spec)
            article = catalog.load_json(path)
            self.assertEqual([], catalog.json_schema_errors(article, schemas["article"]))
            catalog.validate_article(path, article, errors)
            self.assertEqual(article_id, article["articleId"])
            self.assertEqual("draft", article["status"])
            self.assertEqual("in_review", article["editorial"]["state"])
            self.assertFalse(article["experimental"])
            self.assertEqual([], article["runtimeIdentity"]["aliases"])
            self.assertEqual("comfy_extras.nodes_latent", article["runtimeIdentity"]["pythonModule"])
            self.assertEqual(spec["fingerprint"], article["editorial"]["schemaHash"])
            self.assertEqual(
                spec["recipes"],
                {asset["id"] for asset in article["assets"] if asset["type"] == "recipe"},
            )
            targets = set(article["relations"]["related"] + article["relations"]["alternatives"])
            if article["relations"]["replacedBy"] is not None:
                targets.add(article["relations"]["replacedBy"])
            self.assertTrue(targets.issubset(article_ids), (article_id, targets))

            body = (path.parent / article["body"]).read_text(encoding="utf-8")
            self.assertEqual(10, len(re.findall(r"^## .+$", body, re.MULTILINE)))
            self.assertNotIn("\ufffd", body)
            self.assertIsNone(cliche.search(body), article_id)

            research = catalog.load_json(
                catalog.CONTENT / "research" / "reviews" / f"{article_id}.json"
            )
            self.assertEqual([], catalog.json_schema_errors(research, schemas["research"]))
            self.assertEqual("fact_checked", research["state"])
            self.assertEqual("automated_assisted", research["reviewMode"])
            self.assertTrue(research["checks"]["exampleSchemaValidated"])
            self.assertFalse(research["checks"]["exampleExecuted"])
            self.assertTrue(research["checks"]["russianEdited"])
            self.assertTrue(research["knownGaps"])

        for recipe_id in RECIPE_DIRECTORIES:
            path = recipe_path(recipe_id)
            recipe = catalog.load_json(path)
            self.assertEqual([], catalog.json_schema_errors(recipe, schemas["recipe"]))
            catalog.validate_recipe(path, recipe, article_ids, errors)
            self.assertEqual(recipe_id, recipe["recipeId"])
            self.assertEqual("in_review", recipe["editorial"]["state"])
            self.assertIn("human approval pending", recipe["editorial"]["reviewedBy"])
            self.assertNotIn("workflow", recipe)

            fragment_path = path.parent / recipe["fragment"]["path"]
            fragment = catalog.load_json(fragment_path)
            self.assertEqual([], catalog.json_schema_errors(fragment, schemas["fragment"]))
            catalog.validate_fragment(fragment_path, fragment, errors)
            self.assertEqual(
                EXPECTED_FRAGMENT_NODES[recipe_id],
                [(node["classType"], node["settings"]) for node in fragment["nodes"]],
            )
        self.assertEqual([], errors)

    def test_runtime_fingerprints_ports_settings_and_fragment_types(self) -> None:
        inventory = catalog.load_json(FULL_INVENTORY)
        expected_required = {
            "LatentConcat": ["samples1", "samples2", "dim"],
            "LatentCut": ["samples", "dim", "index", "amount"],
            "LatentCutToBatch": ["samples", "dim", "slice_size"],
            "ReplaceVideoLatentFrames": ["destination", "index"],
        }
        for spec in ARTICLE_SPECS.values():
            class_type = spec["classType"]
            runtime = inventory[class_type]
            self.assertEqual("comfy_extras.nodes_latent", runtime["python_module"])
            self.assertEqual(expected_required[class_type], runtime["input_order"]["required"])
            self.assertEqual(["LATENT"], runtime["output"])
            self.assertFalse(runtime.get("deprecated", False))
            self.assertFalse(runtime.get("experimental", False))
            self.assertFalse(runtime.get("dev_only", False))
            self.assertEqual(spec["fingerprint"], catalog.schema_fingerprint(class_type, runtime))

        self.assertEqual(["source"], inventory["ReplaceVideoLatentFrames"]["input_order"]["optional"])
        self.assertEqual(
            ["x", "-x", "y", "-y", "t", "-t"],
            inventory["LatentConcat"]["input"]["required"]["dim"][1]["options"],
        )
        self.assertEqual(
            {"default": 0, "min": -16384, "max": 16384, "step": 1},
            inventory["LatentCut"]["input"]["required"]["index"][1],
        )
        self.assertEqual(
            {"default": 1, "min": 1, "max": 16384, "step": 1},
            inventory["LatentCutToBatch"]["input"]["required"]["slice_size"][1],
        )

        for recipe_id in RECIPE_DIRECTORIES:
            recipe = catalog.load_json(recipe_path(recipe_id))
            fragment = catalog.load_json(recipe_path(recipe_id).parent / recipe["fragment"]["path"])
            nodes = {node["ref"]: node for node in fragment["nodes"]}
            for external in fragment["externalInputs"]:
                runtime = inventory[nodes[external["to"]]["classType"]]
                inputs = {**runtime["input"].get("required", {}), **runtime["input"].get("optional", {})}
                self.assertEqual(external["type"], inputs[external["input"]][0])
            for connection in fragment["connections"]:
                source = inventory[nodes[connection["from"]]["classType"]]
                target = inventory[nodes[connection["to"]]["classType"]]
                source_index = source["output_name"].index(connection["output"])
                self.assertEqual(
                    source["output"][source_index],
                    target["input"]["required"][connection["input"]][0],
                )

    @unittest.skipUnless(SOURCE.exists(), "pinned ComfyUI source checkout is absent")
    def test_exact_pinned_source_and_replacement_absence(self) -> None:
        latent = (SOURCE / "comfy_extras" / "nodes_latent.py").read_text(encoding="utf-8")
        utils = (SOURCE / "comfy" / "utils.py").read_text(encoding="utf-8")
        self.assertIn('s2 = comfy.utils.repeat_to_batch_size(s2, s1.shape[0])', latent)
        self.assertIn('c = (s2, s1)', latent)
        self.assertIn('dim = -3', latent)
        self.assertIn('samples_out["samples"] = torch.cat(c, dim=dim)', latent)
        self.assertIn('samples_out["samples"] = torch.narrow(s1, dim, index, amount)', latent)
        self.assertIn('index = min(index, s1.shape[dim] - 1)', latent)
        self.assertIn('index = max(index, -s1.shape[dim])', latent)
        self.assertIn('if dim < 2:', latent)
        self.assertIn('return io.NodeOutput(samples)', latent)
        self.assertIn('s = s[:, :math.floor(s.shape[1] / slice_size) * slice_size]', latent)
        self.assertIn('samples_out["samples"] = s.reshape(new_shape).movedim(1, dim)', latent)
        self.assertIn('dest_frames = destination["samples"].shape[2]', latent)
        self.assertIn('index = dest_frames + index', latent)
        self.assertIn('s = source.copy()', latent)
        self.assertIn('s_destination = destination["samples"].clone()', latent)
        self.assertIn('return tensor.repeat(', utils)
        self.assertIn('.narrow(dim, 0, batch_size)', utils)

        replacements = REPLACEMENTS.read_text(encoding="utf-8")
        for spec in ARTICLE_SPECS.values():
            self.assertNotIn(spec["classType"], replacements)

    @unittest.skipUnless(DOCS_WHEEL.exists(), "pinned embedded-docs wheel is absent")
    def test_pinned_embedded_docs_paths_and_omissions(self) -> None:
        self.assertEqual(DOCS_WHEEL_SHA256, hashlib.sha256(DOCS_WHEEL.read_bytes()).hexdigest())
        with zipfile.ZipFile(DOCS_WHEEL) as archive:
            docs: dict[str, str] = {}
            for spec in ARTICLE_SPECS.values():
                for locale in ("en", "ru"):
                    member = f"comfyui_embedded_docs/docs/{spec['classType']}/{locale}.md"
                    self.assertIn(member, archive.namelist())
                    docs[f"{spec['classType']}:{locale}"] = archive.read(member).decode("utf-8")
        self.assertNotIn("shared storage", docs["LatentCut:en"].lower())
        self.assertNotIn("four-dimensional", docs["LatentConcat:en"].lower())
        self.assertNotIn("return the same", docs["LatentCutToBatch:en"].lower())
        self.assertNotIn("source metadata", docs["ReplaceVideoLatentFrames:en"].lower())

    @unittest.skipUnless(WORKFLOW_WHEEL.exists(), "official workflow wheel is absent")
    def test_exhaustive_official_census_and_exact_topologies(self) -> None:
        self.assertEqual(WORKFLOW_WHEEL_SHA256, hashlib.sha256(WORKFLOW_WHEEL.read_bytes()).hexdigest())
        targets = {spec["classType"] for spec in ARTICLE_SPECS.values()}
        records: list[dict[str, Any]] = []
        graphs: dict[tuple[str, str], dict[str, Any]] = {}
        json_count = 0
        root_graph_count = 0
        with zipfile.ZipFile(WORKFLOW_WHEEL) as archive:
            members = [
                name for name in archive.namelist()
                if "/templates/" in name and name.endswith(".json")
            ]
            for member in members:
                json_count += 1
                payload = json.loads(archive.read(member).decode("utf-8"))
                if not isinstance(payload, dict):
                    continue
                if isinstance(payload.get("nodes"), list):
                    root_graph_count += 1
                for record in workflow_records(payload, member):
                    graphs[(Path(member).name, record["scope"])] = record["graph"]
                    if record["node"].get("type") in targets:
                        records.append(record)
        self.assertEqual(512, json_count)
        self.assertEqual(496, root_graph_count)
        self.assertEqual(
            {"LatentConcat": 8, "LatentCut": 5, "LatentCutToBatch": 4, "ReplaceVideoLatentFrames": 1},
            dict(Counter(record["node"]["type"] for record in records)),
        )
        self.assertEqual(
            {"LatentConcat": (2, 6), "LatentCut": (2, 3), "LatentCutToBatch": (0, 4), "ReplaceVideoLatentFrames": (0, 1)},
            {
                class_type: (
                    sum(r["scope"] == "root" for r in records if r["node"]["type"] == class_type),
                    sum(r["scope"] != "root" for r in records if r["node"]["type"] == class_type),
                )
                for class_type in targets
            },
        )

        wan = graphs[("video_wan2_2_14B_s2v.json", "root")]
        wan_nodes = {node["id"]: node for node in wan["nodes"]}
        wan_links = {link["id"]: link for link in map(normalized_link, wan["links"])}
        self.assertEqual(["t", 0, 1], wan_nodes[94]["widgets_values"])
        self.assertEqual(["t"], wan_nodes[95]["widgets_values"])
        self.assertEqual((87, 0, 94, 0, "LATENT"), tuple(wan_links[279][key] for key in ("origin_id", "origin_slot", "target_id", "target_slot", "type")))
        self.assertEqual((94, 0, 95, 0, "LATENT"), tuple(wan_links[269][key] for key in ("origin_id", "origin_slot", "target_id", "target_slot", "type")))
        self.assertEqual((87, 0, 95, 1, "LATENT"), tuple(wan_links[280][key] for key in ("origin_id", "origin_slot", "target_id", "target_slot", "type")))
        self.assertEqual((95, 0, 80, 0, "LATENT"), tuple(wan_links[271][key] for key in ("origin_id", "origin_slot", "target_id", "target_slot", "type")))

        for scope, cut_id, batch_id, link_id in (("subgraph:0", 140, 76, 197), ("subgraph:1", 141, 123, 198)):
            qwen = graphs[("image_qwen_image_layered.json", scope)]
            nodes = {node["id"]: node for node in qwen["nodes"]}
            links = {link["id"]: link for link in map(normalized_link, qwen["links"])}
            self.assertEqual(["t", 1, 16384], nodes[cut_id]["widgets_values"])
            self.assertEqual(["t", 1], nodes[batch_id]["widgets_values"])
            self.assertEqual((cut_id, 0, batch_id, 0, "LATENT"), tuple(links[link_id][key] for key in ("origin_id", "origin_slot", "target_id", "target_slot", "type")))

        kandinsky = graphs[("video_kandinsky5_i2v.json", "subgraph:0")]
        k_nodes = {node["id"]: node for node in kandinsky["nodes"]}
        k_links = {link["id"]: link for link in map(normalized_link, kandinsky["links"])}
        self.assertEqual([0], k_nodes[64]["widgets_values"])
        self.assertEqual((63, 0, 64, 0, "LATENT"), tuple(k_links[98][key] for key in ("origin_id", "origin_slot", "target_id", "target_slot", "type")))
        self.assertEqual((62, 3, 64, 1, "LATENT"), tuple(k_links[99][key] for key in ("origin_id", "origin_slot", "target_id", "target_slot", "type")))
        self.assertEqual((64, 0, 69, 0, "LATENT"), tuple(k_links[104][key] for key in ("origin_id", "origin_slot", "target_id", "target_slot", "type")))

    @unittest.skipUnless(SOURCE.exists(), "pinned ComfyUI source checkout is absent")
    def test_safe_exact_source_tensor_probe(self) -> None:
        candidates = [
            Path(os.environ.get("TEMP", ""))
            / "nodes-wizard-comfyui-v0.32.0-venv"
            / "Scripts"
            / "python.exe",
            Path(sys.executable),
        ]
        python = next((candidate for candidate in candidates if candidate.exists()), None)
        if python is None:
            self.skipTest("no Python interpreter for latent splice probe")
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
        self.assertEqual([2, 1, 3, 2, 3], payload["concat"]["videoShape"])
        self.assertEqual([1, 5, 2, 2], payload["concat"]["imageTShape"])
        self.assertEqual([3.0, 4.0], payload["cut"]["lastTwo"])
        self.assertEqual([1, 2, 1, 1], payload["cut"]["imageTShape"])
        self.assertEqual([4, 1, 2, 2, 2], payload["cutToBatch"]["shape"])
        self.assertTrue(payload["cutToBatch"]["fourDTIsIdentity"])
        self.assertEqual([0.0, 7.0, 8.0, 0.0, 0.0], payload["replace"]["frames"])
        self.assertEqual("source", payload["replace"]["metadataOrigin"])
        self.assertTrue(payload["replace"]["tooNegativeRaises"])


if __name__ == "__main__":
    unittest.main()
