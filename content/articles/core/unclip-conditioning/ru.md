# unCLIPConditioning: прикрепить визуальный embedding к conditioning

## Что делает нода

`unCLIPConditioning` не смешивает tensors сразу. Она добавляет в metadata каждого элемента `CONDITIONING` запись с тремя полями: исходным `CLIP_VISION_OUTPUT`, `strength` и `noise_augmentation`. Совместимая generative model прочитает список `unclip_conditioning` позже, когда ComfyUI будет собирать условия для sampling.

Если список уже существует, новая запись добавляется в конец. Поэтому последовательные экземпляры ноды накапливают референсы. Текстовый tensor каждого элемента остаётся тем же объектом, а его metadata-словарь копируется неглубоко.

При `strength = 0` действует отдельная ветка: нода возвращает тот же входной список без копирования и не записывает даже `noise_augmentation`. Это настоящий no-op на уровне `unCLIPConditioning`, в отличие от нулевого `multiply` у `StyleModelApply`.

## Когда использовать и когда не использовать

Используйте эту ноду только с моделью, которая понимает metadata `unclip_conditioning`. Классические примеры в коде — SD 2.1 unCLIP и SDXL revision; отдельные model classes могут читать те же данные по-своему. В официальном шаблоне SDXL revision два визуальных референса добавляются к positive conditioning перед `KSampler`.

Не считайте совпадение порта `CONDITIONING` доказательством поддержки. Обычная модель может не использовать эту metadata, и граф выполнится без ожидаемого визуального влияния. Для Flux Redux предназначена `StyleModelApply`, которая добавляет tokens; для ControlNet — соответствующая ControlNet-нода и control image.

`noise_augmentation` не является шумом в latent или исходной картинке. Нода лишь сохраняет число. Конкретный model consumer решает, как превратить его в noise level, а некоторые потребители могут вовсе не учитывать это поле.

## Короткий рецепт подключения

1. Получите базовый `CONDITIONING` от текстового encoder, совместимого с unCLIP/revision checkpoint.
2. Загрузите согласованный `CLIP_VISION` и пропустите референс через `CLIPVisionEncode`.
3. Подключите `CLIP_VISION_OUTPUT` к `unCLIPConditioning`.
4. Для воспроизведения официального SDXL revision case начните со `strength = 0.75`, `noise_augmentation = 0`.
5. Передайте выход как positive conditioning sampler. Для второго референса соедините ещё одну `unCLIPConditioning` после первой.

Fragment «Добавить один визуальный референс к conditioning» содержит `CLIPVisionEncode → unCLIPConditioning` с этими официальными значениями. `CLIP_VISION`, `IMAGE` и базовый `CONDITIONING` остаются внешними; checkpoint, sampler и полный workflow не включены.

## Входы, выходы и параметры

`conditioning` принимает `CONDITIONING`, `clip_vision_output` — `CLIP_VISION_OUTPUT`. `strength` — `FLOAT` от `-10` до `10`, default `1`, шаг `0.01`. `noise_augmentation` — `FLOAT` от `0` до `1`, default `0`, шаг `0.01`. Выход — один `CONDITIONING` без list-семантики.

Для ненулевого strength metadata получает структуру вида `unclip_conditioning: [{clip_vision_output, strength, noise_augmentation}]`. Helper `conditioning_set_values(..., append=True)` создаёт новый список через `old_value + new_value`, если ключ уже был. Порядок референсов тем самым сохраняется.

Отрицательный `strength` разрешён runtime-контрактом. В стандартной функции `unclip_adm` итоговый ADM tensor умножается на это число, поэтому знак действительно меняет направление вклада. Визуальный смысл отрицательных значений зависит от модели и не равен простой операции «анти-изображение».

В `unclip_adm` значение `noise_augmentation` переводится в дискретный уровень формулой `round((max_noise_level - 1) × value)`. Затем noise augmentor обрабатывает каждый `image_embeds` из batch. Это поведение относится к model classes, вызывающим эту функцию; сама нода ничего не округляет и не добавляет шум.

При нескольких референсах стандартный consumer сначала строит ADM для каждого изображения, складывает их, затем может применить дополнительный merge noise level. В SD 2.1 unCLIP default `unclip_noise_augment_merge` равен `0.05`. Другие model classes, например Stable Cascade, читают записи иначе и могут использовать только `image_embeds × strength`.

## Типовые связки

Проверенная SDXL revision топология: `LoadImage → CLIPVisionEncode → unCLIPConditioning → unCLIPConditioning → KSampler`. Первая нода получает текстовый positive conditioning; вторая получает выход первой и embedding другого изображения. Negative conditioning в том шаблоне идёт к sampler отдельно.

`CLIPVisionLoader` должен загрузить encoder, подходящий checkpoint. В официальном case это `clip_vision_g.safetensors`. Одинаковый visual encoder можно разветвить на несколько `CLIPVisionEncode`, если референсы разные.

Цепочка с одним референсом может завершаться непосредственно на sampler, но только generative model определяет, будет ли поле прочитано. При диагностике сравнивайте seed-identical прогоны с нодой и с bypass, не меняя одновременно prompt или sampler settings.

`ConditioningCombine` не заменяет последовательное применение: он объединяет элементы conditioning, тогда как `unCLIPConditioning` дописывает список внутри metadata каждого существующего элемента.

## Практический пример

Полный просмотр 512 JSON-файлов пакета 0.1.42 нашёл два `unCLIPConditioning`, оба в корневом графе `sdxl_revision_text_prompts`. В subgraph нода не встретилась. У обеих значения виджетов `[0.75, 0]`.

Первый экземпляр получает positive `CONDITIONING` от `CLIPTextEncode` и visual output первого изображения. Его выход входит во второй экземпляр вместе с visual output второго изображения. Затем накопленный conditioning подключён к positive-порту `KSampler`. Это реальный пример append-семантики, а не два независимых ответвления.

Exact-source проба без model weights начала с двух элементов conditioning; у второго уже была одна тестовая запись. После вызова со `strength = -0.75` и `noise_augmentation = 0.2` первый элемент получил список длины 1, второй — длины 2, причём старая запись осталась первой. Исходные metadata не изменились.

Отдельный вызов со `strength = 0` вернул исходный список по идентичности, хотя `noise_augmentation` был равен `1`. Проба проверяет только запись metadata и helper из закреплённого кода; полный encode → model → sampler fragment не выполнялся.

## Частые ошибки и способы проверки

**Референс не влияет на результат.** Сначала проверьте, поддерживает ли загруженная generative model `unclip_conditioning`. Затем убедитесь, что `CLIP_VISION` соответствует ей, и сравните одинаковые seed с ненулевым strength и bypass.

**`noise_augmentation` принят за denoise.** Эти параметры находятся на разных уровнях. `noise_augmentation` относится к обработке image embedding совместимой моделью, а sampler denoise управляет работой с latent.

**После нескольких нод влияние стало слишком сильным.** Записи складываются, не заменяются. Откройте цепочку от начала до sampler, посчитайте все `unCLIPConditioning` и проверяйте референсы по одному.

**Отрицательный strength дал неожиданные цвета или композицию.** Знак меняет embedding математически, но не формулирует понятное отрицательное описание. Начните с малого положительного значения; отрицательную ветку оценивайте как эксперимент конкретного checkpoint.

**Batch референсов ведёт себя как несколько условий.** `CLIP_VISION_OUTPUT` хранит batch целиком. Стандартный `unclip_adm` проходит по каждому `image_embeds`, поэтому один metadata-элемент способен породить несколько ADM-вкладов.

**Чужая custom node уже записала одноимённый ключ не списком.** Helper делает сложение старого и нового значений. Неверный тип metadata приведёт к ошибке; найдите ноду, которая первой создала `unclip_conditioning`.

## Производительность и внутреннее поведение

Сама `unCLIPConditioning` дешева: она проходит по списку conditioning, сохраняет прежние text tensors и неглубоко копирует словари. Тяжёлый `CLIPVisionEncode` уже выполнен до неё, а реальная обработка ADM откладывается до model conditioning.

Metadata содержит ссылку на весь `CLIP_VISION_OUTPUT`, поэтому накопление многих референсов удерживает их hidden states и embeddings. Если visual output больше нигде не нужен, память освободится только после завершения зависимой очереди по правилам runtime.

Downstream-расход зависит от model class. Стандартный `unclip_adm` проходит по каждому image embedding, вызывает noise augmentor и при нескольких вкладах делает `stack` и сумму. Число записей и размер batch перемножаются.

Неглубокое копирование означает, что прочие вложенные metadata остаются общими с входом. Список `unclip_conditioning` создаётся заново через конкатенацию, так что добавление не изменяет старый список на месте.

## Совместимость, изменения и устаревание

Статья проверена для ComfyUI `0.32.0`, frontend `1.48.7`, модуль `nodes`. Runtime fingerprint: `sha256:253ff654e5ed2a6fd5ef99894e4657a0268830299a49bddedec8a4c1770a567b`.

Нода не помечена как deprecated, experimental или API node; записи в Node Replacement API нет. Контракт metadata прост, но его смысл распределён между самой нодой и model classes. Изменение `conditioning_set_values`, `unclip_adm` или конкретного consumer требует повторной проверки.

Встроенная документация 0.5.9 верно называет назначение входов, но создаёт впечатление, будто нода сразу интегрирует visual output и применяет шум. В 0.32.0 она только записывает данные; использование и даже учёт `noise_augmentation` зависят от загруженной модели.

## Связанные ноды и источники

`CLIPVisionEncode` создаёт объект визуальных признаков. `CLIPTextEncode` обычно формирует базовый conditioning. `KSampler` получает уже помеченный список, но model wrapper решает, как превратить metadata в дополнительные условия. `StyleModelApply` использует тот же тип visual output другим способом и не является прямой заменой.

- [Реализация `unCLIPConditioning`](https://github.com/Comfy-Org/ComfyUI/blob/c2bcbecd82ec5ae66594340b395c24ef0217b238/nodes.py#L1176-L1194)
- [Append helper для conditioning metadata](https://github.com/Comfy-Org/ComfyUI/blob/c2bcbecd82ec5ae66594340b395c24ef0217b238/node_helpers.py#L9-L23)
- [Стандартная сборка unCLIP ADM](https://github.com/Comfy-Org/ComfyUI/blob/c2bcbecd82ec5ae66594340b395c24ef0217b238/comfy/model_base.py#L439-L478)
- [Встроенная документация 0.5.9](https://github.com/Comfy-Org/embedded-docs/blob/1d258cf6e374d60d138a2bfcd273c7e11f750ef9/comfyui_embedded_docs/docs/UnclipConditioning/en.md)
- [Официальные workflow-шаблоны 0.1.42](https://pypi.org/project/comfyui-workflow-templates-json/0.1.42/)
