# Save Animated PNG: сохранить IMAGE-бэтч как APNG

`SaveAnimatedPNG` записывает все элементы IMAGE-бэтча в один файл `.png` с несколькими кадрами. Это APNG, а не папка последовательных PNG и не video-контейнер с аудио.

## Бэтч определяет число кадров

Helper переводит каждый элемент первой оси IMAGE в Pillow Image. Первый вызывает `save_all=True`, остальные передаются через `append_images`.

При одном входном кадре получается обычный однокадровый PNG; UI считает результат animated только если элементов больше одного. Нода сама не создаёт промежуточные кадры.

## FPS задаёт общую duration

Для каждого кадра используется `int(1000.0 / fps)` миллисекунд. Диапазон runtime — 0.01–1000 FPS, default 6.

APNG получает одну duration для всей последовательности. Индивидуальные задержки кадров задать нельзя, а целочисленное округление может слегка изменить фактическую скорость.

## Путь преобразования остаётся 8-битным

Перед записью IMAGE умножается на 255, ограничивается 0–255 и переводится в `uint8`. RGB и RGBA поддерживаются Pillow; alpha сохраняется в RGBA APNG.

Значения HDR и точность выше 8 бит здесь теряются. Для одиночных 16-bit PNG предназначена отдельная ветка SaveImageAdvanced, а не SaveAnimatedPNG.

## compress_level меняет размер, а не пиксели

Параметр допускает 0–9, default 4 и помечен advanced. Он передаётся Pillow как PNG `compress_level`.

Большее значение обычно увеличивает время DEFLATE и уменьшает файл, но не делает PNG lossy. Оно не меняет FPS, глубину цвета и число кадров.

## Метаданные используют специальные comf chunks

Для APNG helper создаёт chunks типа `comf` после IDAT. Внутри сохраняются ключ, NUL и JSON prompt либо элементы `extra_pnginfo`.

Если metadata отключена, chunks не добавляются. Не все сторонние PNG-инструменты понимают ComfyUI `comf`, поэтому переносимость animation не равна переносимости workflow metadata.

## Нода возвращает исходный IMAGE

SaveAnimatedPNG — output node: выполнение создаёт файл и UI-result. Одновременно выход `images` передаёт тот же входной бэтч дальше по графу.

Passthrough не является повторным чтением APNG. Если нужно проверить именно записанный файл, загрузите его в следующем запуске через подходящую loader-ноду.

## APNG и animated WebP решают разные задачи

APNG сохраняет 8-битные пиксели без lossy-сжатия и управляет только compress level. WebP предлагает lossless/lossy, quality и method и часто даёт меньший файл.

Выбирайте APNG, когда важна PNG-совместимая без потерь последовательность; WebP — когда важнее размер и настраиваемое сжатие. Поддержка animation зависит от просмотрщика в обоих случаях.

## В официальном wheel примеров нет

Полный recursive scan 496 workflow-графов и всех subgraph не нашёл ни одного exact `SaveAnimatedPNG`. Поэтому нельзя приписать официальный FPS или compress level набору 0.1.42.

Recipe использует runtime defaults как исходную точку, но выбирает 12 FPS для наглядного самостоятельного fragment. Он явно source-derived.

## Локальная APNG-проверка сохранила RGBA

Безопасный тест создал три синтетических RGBA-кадра, записал их Pillow с `save_all`, duration и compress level, затем перечитал. Число кадров, размер и alpha совпали с ожидаемыми.

Проверка выполняет ту же encoding/save ветку helper на локальном временном файле, но не запускает ComfyUI node class, hidden metadata и UI-wrapper.

## Fragment сохраняет внешний RGBA-бэтч

Рецепт оставляет IMAGE внешним и задаёт 12 FPS, `compress_level = 4`. После ноды passthrough идёт в PreviewImage, чтобы показать, что граф может продолжаться.

Fragment прошёл схему, но в ComfyUI не исполнялся. Локальная проверка не заменяет тест реального output directory и metadata. Редактор пока не проверил материал вручную.

## Источники

- [SaveAnimatedPNG в ComfyUI v0.32.0](https://github.com/Comfy-Org/ComfyUI/blob/c2bcbecd82ec5ae66594340b395c24ef0217b238/comfy_extras/nodes_images.py#L236-L267)
- [Animated PNG helper](https://github.com/Comfy-Org/ComfyUI/blob/c2bcbecd82ec5ae66594340b395c24ef0217b238/comfy_api/latest/_ui.py#L76-L235)
- [Закреплённый набор workflow templates 0.1.42](https://github.com/Comfy-Org/workflow_templates/tree/cca1ea5ea4560108ecc2f44dee951f41ea433062/templates)
