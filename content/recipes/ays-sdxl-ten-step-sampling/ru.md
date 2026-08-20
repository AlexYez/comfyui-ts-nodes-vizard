# SDXL с нативным AYS-расписанием

Fragment подключает `AlignYourStepsScheduler` к `SamplerCustomAdvanced`. Выбраны `SDXL`, десять шагов и `denoise = 1`: при этой длине используется исходная таблица из ComfyUI 0.32.0 без интерполяции.

## Что подключить

Подайте совместимые `NOISE`, `GUIDER`, `SAMPLER` и `LATENT` на внешние порты. Guider должен быть построен из SDXL-модели, sampling-шкала которой подходит выбранной таблице. Scheduler не получает `MODEL` и сам этого не проверяет.

## Что проверить

До запуска убедитесь, что `SIGMAS` содержат одиннадцать значений, идут по убыванию и заканчиваются нулём. Если используется model sampling patch, примените его к модели guider и отдельно проверьте, остаётся ли AYS-таблица уместной.

## Границы примера

Полный scan официальных workflow templates 0.1.42 не нашёл `AlignYourStepsScheduler`. Этот fragment собран из точной runtime-схемы и исходника; его расписание проверено отдельно, но модель, sampler и полный граф не запускались. Редактор пока не проверил материал вручную.

## Источники

- [AlignYourStepsScheduler в ComfyUI v0.32.0](https://github.com/Comfy-Org/ComfyUI/blob/c2bcbecd82ec5ae66594340b395c24ef0217b238/comfy_extras/nodes_align_your_steps.py#L1-L59)
