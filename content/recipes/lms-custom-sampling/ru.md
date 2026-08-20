# Подключить LMS order 4 к custom sampling

Fragment передаёт `SamplerLMS.SAMPLER` во вход `sampler` у `SamplerCustomAdvanced`. `order = 4` — runtime default; фактический порядок растёт вместе с доступной историей производных и не превышает это значение.

Подайте внешние `NOISE`, `GUIDER`, `SIGMAS` и `LATENT`. Проверьте убывание sigma и terminal zero: LMS вычисляет коэффициенты по реальным точкам расписания, а на переходе к нулю возвращает denoised напрямую.

Exact-ноды и выбора `lms` у `KSamplerSelect` нет в official wheel 0.1.42. Wrapper исполнен с подставной фабрикой, но полный численный sampling не запускался. Редактор пока не проверил материал вручную.

## Источники

- [SamplerLMS](https://github.com/Comfy-Org/ComfyUI/blob/c2bcbecd82ec5ae66594340b395c24ef0217b238/comfy_extras/nodes_custom_sampler.py#L537-L552)
- [Linear Multistep implementation](https://github.com/Comfy-Org/ComfyUI/blob/c2bcbecd82ec5ae66594340b395c24ef0217b238/comfy/k_diffusion/sampling.py#L406-L440)
