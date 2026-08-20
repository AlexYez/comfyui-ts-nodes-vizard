# ConditioningSetPropertiesAndCombine: свойства новой ветви и объединение

## Назначение

`ConditioningSetPropertiesAndCombine` обрабатывает список `cond_NEW`: добавляет optional hooks, mask и диапазон sampling. Затем нода ставит его записи после исходного списка `cond`.

Это списочное объединение, а не перенос свойств на базовую ветвь и не смешивание embedding. Runtime помечает ноду как experimental.

## Место в графе

В `cond` подают уже готовую основную ветвь, а в `cond_NEW` — дополнительное условие, которое нужно ограничить маской, hook-группой или диапазоном времени. Выход направляют на соответствующий conditioning-вход sampler или guider.

Обычный `ConditioningCombine` только соединяет два списка. `ConditioningSetPropertiesAndCombine` перед соединением меняет metadata второй ветви. `ConditioningSetProperties` выполняет ту же обработку `cond_NEW`, но не добавляет `cond`.

## Входы

`cond` и `cond_NEW` — обязательные значения `CONDITIONING`. `strength` имеет диапазон 0–10 и шаг 0,01. `set_cond_area` принимает `default` либо `mask bounds`.

Optional-входы: `mask: MASK`, `hooks: HOOKS`, `timesteps: TIMESTEPS_RANGE`. Strength становится `mask_strength` только при подключённой маске. Area mode тоже не используется без `mask`.

## Выход

Выход содержит сначала все записи `cond`, затем все записи обработанного `cond_NEW`. Длина равна сумме длин обоих списков; нода не сопоставляет записи по индексам и не усредняет их тензоры.

Metadata и embedding базового `cond` helper не меняет. У новой ветви основные тензоры сохраняются, а словари копируются при добавлении подключённых свойств.

## Как работает

Для `cond_NEW` helper по очереди добавляет hooks, маску и timestep-границы. Hooks записываются как `HookGroup` и объединяются с уже существующей группой. Маска создаёт ключи `mask`, `mask_strength` и `set_area_to_bounds`; tuple времени создаёт `start_percent` и `end_percent`.

После этого `combine_conditioning([cond, processed_new])` последовательно расширяет новый список. Никакие свойства `processed_new` не переносятся в записи `cond`.

## Параметры и настройка

`mask bounds` записывает boolean `set_area_to_bounds: true`; `default` записывает `false`. В обоих режимах mask tensor остаётся привязан к новой ветви. Strength не является общим весом всего результата.

Если `cond_NEW` уже содержит hooks, подключённая группа добавляется к ним через clone-and-combine. Если диапазон времени уже задан, новый `TIMESTEPS_RANGE` перезаписывает `start_percent` и `end_percent` только в новой ветви.

## Проверенный пример

Fragment «Основная и масочная conditioning-ветви» принимает внешние `cond`, `cond_NEW` и `MASK`. Для новой ветви установлены `strength: 0.65` и `set_cond_area: mask bounds`; hooks и timesteps не подключены. Выход сохраняет основную ветвь первой и добавляет после неё масочную.

Exhaustive scan 512 official workflow templates JSON 0.1.42, включая подграфы, не нашёл `ConditioningSetPropertiesAndCombine`. Значения fragment выбраны для проверки runtime-диапазонов и helper-семантики, а не перенесены из официального workflow. Sampling не выполнялся.

## Частые ошибки

**Ожидают, что свойства cond_NEW изменят cond.** Helper передаёт базовый список прямо в результат. Маска, hooks и время применяются только ко второй ветви.

**Combine понимают как усреднение.** Нода соединяет списки. Sampler позже обрабатывает обе записи по собственным правилам.

**Strength принимают за вес всего объединения.** Это `mask_strength` новой ветви и только при наличии mask.

**Порядок входов считают неважным.** `cond` идёт первым и остаётся нетронутым; `cond_NEW` обрабатывается и добавляется вторым.

## Ограничения и производительность

Сама нода копирует metadata новой ветви и создаёт общий список. Тензоры embedding не смешиваются. Если optional-входы отсутствуют, результат близок к обычному `cond + cond_NEW` с сохранёнными ссылками на записи.

Дополнительные записи могут увеличить число conditioning-вычислений в sampler. Разные hooks способны разделить их на отдельные группы. Перекрывающиеся маски и интервалы могут взаимодействовать нелинейно, поэтому fragment требует реального model run перед публикацией как готового preset.

## Совместимость и источники

Статья описывает ComfyUI 0.32.0 на commit `c2bcbecd82ec5ae66594340b395c24ef0217b238`. Runtime ID — `ConditioningSetPropertiesAndCombine`, python module — `comfy_extras.nodes_hooks`, флаг — experimental.

Embedded docs 0.5.9 по пути `comfyui_embedded_docs/docs/ConditioningSetPropertiesAndCombine/en.md` говорят о применении свойств новой conditioning к существующей. Реализация точнее: она обрабатывает только `cond_NEW`, а затем соединяет списки в порядке `cond + cond_NEW`.

- [Класс `ConditioningSetPropertiesAndCombine`](https://github.com/Comfy-Org/ComfyUI/blob/c2bcbecd82ec5ae66594340b395c24ef0217b238/comfy_extras/nodes_hooks.py#L117-L147)
- [Обработка свойств и порядок объединения](https://github.com/Comfy-Org/ComfyUI/blob/c2bcbecd82ec5ae66594340b395c24ef0217b238/comfy/hooks.py#L672-L773)
- [Official workflow templates JSON 0.1.42](https://pypi.org/project/comfyui-workflow-templates-json/0.1.42/)
- [Pinned embedded docs 0.5.9](https://pypi.org/project/comfyui-embedded-docs/0.5.9/)
