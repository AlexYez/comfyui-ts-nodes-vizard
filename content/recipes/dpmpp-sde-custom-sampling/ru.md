# DPM++ SDE с r 0,5 для SamplerCustomAdvanced

Fragment создаёт `SamplerDPMPP_SDE` с `eta = 1`, `s_noise = 1`, `r = 0,5`, `noise_device = gpu`. Выход подключён к `SamplerCustomAdvanced.sampler`; NOISE, GUIDER, SIGMAS и LATENT подаются снаружи.

Значение `r = 0,5` взято из exact default. Runtime разрешает ноль, но алгоритм делит на `2r`, поэтому fragment намеренно не использует нижнюю границу. Официального workflow case в 0.1.42 нет; fragment не исполнялся.
