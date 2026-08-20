# Catalog CLI

Все Python-команды работают на стандартной библиотеке и не обращаются к сети.

```text
python tools/catalog.py validate
python tools/catalog.py validate-compiled content/generated/catalog.json
python tools/catalog.py sync-manifest --check
python tools/catalog.py build
python tools/catalog.py build --check
python tools/catalog.py ci
```

Runtime-команды:

```text
python tools/catalog.py fingerprint object_info.json
python tools/catalog.py fingerprint object_info.json --node-id KSampler
python tools/catalog.py diff --before old.json --after new.json --replacements replacements.json
python tools/catalog.py coverage --inventory object_info.json --replacements replacements.json
python tools/catalog.py inventory-report --object-info object_info.json --replacements replacements.json --system-stats system_stats.json --baseline old.json --output-dir artifacts/report
python tools/catalog.py snapshot-report --inventory content/runtime/comfyui-0.32.0.object-info.json --metadata content/runtime/comfyui-0.32.0.object-info.meta.json --output-json content/runtime/comfyui-0.32.0.inventory-report.json --output-markdown content/runtime/comfyui-0.32.0.inventory-report.md
python tools/catalog.py release-gate --inventory object_info.json --frontend-inventory frontend_inventory.json --replacements replacements.json
```

Исследовательский отчёт для редакционной работы строится отдельно. Он не пишет статьи и не превращает runtime-описание в якобы готовый текст:

```text
python tools/research.py report --inventory content/runtime/comfyui-0.32.0.object-info.json --frontend-inventory content/runtime/comfyui-frontend-1.48.7.frontend-inventory.json --embedded-docs-wheel .upstream-cache/comfyui_embedded_docs-0.5.9-py3-none-any.whl --workflow-wheel .upstream-cache/comfyui_workflow_templates_json-0.1.42-py3-none-any.whl --source-root .comfyui-source-0.32.0 --comfyui-version 0.32.0 --frontend-version 1.48.7 --output content/research/comfyui-0.32.0.evidence.json

python tools/research.py inspect --inventory content/runtime/comfyui-0.32.0.object-info.json --embedded-docs-wheel .upstream-cache/comfyui_embedded_docs-0.5.9-py3-none-any.whl --workflow-wheel .upstream-cache/comfyui_workflow_templates_json-0.1.42-py3-none-any.whl --source-root .comfyui-source-0.32.0 --node-id VAEDecode --output artifacts/research/VAEDecode.json
```

Для каждой ноды общий отчёт соединяет точную runtime-схему, путь к реализации, наличие закреплённых `en.md`/`ru.md` и все случаи в официальных workflow. Для каждого случая сохраняются фактические соседи по связям. `inspect` выдаёт не сокращённое досье одной ноды: полный runtime object, фрагменты исходника, точные тексты закреплённой документации и несколько наименьших официальных графов с самой нодой, связанными соседями, виджетами и links. Поле `researchState` остаётся `pending`, а checklist в досье — `false`: инструменты служат очередью и доказательной базой, но не заменяют чтение кода, проверку workflow и редактуру. `--check` сравнивает существующий общий отчёт побайтно и ничего не меняет.

Полный frontend-only inventory воспроизводится из checkout официального frontend-пакета. Экстрактор сверяет фиксированные определения для classic canvas и Nodes 2.0 и не включает динамические backend/custom/subgraph либо test/dev типы:

```text
python tools/frontend_inventory.py --source-root ../ComfyUI_frontend-1.48.7 --frontend-version 1.48.7 --frontend-commit 6d6af63c00f132cd25dc29307fc56bd2c094fa22 --comfyui-version 0.32.0 --comfyui-commit c2bcbecd82ec5ae66594340b395c24ef0217b238 --captured-at 2026-08-13T18:03:35Z --check content/runtime/comfyui-frontend-1.48.7.frontend-inventory.json
```

`validate`, `validate-compiled`, `build --check`, `fingerprint`, `diff` без `--output`, `coverage` и `ci` не изменяют файлы. `validate-compiled` проверяет один готовый catalog artifact по `content/schemas/compiled-catalog.schema.v1.json`; аргумент `-` читает строгий UTF-8 JSON из stdin. `build` пишет только в указанный `--output-dir`; по умолчанию это `content/generated`. `inventory-report` создаёт `inventory-report.json` и `inventory-report.md` в явно заданном каталоге.

`release-gate` — отдельный read-only барьер для stable-релиза. Он возвращает ненулевой код и печатает все причины, если backend или frontend inventory покрыт не полностью, fingerprints или lifecycle расходятся, core/frontend-статьи и связанные рецепты не одобрены, примеры повреждены либо отсутствует явное человеческое одобрение выпуска. `--frontend-inventory` использует `content/schemas/frontend-inventory.schema.v1.json`, исключает `dev_only`, сверяет `frontendVersion` с целью в `update-manifest.json` и обязателен для успешного stable-gate. Альфа-каталог с `humanApproval.state = "pending"` обязан не пройти эту команду; это не влияет на `ci`.

Очередь человеческого ревью для локальных нод печатается без изменения файлов:

```text
python tools/review_queue.py
python tools/review_queue.py --article-id core.ksampler-advanced
python tools/review_queue.py --format json
```

Отчёт показывает runtime-статус, редакционное состояние, research checks, незакрытые ограничения и связанные рецепты. Он не переводит материалы в `approved` и не подменяет решение ответственного редактора.

`snapshot-report` строит детерминированный JSON/Markdown для pinned raw `/object_info`. Исходный snapshot не меняется и не фильтруется. Исключение `dev_only` и тестовых типов применяется только в отчёте; raw count, user server count, flags, пересечения и список node IDs остаются проверяемыми тестами.

В составе `ci` собранный `content/generated/catalog.json` валидируется по `content/schemas/compiled-catalog.schema.v1.json`. Контракт закрывает article manifest, runtime identity, lifecycle, совместимость, связи, assets, источники и редакторские поля. Дополнительные поля разрешены только внутри расширяемых объектов workflow и пользовательских `settings` фрагмента.

Подпись требует установленных зависимостей проекта:

```text
node tools/sign-update.mjs --help
node tools/sign-update.mjs sign --manifest content/generated/update-manifest.example.json --artifact-root content --output release/update-manifest.json
```

`--artifact-root` обязателен для `sign`. До чтения private seed инструмент:

1. находит ровно одну запись `artifacts`, чей последний компонент пути равен `catalog.json`;
2. требует переносимый относительный путь без `.`, `..`, двоеточий, обратных слешей и выхода через symlink за пределы `--artifact-root`;
3. требует `contentType = "application/json"`, неотрицательный безопасный целый `size` и SHA-256 из 64 строчных hex-символов;
4. сравнивает `size` и SHA-256 с точными локальными байтами;
5. требует строгий UTF-8 JSON и равенство `catalogVersion` в manifest и catalog artifact;
6. передаёт те же проверенные байты через stdin в `python tools/catalog.py validate-compiled -` и требует полного соответствия compiled-catalog schema.

Любая ошибка завершает `sign` с ненулевым кодом до создания output. Python можно явно задать через `NODES_WIZARD_PYTHON`; по умолчанию используется `python` в Windows и `python3` в остальных системах. Приватный seed принимается только через `NODES_WIZARD_SIGNING_SEED`. Для проверки подписи нужен независимо доставленный `NODES_WIZARD_TRUSTED_PUBLIC_KEY`.
