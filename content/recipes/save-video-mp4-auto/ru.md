# Сохранить VIDEO с автоматическими настройками

Подключите готовый `VIDEO` ко входу `SaveVideo`. В v0.32.0 `format = auto` всё равно создаёт файл `.mp4`, а `codec = auto` позволяет файловому объекту попытаться перенести совместимые потоки без повторного сжатия.

Если muxer сообщает о несовместимом потоке, выберите `codec = h264`, затем `encoding = re-encode` и задайте CRF. Это уже другой режим: видеоряд будет сжат заново.

Фрагмент не создаёт исходный `VIDEO` и не является полным workflow. В официальном шаблоне SeedVR2 такая `SaveVideo` получает объект из подграфа после `CreateVideo`.

Редактор пока не проверил материал вручную.

### Источники

- [SaveVideo в ComfyUI v0.32.0](https://github.com/Comfy-Org/ComfyUI/blob/c2bcbecd82ec5ae66594340b395c24ef0217b238/comfy_extras/nodes_video.py#L75-L149)
- [Официальный SeedVR2 workflow](https://github.com/Comfy-Org/workflow_templates/blob/cca1ea5ea4560108ecc2f44dee951f41ea433062/templates/utility_seedvr2_3b_int8_upscale_video.json)
