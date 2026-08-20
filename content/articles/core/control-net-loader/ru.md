# ControlNetLoader: выбрать и загрузить модель контроля

`ControlNetLoader` читает выбранный checkpoint и возвращает `CONTROL_NET`. Он не принимает базовую `MODEL`, не применяет подсказку и не меняет conditioning: для этого после loader нужна `ControlNetApplyAdvanced` или совместимая специализированная нода.

## Combo строится из двух стандартных каталогов

Runtime получает `control_net_name` через `folder_paths.get_filename_list("controlnet")`. В ComfyUI 0.32.0 эта категория объединяет `models/controlnet` и `models/t2i_adapter`.

Пути, добавленные в `extra_model_paths.yaml` для той же категории, также могут попасть в список. Если новый файл не появился, обновите список моделей или интерфейс; само выполнение ноды не сканирует произвольный путь из текстового поля.

## Список ограничен расширениями моделей

Общий набор разрешает `.ckpt`, `.pt`, `.pt2`, `.bin`, `.pth`, `.safetensors`, `.pkl` и `.sft`. Расширение допускает файл в combo, но не доказывает, что внутри лежит поддерживаемый ControlNet.

Для safetensors используется соответствующий reader. Остальные checkpoint-файлы проходят через `torch.load(..., weights_only=True)` в закреплённом source; затем loader анализирует полученный state dict.

## Архитектура определяется по ключам state dict

Loader различает несколько семейств: diffusers ControlNet и Union, классические ControlNet, Control LoRA, Hunyuan, Flux, SD3/SD3.5, Qwen и T2I Adapter fallback. Решение принимается по характерным именам и формам весов.

Имя файла не выбирает реализацию. Переименование несовместимого checkpoint не сделает его ControlNet нужной архитектуры.

## Обычный loader не получает базовую MODEL

`ControlNetLoader` вызывает `comfy.controlnet.load_controlnet(path)` без второго аргумента. Это правильный путь для самостоятельного ControlNet, веса которого уже готовы к загрузке.

Для checkpoint с разностными весами существует `DiffControlNetLoader`: он передаёт базовую `MODEL`. Не подменяйте выбор ноды догадкой по слову `controlnet` в имени файла — смотрите инструкцию к конкретной модели.

## Нераспознанный файл останавливает ноду

Если общий loader не смог определить ControlNet или T2I Adapter, он возвращает `None` и пишет ошибку в log. `ControlNetLoader` дополнительно превращает такой результат в `RuntimeError` о невалидной модели.

Сообщение не означает, что файл обязательно повреждён: возможны неподдерживаемый формат, неверная папка модели или checkpoint другого типа.

## Совместимость проверяется не типом порта

Все успешно загруженные варианты выходят как `CONTROL_NET`, однако этот тип не кодирует семейство базовой модели, число каналов подсказки и ожидаемый preprocessor. Несовместимость часто проявляется только при подготовке или sampling.

Выбирайте ControlNet, checkpoint, карту контроля и VAE из одной проверенной схемы. Официальный workflow модели надёжнее случайного сочетания файлов с совпадающими socket types.

## Выполнение использует кэш входной сигнатуры

У ноды нет собственного `IS_CHANGED` с хэшем или временем изменения файла. Execution cache учитывает class type и выбранное имя; повтор без изменения входов может вернуть уже загруженный объект.

Если заменить файл другими байтами под тем же именем, входная сигнатура не изменится. Для гарантированной перезагрузки очистите подходящий cache или перезапустите ComfyUI, а не полагайтесь только на неизменившийся combo.

## В wheel есть SD3.5 и Qwen ControlNet

Полный census 496 root workflow и 272 subgraph нашёл семь `ControlNetLoader`: пять в root и два в subgraph. Шесть включены, один экземпляр Qwen inpainting имеет `mode = 4` и относится к bypassed-ветке.

Файлы включают SD3.5 blur/canny/depth и три Qwen-Image семейства. Пять loader подключены к `ControlNetApplyAdvanced`; два Qwen inpainting — к специализированной apply-ноде.

## SD3.5 Canny показывает полную связку

В официальном `sd3.5_large_canny_controlnet_example` loader № 46 выбирает `sd3.5_large_controlnet_canny.safetensors`. Его выход идёт в apply № 51, карта Canny № 47 — в `image`, а VAE checkpoint № 4 — в optional `vae`.

Apply использует strength 0,66 и диапазон 0–1, затем передаёт обе ветви в KSampler № 3. Это доказанная топология именно для указанного комплекта SD3.5.

## Fragment оставляет модели и conditioning внешними

Рецепт сохраняет центральную часть официальной топологии: `ControlNetLoader → ControlNetApplyAdvanced` с параметрами 0,66 / 0 / 1. Positive, negative, подготовленная IMAGE-карта и VAE приходят извне; filename служит явным placeholder для установленной модели.

Fragment не содержит SD3.5 checkpoint, Canny preprocessor и sampler, поэтому не выдаётся за полный workflow. Схема проверена, но реальный файл ControlNet не загружался и fragment в ComfyUI не исполнялся. Редактор пока не проверил материал вручную.

## Источники

- [ControlNetLoader и DiffControlNetLoader в ComfyUI v0.32.0](https://github.com/Comfy-Org/ComfyUI/blob/c2bcbecd82ec5ae66594340b395c24ef0217b238/nodes.py#L862-L894)
- [Определение форматов ControlNet](https://github.com/Comfy-Org/ComfyUI/blob/c2bcbecd82ec5ae66594340b395c24ef0217b238/comfy/controlnet.py#L728-L893)
- [Каталоги и расширения моделей](https://github.com/Comfy-Org/ComfyUI/blob/c2bcbecd82ec5ae66594340b395c24ef0217b238/folder_paths.py#L10-L38)
- [Execution cache по входной сигнатуре](https://github.com/Comfy-Org/ComfyUI/blob/c2bcbecd82ec5ae66594340b395c24ef0217b238/comfy_execution/caching.py#L82-L127)
- [Официальный SD3.5 Canny workflow](https://github.com/Comfy-Org/workflow_templates/blob/cca1ea5ea4560108ecc2f44dee951f41ea433062/templates/sd3.5_large_canny_controlnet_example.json)
