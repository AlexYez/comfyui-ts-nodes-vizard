# SD3 2B: смешать joint_blocks.23 и final_layer

Подключите две модели одной точной архитектуры SD3 2B. `joint_blocks.23. = 0,8` задаёт 80% `model1` и 20% `model2`; `final_layer. = 0,1` — 10% первой и 90% второй. Остальные 28 коэффициентов используют значение 1.

Это учебная проверка точных префиксов и направления коэффициента. Она не подтверждает художественную пользу выбранных значений и не подходит для SD3.5 или модели другого размера. До сэмплирования сравните формы и остановитесь при `WARNING SHAPE MISMATCH`.

В официальном пакете шаблонов 0.1.42 `ModelMergeSD3_2B` отсутствует. Фрагмент основан на исходном коде, не включает загрузчики, данные кондиционирования, сэмплер, VAE или сохранение и полностью не исполнялся. Редактор пока не проверил материал вручную.

## Источники

- [ModelMergeSD3_2B](https://github.com/Comfy-Org/ComfyUI/blob/c2bcbecd82ec5ae66594340b395c24ef0217b238/comfy_extras/nodes_model_merging_model_specific.py#L55-L76)
- [Общий алгоритм смешивания](https://github.com/Comfy-Org/ComfyUI/blob/c2bcbecd82ec5ae66594340b395c24ef0217b238/comfy_extras/nodes_model_merging.py#L138-L168)
- [Обработка несовпадающих форм](https://github.com/Comfy-Org/ComfyUI/blob/c2bcbecd82ec5ae66594340b395c24ef0217b238/comfy/lora.py#L438-L501)
- [Официальные шаблоны 0.1.42](https://github.com/Comfy-Org/workflow_templates/tree/cca1ea5ea4560108ecc2f44dee951f41ea433062/templates)
