# APG: проекция, ограничение нормы и momentum для CFG

## Что делает нода

`APG` клонирует `MODEL` и регистрирует pre-CFG hook. На каждом шаге hook берёт разность conditional и unconditional predictions, может накопить её с momentum, ограничить L2-норму и разложить относительно conditional prediction на параллельную и ортогональную части. Параллельная часть умножается на `eta`, ортогональная остаётся без такого множителя.

Метод Adaptive Projected Guidance предложен для уменьшения пересвета и артефактов при высоком classifier-free guidance (CFG). Идея состоит в том, что составляющая guidance, направленная вдоль conditional prediction, сильнее связана с насыщенностью; её можно ослабить, не так сильно затрагивая ортогональную составляющую.

Нода не меняет веса и не создаёт отдельный `GUIDER`. Она меняет поведение любого downstream CFG sampling, который вызывает стандартный pre-CFG контракт ComfyUI.

## Когда использовать и когда не использовать

Используйте APG для контролируемых сравнений при заметном пересвете, чрезмерной насыщенности или артефактах высокого CFG. Сначала сохраните обычный результат с тем же seed, затем меняйте `eta`, `norm_threshold` и `momentum` по одному.

Не включайте ноду как безусловное «улучшение качества». В официальном workflow wheel 0.1.42 exact `APG` отсутствует во всех 512 JSON и вложенных subgraph; подтверждённого универсального preset для core-ноды нет. Runtime defaults — стартовая точка интерфейса, а не рекомендация для каждой модели.

APG требует conditional и unconditional predictions. Если sampling оптимизирует CFG=1 и вычисляет только одну condition, hook сразу возвращает вход без изменений. `cond_scale = 0` опасен: source делит на него при восстановлении modified conditional, и probe получил не-конечные значения.

## Короткий рецепт подключения

1. Подайте исходный `MODEL` в `APG`.
2. Для первого прогона оставьте runtime defaults: `eta = 1`, `norm_threshold = 5`, `momentum = 0`.
3. Используйте выходной model в обычном CFG-графе: например, в `CFGGuider` и model-dependent scheduler.
4. Держите seed, prompt, sampler, sigmas и CFG неизменными.
5. Сравните с полностью убранной APG-ноды, затем пробуйте меньший `eta` или отрицательный momentum.

Fragment «APG: контрольная конфигурация» содержит одну patch-ноду и внешний `MODEL`. Он не обещает готового визуального preset и не включает полный workflow, поскольку model-specific APG generation не выполнялась.

## Входы, выходы и параметры

`model` — обязательный `MODEL`. На выходе возвращается clone с добавленной pre-CFG function.

`eta` — `FLOAT` от `−10` до `10`, шаг `0.01`, default `1`. Он умножает только guidance, параллельную conditional prediction. `eta = 0` удаляет эту составляющую после norm/momentum; отрицательные значения разворачивают её. Tooltip называет `1` default CFG behavior, но точный hook-контракт требует оговорки из практического примера ниже.

`norm_threshold` — `FLOAT` от `0` до `50`, шаг `0.1`, default `5`. При значении выше нуля batch-wise L2-норма по последним трём осям обрезается сверху: коэффициент равен `min(1, threshold / norm)`. Малый vector не увеличивается. `0` отключает ограничение.

`momentum` — `FLOAT` от `−5` до `1`, шаг `0.01`, default `0`. При ненулевом значении состояние обновляется как `running = momentum × running + guidance`. Это накопитель без множителя `(1 − momentum)`, а не нормированное скользящее среднее. Когда sigma возрастает относительно предыдущего вызова, состояние сбрасывается.

## Типовые связки

Наиболее прозрачная цепочка — `MODEL → APG → CFGGuider`. Тот же patched `MODEL` следует подать в `BasicScheduler`, если scheduler читает sampling object модели, а `GUIDER`, `SIGMAS`, noise, sampler и latent соединить в `SamplerCustomAdvanced`.

С `SamplerCustom` core-нода тоже работает, если выбранный path использует обычный model sampling и CFG. APG стоит располагать до других model patch nodes, либо явно фиксировать порядок: несколько pre-CFG hooks выполняются последовательно в порядке регистрации, поэтому перестановка может изменить результат.

Нода не заменяет `CFGGuider` и не принимает positive/negative conditioning. Она только меняет predictions перед заключительным CFG-смешиванием.

## Практический пример

Exact-source tensor probe проверил hook вместе с формулой CFG ComfyUI. Для `eta = 1`, `norm_threshold = 0`, `momentum = 0` итог после hook и стандартного смешивания равен:

```text
conditional + cfg × (conditional − unconditional)
```

Это отличается от обычного:

```text
unconditional + cfg × (conditional − unconditional)
```

То есть pinned реализация при этих настройках добавляет ещё одну исходную разность guidance. Формулировку tooltip «Default CFG behavior at 1» нельзя понимать как точное равенство обычному CFG при отключённом norm threshold; probe это опровергает на ненулевой разности.

Для отрицательного `momentum = −0.5` и простых guidance `1`, затем `2` probe увидел накопитель `1`, затем `1.5`; при последующем росте sigma state сбросился до текущего `2`. После восстановления modified conditional наблюдаемые первые элементы были `1.5`, `2.5`, `3.0`. Это проверка exact code, а не визуальная оценка модели.

## Частые ошибки и способы проверки

**`eta = 1` дал не тот же кадр, что без APG.** В pinned hook это ожидаемо: даже без norm/momentum восстановление conditional устроено так, чтобы downstream CFG сформировал APG update. Сравнивайте с source-формулой, а не только с tooltip.

**При CFG=1 APG будто отключилась.** ComfyUI может не вычислять unconditional branch; при одном элементе `conds_out` hook возвращает его без обработки. Для теста задайте CFG, при котором обе ветви действительно считаются.

**NaN или Inf при CFG=0.** `modified_cond` содержит деление на `cond_scale`. Не используйте нулевой CFG с этой реализацией.

**Momentum усиливает колебания.** Диапазон допускает значения до `−5` и до `1`; накопитель не нормируется. Начинайте с `0`, затем проверяйте умеренное отрицательное значение на фиксированном seed.

**После второго запуска результат зависит от истории.** Closure хранит `running_avg` и `prev_sigma`. Сброс происходит при возрастании sigma, а не отдельным явным событием «новый prompt». Если custom schedule не начинает новый проход с большей sigma, создайте новый patched model или отключите momentum.

## Производительность и внутреннее поведение

APG не добавляет вызов diffusion model. На каждом CFG-шаге она выполняет разность tensors, при необходимости один norm и масштабирование, inner product для projection и несколько сложений. Память расходуется на guidance и, при momentum, на state размером с prediction.

Норма и проекция считаются по последним трём осям. Для image-like `[B, C, H, W]` каждый batch получает свой коэффициент. Для пятимерного video tensor последняя тройка — `[T, H, W]`, а channel-ось остаётся вне суммы; это следует из кода и может отличаться от ожидания «одна норма на весь видеолатент».

Projection нормализует conditional prediction. Нулевая conditional prediction превращается в нулевой unit vector средствами `torch.nn.functional.normalize`; параллельная часть становится нулевой, guidance остаётся ортогональной. Ограничение нормы только уменьшает large guidance и не увеличивает малую.

## Совместимость, изменения и устаревание

Статья проверена для ComfyUI `0.32.0`, frontend `1.48.7` и модуля `comfy_extras.nodes_apg`. Runtime fingerprint: `sha256:3d083411a43984456846f83f333087dce0ce01bc0264758d21b81e312a9f42ee`.

Нода не experimental, deprecated, dev-only и не API node. Display name — `Adaptive Projected Guidance`; runtime search aliases и запись Node Replacement API отсутствуют.

Embedded docs 0.5.9 передают общую идею и диапазоны, но называют momentum «running average» и не раскрывают формулу без `(1 − momentum)`, reset при росте sigma, поведение CFG=0 и точное восстановление conditional. После обновления нужно перепроверять не только schema, но и эти внутренние строки.

## Связанные ноды и источники

`CFGGuider` создаёт обе ветви predictions и задаёт `cond_scale`. `SamplerCustom` и `SamplerCustomAdvanced` выполняют sampling с patched model. Другие model patch nodes могут сосуществовать, но порядок их hooks должен быть проверен отдельно.

- [Реализация `APG`](https://github.com/Comfy-Org/ComfyUI/blob/c2bcbecd82ec5ae66594340b395c24ef0217b238/comfy_extras/nodes_apg.py#L7-L99)
- [Pre-CFG и итоговое CFG-смешивание](https://github.com/Comfy-Org/ComfyUI/blob/c2bcbecd82ec5ae66594340b395c24ef0217b238/comfy/samplers.py#L592-L627)
- [Статья APG, ICLR 2025](https://openreview.net/forum?id=e2ONKX6qzJ)
- [Встроенная документация 0.5.9](https://github.com/Comfy-Org/embedded-docs/blob/1d258cf6e374d60d138a2bfcd273c7e11f750ef9/comfyui_embedded_docs/docs/APG/en.md)
