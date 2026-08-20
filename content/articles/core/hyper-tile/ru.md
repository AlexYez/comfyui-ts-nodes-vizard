# HyperTile: разбиение self-attention на пространственные тайлы

## Что делает нода

`HyperTile` клонирует `MODEL` и добавляет две функции вокруг `attn1`. Входной patch определяет, соответствует ли длина token sequence одному из выбранных пространственных уровней. Если да, он делит условную сетку на `nh × nw` тайлов и переносит их в batch:

```text
B × (nh × tile_h × nw × tile_w) × C
→ (B × nh × nw) × (tile_h × tile_w) × C
```

Self-attention получает больше batch elements, но более короткие последовательности. После attention выходной patch выполняет обратные `rearrange` и восстанавливает исходную последовательность токенов. При `nh × nw = 1` тензор проходит без перестройки.

Применяемые уровни вычисляются из последних двух осей `original_shape`: площадь `H × W` для depth `0`, затем `H × W / 4`, `/16` и так далее до `max_depth`. Длина `q` должна точно совпасть с одной из этих площадей. Это generic token-count contract, а не список имён слоёв конкретной архитектуры.

HyperTile уменьшает размер отдельных attention matrices и может снизить затраты вычислений и памяти. Он не делит VAE и не выполняет tiled decode: core-нода патчит только `MODEL` self-attention.

## Когда использовать и когда не использовать

HyperTile имеет смысл проверять, когда self-attention становится узким местом на большом spatial latent. Чем больше токенов и чем больше тайлов, тем сильнее сокращается длина каждой attention sequence. Реальный выигрыш зависит от attention backend, размера batch, модели и накладных расходов rearrange.

Нода меняет область взаимодействия attention. Токены внутри одного тайла обрабатываются вместе, а границы тайлов могут отражаться на изображении. Upstream-проект отдельно предупреждает о мягких tile patterns. Поэтому скорость и память нельзя оценивать без проверки качества на том же seed.

Не воспринимайте `swap_size` как случайный сдвиг границы тайлов. В pinned source нет `roll`, offset или смены начальной координаты. Функция случайно выбирает число тайлов из делителей размера; сама сетка всегда начинается в фиксированном начале последовательности.

В официальном workflow wheel 0.1.42 exact `HyperTile` отсутствует среди 512 JSON и recursive subgraphs. Default `tile_size = 256`, `swap_size = 2`, `max_depth = 0`, `scale_depth = false` — runtime-конфигурация, а не официальный performance preset.

## Короткий рецепт подключения

1. Подайте `MODEL` в `HyperTile`.
2. Для первого опыта оставьте defaults: `256`, `2`, `0`, `false`.
3. Передайте выход в прежний sampler path.
4. Сохраните baseline без HyperTile при том же seed.
5. Сравните peak memory, время шага и изображение.
6. Если тайлинг не активировался, проверьте token count и делители spatial shape.
7. Если нужны более глубокие уровни, увеличьте `max_depth` на один и повторите измерение.

Fragment «HyperTile: source-derived runtime defaults» содержит одну patch-ноду и внешний `MODEL`. Он не включает полный workflow, потому что в official wheel нет реального topology/widgets case, а model performance run не выполнялся.

## Входы, выходы и параметры

`model` — обязательный `MODEL`. Нода ставит один `attn1_patch` и один `attn1_output_patch` на clone.

`tile_size` — advanced `INT`, default `256`, диапазон `1…2048`. Внутри вычисляется `latent_tile_size = max(32, tile_size) // 8`. Значения `1…39` дают `4` latent units, то есть тот же floor, что `32` pixels; `40` даёт `5`. Остаток от деления на восемь отбрасывается.

`swap_size` — advanced `INT`, default `2`, диапазон `1…128`. Он ограничивает число первых подходящих делителей, из которых `random_divisor` выбирает tile count. При `1` выбор детерминирован. Из-за exact вызова `randint(high=len(options) − 1)` последний кандидат исключён, когда вариантов больше одного. Для двух кандидатов выбирается только первый; это проверено probe.

`max_depth` — advanced `INT`, default `0`, диапазон `0…10`. Ноль разрешает только площадь исходных `H × W`; единица добавляет уровень `/4`. Значения глубже реальной архитектуры ничего не добавят, пока token count не совпадёт.

`scale_depth` — advanced `BOOLEAN`, default `false`. При `true` минимальный размер делителя умножается на `2^depth`, поэтому глубокий уровень обычно получает меньше тайлов и более длинные sequences.

Выход — один `MODEL`. Exact NodeId — `HyperTile`, модуль — `comfy_extras.nodes_hypertile`, категория — `model/patch/unet`; runtime aliases отсутствуют.

## Типовые связки

Базовая цепочка — `MODEL → HyperTile → sampler` или `MODEL → HyperTile → CFGGuider → SamplerCustomAdvanced`. Нода не требует отдельного latent input: spatial shape приходит через `extra_options["original_shape"]` во время model forward.

`ModelAttentionBackend` меняет attention implementation, а HyperTile — форму входов. Эти patches могут сочетаться, но backend должен корректно обработать изменённый batch и token count. Exact `attention_basic` использует batch из tiled `q` при reshape `k/v`, поэтому синтетический batch `2` успешно превратился в batch `8` и восстановился.

Порядок рядом с `SelfAttentionGuidance` или NAG важен. Input attention patches идут по списку до attention, output patches — по списку после него. Если output guidance patch увидит tiled tensor до восстановления, его batch grouping и spatial assumptions могут нарушиться.

Не складывайте два HyperTile без отдельной проверки. У каждого экземпляра есть собственный `temp`, но input и output patch lists исполняются в одном направлении, а корректное снятие вложенных преобразований обычно требует обратного порядка. Второй patch также может принять укороченную sequence за более глубокий уровень.

## Практический пример

Probe взял `original_shape = 64 × 64`, batch `2` и `4096` токенов. При defaults `latent_tile_size = 32`; делители `64`, начиная с `32`, дали tile count `2` по каждой оси. `q` изменил форму с `2 × 4096 × 4` на `8 × 1024 × 4`, а `k/v` остались исходными объектами до attention.

Exact `attention_basic` затем использовал новый batch из `q` и переинтерпретировал общее число элементов `k/v` в те же `8 × 1024` группы. Выходной HyperTile patch восстановил форму `2 × 4096 × 4`. Это подтверждает batch path без весов, но не измеряет скорость backend.

Проверка `random_divisor(120, 4, 4)` на 64 seeds увидела tile counts `30`, `24` и `20`; четвёртый кандидат `15` никогда не выбирался. Для типичного `random_divisor(64, 32, 2)` все seeds дали `2`: default swap-size в этой геометрии не создаёт случайности.

При `tile_size` `1` и `39` sequence `32 × 32` разбилась одинаково на batch `64` по `16` токенов. Значение `40` дало batch `16` по `64` токена. Эти формы полезнее расплывчатого выражения «размер округляется»: они показывают точный integer floor.

## Частые ошибки и способы проверки

**`swap_size = 2`, но сетка не меняется между seed.** Если найдено ровно два кандидата, exact upper bound исключает последний и выбор всегда падает на первый. Случайность появляется только при достаточном числе делителей.

**Ожидался random shift тайлов.** Код меняет divisor, а не origin. Граница начинается в одном месте; пространственного offset нет. Не приписывайте `swap_size` поведение, которого нет в source.

**HyperTile не активируется.** Сравните `q.shape[-2]` со списком `H × W / 4^depth`. Joint spatiotemporal attention с `T × H × W` токенами не совпадает с одной spatial area и проходит без tiling.

**`rearrange` падает на нестандартной модели.** `h` и `w` восстанавливаются через округлённый квадратный корень и aspect ratio. Если их произведение не равно token count или размеры не делятся на выбранные tile counts, pattern не собирается.

**После добавления второго attention patch испортился batch.** Проверьте порядок input/output patches. HyperTile временно переносит tile count в batch; соседний patch должен либо понимать эту форму, либо выполняться после восстановления.

## Производительность и внутреннее поведение

При `N` токенах и `t` тайлах attention работает примерно с `t` sequences длиной `N/t`. Квадратичная часть тогда масштабируется ближе к `N²/t`, но точная экономия зависит от backend, heads, kernel launches и памяти. Rearrange создаёт новые views или copies согласно layout.

`random_divisor` сначала ограничивает минимальный divisor значением `value`, затем перебирает все делители от минимума вверх. Из первых `swap_size` делителей строятся tile counts `value/divisor`. Функция использует глобальный torch RNG и тем самым потребляет его состояние.

`temp = (nh, nw, h, w)` хранится в closure между input и output patch. После успешной сборки `temp` сбрасывается в `None`. Реализация предполагает синхронную пару вызовов без перекрытия; необычная reentrant execution требует отдельной проверки.

Для `scale_depth = true` probe на depth `1`, tile size `64` получил `4 × 256` вместо `16 × 64`: число batch tiles уменьшилось в четыре раза, а sequence стала длиннее. Это прямое следствие увеличенного minimum divisor.

## Совместимость, изменения и устаревание

Материал проверен по ComfyUI 0.32.0, source commit `c2bcbecd…`, frontend 1.48.7 и exact runtime inventory. Флаги `experimental`, `deprecated`, `dev_only`, `api_node` равны `false`. Replacement API не содержит `HyperTile`.

5D `original_shape` само по себе не вызывает ошибку: код читает только последние `H/W`. Probe показал, что per-frame spatial attention с `4096` токенами на кадр может тайлиться, если frames уже находятся в batch. Joint sequence `T × H × W` была пропущена. Это не универсальная video support guarantee.

Upstream HyperTile патчил и U-Net, и VAE по именам слоёв; core-нода ComfyUI использует generic `attn1` hooks только на `MODEL`. Embedded docs 0.5.9 полезно описывает параметры, но формулировка про перестановку тайлов неточна относительно exact random-divisor code.

## Связанные ноды и источники

`ModelAttentionBackend` определяет attention kernel, который получает tiled форму. `SelfAttentionGuidance` тоже патчит `attn1` и хранит attention map, поэтому порядок с HyperTile требует особой проверки. Это связанные механизмы, а не replacements.

Контракт сверялся с `comfy_extras/nodes_hypertile.py`, базовым attention loop ComfyUI, embedded docs 0.5.9 и [официальным репозиторием HyperTile](https://github.com/tfernd/HyperTile). Exhaustive wheel census дал ноль точных экземпляров. Probe подтвердил reshape batch `2`, divisor randomness, off-by-one выбора, tile floor, depth scaling и два video token layouts; full model timing, качество и человеческое утверждение ещё ожидаются.
