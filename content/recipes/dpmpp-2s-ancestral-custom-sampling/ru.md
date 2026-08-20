# DPM++ 2S ancestral для SamplerCustomAdvanced

Fragment выставляет `eta = 1`, `s_noise = 1` у `SamplerDPMPP_2S_Ancestral` и подключает `SAMPLER` к `SamplerCustomAdvanced`. Остальные компоненты custom sampling остаются внешними.

Настройки соответствуют exact defaults. В official workflow wheel 0.1.42 нода отсутствует, поэтому fragment не связывает sampler с вымышленной модельной рекомендацией. Schema и port contract проверены; импорт и выполнение не проводились.
