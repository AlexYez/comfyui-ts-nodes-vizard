# GLIGENLoader: загрузить модель пространственного условия

## Что делает нода

`GLIGENLoader` находит файл в группе путей `gligen`, безопасно читает тензоры и собирает GLIGEN-модель для пространственного conditioning. В обычной установке каталог — `ComfyUI/models/gligen`; дополнительные пути задаются через `extra_model_paths.yaml`.

Загрузчик ищет fuser-веса в input, middle и output blocks, восстанавливает gated attention modules и position network. После сборки он при необходимости переводит модель в fp16 и оборачивает её в `CoreModelPatcher` с load-device ComfyUI и offload-device UNet.

Выход `GLIGEN` сам по себе не меняет `MODEL` или `CONDITIONING`. Объект нужно записать в conditioning через `GLIGENTextBoxApply`; sampler обнаружит metadata и подключит middle patch во время denoise.

## Когда использовать и когда не использовать

Используйте загрузчик для GLIGEN checkpoint, предназначенного для позиционного текстового conditioning и совместимого с основной diffusion-моделью. Типичный сценарий — задать текст и прямоугольник, где должен появиться объект.

Не загружайте сюда обычный Stable Diffusion checkpoint, ControlNet, LoRA или IP-Adapter. Реализация ожидает специальные ключи `.fuser.` и `position_net.*`; совпадающее расширение файла не делает веса GLIGEN.

Если задача сводится к региональному весу уже готового conditioning без GLIGEN-модели, используйте area/mask conditioning utilities. Они меняют metadata другого вида и не требуют отдельного fuser-патча.

## Короткий рецепт подключения

1. Поместите совместимый GLIGEN checkpoint в `models/gligen`.
2. Выберите его в `gligen_name`.
3. Подключите `GLIGEN` к `gligen_textbox_model` ноды `GLIGENTextBoxApply`.
4. Подайте туда базовое `CONDITIONING` и `CLIP`, затем задайте текст и рамку.
5. Направьте выходное conditioning в sampler вместе с совместимой основной моделью.

Fragment «Добавить текстовую область 256×256» показывает загрузчик и apply, но оставляет имя checkpoint для выбора из локальной установки. Он основан на закреплённом исходнике и runtime: официальный набор workflow 0.1.42 не содержит GLIGEN-ноды. Веса и сэмплер не запускались.

## Входы, выходы и параметры

`gligen_name` — обязательный динамический список файлов из группы `gligen`. Чистый `/object_info` содержит пустой массив, потому что repository snapshot не включает модели. Значения списка исключены из schema fingerprint.

Выход один: `GLIGEN`, не list-output. Это `CoreModelPatcher` вокруг внутренней `Gligen` с fuser-модулями и position network. Интерфейс ноды не содержит device, dtype, strength или координат: device/dtype выбираются общей политикой, а прямоугольники задаёт `GLIGENTextBoxApply`.

Loader не возвращает `MODEL`. GLIGEN работает как дополнительная модель, которую sampler извлекает из conditioning metadata.

## Типовые связки

Основная цепочка: `GLIGENLoader → GLIGENTextBoxApply → KSampler`. В apply также приходят positive `CONDITIONING` и `CLIP`. Обычный negative conditioning можно оставить без GLIGEN metadata, если workflow не требует обратного пространственного условия.

Несколько `GLIGENTextBoxApply` можно поставить последовательно для нескольких объектов. Все записи должны использовать одну совместимую GLIGEN-модель; последняя apply хранит один model patcher и общий список position params.

Sampler helpers извлекают GLIGEN из conditioning как additional model. Затем sampler вызывает `set_position` и ставит полученный callback в `middle_patch`.

## Практический пример

Полный census `comfyui-workflow-templates-json 0.1.42` проверил 512 JSON, все root nodes и 272 subgraphs. Ни `GLIGENLoader`, ни `GLIGENTextBoxApply` не встречаются. Следовательно, закреплённый официальный набор не даёт подтверждённого имени файла, widget values или topology.

Fragment использует явную подсказку `выберите совместимый GLIGEN textbox checkpoint`, а не выдуманное имя модели. В изолированной пробе закреплённого класса подменены только поиск пути и `comfy.sd.load_gligen`: подтверждены группа `gligen`, переданный путь и возврат объекта без преобразования на уровне класса ноды.

Эта проба не читает реальные веса. Структура fuser, fp16-ветвь и patcher проверены чтением `comfy/gligen.py` и `comfy/sd.py`.

## Частые ошибки и способы проверки

**В списке нет файла.** Проверьте каталог `models/gligen`, расширение из разрешённых `folder_paths` и обновление inventory.

**Загрузка падает на ключах position network.** Это признак неподходящего или неполного checkpoint. Нужны fuser-веса и `position_net.null_positive_feature` с остальными слоями position network.

**Рамки не влияют на результат.** Убедитесь, что `GLIGENTextBoxApply` стоит в той ветви conditioning, которая действительно подключена к sampler.

**GLIGEN не совпадает с основной моделью.** Runtime-тип не проверяет семейство diffusion model. Сверяйте key dimension и назначение checkpoint.

**Ищут ручной fp16-переключатель.** У этой ноды его нет. Решение принимает `model_management.should_use_fp16()`.

## Производительность и внутреннее поведение

`comfy.sd.load_gligen` читает checkpoint с `safe_load=True`, строит attention-модули и position network. Для key dimension 768 используется восемь heads; для другого размера head dimension фиксируется в 64, а число heads вычисляется из query dimension.

Если общая политика ComfyUI выбирает fp16, вся собранная модель переводится через `.half()`. Иначе loader не делает дополнительного явного cast. `CoreModelPatcher` использует текущий torch device для загрузки и UNet offload device для выгрузки.

Во время sampling GLIGEN становится дополнительной моделью. Память расходуется не только при загрузке: сэмплер должен загрузить patcher и выполнить gated attention для пространственных условий.

## Совместимость, изменения и статус

Статья закреплена на ComfyUI `0.32.0`, frontend `1.48.7`, runtime ID `GLIGENLoader`, модуле `nodes`. Fingerprint: `sha256:d87968d9c43ce26992edd9757b34ce0469e91be1dec348875cb151df645401ac`.

Runtime не ставит deprecated, experimental, dev-only или API-node flags; это не output node. В pinned wheel официальных workflow GLIGEN отсутствует, поэтому статья остаётся draft/in_review.

Embedded docs 0.5.9 указывают каталог и общий смысл выхода, но не раскрывают структуру checkpoint, fp16-ветвь, device/offload и sampler lifecycle.

## Связанные ноды и источники

`GLIGENTextBoxApply` добавляет модель, CLIP embedding и координаты в metadata. `CLIPTextEncode` создаёт базовое текстовое conditioning, а `KSampler` применяет spatial patch. Area/mask conditioning меняют область стандартного conditioning без GLIGEN fuser.

- [Реализация `GLIGENLoader`](https://github.com/Comfy-Org/ComfyUI/blob/c2bcbecd82ec5ae66594340b395c24ef0217b238/nodes.py#L1196-L1209)
- [Safe load, fp16 и `CoreModelPatcher`](https://github.com/Comfy-Org/ComfyUI/blob/c2bcbecd82ec5ae66594340b395c24ef0217b238/comfy/sd.py#L1997-L2002)
- [Сборка fuser и position network](https://github.com/Comfy-Org/ComfyUI/blob/c2bcbecd82ec5ae66594340b395c24ef0217b238/comfy/gligen.py#L259-L299)
- [Embedded docs 0.5.9 для `GLIGENLoader`](https://github.com/Comfy-Org/embedded-docs/blob/1d258cf6e374d60d138a2bfcd273c7e11f750ef9/comfyui_embedded_docs/docs/GligenLoader/en.md)
- [Официальный workflow bundle 0.1.42](https://pypi.org/project/comfyui-workflow-templates-json/0.1.42/)
