#!/usr/bin/env python3
"""Build deterministic evidence dossiers for Nodes Wizard article research.

The report is deliberately not an article generator.  It joins the exact
runtime inventory with version-pinned embedded documentation and official
workflow templates so an editor can inspect how every node is actually used.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import zipfile
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

try:
    from tools.catalog import object_info_nodes, parse_frontend_inventory
except ModuleNotFoundError:  # Running as ``python tools/research.py``.
    from catalog import object_info_nodes, parse_frontend_inventory


ROOT = Path(__file__).resolve().parents[1]
REPORT_SCHEMA_VERSION = "1.0"
WORKFLOW_PREFIX = "comfyui_workflow_templates_json/templates/"
DOCS_PREFIX = "comfyui_embedded_docs/docs/"
DIST_VERSION_RE = re.compile(r"-(?P<version>\d+(?:\.\d+)+(?:[A-Za-z0-9.-]*)?)\.dist-info/")
WORKFLOW_METADATA_RE = re.compile(r"^(?:index(?:\.[A-Za-z0-9-]+)?|index_logo|fuse_options)\.json$")


class ResearchError(Exception):
    """Raised when pinned evidence cannot be read without guessing."""


def _load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ResearchError(f"cannot read JSON {path}: {error}") from error


def _sha256(data: bytes) -> str:
    return f"sha256:{hashlib.sha256(data).hexdigest()}"


def _package_version(archive: zipfile.ZipFile, distribution: str) -> str:
    prefix = distribution.replace("-", "_") + "-"
    candidates = [
        name
        for name in archive.namelist()
        if name.startswith(prefix) and name.endswith(".dist-info/METADATA")
    ]
    if len(candidates) != 1:
        raise ResearchError(
            f"{archive.filename}: expected one {distribution} METADATA file, found {len(candidates)}"
        )
    match = DIST_VERSION_RE.search(candidates[0])
    if not match:
        raise ResearchError(f"{archive.filename}: cannot determine package version")
    return match.group("version")


def _read_docs_index(wheel_path: Path) -> tuple[str, dict[str, dict[str, Any]]]:
    try:
        archive = zipfile.ZipFile(wheel_path)
    except (OSError, zipfile.BadZipFile) as error:
        raise ResearchError(f"cannot open embedded-docs wheel {wheel_path}: {error}") from error

    with archive:
        version = _package_version(archive, "comfyui_embedded_docs")
        documents: dict[str, dict[str, Any]] = defaultdict(dict)
        for name in sorted(archive.namelist()):
            if not name.startswith(DOCS_PREFIX) or not name.endswith(".md"):
                continue
            relative = name[len(DOCS_PREFIX) :]
            parts = relative.split("/")
            if len(parts) != 2 or not parts[0] or not parts[1]:
                continue
            class_type, filename = parts
            locale = filename[:-3]
            data = archive.read(name)
            try:
                text = data.decode("utf-8")
            except UnicodeDecodeError as error:
                raise ResearchError(f"{wheel_path}:{name} is not UTF-8: {error}") from error
            documents[class_type][locale] = {
                "archivePath": name,
                "bytes": len(data),
                "lines": len(text.splitlines()),
                "sha256": _sha256(data),
            }
    return version, {key: documents[key] for key in sorted(documents)}


def _read_node_docs(wheel_path: Path, class_type: str) -> dict[str, dict[str, Any]]:
    """Return exact pinned documentation text for one runtime class type."""

    result: dict[str, dict[str, Any]] = {}
    try:
        archive = zipfile.ZipFile(wheel_path)
    except (OSError, zipfile.BadZipFile) as error:
        raise ResearchError(f"cannot open embedded-docs wheel {wheel_path}: {error}") from error
    with archive:
        prefix = f"{DOCS_PREFIX}{class_type}/"
        for name in sorted(archive.namelist()):
            if not name.startswith(prefix) or not name.endswith(".md"):
                continue
            relative = name[len(prefix) :]
            if "/" in relative:
                continue
            data = archive.read(name)
            try:
                text = data.decode("utf-8")
            except UnicodeDecodeError as error:
                raise ResearchError(f"{wheel_path}:{name} is not UTF-8: {error}") from error
            result[relative[:-3]] = {
                "archivePath": name,
                "sha256": _sha256(data),
                "text": text,
            }
    return result


def _workflow_node_type(node: Any) -> str | None:
    if not isinstance(node, Mapping):
        return None
    node_type = node.get("type")
    return node_type if isinstance(node_type, str) and node_type else None


def _workflow_nodes(workflow: Mapping[str, Any]) -> tuple[dict[Any, str], Counter[str]]:
    nodes_by_id: dict[Any, str] = {}
    counts: Counter[str] = Counter()
    raw_nodes = workflow.get("nodes")
    if not isinstance(raw_nodes, list):
        return nodes_by_id, counts
    for node in raw_nodes:
        node_type = _workflow_node_type(node)
        if node_type is None:
            continue
        counts[node_type] += 1
        node_id = node.get("id") if isinstance(node, Mapping) else None
        if isinstance(node_id, (str, int)) and not isinstance(node_id, bool):
            nodes_by_id[node_id] = node_type
    return nodes_by_id, counts


def _workflow_edges(workflow: Mapping[str, Any], nodes_by_id: Mapping[Any, str]) -> list[tuple[str, str]]:
    result: list[tuple[str, str]] = []
    links = workflow.get("links")
    if not isinstance(links, list):
        return result
    for link in links:
        if not isinstance(link, list) or len(link) < 5:
            continue
        source = nodes_by_id.get(link[1])
        target = nodes_by_id.get(link[3])
        if source and target:
            result.append((source, target))
    return result


def _is_workflow_metadata(name: str) -> bool:
    return WORKFLOW_METADATA_RE.fullmatch(Path(name).name) is not None


def _read_workflow_index(wheel_path: Path) -> tuple[str, dict[str, Any], dict[str, list[dict[str, Any]]]]:
    try:
        archive = zipfile.ZipFile(wheel_path)
    except (OSError, zipfile.BadZipFile) as error:
        raise ResearchError(f"cannot open workflow wheel {wheel_path}: {error}") from error

    workflows: dict[str, Any] = {}
    occurrences: dict[str, list[dict[str, Any]]] = defaultdict(list)
    with archive:
        version = _package_version(archive, "comfyui_workflow_templates_json")
        names = [
            name
            for name in sorted(archive.namelist())
            if name.startswith(WORKFLOW_PREFIX) and name.endswith(".json")
        ]
        for name in names:
            raw = archive.read(name)
            try:
                workflow = json.loads(raw.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError) as error:
                raise ResearchError(f"{wheel_path}:{name} is not valid UTF-8 JSON: {error}") from error
            if _is_workflow_metadata(name):
                continue
            if not isinstance(workflow, Mapping):
                raise ResearchError(f"{wheel_path}:{name} must contain a workflow object")
            if not isinstance(workflow.get("nodes"), list):
                raise ResearchError(f"{wheel_path}:{name} has no workflow nodes array")
            workflow_id = Path(name).stem
            if workflow_id in workflows:
                raise ResearchError(f"duplicate workflow id {workflow_id!r} in {wheel_path}")
            nodes_by_id, node_counts = _workflow_nodes(workflow)
            edges = _workflow_edges(workflow, nodes_by_id)
            workflows[workflow_id] = {
                "archivePath": name,
                "bytes": len(raw),
                "sha256": _sha256(raw),
                "nodeCount": sum(node_counts.values()),
                "nodeTypes": sorted(node_counts),
            }
            upstream: dict[str, Counter[str]] = defaultdict(Counter)
            downstream: dict[str, Counter[str]] = defaultdict(Counter)
            for source, target in edges:
                downstream[source][target] += 1
                upstream[target][source] += 1
            for node_type in sorted(node_counts):
                occurrences[node_type].append(
                    {
                        "workflowId": workflow_id,
                        "instances": node_counts[node_type],
                        "upstream": [
                            {"classType": class_type, "links": count}
                            for class_type, count in sorted(upstream[node_type].items())
                        ],
                        "downstream": [
                            {"classType": class_type, "links": count}
                            for class_type, count in sorted(downstream[node_type].items())
                        ],
                    }
                )
    return version, workflows, {key: occurrences[key] for key in sorted(occurrences)}


def _connected_node_ids(workflow: Mapping[str, Any], target_ids: set[Any]) -> set[Any]:
    result: set[Any] = set()
    links = workflow.get("links")
    if not isinstance(links, list):
        return result
    for link in links:
        if not isinstance(link, list) or len(link) < 5:
            continue
        source_id, target_id = link[1], link[3]
        if source_id in target_ids:
            result.add(target_id)
        if target_id in target_ids:
            result.add(source_id)
    return result


def _workflow_cases(wheel_path: Path, class_type: str, limit: int) -> list[dict[str, Any]]:
    if limit < 1:
        raise ResearchError("workflow limit must be at least 1")
    candidates: list[tuple[int, str, dict[str, Any]]] = []
    try:
        archive = zipfile.ZipFile(wheel_path)
    except (OSError, zipfile.BadZipFile) as error:
        raise ResearchError(f"cannot open workflow wheel {wheel_path}: {error}") from error
    with archive:
        names = [
            name
            for name in sorted(archive.namelist())
            if name.startswith(WORKFLOW_PREFIX) and name.endswith(".json")
        ]
        for name in names:
            raw = archive.read(name)
            try:
                workflow = json.loads(raw.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError) as error:
                raise ResearchError(f"{wheel_path}:{name} is not valid UTF-8 JSON: {error}") from error
            if _is_workflow_metadata(name):
                continue
            if not isinstance(workflow, Mapping):
                raise ResearchError(f"{wheel_path}:{name} must contain a workflow object")
            nodes = workflow.get("nodes")
            if not isinstance(nodes, list):
                continue
            targets = [
                node
                for node in nodes
                if isinstance(node, Mapping) and _workflow_node_type(node) == class_type
            ]
            if not targets:
                continue
            target_ids = {
                node.get("id")
                for node in targets
                if isinstance(node.get("id"), (str, int)) and not isinstance(node.get("id"), bool)
            }
            neighbor_ids = _connected_node_ids(workflow, target_ids)
            neighbors = [
                node
                for node in nodes
                if isinstance(node, Mapping) and node.get("id") in neighbor_ids
            ]
            links = [
                link
                for link in workflow.get("links", [])
                if isinstance(link, list)
                and len(link) >= 5
                and (link[1] in target_ids or link[3] in target_ids)
            ]
            workflow_id = Path(name).stem
            case = {
                "workflowId": workflow_id,
                "archivePath": name,
                "workflowNodeCount": len(nodes),
                "targetNodes": targets,
                "neighborNodes": neighbors,
                "links": links,
            }
            candidates.append((len(nodes), workflow_id, case))
    candidates.sort(key=lambda item: (item[0], item[1]))
    return [item[2] for item in candidates[:limit]]


def _source_evidence(
    definition: Mapping[str, Any], source_root: Path, class_type: str, context_lines: int = 12
) -> dict[str, Any] | None:
    relative = _source_path(definition.get("python_module"), source_root)
    if relative is None:
        return None
    path = source_root / relative
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeDecodeError) as error:
        raise ResearchError(f"cannot read source {path}: {error}") from error
    matches = [index for index, line in enumerate(lines) if class_type in line]
    excerpts: list[dict[str, Any]] = []
    covered_until = -1
    for index in matches[:8]:
        start = max(0, index - context_lines)
        end = min(len(lines), index + context_lines + 1)
        if start <= covered_until:
            if excerpts:
                previous = excerpts[-1]
                previous_end = max(previous["endLine"], end)
                previous["endLine"] = previous_end
                previous["text"] = "\n".join(
                    f"{number + 1:>6}  {lines[number]}"
                    for number in range(previous["startLine"] - 1, previous_end)
                )
                covered_until = previous_end
            continue
        excerpts.append(
            {
                "startLine": start + 1,
                "endLine": end,
                "text": "\n".join(
                    f"{number + 1:>6}  {lines[number]}" for number in range(start, end)
                ),
            }
        )
        covered_until = end
    return {"path": relative, "matches": [index + 1 for index in matches], "excerpts": excerpts}


def _source_path(python_module: Any, source_root: Path | None) -> str | None:
    if not isinstance(python_module, str) or not python_module or source_root is None:
        return None
    candidate = source_root.joinpath(*python_module.split(".")).with_suffix(".py")
    try:
        relative = candidate.resolve().relative_to(source_root.resolve())
    except (OSError, ValueError):
        return None
    return relative.as_posix() if candidate.is_file() else None


def _runtime_inputs(definition: Mapping[str, Any]) -> list[dict[str, Any]]:
    inputs = definition.get("input")
    if not isinstance(inputs, Mapping):
        return []
    result: list[dict[str, Any]] = []
    for group in ("required", "optional", "hidden"):
        values = inputs.get(group)
        if not isinstance(values, Mapping):
            continue
        for name, specification in values.items():
            if not isinstance(name, str):
                continue
            data_type: Any = None
            if isinstance(specification, list) and specification:
                first = specification[0]
                if isinstance(first, str):
                    data_type = first
                elif isinstance(first, list):
                    data_type = "COMBO"
            elif group == "hidden" and isinstance(specification, str):
                data_type = specification
            result.append({"name": name, "type": data_type, "group": group})
    return result


def _runtime_outputs(definition: Mapping[str, Any]) -> list[dict[str, Any]]:
    types = definition.get("output")
    names = definition.get("output_name")
    if not isinstance(types, list):
        return []
    result: list[dict[str, Any]] = []
    for index, data_type in enumerate(types):
        name = names[index] if isinstance(names, list) and index < len(names) else None
        result.append({"name": name, "type": data_type})
    return result


def build_report(
    inventory_payload: Any,
    embedded_docs_wheel: Path,
    workflow_wheel: Path,
    *,
    frontend_payload: Any | None = None,
    source_root: Path | None = None,
    comfyui_version: str,
    frontend_version: str,
) -> dict[str, Any]:
    runtime = object_info_nodes(inventory_payload)
    frontend = (
        parse_frontend_inventory(frontend_payload, "frontend inventory")
        if frontend_payload is not None
        else None
    )
    docs_version, docs = _read_docs_index(embedded_docs_wheel)
    workflow_version, workflows, workflow_occurrences = _read_workflow_index(workflow_wheel)

    dossiers: list[dict[str, Any]] = []
    for class_type in sorted(runtime):
        definition = runtime[class_type]
        doc_locales = docs.get(class_type, {})
        occurrences = workflow_occurrences.get(class_type, [])
        dossiers.append(
            {
                "classType": class_type,
                "origin": "backend",
                "pythonModule": definition.get("python_module"),
                "sourcePath": _source_path(definition.get("python_module"), source_root),
                "displayName": definition.get("display_name"),
                "category": definition.get("category"),
                "description": definition.get("description"),
                "flags": {
                    "api": definition.get("api_node") is True,
                    "deprecated": definition.get("deprecated") is True,
                    "experimental": definition.get("experimental") is True,
                },
                "inputs": _runtime_inputs(definition),
                "outputs": _runtime_outputs(definition),
                "embeddedDocs": {locale: doc_locales[locale] for locale in sorted(doc_locales)},
                "workflowUsage": occurrences,
                "researchState": "pending",
            }
        )

    if frontend is not None:
        frontend_nodes = frontend.get("nodes", {})
        for class_type in sorted(frontend_nodes):
            definition = frontend_nodes[class_type]
            doc_locales = docs.get(class_type, {})
            dossiers.append(
                {
                    "classType": class_type,
                    "origin": "frontend",
                    "pythonModule": None,
                    "sourcePath": None,
                    "displayName": definition.get("displayName"),
                    "category": definition.get("category"),
                    "description": definition.get("description"),
                    "flags": {
                        "api": False,
                        "deprecated": definition.get("deprecated") is True,
                        "experimental": definition.get("experimental") is True,
                    },
                    "inputs": [],
                    "outputs": [],
                    "embeddedDocs": {locale: doc_locales[locale] for locale in sorted(doc_locales)},
                    "workflowUsage": workflow_occurrences.get(class_type, []),
                    "researchState": "pending",
                }
            )

    dossiers.sort(key=lambda item: (item["origin"], item["classType"]))
    backend_dossiers = [item for item in dossiers if item["origin"] == "backend"]
    frontend_dossiers = [item for item in dossiers if item["origin"] == "frontend"]
    report = {
        "schemaVersion": REPORT_SCHEMA_VERSION,
        "baseline": {
            "comfyui": comfyui_version,
            "frontend": frontend_version,
            "embeddedDocs": docs_version,
            "workflowTemplatesJson": workflow_version,
        },
        "summary": {
            "backendNodes": len(backend_dossiers),
            "frontendNodes": len(frontend_dossiers),
            "nodesWithRussianDocs": sum("ru" in item["embeddedDocs"] for item in dossiers),
            "nodesWithOfficialWorkflow": sum(bool(item["workflowUsage"]) for item in dossiers),
            "nodesWithoutOfficialWorkflow": sum(not item["workflowUsage"] for item in dossiers),
            "officialWorkflows": len(workflows),
        },
        "workflows": {key: workflows[key] for key in sorted(workflows)},
        "nodes": dossiers,
    }
    return report


def _canonical_json(data: Any) -> str:
    return json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def command_report(args: argparse.Namespace) -> int:
    report = build_report(
        _load_json(Path(args.inventory)),
        Path(args.embedded_docs_wheel),
        Path(args.workflow_wheel),
        frontend_payload=_load_json(Path(args.frontend_inventory)) if args.frontend_inventory else None,
        source_root=Path(args.source_root) if args.source_root else None,
        comfyui_version=args.comfyui_version,
        frontend_version=args.frontend_version,
    )
    output = Path(args.output)
    rendered = _canonical_json(report)
    if args.check:
        try:
            current = output.read_text(encoding="utf-8")
        except OSError as error:
            print(f"research report is missing: {error}", file=sys.stderr)
            return 1
        if current != rendered:
            print(f"research report is stale: {output}", file=sys.stderr)
            return 1
        print(f"research report is current: {output}")
        return 0
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(rendered, encoding="utf-8", newline="\n")
    print(
        f"wrote {output}: {report['summary']['backendNodes']} backend, "
        f"{report['summary']['frontendNodes']} frontend-only nodes"
    )
    return 0


def command_inspect(args: argparse.Namespace) -> int:
    inventory = object_info_nodes(_load_json(Path(args.inventory)))
    definition = inventory.get(args.node_id)
    if definition is None:
        raise ResearchError(f"node {args.node_id!r} is absent from the runtime inventory")
    docs = _read_node_docs(Path(args.embedded_docs_wheel), args.node_id)
    dossier = {
        "schemaVersion": REPORT_SCHEMA_VERSION,
        "classType": args.node_id,
        "runtimeDefinition": definition,
        "source": _source_evidence(definition, Path(args.source_root), args.node_id),
        "embeddedDocs": docs,
        "workflowCases": _workflow_cases(
            Path(args.workflow_wheel), args.node_id, args.workflow_limit
        ),
        "editorialChecklist": {
            "implementationRead": False,
            "runtimeFieldsChecked": False,
            "workflowRunOrTraced": False,
            "limitationsChecked": False,
            "russianEdited": False,
            "factsRecheckedAfterEditing": False,
        },
    }
    rendered = _canonical_json(dossier)
    if args.output:
        output = Path(args.output)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(rendered, encoding="utf-8", newline="\n")
        print(f"wrote {output}")
    else:
        sys.stdout.buffer.write(rendered.encode("utf-8"))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Join pinned ComfyUI runtime, documentation, source, and workflow evidence."
    )
    commands = parser.add_subparsers(dest="command", required=True)
    report = commands.add_parser("report", help="write a deterministic per-node research report")
    report.add_argument("--inventory", required=True, help="clean ComfyUI /object_info snapshot")
    report.add_argument("--frontend-inventory", help="versioned frontend-only node inventory")
    report.add_argument("--embedded-docs-wheel", required=True, help="pinned comfyui-embedded-docs wheel")
    report.add_argument("--workflow-wheel", required=True, help="pinned workflow-templates-json wheel")
    report.add_argument("--source-root", help="optional checked-out ComfyUI source root")
    report.add_argument("--comfyui-version", required=True)
    report.add_argument("--frontend-version", required=True)
    report.add_argument("--output", required=True)
    report.add_argument("--check", action="store_true", help="compare output without writing")
    report.set_defaults(func=command_report)
    inspect = commands.add_parser("inspect", help="print the unabridged evidence dossier for one backend node")
    inspect.add_argument("--inventory", required=True, help="clean ComfyUI /object_info snapshot")
    inspect.add_argument("--embedded-docs-wheel", required=True, help="pinned comfyui-embedded-docs wheel")
    inspect.add_argument("--workflow-wheel", required=True, help="pinned workflow-templates-json wheel")
    inspect.add_argument("--source-root", required=True, help="checked-out ComfyUI source root")
    inspect.add_argument("--node-id", required=True)
    inspect.add_argument("--workflow-limit", type=int, default=8)
    inspect.add_argument("--output")
    inspect.set_defaults(func=command_inspect)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return int(args.func(args))
    except ResearchError as error:
        print(f"research error: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
