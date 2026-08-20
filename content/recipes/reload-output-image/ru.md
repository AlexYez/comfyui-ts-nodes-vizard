# Загрузить сохранённый output и проверить прозрачность

Нажмите refresh у LoadImageOutput и выберите нужный файл вручную: первый пункт не обязательно самый новый. IMAGE идёт в один PreviewImage, MASK — через MaskToImage во второй.

Белая область второго preview соответствует прозрачности, потому что loader возвращает `1 − alpha`. У файла без alpha нулевая MASK может иметь служебный размер `64 × 64`.

В wheel 0.1.42 такого workflow нет. Fragment требует реального output-файла и в ComfyUI не исполнялся; редактор пока не проверил материал вручную.

## Источник

- [LoadImageOutput в ComfyUI v0.32.0](https://github.com/Comfy-Org/ComfyUI/blob/c2bcbecd82ec5ae66594340b395c24ef0217b238/nodes.py#L1734-L1880)
