# ConditioningZeroOut: нулевые тензоры с сохранением структуры

## Назначение

`ConditioningZeroOut` заменяет числовые тензоры каждой записи conditioning нулями той же формы. Основной тензор обнуляется всегда; `pooled_output` и `conditioning_lyrics` — если такие metadata-поля присутствуют.

Нода сохраняет сам список и остальные служебные данные. Результат остаётся типом `CONDITIONING`, поэтому его можно подключить туда же, куда исходную запись.

## Место в графе

Частый официальный паттерн — ответвить conditioning от text encode, передать одну ветвь как positive, а вторую обнулить и подключить как negative. Так устроены image-, audio- и video-шаблоны из пакета 0.1.42.

`ConditioningZeroOut` отличается от пустой строки в `CLIPTextEncode`. Пустой текст всё равно токенизируется и кодируется архитектурой; ZeroOut сначала получает готовую форму conditioning, затем заменяет выбранные тензоры нулями.

## Входы

Единственный обязательный вход `conditioning` имеет тип `CONDITIONING`. Виджетов и числовых параметров нет.

Нода принимает список любой длины и обрабатывает каждую запись отдельно. Она не проверяет, предназначен ли результат для positive, negative, inpaint или другого downstream-входа.

## Выход

Выход содержит столько же записей, сколько вход. Для основного тензора используется `torch.zeros_like`, поэтому сохраняются форма, dtype и device. Тем же способом заменяются найденные `pooled_output` и `conditioning_lyrics`.

Словарь metadata предварительно копируется. Area, mask, strength, временной диапазон, control, hooks и неизвестные ноде ключи остаются на месте.

## Как работает

Метод проходит по списку, копирует словарь второй части записи и проверяет два специальных ключа. Затем формирует новую пару: нулевой основной тензор и обновлённый словарь.

Embedded docs 0.5.9 описывают только обнуление `pooled_output`. Закреплённый исходник дополнительно и безусловно обнуляет основной `t[0]`, а при наличии — `conditioning_lyrics`. Для понимания ноды это существенное расхождение.

## Параметры и настройка

Настраивать внутри ноды нечего. Важен источник формы: нулевой результат наследует размеры от конкретного text encoder или conditioning-ноды. Поэтому для совместимости обычно ответвляют conditioning, уже рассчитанное тем же encoder, который используется в основной ветви.

Не удаляйте локальные metadata автоматически. Если вход имел area или mask, нулевой тензор сохранит эти ограничения. Это может быть нужно для согласования областей, но может и скрыть ошибку в графе.

## Проверенный пример

В official workflow templates JSON 0.1.42 найдено 53 экземпляра `ConditioningZeroOut` в 47 файлах: 17 в корневых графах и 36 в подграфах. У всех `widgets_values: []`. В 28 случаях выход идёт в слот 2 `KSampler`, то есть в `negative`.

Шаблон `flux_schnell_full_text_to_image`, workflow `908d0bfb-e192-4627-9b57-147496e6e2dd`, содержит цепочку `CLIPTextEncodeFlux` № 41 → `ConditioningZeroOut` № 42 → `negative` у `KSampler` № 31. В `audio_ace_step1_5_xl_base`, workflow `88ac5dad-efd7-40bb-84fe-fbaefdee1fa9`, нода № 47 превращает выход `TextEncodeAceStepAudio1.5` № 94 в negative для `KSampler` № 3.

Есть и промежуточные случаи. В `flux_canny_model_example`, workflow `90469c7e-4751-418c-9bd5-e43b3745a118`, нода № 37 подаёт нулевой результат в negative-вход `InstructPixToPixConditioning` № 35. Рецепт каталога воспроизводит минимальную доказанную операцию; реальный model run для него не выполнялся.

## Частые ошибки

**ZeroOut считают отсутствующим conditioning.** На выходе остаётся полноценный список с нулевыми тензорами и metadata. Downstream-код по-прежнему видит запись.

**Нода подключена к positive вместо negative.** Тип порта не различает роли. Проследите конкретную связь до guider или sampler.

**Пустой prompt считают точным эквивалентом.** Закодированная пустая строка обычно не является тензором из одних нулей. Сравнивайте оба варианта на одной модели.

**Ожидают, что multiplier 0 даст тот же результат.** `ConditioningMultiply` не обнуляет `conditioning_lyrics` и другие произвольные тензорные metadata.

## Ограничения и производительность

Для каждого затронутого тензора `zeros_like` выделяет новый тензор того же размера. Операция проще text encoding, но не бесплатна при больших списках или крупных дополнительных полях.

Нулевое conditioning не отключает negative-ветвь вычислений и не гарантирует нейтральный визуальный результат для каждой архитектуры. Нода также не удаляет hooks, control или spatial metadata: их downstream-эффект нужно оценивать отдельно.

## Совместимость и источники

Материал описывает ComfyUI 0.32.0 на commit `c2bcbecd82ec5ae66594340b395c24ef0217b238`; runtime ID и python module — `ConditioningZeroOut` и `nodes`.

Полный scan wheel 0.1.42 охватил 512 JSON, включая `definitions.subgraphs`. Помимо 28 прямых KSampler negative-связей, найдены inpaint, ControlNet, CFGGuider, audio и video-соседи. Embedded docs 0.5.9 по пути `comfyui_embedded_docs/docs/ConditioningZeroOut/en.md` помечены как AI-generated и неполно перечисляют обнуляемые поля.

- [Реализация `ConditioningZeroOut`](https://github.com/Comfy-Org/ComfyUI/blob/c2bcbecd82ec5ae66594340b395c24ef0217b238/nodes.py#L272-L295)
- [Official workflow templates JSON 0.1.42](https://pypi.org/project/comfyui-workflow-templates-json/0.1.42/)
- [Pinned embedded docs 0.5.9](https://pypi.org/project/comfyui-embedded-docs/0.5.9/)
