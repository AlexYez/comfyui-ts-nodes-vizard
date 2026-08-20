# NAGuidance: нормализованное negative guidance внутри attention

## Что делает нода

`NAGuidance` клонирует `MODEL` и регистрирует patch выходов `attn1`. Patch начинает работу только тогда, когда текущий model call содержит сразу positive/conditional и negative/unconditional группы: ComfyUI отмечает их числами `0` и `1` в `cond_or_uncond`. Нода находит обе группы по этим меткам, а не по жёсткому порядку batch.

Для каждого attention-токена она строит экстраполированный вектор:

```text
guided = positive × nag_scale − negative × (nag_scale − 1)
       = positive + (nag_scale − 1) × (positive − negative)
```

Затем вычисляются L1-нормы `positive` и `guided` по последнему измерению. Если отношение `norm_guided / norm_positive` выше `nag_tau`, guided уменьшается до верхней границы `nag_tau × norm_positive`. Если отношение ниже tau, дополнительного увеличения до границы нет. После этого результат смешивается с исходным positive через `nag_alpha`.

Метод задуман для negative prompt там, где distilled или schnell-модель с малым числом шагов слабо реагирует на обычный CFG. Нода не принимает текст и conditioning напрямую: она меняет attention внутри модели, а positive и negative ветви по-прежнему должны прийти из guider.

## Когда использовать и когда не использовать

NAG стоит проверять с моделью, для которой обычный negative prompt действительно не даёт нужного эффекта, особенно в distilled/few-step режиме. Подберите короткий проверяемый запрет — например, один нежелательный объект или свойство — и сравните результат при одном seed с нодой и без неё. Так легче отделить действие negative guidance от обычной вариативности.

Нода экспериментальная. В официальном workflow wheel 0.1.42 точный `NAGuidance` отсутствует во всех 512 JSON и вложенных subgraph. Runtime defaults `nag_scale = 5`, `nag_alpha = 0.5`, `nag_tau = 1.5` — лишь исходные значения интерфейса; официальный набор для конкретной schnell-модели не опубликован.

Не добавляйте NAG в path, который вычисляет только одну conditioning-группу. Если в `cond_or_uncond` нет одновременно меток `0` и `1`, patch возвращает attention без изменений. Нода сама отключает CFG1 optimization, но guider всё равно должен корректно передать positive и negative conditioning.

Не трактуйте tau как точную нормализацию до заданного отношения. Реализация только обрезает значения сверху. Не переносите также утверждение tooltip «alpha 0 — no effect» на все архитектурные ветви без оговорки: при наличии `img_slice` exact source записывает positive-результат и в negative image slice даже при `nag_alpha = 0`.

## Короткий рецепт подключения

1. Сформируйте positive и содержательный negative conditioning для выбранной модели.
2. Подайте исходный `MODEL` в `NAGuidance`.
3. Для контрольного опыта оставьте `nag_scale = 5`, `nag_alpha = 0.5`, `nag_tau = 1.5`.
4. Передайте выходной `MODEL` и обе conditioning-ветви в `CFGGuider` или равнозначный sampling path.
5. Зафиксируйте seed, sigmas, sampler, число шагов и текст.
6. Сравните граф без NAG, затем меняйте только один параметр: сначала alpha, потом scale или tau.

Fragment «NAG: source-derived runtime defaults» содержит одну model patch-ноду и внешний `MODEL`. Он не включает prompt, loader или sampler, потому что официальный пакет 0.1.42 не содержит реальной топологии NAG, а совместимость с конкретной distilled-моделью не была исполнена end-to-end.

## Входы, выходы и параметры

`model` — обязательный `MODEL`. Нода клонирует его, добавляет `attn1` output patch и вызывает `disable_model_cfg1_optimization()` на копии.

`nag_scale` — `FLOAT`, default `5.0`, минимум `0.0`, максимум `50.0`, шаг `0.1`. При `1` формула guided совпадает с positive. Значения выше `1` продолжают движение от negative к positive и дальше; при `0` исходный guided равен negative до нормализации и alpha-смешивания. Большой доступный максимум не означает, что `50` безопасно для любой модели.

`nag_alpha` — `FLOAT`, default `0.5`, диапазон `0.0…1.0`, шаг `0.01`. Это доля нормализованного guided в смеси: `z_final = guided_normalized × alpha + positive × (1 − alpha)`. При обычной ветви без `img_slice` ноль даёт исходный positive. Архитектурная ветвь с `img_slice` дополнительно копирует этот positive в negative image slice.

`nag_tau` — `FLOAT`, default `1.5`, минимум `1.0`, максимум `10.0`, шаг `0.01`. Он задаёт верхнюю границу отношения L1-норм. В знаменателях используется нижняя отсечка `1e−6`, чтобы нулевые нормы не приводили к делению на ноль.

Выход — один пропатченный `MODEL`. Системное имя — `NAGuidance`, display name — `Normalized Attention Guidance`, модуль — `comfy_extras.nodes_nag`, категория — `advanced/guidance`.

## Типовые связки

Явная схема: `MODEL → NAGuidance → CFGGuider`, а positive и negative conditioning подключаются к тому же guider. Дальше `GUIDER` вместе с sampler, sigmas, noise и latent передаётся в `SamplerCustomAdvanced`. Если scheduler читает model sampling object, используйте выход NAG и для него.

NAG работает на всех зарегистрированных `attn1` output patches, а не на одном фиксированном middle-блоке. Если модель сообщает `img_slice`, изменения ограничиваются image tokens; остальные токены сохраняются. В этой ветви один и тот же `z_final` записывается в positive и negative image slices. Без `img_slice` меняется только positive-группа.

`PerturbedAttentionGuidance` связано с NAG общей областью attention guidance, но не заменяет его. PAG создаёт дополнительный conditional model call с отключённым q-k attention. NAG не запускает отдельный forward прямо в своём patch, а преобразует уже вычисленные positive/negative attention outputs и принудительно сохраняет обе CFG-ветви.

## Практический пример

Exact-source tensor-probe подал две группы attention: negative первой и positive второй, поскольку `cond_or_uncond = [1, 0]`. Для `nag_scale = 5`, `nag_alpha = 1`, `nag_tau = 1.5` часть guided-токенов превысила разрешённое отношение норм. Probe получил изменённую positive-группу и побитово сохранил negative-группу; ручной расчёт формулы и tau cap совпал с результатом кода.

При `nag_alpha = 0` и без `img_slice` весь тензор остался прежним. Затем probe повторил вызов с image slice по токенам `1:3`: non-image токен `0` сохранился, positive image tokens не изменились, а negative image tokens стали точной копией positive. Это тонкость реализации 0.32.0, важная для архитектур, которые передают `img_slice`.

Для проверки с моделью используйте negative prompt с одним легко наблюдаемым признаком. Сначала подтвердите, что обычный guider действительно вычисляет обе ветви. Затем сравните `alpha = 0`, default `0.5` и меньший scale, не меняя seed. Оценивайте не только удаление нежелательного признака, но и потерю объектов, композиции и текстур.

## Частые ошибки и способы проверки

**Negative prompt не влияет на результат.** Проверьте `cond_or_uncond`: patch действует только при одновременном наличии групп `0` и `1`. Убедитесь, что negative conditioning подключён к используемому guider, а sampling получает выход NAG.

**`nag_tau` увеличили, но норма не стала ровно равна tau.** Код не подтягивает малые отношения вверх. Он оставляет guided как есть при `ratio ≤ tau` и уменьшает только превышения.

**`nag_alpha = 0`, но часть batch изменилась.** Если модель передала `img_slice`, pinned source копирует positive result в обе image-группы. Для проверки логируйте форму attention, `cond_or_uncond` и наличие `img_slice`; не считайте эту ветвь обычным alpha-blend.

**На CFG=1 расход выше ожидаемого.** Нода отключает model CFG1 optimization, чтобы обе группы были доступны. Сравнивайте скорость с полностью обойдённым NAG, а не только с `nag_alpha = 0`.

**Большой scale разрушил изображение.** Вернитесь к baseline и меняйте scale постепенно. Tau ограничивает L1-норму guided относительно positive, но не гарантирует сохранение направления, композиции или семантики.

## Производительность и внутреннее поведение

Само преобразование attention состоит из поэлементной линейной комбинации, двух L1-норм по последней оси, вычисления ratio и alpha-смешивания. Нода не вызывает `calc_cond_batch` и не делает отдельный полный forward внутри patch. Однако отключение CFG1 optimization может вернуть второй model branch там, где sampling иначе вычислял бы только один, поэтому реальная стоимость зависит от CFG path.

Batch делится на группы через `half_size = batch_size // len(cond_or_uncond)`. Индексы positive и negative находятся по значениям флагов. Такая логика предполагает, что batch корректно сгруппирован и делится на число conditioning-групп; нестандартное объединение требует отдельной проверки.

Нормы считаются по последнему feature-измерению каждого токена, а не по всему latent или всему attention layer. `clamp_min(1e−6)` защищает нулевые векторы. Patch меняет переданный tensor slices на месте, особенно явно в ветви `img_slice`.

В исходнике есть закомментированные `start_percent` и `end_percent`, но runtime-схема их не предоставляет. В версии 0.32.0 NAG применяется при каждом подходящем attention-вызове на всём sampling interval.

## Совместимость, изменения и устаревание

Статья сверена с ComfyUI 0.32.0, commit `c2bcbecd…`, frontend 1.48.7 и exact `/object_info`. Runtime выставляет `experimental = true`; флаги `deprecated`, `dev_only`, `api_node` равны `false`. В pinned Node Replacement API `NAGuidance` не указан.

Поведение зависит от CFG batch grouping и необязательного `img_slice`, поэтому перенос между архитектурами нельзя оценивать только по совпадению типов `MODEL`. После обновления ComfyUI проверяйте реализацию output patch, schema fingerprint и значение experimental.

Embedded docs 0.5.9 передают назначение параметров и сценарий distilled/schnell, но формулировка alpha=0 не охватывает side effect ветви `img_slice`. Wizard сохраняет эту оговорку по exact source и probe. Ни официальный workflow, ни полный запуск distilled-модели пока не подтверждены; материал остаётся draft.

## Связанные ноды и источники

`CFGGuider` передаёт positive и negative conditioning, без которых NAG не активируется. `SamplerCustomAdvanced` удобен для явной сборки всего sampling path. `PerturbedAttentionGuidance` относится к attention guidance, но использует дополнительный conditional-прогон и другую формулу.

Факты проверены по `comfy_extras/nodes_nag.py`, embedded docs 0.5.9 и работе [Normalized Attention Guidance: Universal Negative Guidance for Diffusion Model](https://arxiv.org/abs/2505.21179). Exhaustive census 512 workflow JSON и recursive subgraphs не нашёл `NAGuidance`. Model-free probe подтвердил формулу, L1 cap, CFG1 flag и обе ветви `img_slice`; визуальная оценка distilled-модели и человеческое утверждение ещё не проведены.
