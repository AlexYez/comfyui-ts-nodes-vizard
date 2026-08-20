# Playground 2.5: EDM sampling и latent format

Fragment ставит режим `edm_playground_v2.5`, диапазон sigma 0,002–80 и ведёт patched модель в `BasicScheduler`. Эти значения совпадают с detection-ветвью Playground 2.5 в ComfyUI 0.32.0.

## Подключение

Используйте только подходящий SDXL Playground 2.5 `MODEL`. Выход patch подключите также к guider. Нода меняет latent format, поэтому VAE и весь latent pipeline должны относиться к тому же семейству.

## Настройки

Не задавайте `sigma_min = 0`: runtime-схема разрешает ноль, но реализация вызывает `log(0)` и падает. Всегда сохраняйте `0 < sigma_min < sigma_max`.

## Границы проверки

Exact patch, классы, `sigma_data = 0,5`, latent-format branch и 1000 sigma проверены без весов. В официальном workflow wheel прямого случая ноды нет; полный Playground sampling не выполнялся. Редактор пока не проверил материал вручную.

## Источники

- [ModelSamplingContinuousEDM в ComfyUI v0.32.0](https://github.com/Comfy-Org/ComfyUI/blob/c2bcbecd82ec5ae66594340b395c24ef0217b238/comfy_extras/nodes_model_advanced.py#L197-L240)
- [Распознавание Playground 2.5](https://github.com/Comfy-Org/ComfyUI/blob/c2bcbecd82ec5ae66594340b395c24ef0217b238/comfy/supported_models.py#L211-L232)
