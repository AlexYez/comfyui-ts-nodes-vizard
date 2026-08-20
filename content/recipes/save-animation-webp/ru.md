# Сохранить RGBA-анимацию в lossless WebP с 16 FPS

Подайте готовый IMAGE-бэтч в SaveAnimatedWEBP. Настройки повторяют включённую output-ноду № 80 из `video_wan2.1_alpha_t2v_14B`: 16 FPS, lossless, quality 80, method default.

Helper квантует tensor до 8 бит, затем записывает один файл. При 16 FPS duration равна 62 мс из-за целочисленного `int(1000 / fps)`.

Локальная Pillow-проверка записала и перечитала три RGBA-кадра; alpha и частичная прозрачность сохранились, но RGB у полностью прозрачного пикселя не гарантируется. Fragment в ComfyUI не исполнялся, metadata не проверялась. Редактор пока не проверил материал вручную.

## Источники

- [SaveAnimatedWEBP в ComfyUI v0.32.0](https://github.com/Comfy-Org/ComfyUI/blob/c2bcbecd82ec5ae66594340b395c24ef0217b238/comfy_extras/nodes_images.py#L197-L232)
- [Официальный alpha-video workflow](https://github.com/Comfy-Org/workflow_templates/blob/cca1ea5ea4560108ecc2f44dee951f41ea433062/templates/video_wan2.1_alpha_t2v_14B.json)
