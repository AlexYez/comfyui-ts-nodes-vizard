# SDXL: смешать три средних блока пополам

Фрагмент принимает два внешних SDXL `MODEL` и задаёт `middle_block.0 = 0,5`, `middle_block.1 = 0,5`, `middle_block.2 = 0,5`. У этих полей `/object_info` нет завершающей точки. Остальные коэффициенты остаются равными 1 и сохраняют соответствующие веса `model1`.

При совпадающих формах три средние группы получают равные доли моделей. Это проверка точных имён префиксов и направления коэффициента, а не универсальная рекомендация: базовую модель, refiner и другие варианты SDXL нельзя смешивать без сравнения словарей весов.

В официальных шаблонах 0.1.42 точный тип не встречается. Фрагмент не содержит загрузчиков, сэмплера, CLIP, VAE или сохранения и полностью не исполнялся. Любой `WARNING SHAPE MISMATCH` делает результат непригодным до разбора. Редактор пока не проверил материал вручную.

## Источники

- [ModelMergeSDXL](https://github.com/Comfy-Org/ComfyUI/blob/c2bcbecd82ec5ae66594340b395c24ef0217b238/comfy_extras/nodes_model_merging_model_specific.py#L29-L53)
- [Общий алгоритм смешивания](https://github.com/Comfy-Org/ComfyUI/blob/c2bcbecd82ec5ae66594340b395c24ef0217b238/comfy_extras/nodes_model_merging.py#L138-L168)
- [Обработка несовпадающих форм](https://github.com/Comfy-Org/ComfyUI/blob/c2bcbecd82ec5ae66594340b395c24ef0217b238/comfy/lora.py#L438-L501)
- [Официальные шаблоны 0.1.42](https://github.com/Comfy-Org/workflow_templates/tree/cca1ea5ea4560108ecc2f44dee951f41ea433062/templates)
