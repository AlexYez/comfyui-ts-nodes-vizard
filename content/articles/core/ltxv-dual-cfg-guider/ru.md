# LTXVDualCFGGuider: отдельный CFG для видео и аудио

## Что делает нода

`LTXVDualCFGGuider` создаёт объект `GUIDER` для LTXV-AV. Он принимает одну модель и одну пару positive/negative conditioning, но позволяет задать разные classifier-free guidance scales для video и audio частей nested latent.

Во время sampling nested tensors упаковываются последовательно в один flattened tensor. Guider запоминает длину первого сегмента по форме первой части и применяет:

```text
video = uncond + (cond - uncond) × video_cfg
audio = uncond + (cond - uncond) × audio_cfg
```

Разделение происходит не по именам и не по channel count. Первый packed segment считается video, весь хвост — audio. Поэтому порядок частей latent входит в контракт ноды.

## Когда использовать и когда не использовать

Нода нужна для LTXV-AV sampling с nested latent, когда video и audio требуют разных CFG. Например, можно отдельно исследовать, насколько сильно prompt должен влиять на каждый поток, не создавая две независимые sampling-цепочки.

Если `video_cfg` и `audio_cfg` равны, исходник сознательно переходит к обычному CFG с `video_cfg`. Это полезно для совместимости, но не демонстрирует dual-scale поведение. Именно такой случай `[1, 1]` встречается во всех пяти exact instances официального workflow wheel 0.1.42.

Для обычного плоского latent или nested container менее чем с двумя частями guider также использует только `video_cfg`. Не выбирайте эту ноду ради раздельной шкалы, если upstream не формирует video-first AV latent.

## Короткий рецепт подключения

Приложенный fragment переносит доказанную локальную ветвь официальных LTX‑2.5 subgraphs:

1. Подайте LTXV-AV `MODEL` в `LTXVDualCFGGuider`.
2. Подключите positive и negative от совместимой LTXV conditioning/guide ветви.
3. Оставьте official widgets `video_cfg = 1`, `audio_cfg = 1` для точного воспроизведения узла.
4. Соедините выход `GUIDER` со входом `guider` ноды `SamplerCustomAdvanced`.
5. Отдельно подключите noise, sampler, sigmas и nested AV latent.

Wheel содержит один такой узел в LTX‑2.5 first/last-frame-to-video и по два — в image-to-video и text-to-video. Fragment не переносит имена моделей и всю subgraph, поэтому он остаётся безопасным fragment-only recipe.

## Входы, выходы и параметры

- `model` (`MODEL`) — LTXV-AV model patcher, который будет использовать guider.
- `positive` (`CONDITIONING`) — conditional branch.
- `negative` (`CONDITIONING`) — unconditional/negative branch.
- `video_cfg` (`FLOAT`) — CFG для первого packed latent segment, default `3`, диапазон `0…100`, шаг `0.1`, округление UI `0.01`.
- `audio_cfg` (`FLOAT`) — CFG для всего packed tail, default `7`, тот же диапазон и шаг.
- выход `GUIDER` — экземпляр `Guider_LTXAVDualCFG` с сохранёнными conditioning и scales.

При установке параметров внутреннее поле `cfg` сначала получает `max(video_cfg, audio_cfg)`. При реальном unequal dual path итог считает custom `sampler_cfg_function`; это поле не заменяет две отдельные формулы.

## Типовые связки

В официальных LTX‑2.5 cases модель приходит от `UNETLoader`. Positive и negative поступают из LTXV conditioning branches; в first/last-frame case positive проходит через `LTXVAddGuide`. Выход guider всегда соединён с `SamplerCustomAdvanced`.

Перед guider можно поставить `LTXVModalityGuidance` или `LTXVSpatioTemporalGuidance`. Они возвращают изменённый `MODEL`, тогда как dual CFG отвечает за сборку conditional и unconditional predictions по сегментам latent.

Scheduler и sampler остаются отдельными входами `SamplerCustomAdvanced`. `LTXVScheduler` и `ModelSamplingLTXV` не задают video/audio CFG и не заменяют эту ноду.

## Практический пример

Представим nested latent из трёх частей. После packing первая часть занимает 60 значений на каждый batch item, а две оставшиеся идут следом. При `video_cfg = 3`, `audio_cfg = 7` custom CFG применит `3` к первым 60 значениям и `7` ко всему остальному хвосту.

Это поведение подтверждено model-free probe с точным классом: размер video boundary вычислялся как произведение `shape[1:]` первой части, то есть без batch dimension. Третья часть не получила отдельную шкалу — она вошла в audio tail.

Проба также подтвердила fallback: при равных scales используется стандартный CFG, а для flat tensor применяется `video_cfg`. Полный LTX‑2.5 sampling с весами не запускался.

## Частые ошибки и способы проверки

**Ожидание двух CFG на плоском latent.** Проверьте, что sampler получает nested latent минимум из двух частей. Иначе `audio_cfg` не участвует.

**Перепутан порядок частей.** Guider считает video именно первый segment. Если upstream упаковал части иначе, граница окажется неверной. Сверяйте конструктор latent и official LTXV-AV topology.

**Равные scales принимают за dual CFG.** При `video_cfg = audio_cfg` ветвление отключено. Для проверки самой механики задайте разные значения на копии workflow и сравните контрольные seeds.

**Третья часть ожидает собственный scale.** Реализация делит tensor только один раз. Любые дополнительные parts входят в хвост с `audio_cfg`.

**Несовместимые conditioning или model.** Нода хранит объекты без ранней проверки архитектуры. Ошибка формы, dtype или model contract проявится позже в sampling. Сверьте, что model, conditioning и nested latent принадлежат одной LTXV-AV цепочке.

## Производительность и внутреннее поведение

Guider наследует `CFGGuider`. Перед sampling он определяет video boundary из первой nested shape. Nested parts упаковываются в порядке следования, каждый tensor сначала преобразуется в форму `[B, 1, -1]`, затем segments объединяются по последнему измерению.

Для разных scales `predict_noise` копирует `model_options`, добавляет custom `sampler_cfg_function` и выставляет `disable_cfg1_optimization = True`. Это требуется, чтобы conditional и unconditional predictions были доступны для собственной покомпонентной формулы. Даже если одна из двух шкал равна `1`, unequal path не полагается на CFG=1 shortcut.

При равных scales или отсутствии корректного nested split используется стандартная реализация родительского guider с `video_cfg`. Отдельных model passes для каждого modality нода не запускает: разделение применяется к уже полученным packed predictions.

## Совместимость, изменения и устаревание

Материал проверен для ComfyUI `0.32.0` и frontend `1.48.7`. Exact NodeId зарегистрирован в `comfy_extras.nodes_lt`, category `model/sampling/guiders`. В `/object_info` он active, не experimental, не deprecated, не API-only и не dev-only.

Schema fingerprint: `sha256:3e7769b6f756a7f1615523d04d8fb59d0f94b21a1b7304b1076b13ba8d8b03e5`.

Node Replacement API не объявляет для него замену. В embedded docs 0.5.9 отдельной exact-страницы нет. В полном recursive census workflow wheel 0.1.42 найдено пять subgraph instances; все используют widgets `[1, 1]` и ведут `GUIDER` в `SamplerCustomAdvanced`.

## Связанные ноды и источники

- `SamplerCustomAdvanced` — официальный downstream-потребитель `GUIDER` в найденных LTX‑2.5 subgraphs.
- `CFGGuider` — альтернатива для одной общей CFG-шкалы.
- `LTXVModalityGuidance` — model callback для audio/video coupling.
- `LTXVSpatioTemporalGuidance` — model callback с perturbed self-attention в выбранных blocks.
- `LTXVScheduler` и `ModelSamplingLTXV` — соседние элементы LTXV sampling chain.

Источники: [реализация dual guider](https://github.com/Comfy-Org/ComfyUI/blob/c2bcbecd82ec5ae66594340b395c24ef0217b238/comfy_extras/nodes_lt.py#L1053-L1120), [CFG path и custom sampler function](https://github.com/Comfy-Org/ComfyUI/blob/c2bcbecd82ec5ae66594340b395c24ef0217b238/comfy/samplers.py#L592-L627), [упаковка nested tensors](https://github.com/Comfy-Org/ComfyUI/blob/c2bcbecd82ec5ae66594340b395c24ef0217b238/comfy/utils.py#L1374-L1394), [официальный LTX‑2.5 T2V template](https://github.com/Comfy-Org/workflow_templates/blob/cca1ea5ea4560108ecc2f44dee951f41ea433062/templates/video_ltx2_5_t2v.json).
