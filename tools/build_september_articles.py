"""Compile 64 authored guides and pinned evidence, never auto-invent article prose.

Run with the ComfyUI v0.37.0 source checkout and workflow JSON wheel 0.1.92.
No model inference is implied by this editorial build.
"""
from __future__ import annotations

import ast
import hashlib
import json
import re
import zipfile
from collections import Counter, defaultdict
from pathlib import Path

from catalog import ROOT, schema_fingerprint, write_json
from september_content import mesh, music, pose, trellis, utilities, video_guides

MODULES = (mesh, music, trellis, utilities, pose, video_guides)
ARTICLES = {key: value for module in MODULES for key, value in module.ARTICLES.items()}
COMMIT = "73c9bad4d21e7addbe1d13bc92eee0f1431b017d"
DATE = "2026-09-27"
CONTENT = ROOT / "content"
INVENTORY = CONTENT / "runtime/comfyui-0.37.0.object-info.json"
SOURCE_ROOT = ROOT / ".comfyui-source-0.37.0"
WHEEL = ROOT / ".upstream-cache/comfyui_workflow_templates_json-0.1.92-py3-none-any.whl"
WORKFLOW_URL = "https://pypi.org/project/comfyui-workflow-templates-json/0.1.92/"
CASE_NOTES = {
    "MiniMaxMusic3TextEncode": "В музыкальном шаблоне seconds напрямую управляет пустым latent, а ConditioningZeroOut готовит отрицательную ветку для KSampler. Так длительность не приходится дублировать вручную.",
    "EmptyMiniMaxMusic3LatentAudio": "В audio_minimax_music_3 длительность приходит от энкодера, затем KSampler передаёт результат в обычное или tiled-декодирование аудио. Число 120 в сохранённом виджете не заменяет подключённый seconds.",
    "YuE2GenerateABC": "В text2music ABC проходит через переключатель: нотный план можно использовать либо отключить. Это отдельный этап до акустического conditioning, не готовая музыка.",
    "YuE2GenerateMusic": "В cover-шаблоне ABC поступает от SheetSage2 через PreviewAny; в text2music — из ветки генерации нот. В обоих случаях seconds связан с пустым YuE2 latent, а результат KSampler затем декодируется в звук.",
    "EmptyYuE2LatentAudio": "И в cover, и в text2music вход seconds подключён к YuE2GenerateMusic. Поэтому сохранённое в виджете значение не является фактической длительностью при выполнении связанного графа.",
    "SheetSage2AudioToABC": "В audio_yue2_music_cover выбран melody. ABC проходит через PreviewAny к YuE2GenerateMusic: исходная запись задаёт музыкальный план, а описание и слова следующего этапа управляют новым результатом.",
    "ConditioningLoader": "Шаблоны Marigold загружают заранее подготовленный conditioning для конкретной задачи — albedo или depth — и передают его в BasicGuider. Это реальный случай использования без повторного текстового кодирования.",
    "MarigoldV2PostProcess": "В Marigold-нода стоит после VAEDecode. prediction подключён к входу подграфа, поэтому видимое сохранённое значение depth внутри определения не доказывает, что albedo-шаблон исполняется в режиме глубины.",
    "TextEncodeQwenImage21": "В Qwen edit-шаблонах энкодер получает CLIP и VAE, выдаёт оба conditioning для KSampler, а latent проходит через переключатель. Для редактирования важно сохранить размер, выбранный по первому референсу.",
    "QwenImage21Cache": "В Qwen edit-шаблонах нода расположена между UNETLoader и KSampler. Параметры кэша выведены наружу подграфа, поэтому сравнение режимов не требует менять внутреннюю цепочку генерации.",
    "BlockSparseAttention": "В двух FastH3-шаблонах выбран VSA после ModelAttentionBackend; изменённая модель поступает и в BasicGuider, и в BasicScheduler. Это пример специально совместимой цепочки, а не рекомендация включать VSA для любой модели.",
    "StartLoop": "В Wan Animate 2 цикл последовательно обрабатывает части движения. Его текущее переносимое значение разбирается через два GetItemFromList, а переключатели различают первый и следующие шаги.",
    "EndLoop": "В Wan Animate 2 включено accumulate: наружу возвращаются результаты итераций, затем RebatchImages собирает нужные batch. CreateList готовит переносимые данные, отделённые от возвращаемых кадров.",
    "GetItemFromList": "В Wan Animate 2 две ноды выбирают индексы 0 и 1 из переносимого значения StartLoop. Это разбор списка состояний цикла, не выбор двух кадров из IMAGE-тензора.",
}


def graph_scopes(value, scope="root"):
    """Visit graph definitions separately: node IDs are local to each subgraph."""
    if isinstance(value, dict):
        if isinstance(value.get("nodes"), list) and isinstance(value.get("links"), list):
            yield scope, value
        for key, child in value.items():
            if key not in ("nodes", "links"):
                yield from graph_scopes(child, scope + "/" + key)
    elif isinstance(value, list):
        for index, child in enumerate(value):
            yield from graph_scopes(child, scope + f"/{index}")


def workflow_census(wheel):
    workflows, occurrences = {}, defaultdict(list)
    with zipfile.ZipFile(wheel) as archive:
        for name in sorted(archive.namelist()):
            if not name.startswith("comfyui_workflow_templates_json/templates/") or not name.endswith(".json"):
                continue
            raw = archive.read(name)
            value = json.loads(raw)
            scopes = list(graph_scopes(value))
            if not scopes:
                continue
            workflow_id = Path(name).stem
            node_types = {n.get("type") for _, g in scopes for n in g["nodes"] if isinstance(n.get("type"), str)}
            workflows[workflow_id] = {"archivePath": name, "sha256": "sha256:" + hashlib.sha256(raw).hexdigest(), "nodeTypes": sorted(node_types), "bytes": len(raw)}
            for scope, graph in scopes:
                nodes = {n["id"]: n for n in graph["nodes"] if "id" in n and "type" in n}
                edges = []
                for link in graph["links"]:
                    if isinstance(link, list) and len(link) >= 5:
                        origin, target = link[1], link[3]
                    elif isinstance(link, dict) and "origin_id" in link and "target_id" in link:
                        origin, target = link["origin_id"], link["target_id"]
                    else:
                        continue
                    # Boundary ports are explicit; do not resolve IDs in another scope.
                    edges.append((nodes.get(origin, {}).get("type", "SubgraphInput"), nodes.get(target, {}).get("type", "SubgraphOutput")))
                for kind in sorted({n["type"] for n in nodes.values()} & set(ARTICLES)):
                    before = Counter(a for a, b in edges if b == kind)
                    after = Counter(b for a, b in edges if a == kind)
                    occurrences[kind].append({"workflowId": workflow_id, "graphScope": scope, "graphName": graph.get("name", "main"), "upstream": [{"classType": k, "links": v} for k, v in sorted(before.items())], "downstream": [{"classType": k, "links": v} for k, v in sorted(after.items())], "instances": [{"nodeId": n["id"], "widgets": n.get("widgets_values")} for n in nodes.values() if n["type"] == kind]})
    return workflows, dict(occurrences)


def slug(node_id):
    value = re.sub(r"([a-z0-9])([A-Z])", r"\1-\2", node_id)
    return re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")


def cell(value):
    if not isinstance(value, str):
        value = json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    return value.replace("|", "\\|").replace("\n", " ").replace("`", "'")


def input_rows(inputs, prefix=""):
    """Include conditional V3 inputs without dumping tooltips or opaque JSON."""
    rows = []
    for group in ("required", "optional"):
        for name, spec in inputs.get(group, {}).items():
            kind = spec[0]
            options = spec[1] if len(spec) > 1 and isinstance(spec[1], dict) else {}
            details = []
            if isinstance(kind, list):
                details.append("варианты: " + ", ".join(map(cell, kind)))
                kind = "COMBO"
            for key, label in (("default", "по умолчанию"), ("min", "минимум"), ("max", "максимум"), ("step", "шаг")):
                if key in options:
                    details.append(f"{label}: {cell(options[key])}")
            branches = options.get("options", [])
            if branches and all(isinstance(x, dict) and "key" in x for x in branches):
                details.append("режимы: " + ", ".join(cell(x["key"]) for x in branches))
            elif branches and all(isinstance(x, (str, int, float)) for x in branches):
                details.append("варианты: " + ", ".join(map(cell, branches)))
            template = options.get("template", {})
            if "names" in template:
                names = template["names"]
                details.append(f"входы: {names[0]} … {names[-1]}" if names else "нет имён")
            if "prefix" in template:
                details.append(f"префикс: {cell(template['prefix'])}")
            if "allowed_types" in template:
                details.append("допустимый тип: " + cell(template["allowed_types"]))
            rows.append(f"| `{cell(prefix + name)}` | `{cell(kind)}` | {'нет' if group == 'optional' else 'да'} | {'; '.join(details) or 'соединение / значение без фиксированного default'} |")
            for branch in branches:
                if isinstance(branch, dict) and "inputs" in branch:
                    rows.extend(input_rows(branch["inputs"], f"{prefix}{name}={branch['key']} → "))
            if "input" in template:
                rows.extend(input_rows(template["input"], f"{prefix}{name} → "))
    return rows


def schema_table(definition):
    rows = ["## Входы и настройки", "", "Снимок ComfyUI 0.37.0. Условные поля показаны вместе с режимом, в котором они доступны; список установленных моделей зависит от вашей системы.", "", "| Вход | Тип | Обязательный | Значения из схемы |", "| --- | --- | --- | --- |", *input_rows(definition["input"]), "", "## Выходы", "", "| Выход | Тип | Список |", "| --- | --- | --- |"]
    for index, kind in enumerate(definition.get("output", [])):
        name = definition.get("output_name", definition["output"])[index]
        is_list = definition.get("output_is_list", [False] * len(definition["output"]))[index]
        rows.append(f"| `{cell(name)}` | `{cell(kind)}` | {'да' if is_list else 'нет'} |")
    return "\n".join(rows)


def source_location(node_id, definition):
    path = definition["python_module"].replace(".", "/") + ".py"
    raw = (SOURCE_ROOT / path).read_bytes()
    tree = ast.parse(raw.decode("utf-8-sig"))
    candidates = [node for node in tree.body if isinstance(node, ast.ClassDef) and (node.name == node_id or any(isinstance(x, ast.keyword) and x.arg == "node_id" and isinstance(x.value, ast.Constant) and x.value.value == node_id for x in ast.walk(node)))]
    if len(candidates) != 1:
        raise ValueError(f"Expected one source class for {node_id}: {len(candidates)}")
    node = candidates[0]
    return {"url": f"https://github.com/Comfy-Org/ComfyUI/blob/{COMMIT}/{path}#L{node.lineno}-L{node.end_lineno}", "path": path, "lines": f"{node.lineno}-{node.end_lineno}"}, hashlib.sha256(raw).hexdigest()


def main():
    assert len(ARTICLES) == sum(len(m.ARTICLES) for m in MODULES) == 64
    inventory = json.loads(INVENTORY.read_text(encoding="utf-8"))
    version = "0.1.92"
    workflows, occurrences = workflow_census(WHEEL)
    identities = {}
    for path in (CONTENT / "articles").rglob("manifest.json"):
        article = json.loads(path.read_text(encoding="utf-8"))
        identity = article.get("runtimeIdentity", {})
        if identity.get("packageId") == "comfy-core":
            identities[identity["classType"]] = article["articleId"]
    identities.update({key: "core." + slug(key) for key in ARTICLES})
    evidence = {"schemaVersion": "1.0", "comfyui": "0.37.0", "frontend": "1.52.7", "sourceCommit": COMMIT, "inventorySha256": hashlib.sha256(INVENTORY.read_bytes()).hexdigest(), "workflowTemplatesJson": version, "workflowWheelSha256": hashlib.sha256(WHEEL.read_bytes()).hexdigest(), "articles": {}}
    for node_id, (title, summary, controls, example, limitations, related) in sorted(ARTICLES.items()):
        definition = inventory[node_id]
        assert not definition.get("api_node") and not definition.get("dev_only"), node_id
        article_id = identities[node_id]
        location, source_hash = source_location(node_id, definition)
        cases = occurrences.get(node_id, [])
        cases = cases[:2]
        sources = [{"sourceId": article_id + "-source", "title": f"{node_id}: реализация ComfyUI 0.37.0", **{k: location[k] for k in ("url",)}, "publisher": "Comfy-Org", "kind": "source", "accessedAt": DATE, "supports": ["назначение", "параметры", "ограничения реализации"]}]
        case_sections = []
        if cases and node_id in CASE_NOTES:
            case_sections.append(CASE_NOTES[node_id])
        case_records = []
        for case in cases:
            workflow_id = case["workflowId"]
            before = ", ".join("`" + x["classType"] + "`" for x in case["upstream"]) or "нет входящих связей"
            after = ", ".join("`" + x["classType"] + "`" for x in case["downstream"]) or "нет исходящих связей"
            role = f"Граф: {case['graphName']} ({case['graphScope']}). Входящие связи: {before}. Исходящие связи: {after}."
            case_sections.append(f"В официальном шаблоне `{workflow_id}`: {role} Имя файла: `{workflow_id}.json`, пакет [workflow-templates-json 0.1.92]({WORKFLOW_URL}). SubgraphInput/Output обозначают границы подграфа. Это сохранённые связи; переключатели и внешние входы могут менять путь исполнения и значения виджетов. Полный запуск с весами здесь не выполнялся.")
            case_records.append({"id": workflow_id, "role": role})
        if cases:
            sources.append({"sourceId": article_id + "-workflow", "title": "Официальные workflow, пакет 0.1.92", "url": WORKFLOW_URL, "publisher": "Comfy-Org", "kind": "source", "accessedAt": DATE, "supports": ["реальные связи в шаблоне", "порядок этапов"]})
        else:
            case_sections.append("В проверенном пакете официальных workflow-templates-json 0.1.92 отдельного примера этой ноды не найдено. Схема выше составлена по реализации и контрактам входов; это не отчёт о выполненной генерации.")
        manifest = {
            "$schema": "../../../schemas/article.schema.v1.json", "schemaVersion": "1.0", "articleId": article_id, "kind": "core", "locale": "ru", "title": title, "summary": summary, "body": "ru.md",
            "runtimeIdentity": {"classType": node_id, "pythonModule": definition["python_module"], "packageId": "comfy-core", "origin": "backend", "aliases": []},
            "status": "draft", "experimental": bool(definition.get("experimental")),
            "compatibility": {"comfyui": ">=0.37.0", "frontend": ">=1.52.7", "verifiedOn": DATE, "sourceRevision": f"ComfyUI 0.37.0 @ {COMMIT}; frontend 1.52.7"},
            "relations": {"related": [identities[x] for x in related.split()], "alternatives": [], "replacedBy": None},
            "tags": ["ComfyUI", definition["category"], node_id], "searchAliases": list(dict.fromkeys([node_id, definition.get("display_name", node_id), *(definition.get("search_aliases") or [])])), "concepts": [title.split(":", 1)[-1].strip()], "assets": [],
            "editorial": {"state": "in_review", "owner": "TS Nodes Wizard editorial", "reviewedBy": "Source and runtime review; human approval pending", "reviewedAt": DATE, "factsReviewedAt": DATE, "schemaHash": schema_fingerprint(node_id, definition)}, "sources": sources,
        }
        body = f"# {title}\n\n{summary}\n\n## Как пользоваться\n\n{controls}\n\n## Пример подключения\n\n{example}\n\n## Ограничения и частые ошибки\n\n{limitations}\n\n{schema_table(definition)}\n\n## Проверенные источники и кейсы\n\n" + "\n\n".join(case_sections) + f"\n\n[Реализация в ComfyUI 0.37.0]({location['url']}). Параметры сверены со снимком `/object_info` от 27 сентября 2026 года.\n\nСтатья прошла техническую и языковую подготовку; человеческое утверждение ещё не выполнено. Полная генерация с моделями в рамках этой проверки не запускалась.\n"
        directory = CONTENT / "articles/core" / slug(node_id)
        directory.mkdir(parents=True, exist_ok=True)
        write_json(directory / "manifest.json", manifest)
        (directory / "ru.md").write_text(body, encoding="utf-8", newline="\n")
        review = {"$schema": "../../schemas/article-research.schema.v1.json", "schemaVersion": "1.0", "articleId": article_id, "node": {"classType": node_id, "pythonModule": definition["python_module"], "origin": "backend"}, "baseline": {"comfyui": "0.37.0", "frontend": "1.52.7", "sourceCommit": COMMIT, "embeddedDocs": "0.5.12 (available; implementation is primary)", "workflowTemplatesJson": version}, "state": "source_reviewed", "reviewMode": "automated_assisted", "evidence": {"runtimeInventory": "runtime/comfyui-0.37.0.object-info.json", "sourceLocations": [location], "embeddedDocs": [], "workflows": case_records}, "checks": {"implementationRead": True, "runtimeCompared": True, "officialCasesInspected": bool(cases), "exampleSchemaValidated": False, "exampleExecuted": False, "russianEdited": True, "factsRecheckedAfterEditing": True}, "knownGaps": ["Human editorial approval pending", "Full model workflow execution not performed", "Worked example is explanatory, not an executable validated recipe"] + ([] if cases else ["No direct occurrence in pinned official workflow templates"]), "updatedAt": DATE}
        write_json(CONTENT / "research/reviews" / (article_id + ".json"), review)
        evidence["articles"][node_id] = {"articleId": article_id, "schemaHash": manifest["editorial"]["schemaHash"], "source": {**location, "fileSha256": source_hash}, "workflows": [{**case, **workflows[case["workflowId"]]} for case in cases]}
    write_json(CONTENT / "research/september-2026-articles.json", evidence)
    print(f"Wrote {len(ARTICLES)} authored articles; {sum(bool(v['workflows']) for v in evidence['articles'].values())} have inspected official workflow cases.")


if __name__ == "__main__":
    main()
