"""Whole-catalog structural/prose triage with honest per-article review scope.

--normalize performs only narrow, protected Markdown prose substitutions.
--check-links requests the curated project URLs, without crawling remote assets.
Reports never count an automated scan as a manual read or fact approval.
"""
from __future__ import annotations

import argparse
import ast
from concurrent.futures import ThreadPoolExecutor
from functools import lru_cache
import hashlib
import re
import urllib.request

import catalog as c

REPLACEMENTS = {
    "Runtime flags": "Флаги ноды", "runtime flags": "флаги ноды",
    "возвращает общий sampling helper": "возвращает общая вспомогательная функция сэмплирования",
    "с model patcher": "с объектом управления моделью",
    "состояние model patcher": "состояние объекта управления моделью",
    "исходный model patcher": "исходный объект управления моделью",
    "list-output": "списковый выход",
    "не является output node": "не является выходной нодой",
    "не output node": "не выходная нода",
    "помечена как output node": "помечена как выходная нода",
    "зарегистрирована как output node": "зарегистрирована как выходная нода",
    "помечена как выходную ноду": "помечена как выходная нода",
    "зарегистрирована как выходную ноду": "зарегистрирована как выходная нода",
    "помечает её output node": "помечает её как выходную ноду",
    "— output node:": "— выходная нода:",
}
PROTECTED = re.compile(r"(```[\s\S]*?```|~~~[\s\S]*?~~~|`+[^`\n]*`+|https?://[^\s)<>]+)")
CLICHES = re.compile(r"важно отметить|стоит отметить|в современном мире|не просто\b|уникальн\w*|идеальн\w*|мощный инструмент|новый уровень|Таким образом,", re.I)


def normalize_prose(body):
    def prose(text):
        for old, new in REPLACEMENTS.items():
            text = text.replace(old, new)
        return text
    return "".join(part if i % 2 else prose(part) for i, part in enumerate(PROTECTED.split(body)))


@lru_cache(maxsize=None)
def classes(root, relative):
    path = root / relative
    if not path.exists():
        return {}
    tree = ast.parse(path.read_text(encoding="utf-8-sig"))
    result = {}
    for item in tree.body:
        if not isinstance(item, ast.ClassDef):
            continue
        result[item.name] = ast.dump(item, include_attributes=False)
        for node in ast.walk(item):
            if isinstance(node, ast.keyword) and node.arg == "node_id" and isinstance(node.value, ast.Constant):
                result[node.value.value] = result[item.name]
    # Legacy registered IDs may differ from their implementation class names.
    for item in tree.body:
        if not isinstance(item, ast.Assign) or not any(isinstance(t, ast.Name) and t.id == "NODE_CLASS_MAPPINGS" for t in item.targets):
            continue
        if isinstance(item.value, ast.Dict):
            for key, value in zip(item.value.keys, item.value.values):
                if isinstance(key, ast.Constant) and isinstance(value, ast.Name) and value.id in result:
                    result[key.value] = result[value.id]
    return result


def check_link(url):
    try:
        request = urllib.request.Request(url, headers={"User-Agent": "TS-Nodes-Wizard-Link-Check/0.3"})
        with urllib.request.urlopen(request, timeout=20) as response:
            # Read a small prefix to detect a generic error response; no assets.
            prefix = response.read(131072).decode("utf-8", errors="replace")
            title = re.search(r"<title[^>]*>(.*?)</title>", prefix, re.I | re.S)
            return {"url": url, "status": response.status, "finalUrl": response.url,
                    "checkedAt": "2026-10-03", "hasHtml": "<" in prefix,
                    "pageTitle": re.sub(r"\s+", " ", title.group(1)).strip() if title else None}
    except Exception as exc:
        return {"url": url, "error": str(exc), "checkedAt": "2026-10-03"}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--normalize", action="store_true")
    parser.add_argument("--check-links", action="store_true")
    args = parser.parse_args()
    focused = set(c.load_json(c.CONTENT / "research/october-2026-update.json")["rewrittenArticles"])
    inventory = c.object_info_nodes(c.load_json(c.CONTENT / "runtime/comfyui-0.38.0.object-info.json"))
    reading = c.load_json(c.CONTENT / "related-reading.json")
    records = []
    for path in sorted((c.CONTENT / "articles").rglob("manifest.json")):
        manifest = c.load_json(path)
        body_path = path.parent / manifest["body"]
        body = body_path.read_text(encoding="utf-8")
        normalized = normalize_prose(body)
        changed = normalized != body
        if args.normalize and changed:
            body_path.write_text(normalized, encoding="utf-8", newline="\n")
            body = normalized
        identity = manifest["runtimeIdentity"]
        node_id = identity["classType"]
        runtime = inventory.get(node_id) if identity.get("packageId") == "comfy-core" else None
        source_changed = None
        if runtime:
            relative = runtime["python_module"].replace(".", "/") + ".py"
            old = classes(c.ROOT / ".comfyui-source-0.37.0", relative).get(node_id)
            new = classes(c.ROOT / ".comfyui-source-0.38.0", relative).get(node_id)
            source_changed = old != new if old and new else None
        expected = manifest["editorial"].get("schemaHash")
        flags = [{"line": body[:m.start()].count("\n") + 1, "phrase": m.group(),
                  "context": body[max(0, m.start()-80):m.end()+140].replace("\n", " ")}
                 for m in CLICHES.finditer(body)]
        records.append({"articleId": manifest["articleId"], "path": body_path.relative_to(c.ROOT).as_posix(),
                        "sha256": hashlib.sha256(body.encode()).hexdigest(), "words": len(body.split()),
                        "manualFocusedCorrection": manifest["articleId"] in focused,
                        "mechanicalTerminologyCorrection": changed and args.normalize,
                        "lifecycle": manifest["status"], "candidatePhrases": flags,
                        "schemaChangedSinceArticle": bool(runtime and expected and expected != c.schema_fingerprint(node_id, runtime)),
                        "ownClassChangedSince037": source_changed,
                        "relatedReading": c.select_related_reading(manifest, reading)["url"],
                        "needsFullEditorialRead": manifest["articleId"] not in focused})
    previous_path = c.CONTENT / "research/october-2026-editorial-audit.json"
    link_results = c.load_json(previous_path).get("projectLinks", []) if previous_path.exists() else []
    if args.check_links:
        urls = sorted({item["url"] for item in [reading["fallback"], *reading["rules"], *reading["common"]]})
        with ThreadPoolExecutor(max_workers=8) as pool:
            link_results = list(pool.map(check_link, urls))
    report = {"checkedThrough": "2026-10-03", "scope": "Every article scanned; focused manual corrections listed separately. Candidate phrases are not automatically errors.",
              "articleCount": len(records), "words": sum(r["words"] for r in records),
              "focusedCorrections": len(focused), "projectLinks": link_results, "articles": records}
    c.write_json(previous_path, report)
    print(f"Scanned {len(records)} articles; focused corrections {len(focused)}; phrase candidates {sum(len(r['candidatePhrases']) for r in records)}")


if __name__ == "__main__":
    main()
