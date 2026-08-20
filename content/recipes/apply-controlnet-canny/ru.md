# Подключить Canny ControlNet с полным диапазоном

Выберите ControlNet, совместимый с базовой MODEL, и подайте заранее рассчитанную Canny-карту в `image`. Positive и negative проходят через одну `ControlNetApplyAdvanced`; VAE подключается к optional-порту.

Значения 0,66 / 0 / 1 повторяют ноду № 51 из официального SD3.5 Canny workflow. Они не являются универсальным пресетом для другой архитектуры или другого изображения.

Fragment оставляет checkpoint, text conditioning, preprocessor и sampler внешними. Он прошёл проверку схемы и pinned topology, но реальный ControlNet не загружался и граф в ComfyUI не исполнялся. Редактор пока не проверил материал вручную.

## Источники

- [ControlNetApplyAdvanced в ComfyUI v0.32.0](https://github.com/Comfy-Org/ComfyUI/blob/c2bcbecd82ec5ae66594340b395c24ef0217b238/nodes.py#L928-L976)
- [Официальный SD3.5 Canny workflow](https://github.com/Comfy-Org/workflow_templates/blob/cca1ea5ea4560108ecc2f44dee951f41ea433062/templates/sd3.5_large_canny_controlnet_example.json)
