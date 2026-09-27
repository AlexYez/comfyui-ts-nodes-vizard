#!/usr/bin/env python3
"""Import pinned Timesaver-owned pack documentation into the Wizard catalog.

This is an editorial import tool, not part of the runtime package.  It reads
checked-out source repositories, extracts their registered execution IDs, and
writes deterministic draft articles plus research records.  Upstream Russian
node docs remain the factual body; Wizard adds provenance and catalog metadata.
"""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
import re
from pathlib import Path
from september_timesaver_guides import GUIDES


ROOT = Path(__file__).resolve().parents[1]
CONTENT = ROOT / "content"
ACCESSED = "2026-09-27"
BASELINE_COMFY = "0.32.0"
BASELINE_FRONTEND = "1.48.7"

PACKS = {
    "timesaver": {
        "slug": "comfyui-timesaver",
        "commit": "c1668b3cfa2161e36bf9b9fa91288b949b4b0b1f",
        "repo": "AlexYez/comfyui-timesaver",
        "version": "12.11.7",
    },
    "cosyvoice": {
        "slug": "comfyui-ts-cosyvoice",
        "commit": "89c8ac96b55daad077c7c9cf0e89304b99766c3a",
        "repo": "AlexYez/comfyui-ts-cosyvoice",
        "version": "1.4.1",
    },
}

STUDIO_GUIDES = {
    "TS_ImageStudio": ("открывает полноэкранный интерфейс TS Image Studio и возвращает последний сохранённый результат как IMAGE", "Добавьте одну ноду в граф, нажмите Open Interface и запускайте выбранный backend из студии. Скрытые `session_id` и `result_path` связывают ноду с галереей сессии; пустой путь даёт пустой IMAGE 1×1."),
    "TS_StudioInputText": ("помечает строковый параметр backend-графа, например prompt", "Студия находит маркер по `param_name`, подставляет значение из деки и отправляет изменённый API-граф. При ручном запуске нода просто возвращает `value`, поэтому шаблон остаётся исполнимым вне студии."),
    "TS_StudioInputNumber": ("помечает числовой параметр и одновременно отдаёт FLOAT и округлённый INT", "Подключайте нужный выход к параметру backend-графа. `param_name` связывает маркер с контролом манифеста; целочисленный выход использует округление, а не усечение."),
    "TS_StudioInputSeed": ("передаёт 64-битный seed из интерфейса студии в backend-граф", "Используйте маркер вместо литерала seed в sampler. В обычном графе он возвращает введённое значение, а перед запуском из студии frontend заменяет его seed текущего задания."),
    "TS_StudioInputImage": ("загружает исходное изображение по annotated-пути и отдаёт IMAGE вместе с MASK", "Это точка подстановки для img2img, edit, inpaint и upscale backend. Студия подготавливает файл и заменяет `value`; при ручной проверке выберите входное изображение так же, как у штатного загрузчика."),
    "TS_StudioInputMask": ("загружает маску рисования по annotated-пути", "Маркер применяется в inpaint-backend. Белая область означает зону обработки в цепочке студии; перед ручным запуском убедитесь, что маска относится к тому же кадру и имеет ожидаемый размер."),
    "TS_StudioLoraStack": ("оставляет место, куда студия встраивает выбранную цепочку LoRA", "Без подстановки нода пропускает MODEL без изменений. В backend-шаблоне ставьте её после загрузки модели; frontend заменяет маркер цепочкой loader-нод для выбранных LoRA."),
    "TS_StudioManifest": ("хранит JSON-описание режима, контролов, моделей и зависимостей backend-шаблона", "Манифест читается при построении деки и удаляется из API-графа перед отправкой. При ручном запуске он лишь возвращает строку JSON; генерацию не меняет."),
    "TS_StudioOutput": ("сохраняет финальный IMAGE и возвращает UI-превью с метаданными сессии", "Ставьте ноду в конце каждого backend-шаблона. Она пишет результат по студийному префиксу и добавляет чанк `ts_studio`, благодаря которому Artius Browser и сама студия могут восстановить сессию."),
    "TS_StudioInpaintCrop": ("вырезает область вокруг белой маски, готовит жёсткую и мягкую маски и план обратной вставки", "Передайте полный кадр и маску; `context`, `padding`, ограничения размера и feather определяют рабочий crop. Выход `plan` обязателен для парной TS Studio Inpaint Restore. Пустая маска возвращает исходник и пустые маски без выдуманной области."),
    "TS_StudioInpaintRestore": ("возвращает обработанный crop в исходный кадр по плану из TS Studio Inpaint Crop", "Подайте исходный `image`, перерисованный `patch` и тот же `plan`. Нода масштабирует patch к области и смешивает его мягкой маской; чужой или потерянный plan нельзя восстановить по одному crop."),
}

STUDIO_RELATED = {
    "TS_ImageStudio": ["custom.comfyui-timesaver.ts-studiooutput", "custom.comfyui-artius-browser.artius-browser"],
    "TS_StudioInpaintCrop": ["custom.comfyui-timesaver.ts-studioinpaintrestore"],
    "TS_StudioInpaintRestore": ["custom.comfyui-timesaver.ts-studioinpaintcrop"],
}


def dump(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8")


def slugify(value: str) -> str:
    value = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return value or hashlib.sha256(value.encode()).hexdigest()[:12]


def dict_string_keys(node: ast.AST) -> list[str]:
    if not isinstance(node, ast.Dict):
        return []
    return [key.value for key in node.keys if isinstance(key, ast.Constant) and isinstance(key.value, str)]


def literal_string_dict(node: ast.AST) -> dict[str, str]:
    if not isinstance(node, ast.Dict):
        return {}
    result: dict[str, str] = {}
    for key, value in zip(node.keys, node.values):
        if isinstance(key, ast.Constant) and isinstance(key.value, str) and isinstance(value, ast.Constant) and isinstance(value.value, str):
            result[key.value] = value.value
    return result


def timesaver_nodes(repo: Path) -> list[dict[str, object]]:
    nodes: list[dict[str, object]] = []
    for path in sorted((repo / "nodes").rglob("ts_*.py")):
        if any(part.startswith("_") for part in path.relative_to(repo / "nodes").parts):
            continue
        tree = ast.parse(path.read_text(encoding="utf-8-sig"))
        mappings: list[str] = []
        displays: dict[str, str] = {}
        mapping_line = 1
        for item in tree.body:
            if not isinstance(item, ast.Assign):
                continue
            names = [target.id for target in item.targets if isinstance(target, ast.Name)]
            if "NODE_CLASS_MAPPINGS" in names:
                mappings = dict_string_keys(item.value)
                mapping_line = item.lineno
            if "NODE_DISPLAY_NAME_MAPPINGS" in names:
                displays = literal_string_dict(item.value)
        rel = path.relative_to(repo).as_posix()
        for class_type in mappings:
            docs = repo / "js" / "docs" / class_type / "ru.md"
            nodes.append({
                "classType": class_type,
                "displayName": displays.get(class_type, class_type),
                "pythonModule": "custom_nodes.comfyui-timesaver",
                "sourcePath": rel,
                "sourceLine": mapping_line,
                "documentationPath": docs.relative_to(repo).as_posix() if docs.exists() else None,
            })
    return nodes


def cosyvoice_nodes(repo: Path) -> list[dict[str, object]]:
    nodes: list[dict[str, object]] = []
    pattern = re.compile(r'node_id="([^"]+)"[\s\S]{0,180}?display_name="([^"]+)"')
    for path in sorted((repo / "nodes").glob("ts_*_node.py")):
        text = path.read_text(encoding="utf-8-sig")
        match = pattern.search(text)
        if not match:
            continue
        class_type, display_name = match.groups()
        line = text[: match.start()].count("\n") + 1
        docs = repo / "web" / "docs" / class_type / "ru.md"
        nodes.append({
            "classType": class_type,
            "displayName": display_name,
            "pythonModule": "custom_nodes.comfyui-ts-cosyvoice",
            "sourcePath": path.relative_to(repo).as_posix(),
            "sourceLine": line,
            "documentationPath": docs.relative_to(repo).as_posix() if docs.exists() else None,
        })
    return nodes


def clean_body(text: str, title: str, source_url: str, pack_title: str) -> str:
    text = text.strip().replace("\r\n", "\n")
    if not text.startswith("# "):
        text = f"# {title}\n\n{text}"
    text = re.sub(r"\n---\s*\n[\s\S]*?Полный справочник нод:[^\n]*$", "", text).rstrip()
    return (
        text
        + "\n\n## Проверка и происхождение материала\n\n"
        + f"Материал импортирован из встроенной справки `{pack_title}` на {ACCESSED}; регистрация ноды проверена по исходнику. "
        + "Статья имеет статус черновика до отдельной ручной редакционной проверки в Wizard. "
        + "Если установлена другая версия пака, ориентируйтесь также на живые входы и выходы в панели.\n\n"
        + f"- [Закреплённый исходник ноды]({source_url})\n"
    )


def fallback_body(node: dict[str, object], source_url: str, pack_title: str) -> str:
    title = str(node["displayName"])
    if str(node["classType"]) not in STUDIO_GUIDES:
        raise ValueError(f"No documentation or reviewed guide for {node['classType']}")
    purpose, usage = STUDIO_GUIDES[str(node["classType"])]
    return f"""# {title}

## Что делает нода

`{node['classType']}` {purpose}. Это часть TS Image Studio: frontend собирает обычный API-граф из JSON-шаблона и запускает его через стандартную очередь ComfyUI.

## Когда она нужна

{usage}

Маркерные ноды можно открыть и выполнить вручную: это позволяет отлаживать backend как обычный workflow. Но в штатной работе значения подставляет студия, поэтому удаление `param_name`, манифеста или парной служебной связи ломает автоматическую сборку.

## Практическая проверка

Реальный кейс находится в `js/image/studio/workflows`: студия использует эти ноды в шаблонах text-to-image, edit, inpaint, outpaint и upscale. Сохраняйте соседние связи и виджеты. Отдельный искусственный workflow не приводится: для служебной ноды он исказил бы назначение.

## Ограничения и диагностика

Шаблоны зависят от точных `classType` и `param_name`. Переименование маркера, неподходящий тип выхода или удаление `plan` приводят к ошибке ещё до либо во время исполнения. При несовпадении версии Wizard пометит схему как изменившуюся. Подробности реализации смотрите в закреплённом исходнике и архитектурной карте студии.

## Проверка и происхождение материала

Регистрация подтверждена статическим разбором `NODE_CLASS_MAPPINGS` на commit пака от {ACCESSED}. Ручная редакционная проверка и отдельный практический кейс ещё нужны.

- [Закреплённый исходник ноды]({source_url})
- [Архитектура TS Image Studio](https://github.com/AlexYez/comfyui-timesaver/blob/{PACKS['timesaver']['commit']}/nodes/image/studio/ARCHITECTURE.md)
"""


def article_and_review(pack: dict[str, str], node: dict[str, object], repo_path: Path) -> tuple[dict, str, dict]:
    class_type = str(node["classType"])
    display_name = str(node["displayName"])
    article_id = f"custom.{slugify(pack['slug'])}.{slugify(class_type)}"
    source_path = str(node["sourcePath"])
    line = int(node["sourceLine"])
    source_url = f"https://github.com/{pack['repo']}/blob/{pack['commit']}/{source_path}#L{line}"
    docs_path = node.get("documentationPath")
    if docs_path:
        body = clean_body((repo_path / str(docs_path)).read_text(encoding="utf-8-sig"), display_name, source_url, pack["slug"])
    else:
        body = fallback_body(node, source_url, pack["slug"])
    if pack["slug"] == "comfyui-timesaver" and class_type in GUIDES:
        body = f"# {display_name}\n\n{GUIDES[class_type]}\n\n## Источники и границы проверки\n\nОписание подготовлено по исходнику и справке TimeSaver 12.11.7. Полное выполнение с моделями и человеческое утверждение ещё не проведены.\n\n- [Реализация ноды]({source_url})\n- [Справка автора пака](https://github.com/{pack['repo']}/blob/{pack['commit']}/{docs_path})\n"
    first_paragraph = next((re.sub(r"[`*_]", "", p).replace("\n", " ") for p in body.split("\n\n") if p and not p.startswith("#")), "")
    summary = first_paragraph[:357].rstrip() + ("…" if len(first_paragraph) > 357 else "")
    manifest = {
        "$schema": "../../../../schemas/article.schema.v1.json", "schemaVersion": "1.0", "articleId": article_id,
        "kind": "custom", "locale": "ru", "title": display_name, "summary": summary, "body": "ru.md",
        "runtimeIdentity": {"classType": class_type, "pythonModule": node["pythonModule"], "packageId": pack["slug"], "origin": "backend", "aliases": []},
        "status": "draft", "experimental": pack["slug"] == "comfyui-timesaver" and class_type == "TS_NAG",
        "compatibility": {"comfyui": ">=0.32.0", "frontend": ">=1.48.7", "verifiedOn": ACCESSED, "sourceRevision": f"{pack['slug']} {pack['version']} @ {pack['commit']}"},
        "relations": {"related": STUDIO_RELATED.get(class_type, (["custom.comfyui-timesaver.ts-imagestudio"] if class_type.startswith("TS_Studio") else [])), "alternatives": [], "replacedBy": None},
        "tags": ["custom nodes", pack["slug"], class_type], "searchAliases": list(dict.fromkeys([class_type, display_name])),
        "concepts": ["сторонняя нода ComfyUI"], "assets": [],
        "editorial": {"state": "in_review", "owner": "TS Nodes Wizard editorial", "reviewedBy": "Pinned upstream source and embedded Russian documentation; human approval pending", "reviewedAt": ACCESSED, "factsReviewedAt": ACCESSED},
        "sources": [{"sourceId": f"{article_id}-source-1", "title": f"{display_name} in {pack['slug']} {pack['version']}", "url": source_url, "publisher": "AlexYez", "kind": "source", "accessedAt": ACCESSED, "supports": ["runtime registration", "implementation"]}],
    }
    if docs_path:
        manifest["sources"].append({"sourceId": f"{article_id}-source-2", "title": f"Embedded Russian documentation for {display_name}", "url": f"https://github.com/{pack['repo']}/blob/{pack['commit']}/{docs_path}", "publisher": "AlexYez", "kind": "documentation", "accessedAt": ACCESSED, "supports": ["usage", "parameters", "limitations"]})
    elif pack["slug"] == "comfyui-timesaver" and class_type in STUDIO_GUIDES:
        manifest["sources"].append({"sourceId": f"{article_id}-source-2", "title": "TS Image Studio architecture and execution path", "url": f"https://github.com/{pack['repo']}/blob/{pack['commit']}/nodes/image/studio/ARCHITECTURE.md", "publisher": "AlexYez", "kind": "documentation", "accessedAt": ACCESSED, "supports": ["marker roles", "backend workflows", "execution path", "studio integration"]})
    review = {
        "$schema": "../../schemas/article-research.schema.v1.json", "schemaVersion": "1.0", "articleId": article_id,
        "node": {"classType": class_type, "pythonModule": node["pythonModule"], "origin": "backend"},
        "baseline": {"comfyui": BASELINE_COMFY, "frontend": BASELINE_FRONTEND, "sourceCommit": pack["commit"], "embeddedDocs": f"{pack['slug']} built-in docs", "workflowTemplatesJson": f"{pack['slug']} examples at pinned commit"},
        "state": "source_reviewed", "reviewMode": "automated_assisted",
        "evidence": {"runtimeInventory": f"content/inventory/custom/{pack['slug']}.json", "sourceLocations": [{"url": source_url, "path": source_path, "lines": f"{line}+"}], "embeddedDocs": ([{"locale": "ru", "archivePath": str(docs_path), "assessment": "Primary pack documentation imported and attributed"}] if docs_path else []), "workflows": []},
        "checks": {"implementationRead": False, "runtimeCompared": False, "officialCasesInspected": False, "exampleSchemaValidated": False, "exampleExecuted": False, "russianEdited": False, "factsRecheckedAfterEditing": False},
        "knownGaps": ["Human editorial approval pending"] + ([] if docs_path else ["No dedicated upstream article or verified standalone recipe"]), "updatedAt": ACCESSED,
    }
    return manifest, body, review


def write_pack(pack_key: str, repo: Path, nodes: list[dict[str, object]]) -> None:
    pack = PACKS[pack_key]
    inventory = {"schemaVersion": "1.0", "packageId": pack["slug"], "repository": f"https://github.com/{pack['repo']}", "sourceCommit": pack["commit"], "version": pack["version"], "capturedAt": ACCESSED, "nodes": nodes}
    dump(CONTENT / "inventory" / "custom" / f"{pack['slug']}.json", inventory)
    for node in nodes:
        manifest, body, review = article_and_review(pack, node, repo)
        directory = CONTENT / "articles" / "custom" / slugify(pack["slug"]) / slugify(str(node["classType"]))
        dump(directory / "manifest.json", manifest)
        (directory / "ru.md").write_text(body, encoding="utf-8")
        dump(CONTENT / "research" / "reviews" / f"{manifest['articleId']}.json", review)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--timesaver", type=Path)
    parser.add_argument("--cosyvoice", type=Path)
    args = parser.parse_args()
    if not args.timesaver and not args.cosyvoice:
        parser.error("Select at least one source repository")
    for key, repo, extract, count in (("timesaver", args.timesaver, timesaver_nodes, 89), ("cosyvoice", args.cosyvoice, cosyvoice_nodes, 7)):
        if repo is None:
            continue
        import subprocess
        commit = subprocess.check_output(["git", "-c", f"safe.directory={repo.resolve().as_posix()}", "-C", str(repo), "rev-parse", "HEAD"], text=True).strip()
        if commit != PACKS[key]["commit"]:
            raise SystemExit(f"{key}: checkout does not match pinned source commit")
        nodes = extract(repo)
        if len(nodes) != count:
            raise SystemExit(f"Unexpected {key} inventory size: {len(nodes)} != {count}")
        write_pack(key, repo, nodes)
        print(f"Imported {len(nodes)} {key} articles")


if __name__ == "__main__":
    main()
