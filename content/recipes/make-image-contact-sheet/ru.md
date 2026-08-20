# Собрать два IMAGE в сетку 2 × 1

Два внешних IMAGE сначала образуют бэтч. ImageGrid распрямляет его на два элемента, растягивает каждый до `256 × 256` и размещает в одной строке с промежутком 4 пикселя. Итоговый холст имеет размер `516 × 256`.

Это диагностический коллаж, а не обратимое преобразование: ImageGrid использует 8-битный PIL RGB и не сохраняет alpha. Квадратные ячейки также могут исказить исходное соотношение сторон.

В workflow wheel 0.1.42 ImageGrid отсутствует, поэтому fragment помечен как source-derived. Формула холста и 8-битное округление проверены в чистой Python-модели; PIL и сама нода не запускались. Fragment в ComfyUI не исполнялся. Редактор пока не проверил материал вручную.

## Источники

- [BatchImagesNode в ComfyUI v0.32.0](https://github.com/Comfy-Org/ComfyUI/blob/c2bcbecd82ec5ae66594340b395c24ef0217b238/comfy_extras/nodes_post_processing.py#L514-L588)
- [ImageGridNode в ComfyUI v0.32.0](https://github.com/Comfy-Org/ComfyUI/blob/c2bcbecd82ec5ae66594340b395c24ef0217b238/comfy_extras/nodes_dataset.py#L1628-L1699)
