import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CONTENT = ROOT / "content"


def load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def custom_manifests():
    return [load(path) for path in sorted((CONTENT / "articles" / "custom").rglob("manifest.json"))]


class CustomPackCatalogTests(unittest.TestCase):
    def test_owned_pack_inventory_has_exact_article_coverage(self):
        manifests = custom_manifests()
        identities = {
            (item["runtimeIdentity"].get("packageId"), item["runtimeIdentity"].get("pythonModule"), item["runtimeIdentity"]["classType"]): item
            for item in manifests if item["runtimeIdentity"]["origin"] == "backend"
        }
        expected = set()
        for inventory_path in sorted((CONTENT / "inventory" / "custom").glob("*.json")):
            inventory = load(inventory_path)
            for node in inventory.get("nodes", []):
                key = (inventory["packageId"], node["pythonModule"], node["classType"])
                expected.add(key)
                self.assertIn(key, identities, f"Missing article for {key}")
                article = identities[key]
                self.assertIn(inventory["sourceCommit"], article["compatibility"]["sourceRevision"])
                self.assertTrue(any(inventory["sourceCommit"] in source["url"] for source in article["sources"]))
        self.assertEqual(set(identities), expected)

    def test_owned_pack_inventory_counts_are_intentional(self):
        timesaver = load(CONTENT / "inventory" / "custom" / "comfyui-timesaver.json")
        cosyvoice = load(CONTENT / "inventory" / "custom" / "comfyui-ts-cosyvoice.json")
        artius = load(CONTENT / "inventory" / "custom" / "comfyui-artius-browser.json")
        self.assertEqual(len(timesaver["nodes"]), 89)
        self.assertEqual(len(cosyvoice["nodes"]), 7)
        self.assertEqual(artius["nodes"], [])
        self.assertEqual(artius["frontendExtensions"][0]["extensionId"], "timesaver-artius-browser")

    def test_every_owned_node_article_is_a_reviewable_draft(self):
        for article in custom_manifests():
            self.assertEqual(article["status"], "draft")
            self.assertEqual(article["editorial"]["state"], "in_review")
            self.assertTrue(article["sources"])
            self.assertTrue(article["editorial"]["reviewedBy"].endswith("pending"))

    def test_september_timesaver_revision_and_experimental_flag(self):
        inventory = load(CONTENT / "inventory/custom/comfyui-timesaver.json")
        self.assertEqual(inventory["version"], "12.11.7")
        self.assertEqual(inventory["sourceCommit"], "c1668b3cfa2161e36bf9b9fa91288b949b4b0b1f")
        nag = next(item for item in custom_manifests() if item["runtimeIdentity"]["classType"] == "TS_NAG")
        self.assertTrue(nag["experimental"])
        body = (CONTENT / "articles/custom/comfyui-timesaver/ts-nag/ru.md").read_text(encoding="utf-8")
        for parameter in ("nag_scale", "nag_alpha", "nag_tau"):
            self.assertIn(parameter, body)

    def test_frontend_only_artius_is_not_misrepresented_as_a_canvas_node(self):
        article = load(CONTENT / "articles" / "custom" / "comfyui-artius-browser" / "artius-browser" / "manifest.json")
        self.assertEqual(article["kind"], "concept")
        self.assertEqual(article["runtimeIdentity"]["origin"], "concept")
        body = (CONTENT / "articles" / "custom" / "comfyui-artius-browser" / "artius-browser" / "ru.md").read_text(encoding="utf-8")
        self.assertIn("Это не набор нод", body)
        self.assertIn("get_node_list()", body)
