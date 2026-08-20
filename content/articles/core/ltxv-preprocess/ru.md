# LTXVPreprocess: имитировать видеокомпрессию референсного IMAGE

## Что делает нода

`LTXVPreprocess` добавляет к IMAGE потери, характерные для видеокодека. Каждый элемент batch отдельно записывается в память как однокадровый MP4 с `libx264`, декодируется обратно в RGB и собирается в новый batch.

Параметр `img_compression` напрямую передаётся кодеку как CRF. Чем он выше, тем сильнее компрессия и заметнее артефакты. Значение `0` включает специальную ветвь без encode/decode.

Это не temporal video compression: кадры не видят соседей и обрабатываются независимыми однокадровыми контейнерами.

## Когда использовать и когда не использовать

Используйте preprocessing перед `LTXVImgToVideoInplace` или `LTXVAddGuide`, когда официальный LTX 2.x workflow предполагает референс с компрессионными потерями. Такая подготовка приближает чистое изображение к материалу, встречавшемуся при обучении video-модели.

Не применяйте ноду как обычный ресайзер, цветокорректор или средство уменьшения файла. На выходе остаётся tensor IMAGE, а временный MP4 живёт только в памяти.

Для точного сохранения пикселей выберите `0` или не добавляйте ноду. Если последующая ветвь требует альфа-канал, compressed path не подходит: кодек работает с RGB24.

## Короткий рецепт подключения

1. Подготовьте IMAGE нужного aspect ratio через resize/crop.
2. Подключите его к `LTXVPreprocess`.
3. Для первого теста возьмите официальный preset `18`, `25` или `33`.
4. Передайте `output_image` в `LTXVAddGuide` либо `LTXVImgToVideoInplace`.
5. Сравните результат с `img_compression = 0` на одном seed.

Рецепт Wizard использует два preprocessing-узла со значением `25`, как официальный style-transition subgraph, и направляет их в guides начала и конца клипа.

## Входы, выходы и параметры

`image` — batch формата IMAGE. В штатном случае это float tensor с RGB-каналами и значениями около `0…1`.

`img_compression` — INT от `0` до `100`, default `35`. Внутри это CRF, а не процент сохранённого качества: увеличение числа обычно ухудшает картинку.

`output_image` — новый IMAGE batch. В compressed path значения формируются из декодированного `uint8` RGB и делятся на `255`; dtype и device возвращаются к dtype/device входного кадра.

## Типовые связки

В workflow wheel 0.1.42 найдено 15 экземпляров в 12 файлах, все внутри subgraph и в mode `Always`. Значение `18` используется восемь раз, `25` — четыре, `33` — три. Runtime default `35` в этих шаблонах не встречается.

Чаще всего перед нодой стоит `ResizeImagesByLongerEdge` либо `ResizeImageMaskNode`. Выход подключается к `LTXVImgToVideoInplace`; в LTX 2.5 он также подаётся в `TextGenerateLTX2Prompt`.

В двухреференсном style-transition graph отдельный preprocess используется для начального и конечного изображения.

## Практический пример

В `video_ltx2_3_flf2v` `ResizeImageMaskNode` №124 и №125 готовят два изображения. `LTXVPreprocess` №104 и №99 обрабатывают их с CRF `25`, после чего изображения идут в две последовательные `LTXVAddGuide`: первая с `frame_idx = 0`, вторая с `frame_idx = -1`.

В `video_ltx2_3_i2v` preprocessing №289 использует `18` и разветвляется к двум `LTXVImgToVideoInplace` разных стадий. Это один подготовленный референс для latent до и после upscale.

Эти topology проверены напрямую в official wheel. Полный workflow с реальным кодеком и model weights в Wizard пока не исполнялся.

## Частые ошибки и проверка

**Размер стал на один пиксель меньше.** Перед H.264 encode код обрезает высоту и ширину вниз до чётных значений. Подготавливайте чётные dimensions заранее.

**CRF 100 выглядит хуже, а не лучше.** Поле названо «amount of compression»: высокий CRF означает более сильную потерю качества. Для bypass нужен ровно `0`.

**Ошибка codec/libx264.** Ветка `img_compression > 0` зависит от PyAV и доступного encoder `libx264`. Проверьте packaged environment ComfyUI; смена sampler или VAE эту ошибку не исправит.

**RGBA падает в compressed path.** Код передаёт четырёхканальный NumPy array в `VideoFrame.from_ndarray(..., format="rgb24")` без среза RGB; pinned PyAV отвечает `ValueError: Unexpected numpy array shape`. При CRF `0` codec path пропускается и четыре канала сохраняются. Для CRF выше нуля заранее подайте RGB, а alpha/mask ведите отдельно.

## Производительность и внутреннее поведение

Для каждого кадра создаётся отдельный MP4 container в `BytesIO`, отдельный H.264 stream с rate `1`, preset `veryfast` и yuv420p frame. Затем контейнер открывается снова и декодируется первый video frame.

Перед encode tensor умножается на `255`, переводится в `byte`, переносится на CPU и преобразуется в NumPy. После decode данные копируются обратно на исходный device. Большой batch увеличивает число codec initialization и CPU↔device transfers линейно.

При `img_compression = 0` codec path пропускается, но `execute` всё равно складывает кадры через `torch.stack`, поэтому возвращается новый batch tensor.

## Совместимость, изменения и устаревание

Статья проверена для ComfyUI `0.32.0`, frontend `1.48.7`, runtime ID `LTXVPreprocess` и модуля `comfy_extras.nodes_lt`. Fingerprint: `sha256:0343134bdc3eb505b9b6fe3e4cef2808a3e8fb8c04e5e046eb86f80773ae2606`.

Нода активна, не experimental и не deprecated; formal replacement отсутствует. Практическая совместимость compressed path зависит не только от schema, но и от PyAV/libx264 в установленной сборке.

Embedded docs 0.5.9 верно называют MP4 round-trip и zero bypass, но не объясняют отдельный encode каждого кадра, чётное crop, RGB-only path и стоимость transfers.

## Связанные ноды и источники

`ResizeImageMaskNode` задаёт геометрию до codec round-trip. `LTXVAddGuide` и `LTXVImgToVideoInplace` используют подготовленный IMAGE как референс; они сами выполняют дополнительный resize под latent/VAE.

- [Реализация `LTXVPreprocess`](https://github.com/Comfy-Org/ComfyUI/blob/c2bcbecd82ec5ae66594340b395c24ef0217b238/comfy_extras/nodes_lt.py#L677-L743)
- [Официальный LTX 2.3 style-transition template](https://github.com/Comfy-Org/workflow_templates/blob/cca1ea5ea4560108ecc2f44dee951f41ea433062/templates/video_ltx2_3_flf2v.json)
- [Официальный LTX 2.5 I2V template](https://github.com/Comfy-Org/workflow_templates/blob/cca1ea5ea4560108ecc2f44dee951f41ea433062/templates/video_ltx2_5_i2v.json)
- [Embedded docs 0.5.9](https://github.com/Comfy-Org/embedded-docs/blob/1d258cf6e374d60d138a2bfcd273c7e11f750ef9/comfyui_embedded_docs/docs/LTXVPreprocess/en.md)
