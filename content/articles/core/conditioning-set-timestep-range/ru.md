# ConditioningSetTimestepRange: диапазон действия по denoising

## Назначение

`ConditioningSetTimestepRange` ограничивает запись `CONDITIONING` частью нормализованного denoising-диапазона. Нода сохраняет `start_percent` и `end_percent`; перед sampling эти доли переводятся в sigma через активную модель.

Поля не являются секундами и не задают номера дискретных шагов напрямую. Они описывают положение от 0 до 1 в модели sampling.

## Место в графе

Ноду ставят после источника conditioning и до `ConditioningCombine` либо входа сэмплера. Чтобы один prompt работал в начале, а другой позже, каждую ветвь ограничивают своим диапазоном и только затем объединяют списки.

Пространственные ноды `ConditioningSetMask` и `ConditioningSetArea` отвечают на вопрос «где», а `ConditioningSetTimestepRange` — «на какой части denoising». Их metadata можно сочетать в одной записи.

## Входы

`conditioning` — список `CONDITIONING`. Одинаковые границы записываются во все его элементы.

`start` — начало нормализованного диапазона от 0,000 до 1,000, по умолчанию 0,000. `end` — конец с тем же диапазоном и шагом 0,001, по умолчанию 1,000.

Runtime задаёт пределы каждого виджета отдельно, но класс не проверяет, что `start ≤ end`. Для рабочего интервала задавайте начало меньше конца.

## Выход

Выход имеет тип `CONDITIONING` и прежнее число записей. Helper сохраняет embedding, копирует каждый словарь metadata и записывает два ключа: `start_percent` и `end_percent`.

Повторный вызов `ConditioningSetTimestepRange` не пересекает новый диапазон со старым: он заменяет оба ключа. Маски, area, strength и прочие metadata остаются без изменения.

## Как работает

Перед sampling функция `calculate_start_end_timesteps` вызывает `model.model_sampling.percent_to_sigma` отдельно для начала и конца. Полученные значения сохраняются как `timestep_start` и `timestep_end`. Во время обработки запись пропускается, если текущая sigma находится вне этих границ.

Если conditioning уже содержит `clip_start_percent` и `clip_end_percent` от CLIP schedule, sampler берёт пересечение: максимум начал и минимум концов. Это downstream-правило не реализовано самой нодой, но влияет на фактическое окно действия.

## Параметры и настройка

`start: 0.0`, `end: 1.0` оставляет запись доступной на полном нормализованном диапазоне. Для первой половины задайте `0.0–0.5`, для второй — `0.5–1.0`. Это половины по percent-шкале, а не обещание ровно половины UI-шагов.

Разные scheduler и model sampling по-разному связывают percent, sigma и дискретный список шагов. Для сравнения закрепляйте модель, scheduler, число steps и seed. Не переносите найденную границу как точный номер шага в другой граф.

## Проверенный пример

Fragment-only рецепт «Conditioning в первой половине нормализованного denoising» принимает внешний `CONDITIONING` и задаёт `start: 0.0`, `end: 0.5`. Контракт портов и шаг виджета сверены с полным `/object_info`; percent-to-sigma — с sampler ComfyUI 0.32.0.

Все 512 official workflow templates JSON 0.1.42, включая подграфы, проверены на runtime ID. `ConditioningSetTimestepRange` не найден, поэтому официального сочетания widget values и topology neighbors нет. Fragment не проходил реальный denoising-run.

## Частые ошибки

**Start и end принимают за номера steps.** Значение 0,5 не означает буквально шаг 10 из 20. Оно переводится в sigma функцией активной модели, а sampler использует собственный список sigma.

**Start больше end.** Класс принимает такую пару и молча записывает её. Получается перевёрнутое или пустое окно; нода не вызывает helper, который предупреждает о неправильном порядке.

**Две временные ветви соединены последовательно.** Второй `ConditioningSetTimestepRange` заменит диапазон первого. Для двух окон создайте две записи и объедините их списки.

**Ожидают плавного перехода.** Нода задаёт границы доступности записи, а не кривую интерполяции силы. Для плавного изменения нужен другой механизм.

## Ограничения и производительность

Запись двух чисел почти ничего не стоит. Вне диапазона sampler пропускает конкретную запись conditioning, но все sampling steps и основная работа модели не исчезают автоматически. Поэтому нода не является общим способом ускорить workflow.

Точность виджета 0,001 выше, чем обязательно достижимая точность дискретного расписания: несколько близких значений могут попасть между теми же соседними sigma. При `start == end` полезного интервала обычно не остаётся; поведение на точной границе зависит от sampled sigma.

## Совместимость и источники

Статья закреплена на ComfyUI 0.32.0 и commit `c2bcbecd82ec5ae66594340b395c24ef0217b238`. Runtime ID и python module — `ConditioningSetTimestepRange` и `nodes`; входы start/end ограничены диапазоном 0–1.

В wheel embedded docs 0.5.9 каталог назван `comfyui_embedded_docs/docs/ConditioningSettimestepRange/en.md`: буква `t` в `timestep` строчная, поэтому exact-ID discovery не находит документ для `ConditioningSetTimestepRange`. Файл помечен как AI-generated и не объясняет percent-to-sigma, перезапись диапазона или отсутствие проверки порядка.

- [Реализация `ConditioningSetTimestepRange`](https://github.com/Comfy-Org/ComfyUI/blob/c2bcbecd82ec5ae66594340b395c24ef0217b238/nodes.py#L297-L311)
- [Копирование metadata conditioning](https://github.com/Comfy-Org/ComfyUI/blob/c2bcbecd82ec5ae66594340b395c24ef0217b238/node_helpers.py#L9-L23)
- [Перевод percent в sigma и пересечение с CLIP schedule](https://github.com/Comfy-Org/ComfyUI/blob/c2bcbecd82ec5ae66594340b395c24ef0217b238/comfy/samplers.py#L859-L882)
- [Пропуск conditioning вне sigma-границ](https://github.com/Comfy-Org/ComfyUI/blob/c2bcbecd82ec5ae66594340b395c24ef0217b238/comfy/samplers.py#L33-L45)
- [Official workflow templates JSON 0.1.42](https://pypi.org/project/comfyui-workflow-templates-json/0.1.42/)
- [Pinned embedded docs 0.5.9](https://pypi.org/project/comfyui-embedded-docs/0.5.9/)
