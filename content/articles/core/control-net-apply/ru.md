# ControlNetApply: устаревшее применение ControlNet к одному conditioning

## Что делает нода

`ControlNetApply` — старая backend-нода с одним входом `CONDITIONING`. Для каждого элемента списка она создаёт копию объекта `CONTROL_NET`, прикрепляет к ней изображение-подсказку и strength, затем сохраняет объект в metadata под ключом `control`. Если там уже был ControlNet, он становится предыдущим звеном цепочки.

Изображение приходит в формате `[B, H, W, C]` и перед записью переставляется в `[B, C, H, W]` через `movedim`. Сама нода не запускает ControlNet: вычисление произойдёт во время sampling, когда sampler прочитает metadata.

В ComfyUI 0.32.0 класс содержит `DEPRECATED = True`, а display name — `Apply ControlNet (DEPRECATED)`. Нода остаётся исполняемой для старых workflow, но новые графы не следует строить вокруг её ограниченной сигнатуры.

## Когда использовать и когда не использовать

Используйте её для открытия, диагностики и аккуратного воспроизведения legacy-графа. Если результат старого проекта меняется после обновления, сначала проверьте его в исходной топологии, а уже затем переносите на современную ноду.

Для нового workflow выбирайте `ControlNetApplyAdvanced`: у него есть отдельные positive и negative, диапазон `start_percent`–`end_percent` и опциональный `VAE`. При этом `ControlNetApplyAdvanced` не объявлен формальной заменой через Node Replacement API 0.32.0. Автоматического преобразования портов и виджетов нет, а поведение metadata отличается, поэтому перенос выполняется вручную.

Legacy-нода не подходит для ControlNet, которому нужен VAE: у неё нет входа `vae`, и `set_cond_hint` вызывается без него. Не применяйте её также ради препроцессинга. Canny, depth, pose или другой control image готовится отдельной нодой в формате, ожидаемом конкретной моделью.

## Короткий рецепт подключения

1. Оставьте `conditioning`, `control_net`, `image` и `strength` такими, какими они сохранены в старом графе.
2. Для контрольной проверки используйте прежние checkpoint, control model, preprocessor и seed.
3. Если `strength = 0`, ожидайте точный bypass: нода вернёт исходный список.
4. Для ручного переноса поставьте `ControlNetApplyAdvanced`, подключите исходные positive и negative, задайте тот же strength, `start_percent = 0`, `end_percent = 1`.
5. Подайте VAE, если новая ControlNet-модель его требует, и сравните результат с legacy-графом до удаления старой ноды.

Fragment «Воспроизвести legacy-подключение для проверки старого графа» содержит только `ControlNetApply` с `strength = 1` и внешними объектными входами. Это source-derived диагностический фрагмент: в официальных workflow 0.1.42 legacy-нода не встречается, полного workflow нет.

## Входы, выходы и параметры

`conditioning` принимает один `CONDITIONING`; `control_net` — `CONTROL_NET`; `image` — `IMAGE`. `strength` — `FLOAT` от `0` до `10`, default `1`, шаг интерфейса `0.01`. Выход один — `CONDITIONING`; нода не имеет negative-порта, диапазона по шагам и VAE.

При точном `strength == 0` метод сразу возвращает входной conditioning по идентичности. Для любого другого значения он проходит по всем элементам списка. Text tensor сохраняется, metadata-словарь копируется неглубоко, а `control_net.copy().set_cond_hint(...)` вызывается заново для каждого элемента.

Поскольку диапазон не передаётся, `ControlBase.set_cond_hint` использует default `(0.0, 1.0)`: контроль рассчитан на весь sampling. Поскольку VAE тоже не передаётся, ControlNet с latent format может сначала предупредить о его отсутствии, а затем потребовать современную apply-ноду с VAE-входом.

Если metadata уже содержит `control`, новый объект вызывает `set_previous_controlnet` с прежним. Так несколько legacy apply-нод образуют цепочку. При отсутствии ключа метод установки предыдущего звена вообще не вызывается, хотя стандартная копия обычно начинает с `None`.

Ключ `control_apply_to_uncond` устанавливается в `True`. На этапе подготовки sampler ищет такие записи в positive conditioning и переносит control в остальные наборы условий с совпадающей областью. Это старый способ распространить один ControlNet на unconditional/negative ветвь.

## Типовые связки

Legacy-топология обычно выглядела как `preprocessor image + ControlNetLoader + positive CONDITIONING → ControlNetApply → KSampler positive`. Отдельный negative conditioning также входил в sampler, а флаг `control_apply_to_uncond=True` обеспечивал распространение control из positive ветви.

Несколько ControlNet соединялись последовательно: выход первой `ControlNetApply` входил в `conditioning` второй. Каждая нода сохраняла прежний объект как `previous_controlnet`, поэтому во время sampling выполнялась цепочка control models.

Современная топология иная: `positive + negative + CONTROL_NET + IMAGE → ControlNetApplyAdvanced → KSampler`. Оба выхода подключаются к соответствующим портам sampler. Advanced ставит `control_apply_to_uncond=False`, потому что control уже записан в обе ветви явно.

Для Canny сначала готовится edge image, затем он поступает в apply-ноду. Для depth или pose нужен соответствующий detector. `LoadImage` без препроцессора допустим только для ControlNet, обученной на таком типе входа.

## Практический пример

Исчерпывающий просмотр 512 JSON-файлов официального пакета 0.1.42, включая все `definitions.subgraphs[*].nodes`, не нашёл ни одного `ControlNetApply`. Это согласуется с deprecated-статусом, но не доказывает, что старых пользовательских графов больше нет.

Для сравнения `ControlNetApplyAdvanced` встретился пять раз в пяти файлах: три раза в корневых графах и два — внутри subgraph. В SD3.5 Canny case используется `strength = 0.66`, в depth — `0.7`, в остальных — `1`; у всех диапазон `[0, 1]`. Оба выхода идут в positive и negative порты `KSampler`.

Exact-source проба без весов передала legacy-ноде два элемента conditioning и изображение `[2, 5, 7, 3]`. Было создано две отдельные копии ControlNet, каждая получила view формы `[2, 3, 5, 7]`; первая сохранила прежний control, у второй метод `set_previous_controlnet` не вызывался. В обеих metadata появился флаг `True`.

Та же проба запустила Advanced с общим previous control в positive и negative. Advanced переиспользовал одну копию для этого предыдущего звена, передал диапазон `(0.1, 0.8)` и VAE, а флаг выставил в `False`. Это подтверждает несовпадающую внутреннюю семантику; probe не исполнял настоящую ControlNet-модель или sampler.

## Частые ошибки и способы проверки

**Встроенная справка показывает positive, negative, VAE и диапазон, которых нет на ноде.** Документы 0.5.9 для `ControlNetApply` фактически описывают интерфейс Advanced. Доверяйте `/object_info` установленной версии: у legacy только четыре входа.

**После замены на Advanced один из sampler-портов остался старым.** Подключите оба новых выхода — positive к positive, negative к negative. Одного выхода, который сам распространится через `control_apply_to_uncond=True`, у Advanced нет.

**ControlNet требует VAE.** Legacy-нода не умеет его принять. Используйте Advanced и подключите VAE, совместимый с основной моделью и ControlNet.

**Контроль действует весь sampling, хотя нужен только в начале.** Legacy всегда передаёт default `(0, 1)`. Диапазон можно задать только современной apply-нодой или другим специализированным узлом.

**Результат не соответствует control image.** Проверьте не только strength, но и preprocessor, разрешение, порядок каналов, тип модели ControlNet и основную generative model. Совпадение типа `CONTROL_NET` не проверяет обучающую задачу модели.

**Несколько применений стали медленными.** Каждая нода добавляет ещё одно звено ControlNet. Проследите цепочку `previous_controlnet` и временно проверяйте модели по одной.

**При strength 0 всё ещё ожидается подготовка control image.** Сама legacy-нода обходит работу и возвращает исходный conditioning, но upstream preprocessor может уже быть выполнен, если его выход нужен где-либо ещё.

## Производительность и внутреннее поведение

`movedim` обычно создаёт представление тех же данных без копирования, что и подтвердила tensor-проба по общему storage. Нода сохраняет этот BCHW-view как `cond_hint_original` внутри каждой копии control object. Реальное масштабирование подсказки и forward ControlNet происходят позже.

При ненулевом strength вычислительная стоимость ControlNet почти не зависит от величины числа: `0.1` не означает десятикратного ускорения. Быстрый путь есть только для точного нуля. Несколько chained controls добавляют отдельный model forward на соответствующих шагах.

Legacy-класс делает копию wrapper для каждого элемента conditioning, даже если их previous control одинаков. Advanced кэширует копии по previous control и способен разделить один wrapper между соответствующими positive/negative элементами. Веса модели при этом управляются внутренними объектами ComfyUI; число wrapper-копий не следует путать с полной загрузкой весов для каждого элемента.

Metadata копируется неглубоко: прежние вложенные значения остаются общими, новые `control` и `control_apply_to_uncond` записываются в отдельный словарь. Исходный conditioning не меняется при ненулевой ветке.

## Совместимость, изменения и устаревание

Статья проверена для ComfyUI `0.32.0`, frontend `1.48.7`, модуль `nodes`. Runtime fingerprint: `sha256:a49e7bf116a33c0e9e68cf79730ab39e24656431d92b90bb99fecd4aa258285e`.

Runtime помечает ноду deprecated. В снимке `/api/node_replacements` для 0.32.0 ключа `ControlNetApply` нет, а built-in registry регистрирует для ControlNet только замену `T2IAdapterLoader → ControlNetLoader`. Поэтому `replacedBy` в манифесте статьи оставлен `null`.

`ControlNetApplyAdvanced` — рекомендуемая для новых графов близкая нода, но не формальная и не полностью эквивалентная замена. Она принимает две ветви, передаёт диапазон и VAE, переиспользует копии по previous control и ставит другой флаг распространения. Миграцию надо проверять на сохранённом seed и тех же моделях.

## Связанные ноды и источники

`KSampler` потребляет positive и negative conditioning после подготовки control metadata. `ConditioningZeroOut` используется в официальных SD3.5 Advanced workflow для negative ветви. `LoadImage` или preprocessor дают control hint, но не определяют его смысл без согласованной ControlNet-модели.

- [Legacy и Advanced реализации](https://github.com/Comfy-Org/ComfyUI/blob/c2bcbecd82ec5ae66594340b395c24ef0217b238/nodes.py#L897-L976)
- [Default диапазон и VAE-поведение `set_cond_hint`](https://github.com/Comfy-Org/ComfyUI/blob/c2bcbecd82ec5ae66594340b395c24ef0217b238/comfy/controlnet.py#L82-L124)
- [Built-in Node Replacement registry без записи для legacy apply](https://github.com/Comfy-Org/ComfyUI/blob/c2bcbecd82ec5ae66594340b395c24ef0217b238/comfy_extras/nodes_replacements.py#L6-L93)
- [Встроенная документация 0.5.9 с несовпадающей таблицей портов](https://github.com/Comfy-Org/embedded-docs/blob/1d258cf6e374d60d138a2bfcd273c7e11f750ef9/comfyui_embedded_docs/docs/ControlnetApply/en.md)
- [Официальные workflow-шаблоны 0.1.42](https://pypi.org/project/comfyui-workflow-templates-json/0.1.42/)
