from __future__ import annotations

import hashlib
import json
import re
import unittest
import zipfile
from pathlib import Path
from typing import Any, Iterator

from tools import catalog


SPECS: dict[str, dict[str, Any]] = {
    "core.latent-from-batch": {
        "directory": "latent-from-batch",
        "classType": "LatentFromBatch",
        "module": "nodes",
        "fingerprint": "sha256:6de3b69a5eb3585bf2c6cd8b289a29f80fadd2032ae793e04cc0e5a1f4a58f05",
        "recipe": "select-latent-batch-segment",
    },
    "core.repeat-latent-batch": {
        "directory": "repeat-latent-batch",
        "classType": "RepeatLatentBatch",
        "module": "nodes",
        "fingerprint": "sha256:771a0ccccf7c04bee1534c157714cacf802204ea76fb0426737a758dd42779f1",
        "recipe": "repeat-latent-fixed-noise",
    },
    "core.latent-batch": {
        "directory": "latent-batch",
        "classType": "LatentBatch",
        "module": "comfy_extras.nodes_latent",
        "fingerprint": "sha256:e69f693910f25143899f9b3bd13f8d31a7a619763b6c4dcca796c0a870688c6f",
        "recipe": "combine-two-latent-batches-legacy",
    },
    "core.latent-batch-seed-behavior": {
        "directory": "latent-batch-seed-behavior",
        "classType": "LatentBatchSeedBehavior",
        "module": "comfy_extras.nodes_latent",
        "fingerprint": "sha256:0298a35da1ade870e5c172d6f1a9a35b018df758d3a11a89bf88a1e79fc83567",
        "recipe": "repeat-latent-fixed-noise",
    },
}

INVENTORY = catalog.CONTENT / "runtime" / "comfyui-0.32.0.object-info.json"
REPLACEMENTS = catalog.CONTENT / "runtime" / "comfyui-0.32.0.node-replacements.json"
SOURCE = catalog.ROOT / ".comfyui-source-0.32.0"
DOCS = catalog.ROOT / ".upstream-cache" / "comfyui_embedded_docs-0.5.9-py3-none-any.whl"
WORKFLOWS = catalog.ROOT / ".upstream-cache" / "comfyui_workflow_templates_json-0.1.42-py3-none-any.whl"
DOCS_SHA256 = "30afae432a71c96aa59421d0f37388c66ff6572b8cbeee8ff045e4d5f84f896c"
WORKFLOWS_SHA256 = "242982d65e1c51ca03d892bc1009bb6843f457e7dfc0c20afe6438770b7a14a3"


def article_path(spec: dict[str, Any]) -> Path:
    return catalog.CONTENT / "articles" / "core" / spec["directory"] / "manifest.json"


def graph_scopes(payload: dict[str, Any]) -> Iterator[dict[str, Any]]:
    if isinstance(payload.get("nodes"), list):
        yield payload
    definitions = payload.get("definitions")
    if isinstance(definitions, dict):
        for subgraph in definitions.get("subgraphs", []):
            if isinstance(subgraph, dict):
                yield subgraph


class LatentBatchContentTests(unittest.TestCase):
    def test_articles_recipes_and_ledgers_are_closed_and_honest(self) -> None:
        article_schema = catalog.load_json(catalog.CONTENT / "schemas" / "article.schema.v1.json")
        recipe_schema = catalog.load_json(catalog.CONTENT / "schemas" / "recipe.schema.v1.json")
        fragment_schema = catalog.load_json(catalog.CONTENT / "schemas" / "recipe-fragment.schema.v1.json")
        research_schema = catalog.load_json(catalog.CONTENT / "schemas" / "article-research.schema.v1.json")
        article_ids = {
            catalog.load_json(path)["articleId"]
            for path in (catalog.CONTENT / "articles").rglob("manifest.json")
        }
        errors: list[str] = []
        recipe_directories = {spec["recipe"] for spec in SPECS.values()}

        for article_id, spec in SPECS.items():
            path = article_path(spec)
            article = catalog.load_json(path)
            self.assertEqual([], catalog.json_schema_errors(article, article_schema), article_id)
            catalog.validate_article(path, article, errors)
            self.assertEqual("draft", article["status"])
            self.assertEqual("in_review", article["editorial"]["state"])
            self.assertIn("human approval pending", article["editorial"]["reviewedBy"])
            self.assertEqual(10, len(re.findall(r"^## ", (path.parent / article["body"]).read_text(encoding="utf-8"), re.MULTILINE)))
            record = catalog.load_json(catalog.CONTENT / "research" / "reviews" / f"{article_id}.json")
            self.assertEqual([], catalog.json_schema_errors(record, research_schema), article_id)
            self.assertEqual("fact_checked", record["state"])
            self.assertFalse(record["checks"]["exampleExecuted"])
            self.assertTrue(record["knownGaps"])

        for directory in recipe_directories:
            path = catalog.CONTENT / "recipes" / directory / "recipe.json"
            recipe = catalog.load_json(path)
            self.assertEqual([], catalog.json_schema_errors(recipe, recipe_schema), directory)
            catalog.validate_recipe(path, recipe, article_ids, errors)
            self.assertNotIn("workflow", recipe)
            fragment = catalog.load_json(path.parent / recipe["fragment"]["path"])
            self.assertEqual([], catalog.json_schema_errors(fragment, fragment_schema), directory)
            catalog.validate_fragment(path.parent / recipe["fragment"]["path"], fragment, errors)
            recipe_body = (path.parent / recipe["body"]).read_text(encoding="utf-8")
            prose_without_code = re.sub(
                r"`[^`]+`|https?://\S+", "", recipe_body
            ).casefold()
            for untranslated in (
                " fragment",
                " workflow",
                " batch-",
                " batch ",
                " runtime",
                " schema",
                " pinned",
                " source-derived",
                " downstream",
                " broadcast",
                " spatial-",
                " bilinear resize",
                " center crop",
                " deprecated",
                " autogrow",
                " full audit",
            ):
                self.assertNotIn(untranslated, prose_without_code, directory)
        self.assertEqual([], errors)

    def test_runtime_identity_ports_and_fingerprints(self) -> None:
        nodes = catalog.object_info_nodes(catalog.load_json(INVENTORY))
        for article_id, spec in SPECS.items():
            runtime = nodes[spec["classType"]]
            article = catalog.load_json(article_path(spec))
            self.assertEqual(spec["module"], runtime["python_module"], article_id)
            self.assertEqual(spec["fingerprint"], catalog.schema_fingerprint(spec["classType"], runtime), article_id)
            self.assertEqual(spec["fingerprint"], article["editorial"]["schemaHash"], article_id)
            self.assertFalse(runtime.get("api_node", False))
            self.assertFalse(runtime.get("dev_only", False))
        self.assertEqual(64, nodes["LatentFromBatch"]["input"]["required"]["length"][1]["max"])
        self.assertEqual(64, nodes["RepeatLatentBatch"]["input"]["required"]["amount"][1]["max"])
        self.assertTrue(nodes["LatentBatch"]["deprecated"])
        seed_behavior = nodes["LatentBatchSeedBehavior"]["input"]["required"]["seed_behavior"]
        self.assertEqual("COMBO", seed_behavior[0])
        self.assertEqual(["random", "fixed"], seed_behavior[1]["options"])
        self.assertEqual("fixed", seed_behavior[1]["default"])

    def test_pinned_source_exact_semantics_and_no_formal_replacements(self) -> None:
        nodes_source = (SOURCE / "nodes.py").read_text(encoding="utf-8")
        latent_source = (SOURCE / "comfy_extras" / "nodes_latent.py").read_text(encoding="utf-8")
        sample_source = (SOURCE / "comfy" / "sample.py").read_text(encoding="utf-8")
        for marker in (
            "batch_index += s_in.shape[0]",
            "s_in[batch_index:batch_index + length].clone()",
            "s_in.repeat((amount,)",
            "offset = max(s[\"batch_index\"]) - min(s[\"batch_index\"]) + 1",
        ):
            self.assertIn(marker, nodes_source)
        for marker in (
            "reshape_latent_to(s1.shape, s2, repeat_batch=False)",
            "torch.cat((s1, s2), dim=0)",
            "samples_out.pop('batch_index')",
            "[batch_number] * latent.shape[0]",
        ):
            self.assertIn(marker, latent_source)
        self.assertIn("for i in range(unique_inds[-1]+1)", sample_source)
        replacements = json.dumps(catalog.load_json(REPLACEMENTS), ensure_ascii=False)
        for spec in SPECS.values():
            self.assertNotIn(spec["classType"], replacements)

    def test_docs_and_workflow_census_are_fail_closed(self) -> None:
        self.assertEqual(DOCS_SHA256, hashlib.sha256(DOCS.read_bytes()).hexdigest())
        with zipfile.ZipFile(DOCS) as archive:
            names = set(archive.namelist())
            for class_type in ("LatentFromBatch", "RepeatLatentBatch", "LatentBatch", "LatentBatchSeedBehavior"):
                self.assertIn(f"comfyui_embedded_docs/docs/{class_type}/en.md", names)

        self.assertEqual(WORKFLOWS_SHA256, hashlib.sha256(WORKFLOWS.read_bytes()).hexdigest())
        targets = {spec["classType"] for spec in SPECS.values()}
        counts = {target: 0 for target in targets}
        json_count = root_count = subgraph_count = 0
        with zipfile.ZipFile(WORKFLOWS) as archive:
            for member in archive.namelist():
                if "/templates/" not in member or not member.endswith(".json"):
                    continue
                json_count += 1
                payload = json.loads(archive.read(member).decode("utf-8"))
                scopes = list(graph_scopes(payload)) if isinstance(payload, dict) else []
                if scopes and isinstance(payload, dict) and isinstance(payload.get("nodes"), list):
                    root_count += 1
                subgraph_count += max(0, len(scopes) - (1 if isinstance(payload, dict) and isinstance(payload.get("nodes"), list) else 0))
                for scope in scopes:
                    for node in scope.get("nodes", []):
                        node_type = node.get("type") if isinstance(node, dict) else None
                        if node_type in counts:
                            counts[node_type] += 1
        self.assertEqual((512, 496, 272), (json_count, root_count, subgraph_count))
        self.assertEqual({target: 0 for target in targets}, counts)


if __name__ == "__main__":
    unittest.main()
