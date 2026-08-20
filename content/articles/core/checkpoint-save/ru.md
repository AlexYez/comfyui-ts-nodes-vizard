# CheckpointSave: сохранить MODEL, CLIP и VAE одним checkpoint

## Что делает нода

`CheckpointSave` собирает три уже существующих объекта ComfyUI — `MODEL`, `CLIP` и `VAE` — и записывает их в один файл `.safetensors`. Нода нужна в конце ветки, где модель была изменена: например, после merge или patch. Она не обучает модель, не проверяет качество результата и не создаёт превью.

Файл получает имя вида `<prefix>_00001_.safetensors`. Номер подбирается по содержимому целевой подпапки. Скрытые входы `prompt` и `extra_pnginfo` могут попасть в строковые metadata файла, если ComfyUI запущен без `--disable-metadata`.

Экспорт не равен резервной копии всей среды. В файл входят state dict компонентов, а не custom nodes, workflow-зависимости, внешние модели или настройки запуска ComfyUI.

## Место в графе

Ставьте `CheckpointSave` после нод, которые сформировали окончательные `MODEL`, `CLIP` и `VAE`. Три входа должны описывать совместимый pipeline. Сам факт, что порты соединяются по типу, не доказывает совместимость архитектур, размерностей и соглашений о ключах.

Нода помечена как `OUTPUT_NODE = True` и не имеет соединяемых выходов. Ветка заканчивается записью на диск. Если те же компоненты нужны ещё где-то, разветвите связи до `CheckpointSave`.

`CheckpointSave` отличается от `ModelSave`: первая передаёт сериализатору модель, CLIP и VAE, а вторая — только `MODEL`. Для раздельного экспорта текстового энкодера и автоэнкодера предназначены `CLIPSave` и `VAESave`.

## Входы

- `model: MODEL` — diffusion-модель с уже применёнными patch или merge.
- `clip: CLIP` — текстовый энкодер. Перед сборкой checkpoint ComfyUI вызывает `clip.load_model()`, затем `clip.state_dict_for_saving()`.
- `vae: VAE` — автоэнкодер. В сериализатор передаётся результат `vae.get_sd()`.
- `filename_prefix: STRING` — относительный prefix внутри output-каталога. Значение по умолчанию: `checkpoints/ComfyUI`.
- `prompt: PROMPT` — скрытый снимок prompt-графа, который ComfyUI подставляет автоматически.
- `extra_pnginfo: EXTRA_PNGINFO` — скрытые дополнительные сведения, обычно включая workflow.

Входы `model`, `clip` и `vae` обязательны. Нода не предлагает optional-режим для неполного checkpoint: для model-only файла используйте `ModelSave`.

## Выходы

Соединяемых выходов нет: runtime объявляет пустые `RETURN_TYPES`, а метод `save` возвращает `{}`. Узнать путь через следующую ноду нельзя. Ищите файл в `output/<подпапка из filename_prefix>`.

Для prefix `checkpoints/wizard-merged` и свободного счётчика результатом будет `output/checkpoints/wizard-merged_00001_.safetensors`. Следующий запуск обычно создаст `_00002_`, если первый файл остался в этой папке.

Нода не возвращает отчёт о том, какие metadata или marker-тензоры были добавлены. Для проверки содержимого нужен отдельный инспектор safetensors либо повторная загрузка в совместимой среде.

## Как работает внутри

Сначала общий helper `save_checkpoint` получает защищённый output-путь и следующий номер. Затем он определяет несколько metadata по точному Python-классу базовой модели. В ComfyUI 0.32.0 предусмотрены mappings для SDXL base/edit, SDXL Refiner, SVD img2vid и SD3. Для SD3 helper всегда записывает `stable-diffusion-v3-medium`; рядом в исходнике оставлен TODO для других вариантов SD3. Для остальных семейств modelspec architecture не добавляется.

Если mapping сработал, metadata получают `modelspec.sai_model_spec = 1.0.0`, `modelspec.implementation = sgm` и title с именем и номером файла. Поле `modelspec.predict_key` зависит от точного `model_type`: `epsilon` для `EPS`, `v` для `V_PREDICTION`. V-prediction также добавляет пустой tensor `v_pred`, а при `zsnr` — `ztsnr`. Объект sampling, который одновременно относится к `ModelSamplingContinuousEDM` и `V_PREDICTION`, добавляет tensor-ключи `edm_vpred.sigma_max` и `edm_vpred.sigma_min`.

После этого `comfy.sd.save_checkpoint` загружает model patcher и CLIP, получает state dict CLIP и VAE, вызывает `model.state_dict_for_saving(...)`, добавляет marker-тензоры и делает не-contiguous тензоры contiguous. Финальную запись выполняет safetensors writer.

Флаг `--disable-metadata` удаляет только `prompt` и значения `extra_pnginfo`. Он не отключает modelspec, prediction metadata и marker-тензоры, потому что они формируются вне этого условия.

## Настройки

Практически настраивается один видимый параметр — `filename_prefix`. Его каталожная часть остаётся внутри output. Helper нормализует путь, вычисляет `realpath` целевой папки и output-корня и отклоняет выход за пределы корня. Уже существующий symlink, ведущий наружу, также не проходит эту проверку. Проверка и последующая запись не образуют одну атомарную файловую операцию, поэтому не следует описывать механизм как защиту от любой возможной гонки файловой системы.

Prefix поддерживает подстановки `%width%`, `%height%`, `%year%`, `%month%`, `%day%`, `%hour%`, `%minute%`, `%second%`. У saver-нод ширина и высота не передаются, поэтому `%width%` и `%height%` превращаются в `0`; временные поля берутся из локального времени процесса.

Счётчик определяется просмотром уже существующих имён с тем же basename. Номер равен максимальному распознанному значению плюс один. Блокировки или атомарного резервирования номера нет: два одновременных запуска могут выбрать одинаковый путь. Для параллельного экспорта используйте разные prefix или сериализуйте задания.

## Пример подключения

Fragment `recipe.checkpoint-save-export` содержит одну `CheckpointSave`:

1. Подайте окончательный `MODEL` во вход `model`.
2. Подайте совместимый `CLIP` во вход `clip`.
3. Подайте совместимый `VAE` во вход `vae`.
4. Задайте `filename_prefix = checkpoints/wizard-merged`.
5. Выполните граф и проверьте новый `.safetensors` в `output/checkpoints`.

Во всех 512 JSON официального пакета workflow templates 0.1.42 просмотрены корневые графы и 272 subgraph; `CheckpointSave` не найдена. Поэтому fragment основан на runtime-схеме и исходнике, а не выдан за официальный workflow. Изолированная проба проверила path helper, нумерацию, modelspec и prediction markers на синтетических объектах во временной папке. Настоящие веса и полный fragment в ComfyUI не запускались.

## Частые ошибки

**Файл записался, но не загружается как ожидаемый checkpoint.** Проверьте, что `MODEL`, `CLIP` и `VAE` принадлежат совместимому семейству. Save-код собирает state dict, но не прогоняет загрузчик и тестовую генерацию.

**Ожидался файл строго `ComfyUI.safetensors`.** Нода всегда дописывает пятизначный счётчик и подчёркивание: `ComfyUI_00001_.safetensors`.

**Prefix с `../` завершился ошибкой.** Запись вне output запрещена. Укажите подпапку относительно output, например `checkpoints/experiment-a`.

**При `--disable-metadata` в файле всё равно есть modelspec или `v_pred`.** Этот флаг скрывает prompt/workflow metadata, но не служебные сведения модели и не marker-тензоры.

**SD3-файл помечен как medium, хотя использовался другой вариант.** Это ограничение exact mapping в 0.32.0: код содержит одну строку architecture для SD3 и TODO для других вариантов. Проверяйте marker перед публикацией файла.

**Два параллельных задания конфликтуют.** Счётчик вычисляется без блокировки. Разведите задания по prefix или не запускайте одновременную запись в одну папку.

## Ограничения и производительность

Checkpoint может занимать гигабайты. Перед записью ComfyUI загружает необходимые model patcher и CLIP, собирает объединённый state dict и при необходимости создаёт contiguous-копии тензоров. Пиковая память зависит от модели, состояния patch и того, сколько тензоров пришлось копировать. Затем весь объём синхронно проходит через файловую систему.

Нода не проверяет свободное место заранее, не выполняет checksum готового файла и не делает автоматическую загрузку результата. Прерванная запись или заполненный диск нужно обнаруживать по ошибке и состоянию файла. Для release-процесса полезно отдельно проверить размер, hash, набор ключей и пробную загрузку.

Modelspec покрывает лишь перечисленные в исходнике классы. Отсутствие architecture metadata не означает повреждение, а её наличие не доказывает полную совместимость.

## Совместимость и источники

Материал сверён с ComfyUI `0.32.0`, commit `c2bcbecd82ec5ae66594340b395c24ef0217b238`, frontend `1.48.7`. Runtime fingerprint: `sha256:871a9ebfff7c803bfd46924839e2f4ece21f6fc245cf760282f2bb045d1aeccd`. Нода не помечена как experimental, deprecated, dev-only или API node; replacement для неё в pinned inventory не заявлен.

Embedded docs 0.5.9 дают общий обзор, но утверждение о постоянной папке `output/checkpoints` слишком узко: это только результат default prefix, пользователь может выбрать другую подпапку внутри output. Заявления о поддержке архитектур здесь сужены до точных mappings исходника.

- [Реализация `CheckpointSave` и общего helper](https://github.com/Comfy-Org/ComfyUI/blob/c2bcbecd82ec5ae66594340b395c24ef0217b238/comfy_extras/nodes_model_merging.py#L170-L249)
- [Сборка checkpoint state dict](https://github.com/Comfy-Org/ComfyUI/blob/c2bcbecd82ec5ae66594340b395c24ef0217b238/comfy/sd.py#L2338-L2362)
- [Проверка output-пути и счётчик](https://github.com/Comfy-Org/ComfyUI/blob/c2bcbecd82ec5ae66594340b395c24ef0217b238/folder_paths.py#L520-L566)
- [Embedded docs 0.5.9](https://github.com/Comfy-Org/embedded-docs/blob/1d258cf6e374d60d138a2bfcd273c7e11f750ef9/comfyui_embedded_docs/docs/CheckpointSave/en.md)

Редактор пока не проверил материал вручную.
