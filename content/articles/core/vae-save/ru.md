# VAESave: сохранить state dict VAE в safetensors

## Что делает нода

`VAESave` получает объект `VAE`, извлекает state dict его `first_stage_model` и записывает нумерованный файл `.safetensors`. Diffusion MODEL и CLIP в этот файл не входят.

Нода полезна после загрузки или изменения VAE, когда автоэнкодер нужно хранить отдельно от checkpoint. Она не кодирует и не декодирует изображения, не сравнивает качество reconstruction и не проверяет, сможет ли выбранный loader прочитать результат.

Скрытые `prompt` и `extra_pnginfo` сохраняются как JSON-строки metadata, если ComfyUI запущен без `--disable-metadata`.

## Место в графе

Ставьте `VAESave` в конце ветки `VAE`. Источником может быть `VAELoader` или нода, возвращающая совместимый объект VAE. Saver не имеет соединяемого выхода, поэтому ветку для decode или encode нужно разветвить до него.

`VAESave` сохраняет только автоэнкодер. Если требуется единый файл с MODEL, CLIP и VAE, используйте `CheckpointSave`. Для model-only и CLIP-only экспорта предусмотрены `ModelSave` и `CLIPSave`.

Тип порта `VAE` подтверждает интерфейс объекта, но не указывает семейство модели. Сохраняйте рядом сведения о pipeline и исходном loader.

## Входы

- `vae: VAE` — обязательный объект автоэнкодера.
- `filename_prefix: STRING` — относительный prefix внутри output; default `vae/ComfyUI_vae`.
- `prompt: PROMPT` — скрытый снимок prompt-графа.
- `extra_pnginfo: EXTRA_PNGINFO` — скрытые дополнительные данные, обычно workflow.

В реализации 0.32.0 `VAE.get_sd()` возвращает `first_stage_model.state_dict()`. Нода не принимает dtype, формат сжатия, архитектурный label или выбор отдельных слоёв.

Подключать `IMAGE` или `LATENT` сюда нельзя: нода сохраняет параметры VAE, а не данные, которые VAE кодирует или декодирует.

## Выходы

Соединяемых выходов нет: `RETURN_TYPES` пуст, `save` возвращает `{}`. Путь к файлу не передаётся следующей ноде и не возвращается отдельным UI-result.

Default prefix даёт имя вроде `output/vae/ComfyUI_vae_00001_.safetensors`. Собственный `vae/wizard-vae` создаст `output/vae/wizard-vae_00001_.safetensors` при свободном счётчике.

Успешная запись не подтверждает совместимость с `VAELoader`. Проверяйте файл отдельной загрузкой и encode/decode-тестом на контролируемых данных.

## Как работает внутри

Сначала `folder_paths.get_save_image_path` нормализует prefix, проверяет целевую подпапку и выбирает номер. Затем нода готовит metadata: `prompt` превращается в JSON-строку, каждое значение `extra_pnginfo` также проходит через `json.dumps`.

После этого вызывается `vae.get_sd()`. В pinned реализации VAE этот метод возвращает state dict `first_stage_model` без дополнительной упаковки MODEL или CLIP. Полученный словарь передаётся `comfy.utils.save_torch_file`, который использует `safetensors.torch.save_file`.

В отличие от общего checkpoint helper, `VAESave` не добавляет `modelspec.architecture`, `modelspec.predict_key`, `v_pred`, `ztsnr` или EDM sigma markers. При `--disable-metadata` prompt/workflow metadata не записываются; тензоры VAE сохраняются как прежде.

Метод заканчивается пустым словарём. Никакой автоматической проверки записанного safetensors код ноды не выполняет.

## Настройки

`filename_prefix` управляет только местом внутри output и основой имени. Prefix `vae/project-a/decoder` создаёт подпапку `output/vae/project-a`. Helper сравнивает `realpath` output-корня и целевого каталога, поэтому прямой выход через `..` и уже существующий symlink наружу отклоняются. Проверка и запись идут отдельными шагами, без общей атомарной блокировки.

Счётчик равен максимальному распознанному номеру для того же basename плюс один. Если каталога нет, он создаётся, а первый номер равен `1`. Одновременные записи с одним prefix не резервируют номер атомарно и могут конфликтовать.

Общий helper допускает подстановки даты и времени. `%width%` и `%height%` для VAESave равны `0`, потому что нода не передаёт размеры изображения.

## Пример подключения

Fragment `recipe.vae-save-export` содержит одну `VAESave`:

1. Подключите объект `VAE` ко входу `vae`.
2. Задайте `filename_prefix = vae/wizard-vae`.
3. Выполните граф и найдите новый файл в `output/vae`.
4. В отдельном тестовом графе загрузите файл и проверьте encode/decode на известном изображении.

`VAESave` отсутствует во всех 512 JSON официального workflow-пакета 0.1.42: проверены 496 корневых графов и 272 subgraph. Поэтому fragment — source-derived пример. Изолированная проба во временной папке вызвала точный метод на синтетическом VAE, проверила state dict, metadata, счётчик и блокировку `../escape`. Полный fragment с настоящим VAE не запускался.

## Частые ошибки

**Ожидался checkpoint с моделью.** VAESave пишет только state dict автоэнкодера. Для полного комплекта используйте `CheckpointSave`.

**Файл не появился в папке моделей VAE.** Нода пишет в `output`, а не в каталог `models/vae`. Default путь — `output/vae`. Перемещение в каталог загрузчика — отдельное действие.

**`VAELoader` не показывает новый файл.** Output и model directories различаются. Поместите проверенный файл в настроенный VAE search path и обновите список моделей.

**После загрузки изменились цвета или детали.** Safetensors мог сохраниться корректно, но VAE может не соответствовать используемой diffusion-модели или latent-формату. Сверьте происхождение компонентов.

**Prefix с абсолютным или родительским путём отклонён.** Используйте относительную подпапку внутри output.

**Два запуска выбрали одно имя.** Helper не блокирует счётчик. Разведите параллельные задания по prefix.

## Ограничения и производительность

Запись синхронно проходит по всему state dict VAE. Размер обычно меньше полного checkpoint, но всё равно зависит от архитектуры и dtype. Writer не выполняет пользовательское сжатие, не проверяет свободное место и не вычисляет checksum.

Нода не записывает стандартный architecture label. Получателю нужны имя, происхождение и сведения о совместимом pipeline. Prompt metadata может помочь восстановить граф, но не заменяет технический manifest и отключается флагом запуска.

Изолированный probe проверяет ветку вызовов на маленьких синтетических тензорах. Он не измеряет производительность на полном VAE и не подтверждает совместимость с каждым loader.

## Совместимость и источники

Статья сверена с ComfyUI `0.32.0`, commit `c2bcbecd82ec5ae66594340b395c24ef0217b238`, frontend `1.48.7`. Runtime fingerprint: `sha256:e5a29dc13db67771a7c802fd28188c4f36fe5006c6e01b3237e93a898c5cec77`. Нода не помечена как experimental, deprecated, dev-only или API node; replacement не заявлен.

В embedded-docs 0.5.9 нет каталога `VAESave` и страниц EN/RU. Назначение, точный scope state dict, metadata и файловое поведение поэтому описаны по исполняемому коду.

- [Реализация `VAESave`](https://github.com/Comfy-Org/ComfyUI/blob/c2bcbecd82ec5ae66594340b395c24ef0217b238/comfy_extras/nodes_model_merging.py#L308-L340)
- [`VAE.get_sd`](https://github.com/Comfy-Org/ComfyUI/blob/c2bcbecd82ec5ae66594340b395c24ef0217b238/comfy/sd.py#L1423-L1424)
- [Safetensors writer](https://github.com/Comfy-Org/ComfyUI/blob/c2bcbecd82ec5ae66594340b395c24ef0217b238/comfy/utils.py#L169-L173)
- [Проверка output-пути и счётчик](https://github.com/Comfy-Org/ComfyUI/blob/c2bcbecd82ec5ae66594340b395c24ef0217b238/folder_paths.py#L520-L566)

Редактор пока не проверил материал вручную.
