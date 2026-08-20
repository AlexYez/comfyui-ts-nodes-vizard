# ER-SDE с тремя стадиями

Fragment задаёт `solver_type = ER-SDE`, `max_stage = 3`, `eta = 1`, `s_noise = 1` и подключает sampler к `SamplerCustomAdvanced`.

## Подключение

Добавьте NOISE, GUIDER, SIGMAS и LATENT из одного совместимого pipeline. Для диагностического сравнения смените `solver_type` на `ODE`, не меняя остальные компоненты: constructor принудительно отключит noise injection.

## Что проверено

Runtime-порты и scaler-функции сверены с exact source. Probe проверяет ER-SDE, Reverse-time и ODE closures, включая переход к ODE при eta 0. Официальных workflow с этой нодой в полном wheel 0.1.42 нет; модельный fragment не исполнялся.

## На что обратить внимание

Первые шаги не могут использовать все три стадии — история ещё не накоплена. Eta влияет на ER-SDE scaler, несмотря на обратное утверждение embedded docs. Большие eta могут привести к невалидным значениям.
