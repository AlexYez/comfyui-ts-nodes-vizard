# Нулевой шум для SamplerCustomAdvanced

Fragment подаёт `DisableNoise` в `SamplerCustomAdvanced`. Это точная topology из официальных Lotus Depth, SD 3.5 Depth, Qwen control и LTX depth templates.

## Подключение

Передайте `GUIDER`, `SAMPLER`, `SIGMAS` и существующий `LATENT` во внешние входы. Нулевой noise не отменяет эти части графа: sampler выполнит расписание и модельные вычисления.

## Что именно проверено

Полный census нашёл семь `DisableNoise`, и каждый выход подключён к порту `noise` у `SamplerCustomAdvanced`. Два Hunyuan экземпляра bypassed, остальные подтверждают активное применение. Exact-source probe проверила форму, dtype, CPU и нулевые значения.

Fragment структурно валиден, но не исполнялся с моделью. Он не заявляет, что нулевой шум подходит любому pipeline.

## На что обратить внимание

Результат sampler не обязан совпасть с входным LATENT. Если цель — полностью обойти sampling, нужен другой путь графа. Здесь отключается только случайная составляющая входного NOISE.

