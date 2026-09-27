"""Regression tests for release extraction, not just files in the checkout."""
from pathlib import Path
import tempfile
import unittest
import zipfile

from tools.qualify_install import qualify


class InstallArchiveTests(unittest.TestCase):
    def test_unsafe_members_are_rejected_before_extraction(self):
        for name in ("../escape.py", "/absolute.py", "C:/escape.py", "web\\escape.py", "tools/dev.py"):
            with self.subTest(name=name), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                archive = root / "node.zip"
                with zipfile.ZipFile(archive, "w") as bundle:
                    for required in ("__init__.py", "pyproject.toml", "LICENSE", "LICENSE-CONTENT", "web/nodes-wizard.js", "web/data/catalog.json"):
                        bundle.writestr(required, "")
                    info = zipfile.ZipInfo()
                    info.filename = name
                    bundle.writestr(info, "")
                with self.assertRaises(ValueError):
                    qualify(archive, root / "installed")
                self.assertFalse((root / "installed").exists())

    def test_existing_installation_is_never_overwritten(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with self.assertRaisesRegex(ValueError, "must not exist"):
                qualify(root / "absent.zip", root)
