# Join Image with Alpha: сборка RGBA из IMAGE и MASK

## Что делает нода

`JoinImageWithAlpha` объединяет цветное `IMAGE` и ComfyUI `MASK` в четырёхканальный RGBA. Первые три канала берутся из изображения, четвёртый вычисляется как `alpha = 1 − mask`.

Поэтому чёрная маска (`0`) делает область непрозрачной, а белая (`1`) — прозрачной. Это главное отличие от формулировки «маска как alpha», которая может создать обратное ожидание.

## Когда использовать

Нода нужна перед сохранением прозрачного PNG/WEBP, экспортом видео с alpha или передачей сегментированного объекта в потребителя RGBA. В официальных workflow она собирает прозрачный фон после segmentation и layer separation.

Для наложения source поверх destination используйте `ImageCompositeMasked` или `PorterDuffImageComposite`. Join только прикрепляет канал прозрачности; он не смешивает изображение с фоном.

## Входы

`image` — цветной `IMAGE`. Код использует только `image[..., :3]`: если вход уже RGBA, прежний alpha отбрасывается.

`alpha` — вход типа `MASK`, несмотря на имя порта. Значения интерпретируются как масочная прозрачность и инвертируются перед записью в RGBA.

Нормальный контракт — RGB/RGBA и MASK в диапазоне `0…1`.

## Выход

Выход — RGBA `IMAGE` с шириной и высотой цветного входа. Четвёртый канал равен инвертированной, при необходимости масштабированной маске.

Batch результата равен большему batch из `image` и `alpha`. Короткий вход повторяется циклически до этой длины через `repeat_to_batch_size`.

## Как работает

Маска переносится на устройство изображения и меняет размер до `(image.height, image.width)` через bilinear interpolation. Затем выполняется `1.0 − mask`.

Оба входа повторяются до общего batch. Из изображения берутся первые три канала, alpha получает дополнительную последнюю ось, после чего tensors объединяются через `torch.cat`.

Явного clamp нет. Корректная MASK в `0…1` даёт alpha в том же диапазоне; значения за пределами приведут к alpha за пределами нормы.

## Геометрия и batch

Spatial geometry всегда задаёт `image`. Маска другой пропорции не обрезается по центру — она растягивается bilinear до точной ширины и высоты, поэтому формы могут исказиться.

Batch повторяется по кругу, а не последним кадром. Например, image batch `[A, B]` и три маски дают цветовую последовательность `[A, B, A]`.

Если маска содержит один кадр, он применяется ко всему image batch. Это частый и удобный случай для общей прозрачности серии.

## Проверенные примеры

Найдено пять official workflow. `api_bria_remove_video_background_transparent` подаёт IMAGE и MASK из `BriaTransparentVideoBackground` в Join, затем сохраняет `SaveWEBM`. `utility_image_segment_sam3` соединяет исходный `LoadImage` с маской сегментации и показывает RGBA.

`api_bytedance_seedream_5_0_layer_separation` объединяет `BatchImagesNode` и `BatchMasksNode` перед `SaveImageAdvanced`. Beeble workflow инвертирует маску перед Join и сохраняет изображение. Wan alpha video соединяет `VAEDecode` и `InvertMask` перед `SaveAnimatedWEBP`.

Рецепт повторяет общий проверенный паттерн: внешний RGB и MASK → Join → PreviewImage. Формула, resize и batch repeat исполнены на синтетических tensors; полный fragment ещё не запускался в интерфейсе.

## Частые ошибки

**Прозрачность получилась обратной.** Помните: alpha channel равен `1 − MASK`. Если источник уже хранит непрозрачность, может понадобиться `InvertMask`.

**Старая прозрачность RGBA исчезла.** Join намеренно берёт только первые три канала input image и заменяет alpha новой маской.

**Маска деформировалась.** Нода растягивает её до геометрии image без сохранения пропорций. Подготовьте размеры заранее.

**Кадры маски сопоставились неожиданно.** Короткий batch повторяется циклически. Сведите batch к одинаковой длине или используйте один mask frame.

**Preview показывает клетчатый фон иначе, чем сохранённый файл.** Проверьте формат сохранения: не каждый output сохраняет alpha.

## Ограничения и производительность

Bilinear resize создаёт новый tensor маски, batch repeat может увеличить оба входа, а `torch.cat` выделяет полный RGBA output. Четвёртый канал увеличивает объём относительно RGB примерно на треть.

Нода не выполняет premultiplication RGB на alpha. Цвет под полностью прозрачными пикселями сохраняется и может проявиться при другом способе compositing.

## Совместимость, связанные ноды и источники

Статья сверена с ComfyUI `0.32.0`, модулем `comfy_extras.nodes_compositing`. Runtime fingerprint: `sha256:e2d42488a3b16098fed818a97e05d7e9ad2858ce98055e7daaaa8f0c03a14907`.

`SplitImageWithAlpha` выполняет обратное разделение, `InvertMask` меняет полярность, `ImageCompositeMasked` накладывает слой, `SaveImage` сохраняет output при поддержке alpha его кодеком.

- [Реализация `JoinImageWithAlpha`](https://github.com/Comfy-Org/ComfyUI/blob/c2bcbecd82ec5ae66594340b395c24ef0217b238/comfy_extras/nodes_compositing.py#L188-L209)
- [Официальные workflow templates JSON 0.1.42](https://pypi.org/project/comfyui-workflow-templates-json/0.1.42/)
- [Встроенная документация](https://github.com/Comfy-Org/embedded-docs/blob/main/comfyui_embedded_docs/docs/JoinImageWithAlpha/en.md)
