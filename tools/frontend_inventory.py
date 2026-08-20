#!/usr/bin/env python3
"""Extract fixed, user-visible frontend-only graph node types from ComfyUI frontend.

The extractor intentionally reads the package's production source of truth:
`SYSTEM_NODE_DEFS` (shared with the Vue/Nodes 2.0 node library) and the three
classic-canvas core extensions that register the same fixed LiteGraph types.
Dynamic backend, custom-extension, and user-subgraph registrations are outside
this inventory by definition.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any, Sequence


SYSTEM_DEFS = Path("src/stores/nodeDefStore.ts")
CLASSIC_REGISTRATIONS = (
    Path("src/extensions/core/widgetInputs.ts"),
    Path("src/extensions/core/rerouteNode.ts"),
    Path("src/extensions/core/noteNode.ts"),
)
NODES_2_APP_WIRING = Path("src/scripts/app.ts")
NODES_2_RENDERER = Path("src/renderer/extensions/vueNodes/components/LGraphNode.vue")

COMMIT_RE = re.compile(r"^[a-f0-9]{40}$")
TIMESTAMP_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")
REGISTERED_TYPE_RE = re.compile(
    r"LiteGraph\.registerNodeType\(\s*['\"]([A-Za-z_][A-Za-z0-9_.:-]*)['\"]",
    re.MULTILINE,
)


class InventoryError(Exception):
    pass


def load_text(root: Path, relative: Path) -> str:
    path = root / relative
    try:
        return path.read_text(encoding="utf-8")
    except FileNotFoundError as exc:
        raise InventoryError(f"missing official source file: {relative.as_posix()}") from exc


def object_body(text: str, declaration: str) -> str:
    start = text.find(declaration)
    if start < 0:
        raise InventoryError(f"source declaration not found: {declaration}")
    brace = text.find("{", start + len(declaration))
    if brace < 0:
        raise InventoryError(f"source declaration has no object body: {declaration}")
    depth = 0
    quote: str | None = None
    escaped = False
    for index in range(brace, len(text)):
        character = text[index]
        if quote is not None:
            if escaped:
                escaped = False
            elif character == "\\":
                escaped = True
            elif character == quote:
                quote = None
            continue
        if character in ("'", '"', "`"):
            quote = character
        elif character == "{":
            depth += 1
        elif character == "}":
            depth -= 1
            if depth == 0:
                return text[brace + 1 : index]
    raise InventoryError(f"unterminated object body: {declaration}")


def extract_system_node_types(root: Path) -> set[str]:
    body = object_body(
        load_text(root, SYSTEM_DEFS),
        "export const SYSTEM_NODE_DEFS: Record<string, ComfyNodeDefV1> =",
    )
    # Top-level object keys use exactly two-space indentation in the official source.
    result = set(re.findall(r"(?m)^  ([A-Za-z_][A-Za-z0-9_.:-]*):\s*\{", body))
    if not result:
        raise InventoryError("SYSTEM_NODE_DEFS contains no fixed node types")
    return result


def extract_classic_node_types(root: Path) -> set[str]:
    result: set[str] = set()
    for relative in CLASSIC_REGISTRATIONS:
        result.update(REGISTERED_TYPE_RE.findall(load_text(root, relative)))
    if not result:
        raise InventoryError("classic core extensions contain no literal node registrations")
    return result


def validate_surface_wiring(root: Path) -> None:
    app = load_text(root, NODES_2_APP_WIRING)
    if "...SYSTEM_NODE_DEFS" not in app or "nodeDefStore.updateNodeDefs" not in app:
        raise InventoryError("Nodes 2.0 app no longer merges SYSTEM_NODE_DEFS into its node store")
    renderer = load_text(root, NODES_2_RENDERER)
    if "nodeData.type === 'Reroute'" not in renderer:
        raise InventoryError("Nodes 2.0 renderer no longer exposes its Reroute node branch")


def package_version(root: Path) -> str:
    package = json.loads(load_text(root, Path("package.json")))
    value = package.get("version") if isinstance(package, dict) else None
    if not isinstance(value, str) or not value:
        raise InventoryError("official package.json has no version")
    return value


def checkout_commit(root: Path) -> str | None:
    try:
        result = subprocess.run(
            ["git", "-C", str(root), "rev-parse", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    value = result.stdout.strip().lower()
    return value if COMMIT_RE.fullmatch(value) else None


def build_inventory(
    root: Path,
    frontend_version: str,
    frontend_commit: str,
    comfyui_version: str,
    comfyui_commit: str,
    captured_at: str,
) -> dict[str, Any]:
    if package_version(root) != frontend_version:
        raise InventoryError(
            f"package version mismatch: expected {frontend_version}, got {package_version(root)}"
        )
    for label, value in (
        ("frontend commit", frontend_commit),
        ("ComfyUI commit", comfyui_commit),
    ):
        if not COMMIT_RE.fullmatch(value):
            raise InventoryError(f"{label} must be a full lowercase 40-character SHA")
    if not TIMESTAMP_RE.fullmatch(captured_at):
        raise InventoryError("captured-at must be an exact UTC timestamp ending in Z")
    actual_commit = checkout_commit(root)
    if actual_commit is not None and actual_commit != frontend_commit:
        raise InventoryError(
            f"checkout commit mismatch: expected {frontend_commit}, got {actual_commit}"
        )

    system_types = extract_system_node_types(root)
    classic_types = extract_classic_node_types(root)
    if system_types != classic_types:
        raise InventoryError(
            "fixed type sets differ between SYSTEM_NODE_DEFS and classic registrations: "
            f"system={sorted(system_types)!r}, classic={sorted(classic_types)!r}"
        )
    validate_surface_wiring(root)

    source = (
        "https://github.com/Comfy-Org/ComfyUI_frontend/tree/"
        f"{frontend_commit} (tag v{frontend_version}); pinned by "
        "https://github.com/Comfy-Org/ComfyUI/tree/"
        f"{comfyui_commit} (tag v{comfyui_version}, requirements.txt)"
    )
    return {
        "$schema": "../schemas/frontend-inventory.schema.v1.json",
        "schemaVersion": "1.0",
        "source": source,
        "frontendVersion": frontend_version,
        "capturedAt": captured_at,
        "nodes": [
            {"classType": class_type, "packageId": "comfy-core", "dev_only": False}
            for class_type in sorted(system_types)
        ],
    }


def rendered(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n"


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("--source-root", required=True, type=Path)
    result.add_argument("--frontend-version", required=True)
    result.add_argument("--frontend-commit", required=True)
    result.add_argument("--comfyui-version", required=True)
    result.add_argument("--comfyui-commit", required=True)
    result.add_argument("--captured-at", required=True)
    destination = result.add_mutually_exclusive_group()
    destination.add_argument("--check", type=Path)
    destination.add_argument("--output", type=Path)
    return result


def main(argv: Sequence[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        inventory = build_inventory(
            args.source_root.resolve(),
            args.frontend_version,
            args.frontend_commit.lower(),
            args.comfyui_version,
            args.comfyui_commit.lower(),
            args.captured_at,
        )
        text = rendered(inventory)
        if args.check:
            existing = args.check.read_text(encoding="utf-8")
            if existing != text:
                raise InventoryError(f"inventory is not current: {args.check}")
            print(f"Inventory is current: {args.check}")
        elif args.output:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(text, encoding="utf-8", newline="\n")
            print(f"Wrote {args.output}")
        else:
            print(text, end="")
    except (InventoryError, OSError, json.JSONDecodeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
