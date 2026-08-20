# DPM++ 3M SDE для SamplerCustomAdvanced

Fragment создаёт `SamplerDPMPP_3M_SDE` с `eta = 1`, `s_noise = 1`, `noise_device = gpu` и подключает его к `SamplerCustomAdvanced.sampler`. NOISE, GUIDER, SIGMAS и LATENT приходят извне.

В official workflow bundle 0.1.42 эта специализированная нода не встречается. Числовые значения совпадают с exact defaults, а `gpu` выбран явно из runtime options; это не исполненный модельный пример. Fragment прошёл schema/runtime port check, но не импортировался и не выполнялся.
