#!/usr/bin/env python3
"""Record successful schema validation for article examples in research ledgers."""

from __future__ import annotations

import json
from pathlib import Path

from tools import catalog


ROOT = Path(__file__).resolve().parents[1]
CONTENT = ROOT / "content"


def main() -> int:
    catalog_errors = catalog.validate_catalog()
    if catalog_errors:
        raise SystemExit("Catalog validation failed; research ledgers were not changed.\n" + "\n".join(catalog_errors))

    updated = 0
    for manifest_path in sorted((CONTENT / "articles" / "core").glob("*/manifest.json")):
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        if not any(asset["type"] in {"recipe", "workflow"} for asset in manifest.get("assets", [])):
            continue
        ledger_path = CONTENT / "research" / "reviews" / f"{manifest['articleId']}.json"
        ledger = json.loads(ledger_path.read_text(encoding="utf-8"))
        checks = ledger.setdefault("checks", {})
        if checks.get("exampleSchemaValidated") is True:
            continue
        checks["exampleSchemaValidated"] = True
        ledger_path.write_text(
            json.dumps(ledger, ensure_ascii=False, separators=(",", ":")) + "\n",
            encoding="utf-8",
        )
        updated += 1
    print(f"Updated {updated} research ledger(s).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
