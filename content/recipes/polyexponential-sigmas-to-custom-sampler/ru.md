# Подключить polyexponential SIGMAS к custom sampler

Fragment использует 20 шагов, стандартные положительные границы и `rho = 1`. В этом режиме кривая численно совпадает с exponential-расписанием в пределах погрешности `float32`.

Выход `SIGMAS` подключён к `SamplerCustomAdvanced`. `NOISE`, `GUIDER`, `SAMPLER` и `LATENT` подаются извне; границы должны соответствовать модели внутри guider.

В wheel 0.1.42 этой ноды нет. Точная функция проверена без моделей для `rho = 1`, `rho = 2` и граничных значений, но полный sampling и ручная редакторская проверка не выполнялись.

## Источники

- [PolyexponentialScheduler в ComfyUI v0.32.0](https://github.com/Comfy-Org/ComfyUI/blob/c2bcbecd82ec5ae66594340b395c24ef0217b238/comfy_extras/nodes_custom_sampler.py#L90-L110)
- [Polyexponential-формула](https://github.com/Comfy-Org/ComfyUI/blob/c2bcbecd82ec5ae66594340b395c24ef0217b238/comfy/k_diffusion/sampling.py#L19-L42)
