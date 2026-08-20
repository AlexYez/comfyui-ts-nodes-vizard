# Детерминированный exponential Heun через SEEDS-2

Fragment использует точный preset из runtime description: `solver_type = phi_2`, `r = 1`, `eta = 0`, `s_noise = 1`. По реализации это соответствует sampler `exp_heun_2_x0`.

## Подключение

Передайте совместимые NOISE, GUIDER, SIGMAS и LATENT в `SamplerCustomAdvanced`. Eta 0 отключает SDE injection, но исходный NOISE по-прежнему задаёт стартовую точку sampling.

## Что проверено

Settings и factory options сверены с source. Отдельная обёртка `sample_exp_heun_2_x0` вызывает тот же `sample_seeds_2` с eta 0, `s_noise 0`, r 1 и phi_2; при eta 0 сохранённое здесь `s_noise 1` не используется для injection. Официальных workflow с `SamplerSEEDS2` не найдено, полный model run не выполнялся.

## На что обратить внимание

На обычном ненулевом переходе алгоритм делает две model evaluations. Не путайте детерминированность внутренних SDE-шагов с независимостью от исходного seed: смена NOISE всё равно меняет результат.
