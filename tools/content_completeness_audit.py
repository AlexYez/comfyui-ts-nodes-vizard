#!/usr/bin/env python3
"""Audit editorial depth for every checked-in local-node article."""

from __future__ import annotations

import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CONTENT = ROOT / "content"


def main() -> int:
    articles: list[str] = []
    bad_headings: list[tuple[str, int]] = []
    no_sources: list[str] = []
    no_ledger: list[str] = []
    short_articles: list[tuple[str, int]] = []
    example_schema_false: list[str] = []
    example_executed_false: list[str] = []

    for manifest_path in sorted((CONTENT / "articles" / "core").glob("*/manifest.json")):
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        article_id = manifest["articleId"]
        body = (manifest_path.parent / manifest["body"]).read_text(encoding="utf-8")
        heading_count = len(re.findall(r"^## ", body, flags=re.MULTILINE))
        word_count = len(re.findall(r"[\wЁёА-Яа-я-]+", body, flags=re.UNICODE))
        articles.append(article_id)
        if heading_count < 10:
            bad_headings.append((article_id, heading_count))
        if not manifest.get("sources"):
            no_sources.append(article_id)
        if word_count < 350:
            short_articles.append((article_id, word_count))

        ledger_path = CONTENT / "research" / "reviews" / f"{article_id}.json"
        if not ledger_path.exists():
            no_ledger.append(article_id)
            continue
        ledger = json.loads(ledger_path.read_text(encoding="utf-8"))
        checks = ledger.get("checks", {})
        if not checks.get("exampleSchemaValidated"):
            example_schema_false.append(article_id)
        if not checks.get("exampleExecuted"):
            example_executed_false.append(article_id)

    report = {
        "articleCount": len(articles),
        "underTenHeadingsCount": len(bad_headings),
        "underTenHeadings": bad_headings,
        "missingSourceCount": len(no_sources),
        "missingSources": no_sources,
        "missingLedgerCount": len(no_ledger),
        "missingLedgers": no_ledger,
        "under350WordsCount": len(short_articles),
        "under350Words": short_articles,
        "exampleSchemaNotValidatedCount": len(example_schema_false),
        "exampleSchemaNotValidated": example_schema_false,
        "exampleNotExecutedCount": len(example_executed_false),
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))
    # Short texts remain a prioritized editorial queue, not a mechanical failure:
    # some nodes have deliberately small contracts and do not benefit from padding.
    return 1 if bad_headings or no_sources or no_ledger or example_schema_false else 0


if __name__ == "__main__":
    raise SystemExit(main())
