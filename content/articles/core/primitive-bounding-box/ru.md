# Bounding Box: прямоугольник типа BOUNDING_BOX

Нода с карточкой `Bounding Box` собирает четыре числа — `x`, `y`, `width`, `height` — в значение типа `BOUNDING_BOX`. Она описывает прямоугольник, но сама не получает IMAGE, не рисует рамку и не вырезает пиксели.

## Runtime-имя — PrimitiveBoundingBox

В Python исходник называет класс `BoundingBox`, а runtime schema регистрирует `node_id="PrimitiveBoundingBox"`. Именно `PrimitiveBoundingBox` хранится в `class_type` workflow и используется для точной связи статьи с установленной нодой. `Bounding Box` — только display name.

В object_info ComfyUI 0.32.0 отдельного типа `BoundingBox` нет. Поиск и диагностика должны различать имя Python-класса, runtime node ID и подпись карточки.

## Выход — словарь из четырёх полей

`execute` возвращает структуру `{"x": x, "y": y, "width": width, "height": height}` через один порт `BOUNDING_BOX`. Пикселей, маски и второго выхода в ней нет.

Типизированный сокет не позволяет напрямую подключить этот результат к IMAGE или MASK. Потребитель должен объявлять вход `BOUNDING_BOX` и понимать четыре поля.

## x и y задают начало прямоугольника

Для ImageCropV2 поля `x` и `y` становятся началом тензорного среза: `x` отсчитывается вправо, `y` — вниз. Точка `(0, 0)` соответствует левому верхнему пикселю изображения.

Сам PrimitiveBoundingBox не знает, какой потребитель получит структуру. Интерпретация подтверждена source-level соседом ImageCropV2 и embedded docs, а не вычислением внутри primitive-ноды.

## width и height задают протяжённость

`width` — число столбцов от `x`, `height` — число строк от `y`. Для прямоугольника `x = 100`, `y = 50`, `width = 320`, `height = 240` ImageCropV2 строит срез по X до 420 и по Y до 290, не включая правую и нижнюю границы.

Это размеры области, а не координаты правого нижнего угла. Если передать вместо width значение `x + width`, область получится шире задуманной.

## Диапазоны runtime доходят до 16 384

`x` и `y` принимают целые значения от 0 до 16 384. `width` и `height` — от 1 до 16 384; их значения по умолчанию равны 512.

Embedded docs 0.5.9 указывают верхнюю границу 8192, но pinned source и runtime object_info для ComfyUI 0.32.0 показывают 16 384. Статья следует установленному контракту, а расхождение документации зафиксировано в research record.

## Нода не сверяется с размером IMAGE

У PrimitiveBoundingBox нет входа изображения, поэтому она не может узнать его ширину и высоту. Значения `x = 5000`, `width = 1000` проходят схему даже для IMAGE шириной 512.

Граница виджета — общий `MAX_RESOLUTION`, а не размер конкретного кадра. Проверка или обрезка области происходит только у следующей ноды и зависит от её реализации.

## ImageCropV2 ограничивает начало и обрезает конец срезом

ImageCropV2 прижимает `x` к `image.shape[2] − 1`, а `y` — к `image.shape[1] − 1`. Затем вычисляет `to_x = x + width`, `to_y = y + height` и берёт обычный тензорный срез.

Если прямоугольник выходит за правый или нижний край, Python-срез возвращает только доступные пиксели. Он не дополняет область и не растягивает изображение. Из-за слишком большого x или y результат может сузиться до последнего столбца или строки.

Runtime inventory содержит входы BOUNDING_BOX у `SDPoseKeypointExtractor`, `CropByBBoxes`, `DrawBBoxes` и `SAM3_Detect`. Совпадение типа разрешает соединение, но не гарантирует одинаковую работу с одной структурой или списком областей.

Перед подключением проверяйте контракт потребителя: некоторые ноды ожидают набор bounding boxes, выполняют detection или рисуют рамки. Эта статья описывает ровно одиночный словарь PrimitiveBoundingBox и подтверждённого соседа ImageCropV2.

## В официальном wheel нода не встречается

Exhaustive scan 496 workflow JSON версии 0.1.42 не нашёл ни `PrimitiveBoundingBox`, ни несуществующий runtime type `BoundingBox`. Нода `CreateBoundingBoxes` встречается отдельно, но это другой class type и другой контракт.

Нулевое число официальных примеров — значимый результат, а не повод приписывать ноде чужой workflow. Поэтому статья опирается на source, object_info и embedded docs; research ledger оставляет officialCasesInspected истинным именно для полного zero-occurrence scan.

## Fragment основан на source-level совместимости

Рецепт «Обрезать IMAGE по явному bounding box» соединяет PrimitiveBoundingBox с `crop_region` ImageCropV2 и подаёт внешний IMAGE в сам crop. Координаты `64, 64`, размер `512 × 512` выбраны как нейтральный редактируемый пример, а не взяты из официального шаблона.

Fragment честно помечен source-derived и не выдаётся за official-template topology. Схема соединения проверяется по runtime-портам; живое исполнение и человеческое утверждение пока не проводились.

## Если crop оказался не там или не того размера

Не путайте `width` с правой координатой, а `height` — с нижней. Сначала проверьте x и y, затем убедитесь, что `x + width` и `y + height` укладываются в нужный IMAGE.

Если провод не подключается, сравните точный тип сокета: нужен `BOUNDING_BOX`, а не MASK, IMAGE или JSON. Если нода не находится по имени `BoundingBox`, ищите display name в меню либо runtime ID `PrimitiveBoundingBox` в сохранённом графе.

## Источники

- [PrimitiveBoundingBox в ComfyUI v0.32.0](https://github.com/Comfy-Org/ComfyUI/blob/c2bcbecd82ec5ae66594340b395c24ef0217b238/comfy_extras/nodes_images.py#L92-L110)
- [ImageCropV2 как BOUNDING_BOX-потребитель](https://github.com/Comfy-Org/ComfyUI/blob/c2bcbecd82ec5ae66594340b395c24ef0217b238/comfy_extras/nodes_images.py#L59-L90)
- [Embedded docs 0.5.9 для PrimitiveBoundingBox](https://github.com/Comfy-Org/embedded-docs/blob/1d258cf6e374d60d138a2bfcd273c7e11f750ef9/comfyui_embedded_docs/docs/PrimitiveBoundingBox/en.md)
