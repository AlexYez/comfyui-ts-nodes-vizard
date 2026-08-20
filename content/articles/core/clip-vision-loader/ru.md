# CLIPVisionLoader: загрузить визуальный энкодер

## Что делает нода

`CLIPVisionLoader` берёт файл из группы путей `clip_vision`, разбирает набор весов и возвращает `CLIP_VISION`. В обычной установке это каталог `ComfyUI/models/clip_vision`; дополнительные каталоги можно задать через `extra_model_paths.yaml`.

Загрузчик не принимает изображение и ничего не кадрирует. Он лишь собирает визуальный энкодер и проверяет, что структура весов относится к одной из распознаваемых реализаций. В ComfyUI 0.32.0 детектор знает варианты CLIP Vision, SigLIP/SigLIP2, DINOv2 и DINOv3. Если сигнатура набора весов не распознана, нода завершает работу сообщением `ERROR: clip vision file is invalid and does not contain a valid vision model.`

За подготовку изображения отвечает следующая нода, обычно `CLIPVisionEncode`. Именно она передаёт флаг `crop` в preprocessing выбранного энкодера.

## Когда использовать и когда не использовать

Используйте `CLIPVisionLoader`, когда граф требует отдельный визуальный энкодер: для референса, переноса стиля, Revision conditioning либо image/video-модели, которая принимает `CLIP_VISION_OUTPUT`. Отдельный загрузчик нужен, если визуальные веса не входят в основной checkpoint.

Не подавайте сюда обычный текстовый CLIP, LoRA, IP-Adapter или diffusion model. Расширение `.safetensors` само по себе ничего не доказывает: решение принимается по ключам и форме тензоров внутри файла.

Для checkpoint, который действительно содержит совместимый vision-энкодер, существует `unCLIPCheckpointLoader`. Это не взаимозаменяемые способы во всех графах: отдельный файл из `models/clip_vision` должен соответствовать конкретному потребителю и семейству основной модели.

## Короткий рецепт подключения

1. Поместите совместимые vision-веса в `models/clip_vision` и обновите список моделей.
2. Выберите файл в `clip_name`.
3. Соедините `CLIP_VISION` с одноимённым входом `CLIPVisionEncode`.
4. Подайте `IMAGE` в `CLIPVisionEncode` и выберите `crop = center` или `none`.
5. Передайте `CLIP_VISION_OUTPUT` в принимающую ноду: например, `unCLIPConditioning` или `StyleModelApply`.

Fragment «Загрузить clip_vision_g и закодировать изображение» повторяет часть официального `sdxl_revision_text_prompts`: `CLIPVisionLoader(clip_vision_g.safetensors) → CLIPVisionEncode(crop=center)`. Структура сверена с runtime, но файл модели не загружался и fragment не выполнялся.

## Входы, выходы и параметры

`clip_name` — обязательный динамический список файлов из группы `clip_vision`. В чистом snapshot `/object_info` список пуст: модельные имена зависят от локальной установки и поэтому не входят в fingerprint.

Выход один: `CLIP_VISION`, не list-output. Он содержит модель, настройки preprocessing и patcher для загрузки и offload. Это ещё не признаки изображения. `CLIPVisionEncode` создаёт отдельный `CLIP_VISION_OUTPUT` с `last_hidden_state`, `image_embeds`, размерами входа и, в зависимости от семейства, дополнительными hidden states.

У `CLIPVisionLoader` нет параметра crop. `center` и `none` принадлежат `CLIPVisionEncode`; переносить этот выбор на загрузчик нельзя.

## Типовые связки

Базовая связка: `CLIPVisionLoader → CLIPVisionEncode`. К encode также подключается `LoadImage`. Дальше тип `CLIP_VISION_OUTPUT` направляют в ноду, которая знает семантику конкретной модели.

В официальном шаблоне Flux Redux один `sigclip_vision_patch14_384.safetensors` обслуживает два `CLIPVisionEncode`, а их выходы последовательно проходят через `StyleModelApply`. В SDXL Revision один `clip_vision_g.safetensors` также питает два encode, после чего две `unCLIPConditioning` добавляют референсы в одну положительную ветвь conditioning.

В Wan image-to-video используется `clip_vision_h.safetensors`; официальный узел encode там выставлен в `crop = none`. Это пример того, почему crop нельзя выбирать по привычке: решение принадлежит workflow и ожидаемому preprocessing модели.

## Практический пример

Полный просмотр `comfyui-workflow-templates-json 0.1.42` охватил 512 JSON, все корневые графы и 272 `definitions.subgraphs`. Найдены 25 `CLIPVisionLoader` в 21 файле и 15 разных top-level UUID: 10 нод в root и 15 в subgraphs; все находятся в режиме 0. Несколько шаблонов повторно используют один UUID, поэтому файл остаётся основной единицей подсчёта случаев.

Распределение значений widget: 16 раз `clip_vision_h.safetensors`, 7 раз `sigclip_vision_patch14_384.safetensors`, по одному разу `clip_vision_g.safetensors` и `dino_v3_vit_h.safetensors`. От загрузчиков идут 28 прямых связей к `CLIPVisionEncode`; остальные официальные случаи ведут к специализированной принимающей ноде либо к портам subgraph.

Показательный граф `sdxl_revision_text_prompts`, UUID `22fbfe6b-e7d7-4193-8409-8599b5dce771`: нода №39 загружает `clip_vision_g.safetensors`, выход разветвляется к encode №13 и №36, оба используют `center`, затем две `unCLIPConditioning` последовательно добавляют conditioning изображения. Здесь проверена сериализованная структура связей, а не исполнение модели.

## Частые ошибки и способы проверки

**Файл виден, но не загружается.** Проверьте, что это самостоятельный набор весов визуального энкодера, а не checkpoint другого типа. Закреплённая реализация возвращает отдельную ошибку, когда архитектура не распознана.

**Список пуст после копирования файла.** Обновите frontend или перезапустите серверный inventory. Источник списка — `folder_paths`, а не текст статьи.

**Изображение обрезано не так.** Ищите настройку в `CLIPVisionEncode`. Загрузчик crop не выполняет.

**Размер embedding не подходит принимающей ноде.** Совпадение типа порта `CLIP_VISION_OUTPUT` не гарантирует архитектурную совместимость. Сверьте vision-файл с основной моделью и официальным шаблоном.

**Ожидают текстовый CLIP на выходе.** `CLIP_VISION` нельзя подключить к `CLIPTextEncode`; это другой runtime-тип.

## Производительность и внутреннее поведение

При создании vision-модели ComfyUI выбирает `text_encoder_device`, `text_encoder_offload_device` и `text_encoder_dtype`, затем оборачивает модель в `CoreModelPatcher`. Само кодирование вызывает `load_model_gpu`; поэтому основная device-нагрузка проявляется при `CLIPVisionEncode`, а не при выборе файла в меню.

Вес модели всё равно нужно прочитать и разобрать. Повторные независимые загрузчики одного большого файла могут увеличить RAM/VRAM и время подготовки графа. Один выход можно разветвить на несколько encode, как в официальных Revision и Redux workflows.

Preprocessing приводит изображение к размеру, mean и std из конфигурации распознанного энкодера. Для SigLIP2 используется отдельная ветвь preprocessing; загрузчик выбирает её по модели, а не по имени файла.

## Совместимость, изменения и статус

Статья закреплена на ComfyUI `0.32.0`, frontend `1.48.7`, runtime ID `CLIPVisionLoader`, модуле `nodes`. Fingerprint: `sha256:51c6657ce101c57646f468509b8f221478c86942f23486b67838bb59319c0d41`.

Runtime не помечает ноду как deprecated, experimental, dev-only или API node; она не является output node. Динамические значения `clip_name` исключены из fingerprint, поэтому установка другого набора моделей не создаёт ложный schema drift.

Embedded docs 0.5.9 правильно указывают каталог и тип выхода, но не отделяют загрузку от crop/preprocessing и не перечисляют сигнатуры распознаваемых семейств. Технические выводы здесь сверены с закреплённым исходником.

## Связанные ноды и источники

`CLIPVisionEncode` принимает модель и изображение, выбирает crop и создаёт embedding. `StyleModelApply` использует embedding вместе со style model. `unCLIPConditioning` записывает image embedding в metadata conditioning. `unCLIPCheckpointLoader` нужен только тогда, когда vision-компонент действительно встроен в совместимый checkpoint.

- [Реализация `CLIPVisionLoader` и `CLIPVisionEncode`](https://github.com/Comfy-Org/ComfyUI/blob/c2bcbecd82ec5ae66594340b395c24ef0217b238/nodes.py#L1061-L1095)
- [Детектор архитектур и preprocessing CLIP Vision](https://github.com/Comfy-Org/ComfyUI/blob/c2bcbecd82ec5ae66594340b395c24ef0217b238/comfy/clip_vision.py#L22-L163)
- [Embedded docs 0.5.9 для `CLIPVisionLoader`](https://github.com/Comfy-Org/embedded-docs/blob/1d258cf6e374d60d138a2bfcd273c7e11f750ef9/comfyui_embedded_docs/docs/ClipVisionLoader/en.md)
- [Официальный workflow bundle 0.1.42](https://pypi.org/project/comfyui-workflow-templates-json/0.1.42/)
