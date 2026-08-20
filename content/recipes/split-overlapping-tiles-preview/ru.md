# Нарезать IMAGE и показать порядок тайлов

SplitImageToTileList создаёт row-major список окон `1024 × 1024` с overlap 128. List-aware ImageGrid принимает этот список, уменьшает тайлы до ячеек `256 × 256` и показывает по четыре элемента в строке.

Коллаж нужен только для диагностики порядка и краевых окон. Он проходит через PIL RGB, поэтому не подключайте его к ImageMergeTileList вместо исходного list-output Split.

В официальном wheel 0.1.42 обе ноды этой топологии отсутствуют. Координаты проверены в чистой Python-модели формулы, list-флаги — по pinned runtime; fragment в ComfyUI не исполнялся. Редактор пока не проверил материал вручную.

## Источники

- [SplitImageToTileList в ComfyUI v0.32.0](https://github.com/Comfy-Org/ComfyUI/blob/c2bcbecd82ec5ae66594340b395c24ef0217b238/comfy_extras/nodes_images.py#L705-L764)
- [List-processing base для ImageGrid](https://github.com/Comfy-Org/ComfyUI/blob/c2bcbecd82ec5ae66594340b395c24ef0217b238/comfy_extras/nodes_dataset.py#L579-L741)
