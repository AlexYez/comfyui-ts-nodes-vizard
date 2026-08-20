from __future__ import annotations

import hashlib
import json
import re
import subprocess
import sys
import unittest
import zipfile
from pathlib import Path
from typing import Any, Iterator

from tools import catalog


SPECS = {
    "core.context-windows-manual": ("context-windows-manual", "ContextWindowsManual", "sha256:d491c9f6f3fb62174063563daf364176c845b952d8c2950933d9411d164e58cd", "recipe.wan-animate2-manual-context-window"),
    "core.wan-context-windows-manual": ("wan-context-windows-manual", "WanContextWindowsManual", "sha256:f914298122a9ced8409a1bcd95a934dc659f3396c393905a6d2a2db8bc851d23", "recipe.wan-context-window-81-frames"),
    "core.ltxv-context-windows": ("ltxv-context-windows", "LTXVContextWindows", "sha256:3ffb9e2fbfe2ddf48ccb2bd6971bb89ca001b7e6ccb85b356657c1c4641a0afc", "recipe.ltxv-context-window-145-frames"),
}
RECIPES = {
    "recipe.wan-animate2-manual-context-window": "wan-animate2-manual-context-window",
    "recipe.wan-context-window-81-frames": "wan-context-window-81-frames",
    "recipe.ltxv-context-window-145-frames": "ltxv-context-window-145-frames",
}
DOC_HASHES = {
    "comfyui_embedded_docs/docs/ContextWindowsManual/en.md": "9869d04e9412f23947330a9f767adfcdb2aa3bc8dede255122d5e7e5968f292d",
    "comfyui_embedded_docs/docs/ContextWindowsManual/ru.md": "9a92f7a89e4b4fd31f337be1b60426bf789f23c1a7b6689a5c227850495633e1",
    "comfyui_embedded_docs/docs/WanContextWindowsManual/en.md": "65e89b5e5303de4a71776f6cee55edbb3e7caf4e9765d56a87194bd83643a2cd",
    "comfyui_embedded_docs/docs/WanContextWindowsManual/ru.md": "1eb8ba2c97162cb000632bae031f2ad1edf5acdcebaf6b7a763c6b6ae5b651b0",
    "comfyui_embedded_docs/docs/LTXVContextWindows/en.md": "886743edc3f5efe750118eb851d3c08184aa6474bd31f6bad7fe557dd98a5f24",
    "comfyui_embedded_docs/docs/LTXVContextWindows/ru.md": "0cc73c440c5c93393ab562c4601026c190b6a91c5c36c9ae2d884ed9a5647b22",
}


def graphs(payload: Any) -> Iterator[dict[str, Any]]:
    if isinstance(payload, list):
        for item in payload:
            yield from graphs(item)
        return
    if not isinstance(payload, dict):
        return
    if isinstance(payload.get("nodes"), list):
        yield payload
    defs = payload.get("definitions")
    for sub in defs.get("subgraphs", []) if isinstance(defs, dict) else []:
        if isinstance(sub, dict):
            yield from graphs(sub)


class ContextWindowsContentTests(unittest.TestCase):
    def test_schema_status_headings_and_relations(self) -> None:
        article_schema = catalog.load_json(catalog.CONTENT / "schemas/article.schema.v1.json")
        recipe_schema = catalog.load_json(catalog.CONTENT / "schemas/recipe.schema.v1.json")
        fragment_schema = catalog.load_json(catalog.CONTENT / "schemas/recipe-fragment.schema.v1.json")
        research_schema = catalog.load_json(catalog.CONTENT / "schemas/article-research.schema.v1.json")
        all_ids = {catalog.load_json(p)["articleId"] for p in (catalog.CONTENT / "articles").rglob("manifest.json")}
        errors: list[str] = []
        for article_id, (directory, _, _, recipe_id) in SPECS.items():
            path = catalog.CONTENT / "articles/core" / directory / "manifest.json"
            item = catalog.load_json(path)
            self.assertEqual([], catalog.json_schema_errors(item, article_schema))
            catalog.validate_article(path, item, errors)
            self.assertEqual("draft", item["status"]); self.assertEqual("in_review", item["editorial"]["state"])
            self.assertEqual(recipe_id, item["assets"][0]["id"])
            targets = item["relations"]["related"] + item["relations"]["alternatives"]
            self.assertTrue(set(targets).issubset(all_ids))
            body = (path.parent / "ru.md").read_text(encoding="utf-8")
            self.assertEqual(10, len(re.findall(r"^## ", body, re.MULTILINE)))
            research = catalog.load_json(catalog.CONTENT / "research/reviews" / f"{article_id}.json")
            self.assertEqual([], catalog.json_schema_errors(research, research_schema))
            self.assertEqual("fact_checked", research["state"]); self.assertFalse(research["checks"]["exampleExecuted"])
        for recipe_id, directory in RECIPES.items():
            path = catalog.CONTENT / "recipes" / directory / "recipe.json"
            item = catalog.load_json(path)
            self.assertEqual([], catalog.json_schema_errors(item, recipe_schema)); self.assertNotIn("workflow", item)
            catalog.validate_recipe(path, item, all_ids, errors)
            fragment = catalog.load_json(path.parent / "fragment.json")
            self.assertEqual([], catalog.json_schema_errors(fragment, fragment_schema))
        self.assertEqual([], errors)

    def test_runtime_identity_fingerprints_and_fragment_settings(self) -> None:
        nodes = catalog.object_info_nodes(catalog.load_json(catalog.CONTENT / "runtime/comfyui-0.32.0.object-info.json"))
        for article_id, (directory, class_type, fingerprint, _) in SPECS.items():
            runtime = nodes[class_type]; article = catalog.load_json(catalog.CONTENT / "articles/core" / directory / "manifest.json")
            self.assertEqual("comfy_extras.nodes_context_windows", runtime["python_module"])
            self.assertTrue(runtime["experimental"]); self.assertFalse(runtime["deprecated"])
            self.assertEqual(fingerprint, catalog.schema_fingerprint(class_type, runtime)); self.assertEqual(fingerprint, article["editorial"]["schemaHash"])
        base = catalog.load_json(catalog.CONTENT / "recipes/wan-animate2-manual-context-window/fragment.json")["nodes"][0]["settings"]
        self.assertEqual({"context_length": 21, "context_overlap": 8, "context_schedule": "standard_static", "context_stride": 1, "closed_loop": False, "fuse_method": "pyramid", "dim": 2, "freenoise": True, "cond_retain_index_list": "0", "split_conds_to_windows": False, "latent_retain_index_list": "", "causal_window_fix": True}, base)

    def test_pinned_source_docs_and_probe_fail_closed(self) -> None:
        source = catalog.ROOT / ".comfyui-source-0.32.0"
        docs = catalog.ROOT / ".upstream-cache/comfyui_embedded_docs-0.5.9-py3-none-any.whl"
        self.assertTrue(source.is_dir(), "pinned source must be bootstrapped")
        self.assertTrue(docs.is_file(), "pinned docs must be bootstrapped")
        self.assertEqual("af16cc2d162ba57b29c8bdd358d17fb80a6f69e50316289715e1510ea337e08b", hashlib.sha256((source / "comfy_extras/nodes_context_windows.py").read_bytes()).hexdigest())
        self.assertEqual("8259e2b9adec639962e919a9f2d29ea7f6b45e38d14bcc1ff885a8278975e4d1", hashlib.sha256((source / "comfy/context_windows.py").read_bytes()).hexdigest())
        with zipfile.ZipFile(docs) as archive:
            for member, digest in DOC_HASHES.items(): self.assertEqual(digest, hashlib.sha256(archive.read(member)).hexdigest())
        result = subprocess.run([sys.executable, str(Path(__file__).with_name("context_windows_synthetic_probe.py"))], cwd=catalog.ROOT, text=True, capture_output=True, check=True)
        report = json.loads(result.stdout); self.assertEqual([21, 7], report["conversions"]["wan_81_30"]); self.assertTrue(report["zero_step_rejected"])

    def test_full_official_workflow_census_and_topology(self) -> None:
        wheel = catalog.ROOT / ".upstream-cache/comfyui_workflow_templates_json-0.1.42-py3-none-any.whl"
        self.assertTrue(wheel.is_file(), "pinned workflow wheel must be bootstrapped")
        self.assertEqual("242982d65e1c51ca03d892bc1009bb6843f457e7dfc0c20afe6438770b7a14a3", hashlib.sha256(wheel.read_bytes()).hexdigest())
        counts = {k: 0 for k in ("ContextWindowsManual", "WanContextWindowsManual", "LTXVContextWindows")}; widgets: list[list[Any]] = []
        with zipfile.ZipFile(wheel) as archive:
            json_names = [n for n in archive.namelist() if n.endswith(".json")]
            self.assertEqual(512, len(json_names))
            graph_count = 0
            for name in json_names:
                payload = json.loads(archive.read(name))
                for graph in graphs(payload):
                    graph_count += 1
                    for node in graph.get("nodes", []):
                        t = node.get("type")
                        if t in counts:
                            counts[t] += 1; widgets.append(node.get("widgets_values", []))
            self.assertEqual(768, graph_count)
        self.assertEqual({"ContextWindowsManual": 2, "WanContextWindowsManual": 0, "LTXVContextWindows": 0}, counts)
        self.assertEqual([[21, 8, "standard_static", 1, False, "pyramid", 2, True, "0", False, "", True]] * 2, widgets)

    def test_natural_russian_and_no_false_approval(self) -> None:
        for directory, *_ in SPECS.values():
            body = (catalog.CONTENT / "articles/core" / directory / "ru.md").read_text(encoding="utf-8")
            self.assertNotRegex(body, re.compile(r"official case|source-derived|root workflow|human approved", re.I))
            self.assertNotIn("\ufffd", body)


if __name__ == "__main__":
    unittest.main()
