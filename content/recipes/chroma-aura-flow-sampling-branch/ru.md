# Chroma: один AuraFlow MODEL для guider и scheduler

В официальном `image_chroma_text_to_image` выход `ModelSamplingAuraFlow(shift = 1)` разветвляется в `CFGGuider(cfg = 3,5)` и `BasicScheduler(beta, 26, 1)`. Фрагмент сохраняет эти ноды, значения и две связи.

`MODEL`, positive и negative conditioning остаются внешними. `SamplerCustomAdvanced`, noise, sampler и latent не включены, поэтому фрагмент сам по себе не запускает генерацию.

Не переносите shift 1 и beta/26 на другую модель только из-за этого примера: в том же wheel AuraFlow-нода встречается со значениями 3, 3,1 и другими. Веса Chroma и полный граф не исполнялись. Редактор пока не проверил материал вручную.

## Источники

- [ModelSamplingAuraFlow](https://github.com/Comfy-Org/ComfyUI/blob/c2bcbecd82ec5ae66594340b395c24ef0217b238/comfy_extras/nodes_model_advanced.py#L148-L160)
- [Граф Chroma](https://github.com/Comfy-Org/workflow_templates/blob/cca1ea5ea4560108ecc2f44dee951f41ea433062/templates/image_chroma_text_to_image.json)
