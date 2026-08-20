# BasicGuider перед SamplerCustomAdvanced

Подайте совместимые `MODEL` и `CONDITIONING` в `BasicGuider`. Fragment соединяет полученный `GUIDER` с `SamplerCustomAdvanced`; NOISE, SAMPLER, SIGMAS и LATENT приходят извне.

Такая связь подтверждена официальным `flux_redux_model_example`, UUID `06010f12-03bc-41ce-86bd-14f321d5a152`. Fragment не включает модель и не выполнялся; он проверяет только структуру и типы портов.
