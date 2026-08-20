# Chroma Radiance: ветка beta-расписания

Fragment повторяет точную ветку единственного официального случая 0.1.42: внешний `MODEL` проходит через `ModelSamplingAuraFlow(shift = 1.0)`, затем `BetaSamplingScheduler` читает патченную таблицу с `steps = 30`, `alpha = 0.4`, `beta = 0.4`.

В полном subgraph тот же патченный `MODEL` идёт в `CFGGuider`, а `SIGMAS` — в `SamplerCustomAdvanced`. При сборке графа разветвите выход `ModelSamplingAuraFlow` именно так; scheduler и guider должны видеть одну sampling-конфигурацию.

Fragment не содержит веса Chroma Radiance, conditioning, guider, noise, sampler и latent. Поле полного workflow отсутствует, а модельная генерация не выполнялась. Значения `0.4/0.4` подтверждены только для этого официального Chroma-кейса, не для произвольного checkpoint.
