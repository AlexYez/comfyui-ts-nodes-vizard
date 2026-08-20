# LTXVSpatioTemporalGuidance: STG по выбранным блокам

## Что делает нода

`LTXVSpatioTemporalGuidance` клонирует `MODEL` и добавляет post-CFG callback для LTXV. На активном шаге sampling callback делает дополнительный conditional pass. В этом проходе выбранные transformer blocks получают настройку `stg_skip_self_attn`: их self-attention не вычисляет обычное внимание, а возвращает value projection как есть.

Полученный `perturbed` prediction используется в формуле:

```text
cfg_result + (cond_pred - perturbed) × scale
```

Так основной результат направляется от прохода с ослабленным self-attention. Cross-attention эта ветвь не заменяет: переключатель проверяется только в self-attention path.

Нода не создаёт отдельный `GUIDER` и не меняет conditioning. На выходе остаётся клон `MODEL` с callback, который sampler вызовет позже.

## Когда использовать и когда не использовать

Нода рассчитана на LTXV-модель, в которой transformer читает `stg_self_attn_blocks`. Её можно проверять, когда temporal или spatial consistency в конкретной генерации выигрывает от Spatio-Temporal Guidance. Эффект зависит от checkpoint, выбранных блоков, prompt, seed и участка sigma schedule; универсального набора индексов в официальных материалах нет.

Не ставьте STG на произвольный `MODEL` только потому, что сокет совместим по типу. Модель, которая не обрабатывает эту transformer option, выполнит дополнительный pass без задуманного perturbation. Это увеличит время sampling, но не даст ожидаемой разницы.

`scale = 0` отключает дополнительный проход. В отличие от `LTXVModalityGuidance`, значение `1` здесь не означает bypass: при непустом наборе блоков extra pass выполняется и разность прибавляется с коэффициентом `1`.

## Короткий рецепт подключения

Приложенный fragment показывает source-derived связку:

1. Передайте LTXV `MODEL` в `LTXVSpatioTemporalGuidance`.
2. Для первой проверки оставьте `blocks = "29"`, `scale = 1`, `start_percent = 0`, `end_percent = 1`.
3. Подайте изменённый `MODEL` в `LTXVDualCFGGuider`.
4. Подключите positive и negative conditioning той же LTXV-AV цепочки.
5. Передайте полученный `GUIDER` в `SamplerCustomAdvanced` вместе с совместимым latent, sampler, sigmas и noise.

`29` — default runtime schema, а не доказанный лучший блок. В официальном workflow wheel 0.1.42 точных экземпляров `LTXVSpatioTemporalGuidance` нет, поэтому fragment не закрепляет checkpoint и не называется официальным workflow.

## Входы, выходы и параметры

- `model` (`MODEL`) — модель, которая будет клонирована. Исходный объект не патчится на месте.
- `scale` (`FLOAT`) — коэффициент разности между обычным conditional prediction и perturbed prediction. Default `1`, диапазон `0…100`, шаг `0.01`.
- `blocks` (`STRING`) — строка с индексами transformer blocks. Default `29`. Поле однострочное.
- `start_percent` (`FLOAT`) — начало активного участка sampling, default `0`, диапазон `0…1`, шаг `0.001`.
- `end_percent` (`FLOAT`) — конец участка, default `1`, тот же диапазон и шаг.
- выход `MODEL` — клон с зарегистрированным post-CFG callback.

Парсер не разбирает диапазоны. Он извлекает каждую последовательность цифр через регулярное выражение `\d+`, преобразует числа в `int` и собирает `frozenset`. Поэтому `3-5` означает блоки `3` и `5`, а не `3, 4, 5`; `-7` превращается в `7`; повторы удаляются. Индексы нумеруются с нуля, потому что LTXV transformer перебирает blocks через `enumerate`.

## Типовые связки

Выходной `MODEL` обычно нужен ноде, которая строит sampling guider. Для LTXV-AV это может быть `LTXVDualCFGGuider`; для иной совместимой LTXV-цепочки выбор guider зависит от latent и conditioning.

`LTXVSpatioTemporalGuidance` можно ставить вместе с `LTXVModalityGuidance`. Обе ноды клонируют модель и добавляют post-CFG callback; `ModelPatcher` хранит callbacks списком, поэтому патчи складываются, а не заменяют друг друга. Порядок нод определяет порядок callbacks. На одном активном шаге каждый callback может вызвать собственный дополнительный conditional pass.

`ModelSamplingLTXV`, scheduler и sampler отвечают за sigma schedule. STG лишь преобразует `start_percent` и `end_percent` в sigma-границы через модель и проверяет текущую sigma внутри callback.

## Практический пример

Допустим, callback получил:

- `cfg_result = 2`;
- обычный `cond_pred = 4`;
- perturbed prediction `= 1`;
- `scale = 1.5`.

Тогда результат равен `2 + (4 - 1) × 1.5 = 6.5`. Это пример арифметики callback, а не прогноз качества изображения или видео.

Model-free probe с точным исходным классом также проверил строку `29, 3-5, -7, 29`. Она дала множество `{3, 5, 7, 29}`. Проба подтвердила bypass при `scale = 0`, при строке без цифр и вне sigma-интервала. Настоящий LTXV checkpoint и полный fragment не запускались.

## Частые ошибки и способы проверки

**Запись диапазона через дефис.** `10-15` выбирает только `10` и `15`. Перечислите нужные индексы явно: `10,11,12,13,14,15`.

**Отрицательный индекс.** Знак минус отбрасывается, поэтому `-1` выбирает блок `1`, а не последний блок. Не используйте Python-подобную отрицательную индексацию.

**Несуществующий индекс.** Исходник не сверяет число с длиной transformer. Такой индекс просто не совпадёт ни с одним блоком, и perturbed pass может стать эквивалентен обычному. Проверьте архитектуру конкретного checkpoint.

**Пустая строка или текст без цифр.** Ошибки не будет: множество окажется пустым, callback вернёт исходный `cfg_result` без extra pass.

**Перепутаны проценты.** Интервал проверяется в sigma-пространстве включительно. При `start_percent > end_percent` для обычного убывающего schedule условия чаще всего не пересекутся. Начните с `0…1` и сужайте участок после контрольного запуска.

## Производительность и внутреннее поведение

Клонирование `ModelPatcher` само по себе не копирует все веса. Основная цена появляется при sampling: на каждом активном шаге нода вызывает дополнительный `calc_cond_batch` для того же conditioning.

Перед extra pass callback копирует словари `model_options` и `transformer_options`, затем добавляет `stg_self_attn_blocks`. Исходные options не изменяются. В выбранных LTXV blocks флаг доходит до self-attention, где вместо нормализации Q/K и attention используется `out = v`; остальные части блока продолжают работу.

Чем шире percent-интервал, тем больше дополнительных проходов. Если вместе стоят STG и modality guidance, их стоимость суммируется на шагах, где активны оба callback. Точные VRAM и время зависят от модели, формы nested latent, precision, offload и устройства; в этой проверке они не измерялись.

## Совместимость, изменения и устаревание

Контракт проверен для ComfyUI `0.32.0` и frontend `1.48.7`. Нода находится в `comfy_extras.nodes_lt`, имеет category `advanced/guidance` и в закреплённом `/object_info` не помечена как experimental, deprecated, API-only или dev-only.

Schema fingerprint: `sha256:6a29a729966cc530c7c6dbca805623863f86aad25a220833952461663180b0ca`.

В Node Replacement API для этой версии нет записи о замене. В embedded docs 0.5.9 отдельной страницы для exact NodeId нет. Полный recursive census workflow wheel 0.1.42 просмотрел 512 JSON и 768 root/subgraph graphs; точных instances также не найдено. Это означает отсутствие закреплённого официального примера в проверенных пакетах, а не отсутствие поддержки в runtime.

## Связанные ноды и источники

- `LTXVModalityGuidance` — другой model callback: временно отключает audio/video cross-attention и направляет prediction к связанному результату.
- `LTXVDualCFGGuider` — строит `GUIDER` с отдельными video/audio CFG для nested LTXV-AV latent.
- `SamplerCustomAdvanced` — принимает готовый guider в официальных LTX‑2.5 subgraphs.
- `ModelSamplingLTXV` — задаёт LTXV sampling contract и преобразование процентов в sigma через модель.

Источники: [реализация ноды](https://github.com/Comfy-Org/ComfyUI/blob/c2bcbecd82ec5ae66594340b395c24ef0217b238/comfy_extras/nodes_lt.py#L940-L991), [маршрутизация STG по блокам LTXV-AV](https://github.com/Comfy-Org/ComfyUI/blob/c2bcbecd82ec5ae66594340b395c24ef0217b238/comfy/ldm/lightricks/av_model.py#L932-L960), [ветвь value-passthrough в attention](https://github.com/Comfy-Org/ComfyUI/blob/c2bcbecd82ec5ae66594340b395c24ef0217b238/comfy/ldm/lightricks/model.py#L464-L492), [workflow templates JSON 0.1.42](https://pypi.org/project/comfyui-workflow-templates-json/0.1.42/).
