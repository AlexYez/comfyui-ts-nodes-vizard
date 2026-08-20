# Wan с нативной таблицей OptimalSteps

Fragment выбирает `model_type = Wan`, двадцать шагов и полный denoise. Для Wan это нативная длина закреплённой таблицы: `OptimalStepsScheduler` не интерполирует её перед передачей в `SamplerCustomAdvanced`.

## Что подключить

Подайте `NOISE`, `GUIDER`, `SAMPLER` и `LATENT`. Guider должен использовать Wan-модель с подходящей sampling-конфигурацией. Scheduler не принимает `MODEL`, поэтому строка `Wan` не подтверждает архитектуру автоматически.

## Что проверить

Ожидается 21 значение `SIGMAS`, убывающий ряд и конечный ноль. Для FLUX нативная длина равна 10, для Chroma — 40; переносить двадцать шагов на эти варианты без учёта интерполяции нельзя.

## Границы примера

Прямых случаев `OptimalStepsScheduler` в official workflow templates 0.1.42 не найдено. Fragment составлен по source/runtime и проверен как типизированная связь; exact-расписание исполнено отдельно, но Wan-модель и полный sampling не запускались. Редактор пока не проверил материал вручную.

## Источники

- [OptimalStepsScheduler в ComfyUI v0.32.0](https://github.com/Comfy-Org/ComfyUI/blob/c2bcbecd82ec5ae66594340b395c24ef0217b238/comfy_extras/nodes_optimalsteps.py#L1-L59)
