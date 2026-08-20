# LTXV: построить sampling по форме latent

Фрагмент подаёт внешний `MODEL` и задающий форму `LATENT` в `ModelSamplingLTXV(max_shift = 2,05; base_shift = 0,95)`. Изменённый `MODEL` затем входит в `BasicScheduler(simple, 20, 1)`.

Используйте latent той же формы `[..., T, H, W]`, которая пойдёт в sampler: нода вычисляет shift по произведению размеров после batch и channel. Значения `samples` не читаются.

В официальном wheel 0.1.42 `ModelSamplingLTXV` отсутствует. Эта связь следует только runtime/source-контракту; метод проверен на синтетических формах, но полный фрагмент и модель не запускались. Редактор пока не проверил материал вручную.

## Источники

- [ModelSamplingLTXV](https://github.com/Comfy-Org/ComfyUI/blob/c2bcbecd82ec5ae66594340b395c24ef0217b238/comfy_extras/nodes_lt.py#L567-L610)
- [BasicScheduler](https://github.com/Comfy-Org/ComfyUI/blob/c2bcbecd82ec5ae66594340b395c24ef0217b238/comfy_extras/nodes_custom_sampler.py#L17-L45)
