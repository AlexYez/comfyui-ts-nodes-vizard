from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from tools import catalog, frontend_inventory


OFFICIAL_FRONTEND_COMMIT = "6d6af63c00f132cd25dc29307fc56bd2c094fa22"
OFFICIAL_COMFYUI_COMMIT = "c2bcbecd82ec5ae66594340b395c24ef0217b238"
FULL_INVENTORY = (
    catalog.CONTENT
    / "runtime"
    / "comfyui-frontend-1.48.7.frontend-inventory.json"
)
EXPECTED_TYPES = {"MarkdownNote", "Note", "PrimitiveNode", "Reroute"}


def write(root: Path, relative: str, text: str) -> None:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def make_source_fixture(root: Path, classic_types: set[str] = EXPECTED_TYPES) -> None:
    write(root, "package.json", json.dumps({"version": "1.48.7"}))
    keys = "\n".join(f"  {name}: {{}}" for name in sorted(EXPECTED_TYPES))
    write(
        root,
        "src/stores/nodeDefStore.ts",
        "export const SYSTEM_NODE_DEFS: Record<string, ComfyNodeDefV1> = {\n"
        f"{keys}\n"
        "}\n",
    )

    registrations = {
        "src/extensions/core/widgetInputs.ts": {"PrimitiveNode"},
        "src/extensions/core/rerouteNode.ts": {"Reroute"},
        "src/extensions/core/noteNode.ts": {"Note", "MarkdownNote"},
    }
    remaining = set(classic_types)
    for relative, expected_for_file in registrations.items():
        emitted = sorted(expected_for_file & remaining)
        remaining -= set(emitted)
        write(
            root,
            relative,
            "\n".join(
                f"LiteGraph.registerNodeType('{name}', ExampleNode)" for name in emitted
            ),
        )
    if remaining:
        with (root / "src/extensions/core/noteNode.ts").open("a", encoding="utf-8") as stream:
            stream.write("\n".join(
                f"\nLiteGraph.registerNodeType('{name}', ExampleNode)"
                for name in sorted(remaining)
            ))

    write(
        root,
        "src/scripts/app.ts",
        "const nodeDefArray = [...frontendOnlyDefs, ...SYSTEM_NODE_DEFS]\n"
        "nodeDefStore.updateNodeDefs(nodeDefArray)\n",
    )
    write(
        root,
        "src/renderer/extensions/vueNodes/components/LGraphNode.vue",
        "const isRerouteNode = computed(() => nodeData.type === 'Reroute')\n",
    )


class FrontendInventoryTests(unittest.TestCase):
    def test_checked_in_inventory_is_full_versioned_official_snapshot(self) -> None:
        raw = catalog.load_json(FULL_INVENTORY)
        parsed = catalog.parse_frontend_inventory(raw, FULL_INVENTORY.name)

        self.assertEqual("1.48.7", parsed["frontendVersion"])
        self.assertEqual(EXPECTED_TYPES, set(parsed["nodes"]))
        self.assertEqual(4, len(raw["nodes"]))
        self.assertTrue(all(node["packageId"] == "comfy-core" for node in raw["nodes"]))
        self.assertTrue(all(node["dev_only"] is False for node in raw["nodes"]))
        self.assertIn(OFFICIAL_FRONTEND_COMMIT, parsed["source"])
        self.assertIn(OFFICIAL_COMFYUI_COMMIT, parsed["source"])
        self.assertNotIn(".sample.json", FULL_INVENTORY.name)

    def test_extractor_requires_same_fixed_types_on_both_graph_surfaces(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            make_source_fixture(root)
            result = frontend_inventory.build_inventory(
                root,
                "1.48.7",
                OFFICIAL_FRONTEND_COMMIT,
                "0.32.0",
                OFFICIAL_COMFYUI_COMMIT,
                "2026-08-13T18:03:35Z",
            )

        self.assertEqual(
            ["MarkdownNote", "Note", "PrimitiveNode", "Reroute"],
            [node["classType"] for node in result["nodes"]],
        )

    def test_extractor_fails_if_classic_and_system_definitions_diverge(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            make_source_fixture(root, EXPECTED_TYPES - {"MarkdownNote"})
            with self.assertRaisesRegex(
                frontend_inventory.InventoryError,
                "fixed type sets differ",
            ):
                frontend_inventory.build_inventory(
                    root,
                    "1.48.7",
                    OFFICIAL_FRONTEND_COMMIT,
                    "0.32.0",
                    OFFICIAL_COMFYUI_COMMIT,
                    "2026-08-13T18:03:35Z",
                )


if __name__ == "__main__":
    unittest.main()
