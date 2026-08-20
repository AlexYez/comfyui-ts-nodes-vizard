# Advanced custom sampling с Euler

Fragment соединяет `KSamplerSelect(sampler_name = euler)` с `SamplerCustomAdvanced`. NOISE, GUIDER, SIGMAS и LATENT оставлены внешними: их выбор зависит от модели и задачи.

## Подключение

Подайте воспроизводимый `RandomNoise` или нулевой `DisableNoise`, guider с нужной моделью и conditioning, совместимое расписание SIGMAS и начальный LATENT. Выход `output` подходит для обычного decode; `denoised_output` нужен только когда downstream осознанно использует последнее `x0`.

## Что проверено

Порты и типы сверены с `/object_info`. Полный scan официальных шаблонов нашёл 97 `KSamplerSelect` и 87 `SamplerCustomAdvanced`; Euler был самым частым выбором. Exact-source проба проверяет фабрику sampler и передачу компонентов, но не запускает модель.

## На что обратить внимание

Типы портов не гарантируют модельную совместимость. Scheduler, GUIDER и LATENT должны относиться к одному pipeline. Пустой SIGMAS вернёт исходный latent, а не выполнит полезный sampling.
