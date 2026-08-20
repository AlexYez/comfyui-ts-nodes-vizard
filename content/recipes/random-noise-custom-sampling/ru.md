# Воспроизводимый шум для SamplerCustomAdvanced

Fragment соединяет `RandomNoise(noise_seed = 42)` с `SamplerCustomAdvanced`. Значение 42 в fixed-режиме встречается в официальных LTX workflow, а сама связь `NOISE → noise` подтверждена десятками официальных root и subgraph.

## Подключение

Передайте совместимые `GUIDER`, `SAMPLER`, `SIGMAS` и начальный `LATENT` во внешние входы. Выход sampler можно подключить к VAE Decode или следующей latent-ветке. Frontend-режим изменения seed назначается отдельно; fragment сохраняет только число 42.

## Что именно проверено

Имена портов и типы сверены с `/object_info`. Полный census workflow templates 0.1.42 нашёл 79 `RandomNoise`, обычно перед `SamplerCustomAdvanced`. Exact-source проба подтвердила воспроизводимость, dtype, CPU и поведение `batch_index`.

Fragment не включает модель, guider и расписание, потому что их выбор зависит от pipeline. Полный sampling не запускался, workflow-файл не приложен.

## На что обратить внимание

Одинаковый seed воспроизводит шум только при той же форме и metadata. Повторяющиеся значения `batch_index` дают одинаковые шумовые элементы. Очень большой индекс заставляет генератор вычислить и отбросить промежуточные позиции.

