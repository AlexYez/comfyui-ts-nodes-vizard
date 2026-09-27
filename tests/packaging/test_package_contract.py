"""Packaging contract tests that do not import ComfyUI."""

from __future__ import annotations

import importlib.util
import json
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
        package = json.loads((ROOT / "package.json").read_text(encoding="utf-8"))
        catalog = json.loads((ROOT / "content/catalog.manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(metadata["project"]["version"], package["version"])
        self.assertEqual(metadata["project"]["version"], catalog["catalogVersion"])
        # Manager's StrictVersion parses each of the first three parts as int.
        # Keep editorial alpha status in the catalog, not in the Registry version.
        self.assertRegex(metadata["project"]["version"], r"^\d+\.\d+\.\d+$")
        self.assertEqual(metadata["project"]["dependencies"], [])
        self.assertEqual(
            metadata["project"]["urls"]["Repository"],
            "https://github.com/AlexYez/comfyui-ts-nodes-vizard",
        )
        self.assertEqual(metadata["tool"]["comfy"]["PublisherId"], "timesaver")
        self.assertEqual(metadata["tool"]["comfy"]["DisplayName"], "TS Nodes Wizard")
        self.assertEqual(
            metadata["tool"]["comfy"]["Icon"],
            "https://raw.githubusercontent.com/AlexYez/comfyui-ts-nodes-vizard/refs/heads/main/icon.png",
        )
        self.assertEqual(metadata["tool"]["comfy"]["requires-comfyui"], ">=0.32.0")
        self.assertEqual(metadata["tool"]["comfy"]["includes"], ["web"])

    def test_required_distribution_files_exist(self) -> None:
        required = (
            "README.md",
            "LICENSE",
            "LICENSE-CONTENT",
            "icon.png",
            "web/README.md",
            "web/nodes-wizard.js",
            "web/data/catalog.json",
            "web/data/search-index.json",
        )
        for relative_path in required:
            with self.subTest(path=relative_path):
                self.assertTrue((ROOT / relative_path).is_file())
                self.assertGreater((ROOT / relative_path).stat().st_size, 0)

    def test_only_bootstrap_is_discovered_as_an_extension(self) -> None:
        # ComfyUI discovers **/*.js recursively. Workers must never be run as extensions.
        web = ROOT / "web"
        self.assertEqual(sorted(p.relative_to(web).as_posix() for p in web.rglob("*.js")), ["nodes-wizard.js"])
        self.assertLess((web / "nodes-wizard.js").stat().st_size, 20_000)
        self.assertTrue(list((web / "chunks").glob("*.mjs")))
        self.assertTrue(list((web / "workers").glob("*.mjs")))


if __name__ == "__main__":
    unittest.main()
