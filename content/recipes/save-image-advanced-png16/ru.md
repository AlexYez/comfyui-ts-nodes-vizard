# Сохранить IMAGE как 16-bit PNG

Подайте RGB/RGBA IMAGE-бэтч в SaveImageAdvanced и выберите format `png`, bit depth `16-bit`, input color space `sRGB`. Каждый элемент станет отдельным файлом со счётчиком.

Значения ограничиваются 0–1 и переводятся в диапазон 0–65535. Это не EXR: отрицательный и сверхединичный range не сохраняется.

Все 20 официальных случаев используют PNG 8-bit, поэтому fragment source-derived. PyAV в рабочем Python отсутствует: metadata/transform helpers проверены, но RGB/RGBA 16-bit encoder и fragment не исполнялись. Редактор пока не проверил материал вручную.

## Источник

- [SaveImageAdvanced в ComfyUI v0.32.0](https://github.com/Comfy-Org/ComfyUI/blob/c2bcbecd82ec5ae66594340b395c24ef0217b238/comfy_extras/nodes_images.py#L842-L1238)
