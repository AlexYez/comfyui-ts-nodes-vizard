# ModelSave: сохранить только diffusion MODEL

## Что делает нода

`ModelSave` записывает state dict объекта `MODEL` в нумерованный файл `.safetensors`. CLIP и VAE не передаются в сериализатор, поэтому результат является model-only файлом, а не полным checkpoint.

Нода подходит для экспорта diffusion-модели после merge, LoRA patch или другой операции, меняющей `MODEL`. Она не запекает отдельно хранящиеся CLIP/VAE, не запускает sampler и не проверяет, что результат можно загрузить выбранной loader-нодой.

Общий save helper добавляет некоторые modelspec и prediction сведения для точно распознанных семейств. Hidden prompt/workflow metadata записываются, если не включён `--disable-metadata`.

## Место в графе

Ставьте `ModelSave` после последней ноды, которая меняет `MODEL`. Это terminal output-node без соединяемых выходов. Для одновременного sampling разветвите `MODEL` до saver: одна связь пойдёт в guider или sampler, другая — в `ModelSave`.

Не путайте model-only экспорт с `CheckpointSave`. Последняя требует ещё `CLIP` и `VAE` и собирает единый state dict. `ModelSave` сохраняет только diffusion-часть, поэтому для повторного использования понадобятся совместимые текстовый энкодер и автоэнкодер.

Типичный получатель — подходящий loader diffusion-моделей, но совместимость зависит от архитектуры и схемы ключей, а не только от расширения.

## Входы

- `model: MODEL` — обязательная diffusion-модель с текущими patch.
- `filename_prefix: STRING` — относительный prefix внутри output; default `diffusion_models/ComfyUI`.
- `prompt: PROMPT` — скрытый снимок prompt-графа.
- `extra_pnginfo: EXTRA_PNGINFO` — скрытые дополнительные данные, обычно workflow.

Входов `clip` и `vae` нет. Если downstream-процесс ожидает единый checkpoint, этого файла будет недостаточно.

Нода не принимает dtype или режим quantization. Сохраняемый state dict формирует метод `model.state_dict_for_saving(None, None, None)` внутри общего checkpoint serializer.

## Выходы

Runtime объявляет пустые `RETURN_TYPES`; метод возвращает `{}`. Ни путь, ни сам `MODEL` дальше по графу не передаются.

Default prefix создаёт файл вида `output/diffusion_models/ComfyUI_00001_.safetensors`. Prefix `diffusion_models/wizard-model` даст `wizard-model_00001_.safetensors`, если номер свободен.

Нода не сообщает размер, checksum и итоговый список ключей. Эти проверки нужно выполнять отдельным шагом после записи.

## Как работает внутри

`ModelSave` вызывает тот же helper, что и `CheckpointSave`, но передаёт только `model`. Helper выбирает output-путь и номер, затем пытается определить modelspec architecture по точному классу базовой модели. В 0.32.0 есть mappings для SDXL base/edit, SDXL Refiner, SVD img2vid и SD3; SD3 всегда получает строку `stable-diffusion-v3-medium`, рядом с которой в исходнике стоит TODO для других вариантов.

Для распознанного семейства добавляются `modelspec.sai_model_spec`, `modelspec.implementation` и title. Точный `model_type` определяет `modelspec.predict_key`: `epsilon` для `EPS`, `v` для `V_PREDICTION`. V-prediction также добавляет пустой tensor `v_pred`, при `zsnr` — `ztsnr`. Совместное наследование sampling от `ModelSamplingContinuousEDM` и `V_PREDICTION` добавляет tensors с `sigma_max` и `sigma_min`.

Далее `comfy.sd.save_checkpoint` загружает model patcher, вызывает `model.state_dict_for_saving` без CLIP/VAE/CLIP Vision, добавляет marker-тензоры, приводит non-contiguous тензоры к contiguous и передаёт словарь safetensors writer.

`--disable-metadata` убирает prompt и `extra_pnginfo`, но не modelspec, prediction metadata и marker-тензоры. Эти две категории в коде формируются независимо.

## Настройки

`filename_prefix` может включать подпапки внутри output. Helper проверяет `realpath` целевой папки относительно output-корня и отклоняет `..` или уже существующий symlink, ведущий наружу. Проверка пути и открытие файла не атомарны, поэтому при враждебных изменениях файловой системы между шагами остаётся класс гонок.

Счётчик выбирается по максимальному распознанному номеру для того же basename. Каталог создаётся автоматически. Блокировки нет: параллельные экспорты с одинаковым prefix могут выбрать один номер.

В prefix работают подстановки локальной даты и времени. `%width%` и `%height%` становятся `0`, поскольку ModelSave не передаёт размеры изображения.

## Пример подключения

Fragment `recipe.model-save-export` содержит одну `ModelSave`:

1. Подключите итоговый `MODEL` ко входу `model`.
2. Задайте `filename_prefix = diffusion_models/wizard-model`.
3. Выполните граф и проверьте новый файл в `output/diffusion_models`.
4. Отдельно зафиксируйте версии совместимых CLIP и VAE.
5. Перед публикацией загрузите файл в чистом тестовом графе и проведите короткую детерминированную генерацию.

Во всех 512 JSON workflow templates 0.1.42, включая 272 subgraph, прямых или текстовых вхождений `ModelSave` нет. Fragment составлен по source/runtime контракту. Изолированная temp-dir проба выполнила общий helper на синтетическом MODEL, проверила model-only вызов, metadata и prediction markers. Настоящие веса и полный fragment не запускались.

## Частые ошибки

**Файл приняли за полный checkpoint.** В нём нет CLIP и VAE. Используйте `CheckpointSave`, если нужен единый комплект.

**Loader не принимает файл.** Проверьте архитектуру, схему ключей и ожидаемый тип loader. Расширение safetensors не делает форматы взаимозаменяемыми.

**После загрузки нет ожидаемого LoRA-эффекта.** Убедитесь, что patch действительно присутствовал в переданном `MODEL` и что `state_dict_for_saving` данного model patcher материализует нужные веса. Сравните ключи или выход тестовой генерации.

**При выключенных metadata остались `v_pred` или modelspec-поля.** `--disable-metadata` относится к prompt/workflow, а модельные markers создаются отдельно.

**SD3 architecture label выглядит слишком конкретным.** В pinned коде все объекты класса SD3 получают label medium. Не используйте его как единственное доказательство варианта модели.

**Параллельные задания столкнулись по имени.** Счётчик не резервируется атомарно. Используйте уникальные prefix.

## Ограничения и производительность

Экспорт полной diffusion-модели требует значительного дискового пространства и времени I/O. Serializer загружает model patcher и собирает state dict; non-contiguous тензоры получают contiguous-копии. Пиковая память может вырасти на объём копируемых тензоров.

Нода не проверяет свободное место, не пишет checksum и не выполняет transaction/rename после полной записи. Для release-процесса проверяйте размер, hash, набор ключей и загрузку результата. Не удаляйте исходные веса до этой проверки.

Modelspec mapping ограничен точными классами. Для неизвестного семейства файл может быть корректным, но architecture metadata не появится. Для известных классов label всё равно не заменяет проверку конкретного варианта.

## Совместимость и источники

Статья проверена на ComfyUI `0.32.0`, commit `c2bcbecd82ec5ae66594340b395c24ef0217b238`, frontend `1.48.7`. Runtime fingerprint: `sha256:72ab14234c202d2295bcf27311f564ff53f3905fd2626b855cec673a584a49f1`. Нода не experimental, deprecated, dev-only или API node; replacement не заявлен.

Embedded docs 0.5.9 перечисляют основной вход и отсутствие outputs, но не описывают model-family mappings, prediction markers, path guard и счётчик. Русская embedded-страница начинается переводческим шаблоном и переводит runtime-идентификаторы; здесь имена портов сохранены в точном виде из `/object_info`.

- [Общий `save_checkpoint` helper](https://github.com/Comfy-Org/ComfyUI/blob/c2bcbecd82ec5ae66594340b395c24ef0217b238/comfy_extras/nodes_model_merging.py#L170-L227)
- [Определение `ModelSave`](https://github.com/Comfy-Org/ComfyUI/blob/c2bcbecd82ec5ae66594340b395c24ef0217b238/comfy_extras/nodes_model_merging.py#L342-L360)
- [Сборка и запись model state dict](https://github.com/Comfy-Org/ComfyUI/blob/c2bcbecd82ec5ae66594340b395c24ef0217b238/comfy/sd.py#L2338-L2362)
- [Embedded docs 0.5.9](https://github.com/Comfy-Org/embedded-docs/blob/1d258cf6e374d60d138a2bfcd273c7e11f750ef9/comfyui_embedded_docs/docs/ModelSave/en.md)

Редактор пока не проверил материал вручную.
