# Сохранить RGBA-бэтч как APNG с 12 FPS

Подайте IMAGE-бэтч в SaveAnimatedPNG. Нода создаст один `.png` с несколькими кадрами; `compress_level = 4` влияет на DEFLATE, но не делает изображение lossy.

При 12 FPS helper передаёт Pillow duration 83 мс. Выход `images` остаётся исходным бэтчем и идёт в PreviewImage, а не перечитывает APNG.

В wheel 0.1.42 SaveAnimatedPNG отсутствует. Локальный тест успешно записал и прочитал три RGBA-кадра, но fragment в ComfyUI не исполнялся. Редактор пока не проверил материал вручную.

## Источники

- [SaveAnimatedPNG в ComfyUI v0.32.0](https://github.com/Comfy-Org/ComfyUI/blob/c2bcbecd82ec5ae66594340b395c24ef0217b238/comfy_extras/nodes_images.py#L236-L267)
- [APNG helper](https://github.com/Comfy-Org/ComfyUI/blob/c2bcbecd82ec5ae66594340b395c24ef0217b238/comfy_api/latest/_ui.py#L76-L235)
