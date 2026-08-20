# ConditioningTimestepsRange: три объекта диапазона sampling

## Назначение

`ConditioningTimestepsRange` создаёт три значения типа `TIMESTEPS_RANGE`: выбранный интервал, часть до него и часть после него. Каждое значение — tuple из двух чисел.

Нода не принимает и не меняет `CONDITIONING`. Она только готовит типизированные данные для нод-потребителей, например `ConditioningSetProperties`.

## Место в графе

Основной выход подключают к optional-порту `timesteps` у conditioning- или hook-ноды. `BEFORE_RANGE` и `AFTER_RANGE` позволяют строить соседние ветви с другими условиями или hooks.

`ConditioningSetTimestepRange` работает иначе: принимает готовое `CONDITIONING`, сразу записывает в него две границы и возвращает `CONDITIONING`. `ConditioningTimestepsRange` отделяет создание диапазона от его применения и может передать один объект нескольким совместимым потребителям.

## Входы

`start_percent` и `end_percent` — обязательные FLOAT от 0 до 1 с шагом 0,001. По умолчанию используются 0 и 1.

Runtime проверяет каждое число отдельно, но класс не проверяет условие `start_percent <= end_percent`. При обратном порядке нода всё равно возвращает tuple с заданными значениями.

## Выход

`TIMESTEPS_RANGE` равен `(start_percent, end_percent)`. `BEFORE_RANGE` равен `(0.0, start_percent)`. `AFTER_RANGE` равен `(end_percent, 1.0)`.

Все три порта имеют один runtime-тип `TIMESTEPS_RANGE`, но разные имена и значения. Они не являются списками conditioning, номерами кадров или готовыми sigma.

## Как работает

Метод `create_range` сразу возвращает три Python tuple и не обращается к модели. Когда `ConditioningSetProperties` получает один из них, helper записывает первый элемент как `start_percent`, второй — как `end_percent`.

Перед sampling ComfyUI преобразует эти проценты в model-specific sigma через `percent_to_sigma`. Поэтому tuple хранит нормализованные границы, а не конкретные шаги scheduler.

## Параметры и настройка

Для обычного непрерывного окна задавайте начало не больше конца. Например, 0,2 и 0,75 создают основной tuple `(0.2, 0.75)`, before `(0.0, 0.2)` и after `(0.75, 1.0)`.

При start 0 before-выход становится `(0.0, 0.0)`, а при end 1 after становится `(1.0, 1.0)`. Код не помечает такие tuple как пустые. Точное попадание дискретного sampling-step на границу зависит от scheduler и логики потребителя.

## Проверенный пример

Fragment «Диапазон 0,2–0,75 для conditioning» соединяет основной выход `ConditioningTimestepsRange` с портом `timesteps` у `ConditioningSetProperties`. Вторая нода получает внешний `CONDITIONING`; mask и hooks не подключены. Required-виджеты strength и area mode оставлены в значениях 1,0 и `default`, но без маски они не добавляют metadata.

Ни одного `ConditioningTimestepsRange` не найдено в 512 official workflow templates JSON 0.1.42, включая `definitions.subgraphs`. Fragment сверяет типы, имена выходов и tuple-семантику по runtime/source; model run не выполнялся.

## Частые ошибки

**Диапазон считают интервалом видеокадров.** Это нормализованная часть sampling-процесса. Она не задаёт temporal area видео.

**Выход подключают к порту CONDITIONING.** `TIMESTEPS_RANGE` — отдельный тип. Нужна нода-потребитель с совместимым входом.

**Ждут автоматической перестановки границ.** При start больше end класс не меняет числа и не выдаёт ошибку.

**Три выхода считают непересекающимися по определению.** Их числовые границы совпадают на start и end; фактическое включение граничного шага решает downstream-код.

## Ограничения и производительность

Нода создаёт три коротких tuple и практически не влияет на память или время. Вычислительная стоимость появляется у ветвей conditioning и hooks, которые используют эти диапазоны.

Тип и NodeId помечены experimental. Нода не знает scheduler, число steps или модель и не может показать, сколько реальных итераций попадёт в окно. Для очень короткого интервала диапазон может не захватить отдельный дискретный шаг.

## Совместимость и источники

Материал закреплён на ComfyUI 0.32.0, commit `c2bcbecd82ec5ae66594340b395c24ef0217b238`. Runtime ID — `ConditioningTimestepsRange`, python module — `comfy_extras.nodes_hooks`, `experimental: true`.

Embedded docs 0.5.9 по пути `comfyui_embedded_docs/docs/ConditioningTimestepsRange/en.md` верно перечисляют три tuple, но не отмечают отсутствие проверки порядка, граничные tuple нулевой длины и отличие от прямой ноды `ConditioningSetTimestepRange`.

- [Создание трёх `TIMESTEPS_RANGE`](https://github.com/Comfy-Org/ComfyUI/blob/c2bcbecd82ec5ae66594340b395c24ef0217b238/comfy_extras/nodes_hooks.py#L261-L281)
- [Запись tuple в metadata conditioning](https://github.com/Comfy-Org/ComfyUI/blob/c2bcbecd82ec5ae66594340b395c24ef0217b238/comfy/hooks.py#L713-L717)
- [Прямой `ConditioningSetTimestepRange`](https://github.com/Comfy-Org/ComfyUI/blob/c2bcbecd82ec5ae66594340b395c24ef0217b238/nodes.py#L297-L313)
- [Преобразование percent в model sigma](https://github.com/Comfy-Org/ComfyUI/blob/c2bcbecd82ec5ae66594340b395c24ef0217b238/comfy/samplers.py#L859-L883)
- [Official workflow templates JSON 0.1.42](https://pypi.org/project/comfyui-workflow-templates-json/0.1.42/)
- [Pinned embedded docs 0.5.9](https://pypi.org/project/comfyui-embedded-docs/0.5.9/)
