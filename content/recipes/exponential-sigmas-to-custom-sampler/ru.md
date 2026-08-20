# Передать exponential SIGMAS в custom sampler

Fragment оставляет стандартные 20 шагов и положительные границы 14,614642–0,0291675. `ExponentialScheduler.SIGMAS` подключён к `SamplerCustomAdvanced.sigmas`, а модельная часть остаётся внешней.

Не ставьте ноль в `sigma_min` или `sigma_max`: UI его допускает, но `math.log(0)` завершает выполнение ошибкой. Диапазон также нужно сверить с моделью внутри guider.

Официальных вхождений `ExponentialScheduler` в wheel 0.1.42 нет. Fragment проверен по runtime-схеме и точной функции без модели; полный sampling и ручная редакторская проверка не выполнялись.

## Источники

- [ExponentialScheduler в ComfyUI v0.32.0](https://github.com/Comfy-Org/ComfyUI/blob/c2bcbecd82ec5ae66594340b395c24ef0217b238/comfy_extras/nodes_custom_sampler.py#L69-L88)
- [Экспоненциальная формула](https://github.com/Comfy-Org/ComfyUI/blob/c2bcbecd82ec5ae66594340b395c24ef0217b238/comfy/k_diffusion/sampling.py#L19-L35)
