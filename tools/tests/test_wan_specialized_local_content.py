from __future__ import annotations

import hashlib
import json
import re
import unittest
import zipfile
from collections import Counter
from typing import Any, Iterator

from tools import catalog


SPECS = {
    "core.wan-animate-to-video": ("wan-animate-to-video", "WanAnimateToVideo", "comfy_extras.nodes_wan", "sha256:025c41fdd4245d311b315344b83391e7915a665599f84ed6408b1cd4b6ba5992", "wan-animate-local"),
    "core.wan-camera-embedding": ("wan-camera-embedding", "WanCameraEmbedding", "comfy_extras.nodes_camera_trajectory", "sha256:289ade05c62ae5e51f0a671fdb88551304857a65fdbd798c281edec0974f8215", "wan-camera-embedding-static"),
    "core.wan-camera-image-to-video": ("wan-camera-image-to-video", "WanCameraImageToVideo", "comfy_extras.nodes_wan", "sha256:034102a9c336bb82f1bd1de3a20e3e5294af54bfb30aa4c90c185587a5ea4ebf", "wan-camera-i2v-local"),
    "core.wan-dancer-video": ("wan-dancer-video", "WanDancerVideo", "comfy_extras.nodes_wandancer", "sha256:0d60a4efae99ae2de809b7d8a2b3116abd7b1509b11b8e307a937e4db904927f", "wan-dancer-video-local"),
    "core.wan-phantom-subject-to-video": ("wan-phantom-subject-to-video", "WanPhantomSubjectToVideo", "comfy_extras.nodes_wan", "sha256:2243df002e86dc79bbdc64a6dce0f80991e073cddbfe57cfbd3facbeca4f43e6", "wan-phantom-reference-local"),
    "core.wan-sound-image-to-video-extend": ("wan-sound-image-to-video-extend", "WanSoundImageToVideoExtend", "comfy_extras.nodes_wan", "sha256:69ac0006ca0e3a7746f0080d62bcf8b9bc6786cd873d0923820bb43da9c9c61a", "wan-sound-extend-local"),
    "core.wan-track-to-video": ("wan-track-to-video", "WanTrackToVideo", "comfy_extras.nodes_wan", "sha256:45fc5fc62cc55ca3036b861c8943503bbc304af943bf95e2bf0bf89dc887ef6d", "wan-track-motion-local"),
    "core.wan22-fun-control-to-video": ("wan22-fun-control-to-video", "Wan22FunControlToVideo", "comfy_extras.nodes_wan", "sha256:12b85982fb7d824bec3a790d7502b962cb462b578d92ca5472c1583c9afb50ae", "wan22-fun-control-local"),
}
ROOT = catalog.ROOT
INVENTORY = catalog.CONTENT / "runtime" / "comfyui-0.32.0.object-info.json"
REPLACEMENTS = catalog.CONTENT / "runtime" / "comfyui-0.32.0.node-replacements.json"
SOURCE = ROOT / ".comfyui-source-0.32.0"
DOCS = ROOT / ".upstream-cache" / "comfyui_embedded_docs-0.5.9-py3-none-any.whl"
WORKFLOWS = ROOT / ".upstream-cache" / "comfyui_workflow_templates_json-0.1.42-py3-none-any.whl"


def scopes(payload: Any) -> Iterator[dict[str, Any]]:
    if not isinstance(payload, dict):
        return
    if isinstance(payload.get("nodes"), list):
        yield payload
    definitions = payload.get("definitions")
    if isinstance(definitions, dict):
        yield from (graph for graph in definitions.get("subgraphs", []) if isinstance(graph, dict))


class WanSpecializedLocalContentTests(unittest.TestCase):
    def test_content_contracts_ten_sections_and_honesty(self) -> None:
        schemas = {name: catalog.load_json(catalog.CONTENT / "schemas" / name) for name in (
            "article.schema.v1.json", "recipe.schema.v1.json", "recipe-fragment.schema.v1.json", "article-research.schema.v1.json"
        )}
        article_ids = {catalog.load_json(path)["articleId"] for path in (catalog.CONTENT / "articles").rglob("manifest.json")}
        errors: list[str] = []
        for article_id, (directory, _class_type, _module, _fingerprint, recipe_id) in SPECS.items():
            path = catalog.CONTENT / "articles" / "core" / directory / "manifest.json"
            article = catalog.load_json(path)
            self.assertEqual([], catalog.json_schema_errors(article, schemas["article.schema.v1.json"]), article_id)
            catalog.validate_article(path, article, errors)
            self.assertEqual(("draft", "in_review"), (article["status"], article["editorial"]["state"]))
            self.assertEqual(10, len(re.findall(r"^## ", (path.parent / article["body"]).read_text(encoding="utf-8"), re.MULTILINE)))
            ledger = catalog.load_json(catalog.CONTENT / "research" / "reviews" / f"{article_id}.json")
            self.assertEqual([], catalog.json_schema_errors(ledger, schemas["article-research.schema.v1.json"]), article_id)
            self.assertFalse(ledger["checks"]["exampleExecuted"])
            self.assertTrue(any("человечес" in gap.casefold() for gap in ledger["knownGaps"]))
            recipe_path = catalog.CONTENT / "recipes" / recipe_id / "recipe.json"
            recipe = catalog.load_json(recipe_path)
            self.assertEqual([], catalog.json_schema_errors(recipe, schemas["recipe.schema.v1.json"]), recipe_id)
            catalog.validate_recipe(recipe_path, recipe, article_ids, errors)
            self.assertNotIn("workflow", recipe)
            fragment_path = recipe_path.parent / recipe["fragment"]["path"]
            fragment = catalog.load_json(fragment_path)
            self.assertEqual([], catalog.json_schema_errors(fragment, schemas["recipe-fragment.schema.v1.json"]), recipe_id)
            catalog.validate_fragment(fragment_path, fragment, errors)
        self.assertEqual([], errors)

    def test_runtime_fingerprints_flags_and_replacements(self) -> None:
        nodes = catalog.object_info_nodes(catalog.load_json(INVENTORY))
        for article_id, (directory, class_type, module, fingerprint, _recipe_id) in SPECS.items():
            runtime = nodes[class_type]
            article = catalog.load_json(catalog.CONTENT / "articles" / "core" / directory / "manifest.json")
            self.assertEqual(module, runtime["python_module"])
            self.assertEqual(fingerprint, catalog.schema_fingerprint(class_type, runtime), article_id)
            self.assertEqual(fingerprint, article["editorial"]["schemaHash"])
            self.assertFalse(runtime.get("api_node", False))
            self.assertFalse(runtime.get("deprecated", False))
        self.assertTrue(nodes["WanAnimateToVideo"].get("experimental", False))
        for class_type in set(spec[1] for spec in SPECS.values()) - {"WanAnimateToVideo"}:
            self.assertFalse(nodes[class_type].get("experimental", False))
        replacements = json.dumps(catalog.load_json(REPLACEMENTS), ensure_ascii=False)
        for spec in SPECS.values():
            self.assertNotIn(spec[1], replacements)

    def test_pinned_sources_and_documentation_evidence(self) -> None:
        paths = {
            "wan": (SOURCE / "comfy_extras" / "nodes_wan.py", "39ff111cc45c8d2a75cab1aa3b97ad9bf9037868178af2468bc52b34dbd0d96d"),
            "camera": (SOURCE / "comfy_extras" / "nodes_camera_trajectory.py", "6db196d3599578c143f3d7acfec234acca70631babe0243950bc94d161296656"),
            "dancer": (SOURCE / "comfy_extras" / "nodes_wandancer.py", "489620943dc79abf1b71f90055ec2a9b91008eaf4b6dd4dc0a941037a2d38420"),
        }
        combined = ""
        for path, digest in paths.values():
            self.assertEqual(digest, hashlib.sha256(path.read_bytes()).hexdigest())
            combined += path.read_text(encoding="utf-8")
        for spec in SPECS.values():
            self.assertIn(f"class {spec[1]}", combined)
        with zipfile.ZipFile(DOCS) as archive:
            names = set(archive.namelist())
            for article_id in SPECS:
                ledger = catalog.load_json(catalog.CONTENT / "research" / "reviews" / f"{article_id}.json")
                for evidence in ledger["evidence"].get("embeddedDocs", []):
                    member = evidence["archivePath"]
                    self.assertIn(member, names)
                    match = re.search(r"SHA-256\s+([0-9a-f]{64})", evidence.get("assessment", ""), re.IGNORECASE)
                    if match:
                        self.assertEqual(match.group(1).lower(), hashlib.sha256(archive.read(member)).hexdigest(), article_id)

    def test_exhaustive_workflow_census_and_widgets(self) -> None:
        expected_counts = Counter({
            "WanSoundImageToVideoExtend": 6, "WanCameraEmbedding": 4, "WanCameraImageToVideo": 4,
            "Wan22FunControlToVideo": 3, "WanDancerVideo": 2, "WanTrackToVideo": 1,
        })
        targets = {spec[1] for spec in SPECS.values()}; counts: Counter[str] = Counter(); widgets = {target: Counter() for target in targets}; totals = [0, 0, 0, 0]
        with zipfile.ZipFile(WORKFLOWS) as archive:
            for member in archive.namelist():
                if "/templates/" not in member or not member.endswith(".json"):
                    continue
                totals[0] += 1; payload = json.loads(archive.read(member).decode("utf-8")); graphs = list(scopes(payload))
                has_root = isinstance(payload, dict) and isinstance(payload.get("nodes"), list)
                totals[1] += int(has_root); totals[2] += len(graphs) - int(has_root)
                for graph in graphs:
                    for node in graph.get("nodes", []):
                        totals[3] += 1
                        if isinstance(node, dict) and node.get("type") in targets:
                            class_type = node["type"]; counts[class_type] += 1; widgets[class_type][repr(node.get("widgets_values"))] += 1
        self.assertEqual([512, 496, 272, 8120], totals)
        self.assertEqual(expected_counts, counts)
        self.assertEqual(Counter({"[77]": 6}), widgets["WanSoundImageToVideoExtend"])
        self.assertEqual(Counter({"[832, 480, 81, 1]": 4}), widgets["WanCameraImageToVideo"])
        self.assertEqual(Counter({"[640, 640, 81, 1]": 2, "[704, 704, 121, 1]": 1}), widgets["Wan22FunControlToVideo"])
        self.assertEqual(Counter({"[480, 544, 149]": 1, "[480, 832, 149]": 1}), widgets["WanDancerVideo"])
        self.assertEqual(Counter({"['[]', 720, 480, 81, 1, 220, 10]": 1}), widgets["WanTrackToVideo"])


if __name__ == "__main__":
    unittest.main()
