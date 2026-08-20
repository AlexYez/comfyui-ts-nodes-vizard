# SD1: проверить направление трёх коэффициентов блоков

Подайте два совместимых SD1 `MODEL` в `ModelMergeSD1`. Фрагмент меняет только три поля: `input_blocks.1. = 0,75`, `middle_block.1. = 0,5`, `output_blocks.11. = 0`. Остальные виджеты получают значение 1 по умолчанию.

Для одинаковых ключей это означает 75% `model1` в выбранном входном блоке, равную смесь в среднем блоке и 100% `model2` в выбранном выходном блоке. Проверьте консоль: при `WARNING SHAPE MISMATCH` результат нельзя считать корректным смешиванием.

Фрагмент не содержит загрузчиков, CLIP, VAE, сэмплера или сохранения checkpoint. В официальном пакете шаблонов 0.1.42 точного `ModelMergeSD1` нет; настройки основаны на исходном коде и предназначены для проверки семантики, а не как готовая художественная настройка. Полный пример не исполнялся. Редактор пока не проверил материал вручную.

## Источники

- [ModelMergeSD1](https://github.com/Comfy-Org/ComfyUI/blob/c2bcbecd82ec5ae66594340b395c24ef0217b238/comfy_extras/nodes_model_merging_model_specific.py#L3-L26)
- [Общий алгоритм смешивания](https://github.com/Comfy-Org/ComfyUI/blob/c2bcbecd82ec5ae66594340b395c24ef0217b238/comfy_extras/nodes_model_merging.py#L138-L168)
- [Обработка несовпадающих форм](https://github.com/Comfy-Org/ComfyUI/blob/c2bcbecd82ec5ae66594340b395c24ef0217b238/comfy/lora.py#L438-L501)
- [Официальные шаблоны 0.1.42](https://github.com/Comfy-Org/workflow_templates/tree/cca1ea5ea4560108ecc2f44dee951f41ea433062/templates)
