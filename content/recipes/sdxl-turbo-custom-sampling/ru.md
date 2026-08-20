# SDXL Turbo: custom sampling в один шаг

Этот fragment переносит участок официального `sdxlturbo_example`: `KSamplerSelect(euler_ancestral)`, `SDTurboScheduler(steps = 1, denoise = 1)` и `SamplerCustom(add_noise = true, noise_seed = 0, cfg = 1)`.

## Подключение

Подайте одну и ту же SDXL Turbo `MODEL` в оба внешних входа модели: scheduler использует её для построения SIGMAS, а sampler — для denoising. Отдельно подключите совместимые positive/negative `CONDITIONING` и начальный `LATENT`. Основной выход sampler можно передать в VAE Decode.

## Что проверено

Имена портов, типы и значения сверены с `/object_info` ComfyUI 0.32.0. В официальном workflow ноды `KSamplerSelect #14`, `SDTurboScheduler #22` и `SamplerCustom #13` соединены именно так; widgets sampler равны `[true, 0, "fixed", 1]`.

Fragment не включает checkpoint, text encoders, VAE и сохранение изображения. Полный запуск модели не выполнялся, поэтому это проверенная структура, а не подтверждение конкретного визуального результата.

## На что обратить внимание

CFG 1 и один шаг относятся к SDXL Turbo. Не переносите их автоматически в обычный SDXL. Два внешних MODEL-входа нужно соединить с одним источником; они разделены только потому, что формат fragment описывает каждую точку подключения явно.
