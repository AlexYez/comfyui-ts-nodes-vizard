"""Build the pinned November update without rewriting historical evidence.

Source checkouts and the official inventory artifact are editorial inputs only.
Unreviewed schema/implementation drift remains visible in the output report.
"""
from __future__ import annotations

import ast
import copy
import hashlib
import re
from pathlib import Path

import catalog as c
import build_september_articles as tables
import import_custom_pack_articles as packs
from november_content import CORE, CUSTOM, DELTAS, CORE_DELTAS

DATE = "2026-11-02"
VERSION = "0.43.0"
FRONTEND = "1.57.4"
COMMIT = "426f5eea52a7ece1dd599fff4cb6cd1f352ddd24"
TS_COMMIT = "0e1aa5540cb95b8d5d932d4a082ec01d517cd03a"
TS_VERSION = "12.13.5"
RUN = "41421387267"
JSON_VERSION = "0.1.123"


def body_write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text.rstrip() + "\n", encoding="utf-8", newline="\n")


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def prepend_update(body, marker, section):
    """Replace a bounded editorial note without accumulating blank lines."""
    start, end = f"<!-- {marker}:start -->", f"<!-- {marker}:end -->"
    body = re.sub(r"\n+" + re.escape(start) + r"[\s\S]*?" + re.escape(end) + r"\n*", "\n\n", body)
    heading, rest = body.split("\n", 1)
    return f"{heading}\n\n{start}\n{section.rstrip()}\n{end}\n{rest}"


def class_dump(path, node_id):
    if not path.exists():
        return None
    tree = ast.parse(path.read_text(encoding="utf-8-sig"))
    for node in tree.body:
        if isinstance(node, ast.ClassDef) and node.name == node_id:
            return ast.dump(node, include_attributes=False)
    return None


def probe_source(path, qualified_name, url):
    text = path.read_text(encoding="utf-8-sig")
    items = ast.parse(text).body
    for name in qualified_name.split("."):
        node = next(n for n in items if isinstance(n, (ast.ClassDef, ast.FunctionDef)) and n.name == name)
        items = node.body
    code = "\n".join(text.splitlines()[node.lineno - 1:node.end_lineno])
    import textwrap
    code = textwrap.dedent(code)
    return {"name": qualified_name, "sourceUrl": url + f"#L{node.lineno}-L{node.end_lineno}",
            "code": code, "codeSha256": hashlib.sha256(code.encode()).hexdigest(), "fileSha256": sha(path)}


def review(article, source, commit, runtime, *, partial=False):
    """Never inherit an old example-executed or approval claim."""
    identity = article["runtimeIdentity"]
    return {
        "$schema": "../../schemas/article-research.schema.v1.json", "schemaVersion": "1.0",
        "articleId": article["articleId"],
        "node": {"classType": identity["classType"], "pythonModule": identity["pythonModule"], "origin": "backend"},
        "baseline": {"comfyui": VERSION, "frontend": FRONTEND, "sourceCommit": commit,
                     "embeddedDocs": "Implementation and pinned pack documentation; no human approval",
                     "workflowTemplatesJson": JSON_VERSION},
        "state": "source_reviewed", "reviewMode": "automated_assisted",
        "evidence": {"runtimeInventory": runtime, "sourceLocations": [source], "embeddedDocs": [], "workflows": []},
        "checks": {"implementationRead": not partial, "runtimeCompared": identity["packageId"] == "comfy-core",
                   "officialCasesInspected": False, "exampleSchemaValidated": False, "exampleExecuted": False,
                   "russianEdited": True, "factsRecheckedAfterEditing": not partial},
        "knownGaps": ["Требуется человеческое утверждение", "Full model workflow execution not performed",
                      "Official workflow wiring census is not manual case validation"]
                     + (["Targeted update section only; historical article is not fully re-reviewed"] if partial else [])
                     + (["Custom pack inventory is static source registration, not a live /object_info capture"] if identity["packageId"] != "comfy-core" else []),
        "updatedAt": DATE,
    }


def main():
    root = c.ROOT
    capture = root / ".upstream-cache/november-inventory/comfyui-inventory-v0.43.0"
    stats = c.load_json(capture / "system-stats.json")["system"]
    assert (stats["comfyui_version"], stats["required_frontend_version"]) == (VERSION, FRONTEND)
    files = {}
    for name in ("object-info.json", "node-replacements.json", "system-stats.json"):
        target = c.CONTENT / "runtime" / f"comfyui-{VERSION}.{name}"
        target.write_bytes((capture / name).read_bytes())
        files[target.name] = {"sha256": sha(target), "size": target.stat().st_size}
    c.write_json(c.CONTENT / "runtime" / f"comfyui-{VERSION}.capture.json", {
        "capturedAt": DATE, "checkedThrough": DATE, "sourceCommit": COMMIT,
        "artifactRun": f"https://github.com/AlexYez/comfyui-ts-nodes-vizard/actions/runs/{RUN}",
        "customNodes": "disabled", "device": "cpu", "files": files,
        "qualification": "Inventory capture only; no GPU inference or platform qualification",
    })
    inventory = c.object_info_nodes(c.load_json(capture / "object-info.json"))
    previous = c.object_info_nodes(c.load_json(c.CONTENT / "runtime/comfyui-0.38.0.object-info.json"))
    articles = {m["runtimeIdentity"]["classType"]: (p, m)
                for p in (c.CONTENT / "articles/core").rglob("manifest.json") if (m := c.load_json(p))}
    ids = {k: m["articleId"] for k, (_, m) in articles.items()}
    ids.update({node_id: "core." + tables.slug(node_id) for node_id in CORE if node_id not in ids})
    tables.SOURCE_ROOT = root / ".comfyui-source-0.43.0"
    tables.COMMIT = COMMIT
    tables.ARTICLES = CORE
    wheel = root / f".upstream-cache/comfyui_workflow_templates_json-{JSON_VERSION}-py3-none-any.whl"
    workflows, occurrences = tables.workflow_census(wheel)
    evidence = {}
    for node_id, (title, prose, related) in CORE.items():
        definition = inventory[node_id]
        assert not definition.get("api_node") and not definition.get("dev_only")
        if node_id in articles:
            path, manifest = articles[node_id]
        else:
            path = c.CONTENT / "articles/core" / tables.slug(node_id) / "manifest.json"
            manifest = copy.deepcopy(articles["TextEncodeMingImageEdit"][1])
            manifest.update(articleId=ids[node_id], assets=[])
        # Exact identity follows this verified official module relocation only.
        manifest["runtimeIdentity"].update(classType=node_id, pythonModule=definition["python_module"], aliases=[])
        manifest.update(title=title, summary=re.sub(r"[`*_]", "", prose.split("\n\n")[0])[:360], status="draft",
                        experimental=bool(definition.get("experimental")),
                        tags=["ComfyUI", definition["category"], node_id], concepts=[title],
                        searchAliases=list(dict.fromkeys(x for x in [node_id, definition.get("display_name"), *(definition.get("search_aliases") or [])] if isinstance(x, str) and x)))
        manifest["compatibility"].update(comfyui=">=0.43.0", frontend=">=1.57.4", verifiedOn=DATE,
                                         sourceRevision=f"ComfyUI {VERSION} @ {COMMIT}; frontend {FRONTEND}")
        manifest["editorial"].update(state="in_review", reviewedAt=DATE, factsReviewedAt=DATE,
                                     reviewedBy="Pinned source and runtime review; human approval pending",
                                     schemaHash=c.schema_fingerprint(node_id, definition))
        manifest["relations"]["related"] = [ids[key] for key in related]
        location, digest = tables.source_location(node_id, definition)
        manifest["sources"] = [{"sourceId": ids[node_id] + "-november-source", "title": f"{node_id}: ComfyUI {VERSION}",
                                "url": location["url"], "publisher": "Comfy-Org", "kind": "source", "accessedAt": DATE,
                                "supports": ["назначение", "входы и выходы", "ограничения реализации"]}]
        body = f"# {title}\n\n{prose.strip()}\n\n" + tables.schema_table(definition).replace("Снимок ComfyUI 0.37.0", "Снимок ComfyUI 0.43.0")
        body += f"\n\n## Источники и проверка\n\n[Реализация ComfyUI {VERSION}]({location['url']}). Входы и выходы сверены с чистым серверным снимком. Пример поясняет подключение, но не подтверждает выполненную генерацию с весами. Человеческое утверждение ещё нужно.\n"
        cases = occurrences.get(node_id, [])
        if cases:
            body += f"\n## Официальные примеры подключения\n\nВ закреплённом пакете [workflow-templates-json {JSON_VERSION}](https://pypi.org/project/comfyui-workflow-templates-json/{JSON_VERSION}/) найдено {len(cases)} вхождений. Примеры сохранённых связей:\n\n"
            for case in cases[:2]:
                before = ", ".join("`" + x["classType"] + "`" for x in case["upstream"]) or "нет входящих связей"
                after = ", ".join("`" + x["classType"] + "`" for x in case["downstream"]) or "нет исходящих связей"
                body += f"- `{case['workflowId']}.json`, подграф «{case['graphName']}»: входы от {before}; выходы к {after}.\n"
            body += "\nЭто автоматическая сверка сохранённых соединений, не запуск и не ручная проверка всех сценариев. Внешние входы и переключатели подграфа могут менять путь выполнения.\n"
        else:
            body += f"\nОтдельное вхождение в официальный пакет workflow-templates-json {JSON_VERSION} не найдено.\n"
        c.write_json(path, manifest)
        body_write(path.parent / "ru.md", body)
        ledger = review(manifest, location, COMMIT, f"runtime/comfyui-{VERSION}.object-info.json")
        c.write_json(c.CONTENT / "research/reviews" / (manifest["articleId"] + ".json"), ledger)
        evidence[node_id] = {"articleId": ids[node_id], "source": {**location, "sha256": digest},
                             "schemaHash": manifest["editorial"]["schemaHash"],
                             "workflowOccurrences": [{**case, **workflows[case["workflowId"]]} for case in cases]}

    core_partial = {}
    for node_id, prose in CORE_DELTAS.items():
        path, manifest = articles[node_id]
        location, digest = tables.source_location(node_id, inventory[node_id])
        body = (path.parent / "ru.md").read_text(encoding="utf-8")
        note = f"**Изменения в ComfyUI {VERSION}.** {prose}\n\n[Закреплённая реализация]({location['url']}). Ниже сохранено описание предыдущей проверенной версии; перечисленные изменения имеют приоритет. Полная повторная проверка старого текста и примеров не заявляется."
        body_write(path.parent / "ru.md", prepend_update(body, "november-core", note))
        source_id = manifest["articleId"] + "-november-delta"
        manifest["sources"] = [s for s in manifest["sources"] if s["sourceId"] != source_id]
        manifest["sources"].append({"sourceId": source_id, "title": f"Изменения {node_id} в ComfyUI {VERSION}",
                                    "url": location["url"], "publisher": "Comfy-Org", "kind": "source", "accessedAt": DATE,
                                    "supports": ["ноябрьское дополнение; не полная повторная проверка"]})
        c.write_json(path, manifest)
        core_partial[node_id] = {"articleId": manifest["articleId"], "source": {**location, "sha256": digest},
                                "note": prose, "fullReview": False}

    repo = root / ".upstream-cache/timesaver-november"
    old_repo = root / ".upstream-cache/timesaver-october"
    nodes = packs.timesaver_nodes(repo)
    old_nodes = packs.timesaver_nodes(old_repo)
    old_ids = {n["classType"] for n in old_nodes}
    ts_changes = {}
    packs.ACCESSED = DATE
    pack = dict(packs.PACKS["timesaver"], version=TS_VERSION, commit=TS_COMMIT)
    for node in nodes:
        node_id = node["classType"]
        path = c.CONTENT / "articles/custom/comfyui-timesaver" / packs.slugify(node_id) / "manifest.json"
        manifest = c.load_json(path) if path.exists() else packs.article_and_review(pack, node, repo)[0]
        url = f"https://github.com/{pack['repo']}/blob/{TS_COMMIT}/{node['sourcePath']}#L{node['sourceLine']}"
        manifest["compatibility"]["sourceRevision"] = f"comfyui-timesaver {TS_VERSION} @ {TS_COMMIT} (source inventory, not live qualification)"
        manifest["sources"] = [{"sourceId": manifest["articleId"] + "-november-source", "title": f"{node_id}: TimeSaver {TS_VERSION}",
                                "url": url, "publisher": "AlexYez", "kind": "source", "accessedAt": DATE,
                                "supports": ["регистрация ноды", "реализация"]}]
        full = node_id in CUSTOM
        partial = node_id in DELTAS
        if full:
            title, prose, related = CUSTOM[node_id]
            manifest.update(title=title, summary=re.sub(r"[`*_]", "", prose.split("\n\n")[0])[:360])
            manifest["relations"]["related"] = related
            body = f"# {title}\n\n{prose.strip()}\n"
        elif partial:
            old_body = (path.parent / "ru.md").read_text(encoding="utf-8")
            # Idempotent: replace only this update's bounded section.
            section = "## Изменения в TimeSaver 12.13.5\n\n" + DELTAS[node_id] + f"\n\n[Закреплённая реализация]({url}). Этот раздел обновлён по изменениям; последующий исторический текст не считается полностью повторно проверенным."
            body = prepend_update(old_body, "november-update", section)
        if full or partial:
            manifest["editorial"].update(reviewedAt=DATE, reviewedBy="Source-backed November update; human approval pending")
            if full:
                manifest["editorial"]["factsReviewedAt"] = DATE
                manifest["compatibility"].update(verifiedOn=DATE, comfyui=">=0.43.0", frontend=">=1.57.4")
                body += f"\n## Источники и границы проверки\n\n[Реализация TimeSaver {TS_VERSION}]({url}); [справка автора](https://github.com/{pack['repo']}/blob/{TS_COMMIT}/{node['documentationPath']}). Проверены исходники и документация, не живая установка всех зависимостей и не генерация с весами. Статья остаётся черновиком до человеческого утверждения.\n"
            body_write(path.parent / "ru.md", body)
            ledger = review(manifest, {"url": url, "path": node["sourcePath"], "lines": str(node["sourceLine"]) + "+"},
                            TS_COMMIT, "inventory/custom/comfyui-timesaver.json", partial=partial)
            c.write_json(c.CONTENT / "research/reviews" / (manifest["articleId"] + ".json"), ledger)
        c.write_json(path, manifest)
        old_source = old_repo / node["sourcePath"]
        old_docs = old_repo / node["documentationPath"]
        ts_changes[node_id] = {"new": node_id not in old_ids,
                              "sourceSha256": sha(repo / node["sourcePath"]), "docsSha256": sha(repo / node["documentationPath"]),
                              "sourceChanged": not old_source.exists() or sha(old_source) != sha(repo / node["sourcePath"]),
                              "docsChanged": not old_docs.exists() or sha(old_docs) != sha(repo / node["documentationPath"]),
                              "fullRewrite": full, "targetedUpdate": partial,
                              "needsFullEditorialRead": not full,
                              "needsImplementationReview": not (full or partial) and class_dump(old_source, node_id) != class_dump(repo / node["sourcePath"], node_id)}
    c.write_json(c.CONTENT / "inventory/custom/comfyui-timesaver.json", {
        "schemaVersion": "1.0", "packageId": pack["slug"], "repository": f"https://github.com/{pack['repo']}",
        "sourceCommit": TS_COMMIT, "version": TS_VERSION, "capturedAt": DATE, "nodes": nodes,
    })
    local = {k: v for k, v in c.local_generation_nodes(inventory).items() if not v.get("dev_only")}
    old_local = {k: v for k, v in c.local_generation_nodes(previous).items() if not v.get("dev_only")}
    probes = {}
    for label, relative, name, base in (
        ("branch_lazy", "comfy_extras/nodes_logic.py", "BranchNode.check_lazy_status", tables.SOURCE_ROOT),
        ("branch_execute", "comfy_extras/nodes_logic.py", "BranchNode.execute", tables.SOURCE_ROOT),
        ("latent_size", "comfy_extras/nodes_images.py", "GetLatentSize.execute", tables.SOURCE_ROOT),
        ("audio_size", "comfy_extras/nodes_audio.py", "GetAudioLatentSize.execute", tables.SOURCE_ROOT),
        ("split_padding", "comfy_extras/nodes_images.py", "split_padding", tables.SOURCE_ROOT),
        ("lora_model", "comfy_extras/nodes_lora_stack.py", "LoadLoraModel.execute", tables.SOURCE_ROOT),
        ("lora_clip", "comfy_extras/nodes_lora_stack.py", "LoadLoraTextEncoder.execute", tables.SOURCE_ROOT),
        ("batch_name", "nodes/files/ts_batch_write.py", "_safe_name", repo),
    ):
        repository = "Comfy-Org/ComfyUI" if base == tables.SOURCE_ROOT else "AlexYez/comfyui-timesaver"
        commit = COMMIT if base == tables.SOURCE_ROOT else TS_COMMIT
        probes[label] = probe_source(base / relative, name, f"https://github.com/{repository}/blob/{commit}/{relative}")
    c.write_json(c.CONTENT / "research/november-2026-update.json", {
        "checkedThrough": DATE, "comfyui": VERSION, "frontend": FRONTEND, "sourceCommit": COMMIT,
        "inventoryCaptureRun": RUN, "localCoreCount": len(local), "newCoreNodes": sorted(local.keys() - old_local.keys()),
        "removedCoreNodes": sorted(old_local.keys() - local.keys()),
        "changedCoreSchemas": sorted(k for k in local.keys() & old_local.keys() if c.schema_fingerprint(k, local[k]) != c.schema_fingerprint(k, old_local[k])),
        "moduleRelocations": [{"nodeId": k, "oldModule": old_local[k]["python_module"], "newModule": local[k]["python_module"]}
                              for k in sorted(local.keys() & old_local.keys()) if local[k]["python_module"] != old_local[k]["python_module"]],
        "coreArticles": evidence, "coreTargetedUpdates": core_partial, "timesaverVersion": TS_VERSION, "timesaverCommit": TS_COMMIT,
        "timesaverNodes": ts_changes, "workflowTemplatesJson": JSON_VERSION, "workflowWheelSha256": sha(wheel),
        "scope": "New guides, changed schemas and targeted pack updates. Historical editorial debt not silently approved.",
        "sourceProbes": probes,
        "humanApproved": False, "exampleExecuted": False,
    })
    # Make the new source files visible before coverage validation.
    manifest = c.load_json(c.CATALOG_MANIFEST)
    manifest.update(catalogVersion="0.3.3", generatedAt=DATE + "T00:00:00Z")
    manifest["articles"] = sorted(p.relative_to(c.CONTENT).as_posix() for p in (c.CONTENT / "articles").rglob("manifest.json"))
    c.write_json(c.CATALOG_MANIFEST, manifest)
    update_path = c.CONTENT / "update-manifest.json"
    update = c.load_json(update_path)
    update.update(catalogVersion="0.3.3", publishedAt=DATE + "T00:00:00Z", signature=None)
    update["inventory"] = {"source": f"runtime/comfyui-{VERSION}.object-info.json", "comfyuiVersion": VERSION,
                           "frontendVersion": FRONTEND, "capturedAt": DATE + "T00:00:00Z"}
    update["changes"] = {
        "summary": "Ноябрьское обновление: 16 новых локальных нод ComfyUI и шесть TimeSaver; обновлены изменившиеся статьи и инструкции. Редакционный статус alpha.",
        "added": sorted([ids[k] for k in local.keys() - old_local.keys()]
                        + ["custom.comfyui-timesaver." + packs.slugify(n["classType"]) for n in nodes if n["classType"] not in old_ids]),
        "updated": sorted([ids[k] for k in CORE if k in old_local]
                          + [ids[k] for k in CORE_DELTAS]
                          + ["custom.comfyui-timesaver." + packs.slugify(k) for k in CUSTOM.keys() | DELTAS.keys() if k in old_ids]),
        "deprecated": [], "removed": [],
    }
    c.write_json(update_path, update)
    report = c.inventory_report(c.CONTENT / f"runtime/comfyui-{VERSION}.object-info.json",
                                c.CONTENT / f"runtime/comfyui-{VERSION}.node-replacements.json",
                                c.CONTENT / f"runtime/comfyui-{VERSION}.system-stats.json",
                                c.CONTENT / "runtime/comfyui-0.38.0.object-info.json")
    report["inventory"]["path"] = f"content/runtime/comfyui-{VERSION}.object-info.json"
    report["baseline"]["path"] = "content/runtime/comfyui-0.38.0.object-info.json"
    c.write_json(c.CONTENT / f"runtime/comfyui-{VERSION}.inventory-report.json", report)
    body_write(c.CONTENT / f"runtime/comfyui-{VERSION}.inventory-report.md", c.report_markdown(report))
    print(f"Core {len(local)}; new {len(local.keys() - old_local.keys())}; TimeSaver {len(nodes)}; full articles {len(CORE) + len(CUSTOM)}; targeted sections {len(DELTAS)}")


if __name__ == "__main__":
    main()
