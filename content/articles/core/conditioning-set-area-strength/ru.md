# ConditioningSetAreaStrength: metadata-сила записи

## Назначение

`ConditioningSetAreaStrength` записывает каждой записи conditioning числовой metadata-ключ `strength`. Sampler позже использует его как общий пространственный множитель. Основной embedding и pooled output нода не меняет.

Несмотря на слово Area в названии, нода не создаёт прямоугольник. Если metadata `area` отсутствует, strength действует на всю доступную область записи.

## Место в графе

Ноду можно поставить после `ConditioningSetArea`, `ConditioningSetAreaPercentage` или `ConditioningSetMask`, чтобы заменить общий `strength` без повторной настройки геометрии. Она также принимает обычное conditioning без area.

`ConditioningMultiply` масштабирует embedding заранее. Здесь тензор остаётся прежним, а вес учитывается при пространственном смешивании результатов sampler. Эти операции могут стоять в одной цепочке и тогда действуют на разных уровнях.

## Входы

`conditioning` — список `CONDITIONING`. Одинаковый strength записывается в каждую его запись.

`strength` — число от 0,00 до 10,00 с шагом 0,01; значение по умолчанию равно 1,00. Отрицательные значения runtime не допускает.

Нода не требует входа `area` и не проверяет наличие ключа area в metadata.

## Выход

На выходе остаётся тот же тип и то же число записей. Helper сохраняет ссылку на основной тензор, копирует словарь metadata и устанавливает `strength` в новое значение.

Если ключ уже был задан `ConditioningSetArea` или другой нодой, он заменяется. `mask_strength` — отдельный ключ и не меняется.

## Как работает

Метод вызывает `conditioning_set_values(conditioning, {"strength": strength})`. Никакой тензорной арифметики в классе нет.

В sampler `get_area_and_mult` начинает с strength 1, читает metadata-`strength`, затем формирует множитель `mask × strength`. Если у записи есть маска, сама маска уже учитывает `mask_strength`. В результате общий вес содержит оба коэффициента.

## Параметры и настройка

Значение 1,00 оставляет единичный общий множитель. 0,50 уменьшает его вдвое, а 0,00 создаёт нулевую карту вклада. Нулевое значение не удаляет запись и само по себе не гарантирует, что downstream-код пропустит модельный расчёт.

Если нужно изменить только силу маски, используйте `strength` внутри `ConditioningSetMask`: она записывает `mask_strength`. Если нужно изменить embedding независимо от spatial blending, применяйте `ConditioningMultiply`.

## Проверенный пример

Fragment-only рецепт «Сила conditioning 0,6» принимает внешний `CONDITIONING` и задаёт `strength: 0.6`. Runtime-тип, диапазон и имя поля сверены с полным `/object_info`; чтение metadata — с `comfy/samplers.py`.

Exhaustive-поиск по 512 official workflow templates JSON 0.1.42, включая все подграфы, не нашёл `ConditioningSetAreaStrength`. Поэтому у закреплённого пакета нет реальных widget values или topology neighbors. Fragment не проходил sampling-run.

## Частые ошибки

**От ноды ждут создания area.** Она записывает только `strength`. Прямоугольник задают `ConditioningSetArea` или percentage-вариант.

**Strength принимают за изменение embedding.** Тензор остаётся тем же. Число становится metadata-множителем sampler.

**Путают strength и mask_strength.** При наличии маски оба значения участвуют в произведении. Изменение одного не перезаписывает другое.

**Strength 0 используют как способ ускорения.** Запись остаётся в списке; закреплённый код не отбрасывает её только по нулевому `strength`.

## Ограничения и производительность

Сама нода копирует небольшие словари и не выделяет новые embedding. Это дешёвая операция по сравнению с text encoding и sampling.

Число выше единицы усиливает карту вклада, но визуальный эффект не обязан быть линейным. При перекрытии нескольких областей sampler нормализует и сочетает их по своим правилам; одна настройка strength не описывает весь итог.

## Совместимость и источники

Статья закреплена на ComfyUI 0.32.0 и commit `c2bcbecd82ec5ae66594340b395c24ef0217b238`. Runtime ID — `ConditioningSetAreaStrength`, python module — `nodes`, диапазон — 0–10.

Embedded docs 0.5.9 по пути `comfyui_embedded_docs/docs/ConditioningSetAreaStrength/en.md` помечены как AI-generated. Они называют параметр «интенсивностью», но не сообщают, что это metadata sampler, что area необязательна и что mask strength хранится отдельно.

- [Реализация `ConditioningSetAreaStrength`](https://github.com/Comfy-Org/ComfyUI/blob/c2bcbecd82ec5ae66594340b395c24ef0217b238/nodes.py#L229-L242)
- [Копирование metadata conditioning](https://github.com/Comfy-Org/ComfyUI/blob/c2bcbecd82ec5ae66594340b395c24ef0217b238/node_helpers.py#L9-L23)
- [Чтение strength и формирование множителя](https://github.com/Comfy-Org/ComfyUI/blob/c2bcbecd82ec5ae66594340b395c24ef0217b238/comfy/samplers.py#L33-L80)
- [Official workflow templates JSON 0.1.42](https://pypi.org/project/comfyui-workflow-templates-json/0.1.42/)
- [Pinned embedded docs 0.5.9](https://pypi.org/project/comfyui-embedded-docs/0.5.9/)
