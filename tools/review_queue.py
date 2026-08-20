from __future__ import annotations

import argparse
import json
from collections import Counter
from typing import Any

try:
    from tools import catalog
except ModuleNotFoundError:  # Running as ``python tools/review_queue.py``.
    import catalog


def load_queue() -> dict[str, Any]:
    inventory = catalog.object_info_nodes(catalog.load_json(catalog.CONTENT / "runtime" / "comfyui-0.32.0.object-info.json"))
    recipes = {recipe["recipeId"]: recipe for path in (catalog.CONTENT / "recipes").rglob("recipe.json") for recipe in [catalog.load_json(path)]}
    rows: list[dict[str, Any]] = []
    for path in sorted((catalog.CONTENT / "articles").rglob("manifest.json")):
        article = catalog.load_json(path)
        identity = article.get("runtimeIdentity", {})
        class_type = identity.get("classType")
        runtime = inventory.get(class_type)
        if identity.get("origin") != "backend" or runtime is None or runtime.get("api_node", False):
            continue
        article_id = article["articleId"]
        research_path = catalog.CONTENT / "research" / "reviews" / f"{article_id}.json"
        research = catalog.load_json(research_path) if research_path.exists() else {}
        recipe_rows = []
        for asset in article.get("assets", []):
            if asset.get("type") == "recipe":
                recipe = recipes.get(asset.get("id"), {})
                recipe_rows.append({"recipeId": asset.get("id"), "title": recipe.get("title", asset.get("label")), "editorialState": recipe.get("editorial", {}).get("state")})
        rows.append({
            "articleId": article_id, "title": article.get("title"), "classType": class_type,
            "pythonModule": identity.get("pythonModule"), "runtimeLifecycle": catalog._runtime_article_status(runtime),
            "articleStatus": article.get("status"), "editorialState": article.get("editorial", {}).get("state"),
            "researchState": research.get("state"), "reviewMode": research.get("reviewMode"),
            "checks": research.get("checks", {}), "knownGaps": research.get("knownGaps", []),
            "sourceCount": len(article.get("sources", [])), "recipes": recipe_rows,
        })
    states = Counter(row["editorialState"] for row in rows)
    return {"schemaVersion": "1.0", "localArticleCount": len(rows), "editorialStates": dict(sorted(states.items(), key=lambda item: str(item[0]))), "articles": rows}


def markdown(report: dict[str, Any], article_id: str | None = None) -> str:
    rows = report["articles"]
    if article_id:
        rows = [row for row in rows if row["articleId"] == article_id]
        if not rows:
            raise SystemExit(f"Unknown local articleId: {article_id}")
    lines = ["# TS Nodes Wizard — очередь человеческого ревью", "", f"Локальных статей: {report['localArticleCount']}. Автоматическое утверждение запрещено.", ""]
    for row in rows:
        lines.extend([
            f"## {row['articleId']} — {row['title']}", "",
            f"- Runtime: `{row['classType']}` / `{row['pythonModule']}`; ожидаемый статус: `{row['runtimeLifecycle']}`.",
            f"- Сейчас: article `{row['articleStatus']}`, editorial `{row['editorialState']}`, research `{row['researchState']}` / `{row['reviewMode']}`.",
            f"- Источников: {row['sourceCount']}; рецептов: {len(row['recipes'])}.",
        ])
        if row["knownGaps"]:
            lines.append("- Перед утверждением закрыть:")
            lines.extend(f"  - {gap}" for gap in row["knownGaps"])
        else:
            lines.append("- Незакрытых ограничений в research record нет.")
        if row["recipes"]:
            lines.append("- Связанные рецепты:")
            lines.extend(f"  - `{recipe['recipeId']}` — {recipe['title']} (`{recipe['editorialState']}`)." for recipe in row["recipes"])
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description="Read-only human review queue for local TS Nodes Wizard content.")
    parser.add_argument("--format", choices=("json", "markdown"), default="markdown")
    parser.add_argument("--article-id", help="show one exact articleId")
    args = parser.parse_args()
    report = load_queue()
    if args.format == "json":
        if args.article_id:
            report = {**report, "articles": [row for row in report["articles"] if row["articleId"] == args.article_id]}
            if not report["articles"]:
                raise SystemExit(f"Unknown local articleId: {args.article_id}")
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(markdown(report, args.article_id), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
