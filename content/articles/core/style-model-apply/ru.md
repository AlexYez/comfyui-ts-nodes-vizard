# StyleModelApply: добавить style-токены в conditioning

## Что делает нода

`StyleModelApply` берёт визуальные признаки из `CLIP_VISION_OUTPUT`, пропускает `last_hidden_state` через `STYLE_MODEL` и дописывает полученные style-токены в конец текстовых токенов каждого элемента `CONDITIONING`. Исходный текст не заменяется: выход содержит прежнюю последовательность, за которой идут новые токены референса.

Параметр `strength_type` выбирает два разных механизма. В режиме `multiply` значения style embedding умножаются на `strength`. В режиме `attn_bias` сами style-токены не масштабируются; число превращается в `log(strength)` и записывается в расширенную attention mask, если такая маска нужна. Это не два названия одной и той же операции.

Нода возвращает новый список conditioning. Tensor текста используется как источник для `torch.cat`, metadata-словарь каждого элемента копируется неглубоко. Вложенные объекты остаются общими, если нода не заменяет их отдельно.

## Когда использовать и когда не использовать

Используйте `StyleModelApply`, когда у вас есть согласованная тройка: визуальный энкодер, style model и generative model с подходящей шириной conditioning. Официальный пример Flux Redux соединяет SigLIP, `flux1-redux-dev.safetensors` и Flux conditioning. Старый StyleAdapter — другая архитектурная ветка; переносить его в Flux-граф только из-за совпадения типа `STYLE_MODEL` нельзя.

Нода подходит для одного или нескольких референсов. Несколько влияний добавляются последовательными экземплярами: выход первого идёт в `conditioning` второго. Это увеличивает число токенов, а не усредняет изображения автоматически.

Не используйте её как общий «фильтр стиля» для любого checkpoint. Если нет подходящего style model, обычный prompt, IP-Adapter-подобная custom node или архитектурный image-conditioning могут быть уместнее, но их семантика другая. `unCLIPConditioning` тоже работает с `CLIP_VISION_OUTPUT`, однако сохраняет ADM-условие в metadata и требует модель, которая его читает.

## Короткий рецепт подключения

1. Получите базовый `CONDITIONING` из совместимого текстового encode; в Flux-графе он может пройти через `FluxGuidance`.
2. Загрузите `STYLE_MODEL` через `StyleModelLoader`.
3. Закодируйте референс согласованным визуальным энкодером через `CLIPVisionEncode`.
4. Начните со `strength = 1` и `strength_type = multiply` — именно эта пара используется в официальном Flux Redux workflow.
5. Подайте выход дальше в guider или sampler. Для второго референса поставьте ещё одну `StyleModelApply` после первой.

Fragment «Добавить style-токены одного референса» начинается непосредственно с `StyleModelApply`: все три сложных объекта приходят через внешние входы. Он не содержит downloader, checkpoint names или полного workflow.

## Входы, выходы и параметры

`conditioning` принимает `CONDITIONING`; `style_model` — `STYLE_MODEL`; `clip_vision_output` — `CLIP_VISION_OUTPUT`. `strength` — `FLOAT` от `0` до `10`, default `1`, шаг интерфейса `0.001`. `strength_type` допускает только `multiply` и `attn_bias`. Выход — один `CONDITIONING`, не list-output.

`StyleModel.get_cond` передаёт в модель поле `last_hidden_state`. Результат имеет форму наподобие `[B_ref, N_style, D]`. Нода объединяет первые две оси через `flatten(0, 1)` и добавляет ось batch: получается `[1, B_ref × N_style, D]`. Таким образом, пакет референсов превращается в одну общую последовательность style-токенов.

Для `multiply` выполняется умножение всей этой последовательности. При `strength = 0` style-токены остаются в conditioning, но становятся нулевыми; это не быстрый возврат исходного объекта. При значении выше единицы увеличивается амплитуда embedding. Смысл масштаба зависит от style model, поэтому предел `10` — техническая граница виджета, а не рекомендуемое значение.

Для `attn_bias` при `strength = 1` и отсутствии прежней mask новая mask не создаётся. При других значениях используется `log(strength)`: диапазон `0 < strength < 1` даёт отрицательное смещение, `strength > 1` — положительное, `0` — `-inf`. Style embedding при этом остаётся немасштабированным.

Если metadata уже содержит `attention_mask`, нода расширяет её даже в режиме `multiply`. Размер старой reference-области берётся из `attention_mask_img_shape`, default `(1, 1)`. Boolean mask переводится в additive bias через логарифм: `True` становится `0`, `False` — `-inf`. Новая mask всегда создаётся как `float16`, затем переносится на устройство текстового tensor.

## Типовые связки

Официальная Flux Redux связка: `LoadImage → CLIPVisionEncode`, параллельно `CLIPVisionLoader` и `StyleModelLoader`, затем `FluxGuidance → StyleModelApply → BasicGuider`. Visual encoder и Redux model должны соответствовать друг другу по ожидаемой ширине признаков.

Для двух референсов используется цепочка `StyleModelApply → StyleModelApply`. Каждый экземпляр получает собственный `CLIP_VISION_OUTPUT`, но один и тот же `STYLE_MODEL`; итоговый conditioning содержит токены обоих изображений в порядке применения.

Если conditioning уже несёт spatial attention mask, `StyleModelApply` вставляет style-область между текстовой и reference-областью mask. Такие графы требуют особенно аккуратной проверки размеров: metadata должна соответствовать фактическому числу текстовых и image-reference токенов.

`CLIPTextEncode` или другой encoder должен выдавать ширину `D`, совместимую с выходом style model. Нода не проецирует style-токены к ширине текста: проекция должна быть частью загруженной `STYLE_MODEL`.

## Практический пример

Исчерпывающий просмотр 512 JSON-файлов пакета 0.1.42 нашёл два экземпляра `StyleModelApply`, оба в корневом графе `flux_redux_model_example`. Внутри subgraph таких нод нет. У обоих виджеты равны `[1, "multiply"]`.

Первый экземпляр получает conditioning от `FluxGuidance`, style model от `StyleModelLoader` и embedding первого изображения от `CLIPVisionEncode`. Его выход подаётся во второй экземпляр с embedding второго изображения. После этого объединённый conditioning идёт в `BasicGuider`. Это подтверждает реальную последовательную топологию, но не устанавливает универсальное «правильное» число референсов.

Exact-source tensor-проба без весов использовала текст `[1, 2, 4]` и style output `[1, 3, 4]`. В режиме `multiply` со значением `0.5` получился tensor `[1, 5, 4]`: первые два токена совпали с текстом, последние три стали равны `0.5`. При нуле форма осталась `[1, 5, 4]`, а добавленные токены обнулились.

Для `attn_bias = 0.25`, двух текстовых и двух style-токенов, без прежней mask, код создал mask `[1, 5, 5]`: пятая позиция появилась из default reference shape `(1, 1)`. Отдельная проба с text batch 2 и style batch 1 завершилась ошибкой `torch.cat`; не стоит рассчитывать на broadcasting этой оси.

## Частые ошибки и способы проверки

**`torch.cat` сообщает о несовместимых размерах.** Проверьте ширину последней оси текста и style output, затем batch. После `flatten` style-последовательность всегда имеет batch 1; conditioning с batch больше одного напрямую не расширяется.

**После `strength = 0` граф стал тяжелее, хотя стиль исчез.** В `multiply` нулевые токены всё равно вычисляются и добавляются. Если нужен настоящий no-op, обойдите ноду или отключите ветку на уровне графа.

**`attn_bias = 0` дал `-inf`.** Это предусмотрено реализацией: `torch.log(0)` используется как запрет внимания к вставленным токенам для определённых строк mask. Если downstream плохо обрабатывает бесконечности, не выбирайте ноль без проверки модели.

**Маска имеет неверную форму.** Сверьте `attention_mask_img_shape` и старую mask: код ожидает матрицу для `N_text + N_ref`. Несогласованные metadata приводят к ошибке присваивания при копировании четырёх областей.

**Два референса дают непредсказуемый результат.** Они добавляются последовательно, а не нормализуются как набор. Поменяйте порядок, проверьте каждый референс отдельно и уменьшите strength до объединения.

**Style model не загружается.** В 0.32.0 loader распознаёт два семейства по ключам checkpoint: `style_embedding` для StyleAdapter и `redux_down.weight` для Flux Redux. Другой state dict завершится ошибкой `invalid style model`.

## Производительность и внутреннее поведение

До добавления токенов выполняется forward style model по `last_hidden_state`. Для StyleAdapter это transformer над visual tokens и восемью обученными style tokens; для Flux Redux — две линейные проекции с SiLU. Затем для каждого элемента conditioning создаётся новый tensor через `torch.cat`.

Расход памяти растёт с числом референсов и их токенов. Особо дорогая ветка — расширение attention mask: её обе пространственные оси получают `N_style`, поэтому объём растёт квадратично от общей длины. Новая mask создаётся на CPU как `float16`, заполняется, затем переносится на устройство текста.

Один рассчитанный style tensor переиспользуется для всех элементов входного списка. Metadata копируется неглубоко; неизменённые вложенные значения остаются теми же объектами. При существующей mask создаётся новый tensor, поэтому исходная mask не переписывается на месте.

Пакет visual embeddings сначала сплющивается в последовательность. Это экономит отдельный проход по conditioning, но не сохраняет границу между изображениями как отдельную batch-ось. Большой batch напрямую увеличивает длину контекста.

## Совместимость, изменения и устаревание

Статья проверена для ComfyUI `0.32.0`, frontend `1.48.7`, модуль `nodes`. Runtime fingerprint: `sha256:bb7470a38daad2f08eb32839b624331a9523483a216d707a353300b99a25bcf6`.

Нода не отмечена как deprecated, experimental или API node; формальной замены в Node Replacement API нет. Search alias `style transfer` задан самим backend. Совместимость определяется не только сигнатурой: изменения формата attention mask, StyleModel wrapper или ширины Redux output потребуют новой проверки.

Встроенная документация 0.5.9 описывает три объектных входа, но пропускает `strength` и `strength_type`. Она также не объясняет flatten batch, добавление токенов, shallow-copy metadata и mask-ветвь. Для этих деталей приоритет имеет код закреплённой версии.

## Связанные ноды и источники

`CLIPVisionEncode` готовит `last_hidden_state`, которое читает style model. `CLIPTextEncode` даёт базовый текстовый контекст. `unCLIPConditioning` — родственная по входному типу, но не взаимозаменяемая операция: она записывает визуальные данные в metadata вместо добавления style-токенов.

- [Реализация `StyleModelApply`](https://github.com/Comfy-Org/ComfyUI/blob/c2bcbecd82ec5ae66594340b395c24ef0217b238/nodes.py#L1113-L1174)
- [Загрузка и вызов style model](https://github.com/Comfy-Org/ComfyUI/blob/c2bcbecd82ec5ae66594340b395c24ef0217b238/comfy/sd.py#L1450-L1468)
- [Реализация Flux Redux encoder](https://github.com/Comfy-Org/ComfyUI/blob/c2bcbecd82ec5ae66594340b395c24ef0217b238/comfy/ldm/flux/redux.py#L1-L25)
- [Встроенная документация 0.5.9](https://github.com/Comfy-Org/embedded-docs/blob/1d258cf6e374d60d138a2bfcd273c7e11f750ef9/comfyui_embedded_docs/docs/StyleModelApply/en.md)
- [Официальные workflow-шаблоны 0.1.42](https://pypi.org/project/comfyui-workflow-templates-json/0.1.42/)
