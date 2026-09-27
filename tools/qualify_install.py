"""Build a Registry-style ZIP and verify a fresh, dependency-free installation.

Uses the documented git-tracked + .comfyignore + tool.comfy.includes selection.
--archive can instead qualify the actual ZIP downloaded from the Registry.
pathspec is a development dependency, never an extension dependency.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
from pathlib import Path, PurePosixPath
import re
import subprocess
import tempfile
import tomllib
import zipfile

ROOT = Path(__file__).resolve().parents[1]


def package(destination: Path) -> None:
    from pathspec import PathSpec
    spec = PathSpec.from_lines("gitwildmatch", (ROOT / ".comfyignore").read_text().splitlines())
    tracked = subprocess.check_output(["git", "-c", f"safe.directory={ROOT.as_posix()}", "-C", str(ROOT), "ls-files", "-z"]).decode().split("\0")
    includes = tomllib.loads((ROOT / "pyproject.toml").read_text())["tool"]["comfy"]["includes"]
    forced = {p.relative_to(ROOT).as_posix() for folder in includes for p in (ROOT / folder).rglob("*") if p.is_file()}
    selected = {p for p in tracked if p and not spec.match_file(p)} | forced
    destination.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(destination, "w", zipfile.ZIP_DEFLATED) as archive:
        for name in sorted(selected):
            source = ROOT / name
            if source.is_symlink() or not source.is_file():
                raise ValueError(f"Invalid package member: {name}")
            archive.write(source, name)


def qualify(archive: Path, destination: Path) -> dict:
    if destination.exists():
        raise ValueError("Installation target must not exist")
    with zipfile.ZipFile(archive) as bundle:
        names = bundle.namelist()
        if len(names) != len(set(names)):
            raise ValueError("Duplicate ZIP members")
        required = {"__init__.py", "pyproject.toml", "LICENSE", "LICENSE-CONTENT", "web/nodes-wizard.js", "web/data/catalog.json"}
        if not required.issubset(names):
            raise ValueError(f"Missing required members: {sorted(required - set(names))}")
        for member in bundle.infolist():
            # ZipInfo.filename is normalized on Windows; validate the raw spelling.
            name = member.orig_filename
            path = PurePosixPath(name)
            if path.is_absolute() or ".." in path.parts or "\\" in name or ":" in name:
                raise ValueError(f"Unsafe ZIP member: {name}")
            if not (name.startswith("web/") or name in {"__init__.py", "pyproject.toml", "README.md", "LICENSE", "LICENSE-CONTENT", "icon.png"}):
                raise ValueError(f"Development material leaked into package: {name}")
        if bundle.testzip() is not None:
            raise ValueError("Corrupt archive")
        bundle.extractall(destination)
    metadata = tomllib.loads((destination / "pyproject.toml").read_text(encoding="utf-8"))
    version = metadata["project"]["version"]
    if not re.fullmatch(r"\d+\.\d+\.\d+", version):
        raise ValueError("Registry version is not compatible with Manager StrictVersion")
    assert metadata["project"]["dependencies"] == []
    spec = importlib.util.spec_from_file_location("wizard_isolated_install", destination / "__init__.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert module.NODE_CLASS_MAPPINGS == {}
    assert module.WEB_DIRECTORY == "./web"
    web = destination / "web"
    assert [p.relative_to(web).as_posix() for p in web.rglob("*.js")] == ["nodes-wizard.js"]
    for script in [web / "nodes-wizard.js", *web.rglob("*.mjs")]:
        # Check relative hashed chunk and Worker URLs in the generated code.
        for relative in re.findall(r'["\'](\.{1,2}/[^"\']+\.(?:mjs|json))["\']', script.read_text(encoding="utf-8")):
            target = (script.parent / relative).resolve()
            assert target.is_relative_to(web.resolve()) and target.is_file(), (script, relative)
    assert list(web.glob("workers/*.mjs")), "Missing search worker"
    catalog = json.loads((web / "data/catalog.json").read_text(encoding="utf-8"))
    assert len(catalog["articles"]) >= 700
    # Manager writes this after extraction; recognition also requires numeric version.
    (destination / ".tracking").write_text("\n".join(names), encoding="utf-8")
    return {"version": version, "files": len(names), "zipBytes": archive.stat().st_size, "articles": len(catalog["articles"]), "webRoot": str(web.resolve())}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", type=Path)
    parser.add_argument("--output", type=Path, default=ROOT / ".upstream-cache/release/node.zip")
    parser.add_argument("--install-dir", type=Path)
    args = parser.parse_args()
    archive = args.archive or args.output
    if args.archive is None:
        package(archive)
    if args.install_dir:
        print(json.dumps(qualify(archive, args.install_dir), indent=2))
    else:
        with tempfile.TemporaryDirectory(prefix="wizard-install-") as temporary:
            print(json.dumps(qualify(archive, Path(temporary) / "custom_nodes/renamed-wizard"), indent=2))


if __name__ == "__main__":
    main()
