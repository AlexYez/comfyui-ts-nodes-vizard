# Save Image Advanced: PNG 8/16-bit и scene-linear EXR

`SaveImageAdvanced` сохраняет каждый элемент IMAGE-бэтча отдельным файлом и даёт две ветки формата: PNG с 8 или 16 битами и EXR с 32-bit float. Параметры `bit_depth` и `input_color_space` появляются внутри dynamic combo выбранного формата.

## PNG и EXR имеют разные наборы настроек

Для `png` доступны `8-bit` и `16-bit`, а `input_color_space` фиксирован как `sRGB`. Для `exr` доступен только `32-bit float`; вход можно объявить `sRGB`, `HDR` или `linear`.

Это зависимые параметры `COMFY_DYNAMICCOMBO_V3`, а не четыре независимых widget. Сериализованный workflow хранит выбранный format и значения его branch.

## PNG ограничивает значения и квантует

PNG-путь умножает tensor на 255 либо 65535, затем clamp до этого диапазона и переводит в `uint8` или `uint16`. Значения меньше 0 становятся 0, выше 1 — максимумом.

Поддержаны 1, 3 и 4 канала: grayscale, RGB, RGBA. Другая глубина каналов вызывает `ValueError`, а не автоматическое удаление или дополнение.

## EXR сохраняет float range без clamp

EXR-путь переводит массив в `float32`, но не ограничивает 0–1. Отрицательные значения и значения выше единицы могут сохраниться, что важно для scene-linear pipelines.

Также поддержаны 1, 3 и 4 канала. Файл кодируется через PyAV codec context с float pixel formats, а не через Pillow.

## sRGB для EXR линейризуется

Если выбран EXR + `sRGB`, нода применяет обратную sRGB EOTF: линейный участок ниже 0.04045 и степень 2.4 выше. Alpha четвёртого канала проходит без преобразования.

Результат записывается как scene-linear Rec.709. Значение `input_color_space` описывает кодировку входного tensor, а не пожелание назначить произвольный профиль готовому файлу.

## HDR означает HLG Rec.2020 input

EXR + `HDR` интерпретирует вход как HLG-кодированный Rec.2020 по BT.2100 и применяет обратную HLG OETF. В EXR сохраняется scene-linear light в гамуте Rec.2020.

Это не универсальный переключатель «сделать HDR». Если upstream уже linear или использует другую transfer function, выбор HDR даст неверные численные значения.

## linear проходит без transfer conversion

EXR + `linear` оставляет пиксели без sRGB/HLG преобразования и считает primaries Rec.709. Этот режим предназначен для уже scene-linear результата renderer или compositor.

Alpha при всех трёх EXR-вариантах не проходит через цветовую функцию. В metadata добавляются chromaticities Rec.709 либо Rec.2020, соответствующие выбранной интерпретации.

## Метаданные внедряются по-разному

PNG получает `prompt` и `extra_pnginfo` как `tEXt` chunks сразу после IHDR. EXR получает string attributes и `chromaticities`; при вставке код пересчитывает абсолютные offsets таблицы chunks.

При `--disable-metadata` эти данные не добавляются. Формат и цветовые данные не следует путать с приватностью: проверьте итоговый файл перед распространением.

## Каждый batch-элемент становится отдельным файлом

Цикл вызывает encoder для каждого `image`, подставляет `%batch_num%`, добавляет пятизначный counter и расширение `.png` либо `.exr`. Результаты перечисляются в UI как `type = "output"`.

Выход `images` возвращает исходный IMAGE-бэтч дальше. Как и у других save-нод, passthrough не декодирует только что записанные файлы.

## Официальные шаблоны используют только PNG 8-bit

Полный scan нашёл 20 SaveImageAdvanced: все в root, все включены (`mode = 0`), все в 20 файлах. Каждая нода сохраняет `png`, `8-bit`, `sRGB`; случаев EXR и 16-bit PNG нет.

В `api_bytedance_seedream_5_0_layer_separation` JoinImageWithAlpha № 31 передаёт RGBA в SaveImageAdvanced № 23 с префиксом `layers/image_layer`. Это реальный alpha-output, но именно 8-bit branch.

## Fragment документирует не показанную в wheel 16-bit ветку

Рецепт принимает внешний RGB/RGBA IMAGE и задаёт `png`, `16-bit`, `sRGB`. Он source-derived, потому что официальный wheel такую комбинацию не содержит.

Локально выполнены transfer-функции и PNG metadata injection из закреплённого AST. PyAV в рабочем Python отсутствует, поэтому сам `_encode_image` для RGB/RGBA 16-bit PNG и EXR не исполнялся; fragment также не запускался в ComfyUI. Редактор пока не проверил материал вручную.

## Источники

- [SaveImageAdvanced и encoder в ComfyUI v0.32.0](https://github.com/Comfy-Org/ComfyUI/blob/c2bcbecd82ec5ae66594340b395c24ef0217b238/comfy_extras/nodes_images.py#L842-L1238)
- [Embedded docs 0.5.9 для SaveImageAdvanced](https://github.com/Comfy-Org/embedded-docs/blob/1d258cf6e374d60d138a2bfcd273c7e11f750ef9/comfyui_embedded_docs/docs/SaveImageAdvanced/en.md)
- [Официальный `api_bytedance_seedream_5_0_layer_separation`](https://github.com/Comfy-Org/workflow_templates/blob/cca1ea5ea4560108ecc2f44dee951f41ea433062/templates/api_bytedance_seedream_5_0_layer_separation.json)
- [Закреплённый набор workflow templates 0.1.42](https://github.com/Comfy-Org/workflow_templates/tree/cca1ea5ea4560108ecc2f44dee951f41ea433062/templates)
