# SkipLayerGuidanceSD3: SD3-обёртка над пропуском double-блоков

## Что делает нода

`SkipLayerGuidanceSD3` — узкая обёртка над `SkipLayerGuidanceDiT`. Она передаёт `layers` в generic-реализацию как `double_layers`, оставляет `single_layers` пустым и использует `rescaling_scale = 0`. В активном окне выполняется дополнительный conditional-проход с обходом выбранных joint-блоков MMDiT, после чего разность predictions добавляется к CFG-результату.

Нода помечена experimental. Название фиксирует исходную модельную семью, но execute не проверяет тип модели: фактическая совместимость определяется поддержкой replacement-ключей `("double_block", index)`.

## Место в графе

Поместите ноду после загрузки SD3 MODEL и после patches, меняющих `model_sampling`, затем передайте выход sampler или guider. Границы окна переводятся в sigma внутри вызванного generic execute в момент построения MODEL-ветви; downstream sampling patch уже не пересчитает их.

Нода добавляет post-CFG hook в список. Другие post-hooks выполнятся в порядке их добавления. На дополнительном проходе SLG заменяет совпавшие double-block replacements своим обходом, сохраняя replacements других блоков и пространств имён.

## Входы

`model: MODEL` — входная модель. `layers: STRING` имеет default `"7, 8, 9"` и advanced-флаг. Строка разбирается тем же `re.findall(r'\d+')`, что и generic-нода: разделители свободные, знак минус не сохраняется, десятичная запись распадается на несколько индексов, диапазон не проверяется.

`scale: FLOAT` — default 3, диапазон 0–10, шаг 0,1. `start_percent` и `end_percent` — defaults 0,01 и 0,15, диапазон 0–1, шаг 0,001. Все пять входов обязательны в `/object_info`.

## Выходы

Единственный выход `MODEL` возвращает результат generic execute. При пустой строке `layers` generic guard видит пустые double- и single-списки и возвращает исходный MODEL без clone.

Выход не содержит latent или prediction. Patch проявится только во время sampling, когда sampler вызовет post-CFG hook.

## Как работает внутри

MMDiT хранит joint blocks в массиве `joint_blocks` и для каждого индекса проверяет ключ `("double_block", i)` в `patches_replace["dit"]`. Обычный block возвращает обновлённые text и image tensors; функция SLG вместо него возвращает входные `txt` и `img`, то есть обходит вычисление блока.

Generic-формула использует `R + scale × (C − S)`, где `R` — текущий CFG-результат, `C` — обычный conditional prediction, `S` — conditional prediction с обходом блоков. Окно проверяется включительно: `sigma_end ≤ σ ≤ sigma_start`. SD3-обёртка не включает rescaling.

## Настройки

Defaults `7, 8, 9` — исходные значения интерфейса, а не проверенный preset для любого SD3 checkpoint. Сначала убедитесь, что модель действительно использует MMDiT joint blocks и что индексы существуют. Сравнивайте с обходной MODEL-ветвью при одинаковых seed, sigmas и conditioning.

`scale = 0` оставляет hook, но не запускает дополнительный проход. `start_percent > end_percent` создаёт пустое окно; равные значения требуют точного совпадения sigma с границей. Пустой `layers` — более полный no-op, поскольку clone и hook вообще не создаются.

## Пример подключения

Исчерпывающий обход bundle 0.1.42 — 512 JSON, 496 root graphs и 272 `definitions.subgraphs` — не нашёл ни одного `SkipLayerGuidanceSD3` и ни одного текстового упоминания exact ID. Поэтому `recipe.skip-layer-guidance-sd3-source` не выдаётся за официальный template.

Source-derived fragment использует `MODEL → ModelSamplingSD3 (shift 3) → SkipLayerGuidanceSD3 (layers 7,8,9; scale 3; окно 0,01–0,15) → KSampler`. Positive, negative и latent остаются внешними входами. Fragment проверен по runtime-схеме, но не импортировался, не запускал SD3 weights и не подтверждает качество этого preset.

## Частые ошибки

**Ищут официальный SD3 workflow для этой ноды в bundle 0.1.42.** Его там нет; пример справочника выведен из source и schema.

**Считают `layers` универсальными номерами.** Это индексы `joint_blocks` конкретной архитектуры. Несуществующий индекс молча не применяется.

**Ждут изменения single blocks.** Обёртка передаёт только `double_layers=layers`; `single_layers` остаётся пустым.

**Повторяют описание negative conditioning.** Закреплённый generic-код вызывает дополнительный batch с `cond`.

**Ставят ModelSamplingSD3 после SLG.** Patch сработает, но проценты уже были переведены в sigma по предыдущему sampling-объекту.

## Ограничения и производительность

Каждый активный шаг добавляет один conditional forward MMDiT. Стоимость растёт с шириной окна и размером модели. Обход нескольких блоков делает дополнительный проход дешевле полного, но он всё равно обрабатывает остальные блоки и tensors conditioning/latent.

Нет runtime-проверки семейства, длины `joint_blocks` или смысла выбранных индексов. Нет epsilon-rescaling, потому что SD3 wrapper его не включает. Реальные SD3 weights, качество, VRAM, multi-GPU и совместимость со сторонними block replacements в этой проверке не исполнялись.

## Совместимость и источники

Статья закреплена на ComfyUI `0.32.0`, frontend `1.48.7`, runtime ID `SkipLayerGuidanceSD3`, модуле `comfy_extras.nodes_sd3`. Fingerprint: `sha256:1ec2296cddaf0b1af19cabf4341fab23974bdd65e67589273c697abe280c2ee9`. Runtime flags: experimental true; deprecated, dev_only и api_node false. Replacements и execution aliases отсутствуют.

Embedded docs 0.5.9 описывают дополнительный negative-conditioning pass, хотя обёртка делегирует generic-коду с `cond`. Русская страница содержит шаблонную строку «Вот перевод…» и переводит runtime-имена входов. Механика статьи опирается на pinned source.

- [Обёртка `SkipLayerGuidanceSD3`](https://github.com/Comfy-Org/ComfyUI/blob/c2bcbecd82ec5ae66594340b395c24ef0217b238/comfy_extras/nodes_sd3.py#L169-L199)
- [Generic-реализация SLG](https://github.com/Comfy-Org/ComfyUI/blob/c2bcbecd82ec5ae66594340b395c24ef0217b238/comfy_extras/nodes_slg.py#L8-L88)
- [MMDiT block replacement](https://github.com/Comfy-Org/ComfyUI/blob/c2bcbecd82ec5ae66594340b395c24ef0217b238/comfy/ldm/modules/diffusionmodules/mmdit.py#L940-L979)
- [Embedded docs 0.5.9](https://github.com/Comfy-Org/embedded-docs/blob/1d258cf6e374d60d138a2bfcd273c7e11f750ef9/comfyui_embedded_docs/docs/SkipLayerGuidanceSD3/en.md)
- [Официальный workflow bundle 0.1.42](https://pypi.org/project/comfyui-workflow-templates-json/0.1.42/)
