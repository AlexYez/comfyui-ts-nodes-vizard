import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import catalog
from editorial_catalog_check import normalize_prose
from october_content import CORE


class OctoberCatalogTests(unittest.TestCase):
    def test_full_current_local_inventory_is_covered_by_exact_identity(self):
        _, articles, _, _ = catalog.load_source_catalog()
        identities = {(m["runtimeIdentity"].get("pythonModule"), m["runtimeIdentity"]["classType"])
                      for _, m in articles if m["runtimeIdentity"].get("packageId") == "comfy-core"}
        inventory = {k: v for k, v in catalog.local_generation_nodes(catalog.load_json(ROOT / "content/runtime/comfyui-0.38.0.object-info.json")).items() if not v.get("dev_only")}
        self.assertEqual(len(inventory), 666)
        for node_id, definition in inventory.items():
            self.assertIn((definition["python_module"], node_id), identities)

    def test_current_fingerprints_survive_historical_default_compilation(self):
        compiled, _ = catalog.compile_catalog()
        inventory = catalog.load_json(ROOT / "content/runtime/comfyui-0.38.0.object-info.json")
        by_node = {m["manifest"]["node"]["nodeId"]: m for m in compiled["articles"]}
        for node_id in CORE:
            self.assertEqual(by_node[node_id]["manifest"]["compatibility"]["schemaFingerprint"],
                             catalog.schema_fingerprint(node_id, inventory[node_id]))
            self.assertEqual(by_node[node_id]["manifest"]["editorialState"], "in_review")

    def test_current_articles_include_authored_prose_and_exact_current_tables(self):
        from build_september_articles import schema_table
        _, articles, _, _ = catalog.load_source_catalog()
        inventory = catalog.load_json(ROOT / "content/runtime/comfyui-0.38.0.object-info.json")
        for path, article in articles:
            node_id = article["runtimeIdentity"]["classType"]
            if node_id not in CORE:
                continue
            body = (path.parent / article["body"]).read_text(encoding="utf-8")
            self.assertIn(CORE[node_id][1].strip(), body)
            self.assertIn(schema_table(inventory[node_id]).replace("Снимок ComfyUI 0.37.0", "Снимок ComfyUI 0.38.0"), body)
            self.assertTrue(any("6b747c0428c343e1417219641db93a4fb7cb69ae" in s["url"] for s in article["sources"]))

    def test_removed_studio_drafts_are_archived_without_fake_approval(self):
        _, articles, _, _ = catalog.load_source_catalog()
        removed = [m for _, m in articles if m["status"] == "removed"]
        self.assertEqual(len(removed), 11)
        for article in removed:
            self.assertEqual(article["editorial"]["state"], "in_review")
            self.assertIn("12.11.7", article["compatibility"]["sourceRevision"])
        self.assertEqual(catalog.validate_catalog(), [])

    def test_related_reading_does_not_confuse_mesh_merge_with_weight_merge(self):
        reading = catalog.load_json(ROOT / "content/related-reading.json")
        _, articles, _, _ = catalog.load_source_catalog()
        by_id = {m["articleId"]: m for _, m in articles}
        for article_id in ("core.merge-meshes", "core.merge-image-lists", "core.merge-text-lists"):
            self.assertNotIn("model-merge", catalog.select_related_reading(by_id[article_id], reading)["url"])
        self.assertIn("/model-merge/", catalog.select_related_reading(by_id["core.model-merge-sdxl"], reading)["url"])
        self.assertIn("/ksampler-", catalog.select_related_reading(by_id["core.ksampler"], reading)["url"])

    def test_mechanical_edit_preserves_code_identifiers_and_urls(self):
        body = 'Runtime flags; не является output node. `Runtime flags`\n```text\nlist-output\n```\nhttps://example.org/list-output'
        edited = normalize_prose(body)
        self.assertIn("Флаги ноды; не является выходной нодой.", edited)
        self.assertIn("`Runtime flags`", edited)
        self.assertIn("```text\nlist-output\n```", edited)
        self.assertIn("https://example.org/list-output", edited)

    def test_audit_does_not_claim_every_article_was_manually_read(self):
        report = catalog.load_json(ROOT / "content/research/october-2026-editorial-audit.json")
        self.assertEqual(len(report["articles"]), 771)
        self.assertGreater(sum(a["needsFullEditorialRead"] for a in report["articles"]), 0)
        self.assertEqual(len({a["articleId"] for a in report["articles"]}), 771)

    def test_output_node_term_keeps_russian_grammar(self):
        self.assertEqual("Нода помечена как выходная нода", normalize_prose("Нода помечена как output node"))
        self.assertEqual("Нода зарегистрирована как выходная нода", normalize_prose("Нода зарегистрирована как output node"))
        self.assertEqual("Код помечает её как выходную ноду", normalize_prose("Код помечает её output node"))

    def test_timesaver_corrections_have_exact_authored_text_and_honest_evidence(self):
        from october_content import CUSTOM
        _, articles, _, _ = catalog.load_source_catalog()
        for path, article in articles:
            node_id = article["runtimeIdentity"]["classType"]
            if node_id not in CUSTOM:
                continue
            self.assertIn(CUSTOM[node_id].strip(), (path.parent / article["body"]).read_text(encoding="utf-8"))
            review = catalog.load_json(ROOT / "content/research/reviews" / (article["articleId"] + ".json"))
            self.assertEqual(review["baseline"]["sourceCommit"], "819d4e573a266fbc2aafb10554943f1e781c351a")
            self.assertTrue(review["checks"]["implementationRead"])
            self.assertTrue(review["checks"]["factsRecheckedAfterEditing"])
            self.assertFalse(review["checks"]["runtimeCompared"])
            self.assertFalse(review["checks"]["exampleExecuted"])


if __name__ == "__main__":
    unittest.main()
