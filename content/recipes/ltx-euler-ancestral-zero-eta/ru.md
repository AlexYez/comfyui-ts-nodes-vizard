# LTX: Euler ancestral без повторного зашумления

Fragment задаёт `SamplerEulerAncestral(eta = 0, s_noise = 1)` и подключает его к `SamplerCustomAdvanced`. Такая пара присутствует в официальных LTX 2.3 и 2.5 subgraph.

## Подключение

Подайте LTX-совместимые NOISE, GUIDER, SIGMAS и LATENT. В официальном `template_ltx2_3_style_transition` это `RandomNoise`, `CFGGuider`, `ManualSigmas` и video latent; downstream использует `denoised_output` sampler.

## Что проверено

Полный scan 512 JSON и всех subgraph нашёл три `SamplerEulerAncestral`. У каждого widgets равны `[0, 1]`, а выход `SAMPLER` подключён к `SamplerCustomAdvanced`. Реализация подтверждает: при eta 0 ancestral-составляющая повторного шума зануляется.

Fragment не включает остальные LTX-ноды и не исполнялся с модельными весами. Он сохраняет только доказанный участок topology.

## На что обратить внимание

`eta = 0` не удаляет исходный NOISE и не задаёт число шагов. SIGMAS должны прийти из проверенного LTX-расписания. Для другого model sampling та же настройка может пройти через отдельную RF/CONST-ветвь алгоритма.
