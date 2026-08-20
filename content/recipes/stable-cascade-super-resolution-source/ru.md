# Проверить входы experimental Stable Cascade super-resolution

Fragment содержит только `StableCascade_SuperResolutionControlnet` и её обязательные входы `IMAGE` и `VAE`. Он нужен для изучения контракта ноды, а не как готовый super-resolution workflow.

Нода отдаёт `controlnet_input`, `stage_c` и `stage_b`. Первый выход объявлен как `IMAGE`, но реализация помещает туда результат `vae.encode`, переставленный из NCHW в NHWC. Это не обычные RGB-пиксели; подключайте его лишь туда, где такой закодированный hint ожидается явно.

В полном рекурсивном просмотре 512 JSON из workflow wheel 0.1.42 точных экземпляров ноды нет. В шести официальных Stable Cascade PNG из `ComfyUI_examples` её также нет. Поэтому fragment не добавляет выдуманные loader, ControlNetApply или sampler.

Безопасная проба подтвердила удаление альфа-канала, перестановку осей результата VAE и формы двух нулевых latent. Реальные VAE, ControlNet и sampling не запускались; редактор ещё не утверждал материал вручную.

## Источники

- [Реализация experimental-ноды](https://github.com/Comfy-Org/ComfyUI/blob/c2bcbecd82ec5ae66594340b395c24ef0217b238/comfy_extras/nodes_stable_cascade.py#L117-L148)
- [Официальные Stable Cascade examples](https://github.com/comfyanonymous/ComfyUI_examples/tree/f9431bb000ce792094ff345446e22cac1ea6cef3/stable_cascade)
