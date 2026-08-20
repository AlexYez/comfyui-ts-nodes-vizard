# Save Animated WebP: записать IMAGE-бэтч одним WebP

`SaveAnimatedWEBP` воспринимает первую ось IMAGE как последовательность кадров и записывает один файл `.webp` в output. В отличие от обычного SaveImage, весь бэтч становится одним контейнером, а не набором отдельных PNG.

## Каждый элемент бэтча становится кадром

Save helper перебирает `images` и переводит каждый tensor в Pillow Image. Первый кадр вызывает `save(..., save_all=True)`, остальные передаются через `append_images`.

Если вход содержит один IMAGE, файл всё равно создаётся как WebP, но UI отмечает результат анимированным только при `len(images) > 1`. Нода не повторяет единственный кадр автоматически.

## FPS превращается в целые миллисекунды

Для всех кадров используется `duration = int(1000.0 / fps)`. Runtime допускает FPS от 0.01 до 1000 с шагом 0.01.

Из-за `int` длительность округляется вниз. При 6 FPS записывается 166 мс, при 16 FPS — 62 мс. Фактическая скорость контейнера может немного отличаться от введённого значения.

## Преобразование в Pillow квантует до 8 бит

Каждый IMAGE умножается на 255, ограничивается диапазоном 0–255 и переводится в `uint8`. Значения за пределами 0–1 обрезаются, дробная точность выше 8 бит теряется до WebP-кодирования.

RGBA сохраняет четвёртый канал, если Pillow/WebP build его поддерживает. Это не float/HDR-export и не путь для 16-битных данных.

## lossless и quality отвечают за разные режимы

`lossless` по умолчанию включён. В этом режиме WebP хранит пиксели без lossy-кодирования после уже выполненной 8-битной квантизации. `quality` задаётся от 0 до 100 и передаётся Pillow вместе с флагом lossless.

При `lossless = false` quality непосредственно управляет компромиссом между размером и потерями. Даже lossless WebP не восстанавливает значения, отброшенные tensor→uint8 conversion.

## method выбирает усилие компрессора

Combo предлагает `default`, `fastest`, `slowest`. Код переводит их в числа Pillow: 4, 0 и 6 соответственно.

Это настройка скорости и усилия кодирования, а не FPS или качество изображения. `slowest` обычно тратит больше времени на поиск меньшего файла; конкретный выигрыш зависит от кадров и версии WebP-библиотеки.

## Метаданные пишутся в EXIF

Если metadata не отключена, prompt помещается в EXIF tag `0x0110`, а элементы `extra_pnginfo` — в последовательные tags, начиная с `0x010F`. Данные сериализуются как JSON-строки.

Перед публикацией не считайте WebP обезличенным. Проверьте EXIF или запускайте ComfyUI с отключёнными metadata, если workflow и prompt не должны сопровождать файл.

## Нода сохраняет файл и возвращает IMAGE

Runtime помечает её output node, поэтому запись является побочным эффектом выполнения. Одновременно `NodeOutput` возвращает исходный `images`, и ветку можно продолжить после save-ноды.

Повторный запуск с изменившимся upstream создаёт следующий файл со счётчиком. `filename_prefix` может включать подпапку и поддерживаемые ComfyUI formatting tokens.

## Официальный alpha-video пример использует 16 FPS

В `video_wan2.1_alpha_t2v_14B` VAEDecode № 8 даёт RGB, InvertMask № 84 — alpha, а JoinImageWithAlpha № 86 собирает RGBA. Его выход подключён к SaveAnimatedWEBP № 80.

Сохранены настройки `ComfyUI`, 16 FPS, `lossless = true`, quality 80 и method `default`. Это единственный включённый SaveAnimatedWEBP в wheel 0.1.42.

## Остальные четыре официальных экземпляра bypassed

Полный recursive scan 496 workflow-графов нашёл пять SaveAnimatedWEBP, все в root. Четыре Wan/VACE экземпляра имеют `mode = 4`, 6 FPS и те же lossless/quality/method defaults.

Bypassed-нода не доказывает, что WebP реально сохраняется в обычном запуске шаблона. Census различает сериализованную топологию и включённый output.

## Fragment оставляет RGBA-бэтч внешним

Рецепт подключает внешний IMAGE-бэтч к SaveAnimatedWEBP с точными настройками официального alpha-video случая: 16 FPS, lossless, quality 80, default method. API/video-generation ветка не включена.

Локально Pillow успешно записал и перечитал трёхкадровый RGBA WebP: alpha и частичная прозрачность сохранились. RGB у полностью прозрачного пикселя не проверялся и не гарантируется. Это проверка helper-compatible encoding branch, а не исполнение fragment или ComfyUI UI metadata. Редактор пока не проверил материал вручную.

## Источники

- [SaveAnimatedWEBP в ComfyUI v0.32.0](https://github.com/Comfy-Org/ComfyUI/blob/c2bcbecd82ec5ae66594340b395c24ef0217b238/comfy_extras/nodes_images.py#L197-L232)
- [Animated WebP helper](https://github.com/Comfy-Org/ComfyUI/blob/c2bcbecd82ec5ae66594340b395c24ef0217b238/comfy_api/latest/_ui.py#L76-L269)
- [Официальный `video_wan2.1_alpha_t2v_14B`](https://github.com/Comfy-Org/workflow_templates/blob/cca1ea5ea4560108ecc2f44dee951f41ea433062/templates/video_wan2.1_alpha_t2v_14B.json)
- [Закреплённый набор workflow templates 0.1.42](https://github.com/Comfy-Org/workflow_templates/tree/cca1ea5ea4560108ecc2f44dee951f41ea433062/templates)
