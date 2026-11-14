import sys
import unittest
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import catalog as c
from nov14_content import CORE


class November14Tests(unittest.TestCase):
    def test_new_inventory_has_13_new_local_nodes_and_full_coverage(self):
        new = c.local_generation_nodes(c.object_info_nodes(c.load_json(c.CONTENT / "runtime/comfyui-0.45.0.object-info.json")))
        old = c.local_generation_nodes(c.object_info_nodes(c.load_json(c.CONTENT / "runtime/comfyui-0.43.0.object-info.json")))
        self.assertEqual(set(CORE), new.keys() - old.keys())
        self.assertEqual(695, len(new))
        rows = {m["runtimeIdentity"]["classType"]: (p, m) for p in (c.CONTENT / "articles/core").glob("*/manifest.json") if (m := c.load_json(p))}
        for key, definition in new.items():
            self.assertEqual(definition["python_module"], rows[key][1]["runtimeIdentity"]["pythonModule"])
        for key, (_, prose) in CORE.items():
            path, m = rows[key]
            self.assertIn(prose.strip(), (path.parent / "ru.md").read_text(encoding="utf-8"))
            self.assertEqual(c.schema_fingerprint(key, new[key]), m["editorial"]["schemaHash"])
            ledger = c.load_json(c.CONTENT / "research/reviews" / (m["articleId"] + ".json"))
            self.assertFalse(ledger["checks"]["exampleExecuted"])

    def test_every_article_has_verified_curated_link(self):
        report = c.load_json(c.CONTENT / "research/neurosaver-2026-11-14.json")
        self.assertEqual(806, report["articleCount"])
        self.assertEqual(806, len({r["articleId"] for r in report["articles"]}))
        self.assertTrue(all(r.get("status") == 200 for r in report["links"]))
        compiled, _ = c.compile_catalog()
        for a in compiled["articles"]:
            self.assertEqual(1, a["body"].count("## Связанные материалы"))
            self.assertIn("https://neurosaver.ru/", a["body"])

    def test_specific_models_do_not_use_generic_reading(self):
        reading = c.load_json(c.CONTENT / "related-reading.json")
        manifests = [c.load_json(p) for p in (c.CONTENT / "articles").glob("**/manifest.json")]
        by_node = {m["runtimeIdentity"]["classType"]: m for m in manifests}
        for key, part in (("MiniMaxH3ContextWindows", "minimax-h3"), ("MOSSImageLayoutPrompt", "moss-image"), ("LTXVConditioning", "ltx-video")):
            self.assertIn(part, c.select_related_reading(by_node[key], reading)["url"])
        self.assertNotIn("canny", c.select_related_reading(by_node["ResizeImagesByShorterEdge"], reading)["url"])


if __name__ == "__main__":
    unittest.main()
