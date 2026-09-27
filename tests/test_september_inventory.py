import hashlib
import json
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
RUNTIME = ROOT / "content/runtime"


class SeptemberInventoryTests(unittest.TestCase):
    def test_captured_payloads_match_provenance(self):
        provenance = json.loads((RUNTIME / "comfyui-0.37.0.capture.json").read_text())
        for name, expected in provenance["files"].items():
            data = (RUNTIME / name).read_bytes()
            self.assertEqual(len(data), expected["size"])
            self.assertEqual(hashlib.sha256(data).hexdigest(), expected["sha256"])

    def test_new_nodes_remain_explicit_editorial_debt(self):
        report = json.loads((RUNTIME / "comfyui-0.37.0.inventory-report.json").read_text())
        coverage = report["coverage"]
        self.assertEqual(coverage["runtimeNodeCount"], 665)
        self.assertEqual(len(coverage["missingArticles"]), 64)
        self.assertEqual(len(coverage["staleArticles"]), 31)
        self.assertEqual(coverage["articlesMissingRuntimeNode"], [])
        self.assertIn("StartLoop", coverage["missingArticles"])
        self.assertIn("MiniMaxH3AddGuide", coverage["missingArticles"])

    def test_latest_frontend_types_match_the_exact_registry(self):
        inventory = json.loads((RUNTIME / "comfyui-frontend-1.52.7.frontend-inventory.json").read_text())
        self.assertEqual(inventory["frontendVersion"], "1.52.7")
        self.assertEqual({node["classType"] for node in inventory["nodes"]}, {"Note", "MarkdownNote", "PrimitiveNode", "Reroute"})
