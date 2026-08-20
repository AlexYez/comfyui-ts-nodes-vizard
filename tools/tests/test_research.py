from __future__ import annotations

import json
import tempfile
import unittest
import zipfile
from pathlib import Path

from tools import research
from tools import catalog


def write_wheel(path: Path, members: dict[str, str]) -> None:
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, value in members.items():
            archive.writestr(name, value.encode("utf-8"))


class ResearchReportTests(unittest.TestCase):
    def test_checked_in_full_report_matches_both_pinned_inventories(self) -> None:
        report_path = catalog.CONTENT / "research" / "comfyui-0.32.0.evidence.json"
        report = json.loads(report_path.read_text(encoding="utf-8"))
        backend = catalog.object_info_nodes(
            catalog.load_json(catalog.CONTENT / "runtime" / "comfyui-0.32.0.object-info.json")
        )
        frontend = catalog.parse_frontend_inventory(
            catalog.load_json(
                catalog.CONTENT / "runtime" / "comfyui-frontend-1.48.7.frontend-inventory.json"
            )
        )["nodes"]
        backend_in_report = {
            node["classType"] for node in report["nodes"] if node["origin"] == "backend"
        }
        frontend_in_report = {
            node["classType"] for node in report["nodes"] if node["origin"] == "frontend"
        }
        self.assertEqual(set(backend), backend_in_report)
        self.assertEqual(set(frontend), frontend_in_report)
        self.assertEqual(840, report["summary"]["backendNodes"])
        self.assertEqual(4, report["summary"]["frontendNodes"])
        self.assertEqual(496, report["summary"]["officialWorkflows"])
        self.assertEqual(844, len(report["nodes"]))

    def test_report_joins_runtime_docs_source_and_real_workflow_neighbors(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            docs_wheel = root / "comfyui_embedded_docs-0.5.9.whl"
            workflow_wheel = root / "comfyui_workflow_templates_json-0.1.42.whl"
            source_root = root / "ComfyUI"
            source_root.mkdir()
            (source_root / "nodes.py").write_text("class Example: pass\n", encoding="utf-8")

            write_wheel(
                docs_wheel,
                {
                    "comfyui_embedded_docs-0.5.9.dist-info/METADATA": "Name: comfyui-embedded-docs\nVersion: 0.5.9\n",
                    "comfyui_embedded_docs/docs/Example/en.md": "# Example\nEnglish facts.\n",
                    "comfyui_embedded_docs/docs/Example/ru.md": "# Example\nРусский черновик.\n",
                },
            )
            workflow = {
                "nodes": [
                    {"id": 1, "type": "Producer"},
                    {"id": 2, "type": "Example"},
                    {"id": 3, "type": "Consumer"},
                ],
                "links": [
                    [1, 1, 0, 2, 0, "IMAGE"],
                    [2, 2, 0, 3, 0, "IMAGE"],
                ],
            }
            write_wheel(
                workflow_wheel,
                {
                    "comfyui_workflow_templates_json-0.1.42.dist-info/METADATA": "Name: comfyui-workflow-templates-json\nVersion: 0.1.42\n",
                    "comfyui_workflow_templates_json/templates/real_case.json": json.dumps(workflow),
                },
            )
            inventory = {
                "Example": {
                    "input": {"required": {"image": ["IMAGE", {}]}},
                    "output": ["IMAGE"],
                    "output_name": ["IMAGE"],
                    "python_module": "nodes",
                    "display_name": "Example node",
                    "description": "Transforms an image.",
                    "category": "image/test",
                    "api_node": False,
                    "deprecated": False,
                    "experimental": False,
                    "dev_only": False,
                }
            }

            report = research.build_report(
                inventory,
                docs_wheel,
                workflow_wheel,
                source_root=source_root,
                comfyui_version="0.32.0",
                frontend_version="1.48.7",
            )

            self.assertEqual(
                {
                    "comfyui": "0.32.0",
                    "frontend": "1.48.7",
                    "embeddedDocs": "0.5.9",
                    "workflowTemplatesJson": "0.1.42",
                },
                report["baseline"],
            )
            self.assertEqual(1, report["summary"]["backendNodes"])
            self.assertEqual(1, report["summary"]["nodesWithRussianDocs"])
            self.assertEqual(1, report["summary"]["nodesWithOfficialWorkflow"])
            dossier = report["nodes"][0]
            self.assertEqual("nodes.py", dossier["sourcePath"])
            self.assertEqual("pending", dossier["researchState"])
            self.assertEqual([{"classType": "Producer", "links": 1}], dossier["workflowUsage"][0]["upstream"])
            self.assertEqual([{"classType": "Consumer", "links": 1}], dossier["workflowUsage"][0]["downstream"])
            self.assertRegex(dossier["embeddedDocs"]["ru"]["sha256"], r"^sha256:[a-f0-9]{64}$")

            exact_docs = research._read_node_docs(docs_wheel, "Example")
            self.assertEqual("# Example\nРусский черновик.\n", exact_docs["ru"]["text"])
            cases = research._workflow_cases(workflow_wheel, "Example", 1)
            self.assertEqual("real_case", cases[0]["workflowId"])
            self.assertEqual({"Producer", "Consumer"}, {node["type"] for node in cases[0]["neighborNodes"]})
            source = research._source_evidence(inventory["Example"], source_root, "Example")
            self.assertEqual("nodes.py", source["path"])
            self.assertEqual([1], source["matches"])

    def test_corrupt_workflow_is_rejected_instead_of_silently_skipped(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            docs_wheel = root / "docs.whl"
            workflow_wheel = root / "workflows.whl"
            write_wheel(
                docs_wheel,
                {
                    "comfyui_embedded_docs-0.5.9.dist-info/METADATA": "Name: x\n",
                },
            )
            write_wheel(
                workflow_wheel,
                {
                    "comfyui_workflow_templates_json-0.1.42.dist-info/METADATA": "Name: x\n",
                    "comfyui_workflow_templates_json/templates/broken.json": "{not-json",
                },
            )
            with self.assertRaises(research.ResearchError):
                research.build_report(
                    {},
                    docs_wheel,
                    workflow_wheel,
                    comfyui_version="0.32.0",
                    frontend_version="1.48.7",
                )


if __name__ == "__main__":
    unittest.main()
