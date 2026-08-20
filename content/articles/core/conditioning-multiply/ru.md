# ConditioningMultiply: масштабирование embedding

## Назначение

`ConditioningMultiply` умножает числовое представление conditioning на один коэффициент. Для каждой записи меняются основной тензор и, если он есть, `pooled_output`. Число записей, их форма и остальные metadata сохраняются.

Это операция над embedding, а не настройка `strength` для sampler. Она изменяет данные ещё до того, как downstream-код применит область, маску или временной диапазон.

## Место в графе

Ноду ставят после `CLIPTextEncode` либо другого источника `CONDITIONING` и до сэмплера или последующих преобразований. Если список содержит несколько записей, одинаковый multiplier применяется к каждой.

`ConditioningAverage` смешивает два conditioning и подгоняет их токенную длину. `ConditioningSetAreaStrength` не трогает embedding, а только записывает sampler-множитель в metadata. `ConditioningMultiply` имеет один вход и масштабирует сам тензор.

## Входы

`conditioning` — список записей `CONDITIONING`. В обычной записи первый элемент — основной тензор, второй — словарь metadata.

`multiplier` — число от −100,00 до 100,00 с шагом 0,01; значение по умолчанию равно 1,00. Ноль обнуляет основной тензор и pooled output, отрицательное число меняет знак, а модуль больше единицы увеличивает абсолютные значения.

Runtime не ограничивает настройку безопасным для конкретной модели диапазоном. Границы виджета показывают только то, что принимает нода.

## Выход

На выходе остаётся `CONDITIONING` с тем же числом записей. Основной тензор каждой записи равен `input_tensor × multiplier`. Если в metadata был `pooled_output`, он заменяется на `pooled_output × multiplier`.

Другие ключи копируются без изменения. В частности, `strength`, `mask_strength`, `area`, `mask`, hooks и временные границы не умножаются.

## Как работает

Метод проходит по входному списку. Для каждой записи он создаёт выражение `t[0] * multiplier`, отдельно масштабирует `pooled_output`, если ключ существует, и передаёт результат в helper копирования conditioning.

Реализация не перебирает произвольные тензоры внутри metadata. Например, поле `conditioning_lyrics`, которое отдельно обрабатывает `ConditioningZeroOut`, здесь не масштабируется. Поэтому `multiplier: 0` и `ConditioningZeroOut` не полностью эквивалентны для всех видов conditioning.

## Параметры и настройка

Значение 1,00 полезно как контроль: оно создаёт новые тензоры с теми же числовыми значениями. Для осторожного ослабления начните с 0,5 и сравнивайте при одинаковых model, seed, scheduler и остальных conditioning.

Отрицательные коэффициенты разрешены контрактом, но не означают «negative prompt». Positive и negative определяются портом downstream-сэмплера. Умножение embedding на −1 — другая числовая операция, и её результат зависит от архитектуры.

## Проверенный пример

Fragment-only рецепт «Масштабирование CONDITIONING на 0,5» принимает внешний `CONDITIONING` и задаёт `multiplier: 0.5`. Тип порта, диапазон и имя настройки сверены с полным `/object_info` ComfyUI 0.32.0; тензорная семантика — с `nodes.py`.

В official workflow templates JSON 0.1.42 проверены все 512 файлов, включая `definitions.subgraphs`. `ConditioningMultiply` не найден, поэтому у закреплённого пакета нет официальных widget values или topology neighbors. Fragment не исполнялся с реальным embedding.

## Частые ошибки

**Multiplier принимают за CFG или силу area.** Нода меняет тензор conditioning. CFG принадлежит guider или sampler, а `strength` — отдельному metadata-механизму.

**Отрицательный multiplier считают способом подключить negative.** Роль conditioning задаёт вход downstream-ноды. Знак embedding не переключает порт.

**Значение 0 считают полной заменой ZeroOut.** Основной тензор и pooled output обнулятся, но другие тензорные metadata, включая возможный `conditioning_lyrics`, останутся прежними.

**Большой коэффициент трактуют как линейное усиление смысла prompt.** Линейно меняются числа, но воспринимаемый результат модели не обязан следовать той же шкале.

## Ограничения и производительность

Нода выделяет новый основной тензор для каждой записи и, при наличии, новый pooled output. Объём операции пропорционален числу элементов этих тензоров. Она не запускает text encoder или diffusion-модель, но может заметно копировать данные в большом списке.

Downstream sampling всё равно выполняется. Нулевой embedding не удаляет запись и не служит сигналом пропустить модельный проход. Совместимость экстремальных и отрицательных значений нода не проверяет.

## Совместимость и источники

Статья закреплена на ComfyUI 0.32.0, commit `c2bcbecd82ec5ae66594340b395c24ef0217b238`. Runtime ID — `ConditioningMultiply`, python module — `nodes`, диапазон multiplier — от −100 до 100.

Embedded docs 0.5.9 по пути `comfyui_embedded_docs/docs/ConditioningMultiply/en.md` помечены как AI-generated. Они верно называют основной тензор и pooled output, но не проводят границу с metadata-`strength` и не отмечают другие тензорные поля. Эти ограничения проверены по реализации.

- [Реализация `ConditioningMultiply`](https://github.com/Comfy-Org/ComfyUI/blob/c2bcbecd82ec5ae66594340b395c24ef0217b238/nodes.py#L162-L183)
- [Копирование metadata conditioning](https://github.com/Comfy-Org/ComfyUI/blob/c2bcbecd82ec5ae66594340b395c24ef0217b238/node_helpers.py#L9-L23)
- [Official workflow templates JSON 0.1.42](https://pypi.org/project/comfyui-workflow-templates-json/0.1.42/)
- [Pinned embedded docs 0.5.9](https://pypi.org/project/comfyui-embedded-docs/0.5.9/)
