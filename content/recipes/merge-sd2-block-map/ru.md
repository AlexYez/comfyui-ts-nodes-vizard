# SD2: сохранить общий коэффициент и смешать последний выходной блок

Подключите два проверенных SD2 `MODEL`. При обычном порядке входов `time_embed. = 1` сохраняет соответствующие и все несопоставленные ключи `diffusion_model.` из `model1`: общий алгоритм использует первый фактически переданный коэффициент, а prompt ComfyUI сохраняет объявленный порядок. `output_blocks.11. = 0,25` задаёт для этой группы 25% первой и 75% второй модели.

`ModelMergeSD2` имеет отдельный идентификатор типа, но в ComfyUI v0.32.0 использует класс `ModelMergeSD1` и ту же карту из 30 коэффициентов. Это не разрешение смешивать SD1 с SD2: входные checkpoint должны принадлежать одной совместимой архитектуре.

Официального шаблона и страницы SD2 во встроенной документации закреплённых версий нет. Фрагмент основан на исходном коде, не включает сэмплирование или сохранение и полностью не исполнялся. При `WARNING SHAPE MISMATCH` остановите проверку. Редактор пока не проверил материал вручную.

## Источники

- [Регистрация ModelMergeSD2](https://github.com/Comfy-Org/ComfyUI/blob/c2bcbecd82ec5ae66594340b395c24ef0217b238/comfy_extras/nodes_model_merging_model_specific.py#L370-L374)
- [Общая карта SD1/SD2](https://github.com/Comfy-Org/ComfyUI/blob/c2bcbecd82ec5ae66594340b395c24ef0217b238/comfy_extras/nodes_model_merging_model_specific.py#L3-L26)
- [Общий алгоритм смешивания](https://github.com/Comfy-Org/ComfyUI/blob/c2bcbecd82ec5ae66594340b395c24ef0217b238/comfy_extras/nodes_model_merging.py#L138-L168)
- [Передача входов prompt в порядке JSON](https://github.com/Comfy-Org/ComfyUI/blob/c2bcbecd82ec5ae66594340b395c24ef0217b238/execution.py#L159-L306)
- [Обработка несовпадающих форм](https://github.com/Comfy-Org/ComfyUI/blob/c2bcbecd82ec5ae66594340b395c24ef0217b238/comfy/lora.py#L438-L501)
- [Официальные шаблоны 0.1.42](https://github.com/Comfy-Org/workflow_templates/tree/cca1ea5ea4560108ecc2f44dee951f41ea433062/templates)
- [Дерево встроенной документации 0.5.9](https://github.com/Comfy-Org/embedded-docs/tree/1d258cf6e374d60d138a2bfcd273c7e11f750ef9/comfyui_embedded_docs/docs)
