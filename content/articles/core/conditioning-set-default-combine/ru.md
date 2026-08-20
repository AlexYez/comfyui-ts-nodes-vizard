# ConditioningSetDefaultCombine: fallback для незаполненной области

## Назначение

`ConditioningSetDefaultCombine` добавляет к обычному conditioning список fallback-записей. Каждая запись второго входа получает metadata `default: true`. Sampler применяет default только там, где после обычных условий остаётся положительный пространственный множитель.

Нода помечена в runtime как experimental. Её поведение нельзя сводить к обычному объединению списков: ключ `default` меняет дальнейшую обработку sampler.

## Место в графе

В `cond` подают обычные условия, например региональные записи с mask или area. В `cond_DEFAULT` — базовое conditioning для остатка кадра. Выход направляют на одну сторону sampler или guider.

`ConditioningCombine` просто ставит записи второго списка после первого, и все они обрабатываются как обычные. `ConditioningSetDefaultCombine` тоже объединяет списки, но предварительно помечает второй как fallback. Если `cond` уже покрывает весь latent с единичным множителем, остаток равен нулю и default не добавляется в расчёт.

## Входы

`cond` — обязательный список обычных `CONDITIONING`. Нода не меняет его записи.

`cond_DEFAULT` — обязательный fallback-список. Его словари копируются, после чего в каждый записывается `default: true`.

`hooks` — необязательный вход типа `HOOKS`. Если он подключён, hooks добавляются только к default-записям. При уже существующих hooks helper объединяет группы через clone-and-combine, а не заменяет их.

## Выход

Выходной список имеет длину `len(cond) + len(cond_DEFAULT)`. Сначала идут исходные записи `cond`, затем копии `cond_DEFAULT` с флагом default и, при наличии, добавленными hooks.

Embedding обоих входов нода не смешивает и не усредняет. Обычные записи сохраняют свои metadata. Если в `cond` уже были записи с ключом `default`, они тоже останутся default для sampler.

## Как работает

Класс передаёт одноэлементные наборы списков в `set_default_conds_and_combine`. Helper применяет hooks к `cond_DEFAULT`, записывает `default: true`, затем выполняет обычное списочное объединение `cond + processed_default`.

Sampler отделяет default-записи от обычных. Он создаёт карту из единиц, вычитает из неё множители всех обычных условий и применяет ReLU. Если карта стала нулевой, default не запускается. Если остался положительный участок, default-запись получает эту остаточную карту вместо своего обычного множителя.

## Параметры и настройка

У ноды нет виджетов. Основная настройка находится в предыдущих нодах: mask, area, strength и временные диапазоны обычного `cond` определяют, какой остаток получит default.

Для понятного графа используйте глобальное `cond_DEFAULT` без собственной area или mask, пока не проверите более сложную схему. В закреплённом sampler рассчитанный multiplier default-записи заменяется остаточной картой, поэтому её обычные `strength` и `mask_strength` не являются итоговым весом fallback.

Optional hooks нужны, когда fallback должен выполняться с отдельными hook-настройками. Они не применяются к первому входу.

## Проверенный пример

Fragment-only рецепт «Основное и default conditioning без hooks» принимает два внешних `CONDITIONING` и подключает их к `cond` и `cond_DEFAULT`. Optional `HOOKS` намеренно оставлен неподключённым. Типы, optional-статус, experimental-флаг и python module сверены с полным `/object_info`.

Во всех 512 official workflow templates JSON 0.1.42, включая `definitions.subgraphs`, runtime ID `ConditioningSetDefaultCombine` отсутствует. Поэтому пример подтверждает только source/runtime-контракт и не выдаётся за официальный fallback workflow. Sampling не выполнялся.

## Частые ошибки

**Ноду принимают за переименованный Combine.** Второй список получает ключ `default`, а sampler рассчитывает для него остаточную карту. У обычного Combine этого шага нет.

**Ожидают, что default всегда влияет вместе с cond.** При полном покрытии обычными условиями остаток равен нулю, и fallback не добавляется в модельный расчёт.

**Hooks подключают ради изменения cond.** Optional hooks применяются только к `cond_DEFAULT`. Первый список helper не меняет.

**Fallback трактуют как проверку «неполного» объекта данных.** Sampler не ищет отсутствующие поля. Он заполняет остаток пространственного multiplier после обычных записей.

## Ограничения и производительность

На уровне ноды создаются копии metadata default-записей и новый список. Основная дополнительная работа происходит в sampler: для каждой стороны conditioning создаётся карта размера latent, из неё вычитаются обычные множители, затем выполняется ReLU.

Default с ненулевым остатком может потребовать отдельный модельный расчёт. Разные hooks также разделяют группы выполнения. При полном обычном покрытии sampler пропускает default-запись. Поскольку API помечен experimental, его контракт требует повторной сверки при обновлении ComfyUI.

## Совместимость и источники

Материал закреплён на ComfyUI 0.32.0 и commit `c2bcbecd82ec5ae66594340b395c24ef0217b238`. Runtime ID — `ConditioningSetDefaultCombine`, а реализующий класс называется `ConditioningSetDefaultAndCombine`; python module — `comfy_extras.nodes_hooks`.

Embedded docs 0.5.9 хранятся по пути `comfyui_embedded_docs/docs/ConditioningSetDefaultAndCombine/en.md`, поэтому exact runtime-ID discovery их не находит. Документ помечен как AI-generated и называет fallback для «неполного» primary conditioning, но не раскрывает остаточную карту, ReLU и условный пропуск default.

- [Класс и runtime NodeId `ConditioningSetDefaultCombine`](https://github.com/Comfy-Org/ComfyUI/blob/c2bcbecd82ec5ae66594340b395c24ef0217b238/comfy_extras/nodes_hooks.py#L202-L226)
- [Hooks, default-флаг и объединение списков](https://github.com/Comfy-Org/ComfyUI/blob/c2bcbecd82ec5ae66594340b395c24ef0217b238/comfy/hooks.py#L692-L711)
- [Helper default conditioning](https://github.com/Comfy-Org/ComfyUI/blob/c2bcbecd82ec5ae66594340b395c24ef0217b238/comfy/hooks.py#L773-L786)
- [Расчёт остаточного множителя](https://github.com/Comfy-Org/ComfyUI/blob/c2bcbecd82ec5ae66594340b395c24ef0217b238/comfy/samplers.py#L165-L206)
- [Отделение default-записей от обычных](https://github.com/Comfy-Org/ComfyUI/blob/c2bcbecd82ec5ae66594340b395c24ef0217b238/comfy/samplers.py#L231-L256)
- [Official workflow templates JSON 0.1.42](https://pypi.org/project/comfyui-workflow-templates-json/0.1.42/)
- [Pinned embedded docs 0.5.9](https://pypi.org/project/comfyui-embedded-docs/0.5.9/)
