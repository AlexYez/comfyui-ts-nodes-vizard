# Hunyuan Video: SD3 shift 7 перед BasicGuider

Фрагмент повторяет одну точную ветвь `hunyuan_video_text_to_video`: внешний `MODEL` проходит через `ModelSamplingSD3(shift = 7)`, а результат входит в `BasicGuider` вместе с внешним conditioning.

В официальном графе `BasicScheduler(simple, 20, 1)` получает отдельную связь прямо от `UNETLoader`, минуя патч. Эта ветвь scheduler и остальные входы `SamplerCustomAdvanced` намеренно не включены во фрагмент.

`shift = 7` подтверждён только для показанного графа Hunyuan Video. Метод патча и порты проверены на подставной модели, но веса и полный граф не запускались. Редактор пока не проверил материал вручную.

## Источники

- [ModelSamplingSD3](https://github.com/Comfy-Org/ComfyUI/blob/c2bcbecd82ec5ae66594340b395c24ef0217b238/comfy_extras/nodes_model_advanced.py#L119-L147)
- [Граф Hunyuan Video](https://github.com/Comfy-Org/workflow_templates/blob/cca1ea5ea4560108ecc2f44dee951f41ea433062/templates/hunyuan_video_text_to_video.json)
