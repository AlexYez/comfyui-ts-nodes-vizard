# Подключить Karras SIGMAS к custom sampler

Fragment использует runtime defaults: 20 шагов, `sigma_max = 14,614642`, `sigma_min = 0,0291675`, `rho = 7`. Выход scheduler подключён к `SamplerCustomAdvanced.sigmas`; остальные sampling-входы нужно подать извне.

У `KarrasScheduler` нет `MODEL`, поэтому числа не подстраиваются под модель внутри guider. Проверьте диапазон для своей sampling-конфигурации, прежде чем запускать длинную очередь.

В wheel 0.1.42 exact type `KarrasScheduler` отсутствует. Fragment основан на pinned source и прошёл точный вычислительный probe без модели; полный sampling и ручная редакторская проверка не выполнялись.

## Источники

- [KarrasScheduler в ComfyUI v0.32.0](https://github.com/Comfy-Org/ComfyUI/blob/c2bcbecd82ec5ae66594340b395c24ef0217b238/comfy_extras/nodes_custom_sampler.py#L47-L67)
- [Формула Karras](https://github.com/Comfy-Org/ComfyUI/blob/c2bcbecd82ec5ae66594340b395c24ef0217b238/comfy/k_diffusion/sampling.py#L19-L29)
