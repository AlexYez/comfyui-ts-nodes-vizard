#!/usr/bin/env python3
"""Validate, compile, fingerprint and compare Nodes Wizard content.

The tool deliberately uses only the Python standard library.  Commands that
write require an explicit destination; validation and CI checks are read-only.
"""

from __future__ import annotations

import argparse
import copy
import datetime as dt
import hashlib
import io
import json
import re
import subprocess
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence


ROOT = Path(__file__).resolve().parents[1]
CONTENT = ROOT / "content"
CATALOG_MANIFEST = CONTENT / "catalog.manifest.json"
GENERATED = CONTENT / "generated"
FRONTEND_INVENTORY_SAMPLE = CONTENT / "runtime" / "comfyui-frontend-1.48.7.frontend-inventory.sample.json"

ARTICLE_STATUSES = {"active", "deprecated", "experimental", "stale", "removed", "draft"}
EDITORIAL_STATES = {"draft", "in_review", "approved"}
ARTICLE_KINDS = {"core", "custom", "virtual", "concept"}
ORIGINS = {"backend", "frontend", "concept"}
IDENTIFIER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_.:-]*$")
ARTICLE_ID_RE = re.compile(r"^[a-z0-9]+(?:[.-][a-z0-9]+)*$")
SHA256_RE = re.compile(r"^sha256:[a-f0-9]{64}$")
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


class CatalogError(Exception):
    """A deterministic content or CLI validation failure."""


def canonical_json_bytes(value: Any) -> bytes:
    """Return canonical UTF-8 JSON used by fingerprints and signatures."""

    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def sha256_prefixed(value: Any) -> str:
    return "sha256:" + hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_json(path: Path) -> Any:
    try:
        with path.open("r", encoding="utf-8") as handle:
            return json.load(handle)
    except FileNotFoundError as exc:
        raise CatalogError(f"missing file: {path}") from exc
    except json.JSONDecodeError as exc:
        raise CatalogError(f"invalid JSON in {path}: {exc}") from exc


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(value, ensure_ascii=False, indent=2, sort_keys=False, allow_nan=False) + "\n"
    path.write_text(text, encoding="utf-8", newline="\n")


def relative_content_path(base: Path, value: Any, label: str) -> Path:
    if not isinstance(value, str) or not value:
        raise CatalogError(f"{label} must be a non-empty relative path")
    candidate = Path(value)
    if candidate.is_absolute():
        raise CatalogError(f"{label} must be relative: {value!r}")
    resolved = (base / candidate).resolve()
    try:
        resolved.relative_to(CONTENT.resolve())
    except ValueError as exc:
        raise CatalogError(f"{label} leaves content/: {value!r}") from exc
    return resolved


def is_date(value: Any) -> bool:
    if not isinstance(value, str) or not DATE_RE.fullmatch(value):
        return False
    try:
        dt.date.fromisoformat(value)
    except ValueError:
        return False
    return True


def is_datetime(value: Any) -> bool:
    """Accept an RFC 3339-style timestamp with an explicit timezone."""

    if not isinstance(value, str):
        return False
    candidate = value[:-1] + "+00:00" if value.endswith("Z") else value
    try:
        parsed = dt.datetime.fromisoformat(candidate)
    except ValueError:
        return False
    return parsed.tzinfo is not None


def require(condition: bool, message: str, errors: list[str]) -> None:
    if not condition:
        errors.append(message)


def require_string(value: Any, label: str, errors: list[str], minimum: int = 1) -> None:
    require(isinstance(value, str) and len(value.strip()) >= minimum, f"{label} must be a string of length >= {minimum}", errors)


def require_string_list(value: Any, label: str, errors: list[str], minimum: int = 0) -> None:
    good = isinstance(value, list) and len(value) >= minimum and all(isinstance(item, str) and item for item in value)
    require(good, f"{label} must be a string array with at least {minimum} item(s)", errors)
    if good:
        require(len(value) == len(set(value)), f"{label} contains duplicates", errors)


def require_exact_keys(value: Any, allowed: set[str], required: set[str], label: str, errors: list[str]) -> None:
    if not isinstance(value, Mapping):
        require(False, f"{label} must be an object", errors)
        return
    missing = sorted(required - set(value))
    unknown = sorted(set(value) - allowed)
    require(not missing, f"{label}: missing keys {missing}", errors)
    require(not unknown, f"{label}: unknown keys {unknown}", errors)


def _json_type_matches(value: Any, expected: str) -> bool:
    if expected == "null":
        return value is None
    if expected == "boolean":
        return isinstance(value, bool)
    if expected == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if expected == "number":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    if expected == "string":
        return isinstance(value, str)
    if expected == "array":
        return isinstance(value, list)
    if expected == "object":
        return isinstance(value, Mapping)
    return False


def json_schema_errors(instance: Any, schema: Mapping[str, Any], label: str = "$" ) -> list[str]:
    """Validate the JSON Schema subset used by the compiled-catalog contract."""

    errors: list[str] = []

    def resolve(reference: str) -> Mapping[str, Any]:
        if not reference.startswith("#/"):
            raise CatalogError(f"unsupported non-local JSON Schema reference: {reference}")
        current: Any = schema
        for token in reference[2:].split("/"):
            token = token.replace("~1", "/").replace("~0", "~")
            if not isinstance(current, Mapping) or token not in current:
                raise CatalogError(f"unresolved JSON Schema reference: {reference}")
            current = current[token]
        if not isinstance(current, Mapping):
            raise CatalogError(f"JSON Schema reference is not an object: {reference}")
        return current

    def visit(value: Any, rule: Mapping[str, Any], path: str) -> None:
        reference = rule.get("$ref")
        if isinstance(reference, str):
            visit(value, resolve(reference), path)
            return
        if "const" in rule and value != rule["const"]:
            errors.append(f"{path}: expected constant {rule['const']!r}")
        enum = rule.get("enum")
        if isinstance(enum, list) and value not in enum:
            errors.append(f"{path}: value {value!r} is not in {enum!r}")

        declared_type = rule.get("type")
        expected_types = [declared_type] if isinstance(declared_type, str) else declared_type
        if isinstance(expected_types, list):
            if not any(isinstance(item, str) and _json_type_matches(value, item) for item in expected_types):
                errors.append(f"{path}: expected JSON type {expected_types!r}")
                return

        if isinstance(value, str):
            minimum = rule.get("minLength")
            maximum = rule.get("maxLength")
            if isinstance(minimum, int) and len(value) < minimum:
                errors.append(f"{path}: string is shorter than {minimum}")
            if isinstance(maximum, int) and len(value) > maximum:
                errors.append(f"{path}: string is longer than {maximum}")
            pattern = rule.get("pattern")
            if isinstance(pattern, str) and re.search(pattern, value) is None:
                errors.append(f"{path}: string does not match {pattern!r}")
            value_format = rule.get("format")
            if value_format == "date" and not is_date(value):
                errors.append(f"{path}: invalid date")
            elif value_format == "date-time" and not is_datetime(value):
                errors.append(f"{path}: invalid timezone-aware date-time")

        if isinstance(value, (int, float)) and not isinstance(value, bool):
            minimum = rule.get("minimum")
            maximum = rule.get("maximum")
            if isinstance(minimum, (int, float)) and value < minimum:
                errors.append(f"{path}: number is less than {minimum}")
            if isinstance(maximum, (int, float)) and value > maximum:
                errors.append(f"{path}: number is greater than {maximum}")

        if isinstance(value, list):
            minimum_items = rule.get("minItems")
            if isinstance(minimum_items, int) and len(value) < minimum_items:
                errors.append(f"{path}: array has fewer than {minimum_items} items")
            if rule.get("uniqueItems") is True:
                normalized = [canonical_json_bytes(item) for item in value]
                if len(normalized) != len(set(normalized)):
                    errors.append(f"{path}: array items are not unique")
            item_rule = rule.get("items")
            if isinstance(item_rule, Mapping):
                for index, item in enumerate(value):
                    visit(item, item_rule, f"{path}[{index}]")

        if isinstance(value, Mapping):
            required = rule.get("required")
            if isinstance(required, list):
                for key in required:
                    if isinstance(key, str) and key not in value:
                        errors.append(f"{path}: missing required property {key!r}")
            properties = rule.get("properties")
            properties = properties if isinstance(properties, Mapping) else {}
            for key, child in value.items():
                child_path = f"{path}.{key}"
                child_rule = properties.get(key)
                if isinstance(child_rule, Mapping):
                    visit(child, child_rule, child_path)
                    continue
                additional = rule.get("additionalProperties", True)
                if additional is False:
                    errors.append(f"{path}: additional property {key!r} is not allowed")
                elif isinstance(additional, Mapping):
                    visit(child, additional, child_path)

    visit(instance, schema, label)
    return errors


def validate_compiled_catalog_instance(instance: Any) -> list[str]:
    schema_path = CONTENT / "schemas" / "compiled-catalog.schema.v1.json"
    schema = load_json(schema_path)
    if not isinstance(schema, Mapping):
        raise CatalogError(f"{schema_path} must contain an object")
    return json_schema_errors(instance, schema)


def validate_article_research_records(
    articles: Sequence[tuple[Path, Mapping[str, Any]]], errors: list[str]
) -> None:
    schema_path = CONTENT / "schemas" / "article-research.schema.v1.json"
    schema = load_json(schema_path)
    if not isinstance(schema, Mapping):
        raise CatalogError(f"{schema_path} must contain an object")
    review_dir = CONTENT / "research" / "reviews"
    records: dict[str, tuple[Path, Mapping[str, Any]]] = {}
    if review_dir.exists():
        for path in sorted(review_dir.glob("*.json")):
            record = load_json(path)
            label = path.relative_to(ROOT).as_posix()
            if not isinstance(record, Mapping):
                errors.append(f"{label}: research record must be an object")
                continue
            errors.extend(f"{label}: {error}" for error in json_schema_errors(record, schema))
            article_id = record.get("articleId")
            if not isinstance(article_id, str):
                continue
            require(path.name == f"{article_id}.json", f"{label}: filename must match articleId", errors)
            require(article_id not in records, f"duplicate research record for {article_id!r}", errors)
            records[article_id] = (path, record)

    article_by_id = {
        str(article.get("articleId")): article
        for _, article in articles
        if isinstance(article.get("articleId"), str)
    }
    for article_id, article in article_by_id.items():
        pair = records.get(article_id)
        require(pair is not None, f"article {article_id} has no research record", errors)
        if pair is None:
            continue
        _, record = pair
        node = record.get("node")
        identity = article.get("runtimeIdentity")
        if isinstance(node, Mapping) and isinstance(identity, Mapping):
            require(node.get("classType") == identity.get("classType"), f"{article_id}: research classType differs from article", errors)
            require(node.get("origin") == identity.get("origin"), f"{article_id}: research origin differs from article", errors)
            expected_module = identity.get("pythonModule") if isinstance(identity.get("pythonModule"), str) else None
            require(node.get("pythonModule") == expected_module, f"{article_id}: research pythonModule differs from article", errors)
        if article.get("editorial", {}).get("state") == "approved":
            checks = record.get("checks") if isinstance(record.get("checks"), Mapping) else {}
            require(record.get("state") == "human_approved", f"approved article {article_id} needs human_approved research", errors)
            require(record.get("reviewMode") == "human", f"approved article {article_id} needs human research review", errors)
            require(all(value is True for value in checks.values()), f"approved article {article_id} has incomplete research checks", errors)
            require(not record.get("knownGaps"), f"approved article {article_id} still has known research gaps", errors)
    for article_id in sorted(set(records) - set(article_by_id)):
        errors.append(f"orphan research record for unknown article {article_id!r}")


def _legacy_input_type(definition: Any) -> str:
    if isinstance(definition, Mapping):
        raw = definition.get("type") or definition.get("data_type") or definition.get("io_type")
        if isinstance(raw, str):
            return raw
        choices = definition.get("options") or definition.get("values")
        if isinstance(choices, list):
            return "COMBO"
    if isinstance(definition, (list, tuple)) and definition:
        first = definition[0]
        if isinstance(first, str):
            return first
        if isinstance(first, (list, tuple)):
            return "COMBO"
    if isinstance(definition, str):
        return definition
    return "UNKNOWN"


_STABLE_CONSTRAINT_KEYS = (
    "min",
    "max",
    "step",
    "round",
    "multiline",
    "dynamicPrompts",
    "forceInput",
    "defaultInput",
    "lazy",
    "rawLink",
    "socketless",
    "advanced",
    "control_after_generate",
)


def _input_options(definition: Any) -> Mapping[str, Any]:
    if isinstance(definition, Mapping):
        return definition
    if isinstance(definition, (list, tuple)) and len(definition) > 1 and isinstance(definition[1], Mapping):
        return definition[1]
    return {}


def normalize_input(name: str, section: str, definition: Any) -> dict[str, Any]:
    input_type = _legacy_input_type(definition)
    options = _input_options(definition)
    normalized: dict[str, Any] = {
        "name": name,
        "type": input_type,
        "section": section,
        "required": section == "required",
    }
    constraints: dict[str, Any] = {}
    for key in _STABLE_CONSTRAINT_KEYS:
        value = options.get(key)
        if isinstance(value, (str, int, float, bool)) and not isinstance(value, complex):
            constraints[key] = value
    # Environment/model-dependent defaults are deliberately excluded for
    # combo inputs.  Scalar defaults remain structural for widgets.
    if input_type != "COMBO":
        default = options.get("default")
        if isinstance(default, (str, int, float, bool)) or default is None and "default" in options:
            constraints["default"] = default
    if constraints:
        normalized["constraints"] = constraints
    return normalized


def normalize_node_schema(node_id: str, raw: Mapping[str, Any]) -> dict[str, Any]:
    """Normalize `/object_info` NodeInfoV1 into a structural object.

    Combo choices and combo defaults are not included: checkpoint/model/file
    lists vary by installation and sampler choices can grow without changing
    an input socket's structural type.
    """

    inputs_root = raw.get("input", {})
    if not isinstance(inputs_root, Mapping):
        inputs_root = {}
    input_order = raw.get("input_order", {})
    if not isinstance(input_order, Mapping):
        input_order = {}
    inputs: list[dict[str, Any]] = []
    for section in ("required", "optional", "hidden"):
        definitions = inputs_root.get(section, {})
        if not isinstance(definitions, Mapping):
            continue
        ordered = input_order.get(section, [])
        names = [name for name in ordered if isinstance(name, str) and name in definitions] if isinstance(ordered, list) else []
        names.extend(name for name in definitions if name not in names)
        for name in names:
            inputs.append(normalize_input(str(name), section, definitions[name]))

    output_types = raw.get("output", [])
    output_names = raw.get("output_name", [])
    output_lists = raw.get("output_is_list", [])
    output_tooltips = raw.get("output_tooltips", [])
    if not isinstance(output_types, list):
        output_types = []
    outputs: list[dict[str, Any]] = []
    for index, output_type in enumerate(output_types):
        output: dict[str, Any] = {
            "name": output_names[index] if isinstance(output_names, list) and index < len(output_names) and isinstance(output_names[index], str) else str(output_type),
            "type": str(output_type),
            "list": bool(output_lists[index]) if isinstance(output_lists, list) and index < len(output_lists) else False,
        }
        if isinstance(output_tooltips, list) and index < len(output_tooltips) and isinstance(output_tooltips[index], str):
            output["tooltip"] = output_tooltips[index]
        outputs.append(output)

    return {
        "nodeId": node_id,
        "pythonModule": raw.get("python_module") if isinstance(raw.get("python_module"), str) else None,
        "inputs": inputs,
        "outputs": outputs,
        "flags": {
            "deprecated": bool(raw.get("deprecated", False)),
            "experimental": bool(raw.get("experimental", False)),
            "api_node": bool(raw.get("api_node", False)),
        },
    }


def schema_fingerprint(node_id: str, raw: Mapping[str, Any]) -> str:
    return sha256_prefixed(normalize_node_schema(node_id, raw))


def object_info_nodes(payload: Any) -> dict[str, Mapping[str, Any]]:
    if not isinstance(payload, Mapping):
        raise CatalogError("object_info must be a JSON object")
    # Accept an explicit wrapper used by some archived snapshots.
    if isinstance(payload.get("nodes"), Mapping):
        payload = payload["nodes"]
    result: dict[str, Mapping[str, Any]] = {}
    for key, value in payload.items():
        if not isinstance(value, Mapping):
            continue
        # Developer/test-only types are not part of the user-facing release inventory.
        if bool(value.get("dev_only", False)):
            continue
        node_id = value.get("name") if isinstance(value.get("name"), str) else str(key)
        result[node_id] = value
    return result


def local_generation_nodes(nodes: Mapping[str, Mapping[str, Any]]) -> dict[str, Mapping[str, Any]]:
    """Return the v1.0 catalog scope: local nodes, excluding paid/remote API nodes."""

    return {
        node_id: node
        for node_id, node in nodes.items()
        if not bool(node.get("api_node", False))
        # Some configuration/helper nodes shipped by the API package do not
        # serialize api_node=true. Their module provenance is still exact and
        # keeps remote-service UI out of the local-generation release scope.
        and not str(node.get("python_module", "")).startswith("comfy_api_nodes.")
    }


def is_test_inventory_node(node_id: str, node: Mapping[str, Any]) -> bool:
    """Identify upstream test fixtures without mutating the raw snapshot."""

    if bool(node.get("test_only", False)):
        return True
    module = str(node.get("python_module", "")).replace("\\", "/").lower()
    if module.startswith("tests.") or ".tests." in module or "/tests/" in module:
        return True
    display_name = str(node.get("display_name", ""))
    return bool(
        re.fullmatch(r"Test.*|.*TestNode|.*Test", node_id)
        or re.fullmatch(r"Test.*|.*TestNode|.*Test", display_name)
    )


def backend_inventory_report(snapshot: Any, metadata: Mapping[str, Any]) -> dict[str, Any]:
    """Build a deterministic report while retaining every raw endpoint entry."""

    if not isinstance(snapshot, Mapping):
        raise CatalogError("backend object_info snapshot must be a JSON object")
    nodes: dict[str, Mapping[str, Any]] = {}
    for node_id, node in snapshot.items():
        if not isinstance(node_id, str) or not isinstance(node, Mapping):
            raise CatalogError("backend object_info entries must map string node IDs to objects")
        nodes[node_id] = node

    dev_only = {node_id for node_id, node in nodes.items() if bool(node.get("dev_only", False))}
    test_only = {node_id for node_id, node in nodes.items() if is_test_inventory_node(node_id, node)}
    excluded = dev_only | test_only
    user_nodes = {node_id: node for node_id, node in nodes.items() if node_id not in excluded}
    flags = ("api_node", "experimental", "deprecated", "dev_only")

    def flag_counts(values: Mapping[str, Mapping[str, Any]]) -> dict[str, int]:
        return {
            "api": sum(bool(node.get("api_node", False)) for node in values.values()),
            "experimental": sum(bool(node.get("experimental", False)) for node in values.values()),
            "deprecated": sum(bool(node.get("deprecated", False)) for node in values.values()),
            "devOnly": sum(bool(node.get("dev_only", False)) for node in values.values()),
        }

    combinations: dict[str, int] = {}
    for node in user_nodes.values():
        enabled = [
            label
            for field, label in (("api_node", "api"), ("experimental", "experimental"), ("deprecated", "deprecated"))
            if bool(node.get(field, False))
        ]
        key = "+".join(enabled) if enabled else "standard"
        combinations[key] = combinations.get(key, 0) + 1

    overlaps: dict[str, int] = {}
    for left_index, left in enumerate(flags):
        for right in flags[left_index + 1:]:
            key = f"{left}+{right}"
            overlaps[key] = sum(
                bool(node.get(left, False)) and bool(node.get(right, False))
                for node in user_nodes.values()
            )

    modules: dict[str, int] = {}
    for node in user_nodes.values():
        module = str(node.get("python_module", "unknown"))
        modules[module] = modules.get(module, 0) + 1

    source = metadata.get("source") if isinstance(metadata.get("source"), Mapping) else {}
    snapshot_meta = metadata.get("snapshot") if isinstance(metadata.get("snapshot"), Mapping) else {}
    return {
        "$schema": "../schemas/backend-inventory-report.schema.v1.json",
        "schemaVersion": "1.0",
        "inventoryId": metadata.get("inventoryId"),
        "source": {
            "repository": source.get("repository"),
            "tag": source.get("tag"),
            "commit": source.get("commit"),
            "backendVersion": source.get("backendVersion"),
        },
        "snapshot": {
            "path": snapshot_meta.get("path"),
            "sha256": snapshot_meta.get("sha256"),
            "size": snapshot_meta.get("size"),
        },
        "counts": {
            "rawNodeCount": len(nodes),
            "userServerNodeCount": len(user_nodes),
            "excludedNodeCount": len(excluded),
            "devOnlyNodeCount": len(dev_only),
            "testNodeCount": len(test_only),
            "pythonModuleCount": len(modules),
        },
        "rawFlags": flag_counts(nodes),
        "userServerFlags": flag_counts(user_nodes),
        "userServerFlagCombinations": dict(sorted(combinations.items())),
        "userServerFlagOverlaps": dict(sorted(overlaps.items())),
        "excluded": {
            "devOnlyNodeIds": sorted(dev_only),
            "testNodeIds": sorted(test_only),
            "unionNodeIds": sorted(excluded),
        },
        "pythonModules": [
            {"module": module, "nodeCount": count}
            for module, count in sorted(modules.items(), key=lambda item: (-item[1], item[0]))
        ],
        "userServerNodeIds": sorted(user_nodes),
    }


def backend_inventory_markdown(report: Mapping[str, Any]) -> str:
    counts = report["counts"]
    flags = report["userServerFlags"]
    source = report["source"]
    lines = [
        f"# ComfyUI {source['backendVersion']} backend inventory",
        "",
        f"- Official tag: `{source['tag']}`",
        f"- Source commit: `{source['commit']}`",
        f"- Raw `/object_info` entries: {counts['rawNodeCount']}",
        f"- User-visible server nodes: {counts['userServerNodeCount']}",
        f"- Excluded only in this report: {counts['excludedNodeCount']} "
        f"(dev-only: {counts['devOnlyNodeCount']}, test: {counts['testNodeCount']})",
        f"- API nodes: {flags['api']}",
        f"- Experimental nodes: {flags['experimental']}",
        f"- Deprecated nodes: {flags['deprecated']}",
        f"- Dev-only nodes among user-visible set: {flags['devOnly']}",
        f"- Python modules: {counts['pythonModuleCount']}",
        "",
        "## Flag combinations",
        "",
    ]
    for key, value in report["userServerFlagCombinations"].items():
        lines.append(f"- `{key}`: {value}")
    lines.extend(["", "## Exclusion policy", ""])
    lines.append(
        "The checked-in object_info file is unfiltered. This derived report excludes entries "
        "with `dev_only = true` and test fixtures identified by an explicit test flag, a tests "
        "module namespace, or a test-only runtime/display identifier."
    )
    lines.extend(["", "## Largest Python modules", ""])
    for item in report["pythonModules"][:25]:
        lines.append(f"- `{item['module']}`: {item['nodeCount']}")
    return "\n".join(lines) + "\n"


def validate_backend_inventory_artifacts(metadata_path: Path, errors: list[str]) -> None:
    label = metadata_path.relative_to(ROOT).as_posix()
    try:
        metadata = load_json(metadata_path)
    except CatalogError as exc:
        errors.append(str(exc))
        return
    require(isinstance(metadata, Mapping), f"{label}: metadata must be an object", errors)
    if not isinstance(metadata, Mapping):
        return
    metadata_schema = load_json(CONTENT / "schemas" / "backend-inventory-metadata.schema.v1.json")
    if isinstance(metadata_schema, Mapping):
        errors.extend(f"{label}: {error}" for error in json_schema_errors(metadata, metadata_schema))
    source = metadata.get("source")
    capture = metadata.get("capture")
    require(isinstance(source, Mapping), f"{label}.source must be an object", errors)
    require(isinstance(capture, Mapping), f"{label}.capture must be an object", errors)
    if isinstance(source, Mapping):
        require(source.get("repository") == "https://github.com/Comfy-Org/ComfyUI", f"{label}: source repository must be official ComfyUI", errors)
        require(isinstance(source.get("commit"), str) and re.fullmatch(r"[a-f0-9]{40}", source["commit"]) is not None, f"{label}: invalid source commit", errors)
        require_string(source.get("backendVersion"), f"{label}.source.backendVersion", errors)
    require(metadata.get("schemaVersion") == "1.0", f"{label}: schemaVersion must be 1.0", errors)

    loaded_snapshot: Any = None
    for field in ("snapshot", "replacements"):
        artifact = metadata.get(field)
        require(isinstance(artifact, Mapping), f"{label}.{field} must be an object", errors)
        if not isinstance(artifact, Mapping):
            continue
        try:
            path = relative_content_path(metadata_path.parent, artifact.get("path"), f"{label}.{field}.path")
        except CatalogError as exc:
            errors.append(str(exc))
            continue
        require(path.exists(), f"{label}: missing {field} artifact {path}", errors)
        if not path.exists():
            continue
        require(path.stat().st_size == artifact.get("size"), f"{label}.{field}: size mismatch", errors)
        require(sha256_file(path) == artifact.get("sha256"), f"{label}.{field}: SHA-256 mismatch", errors)
        if field == "snapshot":
            try:
                loaded_snapshot = load_json(path)
            except CatalogError as exc:
                errors.append(str(exc))

    if loaded_snapshot is not None and isinstance(capture, Mapping):
        require(isinstance(loaded_snapshot, Mapping), f"{label}: snapshot must contain an object", errors)
        if isinstance(loaded_snapshot, Mapping):
            require(len(loaded_snapshot) == capture.get("endpointNodeCount"), f"{label}: endpoint node count mismatch", errors)
            require(capture.get("nodeClassMappingCount") == capture.get("endpointNodeCount"), f"{label}: NODE_CLASS_MAPPINGS and endpoint counts differ", errors)
            report = backend_inventory_report(loaded_snapshot, metadata)
            report_path = metadata_path.with_name(metadata_path.name.replace(".object-info.meta.json", ".inventory-report.json"))
            markdown_path = report_path.with_suffix(".md")
            require(report_path.exists(), f"{label}: missing checked-in inventory report {report_path}", errors)
            require(markdown_path.exists(), f"{label}: missing checked-in inventory report {markdown_path}", errors)
            if report_path.exists():
                try:
                    checked_report = load_json(report_path)
                    require(checked_report == report, f"{label}: checked-in inventory report is stale", errors)
                    report_schema = load_json(CONTENT / "schemas" / "backend-inventory-report.schema.v1.json")
                    if isinstance(report_schema, Mapping):
                        errors.extend(
                            f"{report_path.relative_to(ROOT).as_posix()}: {error}"
                            for error in json_schema_errors(checked_report, report_schema)
                        )
                except CatalogError as exc:
                    errors.append(str(exc))
            if markdown_path.exists():
                require(markdown_path.read_text(encoding="utf-8") == backend_inventory_markdown(report), f"{label}: checked-in inventory Markdown is stale", errors)


def parse_frontend_inventory(payload: Any, label: str = "frontend inventory") -> dict[str, Any]:
    """Validate and normalize a versioned inventory of frontend-only node types."""

    errors: list[str] = []
    keys = {"$schema", "schemaVersion", "source", "frontendVersion", "capturedAt", "nodes"}
    require_exact_keys(payload, keys, keys, label, errors)
    if not isinstance(payload, Mapping):
        raise CatalogError(f"invalid {label}: expected an object")
    schema_ref = payload.get("$schema")
    require(
        isinstance(schema_ref, str) and schema_ref.endswith("frontend-inventory.schema.v1.json"),
        f"{label}.$schema must reference frontend-inventory.schema.v1.json",
        errors,
    )
    require(payload.get("schemaVersion") == "1.0", f"{label}.schemaVersion must be 1.0", errors)
    require_string(payload.get("source"), f"{label}.source", errors, 3)
    require_string(payload.get("frontendVersion"), f"{label}.frontendVersion", errors)
    require(is_datetime(payload.get("capturedAt")), f"{label}.capturedAt must be a timezone-aware timestamp", errors)
    raw_nodes = payload.get("nodes")
    require(isinstance(raw_nodes, list), f"{label}.nodes must be an array", errors)
    nodes: dict[str, dict[str, Any]] = {}
    seen: set[str] = set()
    if isinstance(raw_nodes, list):
        for index, raw_node in enumerate(raw_nodes):
            node_label = f"{label}.nodes[{index}]"
            require_exact_keys(raw_node, {"classType", "packageId", "dev_only"}, {"classType"}, node_label, errors)
            if not isinstance(raw_node, Mapping):
                continue
            class_type = raw_node.get("classType")
            require(
                isinstance(class_type, str) and IDENTIFIER_RE.fullmatch(class_type) is not None,
                f"{node_label}.classType is not a runtime identifier",
                errors,
            )
            if not isinstance(class_type, str):
                continue
            require(class_type not in seen, f"{label}: duplicate classType {class_type!r}", errors)
            seen.add(class_type)
            package_id = raw_node.get("packageId")
            require(package_id is None or isinstance(package_id, str) and bool(package_id.strip()), f"{node_label}.packageId must be a non-empty string", errors)
            require("dev_only" not in raw_node or isinstance(raw_node.get("dev_only"), bool), f"{node_label}.dev_only must be boolean", errors)
            if not bool(raw_node.get("dev_only", False)):
                nodes[class_type] = {
                    "classType": class_type,
                    **({"packageId": package_id} if isinstance(package_id, str) else {}),
                }
    if errors:
        raise CatalogError(f"invalid {label}:\n" + "\n".join(f"- {error}" for error in errors))
    return {
        "schemaVersion": payload["schemaVersion"],
        "source": payload["source"],
        "frontendVersion": payload["frontendVersion"],
        "capturedAt": payload["capturedAt"],
        "nodes": dict(sorted(nodes.items())),
    }


def extract_replacements(payload: Any) -> dict[str, str]:
    replacements: dict[str, str] = {}

    def visit(value: Any) -> None:
        if isinstance(value, Mapping):
            old = value.get("old_node_id") or value.get("oldNodeId") or value.get("old")
            new = value.get("new_node_id") or value.get("newNodeId") or value.get("new")
            if isinstance(old, str) and isinstance(new, str):
                replacements[old] = new
            else:
                for child in value.values():
                    visit(child)
        elif isinstance(value, list):
            for child in value:
                visit(child)

    visit(payload)
    return dict(sorted(replacements.items()))


def load_source_catalog(path: Path = CATALOG_MANIFEST) -> tuple[dict[str, Any], list[tuple[Path, dict[str, Any]]], list[tuple[Path, dict[str, Any]]], list[tuple[Path, dict[str, Any]]]]:
    catalog = load_json(path)
    if not isinstance(catalog, dict):
        raise CatalogError("catalog.manifest.json must contain an object")
    base = path.parent
    articles: list[tuple[Path, dict[str, Any]]] = []
    recipes: list[tuple[Path, dict[str, Any]]] = []
    workflows: list[tuple[Path, dict[str, Any]]] = []
    for key, target in (("articles", articles), ("recipes", recipes), ("workflows", workflows)):
        values = catalog.get(key)
        if not isinstance(values, list):
            raise CatalogError(f"catalog.{key} must be an array")
        for index, value in enumerate(values):
            item_path = relative_content_path(base, value, f"catalog.{key}[{index}]")
            item = load_json(item_path)
            if not isinstance(item, dict):
                raise CatalogError(f"{item_path} must contain an object")
            target.append((item_path, item))
    return catalog, articles, recipes, workflows


def discovered_catalog_members() -> dict[str, list[str]]:
    """Return every source item that belongs to the checked-in catalog.

    The top-level manifest remains explicit and reviewable, while this scan
    prevents a newly researched article from silently sitting outside it.
    """

    patterns = {
        "articles": (CONTENT / "articles", "manifest.json"),
        "recipes": (CONTENT / "recipes", "recipe.json"),
        "workflows": (CONTENT / "workflows", "*.workflow.json"),
    }
    result: dict[str, list[str]] = {}
    for key, (base, pattern) in patterns.items():
        paths = [] if not base.exists() else [path for path in base.rglob(pattern) if path.is_file()]
        result[key] = sorted(path.relative_to(CONTENT).as_posix() for path in paths)
    return result


def catalog_membership_errors(catalog: Mapping[str, Any]) -> list[str]:
    errors: list[str] = []
    discovered = discovered_catalog_members()
    for key in ("articles", "recipes", "workflows"):
        declared = catalog.get(key)
        if not isinstance(declared, list) or not all(isinstance(value, str) for value in declared):
            continue
        expected = discovered[key]
        if declared == expected:
            continue
        missing = sorted(set(expected) - set(declared))
        stale = sorted(set(declared) - set(expected))
        if missing:
            errors.append(f"catalog.{key} omits discovered source files: {missing!r}")
        if stale:
            errors.append(f"catalog.{key} references absent source files: {stale!r}")
        if not missing and not stale:
            errors.append(f"catalog.{key} must use deterministic sorted order")
    return errors


def sync_catalog_manifest(check: bool = False) -> bool:
    catalog = load_json(CATALOG_MANIFEST)
    if not isinstance(catalog, dict):
        raise CatalogError("catalog.manifest.json must contain an object")
    updated = copy.deepcopy(catalog)
    updated.update(discovered_catalog_members())
    rendered = json.dumps(updated, ensure_ascii=False, indent=2) + "\n"
    current = CATALOG_MANIFEST.read_text(encoding="utf-8")
    if current == rendered:
        return True
    if check:
        return False
    CATALOG_MANIFEST.write_text(rendered, encoding="utf-8", newline="\n")
    return True


def validate_article(path: Path, article: dict[str, Any], errors: list[str]) -> None:
    label = path.relative_to(ROOT).as_posix()
    required = {
        "$schema", "schemaVersion", "articleId", "kind", "locale", "title", "summary", "body",
        "runtimeIdentity", "status", "experimental", "compatibility", "relations", "tags", "searchAliases",
        "concepts", "assets", "editorial", "sources",
    }
    require_exact_keys(article, required, required, label, errors)
    article_id = article.get("articleId")
    require(isinstance(article_id, str) and ARTICLE_ID_RE.fullmatch(article_id) is not None, f"{label}: invalid articleId", errors)
    require(article.get("schemaVersion") == "1.0", f"{label}: schemaVersion must be 1.0", errors)
    require(article.get("kind") in ARTICLE_KINDS, f"{label}: invalid kind", errors)
    require(article.get("status") in ARTICLE_STATUSES, f"{label}: invalid status", errors)
    require(isinstance(article.get("experimental"), bool), f"{label}: experimental must be boolean", errors)
    require_string(article.get("title"), f"{label}.title", errors, 3)
    require_string(article.get("summary"), f"{label}.summary", errors, 20)
    require(isinstance(article.get("summary"), str) and len(article.get("summary", "")) <= 360, f"{label}: summary exceeds 360 characters", errors)
    require_string_list(article.get("tags"), f"{label}.tags", errors, 2)
    require_string_list(article.get("searchAliases"), f"{label}.searchAliases", errors)
    require_string_list(article.get("concepts"), f"{label}.concepts", errors, 1)

    body_value = article.get("body")
    try:
        body_path = relative_content_path(path.parent, body_value, f"{label}.body")
        require(body_path.suffix.lower() == ".md", f"{label}.body must point to Markdown", errors)
        require(body_path.exists(), f"{label}: missing body {body_path}", errors)
        if body_path.exists():
            body = body_path.read_text(encoding="utf-8")
            require(body.lstrip().startswith("# "), f"{label}: body must start with an H1", errors)
            require(len(body.strip()) >= 300, f"{label}: body is too short for an approved article", errors)
    except CatalogError as exc:
        errors.append(str(exc))

    identity = article.get("runtimeIdentity")
    require(isinstance(identity, Mapping), f"{label}.runtimeIdentity must be an object", errors)
    if isinstance(identity, Mapping):
        require_exact_keys(identity, {"classType", "pythonModule", "packageId", "origin", "aliases"}, {"classType", "origin", "aliases"}, f"{label}.runtimeIdentity", errors)
        require_string(identity.get("classType"), f"{label}.runtimeIdentity.classType", errors)
        require(identity.get("origin") in ORIGINS, f"{label}: invalid runtime origin", errors)
        aliases = identity.get("aliases")
        require_string_list(aliases, f"{label}.runtimeIdentity.aliases", errors)
        if isinstance(aliases, list):
            for alias in aliases:
                require(bool(IDENTIFIER_RE.fullmatch(alias)), f"{label}: runtime alias is not an execution class_type: {alias!r}", errors)
        if identity.get("origin") == "backend":
            require_string(identity.get("pythonModule"), f"{label}.runtimeIdentity.pythonModule", errors)

    compatibility = article.get("compatibility")
    require(isinstance(compatibility, Mapping), f"{label}.compatibility must be an object", errors)
    if isinstance(compatibility, Mapping):
        require_exact_keys(compatibility, {"comfyui", "frontend", "since", "until", "verifiedOn", "sourceRevision"}, {"verifiedOn", "sourceRevision"}, f"{label}.compatibility", errors)
        require(is_date(compatibility.get("verifiedOn")), f"{label}: invalid compatibility.verifiedOn", errors)
        require_string(compatibility.get("sourceRevision"), f"{label}.compatibility.sourceRevision", errors)

    relations = article.get("relations")
    require(isinstance(relations, Mapping), f"{label}.relations must be an object", errors)
    if isinstance(relations, Mapping):
        require_exact_keys(relations, {"related", "alternatives", "replacedBy"}, {"related", "alternatives", "replacedBy"}, f"{label}.relations", errors)
        require_string_list(relations.get("related"), f"{label}.relations.related", errors)
        require_string_list(relations.get("alternatives"), f"{label}.relations.alternatives", errors)
        replaced_by = relations.get("replacedBy")
        require(replaced_by is None or isinstance(replaced_by, str), f"{label}.relations.replacedBy must be string or null", errors)

    editorial = article.get("editorial")
    require(isinstance(editorial, Mapping), f"{label}.editorial must be an object", errors)
    if isinstance(editorial, Mapping):
        require_exact_keys(editorial, {"state", "owner", "reviewedBy", "reviewedAt", "factsReviewedAt", "schemaHash"}, {"state", "owner", "reviewedBy", "reviewedAt", "factsReviewedAt"}, f"{label}.editorial", errors)
        state = editorial.get("state")
        require(state in EDITORIAL_STATES, f"{label}: invalid editorial state", errors)
        if article.get("status") != "draft":
            require(state == "approved", f"{label}: published article must be approved", errors)
        require_string(editorial.get("owner"), f"{label}.editorial.owner", errors, 2)
        require_string(editorial.get("reviewedBy"), f"{label}.editorial.reviewedBy", errors, 2)
        require(is_date(editorial.get("reviewedAt")), f"{label}: invalid editorial.reviewedAt", errors)
        require(is_date(editorial.get("factsReviewedAt")), f"{label}: invalid editorial.factsReviewedAt", errors)
        schema_hash = editorial.get("schemaHash")
        require(schema_hash is None or isinstance(schema_hash, str) and SHA256_RE.fullmatch(schema_hash) is not None, f"{label}: invalid editorial.schemaHash", errors)

    sources = article.get("sources")
    require(isinstance(sources, list) and bool(sources), f"{label}.sources must not be empty", errors)
    if isinstance(sources, list):
        source_ids: set[str] = set()
        for index, source in enumerate(sources):
            source_label = f"{label}.sources[{index}]"
            require(isinstance(source, Mapping), f"{source_label} must be an object", errors)
            if not isinstance(source, Mapping):
                continue
            require_exact_keys(source, {"sourceId", "title", "url", "publisher", "kind", "accessedAt", "supports"}, {"sourceId", "title", "url", "publisher", "kind", "accessedAt", "supports"}, source_label, errors)
            require_string(source.get("sourceId"), f"{source_label}.sourceId", errors)
            if isinstance(source.get("sourceId"), str):
                require(source["sourceId"] not in source_ids, f"{label}: duplicate sourceId {source['sourceId']!r}", errors)
                source_ids.add(source["sourceId"])
            require_string(source.get("title"), f"{source_label}.title", errors, 3)
            require(isinstance(source.get("url"), str) and source["url"].startswith("https://"), f"{source_label}.url must be HTTPS", errors)
            require_string(source.get("publisher"), f"{source_label}.publisher", errors, 2)
            require(is_date(source.get("accessedAt")), f"{source_label}.accessedAt must be a date", errors)
            require_string_list(source.get("supports"), f"{source_label}.supports", errors, 1)


def validate_recipe(path: Path, recipe: dict[str, Any], article_ids: set[str], errors: list[str]) -> None:
    label = path.relative_to(ROOT).as_posix()
    required = {"schemaVersion", "recipeId", "locale", "title", "summary", "body", "difficulty", "articleIds", "requirements", "fragment", "editorial", "sources"}
    allowed = required | {"$schema", "workflow"}
    require_exact_keys(recipe, allowed, required, label, errors)
    require(isinstance(recipe.get("recipeId"), str) and recipe["recipeId"].startswith("recipe."), f"{label}: invalid recipeId", errors)
    require_string_list(recipe.get("articleIds"), f"{label}.articleIds", errors, 1)
    if isinstance(recipe.get("articleIds"), list):
        for article_id in recipe["articleIds"]:
            require(article_id in article_ids, f"{label}: unknown articleId {article_id!r}", errors)
    for field in ("body",):
        try:
            target = relative_content_path(path.parent, recipe.get(field), f"{label}.{field}")
            require(target.exists(), f"{label}: missing {field} file {target}", errors)
        except CatalogError as exc:
            errors.append(str(exc))
    references: list[tuple[str, Any]] = [("fragment", recipe.get("fragment"))]
    if recipe.get("workflow") is not None:
        references.append(("workflow", recipe.get("workflow")))
    for field, ref in references:
        require(isinstance(ref, Mapping), f"{label}.{field} must be an object", errors)
        if isinstance(ref, Mapping):
            try:
                target = relative_content_path(path.parent, ref.get("path"), f"{label}.{field}.path")
                require(target.exists(), f"{label}: missing {field} file {target}", errors)
                if target.exists():
                    payload = load_json(target)
                    if field == "fragment" and isinstance(payload, dict):
                        validate_fragment(target, payload, errors)
            except CatalogError as exc:
                errors.append(str(exc))
    editorial = recipe.get("editorial")
    require(isinstance(editorial, Mapping), f"{label}.editorial must be an object", errors)
    if isinstance(editorial, Mapping):
        require_exact_keys(editorial, {"state", "reviewedBy", "reviewedAt"}, {"state", "reviewedBy", "reviewedAt"}, f"{label}.editorial", errors)
        require(editorial.get("state") in EDITORIAL_STATES, f"{label}: invalid recipe editorial state", errors)
        require_string(editorial.get("reviewedBy"), f"{label}.editorial.reviewedBy", errors, 2)
        require(is_date(editorial.get("reviewedAt")), f"{label}: invalid recipe editorial.reviewedAt", errors)
    sources = recipe.get("sources")
    require(isinstance(sources, list) and bool(sources), f"{label}: recipe sources must not be empty", errors)


def validate_fragment(path: Path, fragment: dict[str, Any], errors: list[str]) -> None:
    label = path.relative_to(ROOT).as_posix()
    allowed = {"$schema", "schemaVersion", "fragmentId", "title", "externalInputs", "nodes", "connections"}
    require_exact_keys(fragment, allowed, allowed, label, errors)
    require(fragment.get("schemaVersion") == "1.0", f"{label}: schemaVersion must be 1.0", errors)
    refs: set[str] = set()
    nodes = fragment.get("nodes")
    require(isinstance(nodes, list) and bool(nodes), f"{label}: nodes must not be empty", errors)
    if isinstance(nodes, list):
        for index, node in enumerate(nodes):
            node_label = f"{label}.nodes[{index}]"
            require_exact_keys(node, {"ref", "classType", "role", "settings"}, {"ref", "classType", "role", "settings"}, node_label, errors)
            if isinstance(node, Mapping):
                ref = node.get("ref")
                require(isinstance(ref, str) and ref not in refs, f"{node_label}: duplicate or invalid ref", errors)
                if isinstance(ref, str):
                    refs.add(ref)
                require_string(node.get("classType"), f"{node_label}.classType", errors)
                require(isinstance(node.get("settings"), Mapping), f"{node_label}.settings must be an object", errors)
    external_ids: set[str] = set()
    externals = fragment.get("externalInputs")
    require(isinstance(externals, list), f"{label}.externalInputs must be an array", errors)
    if isinstance(externals, list):
        for index, item in enumerate(externals):
            item_label = f"{label}.externalInputs[{index}]"
            require_exact_keys(item, {"id", "type", "to", "input"}, {"id", "type", "to", "input"}, item_label, errors)
            if isinstance(item, Mapping):
                require(item.get("id") not in external_ids, f"{item_label}: duplicate external id", errors)
                if isinstance(item.get("id"), str):
                    external_ids.add(item["id"])
                require(item.get("to") in refs, f"{item_label}: unknown target ref {item.get('to')!r}", errors)
    connections = fragment.get("connections")
    require(isinstance(connections, list), f"{label}.connections must be an array", errors)
    seen_connections: set[tuple[Any, Any, Any, Any]] = set()
    if isinstance(connections, list):
        for index, item in enumerate(connections):
            item_label = f"{label}.connections[{index}]"
            require_exact_keys(item, {"from", "output", "to", "input"}, {"from", "output", "to", "input"}, item_label, errors)
            if isinstance(item, Mapping):
                require(item.get("from") in refs and item.get("to") in refs, f"{item_label}: connection references unknown node", errors)
                key = (item.get("from"), item.get("output"), item.get("to"), item.get("input"))
                require(key not in seen_connections, f"{item_label}: duplicate connection", errors)
                seen_connections.add(key)


def validate_update_manifest(path: Path, errors: list[str]) -> None:
    label = path.relative_to(ROOT).as_posix()
    try:
        manifest = load_json(path)
    except CatalogError as exc:
        errors.append(str(exc))
        return
    allowed = {"$schema", "schemaVersion", "catalogVersion", "publishedAt", "canonicalization", "signatureScope", "compatibility", "inventory", "artifacts", "changes", "signature"}
    require_exact_keys(manifest, allowed, allowed, label, errors)
    require(manifest.get("canonicalization") == "comfy-nodes-wizard-json-v1", f"{label}: unsupported canonicalization", errors)
    require(manifest.get("signatureScope") == "top-level-manifest-excluding-signature", f"{label}: unsupported signature scope", errors)
    artifacts = manifest.get("artifacts")
    require(isinstance(artifacts, list) and bool(artifacts), f"{label}: artifacts must not be empty", errors)
    paths: set[str] = set()
    if isinstance(artifacts, list):
        for index, artifact in enumerate(artifacts):
            item_label = f"{label}.artifacts[{index}]"
            keys = {"path", "sha256", "size", "url", "contentType"}
            require_exact_keys(artifact, keys, keys, item_label, errors)
            if isinstance(artifact, Mapping):
                artifact_path = artifact.get("path")
                require(isinstance(artifact_path, str) and artifact_path not in paths, f"{item_label}: duplicate or invalid path", errors)
                if isinstance(artifact_path, str):
                    paths.add(artifact_path)
                require(isinstance(artifact.get("sha256"), str) and re.fullmatch(r"[a-f0-9]{64}", artifact["sha256"]) is not None, f"{item_label}: invalid sha256", errors)
                require(isinstance(artifact.get("size"), int) and artifact["size"] >= 0, f"{item_label}: invalid size", errors)
                require(isinstance(artifact.get("url"), str) and artifact["url"].startswith("https://"), f"{item_label}: URL must use HTTPS", errors)
    changes = manifest.get("changes")
    if isinstance(changes, Mapping):
        require_exact_keys(changes, {"summary", "added", "updated", "deprecated", "removed"}, {"summary", "added", "updated", "deprecated", "removed"}, f"{label}.changes", errors)
        require_string(changes.get("summary"), f"{label}.changes.summary", errors, 20)
        for key in ("added", "updated", "deprecated", "removed"):
            require_string_list(changes.get(key), f"{label}.changes.{key}", errors)
    else:
        errors.append(f"{label}.changes must be an object")


def validate_schema_sources(errors: list[str]) -> None:
    ids: set[str] = set()
    for path in sorted((CONTENT / "schemas").glob("*.json")):
        label = path.relative_to(ROOT).as_posix()
        try:
            schema = load_json(path)
        except CatalogError as exc:
            errors.append(str(exc))
            continue
        require(isinstance(schema, Mapping), f"{label}: schema must be an object", errors)
        if not isinstance(schema, Mapping):
            continue
        require(schema.get("$schema") == "https://json-schema.org/draft/2020-12/schema", f"{label}: schemas must use JSON Schema 2020-12", errors)
        schema_id = schema.get("$id")
        require(isinstance(schema_id, str) and schema_id not in ids, f"{label}: missing or duplicate $id", errors)
        if isinstance(schema_id, str):
            ids.add(schema_id)


def validate_frontend_inventory_sources(errors: list[str]) -> None:
    # Validate both intentionally small test fixtures and checked-in release
    # inventories.  A non-sample inventory is the evidence accepted by the
    # stable release gate; silently skipping it here would defeat that contract.
    for path in sorted((CONTENT / "runtime").glob("*.frontend-inventory*.json")):
        try:
            parse_frontend_inventory(load_json(path), path.relative_to(ROOT).as_posix())
        except CatalogError as exc:
            errors.append(str(exc))


def validate_backend_inventory_sources(errors: list[str]) -> None:
    for path in sorted((CONTENT / "runtime").glob("*.object-info.meta.json")):
        validate_backend_inventory_artifacts(path, errors)


def validate_runtime_namespace(canonical_class_types: Mapping[str, str], runtime_aliases: Mapping[str, str], errors: list[str]) -> None:
    """Reject aliases that could resolve to another article's canonical type."""

    for alias, alias_article_id in runtime_aliases.items():
        canonical_article_id = canonical_class_types.get(alias)
        require(
            canonical_article_id is None,
            f"runtime alias {alias!r} for {alias_article_id!r} collides with canonical classType of {canonical_article_id!r}",
            errors,
        )


def validate_workflow(path: Path, workflow: dict[str, Any], errors: list[str]) -> None:
    label = path.relative_to(ROOT).as_posix()
    nodes = workflow.get("nodes")
    links = workflow.get("links")
    require(isinstance(nodes, list) and bool(nodes), f"{label}: workflow.nodes must not be empty", errors)
    require(isinstance(links, list), f"{label}: workflow.links must be an array", errors)
    require(isinstance(workflow.get("version"), (int, float, str)), f"{label}: missing workflow version", errors)
    if not isinstance(nodes, list):
        return
    node_ids: set[Any] = set()
    node_types: set[str] = set()
    for index, node in enumerate(nodes):
        require(isinstance(node, Mapping), f"{label}.nodes[{index}] must be an object", errors)
        if not isinstance(node, Mapping):
            continue
        node_id = node.get("id")
        require(node_id not in node_ids, f"{label}: duplicate workflow node id {node_id!r}", errors)
        node_ids.add(node_id)
        require_string(node.get("type"), f"{label}.nodes[{index}].type", errors)
        if isinstance(node.get("type"), str):
            node_types.add(node["type"])
    if isinstance(links, list):
        link_ids: set[Any] = set()
        for index, link in enumerate(links):
            require(isinstance(link, list) and len(link) >= 6, f"{label}.links[{index}] must be a six-field link", errors)
            if isinstance(link, list) and len(link) >= 6:
                require(link[0] not in link_ids, f"{label}: duplicate link id {link[0]!r}", errors)
                link_ids.add(link[0])
                require(link[1] in node_ids and link[3] in node_ids, f"{label}: link {link[0]!r} references an unknown node", errors)


def validate_catalog_manifest(catalog: Mapping[str, Any], errors: list[str]) -> None:
    """Validate source-catalog metadata without imposing stable-release policy."""

    label = "content/catalog.manifest.json"
    keys = {
        "$schema", "schemaVersion", "catalogVersion", "locale", "generatedAt", "release",
        "articles", "recipes", "workflows",
    }
    require_exact_keys(catalog, keys, keys, label, errors)
    require(catalog.get("schemaVersion") == "1.0", "catalog schemaVersion must be 1.0", errors)
    require(
        isinstance(catalog.get("catalogVersion"), str)
        and re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+", catalog["catalogVersion"]) is not None,
        "catalogVersion must be a semantic version",
        errors,
    )
    require(isinstance(catalog.get("locale"), str), "catalog locale must be a string", errors)
    require(is_datetime(catalog.get("generatedAt")), "catalog generatedAt must be a timezone-aware timestamp", errors)
    require_string_list(catalog.get("articles"), "catalog.articles", errors, 1)
    require_string_list(catalog.get("recipes"), "catalog.recipes", errors)
    require_string_list(catalog.get("workflows"), "catalog.workflows", errors)

    release = catalog.get("release")
    require(isinstance(release, Mapping), "catalog.release must be an object", errors)
    if not isinstance(release, Mapping):
        return
    require_exact_keys(release, {"channel", "humanApproval"}, {"channel", "humanApproval"}, "catalog.release", errors)
    require(release.get("channel") in {"alpha", "beta", "stable"}, "catalog.release.channel is invalid", errors)
    approval = release.get("humanApproval")
    require(isinstance(approval, Mapping), "catalog.release.humanApproval must be an object", errors)
    if not isinstance(approval, Mapping):
        return
    approval_keys = {"state", "approvedBy", "approvedAt", "note"}
    require_exact_keys(approval, approval_keys, approval_keys, "catalog.release.humanApproval", errors)
    require(approval.get("state") in {"pending", "approved", "rejected"}, "catalog.release.humanApproval.state is invalid", errors)
    approved_by = approval.get("approvedBy")
    require(approved_by is None or isinstance(approved_by, str) and len(approved_by.strip()) >= 2, "catalog.release.humanApproval.approvedBy must be null or a reviewer name", errors)
    approved_at = approval.get("approvedAt")
    require(approved_at is None or is_datetime(approved_at), "catalog.release.humanApproval.approvedAt must be null or a timezone-aware timestamp", errors)
    note = approval.get("note")
    require(isinstance(note, str) and 10 <= len(note.strip()) <= 500, "catalog.release.humanApproval.note must contain 10-500 characters", errors)


def validate_catalog(path: Path = CATALOG_MANIFEST) -> list[str]:
    errors: list[str] = []
    validate_schema_sources(errors)
    validate_frontend_inventory_sources(errors)
    validate_backend_inventory_sources(errors)
    validate_update_manifest(CONTENT / "update-manifest.json", errors)
    try:
        catalog, articles, recipes, workflows = load_source_catalog(path)
        if path.resolve() == CATALOG_MANIFEST.resolve():
            errors.extend(catalog_membership_errors(catalog))
    except CatalogError as exc:
        return [str(exc)]
    validate_catalog_manifest(catalog, errors)
    article_ids: set[str] = set()
    runtime_keys: dict[tuple[str, str | None, str], str] = {}
    runtime_aliases: dict[str, str] = {}
    canonical_class_types: dict[str, str] = {}
    source_ids: dict[str, str] = {}
    for article_path, article in articles:
        validate_article(article_path, article, errors)
        article_id = article.get("articleId")
        if isinstance(article_id, str):
            require(article_id not in article_ids, f"duplicate articleId {article_id!r}", errors)
            article_ids.add(article_id)
        identity = article.get("runtimeIdentity")
        if isinstance(identity, Mapping) and isinstance(identity.get("classType"), str):
            key = (str(identity.get("origin")), identity.get("pythonModule") if isinstance(identity.get("pythonModule"), str) else None, identity["classType"])
            require(key not in runtime_keys, f"runtime identity {key!r} is shared by {runtime_keys.get(key)!r} and {article_id!r}", errors)
            runtime_keys[key] = str(article_id)
            class_type = identity["classType"]
            prior_canonical = canonical_class_types.get(class_type)
            require(prior_canonical is None or prior_canonical == article_id, f"canonical classType {class_type!r} is shared by {prior_canonical!r} and {article_id!r}", errors)
            canonical_class_types[class_type] = str(article_id)
            for alias in identity.get("aliases", []):
                require(alias not in runtime_aliases, f"runtime alias {alias!r} is shared by {runtime_aliases.get(alias)!r} and {article_id!r}", errors)
                require(alias != identity["classType"], f"{article_id}: runtime alias duplicates classType", errors)
                runtime_aliases[alias] = str(article_id)
        for source in article.get("sources", []):
            if isinstance(source, Mapping) and isinstance(source.get("sourceId"), str):
                prior_url = source_ids.get(source["sourceId"])
                require(prior_url is None or prior_url == source.get("url"), f"sourceId {source['sourceId']!r} maps to multiple URLs", errors)
                source_ids[source["sourceId"]] = str(source.get("url"))
    validate_article_research_records(articles, errors)

    validate_runtime_namespace(canonical_class_types, runtime_aliases, errors)

    for article_path, article in articles:
        relations = article.get("relations", {})
        if not isinstance(relations, Mapping):
            continue
        targets = list(relations.get("related", [])) + list(relations.get("alternatives", []))
        if isinstance(relations.get("replacedBy"), str):
            targets.append(relations["replacedBy"])
        for target in targets:
            require(target in article_ids, f"{article.get('articleId')}: relation points to unknown article {target!r}", errors)
            require(target != article.get("articleId"), f"{article.get('articleId')}: relation points to itself", errors)

    recipe_ids: set[str] = set()
    for recipe_path, recipe in recipes:
        validate_recipe(recipe_path, recipe, article_ids, errors)
        recipe_id = recipe.get("recipeId")
        if isinstance(recipe_id, str):
            require(recipe_id not in recipe_ids, f"duplicate recipeId {recipe_id!r}", errors)
            recipe_ids.add(recipe_id)
    for article_path, article in articles:
        for asset in article.get("assets", []):
            if isinstance(asset, Mapping) and asset.get("type") == "recipe":
                require(asset.get("id") in recipe_ids, f"{article.get('articleId')}: unknown recipe asset {asset.get('id')!r}", errors)
    for workflow_path, workflow in workflows:
        validate_workflow(workflow_path, workflow, errors)
    return errors


def _relations_for_compiled(relations: Mapping[str, Any]) -> list[dict[str, str]]:
    result: list[dict[str, str]] = []
    for target in relations.get("related", []):
        result.append({"type": "related", "articleId": target})
    for target in relations.get("alternatives", []):
        result.append({"type": "alternative", "articleId": target})
    if isinstance(relations.get("replacedBy"), str):
        result.append({"type": "replacedBy", "articleId": relations["replacedBy"]})
    return result


def compile_workflow_assets(article_path: Path, article: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Load workflow assets independently of recipe attachments."""

    compiled: list[dict[str, Any]] = []
    for asset in article.get("assets", []):
        if not isinstance(asset, Mapping) or asset.get("type") != "workflow":
            continue
        if not isinstance(asset.get("path"), str):
            raise CatalogError(f"workflow asset {asset.get('id')!r} has no path")
        workflow = load_json(relative_content_path(article_path.parent, asset["path"], f"{article_path}.assets.workflow.path"))
        if not isinstance(workflow, dict):
            raise CatalogError(f"workflow asset {asset.get('id')!r} must contain an object")
        compiled.append(workflow)
    return compiled


def compile_recipe(recipe_path: Path, recipe: Mapping[str, Any]) -> dict[str, Any]:
    """Inline a recipe's mandatory fragment and its optional full workflow."""

    compiled_recipe = copy.deepcopy(dict(recipe))
    body_path = relative_content_path(recipe_path.parent, recipe["body"], f"{recipe_path}.body")
    compiled_recipe["body"] = body_path.read_text(encoding="utf-8")
    fragment_ref = recipe["fragment"]
    compiled_recipe["fragmentData"] = load_json(
        relative_content_path(
            recipe_path.parent,
            fragment_ref["path"],
            f"{recipe_path}.fragment.path",
        )
    )
    workflow_ref = recipe.get("workflow")
    if isinstance(workflow_ref, Mapping):
        compiled_recipe["workflowData"] = load_json(
            relative_content_path(
                recipe_path.parent,
                workflow_ref["path"],
                f"{recipe_path}.workflow.path",
            )
        )
    return compiled_recipe


def compile_catalog(path: Path = CATALOG_MANIFEST, inventory_path: Path | None = None) -> tuple[dict[str, Any], dict[str, Any]]:
    errors = validate_catalog(path)
    if errors:
        raise CatalogError("catalog validation failed:\n" + "\n".join(f"- {error}" for error in errors))
    catalog, articles, recipes, workflows = load_source_catalog(path)
    inventory: dict[str, Mapping[str, Any]] = {}
    if inventory_path is not None:
        inventory = object_info_nodes(load_json(inventory_path))
    else:
        default_inventory = CONTENT / "runtime" / "comfyui-0.32.0.object-info.json"
        if default_inventory.exists():
            inventory = object_info_nodes(load_json(default_inventory))

    recipe_data: dict[str, dict[str, Any]] = {}
    for recipe_path, recipe in recipes:
        recipe_data[recipe["recipeId"]] = compile_recipe(recipe_path, recipe)

    compiled_articles: list[dict[str, Any]] = []
    search_documents: list[dict[str, Any]] = []
    for article_path, article in articles:
        body_path = relative_content_path(article_path.parent, article["body"], f"{article_path}.body")
        identity = article["runtimeIdentity"]
        node_id = identity["classType"]
        schema_hash = schema_fingerprint(node_id, inventory[node_id]) if identity.get("origin") == "backend" and node_id in inventory else article["editorial"].get("schemaHash")
        compatibility = copy.deepcopy(article["compatibility"])
        compatibility["schemaFingerprint"] = schema_hash
        relation_array = _relations_for_compiled(article["relations"])
        recipe_ids = [asset["id"] for asset in article["assets"] if asset.get("type") == "recipe"]
        workflow_ids = [asset["id"] for asset in article["assets"] if asset.get("type") == "workflow"]
        public_manifest = {
            "articleId": article["articleId"],
            "kind": article["kind"],
            "locale": article["locale"],
            "node": {
                "packageId": identity.get("packageId"),
                "pythonModule": identity.get("pythonModule"),
                "nodeId": node_id,
                "kind": identity["origin"],
            },
            # Kept for the tolerant frontend decoder and context-menu lookup.
            "runtimeIdentity": copy.deepcopy(identity),
            "status": article["status"],
            "experimental": article["experimental"],
            "compatibility": compatibility,
            "relations": relation_array,
            "recipes": recipe_ids,
            "workflows": workflow_ids,
            "sources": copy.deepcopy(article["sources"]),
            "editorialState": article["editorial"]["state"],
            "editorial": copy.deepcopy(article["editorial"]),
            "searchAliases": copy.deepcopy(article["searchAliases"]),
            "assets": copy.deepcopy(article["assets"]),
        }
        item: dict[str, Any] = {
            "manifest": public_manifest,
            "title": article["title"],
            "summary": article["summary"],
            "tags": copy.deepcopy(article["tags"]),
            "concepts": copy.deepcopy(article["concepts"]),
            "body": body_path.read_text(encoding="utf-8"),
        }
        if recipe_ids:
            item["recipeData"] = [recipe_data[recipe_id] for recipe_id in recipe_ids]
        if workflow_ids:
            item["workflowData"] = compile_workflow_assets(article_path, article)
        compiled_articles.append(item)
        search_documents.append({
            "id": article["articleId"],
            "nodeId": node_id,
            "title": article["title"],
            "summary": article["summary"],
            "aliases": article["searchAliases"],
            "runtimeAliases": identity.get("aliases", []),
            "tags": article["tags"],
            "concepts": article["concepts"],
            "body": item["body"],
        })
    compiled_articles.sort(key=lambda item: item["manifest"]["articleId"])
    search_documents.sort(key=lambda item: item["id"])
    compiled = {
        "schemaVersion": catalog["schemaVersion"],
        "catalogVersion": catalog["catalogVersion"],
        "locale": catalog["locale"],
        "generatedAt": catalog["generatedAt"],
        "articles": compiled_articles,
    }
    search_index = {
        "schemaVersion": "1.0",
        "catalogVersion": catalog["catalogVersion"],
        "locale": catalog["locale"],
        "generatedAt": catalog["generatedAt"],
        "documents": search_documents,
    }
    contract_errors = validate_compiled_catalog_instance(compiled)
    if contract_errors:
        raise CatalogError(
            "compiled catalog violates content/schemas/compiled-catalog.schema.v1.json:\n"
            + "\n".join(f"- {error}" for error in contract_errors)
        )
    return compiled, search_index


def generated_text(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2, sort_keys=False, allow_nan=False) + "\n"


def deterministic_bundle(files: Mapping[str, bytes]) -> bytes:
    """Create byte-for-byte reproducible ZIP content."""

    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for name in sorted(files):
            info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.create_system = 3
            info.external_attr = 0o100644 << 16
            archive.writestr(info, files[name])
    return output.getvalue()


def build(output_dir: Path, check: bool, inventory_path: Path | None = None) -> None:
    compiled, search_index = compile_catalog(inventory_path=inventory_path)
    text_artifacts = {
        "catalog.json": generated_text(compiled).encode("utf-8"),
        "search-index.json": generated_text(search_index).encode("utf-8"),
    }
    binary_artifacts = {
        **text_artifacts,
        "catalog-bundle.zip": deterministic_bundle(text_artifacts),
    }
    update = copy.deepcopy(load_json(CONTENT / "update-manifest.json"))
    update["signature"] = None
    for artifact in update.get("artifacts", []):
        name = Path(artifact["path"]).name
        if name not in binary_artifacts:
            raise CatalogError(f"update manifest references an unknown generated artifact: {name}")
        payload = binary_artifacts[name]
        artifact["sha256"] = hashlib.sha256(payload).hexdigest()
        artifact["size"] = len(payload)
    all_artifacts = {
        **binary_artifacts,
        "update-manifest.example.json": generated_text(update).encode("utf-8"),
    }
    if check:
        mismatches: list[str] = []
        for name, value in all_artifacts.items():
            target = output_dir / name
            actual = target.read_bytes() if target.exists() else None
            if actual != value:
                mismatches.append(str(target))
        if mismatches:
            raise CatalogError("generated artifacts are stale or missing: " + ", ".join(mismatches))
        return
    output_dir.mkdir(parents=True, exist_ok=True)
    for name, value in all_artifacts.items():
        (output_dir / name).write_bytes(value)


def diff_inventories(before: Mapping[str, Mapping[str, Any]], after: Mapping[str, Mapping[str, Any]], replacements: Mapping[str, str] | None = None) -> dict[str, Any]:
    before_ids = set(before)
    after_ids = set(after)
    replacements = replacements or {}
    changed: list[dict[str, str]] = []
    status_changed: list[dict[str, Any]] = []
    for node_id in sorted(before_ids & after_ids):
        old_hash = schema_fingerprint(node_id, before[node_id])
        new_hash = schema_fingerprint(node_id, after[node_id])
        if old_hash != new_hash:
            changed.append({"nodeId": node_id, "before": old_hash, "after": new_hash})
        for flag in ("deprecated", "experimental", "api_node"):
            old = bool(before[node_id].get(flag, False))
            new = bool(after[node_id].get(flag, False))
            if old != new:
                status_changed.append({"nodeId": node_id, "flag": flag, "before": old, "after": new})
    removed = []
    for node_id in sorted(before_ids - after_ids):
        item: dict[str, Any] = {"nodeId": node_id}
        if node_id in replacements:
            item["replacedBy"] = replacements[node_id]
        removed.append(item)
    return {
        "schemaVersion": "1.0",
        "added": sorted(after_ids - before_ids),
        "removed": removed,
        "changed": changed,
        "statusChanged": status_changed,
        "unchangedCount": len(before_ids & after_ids) - len(changed),
        "beforeCount": len(before_ids),
        "afterCount": len(after_ids),
    }


def catalog_coverage(nodes: Mapping[str, Mapping[str, Any]], replacements: Mapping[str, str] | None = None) -> dict[str, Any]:
    nodes = local_generation_nodes(nodes)
    _, articles, _, _ = load_source_catalog()
    backend_articles: dict[str, dict[str, Any]] = {}
    frontend_articles: list[str] = []
    stale: list[dict[str, str]] = []
    for _, article in articles:
        identity = article["runtimeIdentity"]
        if identity["origin"] == "backend":
            backend_articles[identity["classType"]] = article
        else:
            frontend_articles.append(article["articleId"])
    runtime_ids = set(nodes)
    covered_ids = runtime_ids & set(backend_articles)
    for node_id in sorted(covered_ids):
        expected = backend_articles[node_id]["editorial"].get("schemaHash")
        actual = schema_fingerprint(node_id, nodes[node_id])
        if isinstance(expected, str) and expected != "sha256:" + "0" * 64 and expected != actual:
            stale.append({"articleId": backend_articles[node_id]["articleId"], "nodeId": node_id, "expected": expected, "actual": actual})
    missing_runtime = sorted(set(backend_articles) - runtime_ids)
    return {
        "schemaVersion": "1.0",
        "runtimeNodeCount": len(runtime_ids),
        "backendArticleCount": len(backend_articles),
        "coveredNodeCount": len(covered_ids),
        "coverageRatio": round(len(covered_ids) / len(runtime_ids), 6) if runtime_ids else 1.0,
        "missingArticles": sorted(runtime_ids - set(backend_articles)),
        "articlesMissingRuntimeNode": [
            {
                "nodeId": node_id,
                "articleId": backend_articles[node_id]["articleId"],
                **({"replacedBy": replacements[node_id]} if replacements and node_id in replacements else {}),
            }
            for node_id in missing_runtime
        ],
        "staleArticles": stale,
        "frontendArticleIds": sorted(frontend_articles),
    }


def _runtime_article_status(node: Mapping[str, Any]) -> str:
    if bool(node.get("deprecated", False)):
        return "deprecated"
    if bool(node.get("experimental", False)):
        return "experimental"
    return "active"


def _example_validation_reasons(
    recipe_path: Path,
    recipe: Mapping[str, Any],
    article_ids: set[str],
) -> list[str]:
    """Validate the files behind a recipe and return stable-gate diagnostics."""

    recipe_id = str(recipe.get("recipeId", recipe_path.name))
    errors: list[str] = []
    if isinstance(recipe, dict):
        validate_recipe(recipe_path, recipe, article_ids, errors)
    else:
        errors.append(f"{recipe_path}: recipe must be an object")
    fields: list[tuple[str, Any]] = [("fragment", validate_fragment)]
    if recipe.get("workflow") is not None:
        fields.append(("workflow", validate_workflow))
    for field, validator in fields:
        reference = recipe.get(field)
        if not isinstance(reference, Mapping) or not isinstance(reference.get("path"), str):
            errors.append(f"{recipe_path}: {field} reference is incomplete")
            continue
        try:
            target = relative_content_path(recipe_path.parent, reference["path"], f"{recipe_path}.{field}.path")
            payload = load_json(target)
            if not isinstance(payload, dict):
                errors.append(f"{target}: {field} must contain an object")
                continue
            local_errors: list[str] = []
            validator(target, payload, local_errors)
            errors.extend(local_errors)
        except CatalogError as exc:
            errors.append(str(exc))
    return [f"broken example {recipe_id}: {error}" for error in errors]


def release_policy_reasons(
    catalog: Mapping[str, Any],
    articles: Sequence[tuple[Path, dict[str, Any]]],
    recipes: Sequence[tuple[Path, dict[str, Any]]],
    workflows: Sequence[tuple[Path, dict[str, Any]]],
    nodes: Mapping[str, Mapping[str, Any]],
    replacements: Mapping[str, str] | None = None,
    frontend_inventory: Mapping[str, Any] | None = None,
) -> list[str]:
    """Return deterministic reasons why this snapshot cannot ship as stable."""

    reasons: list[str] = []
    all_nodes = nodes
    nodes = local_generation_nodes(nodes)
    replacements = replacements or {}
    release = catalog.get("release")
    release = release if isinstance(release, Mapping) else {}
    channel = release.get("channel")
    if channel != "stable":
        reasons.append(f"release channel is {channel!r}; stable is required")
    approval = release.get("humanApproval")
    approval = approval if isinstance(approval, Mapping) else {}
    approval_state = approval.get("state")
    if approval_state == "pending":
        reasons.append("human approval pending: an accountable editor must approve the stable release")
    elif approval_state != "approved":
        reasons.append(f"human approval is {approval_state!r}; approved is required")
    if approval_state == "approved":
        if not isinstance(approval.get("approvedBy"), str) or len(approval["approvedBy"].strip()) < 2:
            reasons.append("human approval has no accountable approvedBy value")
        if not is_datetime(approval.get("approvedAt")):
            reasons.append("human approval has no valid timezone-aware approvedAt timestamp")

    article_ids = {
        article["articleId"]
        for _, article in articles
        if isinstance(article.get("articleId"), str)
    }
    backend_by_node: dict[str, tuple[Path, dict[str, Any]]] = {}
    backend_by_alias: dict[str, tuple[Path, dict[str, Any]]] = {}
    frontend_by_node: dict[str, tuple[Path, dict[str, Any]]] = {}
    frontend_by_alias: dict[str, tuple[Path, dict[str, Any]]] = {}
    release_articles: list[tuple[Path, dict[str, Any]]] = []
    for article_path, article in articles:
        identity = article.get("runtimeIdentity")
        identity = identity if isinstance(identity, Mapping) else {}
        if identity.get("origin") == "backend" and isinstance(identity.get("classType"), str):
            backend_by_node[identity["classType"]] = (article_path, article)
            for alias in identity.get("aliases", []):
                if isinstance(alias, str):
                    backend_by_alias[alias] = (article_path, article)
        if identity.get("origin") == "frontend" and isinstance(identity.get("classType"), str):
            frontend_by_node[identity["classType"]] = (article_path, article)
            for alias in identity.get("aliases", []):
                if isinstance(alias, str):
                    frontend_by_alias[alias] = (article_path, article)
        if article.get("kind") == "core" or identity.get("origin") == "frontend":
            release_articles.append((article_path, article))

    for node_id in sorted(nodes):
        if node_id in backend_by_node:
            continue
        if node_id in backend_by_alias:
            canonical = backend_by_alias[node_id][1].get("runtimeIdentity", {}).get("classType")
            reasons.append(f"runtime identity mismatch: inventory exposes historical alias {node_id!r}, article resolves to {canonical!r}")
        else:
            replacement_note = f"; replacement declares {replacements[node_id]!r}" if node_id in replacements else ""
            reasons.append(f"missing article for runtime node {node_id!r}{replacement_note}")

    for node_id, (_, article) in sorted(backend_by_node.items()):
        article_id = str(article.get("articleId", node_id))
        # API nodes are intentionally outside the v1.0 local-generation scope.
        if node_id in all_nodes and node_id not in local_generation_nodes({node_id: all_nodes[node_id]}):
            continue
        if node_id not in nodes:
            present_aliases = sorted(alias for alias, target in backend_by_alias.items() if target[1] is article and alias in nodes)
            if present_aliases:
                reasons.append(f"runtime identity mismatch for {article_id}: canonical {node_id!r} is absent; aliases present: {present_aliases}")
            elif article.get("status") != "removed":
                replacement_note = f"; replacement is {replacements[node_id]!r}" if node_id in replacements else ""
                reasons.append(f"runtime mismatch for {article_id}: node {node_id!r} is missing from inventory{replacement_note}")
            continue

        runtime_node = nodes[node_id]
        if article.get("status") == "removed":
            reasons.append(f"runtime mismatch for {article_id}: removed article still has runtime node {node_id!r}")
        expected_module = article.get("runtimeIdentity", {}).get("pythonModule")
        actual_module = runtime_node.get("python_module")
        if expected_module != actual_module:
            reasons.append(f"runtime module mismatch for {article_id}: expected {expected_module!r}, got {actual_module!r}")
        expected_status = _runtime_article_status(runtime_node)
        if article.get("status") != expected_status:
            reasons.append(f"runtime lifecycle mismatch for {article_id}: article is {article.get('status')!r}, runtime requires {expected_status!r}")
        runtime_experimental = bool(runtime_node.get("experimental", False))
        if article.get("experimental") is not runtime_experimental:
            reasons.append(f"runtime experimental mismatch for {article_id}: article is {article.get('experimental')!r}, runtime is {runtime_experimental!r}")
        expected_hash = article.get("editorial", {}).get("schemaHash")
        actual_hash = schema_fingerprint(node_id, runtime_node)
        if not isinstance(expected_hash, str) or not SHA256_RE.fullmatch(expected_hash) or expected_hash == "sha256:" + "0" * 64:
            reasons.append(f"stale article {article_id}: no reviewed schema fingerprint")
        elif expected_hash != actual_hash:
            reasons.append(f"stale article {article_id}: expected {expected_hash}, runtime is {actual_hash}")

    if frontend_inventory is None:
        reasons.append("frontend inventory missing: full user-visible frontend node coverage cannot be proven")
    else:
        try:
            release_manifest = load_json(CONTENT / "update-manifest.json")
            expected_frontend_version = release_manifest.get("inventory", {}).get("frontendVersion")
        except CatalogError:
            expected_frontend_version = None
        actual_frontend_version = frontend_inventory.get("frontendVersion")
        if not isinstance(expected_frontend_version, str):
            reasons.append("frontend version mismatch: update manifest has no target frontendVersion")
        elif actual_frontend_version != expected_frontend_version:
            reasons.append(
                f"frontend version mismatch: inventory is {actual_frontend_version!r}, "
                f"release targets {expected_frontend_version!r}"
            )
        frontend_nodes = frontend_inventory.get("nodes")
        if not isinstance(frontend_nodes, Mapping):
            reasons.append("frontend inventory is invalid: normalized nodes map is missing")
            frontend_nodes = {}
        for class_type in sorted(frontend_nodes):
            runtime_frontend = frontend_nodes[class_type]
            if class_type in frontend_by_node:
                _, article = frontend_by_node[class_type]
                article_id = str(article.get("articleId", class_type))
                if article.get("status") == "removed":
                    reasons.append(f"frontend runtime mismatch for {article_id}: removed article still has inventory type {class_type!r}")
                expected_package = article.get("runtimeIdentity", {}).get("packageId")
                actual_package = runtime_frontend.get("packageId") if isinstance(runtime_frontend, Mapping) else None
                if actual_package is not None and expected_package != actual_package:
                    reasons.append(f"frontend package mismatch for {article_id}: expected {expected_package!r}, got {actual_package!r}")
            elif class_type in frontend_by_alias:
                canonical = frontend_by_alias[class_type][1].get("runtimeIdentity", {}).get("classType")
                reasons.append(f"frontend identity mismatch: inventory exposes historical alias {class_type!r}, article resolves to {canonical!r}")
            else:
                reasons.append(f"missing article for frontend runtime type {class_type!r}")
        for class_type, (_, article) in sorted(frontend_by_node.items()):
            article_id = str(article.get("articleId", class_type))
            if article.get("status") == "removed":
                continue
            if class_type in frontend_nodes:
                continue
            present_aliases = sorted(alias for alias, target in frontend_by_alias.items() if target[1] is article and alias in frontend_nodes)
            if present_aliases:
                reasons.append(f"frontend identity mismatch for {article_id}: canonical {class_type!r} is absent; aliases present: {present_aliases}")
            else:
                reasons.append(f"orphan frontend article {article_id}: active type {class_type!r} is absent from frontend inventory")

    recipes_by_id = {
        recipe["recipeId"]: (recipe_path, recipe)
        for recipe_path, recipe in recipes
        if isinstance(recipe.get("recipeId"), str)
    }
    validated_recipe_ids: set[str] = set()
    release_article_ids = {
        article.get("articleId")
        for _, article in release_articles
        if isinstance(article.get("articleId"), str)
    }
    for article_path, article in articles:
        article_id = str(article.get("articleId", article_path.name))
        identity = article.get("runtimeIdentity")
        identity = identity if isinstance(identity, Mapping) else {}
        editorial = article.get("editorial")
        editorial = editorial if isinstance(editorial, Mapping) else {}
        is_release_article = article_id in release_article_ids
        if is_release_article:
            if editorial.get("state") != "approved":
                reasons.append(f"article {article_id} is not editorially approved: {editorial.get('state')!r}")
            if identity.get("origin") == "frontend":
                expected_status = "experimental" if article.get("experimental") is True else "active"
                if article.get("status") != expected_status:
                    reasons.append(f"frontend article {article_id} is {article.get('status')!r}; {expected_status!r} is required")
            elif identity.get("origin") != "backend" and article.get("status") != "active":
                reasons.append(f"core article {article_id} is {article.get('status')!r}; 'active' is required")

        assets = article.get("assets")
        assets = assets if isinstance(assets, list) else []
        example_assets = [asset for asset in assets if isinstance(asset, Mapping) and asset.get("type") in {"recipe", "workflow"}]
        if is_release_article and not example_assets:
            reasons.append(f"article {article_id} has no verified recipe or workflow example")
        for asset in example_assets:
            asset_type = asset.get("type")
            asset_id = asset.get("id")
            if not isinstance(asset_id, str) or not asset_id:
                reasons.append(f"broken example for {article_id}: {asset_type} asset has no id")
                continue
            if asset_type == "recipe":
                recipe_pair = recipes_by_id.get(asset_id)
                if recipe_pair is None:
                    reasons.append(f"broken example for {article_id}: referenced recipe {asset_id!r} is missing")
                    continue
                recipe_path, recipe = recipe_pair
                recipe_editorial = recipe.get("editorial")
                recipe_editorial = recipe_editorial if isinstance(recipe_editorial, Mapping) else {}
                if recipe_editorial.get("state") != "approved":
                    reasons.append(f"referenced recipe {asset_id} is not editorially approved: {recipe_editorial.get('state')!r}")
                if article_id not in recipe.get("articleIds", []):
                    reasons.append(f"broken example {asset_id}: it does not declare referring article {article_id}")
                if asset_id not in validated_recipe_ids:
                    reasons.extend(_example_validation_reasons(recipe_path, recipe, article_ids))
                    validated_recipe_ids.add(asset_id)
            elif asset_type == "workflow":
                try:
                    target = relative_content_path(article_path.parent, asset.get("path"), f"{article_path}.assets.workflow.path")
                    payload = load_json(target)
                    if not isinstance(payload, dict):
                        reasons.append(f"broken example {asset_id}: workflow must contain an object")
                    else:
                        workflow_errors: list[str] = []
                        validate_workflow(target, payload, workflow_errors)
                        reasons.extend(f"broken example {asset_id}: {error}" for error in workflow_errors)
                except CatalogError as exc:
                    reasons.append(f"broken example {asset_id}: {exc}")

    for workflow_path, workflow in workflows:
        workflow_errors: list[str] = []
        validate_workflow(workflow_path, workflow, workflow_errors)
        reasons.extend(f"broken catalog workflow {workflow_path.name}: {error}" for error in workflow_errors)

    return sorted(dict.fromkeys(reasons))


def release_gate_reasons(
    nodes: Mapping[str, Mapping[str, Any]],
    replacements: Mapping[str, str] | None = None,
    path: Path = CATALOG_MANIFEST,
    frontend_inventory: Mapping[str, Any] | None = None,
) -> list[str]:
    """Combine ordinary validation with the stricter stable-release policy."""

    reasons = [f"content validation error: {error}" for error in validate_catalog(path)]
    try:
        catalog, articles, recipes, workflows = load_source_catalog(path)
    except CatalogError as exc:
        reasons.append(f"content validation error: {exc}")
        return sorted(dict.fromkeys(reasons))
    reasons.extend(release_policy_reasons(catalog, articles, recipes, workflows, nodes, replacements, frontend_inventory))
    return sorted(dict.fromkeys(reasons))


def inventory_report(
    object_info_path: Path,
    replacements_path: Path | None,
    system_stats_path: Path | None,
    baseline_path: Path | None,
) -> dict[str, Any]:
    nodes = object_info_nodes(load_json(object_info_path))
    replacements = extract_replacements(load_json(replacements_path)) if replacements_path else {}
    system_stats = load_json(system_stats_path) if system_stats_path else None
    report: dict[str, Any] = {
        "schemaVersion": "1.0",
        "inventory": {
            "path": str(object_info_path),
            "sha256": sha256_file(object_info_path),
            "nodeCount": len(nodes),
        },
        "systemStats": system_stats,
        "replacements": replacements,
        "coverage": catalog_coverage(nodes, replacements),
    }
    if baseline_path:
        report["diff"] = diff_inventories(object_info_nodes(load_json(baseline_path)), nodes, replacements)
        report["baseline"] = {"path": str(baseline_path), "sha256": sha256_file(baseline_path)}
    return report


def report_markdown(report: Mapping[str, Any]) -> str:
    coverage = report["coverage"]
    lines = [
        "# Nodes Wizard inventory report",
        "",
        f"- Runtime nodes: {coverage['runtimeNodeCount']}",
        f"- Backend articles: {coverage['backendArticleCount']}",
        f"- Covered runtime nodes: {coverage['coveredNodeCount']}",
        f"- Coverage: {coverage['coverageRatio']:.2%}",
        f"- Missing articles: {len(coverage['missingArticles'])}",
        f"- Articles without runtime node: {len(coverage['articlesMissingRuntimeNode'])}",
        f"- Stale articles: {len(coverage['staleArticles'])}",
        "",
    ]
    for heading, key in (
        ("Missing articles", "missingArticles"),
        ("Articles without runtime node", "articlesMissingRuntimeNode"),
        ("Stale articles", "staleArticles"),
    ):
        lines.extend([f"## {heading}", ""])
        values = coverage[key]
        if not values:
            lines.append("None.")
        else:
            for value in values:
                lines.append(f"- `{value}`" if isinstance(value, str) else f"- `{json.dumps(value, ensure_ascii=False, sort_keys=True)}`")
        lines.append("")
    if "diff" in report:
        diff = report["diff"]
        lines.extend([
            "## Baseline diff",
            "",
            f"- Added: {len(diff['added'])}",
            f"- Removed: {len(diff['removed'])}",
            f"- Structurally changed: {len(diff['changed'])}",
            f"- Status changes: {len(diff['statusChanged'])}",
            "",
        ])
    return "\n".join(lines)


def print_errors(errors: Sequence[str]) -> None:
    for error in errors:
        print(f"ERROR: {error}", file=sys.stderr)


def command_validate(_: argparse.Namespace) -> int:
    errors = validate_catalog()
    if errors:
        print_errors(errors)
        return 1
    print("Catalog is valid.")
    return 0


def command_validate_compiled(args: argparse.Namespace) -> int:
    if args.catalog == "-":
        label = "<stdin>"
        try:
            instance = json.loads(sys.stdin.buffer.read().decode("utf-8"))
        except UnicodeDecodeError as exc:
            raise CatalogError(f"compiled catalog from stdin is not UTF-8: {exc}") from exc
        except json.JSONDecodeError as exc:
            raise CatalogError(f"invalid JSON from stdin: {exc}") from exc
    else:
        catalog_path = Path(args.catalog).resolve()
        label = str(catalog_path)
        instance = load_json(catalog_path)
    errors = validate_compiled_catalog_instance(instance)
    if errors:
        print_errors([f"{label}: {error}" for error in errors])
        return 1
    print(f"Compiled catalog is valid: {label}")
    return 0


def command_build(args: argparse.Namespace) -> int:
    build(Path(args.output_dir).resolve(), args.check, Path(args.inventory).resolve() if args.inventory else None)
    print("Generated artifacts are current." if args.check else f"Built catalog in {Path(args.output_dir).resolve()}")
    return 0


def command_sync_manifest(args: argparse.Namespace) -> int:
    current = sync_catalog_manifest(check=args.check)
    if not current:
        print("catalog.manifest.json is stale; run sync-manifest", file=sys.stderr)
        return 1
    print("Catalog manifest is current." if args.check else "Synchronized catalog.manifest.json.")
    return 0


def command_fingerprint(args: argparse.Namespace) -> int:
    nodes = object_info_nodes(load_json(Path(args.object_info)))
    if args.node_id:
        if args.node_id not in nodes:
            raise CatalogError(f"node not found: {args.node_id}")
        print(schema_fingerprint(args.node_id, nodes[args.node_id]))
    else:
        print(json.dumps({node_id: schema_fingerprint(node_id, nodes[node_id]) for node_id in sorted(nodes)}, indent=2, sort_keys=True))
    return 0


def command_diff(args: argparse.Namespace) -> int:
    before = object_info_nodes(load_json(Path(args.before)))
    after = object_info_nodes(load_json(Path(args.after)))
    replacements = extract_replacements(load_json(Path(args.replacements))) if args.replacements else {}
    result = diff_inventories(before, after, replacements)
    text = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        Path(args.output).write_text(text, encoding="utf-8", newline="\n")
    else:
        print(text, end="")
    return 0


def command_coverage(args: argparse.Namespace) -> int:
    nodes = object_info_nodes(load_json(Path(args.inventory)))
    replacements = extract_replacements(load_json(Path(args.replacements))) if args.replacements else {}
    print(json.dumps(catalog_coverage(nodes, replacements), ensure_ascii=False, indent=2))
    return 0


def command_inventory_report(args: argparse.Namespace) -> int:
    report = inventory_report(
        Path(args.object_info).resolve(),
        Path(args.replacements).resolve() if args.replacements else None,
        Path(args.system_stats).resolve() if args.system_stats else None,
        Path(args.baseline).resolve() if args.baseline else None,
    )
    output_dir = Path(args.output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    write_json(output_dir / "inventory-report.json", report)
    (output_dir / "inventory-report.md").write_text(report_markdown(report), encoding="utf-8", newline="\n")
    print(f"Wrote {output_dir / 'inventory-report.json'} and {output_dir / 'inventory-report.md'}")
    return 0


def command_snapshot_report(args: argparse.Namespace) -> int:
    inventory_path = Path(args.inventory).resolve()
    metadata_path = Path(args.metadata).resolve()
    snapshot = load_json(inventory_path)
    metadata = load_json(metadata_path)
    if not isinstance(metadata, Mapping):
        raise CatalogError("snapshot metadata must contain an object")
    artifact = metadata.get("snapshot")
    if not isinstance(artifact, Mapping):
        raise CatalogError("snapshot metadata has no snapshot artifact")
    if inventory_path.stat().st_size != artifact.get("size"):
        raise CatalogError("inventory size does not match snapshot metadata")
    if sha256_file(inventory_path) != artifact.get("sha256"):
        raise CatalogError("inventory SHA-256 does not match snapshot metadata")
    report = backend_inventory_report(snapshot, metadata)
    output_json = Path(args.output_json).resolve()
    output_markdown = Path(args.output_markdown).resolve()
    write_json(output_json, report)
    output_markdown.parent.mkdir(parents=True, exist_ok=True)
    output_markdown.write_text(backend_inventory_markdown(report), encoding="utf-8", newline="\n")
    print(f"Wrote {output_json} and {output_markdown}")
    return 0


def command_release_gate(args: argparse.Namespace) -> int:
    nodes = object_info_nodes(load_json(Path(args.inventory)))
    replacements = extract_replacements(load_json(Path(args.replacements))) if args.replacements else {}
    frontend_inventory = (
        parse_frontend_inventory(load_json(Path(args.frontend_inventory)), str(Path(args.frontend_inventory)))
        if args.frontend_inventory
        else None
    )
    reasons = release_gate_reasons(nodes, replacements, frontend_inventory=frontend_inventory)
    if reasons:
        print(f"Stable release gate FAILED ({len(reasons)} reason(s)):", file=sys.stderr)
        for reason in reasons:
            print(f"- {reason}", file=sys.stderr)
        return 1
    print("Stable release gate passed.")
    return 0


def command_ci(_: argparse.Namespace) -> int:
    errors = validate_catalog()
    if errors:
        print_errors(errors)
        return 1
    build(GENERATED, check=True)
    generated_catalog = load_json(GENERATED / "catalog.json")
    generated_errors = validate_compiled_catalog_instance(generated_catalog)
    if generated_errors:
        print_errors([f"generated catalog schema: {error}" for error in generated_errors])
        return 1
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    suite = unittest.defaultTestLoader.discover(
        str(ROOT / "tools" / "tests"),
        pattern="test_*.py",
        top_level_dir=str(ROOT),
    )
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    return 0 if result.wasSuccessful() else 1


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(description=__doc__)
    commands = root.add_subparsers(dest="command", required=True)
    validate = commands.add_parser("validate", help="validate source content without writing")
    validate.set_defaults(func=command_validate)

    validate_compiled = commands.add_parser("validate-compiled", help="validate one compiled catalog artifact without writing")
    validate_compiled.add_argument("catalog", help="path to compiled catalog JSON, or - for stdin")
    validate_compiled.set_defaults(func=command_validate_compiled)

    build_cmd = commands.add_parser("build", help="compile source content")
    build_cmd.add_argument("--output-dir", default=str(GENERATED))
    build_cmd.add_argument("--inventory", help="object_info snapshot used for schema fingerprints")
    build_cmd.add_argument("--check", action="store_true", help="fail if checked-in artifacts differ; do not write")
    build_cmd.set_defaults(func=command_build)

    sync_manifest = commands.add_parser("sync-manifest", help="synchronize the explicit source-file inventory")
    sync_manifest.add_argument("--check", action="store_true", help="fail if manifest differs; do not write")
    sync_manifest.set_defaults(func=command_sync_manifest)

    fingerprint = commands.add_parser("fingerprint", help="compute normalized object_info fingerprints")
    fingerprint.add_argument("object_info")
    fingerprint.add_argument("--node-id")
    fingerprint.set_defaults(func=command_fingerprint)

    diff = commands.add_parser("diff", help="compare two object_info inventories")
    diff.add_argument("--before", required=True)
    diff.add_argument("--after", required=True)
    diff.add_argument("--replacements", help="replacement payload for removed nodes")
    diff.add_argument("--output", help="write JSON to this exact path")
    diff.set_defaults(func=command_diff)

    coverage = commands.add_parser("coverage", help="print catalog coverage for a runtime inventory")
    coverage.add_argument("--inventory", required=True)
    coverage.add_argument("--replacements")
    coverage.set_defaults(func=command_coverage)

    report = commands.add_parser("inventory-report", help="write machine-readable and Markdown nightly reports")
    report.add_argument("--object-info", required=True)
    report.add_argument("--replacements")
    report.add_argument("--system-stats")
    report.add_argument("--baseline")
    report.add_argument("--output-dir", required=True)
    report.set_defaults(func=command_inventory_report)

    snapshot_report = commands.add_parser("snapshot-report", help="build a deterministic report for a pinned raw object_info snapshot")
    snapshot_report.add_argument("--inventory", required=True)
    snapshot_report.add_argument("--metadata", required=True)
    snapshot_report.add_argument("--output-json", required=True)
    snapshot_report.add_argument("--output-markdown", required=True)
    snapshot_report.set_defaults(func=command_snapshot_report)

    release_gate = commands.add_parser("release-gate", help="enforce stable-release content, runtime and approval policy")
    release_gate.add_argument("--inventory", required=True, help="current /object_info snapshot")
    release_gate.add_argument("--frontend-inventory", help="versioned inventory of user-visible frontend-only node types; required to pass stable")
    release_gate.add_argument("--replacements", help="optional /api/node_replacements payload")
    release_gate.set_defaults(func=command_release_gate)

    ci = commands.add_parser("ci", help="run validate, generated check and self-tests")
    ci.set_defaults(func=command_ci)
    return root


def main(argv: Sequence[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        return int(args.func(args))
    except CatalogError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    except OSError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
