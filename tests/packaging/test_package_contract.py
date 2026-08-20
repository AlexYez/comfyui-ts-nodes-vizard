"""Packaging contract tests that do not import ComfyUI."""

from __future__ import annotations

import importlib.util
import pathlib
import tomllib
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[2]


class PackageContractTests(unittest.TestCase):
    def test_comfy_entrypoint_is_client_only(self) -> None:
        spec = importlib.util.spec_from_file_location("comfyui_nodes_wizard", ROOT / "__init__.py")
        self.assertIsNotNone(spec)
        self.assertIsNotNone(spec.loader)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

        self.assertEqual(module.NODE_CLASS_MAPPINGS, {})
        self.assertEqual(module.WEB_DIRECTORY, "./web")

    def test_registry_metadata_matches_contract(self) -> None:
        with (ROOT / "pyproject.toml").open("rb") as stream:
            metadata = tomllib.load(stream)

        self.assertEqual(metadata["project"]["name"], "comfyui-ts-nodes-vizard")
        self.assertEqual(metadata["project"]["version"], "0.1.0-alpha.1")
        self.assertEqual(metadata["project"]["dependencies"], [])
        self.assertEqual(metadata["tool"]["comfy"]["requires-comfyui"], ">=0.32.0")
        self.assertEqual(metadata["tool"]["comfy"]["includes"], ["web"])

    def test_required_distribution_files_exist(self) -> None:
        required = (
            "README.md",
            "LICENSE",
            "LICENSE-CONTENT",
            "web/README.md",
            "web/nodes-wizard.js",
            "web/data/catalog.json",
            "web/data/search-index.json",
        )
        for relative_path in required:
            with self.subTest(path=relative_path):
                self.assertTrue((ROOT / relative_path).is_file())
                self.assertGreater((ROOT / relative_path).stat().st_size, 0)


if __name__ == "__main__":
    unittest.main()
