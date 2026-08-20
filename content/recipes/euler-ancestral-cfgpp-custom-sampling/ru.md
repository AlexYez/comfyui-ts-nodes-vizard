# Подключить Euler ancestral CFG++ к custom sampling

Fragment создаёт `SamplerEulerAncestralCFGPP` с runtime defaults `eta = 1` и `s_noise = 1`, затем подаёт его выход во вход `sampler` у `SamplerCustomAdvanced`. `NOISE`, `GUIDER`, `SIGMAS` и `LATENT` нужно подключить извне.

Проверьте, что `SIGMAS` соответствуют модели внутри guider и заканчиваются нулём. `eta = 0` и `s_noise = 0` не взаимозаменяемы: первое меняет ancestral-разложение, второе только убирает добавляемый random tensor.

Exact-ноды нет в official wheel 0.1.42. Fragment подтверждён source/runtime и wrapper-probe, но полный CFG++ sampling не запускался. Редактор пока не проверил материал вручную.

## Источники

- [SamplerEulerAncestralCFGPP](https://github.com/Comfy-Org/ComfyUI/blob/c2bcbecd82ec5ae66594340b395c24ef0217b238/comfy_extras/nodes_custom_sampler.py#L514-L535)
- [Euler ancestral CFG++ algorithm](https://github.com/Comfy-Org/ComfyUI/blob/c2bcbecd82ec5ae66594340b395c24ef0217b238/comfy/k_diffusion/sampling.py#L1266-L1307)
