# SaveGaussianSplat: сохранение splat-файла с viewport

## Что делает нода

`SaveGaussianSplat` записывает готовый Gaussian Splat `File3D` в папку `output`, показывает сохранённый файл во встроенном 3D-просмотрщике и возвращает входной объект дальше. Она принимает семейство PLY, SPLAT, SPZ и KSPLAT, а также передаёт transform metadata, камеру, `width` и `height`.

Нода не сериализует тензор `SPLAT` и не меняет контейнер. Она вызывает общий helper, который берёт `model_3d.format`, строит имя output-файла и копирует байты через `File3D.save_to`. Название `Save Splat` описывает допустимое семейство, но не доказывает содержимое и не выбирает новый формат.

Как и другие advanced save-ноды, она одновременно имеет `output_node = true` и пять обычных выходов. Запись файла является side effect, а pass-through позволяет продолжить splat-ветвь без повторного импорта.

## Когда использовать и когда не использовать

Используйте `SaveGaussianSplat`, если предыдущая нода уже вернула splat-совместимый `File3D` и нужен постоянный результат с интерактивным preview. Узкий runtime-тип помогает отделить эту ветвь от mesh и point cloud, а выходы камеры и transform metadata сохраняют контекст viewport.

Тензор `SPLAT` напрямую не подключается. Сначала передайте его в `SplatToFile3D` и выберите `ply`, `ksplat` или `spz`. Именно там выполняются сериализация, сжатие и выбор того, какие spherical harmonics попадут в файл. Save-нода копирует уже готовые байты.

Не используйте её для смены PLY на SPZ или KSPLAT. Для такого преобразования требуется `File3DToSplat → SplatToFile3D`, и каждая стадия должна быть проверена на сохранение нужных данных. Для backend-изображения нужен `RenderSplat`; browser viewer не создаёт выход `IMAGE`.

Обычное облако точек PLY лучше отправлять в `SavePointCloud`. Расширение `.ply` само по себе неоднозначно, и backend `SaveGaussianSplat` не читает заголовок, чтобы подтвердить Gaussian-поля.

## Короткий рецепт подключения

Source-derived fragment оставляет producer файла внешним:

1. Получите `FILE_3D_SPLAT_ANY` в формате PLY, SPLAT, SPZ или KSPLAT.
2. Подайте его во вход `model_3d`.
3. Живой Load3D-виджет сформирует обязательный `viewport_state`.
4. Оставьте `filename_prefix = 3d/ComfyUI`, `width = 1024`, `height = 1024`.
5. Не подключайте optional `camera_info` и `model_3d_info`, если нужно использовать текущий viewport.
6. После запуска используйте выход `model_3d` для следующего splat-узла либо дополнительного сохранения.

В 512 JSON официального wheel 0.1.42 нет `SaveGaussianSplat`. Поэтому fragment отмечен как source-derived. Соседний официальный TripoSplat-workflow действительно сохраняет SPZ, но делает это через `SaveGLB`; его нельзя выдавать за случай этой exact-ноды.

## Входы, выходы и параметры

`model_3d` принимает объединение `FILE_3D_SPLAT_ANY`, `FILE_3D_PLY`, `FILE_3D_SPLAT`, `FILE_3D_SPZ` и `FILE_3D_KSPLAT`. Вход обязателен. Внутри ожидается `Types.File3D`, то есть путь или бинарный поток с меткой `format`.

`filename_prefix` по умолчанию равен `3d/ComfyUI`. Итоговое имя выглядит как `<prefix>_00001.<format>`. Если формат пуст, helper выбирает расширение `.glb`, хотя байты splat не преобразуются. Producer обязан сохранять корректную метку.

`viewport_state` — обязательный frontend-managed `LOAD_3D`. Из него backend берёт `camera_info` и `model_3d_info`, если соответствующие optional advanced-входы равны `None`. Явный пустой список model info перекрывает viewport так же, как непустой.

`width` и `height` имеют default `1024`, диапазон `1…4096`, шаг `1`. Frontend использует их для target size и aspect ratio viewer; backend возвращает значения без изменений.

Пять выходов: `FILE_3D_SPLAT_ANY model_3d`, `LOAD3D_MODEL_INFO`, `LOAD3D_CAMERA`, `INT width`, `INT height`. UI-result отдельно содержит путь сохранённой output-копии, итоговую камеру и итоговый список model info.

## Типовые связки

`SPLAT → SplatToFile3D → SaveGaussianSplat` — основной source-derived путь. PLY сохраняет полный набор коэффициентов, который поддерживает текущий writer; KSPLAT и SPZ в закреплённой реализации сериализуют базовый цвет. Выбирайте формат до save-ноды.

`File3DToSplat` выполняет обратный разбор и нужен, если после сохранения требуется `TransformSplat`, `GetSplatCount` или backend-render. Первый выход `SaveGaussianSplat` остаётся File3D, поэтому без parser тензорные splat-ноды его не примут.

`PreviewGaussianSplat` создаёт временную копию и не предназначен для архива результата. Его можно поставить перед save для проверки или заменить на `SaveGaussianSplat`, когда требуется постоянный output и pass-through.

`SaveGLB` принимает те же splat File3D через широкий multitype и встречается в официальной SPZ-ветви. Для готового файла обе ноды сохраняют фактическое расширение; специализированная нода добавляет пять выходов и явный splat-контракт.

## Практический пример

Exact-source probe создал memory-backed SPZ с тестовыми байтами и выполнил `SaveGaussianSplat` с префиксом `3d/gaussian`. В `viewport_state` находились камера и одна transform-запись, optional-входы не подключались.

Нода записала `3d/gaussian_00001.spz`. Сохранённые байты совпали с входными, а первый выход оказался тем же объектом `File3D`. Камера, model info и размеры `1024 × 1024` были взяты из viewport и возвращены в обычных outputs. UI-result ссылался на output и содержал то же итоговое состояние.

Проверка доказывает файловый и pass-through-контракт, но не валидность тестовых байтов как настоящего SPZ и не WebGL-render. Реальный форматный round-trip `SPLAT → SPZ → SPLAT` проверяется в соседнем исследовании `SplatToFile3D`, а весь fragment здесь не исполнялся.

Exhaustive workflow census охватил 768 root/subgraph graphs и не нашёл exact NodeId. Это отсутствие зафиксировано в ledger, чтобы source-derived пример не превратился позже в «официальный» без нового доказательства.

## Частые ошибки и способы проверки

**Вход `SPLAT` не подключается.** Нода принимает File3D. Добавьте `SplatToFile3D` и выберите формат.

**После PLY ожидался SPZ.** `SaveGaussianSplat` не конвертирует. Проверьте `model_3d.format` до ноды и настройку writer upstream.

**PLY открылся как обычное облако точек.** Frontend сначала проверяет наличие Gaussian scale/rotation properties в PLY-заголовке. Если полного набора нет, выбирается point-cloud adapter. Проверьте producer и структуру PLY, а не только расширение.

**Обычный point-cloud PLY показался splat-нодой.** Backend не валидирует содержимое. Используйте точный тип и `SavePointCloud`; для сомнительного файла проверьте заголовок и источник.

**Камера не совпадает с viewport.** Подключённый `camera_info` имеет приоритет. Отсоедините его или передайте нужное значение явно; то же правило действует для `model_3d_info`.

**Контекстное меню viewer не предлагает конвертирующий экспорт.** Frontend extension возвращает пустой список export items, когда текущий adapter распознан как splat. Это установленное поведение 1.48.7.

**Файл получил `.glb` и перестал открываться.** Пустой `File3D.format` вызвал fallback имени. Исправьте метаданные формата у producer; переименование не восстанавливает неизвестную структуру.

## Производительность и внутреннее поведение

Backend не декодирует Gaussian-параметры. Стоимость записи определяется размером File3D и скоростью диска: disk-backed источник копируется, stream-backed полностью читается и записывается. Сжатие SPZ или упаковка KSPLAT уже завершены upstream, поэтому эта нода не тратит CPU на повторное кодирование.

Отсутствие разбора ускоряет запись, но исключает проверку целостности. Повреждённый файл может успешно попасть в output и дать ошибку только при frontend-загрузке или в стороннем viewer.

Frontend повторно загружает output-файл и создаёт Spark `SplatMesh`. Для PLY сначала читаются байты и проверяются свойства заголовка. Большой splat занимает место в исходном объекте, output, памяти браузера и GPU-viewer одновременно.

`model_3d_info` проходит через backend целиком, но frontend применяет к отображаемой модели только первый элемент. Output-данные downstream при этом не урезаются.

## Совместимость, изменения и устаревание

Baseline: ComfyUI 0.32.0 и frontend 1.48.7. Exact NodeId — `SaveGaussianSplat`, display name — `Save Splat`, module — `comfy_extras.nodes_save_3d`, category — `3d`. Нода экспериментальная и output-node; `deprecated`, `dev_only`, `api_node` равны `false`. Replacement API не содержит ID.

Schema fingerprint: `sha256:cae4d85aa5258b1274bdc5a5823eaeb03c3db588b20c6176271a240f9c124df0`. Повторной проверки требуют изменения списка splat-типов, порядка outputs и frontend-маршрутизации PLY.

Frontend extension `Comfy.SaveGaussianSplat` загружает результат из `output`, сериализует viewport, связывает width/height с target viewer size и восстанавливает камеру/первую transform-запись после загрузки. Логика находится отдельно от backend fingerprint.

Embedded docs 0.5.9 перечисляет правильные форматы и порты, но не объясняет отсутствие конвертации и в английском файле содержит служебную обёртку вокруг Markdown. Для фактов о байтах, типах и UI использованы исходники и runtime.

## Связанные ноды и источники

`SplatToFile3D` создаёт PLY, KSPLAT или SPZ из тензоров; `File3DToSplat` выполняет обратный разбор. `PreviewGaussianSplat` показывает временную копию. `SaveGLB` — широкий терминальный вариант, а `SavePointCloud` предназначен для обычного PLY без Gaussian-полей.

Статья сверена с shared helper и schema `SaveGaussianSplat` в `nodes_save_3d.py`, `File3D`, frontend `load3dPreviewExtensions.ts`, `SplatModelAdapter`, embedded docs 0.5.9 и полным workflow census 0.1.42. Probe подтвердил SPZ-extension, byte-preserving output, viewport fallback, object identity и UI-result; реальный browser render и человеческое утверждение ожидаются.
