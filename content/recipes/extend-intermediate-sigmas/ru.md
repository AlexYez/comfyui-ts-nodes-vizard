# Добавить линейные точки в верхнюю часть SIGMAS

Подайте проверенное `SIGMAS` во вход `ExtendIntermediateSigmas`. Настройки `steps = 2`, `start_at_sigma = −1`, `end_at_sigma = 12`, `spacing = linear` вставят одну точку в каждую пару, где текущая sigma не ниже 12.

Выход подключён к `SamplerCustomAdvanced.sigmas`; остальные входы sampling остаются внешними. Учтите, что следующая sigma не участвует в проверке границы, а output для CPU-входа пересобирается как CPU `float32`.

В official wheel 0.1.42 exact-ноды нет. Метод проверен на синтетических tensors, но весь sampling fragment не исполнялся. Редактор пока не проверил материал вручную.

## Источники

- [ExtendIntermediateSigmas](https://github.com/Comfy-Org/ComfyUI/blob/c2bcbecd82ec5ae66594340b395c24ef0217b238/comfy_extras/nodes_custom_sampler.py#L297-L348)
