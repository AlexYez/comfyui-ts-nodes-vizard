# Каталог TS Nodes Wizard

Исходный контент хранится отдельно от собранного файла, который читает интерфейс.

## Структура

- `articles/<origin>/<slug>/manifest.json` — идентичность, связи, совместимость, редакторский статус и источники статьи.
- `articles/<origin>/<slug>/ru.md` — русский текст статьи.
- `recipes/<slug>/recipe.json` и `ru.md` — метаданные и инструкция рецепта.
- `recipes/<slug>/fragment.json` — смысловой фрагмент графа в формате Nodes Wizard. Это не импортируемый workflow ComfyUI.
- `workflows/*.workflow.json` — полные workflow ComfyUI.
- `runtime/comfyui-0.32.0.object-info.json` — полный, неотфильтрованный снимок ответа чистого backend `/object_info`.
- `runtime/comfyui-0.32.0.object-info.meta.json` — точный tag, commit, версия backend, параметры запуска, хеши и provenance снимка.
- `runtime/comfyui-0.32.0.inventory-report.{json,md}` — производный отчёт по пользовательским server nodes. Только здесь исключаются `dev_only` и тестовые фикстуры.
- `runtime/*.object-info.sample.json` — малый тестовый пример. Он больше не является источником схем для сборки каталога.
- `runtime/*.frontend-inventory.sample.json` — небольшая тестовая фикстура пользовательских frontend-only типов; она не доказывает полноту каталога.
- `runtime/*.frontend-inventory.json` — полный версионированный inventory пользовательских frontend-only типов из закреплённого официального frontend-пакета.
- `research/comfyui-0.32.0.evidence.json` — детерминированная очередь из runtime, pinned docs и фактических соседств во всех закреплённых официальных workflow.
- `research/reviews/<articleId>.json` — проверяемый журнал исследования конкретной статьи: просмотренные строки исходника и workflow, выполненные проверки и честно оставленные пробелы.
- `schemas/*.schema.v1.json` — версионированные JSON Schema для исходных и публичных форматов.
- `catalog.manifest.json` — явный порядок и состав исходников.
- `update-manifest.json` — шаблон выпуска с совместимостью, хешами, URL и сводкой изменений.
- `generated/catalog.json` — собранный каталог для frontend.
- `generated/search-index.json` — документы, готовые к загрузке в полнотекстовый индекс.
- `generated/catalog-bundle.zip` — воспроизводимый архив двух runtime-файлов.

У каждого рецепта обязательно есть структурированный `fragment`. Поле `workflow` опционально: его добавляют только тогда, когда для рецепта существует проверенный полный workflow. Для рецепта без такого примера поле можно не указывать или явно задать `null`; Wizard всё равно показывает fragment, но не предлагает открыть нерелевантный workflow.

## Как добавить статью

1. Создайте каталог статьи и `manifest.json` по `schemas/article.schema.v1.json`.
2. Используйте неизменяемый `articleId`. В `runtimeIdentity.classType` запишите точный runtime `class_type`, а не отображаемое или переведённое имя.
3. `runtimeIdentity.aliases` предназначен только для подтверждённых прежних `class_type`. Поисковые синонимы принадлежат `searchAliases`.
4. Укажите как минимум один источник. Поле `supports` называет факты, которые этот источник подтверждает.
5. Создайте `research/reviews/<articleId>.json` по `schemas/article-research.schema.v1.json`. Не отмечайте `exampleExecuted`, если пример только разобран или прошёл schema-проверку.
6. Синхронизируйте явный список исходников и запустите проверки:

   ```text
   python tools/catalog.py sync-manifest
   python tools/catalog.py validate
   python tools/catalog.py build
   python tools/catalog.py ci
   ```

`sync-manifest` находит только ожидаемые source-файлы в `articles`, `recipes` и `workflows`, сортирует пути и обновляет три массива верхнего manifest. Валидация сравнивает список в обе стороны: ни забытая статья, ни ссылка на удалённый файл не проходят CI. Это сохраняет manifest явным, но не заставляет вручную редактировать список из сотен статей.

Опубликованная статья должна иметь `editorial.state = "approved"`, проверяющего, даты редакторской и фактической проверки. Draft нельзя маскировать статусом `active`.

Статус `approved` дополнительно требует research record со `state = "human_approved"`, `reviewMode = "human"`, всеми завершёнными checks и без `knownGaps`. Автоматизированный разбор может довести статью до `in_review`, но не подменяет это решение.

## Fingerprint схемы ноды

CLI нормализует структурную часть `/object_info`, сериализует её как UTF-8 JSON с отсортированными ключами и компактными разделителями, затем вычисляет SHA-256 в форме `sha256:<hex>`.

В fingerprint входят:

- имя, тип и секция каждого входа;
- required/optional;
- стабильные ограничения виджета;
- имя, тип, list-флаг и tooltip каждого выхода;
- флаги `deprecated`, `experimental` и `api_node`;
- `nodeId` и `pythonModule`.

Списки значений combo и их локальные default исключены. Перечень checkpoint, моделей и файлов зависит от установки; смена такого списка не делает статью устаревшей. Тесты отдельно проверяют это правило.

## Происхождение и атрибуция

Каждая запись `sources` содержит стабильный `sourceId`, заголовок, HTTPS URL, издателя, тип источника, дату доступа и список поддержанных фактов. Для технических утверждений предпочтительны закреплённый тег официального исходного кода и официальная документация ComfyUI.

Текст нельзя копировать из стороннего справочника без проверки лицензии. Ссылку на источник и собственное изложение следует хранить даже тогда, когда исходный проект разрешает копирование.

## Обновление по новой версии ComfyUI

Снимите `/object_info`, `/api/node_replacements` и `/system_stats`, затем создайте отчёт вне репозитория:

```text
python tools/catalog.py inventory-report --object-info artifacts/object_info.json --replacements artifacts/node_replacements.json --system-stats artifacts/system_stats.json --baseline content/runtime/comfyui-0.32.0.object-info.sample.json --output-dir artifacts/report
```

Отчёт содержит coverage, новые и удалённые ноды, структурные изменения, смену lifecycle-флагов и официальные replacement-связи. Frontend-ноды вроде `Reroute` не считаются backend-долгом, если их нет в `/object_info`.

## Зафиксированный backend inventory 0.32.0

Полный snapshot получен реальным запуском официального тега `v0.32.0`, commit `c2bcbecd82ec5ae66594340b395c24ef0217b238`. Checkout сохранён локально в игнорируемом каталоге `.comfyui-source-0.32.0/`. Backend запущен на CPU с `--disable-all-custom-nodes`; встроенные `comfy_extras` и `comfy_api_nodes` оставлены включёнными. `/system_stats` подтвердил backend `0.32.0` и обязательные package versions, а число зарегистрированных `NODE_CLASS_MAPPINGS` совпало с числом записей endpoint: 840.

Сырой файл `runtime/comfyui-0.32.0.object-info.json` содержит точные байты ответа `/object_info`: 840 записей, без удаления полей или повторной сериализации. В нём нет custom nodes. Derived-отчёт показывает 840 пользовательских server nodes; в данном запуске endpoint не содержал ни `dev_only`, ни загруженных тестовых нод. Разбивка: 220 API, 137 experimental, 31 deprecated. Эти множества пересекаются, поэтому их нельзя складывать.

Отчёт воспроизводится командой:

```text
python tools/catalog.py snapshot-report --inventory content/runtime/comfyui-0.32.0.object-info.json --metadata content/runtime/comfyui-0.32.0.object-info.meta.json --output-json content/runtime/comfyui-0.32.0.inventory-report.json --output-markdown content/runtime/comfyui-0.32.0.inventory-report.md
```

Pinned requirements включают `comfyui-embedded-docs==0.5.9`. Пакет не вендорится. Английский документ конкретной ноды доступен по шаблону `comfyui_embedded_docs/docs/{classType}/en.md`; точный установленный путь можно получить без догадок:

```text
python -c "import importlib.metadata as m; print(m.distribution('comfyui-embedded-docs').locate_file('comfyui_embedded_docs/docs/KSampler/en.md'))"
```

Эти `en.md` служат официальным вторичным источником. Утверждения о runtime-контракте всё равно сверяются с pinned исходным кодом и `/object_info`.

## Проверка перед стабильным выпуском

Обычный `python tools/catalog.py ci` проверяет схемы, исходники, собранные файлы и тесты. Он намеренно не требует, чтобы альфа-каталог уже был готов к стабильному выпуску. Для stable-релиза есть отдельная проверка по свежему runtime inventory:

```text
python tools/catalog.py release-gate --inventory artifacts/object_info.json --frontend-inventory artifacts/frontend_inventory.json --replacements artifacts/node_replacements.json
```

Команда завершается с кодом `1`, если в inventory есть нода без статьи, статья не совпадает с runtime или устарела по schema fingerprint, статья уровня core/frontend не одобрена и не переведена в подходящий lifecycle-статус, связанный рецепт не одобрен либо пример повреждён. `--frontend-inventory` формируется по `schemas/frontend-inventory.schema.v1.json`; для stable он обязателен. Его `frontendVersion` должен совпадать с целевой версией в `update-manifest.json`. Gate сверяет пользовательские frontend-only типы и статьи в обе стороны, исключая записи с `dev_only = true`. Так активная статья не останется без реального frontend-типа, а новый тип — без статьи.

Файл с суффиксом `.sample.json` — только тестовая фикстура. Для stable нужен заново собранный полный inventory из той версии frontend, которая указана в релизе; тестовый список нельзя использовать как доказательство полноты.

### Воспроизводимый frontend-only inventory для ComfyUI 0.32.0

ComfyUI `v0.32.0` закрепляет `comfyui-frontend-package==1.48.7`. Полный снимок этой пары хранится в `runtime/comfyui-frontend-1.48.7.frontend-inventory.json`; он содержит ровно четыре фиксированных пользовательских типа: `MarkdownNote`, `Note`, `PrimitiveNode`, `Reroute`.

Источники истины в официальном checkout `Comfy-Org/ComfyUI_frontend`:

- `src/stores/nodeDefStore.ts`, объект `SYSTEM_NODE_DEFS` — полный фиксированный набор, который попадает в node store, общий для Nodes 2.0;
- `src/extensions/core/widgetInputs.ts`, `rerouteNode.ts`, `noteNode.ts` — literal-регистрации тех же типов для classic canvas;
- `src/scripts/app.ts` — добавление `SYSTEM_NODE_DEFS` в `nodeDefStore`;
- `src/renderer/extensions/vueNodes/components/LGraphNode.vue` — renderer Nodes 2.0, включая специальную ветку `Reroute`.

Динамические регистрации backend-нод и пользовательских subgraph в `src/services/litegraphService.ts`, а также fixtures, tests, examples и dev-only типы в inventory не входят. Экстрактор требует точного совпадения `SYSTEM_NODE_DEFS` и classic-регистраций, поэтому изменение одной поверхности не останется незамеченным.

Воспроизведение из официального тега:

```text
git clone --depth 1 --branch v1.48.7 https://github.com/Comfy-Org/ComfyUI_frontend.git ../ComfyUI_frontend-1.48.7
python tools/frontend_inventory.py --source-root ../ComfyUI_frontend-1.48.7 --frontend-version 1.48.7 --frontend-commit 6d6af63c00f132cd25dc29307fc56bd2c094fa22 --comfyui-version 0.32.0 --comfyui-commit c2bcbecd82ec5ae66594340b395c24ef0217b238 --captured-at 2026-08-13T18:03:35Z --check content/runtime/comfyui-frontend-1.48.7.frontend-inventory.json
```

Оба полных commit SHA записаны в поле `source`. Инструмент только строит или проверяет inventory и не создаёт статьи.

Для успешного stable-релиза в `catalog.manifest.json` также нужны `release.channel = "stable"` и явное решение ответственного редактора в `release.humanApproval`. Поля `approvedBy` и `approvedAt` заполняют только после человеческой проверки.

Текущий каталог имеет канал `alpha` и `humanApproval.state = "pending"`, поэтому `release-gate` сейчас должен завершаться ошибкой с перечислением причин. Это ожидаемый результат и не делает обычный `ci` красным.

`ci` отдельно проверяет собранный `generated/catalog.json` по полной схеме `schemas/compiled-catalog.schema.v1.json`. Неизвестные поля в article manifest запрещены. Объекты сериализованного workflow допускают дополнительные поля намеренно: их формат расширяет сам ComfyUI, а Nodes Wizard фиксирует только обязательные `nodes`, `links` и `version`.

## Подпись update manifest

`tools/sign-update.mjs` подписывает канонические байты всего top-level manifest, кроме поля `signature`. Seed передаётся только через окружение. Проверка требует отдельно настроенный доверенный публичный ключ; ключ внутри скачанного manifest не устанавливает доверие.

```powershell
$env:NODES_WIZARD_SIGNING_SEED = '<32-byte-base64url-or-hex>'
$env:NODES_WIZARD_SIGNING_KEY_ID = 'release-2026-08'
node tools/sign-update.mjs sign --manifest content/generated/update-manifest.example.json --artifact-root content --output release/update-manifest.json

$env:NODES_WIZARD_TRUSTED_PUBLIC_KEY = '<trusted-32-byte-base64url-or-hex>'
$env:NODES_WIZARD_TRUSTED_KEY_ID = 'release-2026-08'
node tools/sign-update.mjs verify --manifest release/update-manifest.json
```

Для `sign` обязателен корень локальных artifacts. До подписи инструмент находит единственную запись `catalog.json` в `artifacts`, безопасно разрешает её путь внутри `--artifact-root`, сравнивает точный размер и SHA-256 локальных байтов, проверяет строгий UTF-8 JSON и равенство `catalogVersion` в manifest и artifact, затем передаёт эти же байты через stdin в read-only проверку `python tools/catalog.py validate-compiled -`. Она применяет тот же полный `compiled-catalog.schema.v1.json`, который используется в `ci`; проверяется именно захешированный снимок, а не повторно прочитанный файл. Ошибка любой проверки останавливает команду до чтения private seed и до создания подписанного файла.

Пути загрузки в шаблоне используют `example.invalid`. Перед публикацией выпуск должен подставить реальные HTTPS URL и пересобрать manifest до подписи.
