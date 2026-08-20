# Собрать Stable Cascade img2img через Stage C

Fragment воспроизводит sampling-ветвь официального image-to-image примера. Исходный `IMAGE` сначала проходит через `StableCascade_StageC_VAEEncode`. Закодированный `stage_c` меняется первым sampler, а пустой `stage_b` и готовый prior поступают во вторую стадию.

## Подключение

Подайте в `encode` изображение и VAE от checkpoint Stage C. Первый sampler получает модель Stage C, positive и negative. То же исходное positive conditioning подключите к `prepare_b`; второй sampler получает модель Stage B и negative той же текстовой ветви. После fragment декодируйте результат VAE из checkpoint Stage B.

## Настройки из официального примера

`compression` равен `32`. Stage C использует 20 шагов, CFG `4`, `euler_ancestral`, scheduler `simple` и denoise `0.6`; Stage B — 10 шагов, CFG `1.1` и denoise `1`. Оба seed перенесены из PNG, где их клиентская политика установлена на `randomize`.

## Границы проверки

Топология и widgets сверены по workflow-метаданным официального PNG. Безопасная проба выполнила resize, VAE-заглушку и построение обоих latent, но не sampling с настоящими весами. Ручное редакторское утверждение ещё не проведено.

## Источники

- [Официальный Stable Cascade image-to-image workflow](https://github.com/comfyanonymous/ComfyUI_examples/blob/f9431bb000ce792094ff345446e22cac1ea6cef3/stable_cascade/stable_cascade__image_to_image.png)
- [Реализация Stage C VAE encode](https://github.com/Comfy-Org/ComfyUI/blob/c2bcbecd82ec5ae66594340b395c24ef0217b238/comfy_extras/nodes_stable_cascade.py#L56-L88)
