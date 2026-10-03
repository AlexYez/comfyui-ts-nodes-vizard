"""Import pinned October evidence and authored corrections; preserve archives.

This editorial tool does not mark unread articles as reviewed or execute models.
"""
from __future__ import annotations

import copy
import hashlib
import json
import re
from pathlib import Path

import catalog as c
import build_september_articles as tables
import import_custom_pack_articles as packs
from october_content import CORE, CUSTOM

DATE = "2026-10-03"
COMMIT = "6b747c0428c343e1417219641db93a4fb7cb69ae"
TS_COMMIT = "819d4e573a266fbc2aafb10554943f1e781c351a"
VERSION = "0.38.0"
FRONTEND = "1.53.6"
ROOT = c.ROOT


def write_body(path: Path, body: str):
    path.write_text(body.rstrip() + "\n", encoding="utf-8", newline="\n")


def main():
    capture = ROOT / ".upstream-cache/october-inventory/comfyui-inventory-v0.38.0"
    stats = c.load_json(capture / "system-stats.json")["system"]
    assert stats["comfyui_version"] == VERSION and stats["required_frontend_version"] == FRONTEND
    files = {}
    for filename in ("object-info.json", "node-replacements.json", "system-stats.json"):
        path = c.CONTENT / "runtime" / f"comfyui-{VERSION}.{filename}"
        raw = (capture / filename).read_bytes()
        path.write_bytes(raw)
        files[path.name] = {"sha256": hashlib.sha256(raw).hexdigest(), "size": len(raw)}
    c.write_json(c.CONTENT / "runtime" / f"comfyui-{VERSION}.capture.json", {
        "capturedAt": DATE, "checkedThrough": DATE, "sourceCommit": COMMIT,
        "artifactRun": "https://github.com/AlexYez/comfyui-ts-nodes-vizard/actions/runs/37108641550",
        "customNodes": "disabled", "device": "cpu", "files": files,
        "qualification": "Inventory only; no GPU workflow execution or platform compatibility approval",
    })
    inventory = c.object_info_nodes(c.load_json(capture / "object-info.json"))
    articles = {m["runtimeIdentity"]["classType"]: (p, m)
                for p in (c.CONTENT / "articles").rglob("manifest.json")
                if (m := c.load_json(p))["runtimeIdentity"].get("packageId") == "comfy-core"}
    tables.SOURCE_ROOT = ROOT / ".comfyui-source-0.38.0"
    tables.COMMIT = COMMIT
    tables.ARTICLES = CORE
    wheel = ROOT / ".upstream-cache/comfyui_workflow_templates_json-0.1.96-py3-none-any.whl"
    workflows, occurrences = tables.workflow_census(wheel)
    updated = []
    for node_id, (title, prose, related) in CORE.items():
        if node_id in articles:
            path, manifest = articles[node_id]
        else:
            slug = tables.slug(node_id)
            path = c.CONTENT / "articles/core" / slug / "manifest.json"
            manifest = copy.deepcopy(articles["TextEncodeQwenImage21"][1])
            manifest["articleId"] = "core." + slug
            manifest["runtimeIdentity"].update(classType=node_id, pythonModule=inventory[node_id]["python_module"], aliases=[])
            manifest["assets"] = []
            manifest["searchAliases"] = [node_id, inventory[node_id].get("display_name", node_id)]
            manifest["tags"] = ["ComfyUI", inventory[node_id]["category"]]
            manifest["concepts"] = ["редактирование изображений"]
        manifest["title"] = title
        manifest["summary"] = re.sub(r"[`*_]", "", prose.split("\n\n")[0])[:360]
        manifest["status"] = "draft"
        manifest["experimental"] = bool(inventory[node_id].get("experimental"))
        manifest["editorial"].update(state="in_review", reviewedAt=DATE, factsReviewedAt=DATE,
                                     reviewedBy="Source and runtime review; human approval pending",
                                     schemaHash=c.schema_fingerprint(node_id, inventory[node_id]))
        manifest["compatibility"].update(comfyui=">=0.38.0", frontend=">=1.53.6", verifiedOn=DATE,
                                         sourceRevision=f"ComfyUI {VERSION} @ {COMMIT}; frontend {FRONTEND}")
        manifest["relations"]["related"] = related
        location, _ = tables.source_location(node_id, inventory[node_id])
        manifest["sources"] = [{"sourceId": manifest["articleId"] + "-october-source", "title": f"{node_id}: ComfyUI {VERSION}",
                                "url": location["url"], "publisher": "Comfy-Org", "kind": "source", "accessedAt": DATE,
                                "supports": ["назначение", "параметры", "ограничения реализации"]}]
        body = f"# {title}\n\n{prose.strip()}\n\n" + tables.schema_table(inventory[node_id]).replace("Снимок ComfyUI 0.37.0", "Снимок ComfyUI 0.38.0")
        body += f"\n\n## Источники и границы проверки\n\n[Реализация ComfyUI {VERSION}]({location['url']}). Входы и выходы сверены с чистой установкой от 3 октября. Полная генерация с весами не выполнялась; человеческое утверждение ещё нужно.\n"
        cases = occurrences.get(node_id, [])[:2]
        if cases:
            body += "\n## Официальные примеры подключения\n\n"
            for case in cases:
                before = ", ".join("`" + x["classType"] + "`" for x in case["upstream"]) or "нет входящих связей"
                after = ", ".join("`" + x["classType"] + "`" for x in case["downstream"]) or "нет исходящих связей"
                body += f"`{case['workflowId']}.json`, подграф «{case['graphName']}»: входы от {before}; выходы к {after}.\n\n"
            body += "Шаблоны из [официального пакета 0.1.96](https://pypi.org/project/comfyui-workflow-templates-json/0.1.96/), закреплённого ComfyUI 0.38.0. Это сохранённые соединения, не отчёт о запуске. Внешние входы и переключатели подграфа могут менять значения и путь выполнения. `SubgraphInput` и `SubgraphOutput` обозначают границы подграфа.\n"
        else:
            body += "\nВ официальном пакете workflow-templates-json 0.1.96 отдельного примера не найдено; приведённый пример поясняет подключение, но не подтверждает выполненную генерацию.\n"
        c.write_json(path, manifest)
        write_body(path.parent / "ru.md", body)
        review_path = c.CONTENT / "research/reviews" / (manifest["articleId"] + ".json")
        review = copy.deepcopy(c.load_json(c.CONTENT / "research/reviews/core.image-color-space.json"))
        review.update(articleId=manifest["articleId"], updatedAt=DATE)
        review["node"].update(classType=node_id, pythonModule=inventory[node_id]["python_module"])
        review["baseline"].update(comfyui=VERSION, frontend=FRONTEND, sourceCommit=COMMIT)
        review["baseline"]["workflowTemplatesJson"] = "0.1.96"
        review["evidence"].update(runtimeInventory=f"runtime/comfyui-{VERSION}.object-info.json", sourceLocations=[location],
                                  workflows=[{"id": x["workflowId"], "role": f"Saved wiring in {x['graphName']} ({x['graphScope']}); not model execution"} for x in cases])
        review["checks"].update(officialCasesInspected=False, exampleSchemaValidated=False, exampleExecuted=False)
        review["knownGaps"] = ["Требуется человеческое утверждение", "Full model workflow execution not performed",
                               "Worked example is explanatory, not an executable validated recipe", "Automatically extracted workflow wiring still needs manual case review"]
        c.write_json(review_path, review)
        updated.append(manifest["articleId"])

    repo = ROOT / ".upstream-cache/timesaver-october"
    nodes = packs.timesaver_nodes(repo)
    assert len(nodes) == 82
    old_nodes = c.load_json(c.CONTENT / "inventory/custom/comfyui-timesaver.json")["nodes"]
    old_ids = {n["classType"] for n in old_nodes} | {
        c.load_json(p)["runtimeIdentity"]["classType"]
        for p in (c.CONTENT / "articles/custom/comfyui-timesaver").glob("*/manifest.json")}
    new_ids = {n["classType"] for n in nodes}
    packs.ACCESSED = DATE
    pack = dict(packs.PACKS["timesaver"], version="12.12.3", commit=TS_COMMIT)
    for node in nodes:
        path = c.CONTENT / "articles/custom/comfyui-timesaver" / packs.slugify(node["classType"]) / "manifest.json"
        source_url = f"https://github.com/{pack['repo']}/blob/{TS_COMMIT}/{node['sourcePath']}#L{node['sourceLine']}"
        if path.exists():
            manifest = c.load_json(path)
        else:
            manifest, _, review = packs.article_and_review(pack, node, repo)
            c.write_json(c.CONTENT / "research/reviews" / (manifest["articleId"] + ".json"), review)
        manifest["compatibility"].update(verifiedOn=DATE, sourceRevision=f"comfyui-timesaver 12.12.3 @ {TS_COMMIT}")
        for source in manifest["sources"]:
            source["url"] = source["url"].replace("c1668b3cfa2161e36bf9b9fa91288b949b4b0b1f", TS_COMMIT)
            source["accessedAt"] = DATE
        manifest["sources"][0]["url"] = source_url
        docs = (repo / node["documentationPath"]).read_text(encoding="utf-8-sig")
        # Only changed documentation and authored corrections replace prose.
        previous = ROOT / ".upstream-cache/timesaver-september" / node["documentationPath"]
        if node["classType"] in CUSTOM:
            body = f"# {node['displayName']}\n\n{CUSTOM[node['classType']].strip()}"
            body += f"\n\n## Источники\n\n[Реализация]({source_url}); [справка автора](https://github.com/{pack['repo']}/blob/{TS_COMMIT}/{node['documentationPath']}). Проверено по исходнику и справке TimeSaver 12.12.3; выполнение с моделями и человеческое утверждение ещё нужны.\n"
            manifest["summary"] = re.sub(r"[`*_]", "", CUSTOM[node["classType"]].split("\n\n")[0])[:360]
            manifest["editorial"].update(reviewedAt=DATE, factsReviewedAt=DATE)
            review_path = c.CONTENT / "research/reviews" / (manifest["articleId"] + ".json")
            review = c.load_json(review_path)
            review["baseline"]["sourceCommit"] = TS_COMMIT
            review["evidence"]["sourceLocations"] = [{"url": source_url, "path": node["sourcePath"], "lines": str(node["sourceLine"]) + "+"}]
            review["checks"].update(implementationRead=True, russianEdited=True, factsRecheckedAfterEditing=True,
                                    runtimeCompared=False, officialCasesInspected=False, exampleSchemaValidated=False, exampleExecuted=False)
            review["knownGaps"] = ["Требуется человеческое утверждение", "Live custom-pack runtime and full model workflow execution not verified"]
            review["updatedAt"] = DATE
            c.write_json(review_path, review)
            write_body(path.parent / "ru.md", body) if path.parent.exists() else None
            updated.append(manifest["articleId"])
        elif not previous.exists() or previous.read_text(encoding="utf-8-sig") != docs:
            body = packs.clean_body(docs, node["displayName"], source_url, pack["slug"])
            write_body(path.parent / "ru.md", body)
            updated.append(manifest["articleId"])
        else:
            body = None
        c.write_json(path, manifest)
        if body is not None:
            write_body(path.parent / "ru.md", body)
    related = {
        "TS_LoraUnmerged": ["custom.comfyui-timesaver.ts-loraloader", "custom.comfyui-timesaver.ts-shiftedsigmas", "core.lora-loader-model-only"],
        "TS_ShiftedSigmas": ["custom.comfyui-timesaver.ts-loraunmerged", "core.sampler-custom-advanced", "core.split-sigmas"],
        "TS_PromptLibrary": ["custom.comfyui-timesaver.ts-rtpromptenhancer", "custom.comfyui-timesaver.ts-superprompt", "core.text-encode-qwen-image21"],
        "TS_RTPromptEnhancer": ["custom.comfyui-timesaver.ts-superpromptrt", "custom.comfyui-timesaver.ts-promptlibrary"],
        "TS_ImageBatchToImageList": ["custom.comfyui-timesaver.ts-imagelisttoimagebatch"],
        "TS_ImageListToImageBatch": ["custom.comfyui-timesaver.ts-imagebatchtoimagelist"],
    }
    for node_id, targets in related.items():
        path = c.CONTENT / "articles/custom/comfyui-timesaver" / packs.slugify(node_id) / "manifest.json"
        manifest = c.load_json(path)
        manifest["relations"]["related"] = targets
        c.write_json(path, manifest)
    archived = []
    for node_id in sorted(old_ids - new_ids):
        path = c.CONTENT / "articles/custom/comfyui-timesaver" / packs.slugify(node_id) / "manifest.json"
        manifest = c.load_json(path)
        manifest["status"] = "removed"
        body_path = path.parent / "ru.md"
        body = body_path.read_text(encoding="utf-8")
        warning = "## Архив: нода удалена\n\nTS Image Studio и её служебные ноды удалены в TimeSaver 12.11.8. Эта статья описывает последнюю поддерживаемую версию 12.11.7. В новом паке такой ноды нет; старый workflow может открыться с отсутствующими узлами. Прямой совместимой замены автор не объявил.\n\n"
        if "## Архив: нода удалена" not in body:
            heading, rest = body.split("\n", 1)
            write_body(body_path, heading + "\n\n" + warning + rest.lstrip())
        c.write_json(path, manifest)
        archived.append(manifest["articleId"])
    c.write_json(c.CONTENT / "inventory/custom/comfyui-timesaver.json", {
        "schemaVersion": "1.0", "packageId": pack["slug"], "repository": f"https://github.com/{pack['repo']}",
        "sourceCommit": TS_COMMIT, "version": pack["version"], "capturedAt": DATE, "nodes": nodes,
    })
    c.write_json(c.CONTENT / "research/october-2026-update.json", {
        "checkedThrough": DATE, "comfyui": VERSION, "frontend": FRONTEND, "sourceCommit": COMMIT,
        "timesaver": pack, "rewrittenArticles": updated, "archivedArticles": archived,
        "scope": "Focused source-backed corrections and whole-catalog automated checks, not a full manual editorial sign-off",
        "exampleExecuted": False, "humanApproved": False,
        "workflowTemplatesJson": "0.1.96", "workflowWheelSha256": hashlib.sha256(wheel.read_bytes()).hexdigest(),
        "officialWorkflowOccurrences": {node: [{**case, **workflows[case['workflowId']]} for case in occurrences.get(node, [])] for node in CORE},
    })
    runtime = c.CONTENT / "runtime"
    report = c.inventory_report(runtime / "comfyui-0.38.0.object-info.json", runtime / "comfyui-0.38.0.node-replacements.json",
                                runtime / "comfyui-0.38.0.system-stats.json", runtime / "comfyui-0.37.0.object-info.json")
    report["inventory"]["path"] = "content/runtime/comfyui-0.38.0.object-info.json"
    report["baseline"]["path"] = "content/runtime/comfyui-0.37.0.object-info.json"
    c.write_json(runtime / "comfyui-0.38.0.inventory-report.json", report)
    write_body(runtime / "comfyui-0.38.0.inventory-report.md", c.report_markdown(report))
    print(f"Rewritten {len(updated)} articles; archived {len(archived)}")


if __name__ == "__main__":
    main()
