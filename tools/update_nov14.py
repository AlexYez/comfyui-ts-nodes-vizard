"""Pinned 14 November catalog update. Preserves historical review records."""
import copy
import hashlib
import re
from pathlib import Path
import catalog as c
import build_september_articles as t
import import_custom_pack_articles as p
from update_november_catalog import prepend_update
from nov14_content import CORE

DATE = "2026-11-14"
COMMIT = "989d93d0d968e704c589ce0146bb18c77f6b50cc"
TS = "18c863d206a537c8d60c8db6d1c7dbdf4a29721a"
NOTES = {
"TS_Compare": "Ручка, подписи и кнопки сравнения показываются после загрузки обеих картинок или первого кадра видео. Пустое превью остаётся без контроллеров, в том числе если временные файлы прошлого результата недоступны. Это не означает, что прежний файл сохранён в постоянном output.",
"TS_VideoLoader": "Предпросмотр через копию используется для кодеков вне поддерживаемого браузером набора H.264, VP8, VP9 и AV1. Выходные кадры и обрезка берутся из оригинала, не из копии H.264. На сетевом сервере доступ к превью ограничивается разрешёнными корнями; изменение TS_MEDIA_ALLOW_ANY_PATH расширяет доступ и требует осознанной настройки владельцем сервера. Не публикуйте ComfyUI в интернете без отдельной защиты доступа.",
"TS_H3RegenerateModel": "Текущий загрузчик Standard принимает чистую pruned H3 и один complete-файл open_h3_regenerate_2k_lora_complete.safetensors. Он уже содержит LoRA, 50 веток Sharp и проверенную таблицу AdaLN; отдельные sharp_name и reference_checkpoint больше не требуются в пользовательской ноде. При переносе старого графа заново выберите complete-файл. Обычный LoRA Loader не заменяет этот загрузчик, поскольку не применяет специальные Sharp-ветки. Веса не входят в пак; инструкция сборки из исходных файлов приведена в текущей справке автора.",
"TS_ResolutionSelector": "Начальное значение — 1,5 Мп, текущий рабочий диапазон по умолчанию 0,1–4 Мп. max_megapixels задаётся в Properties отдельно для ноды и сохраняется в workflow. Выход остаётся IMAGE с размерами, кратными 32; для LATENT нужен VAE Encode. Рабочий диапазон интерфейса не является обещанием, что выбранная модель поместится в память.",
"TS_EditAlign": "Для p-h3-image и других edit-цепочек используйте как source тот же подготовленный холст, который подаётся в conditioning, а не исходник другого размера или обрезки. При намеренной смене ракурса или композиции отключите выравнивание: оно предназначено для исправления небольшого геометрического сдвига, не для отмены художественной правки.",
"TS_RTX_Upscaler": "Для новой установки используется NVIDIA VFX 0.2 из индекса NVIDIA; на обычном PyPI может находиться пакет-заглушка. Дополнительная зависимость rtx-upscaler ограничивает версию диапазоном >=0.2.0.0,<0.3. Адаптер понимает старый API 0.1, но совместимость SDK и драйвера проверяйте для своего окружения. Измерения ускорения автора относятся к его оборудованию.",
"TS_BatchSource": "Добавлен repeats: задания повторяются подряд A,A,A,B,B,B, а не обходом всей папки. start_at и limit считают позиции после повторов; total — оставшиеся выбранные задания. При repeats=3 для 20 прочитанных промптов и one_per_run нужно 60 запусков очереди. Подключите выход seed к сэмплеру, чтобы повторные варианты получали разные производные seed. count в режиме чтения промптов не задаёт количество найденных файлов.",
"TS_PromptBuilder": "Текущая реализация больше не использует семантические карты и подпапки. Читает .txt непосредственно из nodes/prompts: включённый TXT-блок даёт одну непустую строку, текстовый блок — ваш текст; порядок блоков определяет порядок промпта. Редактор хранит текст и порядок в config_json workflow. Seed 0 даёт новую выборку; положительный seed воспроизводит строки файлов. Изменение своего текста не должно менять выбор другого файла. Старые обещания семантического согласования паков к этой версии не относятся.",
"TS_H3Regenerate": "Шум теперь подаётся отдельным NOISE от Random Noise, seed задаётся там. Появились режимы first and last frames, connected frames (auto) и экспериментальный full reference (Ref2VA). Последний использует уже закодированные референсы positive и требует чистую pruned Ref2VA через Regenerate Model. При denoise 0 референсы отключены. В continue (blend overlap) часть перекрытия фиксируется, оставшаяся пересчитывается и смешивается; проверяйте швы и накопление изменений. Подробные условия текущих режимов приведены в закреплённой справке автора ниже; прежний перечень режимов неполон.",
"TS_H3FastVAEDecode": "Поддержан Fast V2 и режимы auto, fast, low VRAM. В auto при нехватке памяти используется подключённый fallback VAE, а без него пробуется low VRAM. Low VRAM ограничивает одновременно хранимые Q/K/V, не сокращая число кадров. Отдельный Fast-декодер по-прежнему не кодирует картинки; объединённый файл с классическим энкодером и Fast V2 можно использовать через штатный Load VAE. Проверяйте яркость на границах 17-кадровых блоков.",
"TS_DLSSUpscaler": "По умолчанию остаётся v9 (built-in). Для v21 (external CLI) приложение устанавливается отдельно в runtime/visual-enhancer/v21; нода его не скачивает. Разрешены относительные пути внутри пака, не абсолютные и не ../. Внешний режим имеет свои ограничения NR-настроек и временной стабилизации; диапазон tone/structure/skin — 0–1. Транспорт PNG16/FFV1 не является гарантией точности обработки самим приложением. Перед использованием сверяйтесь с инструкцией и лицензией выбранного приложения.",
"TS_SuperPromptRT": "Рекомендуемый API рантайма обновлён до litert-lm-api 0.19.0. Старый CLI 0.16.1 может конфликтовать с ним; не удаляйте CLI, если он нужен другим задачам. Проверяйте окружение тем Python, которым запускается ComfyUI. MTP остаётся выключенным по умолчанию: результаты прежней проверки 0.16.1 нельзя переносить на 0.19.0 как универсальное свойство.",
"TS_RTPromptEnhancer": "Анализ нескольких кадров не равен просмотру видео с точной временной шкалой: модель может ошибаться в направлении движения. В аудио распознавание речи не означает надёжного распознавания инструментов, невербальных звуков или числа событий. Для точной расшифровки выбирайте transcribe и сверяйте названия с записью; инструкция пресета не устраняет ограничений модели.",
}


def main():
    cap = c.ROOT / ".upstream-cache/nov14-inventory/comfyui-inventory-v0.45.0"
    files = {}
    for name in ("object-info.json", "system-stats.json", "node-replacements.json"):
        target = c.CONTENT / "runtime" / ("comfyui-0.45.0." + name)
        raw = (cap / name).read_bytes()
        target.write_bytes(raw)
        files[target.name] = {"sha256": hashlib.sha256(raw).hexdigest(), "size": len(raw)}
    c.write_json(c.CONTENT / "runtime/comfyui-0.45.0.capture.json", {"capturedAt": DATE, "sourceCommit": COMMIT, "artifactRun": "https://github.com/AlexYez/comfyui-ts-nodes-vizard/actions/runs/43578336810", "files": files, "qualification": "Clean CPU inventory, not model workflow execution"})
    inv = c.object_info_nodes(c.load_json(cap / "object-info.json"))
    old = c.object_info_nodes(c.load_json(c.CONTENT / "runtime/comfyui-0.43.0.object-info.json"))
    existing = {m["runtimeIdentity"]["classType"]: (path, m) for path in (c.CONTENT / "articles/core").glob("*/manifest.json") if (m := c.load_json(path))}
    t.SOURCE_ROOT, t.COMMIT = c.ROOT / ".comfyui-source-0.45.0", COMMIT
    added = []
    for key, (title, prose) in CORE.items():
        path = c.CONTENT / "articles/core" / t.slug(key) / "manifest.json"
        m = copy.deepcopy(existing["TextGenerateV2"][1] if "TextGenerateV2" in existing else existing["TextEncodeFibo2"][1])
        aid = "core." + t.slug(key)
        m.update(articleId=aid, title=title, summary=re.sub(r"[`*_]", "", prose.split("\n\n")[0]), assets=[], status="draft", experimental=bool(inv[key].get("experimental")), searchAliases=[key, title], tags=[key, inv[key]["category"]], concepts=[title])
        m["runtimeIdentity"].update(classType=key, pythonModule=inv[key]["python_module"], aliases=[])
        m["relations"] = {"related": [], "alternatives": [], "replacedBy": None}
        m["editorial"].update(state="in_review", schemaHash=c.schema_fingerprint(key, inv[key]), reviewedAt=DATE, factsReviewedAt=DATE, reviewedBy="Pinned implementation review; human approval pending")
        m["compatibility"].update(comfyui=">=0.45.0", frontend=">=1.58.5", verifiedOn=DATE, sourceRevision=f"ComfyUI 0.45.0 @ {COMMIT}")
        if key == "MiniMaxH3ContextWindows":
            source_path = "comfy_extras/nodes_context_windows.py"
            loc = {"url": f"https://github.com/Comfy-Org/ComfyUI/blob/{COMMIT}/{source_path}", "path": source_path, "lines": "MiniMaxH3ContextWindowsNode and ContextWindowsManualNode"}
        else:
            loc, _ = t.source_location(key, inv[key])
        m["sources"] = [{"sourceId": aid + "-source", "title": key + " in ComfyUI 0.45.0", "url": loc["url"], "publisher": "Comfy-Org", "kind": "source", "accessedAt": DATE, "supports": ["назначение", "входы и выходы", "ограничения реализации"]}]
        c.write_json(path, m)
        (path.parent / "ru.md").write_text(f"# {title}\n\n{prose.strip()}\n\n" + t.schema_table(inv[key]).replace("Снимок ComfyUI 0.37.0", "Снимок ComfyUI 0.45.0") + f"\n\n## Источники и границы проверки\n\n[Закреплённая реализация]({loc['url']}). Входы и выходы сверены с чистым серверным снимком. Пример поясняет подключение; генерация с весами не выполнялась, человеческое утверждение ещё нужно.\n", encoding="utf-8", newline="\n")
        ledger = copy.deepcopy(c.load_json(c.CONTENT / "research/reviews/core.text-encode-fibo2.json"))
        ledger.update(articleId=aid, updatedAt=DATE)
        ledger["node"].update(classType=key, pythonModule=inv[key]["python_module"])
        ledger["baseline"].update(comfyui="0.45.0", frontend="1.58.5", sourceCommit=COMMIT, workflowTemplatesJson="not inspected in this update", embeddedDocs="implementation primary")
        ledger["evidence"].update(runtimeInventory="runtime/comfyui-0.45.0.object-info.json", sourceLocations=[loc], workflows=[])
        c.write_json(c.CONTENT / "research/reviews" / (aid + ".json"), ledger)
        added.append(aid)
    for key in sorted(old.keys() & inv.keys()):
        if key not in existing or c.schema_fingerprint(key, old[key]) == c.schema_fingerprint(key, inv[key]):
            continue
        path, m = existing[key]
        loc, _ = t.source_location(key, inv[key])
        notes = {
            "CreateVideo": "Добавлен chroma_subsampling: 444 сохраняет цветовое разрешение, 422 уменьшает его по горизонтали, 420 по обеим осям. Auto использует выбор кодека; неподдерживаемый вариант заменяется ближайшим с предупреждением. Это не битовая глубина и не цветовое пространство.",
            "TextGenerate": "Прежняя Generate Text помечена устаревшей. Для новых графов используйте TextGenerateV2 с несколькими медиавходами; старые графы не нужно подменять по одному display_name без проверки портов.",
            "RenderMesh": "Добавлен world normal для текстурирования, camera_info принимает список камер, а texture позволяет показать отдельную текстуру без изменения mesh. Виды для запекания должны использовать те же камеры и порядок кадров.",
            "ResolutionSelector": "Шаг megapixels теперь 0,01. Это настройка площади, а не гарантия точного совпадения конечного числа пикселей после округления к сетке.",
            "SplatToMesh": "Обновлены параметры построения поверхности. Resolution задаёт плотностную сетку с кубическим ростом памяти; smooth выполняет Taubin-сглаживание. Level смещает автоматически выбранный порог, а color_sharpen влияет на цвет, не геометрию. Solid заполняет внутреннюю область по ориентации гауссиан. Проверяйте тонкие детали и замкнутость результата.",
        }
        note = notes.get(key, "Изменилась серверная схема; сверяйте текущие порты в живой схеме.") + " Ниже сохранён текст предыдущей проверенной версии; полная повторная проверка статьи не заявляется."
        body = (path.parent / "ru.md").read_text(encoding="utf-8")
        (path.parent / "ru.md").write_text(prepend_update(body, "nov14", f"**ComfyUI 0.45.0.** {note}\n\n[Изменённая реализация]({loc['url']})."), encoding="utf-8", newline="\n")
    pairs = [("CreateCameraOrbit", "BatchCameras"), ("CreateCameraOrbit", "BakeTextureFromViews"), ("UltraTexConditioning", "BakeTextureFromViews"), ("RelayVSRConditioning", "VSRDecode"), ("MiniMaxH3ContextWindows", "MiniMaxH3LatentUpscaleWithModel"), ("MiniMaxH3ImageConditioning", "PH3ImageConditioning")]
    for key in CORE:
        path = c.CONTENT / "articles/core" / t.slug(key) / "manifest.json"
        m = c.load_json(path)
        m["relations"]["related"] = ["core." + t.slug(b if a == key else a) for a, b in pairs if key in (a, b)]
        c.write_json(path, m)
    repo = c.ROOT / ".upstream-cache/timesaver-nov14"
    replacements = c.load_json(cap / "node-replacements.json")
    assert any(x.get("new_node_id") == "TextGenerateV2" for x in replacements.get("TextGenerate", []))
    old_path, old_article = existing["TextGenerate"]
    old_article["relations"]["replacedBy"] = "core." + t.slug("TextGenerateV2")
    c.write_json(old_path, old_article)
    nodes = p.timesaver_nodes(repo)
    for n in nodes:
        path = c.CONTENT / "articles/custom/comfyui-timesaver" / p.slugify(n["classType"]) / "manifest.json"
        m = c.load_json(path)
        if n["classType"] in NOTES:
            url = f"https://github.com/AlexYez/comfyui-timesaver/blob/{TS}/{n['sourcePath']}"
            docs = f"https://github.com/AlexYez/comfyui-timesaver/blob/{TS}/{n['documentationPath']}"
            body = (path.parent / "ru.md").read_text(encoding="utf-8")
            (path.parent / "ru.md").write_text(prepend_update(body, "nov14", f"**TimeSaver 12.13.12.** {NOTES[n['classType']]}\n\n[Реализация]({url}) · [Текущая справка автора]({docs}). Дополнение не означает полного повторного утверждения старого текста."), encoding="utf-8", newline="\n")
        m["compatibility"]["sourceRevision"] = f"TimeSaver 12.13.12 @ {TS}; source inventory only"
        m["sources"] = [{**s, "url": re.sub(r"/blob/[a-f0-9]{40}/", f"/blob/{TS}/", s["url"])} for s in m["sources"]]
        c.write_json(path, m)
    c.write_json(c.CONTENT / "inventory/custom/comfyui-timesaver.json", {"schemaVersion": "1.0", "packageId": "comfyui-timesaver", "repository": "https://github.com/AlexYez/comfyui-timesaver", "sourceCommit": TS, "version": "12.13.12", "capturedAt": DATE, "nodes": nodes})
    manifest = c.load_json(c.CATALOG_MANIFEST)
    manifest["generatedAt"] = DATE + "T00:00:00Z"
    manifest["catalogVersion"] = "0.3.4"
    manifest["articles"] = sorted(x.relative_to(c.CONTENT).as_posix() for x in (c.CONTENT / "articles").glob("**/manifest.json"))
    c.write_json(c.CATALOG_MANIFEST, manifest)
    report = c.inventory_report(c.CONTENT / "runtime/comfyui-0.45.0.object-info.json", c.CONTENT / "runtime/comfyui-0.45.0.node-replacements.json", c.CONTENT / "runtime/comfyui-0.45.0.system-stats.json", c.CONTENT / "runtime/comfyui-0.43.0.object-info.json")
    report["inventory"]["path"] = "content/runtime/comfyui-0.45.0.object-info.json"
    report["baseline"]["path"] = "content/runtime/comfyui-0.43.0.object-info.json"
    c.write_json(c.CONTENT / "runtime/comfyui-0.45.0.inventory-report.json", report)
    update_path = c.CONTENT / "update-manifest.json"
    update = c.load_json(update_path)
    update.update(catalogVersion="0.3.4", publishedAt=DATE + "T00:00:00Z", signature=None)
    update["inventory"].update(source="runtime/comfyui-0.45.0.object-info.json", comfyuiVersion="0.45.0", frontendVersion="1.58.5", capturedAt=DATE + "T00:00:00Z")
    update["changes"]["added"] = sorted(set(update["changes"]["added"]) | set(added))
    update["changes"]["summary"] = "Ноябрьские обновления: новые локальные ноды до ComfyUI 0.45.0, дополнения TimeSaver 12.13.12 и тематические ссылки NeuroSaver. Alpha; полное человеческое утверждение не выполнено."
    c.write_json(update_path, update)
    c.write_json(c.CONTENT / "research/nov14-2026-update.json", {"checkedThrough": DATE, "comfyui": "0.45.0", "frontend": "1.58.5", "sourceCommit": COMMIT, "timesaver": "12.13.12", "timesaverCommit": TS, "addedArticles": added, "timesaverNewNodes": [], "targetedTimesaverNotes": sorted(NOTES), "scope": "13 new guides; targeted warnings and additions. Not full review of historical content or all changed pack implementations.", "exampleExecuted": False, "humanApproved": False})
    print("Added", len(added), "articles; total", len(manifest["articles"]))


if __name__ == "__main__":
    main()
