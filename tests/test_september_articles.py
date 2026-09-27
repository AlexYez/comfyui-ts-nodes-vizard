"""Regression contract for the authored September batch (no model inference)."""
import hashlib
import json
from pathlib import Path
import sys
import unittest
import tempfile
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
from build_september_articles import ARTICLES, COMMIT, input_rows, schema_table, slug, workflow_census
from catalog import compile_catalog, local_generation_nodes, schema_fingerprint


class SeptemberArticlesTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.inventory = json.loads((ROOT / "content/runtime/comfyui-0.37.0.object-info.json").read_text(encoding="utf-8"))
        cls.evidence = json.loads((ROOT / "content/research/september-2026-articles.json").read_text(encoding="utf-8"))
        cls.compiled, cls.search = compile_catalog()

    def test_exactly_the_64_new_runtime_identities(self):
        old = json.loads((ROOT / "content/runtime/comfyui-0.32.0.object-info.json").read_text(encoding="utf-8"))
        new_ids = {k for k, v in local_generation_nodes(self.inventory).items() if not v.get("dev_only")} - set(local_generation_nodes(old))
        self.assertEqual(set(ARTICLES), new_ids)
        self.assertEqual(len(ARTICLES), 64)
        self.assertEqual(set(self.evidence["articles"]), new_ids)

    def test_all_authored_sections_and_exact_schema_are_published(self):
        for node_id, record in ARTICLES.items():
            with self.subTest(node=node_id):
                directory = ROOT / "content/articles/core" / slug(node_id)
                manifest = json.loads((directory / "manifest.json").read_text(encoding="utf-8"))
                body = (directory / "ru.md").read_text(encoding="utf-8")
                for section in record[:5]:
                    self.assertIn(section, body)
                self.assertGreater(len(record[2].split()), 25)
                self.assertGreaterEqual(len(record[3].split()), 25)
                self.assertGreater(len(record[4].split()), 25)
                self.assertIn(schema_table(self.inventory[node_id]), body)
                self.assertEqual(manifest["editorial"]["schemaHash"], schema_fingerprint(node_id, self.inventory[node_id]))
                self.assertEqual(manifest["runtimeIdentity"]["pythonModule"], self.inventory[node_id]["python_module"])
                self.assertEqual(manifest["experimental"], self.inventory[node_id]["experimental"])

    def test_no_fake_approval_or_execution(self):
        for node_id in ARTICLES:
            article_id = "core." + slug(node_id)
            review = json.loads((ROOT / "content/research/reviews" / (article_id + ".json")).read_text(encoding="utf-8"))
            with self.subTest(node=node_id):
                self.assertFalse(review["checks"]["exampleExecuted"])
                self.assertFalse(review["checks"]["exampleSchemaValidated"])
                self.assertNotEqual(review["state"], "human_approved")
                self.assertEqual(review["baseline"]["sourceCommit"], COMMIT)
                self.assertEqual(review["checks"]["officialCasesInspected"], bool(review["evidence"]["workflows"]))
                self.assertTrue(review["knownGaps"])

    def test_pinned_case_provenance(self):
        self.assertEqual(sum(bool(x["workflows"]) for x in self.evidence["articles"].values()), 46)
        self.assertEqual(self.evidence["sourceCommit"], COMMIT)
        raw = (ROOT / "content/runtime/comfyui-0.37.0.object-info.json").read_bytes()
        self.assertEqual(self.evidence["inventorySha256"], hashlib.sha256(raw).hexdigest())
        for node_id, record in self.evidence["articles"].items():
            with self.subTest(node=node_id):
                self.assertIn(COMMIT, record["source"]["url"])
                self.assertRegex(record["source"]["fileSha256"], r"^[a-f0-9]{64}$")
                for case in record["workflows"]:
                    self.assertIn(node_id, case["nodeTypes"])
                    self.assertRegex(case["sha256"], r"^sha256:[a-f0-9]{64}$")

    def test_compiled_catalog_has_articles_not_only_autocards(self):
        articles = self.compiled["articles"]
        self.assertEqual(len(articles), 766)
        by_node = {a["manifest"]["node"]["nodeId"]: a for a in articles if a["manifest"]["node"]["packageId"] == "comfy-core"}
        for node_id in ARTICLES:
            with self.subTest(node=node_id):
                article = by_node[node_id]
                self.assertIn("## Пример подключения", article["body"])
                self.assertIn("neurosaver.ru/", article["body"])
                self.assertIn("timesavervfx.com/comfyui/", article["body"])
                self.assertEqual(article["manifest"]["compatibility"]["schemaFingerprint"], schema_fingerprint(node_id, self.inventory[node_id]))

    def test_dynamic_fields_include_their_branch(self):
        table = "\n".join(input_rows(self.inventory["RotateMesh"]["input"]))
        self.assertIn("mode=euler_xyz → angle_x", table)
        self.assertIn("mode=quaternion → qw", table)
        table = schema_table(self.inventory["BuildPoseFile"])
        self.assertIn("format=bvh → units", table)
        self.assertIn("format=glb → mesh_style=body_mesh → bone_vis=octahedrons", table)

    def test_workflow_census_keeps_subgraph_ids_scoped(self):
        fixture = {"nodes": [{"id": 1, "type": "StartLoop"}, {"id": 2, "type": "EndLoop"}], "links": [[1, 1, 0, 2, 0, "*"]], "definitions": {"subgraphs": [{"name": "music", "nodes": [{"id": 1, "type": "MiniMaxMusic3TextEncode"}, {"id": 2, "type": "EmptyMiniMaxMusic3LatentAudio"}], "links": [{"origin_id": 1, "target_id": 2}]}]}}
        with tempfile.TemporaryDirectory() as directory:
            wheel = Path(directory) / "fixture.zip"
            with zipfile.ZipFile(wheel, "w") as archive:
                archive.writestr("comfyui_workflow_templates_json/templates/fixture.json", json.dumps(fixture))
            _, occurrences = workflow_census(wheel)
        self.assertEqual(occurrences["StartLoop"][0]["downstream"], [{"classType": "EndLoop", "links": 1}])
        self.assertEqual(occurrences["EmptyMiniMaxMusic3LatentAudio"][0]["upstream"], [{"classType": "MiniMaxMusic3TextEncode", "links": 1}])
        self.assertEqual(occurrences["MiniMaxMusic3TextEncode"][0]["graphScope"], "root/definitions/subgraphs/0")

    def test_known_noninterchangeable_semantics_are_documented(self):
        self.assertIn("до начала, а не отсчитывают от конца", ARTICLES["LTXVAddLatentGuide"][2])
        self.assertIn("отсчитывается от конца", ARTICLES["MiniMaxH3AddGuide"][2])
        self.assertIn("не означает условие break", ARTICLES["EndLoop"][4])
        self.assertIn("сбрасывает UV", ARTICLES["FillHoles"][4])
        self.assertIn("downscale_ratio_temporal = 1920", ARTICLES["EmptyYuE2LatentAudio"][2])
        self.assertIn("downscale_ratio_temporal = 512", ARTICLES["EmptyMiniMaxMusic3LatentAudio"][2])


if __name__ == "__main__":
    unittest.main()
