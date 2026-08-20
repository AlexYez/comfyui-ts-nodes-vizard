# FreSca: раздельное масштабирование частот CFG guidance

## Что делает нода

`FreSca` клонирует `MODEL` и добавляет pre-CFG hook. На каждом model call hook берёт первые два prediction из `conds_out`: conditional и unconditional. Их разность — guidance до умножения на CFG scale:

```text
guidance = conditional − unconditional
```

Guidance переводится в float32 и преобразуется двумерным FFT по последним пространственным осям. После `fftshift` весь spectrum сначала получает множитель `scale_high`, а центральный прямоугольник — `scale_low`. Его половина ширины по каждой оси равна `min(freq_cutoff, axis_size // 2)`. Обратный FFT возвращает исходный dtype.

Из отфильтрованной разности нода восстанавливает conditional prediction: `filtered_conditional = filtered_guidance + unconditional`. Unconditional и дополнительные элементы `conds_out[2:]` сохраняются. Дальше стандартный CFG смешивает уже изменённую разность.

Работа FreSca показывает, почему важно называть обрабатываемый тензор точно. Это не фильтр изображения, latent или decoder skip. Нода меняет conditional-unconditional noise/model prediction перед CFG.

## Когда использовать и когда не использовать

FreSca стоит исследовать, когда нужен раздельный контроль крупной пространственной структуры и мелких деталей, создаваемых guidance. Low frequencies расположены около центра shifted spectrum и связаны с плавными, крупномасштабными изменениями; внешняя область содержит более быстрые пространственные изменения. Визуальный смысл всё равно зависит от модели и parameterization.

Нода экспериментальная. Для неё нет официального workflow в wheel 0.1.42: точный `FreSca` отсутствует во всех 512 JSON и recursive subgraphs. Defaults `scale_low = 1`, `scale_high = 1.25`, `freq_cutoff = 20` взяты из runtime ComfyUI 0.32.0, но не прошли в Wizard end-to-end проверку на каждой архитектуре.

Hook требует как минимум два predictions и два непустых conditioning entries. Если `len(conds_out) ≤ 1` либо среди первых двух `conds` есть `None`, функция возвращает исходный список без фильтрации. Нода не отключает CFG1 optimization, поэтому в path с одной вычисляемой ветвью эффект может исчезнуть.

Учитывайте размер prediction. На even spatial shape `8 × 8` default cutoff `20` ограничивается половиной каждой оси и покрывает весь spectrum. Тогда `scale_high = 1.25` вообще не используется, а `scale_low = 1` делает filter тождественным. На `64 × 64` центральная область имеет `40 × 40`, и внешние частоты получают high-scale.

## Короткий рецепт подключения

1. Подайте `MODEL` в `FreSca`.
2. Оставьте runtime defaults: `scale_low = 1`, `scale_high = 1.25`, `freq_cutoff = 20`.
3. Подключите выход к CFG sampling path с conditional и unconditional ветвями.
4. Зафиксируйте seed, prompt, negative prompt, CFG, sampler и sigmas.
5. Узнайте фактические `H × W` prediction, чтобы понять, не охватил ли cutoff весь spectrum.
6. Сначала сравните `scale_low = scale_high = 1`, затем меняйте один множитель.

Fragment «FreSca: source-derived runtime defaults» содержит одну patch-ноду и внешний `MODEL`. Он не включает выдуманный checkpoint или workflow: официальный wheel не даёт реального FreSca topology, а полный sampling example не исполнялся.

## Входы, выходы и параметры

`model` — обязательный `MODEL`. Нода клонирует его и регистрирует `sampler_pre_cfg_function`.

`scale_low` — advanced `FLOAT`, default `1.0`, диапазон `0…10`, шаг `0.01`. Он умножает spectrum внутри центрального прямоугольника. Ноль удаляет эти bins из guidance; единица сохраняет; значение выше единицы усиливает.

`scale_high` — advanced `FLOAT`, default `1.25`, тот же диапазон и шаг. Он заполняет всю маску до того, как центральная часть будет перезаписана low-scale. Если cutoff охватил spectrum целиком, high-scale не остаётся ни в одном bin.

`freq_cutoff` — advanced `INT`, default `20`, диапазон `1…10000`, шаг `1`. Код независимо ограничивает его половиной высоты и ширины. Поэтому фактический центральный размер равен `2 × min(cutoff, H//2)` на `2 × min(cutoff, W//2)`. На нечётной оси максимальный срез имеет длину `axis_size − 1`, оставляя одну строку или колонку под `scale_high`.

Выход — один `MODEL`. Exact NodeId и display name — `FreSca`, модуль — `comfy_extras.nodes_fresca`, категория — `experimental`. Runtime search alias `frequency guidance` подтверждён и пригоден для поиска, но resolver использует точную identity.

## Типовые связки

Явная цепочка — `MODEL → FreSca → CFGGuider → SamplerCustomAdvanced`. Positive и negative conditioning должны попасть в один CFG call. Scheduler, который читает model sampling object, получает тот же пропатченный `MODEL`.

Если `scale_low = scale_high = c`, весь guidance умножается примерно на `c` независимо от cutoff. Это похоже на изменение силы conditional-unconditional разности до стандартного CFG, но не превращает FreSca в отдельный guider: downstream CFG scale всё равно применяется своим кодом.

`FreeU` и `FreeU_V2` используют FFT внутри U-Net decoder и фильтруют skip features. FreSca работает после model predictions. Их можно поставить в одну model chain, но тогда FreeU сначала меняет сам forward, а FreSca фильтрует получившуюся guidance-разность.

Pre-CFG hooks накапливаются и исполняются в порядке регистрации. Два FreSca последовательно фильтруют уже изменённую conditional ветвь. Линейные Fourier masks часто композиционно перемножают коэффициенты, но рядом с нелинейным pre-CFG patch порядок может изменить результат.

## Практический пример

Exact-source probe передал conditional и unconditional формы `2 × 3 × 8 × 8`, а также третий prediction. При defaults cutoff ограничился `4` по обеим осям и центральный срез стал `8 × 8`. Весь spectrum получил `scale_low = 1`; conditional вернулся равным исходному в пределах FFT-погрешности. Unconditional и третий элемент сохранили object identity.

При `scale_low = scale_high = 1` float16-тензор `16 × 16` восстановился с тем же dtype и погрешностью менее выбранного допуска `0.002`. Отдельный 5D tensor формы `2 × 4 × 3 × 8 × 10` успешно прошёл FFT последних двух осей и сохранил форму и dtype. Эта ветвь подходит для per-frame spatial prediction, но не доказывает качество video model.

Для нечётной формы `5 × 5` и огромного cutoff центральная область оказалась `4 × 4`: одна frequency row/column сохранила `scale_high`. При `scale_high = 2` результат не был тождественным. Практический вывод прост: cutoff надо интерпретировать вместе с чётностью и размером prediction.

## Частые ошибки и способы проверки

**Default не изменил маленький latent.** Проверьте spatial shape. Если обе оси не больше `40` и чётные, cutoff `20` может покрыть весь spectrum; при `scale_low = 1` фильтр становится identity.

**Изменение high-scale ничего не даёт.** Уменьшите cutoff так, чтобы внешняя область маски не была пустой. Сначала рассчитайте фактический central rectangle, а не подбирайте число наугад.

**Нода не действует при CFG=1.** Проверьте, вычисляются ли обе conditioning-ветви. FreSca сама не отключает CFG1 optimization и делает bypass при одном prediction или `None` в первых двух `conds`.

**Ожидался energy-based cutoff из статьи.** Pinned ComfyUI node реализует фиксированный прямоугольный `freq_cutoff`. Адаптивный energy threshold из более полного reference-кода не входит в её runtime schema.

**Video tensor прошёл, значит поддержка гарантирована.** Helper действительно принимает произвольные ведущие оси и фильтрует последние две. Но группировка predictions, CFG contract и визуальная пригодность конкретной video-модели требуют отдельного запуска.

## Производительность и внутреннее поведение

На каждом pre-CFG вызове с двумя ветвями создаются guidance, float32 complex spectrum и полноразмерная маска. FFT выполняется только по последним двум осям, поэтому batch, channel и возможная time-axis обрабатываются независимо. Дополнительного model forward нет.

Маска сначала полностью заполняется `scale_high`, затем через два последовательных `narrow` выбирается центральная область и записывается `scale_low`. При нулевой половине оси central view может быть пустым, хотя UI не допускает cutoff ниже единицы.

Исходный dtype и device запоминаются. FFT всегда считает в float32, а результат приводится назад. В отличие от FreeU, FreSca не содержит CPU fallback; отсутствие FFT-поддержки или ошибка памяти передаются вызывающему коду.

Пять измерений не распаковываются вручную, поэтому `(..., H, W)` — реальный helper contract. Цена памяти растёт со всеми ведущими измерениями, включая frames.

## Совместимость, изменения и устаревание

Статья проверена по ComfyUI 0.32.0, source commit `c2bcbecd…`, frontend 1.48.7 и exact runtime inventory. `experimental = true`; `deprecated`, `dev_only`, `api_node` равны `false`. В pinned replacement API `FreSca` отсутствует.

Reference-проект FreSca описывает spatial и energy-based cutoffs. Core-нода версии 0.32.0 предоставляет только фиксированный integer cutoff. После обновления нельзя переносить выводы между вариантами без проверки исходника.

Embedded docs 0.5.9 правильно объясняет low/high scaling и ranges, но не говорит о saturation на малых even shapes, нечётном frequency rim, bypass conditioning или 5D contract. Эти детали подтверждены exact source и tensor probe.

## Связанные ноды и источники

`CFGGuider` формирует conditional/unconditional path, от которого зависит FreSca. `FreeU` и `FreeU_V2` тоже используют Fourier scaling, но внутри decoder skip branches. Связь семантическая, не replacement.

Факты сверены с `comfy_extras/nodes_fresca.py`, embedded docs 0.5.9, [официальным проектом FreSca](https://github.com/WikiChao/FreSca) и работой [FreSca: Scaling in Frequency Space Enhances Diffusion Models](https://arxiv.org/abs/2504.02154). Полный census 512 workflow JSON не нашёл ноду. Probe подтвердил branches, cutoff geometry, odd/even behavior, dtype и 5D filtering; full model run и человеческое утверждение ещё ожидаются.
