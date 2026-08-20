# DPM++ 2M SDE midpoint для SamplerCustomAdvanced

Fragment выставляет `solver_type = midpoint`, `eta = 1`, `s_noise = 1`, `noise_device = gpu` и передаёт выход `SAMPLER` в `SamplerCustomAdvanced`. Остальные sampling-компоненты внешние.

Официальный bundle 0.1.42 не содержит `SamplerDPMPP_2M_SDE`; это source-derived минимальная связка, а не проверенная рекомендация модели. Схема и типы соединений проверены. Fragment не импортировался и не выполнялся.
