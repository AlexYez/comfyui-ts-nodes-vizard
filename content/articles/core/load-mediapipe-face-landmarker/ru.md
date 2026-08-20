# LoadMediaPipeFaceLandmarker: загрузить локальную модель лицевых ориентиров

## Что делает нода

`LoadMediaPipeFaceLandmarker` читает файл модели из каталога `ComfyUI/models/detection` и возвращает объект `FACE_DETECTION_MODEL`. Файл содержит два набора весов детектора лица — `short` и `full`, а также общие исходные веса лицевой сетки и блока, который вычисляет 52 blendshape-коэффициента. Там же лежат таблицы связей и эталонная трёхмерная геометрия.

Нода не скачивает файл. Её `execute` только разрешает локальный путь и передаёт его безопасному загрузчику весов. Официальный MediaPipe blueprint указывает файл `mediapipe_face_fp32.safetensors` и URL на Hugging Face, но URL хранится в метаданных графа и не читается серверной нодой.

## Место в графе

Ставьте загрузчик перед `MediaPipeFaceLandmarker`. Выход `FACE_DETECTION_MODEL` подключается к одноимённому входу детектора, а уже детектор принимает `IMAGE` и выпускает ориентиры и рамки.

Один загруженный объект можно подавать в несколько детекторов с разными настройками. Выбирать `short`, `full` или `both` в загрузчике не нужно: обе разновидности собираются одновременно, а нужную выбирает `MediaPipeFaceLandmarker` при выполнении.

## Входы

- `model_name: COMBO` — имя локального файла из зарегистрированного каталога `detection`.

Список динамический. В чистом snapshot `/object_info` 0.32.0 он пуст: в закреплённой установке модель отсутствовала. После помещения поддерживаемого файла в `models/detection` его имя должно появиться в списке.

Пример использует `mediapipe_face_fp32.safetensors`, потому что именно это имя записано в официальных Image и Video blueprint. Это не универсальный псевдоним и не доказательство наличия файла на конкретной машине.

## Выходы

`FACE_DETECTION_MODEL` — не тензор готовых ориентиров, а контейнер моделей и служебной геометрии. Его принимает `MediaPipeFaceLandmarker`; подключать его напрямую к обычным image- или segmentation-нодам нельзя.

Контейнер включает две самостоятельные модели `FaceLandmarker` и отдельный `ModelPatcher` для каждой. У обеих есть собственные модули detector, mesh и blendshapes; mesh- и blendshape-модули загружены одинаковыми исходными весами. Таблицы связей и каноническая геометрия хранятся один раз во внешнем контейнере.

## Как работает внутри

`get_full_path_or_raise("detection", model_name)` проверяет, что файл существует в зарегистрированном каталоге. Затем нода вызывает `load_torch_file(..., safe_load=True)`. В закреплённой реализации этот параметр внутри функции не читается: safetensors в любом случае открывается через `safetensors.safe_open`, а остальные допустимые torch-форматы — через `torch.load(..., weights_only=True)`.

Конструктор извлекает из state dict записи `topology.*` и каноническую геометрию, затем собирает две fp32-модели. Общие ключи `mesh.*` и `blendshapes.*` подаются обеим; префиксы `detector_short.*` и `detector_full.*` выбирают соответствующую ветвь. Загрузка выполняется с `strict=False`, а список несовпавших ключей отдельно не проверяется. Неподходящий файл поэтому может завершиться ошибкой сразу либо оставить часть параметров в исходном состоянии.

При первом реальном распознавании контейнер загружает на выбранное устройство только patcher требуемого варианта. Для `both` детектор последовательно использует оба.

## Настройки

У ноды одна настройка — `model_name`. Менять расширение или имя во фрагменте имеет смысл только вместе с реально установленным совместимым state dict.

Core принудительно строит MediaPipe-модели в `float32`: комментарий исходника связывает это с PReLU и несовместимым переносом буферов при manual cast. Выбора dtype в интерфейсе нет.

Официальный blueprint содержит изменяемый URL `.../resolve/main/...` без SHA-256 или другой контрольной суммы. Frontend 1.48.7 умеет находить отсутствующие модели по `properties.models` и запускать отдельную загрузку, но такая подсказка не закрепляет содержимое файла криптографически. Для воспроизводимой установки храните проверенную контрольную сумму вне workflow.

## Пример подключения

Фрагмент `recipe.mediapipe-face-mask` соединяет `LoadMediaPipeFaceLandmarker(model_name = mediapipe_face_fp32.safetensors)` с `MediaPipeFaceLandmarker`, а затем передаёт `face_landmarks` в `MediaPipeFaceMask`. Второй фрагмент, `recipe.mediapipe-face-mesh-overlay`, заканчивается визуализатором.

Связка загрузчик → детектор → маска подтверждена официальными Image и Video blueprint ComfyUI 0.32.0. В обоих выбран `full`, `num_faces = 0`, `min_confidence = 0.5`, `missing_frame_fallback = empty`. Blueprint одновременно содержит устаревший вход `FACE_LANDMARKER`, которого нет в актуальном `/object_info`; наши фрагменты используют только текущие порты.

В 512 JSON официального wheel с workflow-шаблонами 0.1.42 ни одна из четырёх MediaPipe-нод не встречается: проверены 496 корневых графов, 272 `definitions.subgraphs`, индексы и все строковые значения. Поэтому blueprint указан как отдельный официальный источник, а фрагмент не назван исполненным workflow.

## Частые ошибки

**Список `model_name` пуст.** В `models/detection` нет поддерживаемого файла или ComfyUI ещё не обновил список файлов. Проверьте путь и перезапустите либо обновите интерфейс.

**`FileNotFoundError` при запуске.** Workflow сохранил имя, которого нет в текущей установке. URL из blueprint сам загрузчик не обрабатывает.

**Ошибка несовместимых размеров или ключей.** Файл не соответствует ожидаемой раскладке `detector_short.*`, `detector_full.*`, `mesh.*`, `blendshapes.*`, `topology.*` и canonical data. Одного подходящего имени недостаточно.

**Файл заменили под тем же именем, но результат не изменился.** Исполнительный кэш опирается на класс ноды и входное значение. При замене содержимого без смены `model_name` ранее загруженный объект может остаться в кэше до инвалидирования графа или перезапуска процесса.

**Ожидался отдельный загрузчик для `short` и `full`.** Один файл и один объект содержат оба варианта; выбор делается в следующей ноде.

## Ограничения и производительность

Загрузчик создаёт две fp32-модели. Каждая содержит собственные detector, mesh и blendshape-модули, хотя последние загружены одинаковыми значениями из файла; отдельно контейнер хранит топологию и каноническую геометрию. Это расходует оперативную память ещё до детекции. На нужное устройство модель переносится через model manager при вызове варианта; `both` требует поочерёдной работы обеих ветвей.

Использование `safetensors.safe_open` и `torch.load(weights_only=True)` уменьшает риск произвольного кода из файла, но не подтверждает происхождение или правильность весов. Переданный флаг `safe_load=True` в ComfyUI 0.32.0 сам по себе ничего не переключает. Изменяемый URL без контрольной суммы не даёт воспроизводимой идентичности модели.

Нода не проверяет версию MediaPipe-формата отдельным заголовком и не валидирует полный набор ключей после `strict=False`. Для каталога это остаётся известным пробелом: реальный файл не был загружен, а модельное выполнение не проводилось.

## Совместимость и источники

Материал проверен на ComfyUI `0.32.0`, commit `c2bcbecd82ec5ae66594340b395c24ef0217b238`, frontend `1.48.7`. Runtime fingerprint: `sha256:e9ed899b1ca1ed271949c456eb55ed900f1d4ebc20d3a7571c0a0b4eec8ffe7b`. Нода active, не experimental, deprecated, dev-only или API node; replacement не заявлен.

Embedded docs 0.5.9 использованы только как вторичный источник. Точное поведение локального пути, загрузки файла и состава контейнера сверено с кодом. Официальные blueprint прочитаны отдельно от wheel с workflow-шаблонами; их устаревший вход не перенесён во фрагмент.

- [Состав MediaPipe-контейнера](https://github.com/Comfy-Org/ComfyUI/blob/c2bcbecd82ec5ae66594340b395c24ef0217b238/comfy_extras/nodes_mediapipe.py#L37-L79)
- [Схема и выполнение загрузчика](https://github.com/Comfy-Org/ComfyUI/blob/c2bcbecd82ec5ae66594340b395c24ef0217b238/comfy_extras/nodes_mediapipe.py#L198-L220)
- [Проверка локального пути](https://github.com/Comfy-Org/ComfyUI/blob/c2bcbecd82ec5ae66594340b395c24ef0217b238/folder_paths.py#L441-L468)
- [Безопасная загрузка весов](https://github.com/Comfy-Org/ComfyUI/blob/c2bcbecd82ec5ae66594340b395c24ef0217b238/comfy/utils.py#L122-L167)
- [Image Face Detection blueprint](https://github.com/Comfy-Org/ComfyUI/blob/c2bcbecd82ec5ae66594340b395c24ef0217b238/blueprints/Image%20Face%20Detection%20%28Mediapipe%29.json#L379-L771)
- [Входная сигнатура исполнительного кэша](https://github.com/Comfy-Org/ComfyUI/blob/c2bcbecd82ec5ae66594340b395c24ef0217b238/comfy_execution/caching.py#L82-L127)
- [Frontend missing-model scan](https://github.com/Comfy-Org/ComfyUI_frontend/blob/6d6af63c00f132cd25dc29307fc56bd2c094fa22/src/platform/missingModel/missingModelScan.ts#L39-L68)
- [Frontend download dispatch](https://github.com/Comfy-Org/ComfyUI_frontend/blob/6d6af63c00f132cd25dc29307fc56bd2c094fa22/src/platform/missingModel/missingModelDownload.ts#L7-L139)
- [Embedded docs 0.5.9](https://github.com/Comfy-Org/embedded-docs/blob/1d258cf6e374d60d138a2bfcd273c7e11f750ef9/comfyui_embedded_docs/docs/LoadMediaPipeFaceLandmarker/en.md)

Редактор пока не проверил материал вручную.
