"""Current catalog and isolated pinned-source probes, without model dependencies."""
import ast
import hashlib
from pathlib import Path
import sys
from types import SimpleNamespace as NS
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import catalog as c
from november_content import CORE, CUSTOM, DELTAS, CORE_DELTAS
from build_september_articles import schema_table


class NovemberCatalogTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.report = c.load_json(c.CONTENT / "research/november-2026-update.json")
        cls.raw = c.load_json(c.CONTENT / "runtime/comfyui-0.43.0.object-info.json")
        cls.runtime = c.object_info_nodes(cls.raw)
        _, articles, _, _ = c.load_source_catalog()
        cls.articles = {m["articleId"]: (p, m) for p, m in articles}
        cls.by_node = {m["runtimeIdentity"]["classType"]: (p, m) for p, m in articles}

    def test_exact_current_coverage_and_module_relocation(self):
        local = {k: v for k, v in c.local_generation_nodes(self.runtime).items() if not v.get("dev_only")}
        self.assertEqual(682, len(local))
        self.assertEqual(793, len(self.articles))
        for key, definition in local.items():
            self.assertEqual(definition["python_module"], self.by_node[key][1]["runtimeIdentity"]["pythonModule"])
        self.assertEqual([{"nodeId": "CreateCameraInfo", "oldModule": "comfy_extras.nodes_gaussian_splat", "newModule": "comfy_extras.nodes_camera"}], self.report["moduleRelocations"])
        self.assertEqual("comfy_extras.nodes_camera", self.by_node["CreateCameraInfo"][1]["runtimeIdentity"]["pythonModule"])

    def test_all_22_new_nodes_have_authored_guides(self):
        old = c.object_info_nodes(c.load_json(c.CONTENT / "runtime/comfyui-0.38.0.object-info.json"))
        local_old = c.local_generation_nodes(old)
        local_new = c.local_generation_nodes(self.runtime)
        added = local_new.keys() - local_old.keys()
        self.assertEqual(16, len(added))
        self.assertEqual(set(self.report["newCoreNodes"]), added)
        self.assertTrue(added.issubset(CORE))
        new_pack = {k for k, v in self.report["timesaverNodes"].items() if v["new"]}
        self.assertEqual({"TS_EditAlign", "TS_ModelResize", "TS_VAEFix", "TS_H3Regenerate", "TS_H3RegenerateModel", "TS_H3FastVAEDecode"}, new_pack)
        self.assertTrue(new_pack.issubset(CUSTOM))
        for key in added | new_pack:
            path, article = self.by_node[key]
            body = (path.parent / article["body"]).read_text(encoding="utf-8")
            self.assertIn((CORE[key] if key in CORE else CUSTOM[key])[1].strip(), body)
            self.assertIn("## Пример", body)
            self.assertFalse(key in self.runtime and self.runtime[key].get("api_node"))

    def test_capture_hashes_and_exact_frontend_inventory(self):
        capture = c.load_json(c.CONTENT / "runtime/comfyui-0.43.0.capture.json")
        self.assertEqual("426f5eea52a7ece1dd599fff4cb6cd1f352ddd24", capture["sourceCommit"])
        for name, spec in capture["files"].items():
            data = (c.CONTENT / "runtime" / name).read_bytes()
            self.assertEqual(spec, {"sha256": hashlib.sha256(data).hexdigest(), "size": len(data)})
        front = c.parse_frontend_inventory(c.load_json(c.CONTENT / "runtime/comfyui-frontend-1.57.4.frontend-inventory.json"))
        self.assertEqual("1.57.4", front["frontendVersion"])
        self.assertEqual({"Reroute", "PrimitiveNode", "Note", "MarkdownNote"}, set(front["nodes"]))

    def test_current_tables_fingerprints_and_non_promotional_links(self):
        compiled, _ = c.compile_catalog()
        by_id = {entry["manifest"]["articleId"]: entry for entry in compiled["articles"]}
        for key, (_, prose, _) in CORE.items():
            path, article = self.by_node[key]
            self.assertEqual(c.schema_fingerprint(key, self.runtime[key]), article["editorial"]["schemaHash"])
            body = by_id[article["articleId"]]["body"]
            self.assertIn(prose.strip(), body)
            self.assertIn(schema_table(self.runtime[key]).replace("Снимок ComfyUI 0.37.0", "Снимок ComfyUI 0.43.0"), body)
        for key in CORE.keys() | CUSTOM.keys():
            body = by_id[self.by_node[key][1]["articleId"]]["body"]
            for link in ("https://neurosaver.ru/", "https://timesavervfx.com/comfyui/", "https://timesavervfx.com/comfyui-launcher/"):
                self.assertIn(link, body)
            self.assertEqual(1, body.count("## Связанные материалы"))
        lora_table = schema_table(self.runtime["LoadLoraModel"])
        for field in ("lora_name", "strength", "enabled"):
            self.assertIn("loras → " + field, lora_table)

    def test_pack_deltas_are_not_claimed_as_full_read_or_model_execution(self):
        self.assertEqual(88, len(self.report["timesaverNodes"]))
        for key, change in self.report["timesaverNodes"].items():
            if change["sourceChanged"] or change["docsChanged"]:
                self.assertTrue(change["fullRewrite"] or change["targetedUpdate"], key)
        for key in CORE.keys() | CUSTOM.keys() | DELTAS.keys():
            path, article = self.by_node[key]
            ledger = c.load_json(c.CONTENT / "research/reviews" / (article["articleId"] + ".json"))
            self.assertFalse(ledger["checks"]["exampleExecuted"])
            self.assertFalse(ledger["checks"]["exampleSchemaValidated"])
            self.assertEqual("in_review", article["editorial"]["state"])
            self.assertEqual("draft", article["status"])
            self.assertEqual(key not in DELTAS, ledger["checks"]["implementationRead"])
            if key in DELTAS:
                body = (path.parent / article["body"]).read_text(encoding="utf-8")
                self.assertEqual(1, body.count("<!-- november-update:start -->"))
                self.assertIn(DELTAS[key], body)

    def test_prior_debt_is_visible_and_changelog_is_current(self):
        before = c.load_json(c.CONTENT / "runtime/comfyui-0.38.0.inventory-report.json")["coverage"]
        now = c.load_json(c.CONTENT / "runtime/comfyui-0.43.0.inventory-report.json")["coverage"]
        self.assertEqual([], now["missingArticles"])
        self.assertEqual({x["articleId"] for x in before["staleArticles"]}, {x["articleId"] for x in now["staleArticles"]})
        update = c.load_json(c.CONTENT / "update-manifest.json")
        self.assertEqual("0.3.3", update["catalogVersion"])
        self.assertEqual(22, len(update["changes"]["added"]))
        self.assertEqual(31 + len(CORE_DELTAS), len(update["changes"]["updated"]))
        self.assertIsNone(update["signature"])
        self.assertFalse(self.report["humanApproved"])

    def test_targeted_core_changes_keep_historical_review_dates(self):
        for key, note in CORE_DELTAS.items():
            path, article = self.by_node[key]
            body = (path.parent / article["body"]).read_text(encoding="utf-8")
            self.assertEqual(1, body.count("<!-- november-core:start -->"))
            self.assertIn(note, body)
            self.assertLess(article["editorial"]["factsReviewedAt"], "2026-11-02")
            self.assertFalse(self.report["coreTargetedUpdates"][key]["fullReview"])

    def test_editorial_update_is_idempotent_and_preserves_old_body(self):
        from update_november_catalog import prepend_update
        original = "# Title\n\nOriginal `identifier` and https://example.org/a.\n"
        for marker in ("november-core", "november-update"):
            once = prepend_update(original, marker, "Current facts")
            repeated = once
            for _ in range(10):
                repeated = prepend_update(repeated, marker, "Current facts")
            self.assertEqual(once, repeated)
            self.assertTrue(repeated.endswith(original.split("\n", 1)[1]))
            self.assertEqual(1, repeated.count(f"<!-- {marker}:start -->"))


class IsolatedSourceProbes(unittest.TestCase):
    """Execute only the saved function body with tiny data and inert dependencies."""
    def function(self, key, **namespace):
        evidence = c.load_json(c.CONTENT / "research/november-2026-update.json")["sourceProbes"][key]
        code = evidence["code"]
        self.assertEqual(evidence["codeSha256"], hashlib.sha256(code.encode()).hexdigest())
        tree = ast.parse(code)
        self.assertEqual(1, len(tree.body))
        self.assertIsInstance(tree.body[0], ast.FunctionDef)
        self.assertFalse(any(isinstance(n, (ast.Import, ast.ImportFrom)) for n in ast.walk(tree)))
        ns = {"IO": NS(NodeOutput=lambda *args: args), "io": NS(NodeOutput=lambda *args: args), **namespace}
        exec(compile("from __future__ import annotations\n" + code, evidence["sourceUrl"], "exec"), ns)
        return ns[tree.body[0].name]

    def test_branch_requests_only_selected_input_and_rejects_missing(self):
        lazy = self.function("branch_lazy")
        self.assertEqual(["autogrow.branch1"], lazy(None, "edited", ["original", "edited"], {"branch0": None, "branch1": None}))
        with self.assertRaises(ValueError):
            lazy(None, "edited", ["original", "edited"], {"branch0": 1})
        with self.assertRaises(ValueError):
            lazy(None, "missing", ["original"], {"branch0": 1})
        execute = self.function("branch_execute")
        self.assertEqual((42,), execute(None, "edited", ["original", "edited"], {"branch0": 0, "branch1": 42}))

    def test_sizes_are_latent_units_and_nested_streams_are_distinct(self):
        class Shape:
            def __init__(self, *shape):
                self.shape, self.ndim, self.is_nested = shape, len(shape), False
        video = Shape(1, 16, 21, 60, 104)
        audio = Shape(1, 32, 2, 400)
        combined = NS(is_nested=True, unbind=lambda: (video, audio))
        node = NS(hidden=NS(unique_id=None))
        self.assertEqual((104, 60, 21, 1), self.function("latent_size")(node, {"samples": combined}))
        self.assertEqual((400, 2, 1), self.function("audio_size")(node, {"samples": combined}))
        self.assertEqual((64, 48, 1, 2), self.function("latent_size")(node, {"samples": Shape(2, 4, 48, 64)}))

    def test_odd_padding_is_put_on_right_or_bottom(self):
        split = self.function("split_padding")
        self.assertEqual((1, 2), split(3))
        self.assertEqual((12, 12), split(24))

    def test_lora_rows_skip_without_file_io_and_keep_model_clip_separate(self):
        calls = []
        def load(name):
            calls.append(("file", name))
            return name, {"format": "test"}
        def apply(model, clip, data, sm, sc, **kwargs):
            calls.append(("patch", model, clip, data, sm, sc))
            return (f"{model}:{data}" if model else None, f"{clip}:{data}" if clip else None)
        dependencies = {"_load_lora_file": load, "comfy": NS(sd=NS(load_lora_for_models=apply))}
        rows = [{"lora_name": "skip", "strength": 1, "enabled": False},
                {"lora_name": "zero", "strength": 0, "enabled": True},
                {"lora_name": "a", "strength": .5, "enabled": True},
                {"lora_name": "b", "strength": -.25, "enabled": True}]
        self.assertEqual(("model:a:b",), self.function("lora_model", **dependencies)(None, "model", rows))
        self.assertEqual([("file", "a"), ("file", "b")], [x for x in calls if x[0] == "file"])
        self.assertTrue(all(x[2] is None and x[-1] == 0 for x in calls if x[0] == "patch"))
        calls.clear()
        self.assertEqual(("clip:a:b",), self.function("lora_clip", **dependencies)(None, "clip", rows))
        self.assertTrue(all(x[1] is None and x[-2] == 0 for x in calls if x[0] == "patch"))

    def test_caption_filenames_preserve_parentheses_and_reject_unsafe_names(self):
        safe = self.function("batch_name", LOG_PREFIX="test")
        self.assertEqual("photo (1)", safe("photo (1)", 0, for_file=True))
        self.assertEqual("item_00002", safe("", 2, for_file=True))
        for name in ("../escape", "a/b", "a\\b", "CON", "COM1.txt", "trailing.", "trailing "):
            with self.subTest(name=name), self.assertRaises(ValueError):
                safe(name, 0, for_file=True)


if __name__ == "__main__":
    unittest.main()
