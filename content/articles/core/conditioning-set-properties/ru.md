# ConditioningSetProperties: маска, hooks и диапазон времени

## Назначение

`ConditioningSetProperties` добавляет к `cond_NEW` до трёх видов metadata: маску, группу hooks и диапазон sampling. Нода не принимает произвольные пары «ключ — значение»: набор ключей жёстко задан реализацией.

Контракт помечен как experimental. При обновлении ComfyUI нужно заново проверять названия портов, тип `TIMESTEPS_RANGE` и правила объединения hooks.

## Место в графе

Ноду ставят после источника `CONDITIONING` и перед sampler или guider. Маска ограничивает пространственный вклад, hooks связывают запись с hook-группой, а диапазон времени задаёт часть sampling, в которой запись активна.

`ConditioningSetMask` решает только задачу маски. `ConditioningSetProperties` собирает маску, hooks и расписание в одном узле. Она не объединяет результат с другой conditioning-ветвью; для этого существует `ConditioningSetPropertiesAndCombine`.

## Входы

`cond_NEW` — обязательный `CONDITIONING`. `strength` принимает числа от 0 до 10 с шагом 0,01. `set_cond_area` выбирается из `default` и `mask bounds`.

Optional-вход `mask` имеет тип `MASK`, `hooks` — `HOOKS`, `timesteps` — `TIMESTEPS_RANGE`. `strength` и `set_cond_area` используются только внутри обработки подключённой маски. Без `mask` оба обязательных виджета ничего не записывают в metadata.

## Выход

Выход имеет тип `CONDITIONING` и сохраняет число записей. Основные embedding-тензоры нода не пересчитывает.

При наличии маски каждая запись получает `mask` с tensor-значением, `mask_strength` с числом и `set_area_to_bounds` с boolean-значением. Hooks хранятся под ключом `hooks` как `HookGroup`; диапазон превращается в два числовых ключа — `start_percent` и `end_percent`.

## Как работает

Helper выполняет операции в порядке hooks → mask → timesteps. Подключённая hook-группа добавляется к каждой записи. Если `hooks` уже были в metadata, реализация создаёт объединённую группу через `clone_and_combine`; одинаковые пары групп повторно использует через локальный cache.

Маска с числом измерений меньше трёх получает ведущую batch-ось. Выбор `mask bounds` записывает `set_area_to_bounds: true`, а `default` — `false`. В конце два элемента tuple `TIMESTEPS_RANGE` записываются как `start_percent` и `end_percent`. Повторный вызов перезаписывает mask- и timestep-ключи, но добавляет hooks к существующим.

## Параметры и настройка

Для локального условия подключите `MASK`, задайте `strength` и решите, нужно ли сужать вычисляемую area до границ ненулевой маски. `mask bounds` влияет на area, а не обрезает сам tensor маски.

Вход `hooks` принимает готовый объект `HOOKS`, созданный hook-нодами. Строку, имя LoRA или словарь туда передать нельзя. `timesteps` тоже не пара чисел в двух портах: это типизированный tuple-объект, например с выхода `ConditioningTimestepsRange`.

## Проверенный пример

Fragment «Маска и свойства conditioning» принимает внешние `CONDITIONING` и `MASK`, задаёт `strength: 0.8` и `set_cond_area: mask bounds`. По закреплённому исходнику это записывает mask, `mask_strength: 0.8` и `set_area_to_bounds: true`; hooks и timesteps остаются неподключёнными.

Во всех 512 official workflow templates JSON 0.1.42, включая `definitions.subgraphs`, runtime ID `ConditioningSetProperties` отсутствует. Поэтому fragment подтверждает source/runtime-контракт, но не воспроизводит официальный workflow и не проходил model run.

## Частые ошибки

**Strength меняют без маски и ждут нового веса.** Helper читает strength только в `set_mask_for_conditioning`. Без `MASK` metadata `strength` или `mask_strength` не появляется.

**`mask bounds` считают режимом crop.** Флаг просит sampler определить area по ненулевым границам маски. Сама маска остаётся в metadata.

**Новые hooks считают заменой старых.** По умолчанию hook-группы объединяются. Это может оставить активными обе группы.

**Ноду принимают за Combine.** Она возвращает обработанный `cond_NEW`, но не добавляет к нему отдельный базовый список.

## Ограничения и производительность

Каждый подключённый вид свойства вызывает отдельный проход по списку и копирование metadata-словарей; embedding-тензоры переиспользуются. Без optional-входов helper может вернуть исходный список без изменений, несмотря на видимые required-виджеты strength и area mode.

Hooks могут разделить downstream-вычисления на группы. `mask bounds` может уменьшить обрабатываемую область, но итог зависит от формы маски и sampler. Нода не проверяет порядок границ внутри `TIMESTEPS_RANGE` и не гарантирует совместимость experimental-контракта с другой версией ComfyUI.

## Совместимость и источники

Материал закреплён на ComfyUI 0.32.0, commit `c2bcbecd82ec5ae66594340b395c24ef0217b238`. Runtime ID — `ConditioningSetProperties`, python module — `comfy_extras.nodes_hooks`, `experimental: true`.

Embedded docs 0.5.9 по пути `comfyui_embedded_docs/docs/ConditioningSetProperties/en.md` помечены как AI-generated. Они перечисляют порты, но создают впечатление, что strength сам по себе регулирует conditioning. Исходник показывает: это значение становится `mask_strength` только при подключённой маске.

- [Класс `ConditioningSetProperties`](https://github.com/Comfy-Org/ComfyUI/blob/c2bcbecd82ec5ae66594340b395c24ef0217b238/comfy_extras/nodes_hooks.py#L86-L116)
- [Типы metadata и порядок обработки](https://github.com/Comfy-Org/ComfyUI/blob/c2bcbecd82ec5ae66594340b395c24ef0217b238/comfy/hooks.py#L672-L756)
- [Official workflow templates JSON 0.1.42](https://pypi.org/project/comfyui-workflow-templates-json/0.1.42/)
- [Pinned embedded docs 0.5.9](https://pypi.org/project/comfyui-embedded-docs/0.5.9/)
