# ConditioningSetAreaPercentageVideo: область в пространстве и времени latent

## Назначение

`ConditioningSetAreaPercentageVideo` задаёт область conditioning сразу по трём измерениям video latent: времени, высоте и ширине. Размеры и смещения хранятся как доли от 0 до 1.

Нода также записывает общий metadata-множитель `strength`. Она не обрезает видео, не выбирает исходные кадры и не задаёт окно sampling.

## Место в графе

Ноду ставят после источника `CONDITIONING` и перед video sampler. Она нужна, когда одна запись должна действовать только в части latent по temporal- и spatial-координатам.

`ConditioningSetAreaPercentage` описывает два измерения — height и width. Video-вариант добавляет temporal extent и offset `z`. `ConditioningTimestepsRange` управляет стадией denoising, а не временной осью видео.

## Входы

`conditioning` — обязательный `CONDITIONING`. `width`, `height` и `temporal` задают долю размера по соответствующей оси; значения по умолчанию равны 1. `x`, `y` и `z` задают долю начального смещения; по умолчанию 0.

Все шесть координат принимают значения 0–1 с шагом 0,01. `strength` принимает 0–10 с шагом 0,01 и по умолчанию равен 1. Runtime не проверяет суммы `x + width`, `y + height` и `z + temporal`.

## Выход

Выход сохраняет тип и число записей. В каждый metadata-словарь записывается tuple `area = ("percentage", temporal, height, width, z, y, x)`, число `strength` и boolean `set_area_to_bounds: false`.

Основной embedding и pooled output не меняются. Если запись уже имела area или strength, новые значения их перезаписывают.

## Как работает

Перед sampling multidimensional resolver убирает маркер `percentage`. Для video latent с измерениями `(T, H, W)` он переводит `(temporal, height, width)` в целые размеры и `(z, y, x)` — в целые смещения.

Размер вычисляется через `max(1, round(fraction × dimension))`, смещение — через `round(fraction × dimension)`. Позже `get_area_and_mult` ограничивает длину остатком измерения после смещения и формирует multiplier из area и strength. Порядок tuple совпадает с порядком latent dimensions, а не с привычной записью x, y, z.

## Параметры и настройка

Для области в середине ролика сначала выберите temporal и `z`, затем spatial-размеры и смещения. Например, `temporal: 0.4`, `z: 0.1` означает четыре десятых latent-времени, начиная примерно с одной десятой этой оси.

Это не обязательно те же доли от числа исходных кадров: video VAE может сжимать temporal-ось. Значения, выходящие за правую границу, sampler обрезает. При offset 1 остаток измерения может стать нулевым, несмотря на предварительный минимум размера 1.

## Проверенный пример

Fragment «Область video conditioning в долях latent» задаёт width 0,5, height 0,6, temporal 0,4, смещения x 0,25, y 0,2, z 0,1 и strength 0,9. Все значения проходят runtime-ограничения и создают точный tuple из закреплённого исходника.

Runtime ID отсутствует во всех 512 official workflow templates JSON 0.1.42, включая подграфы. Fragment не содержит video model, latent или sampler, не исполнялся и служит проверкой структуры metadata, а не готовым video preset.

## Частые ошибки

**Temporal принимают за sampling range.** Поле задаёт размер по временной оси video latent. Для стадии denoising используется `TIMESTEPS_RANGE` или `ConditioningSetTimestepRange`.

**Tuple читают в порядке x, y, z.** Сначала идут размеры temporal, height, width, затем смещения z, y, x.

**Суммы size и offset считают автоматически нормализованными.** Runtime ограничивает каждое поле отдельно. Выходящая за latent часть обрезается.

**Ноду используют с обычным 2D latent.** Тип `CONDITIONING` не проверяет размерность будущего latent. Resolver сопоставляет tuple с фактическими dimensions, поэтому video-смысл требует трёх sampled-осей.

## Ограничения и производительность

Сама нода копирует metadata и не обрабатывает кадры или embedding. Основная работа возникает в sampler, который разрешает percentage-area, выделяет нужный subregion и смешивает вклад conditioning.

Для area без mask общий sampler создаёт мягкие края вдоль используемых измерений; эта логика применяется и к temporal-оси. Несколько перекрывающихся областей могут увеличить число conditioning-вычислений. Результат зависит от video latent layout конкретной модели, которое runtime-порт ноды не валидирует.

## Совместимость и источники

Статья описывает ComfyUI 0.32.0 на commit `c2bcbecd82ec5ae66594340b395c24ef0217b238`. Runtime ID — `ConditioningSetAreaPercentageVideo`, python module — `comfy_extras.nodes_video_model`; experimental-флаг не установлен.

Embedded docs 0.5.9 по пути `comfyui_embedded_docs/docs/ConditioningSetAreaPercentageVideo/en.md` верно различают position, size и duration, но не раскрывают tuple-порядок, округление, clipping и зависимость от реальных latent dimensions.

- [Реализация `ConditioningSetAreaPercentageVideo`](https://github.com/Comfy-Org/ComfyUI/blob/c2bcbecd82ec5ae66594340b395c24ef0217b238/comfy_extras/nodes_video_model.py#L126-L147)
- [Преобразование percentage-area в latent-размеры](https://github.com/Comfy-Org/ComfyUI/blob/c2bcbecd82ec5ae66594340b395c24ef0217b238/comfy/samplers.py#L761-L784)
- [Clipping, strength и мягкие края area](https://github.com/Comfy-Org/ComfyUI/blob/c2bcbecd82ec5ae66594340b395c24ef0217b238/comfy/samplers.py#L33-L80)
- [Копирование metadata conditioning](https://github.com/Comfy-Org/ComfyUI/blob/c2bcbecd82ec5ae66594340b395c24ef0217b238/node_helpers.py#L9-L23)
- [Official workflow templates JSON 0.1.42](https://pypi.org/project/comfyui-workflow-templates-json/0.1.42/)
- [Pinned embedded docs 0.5.9](https://pypi.org/project/comfyui-embedded-docs/0.5.9/)
