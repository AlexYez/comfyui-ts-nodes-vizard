# ModelMergeFlux1: смешивание весов по блокам Flux.1

## Что делает нода

`ModelMergeFlux1` — архитектурная надстройка над `ModelMergeBlocks`. Она смешивает совпадающие `diffusion_model`-веса двух Flux.1-моделей и выводит отдельный ratio для входных проекций, 19 `double_blocks`, 38 `single_blocks` и `final_layer`.

Каждый ratio означает долю `model1`: `result = ratio × model1 + (1 − ratio) × model2`. Значение 1 оставляет группу первой модели, 0 берёт вторую.

## Когда использовать и когда не использовать

Используйте ноду для двух совместимых Flux.1 checkpoint с одинаковым вариантом архитектуры и формами весов. Она полезна, когда нужно менять вклад по отдельным transformer-блокам, а единого ratio недостаточно.

Не применяйте эту карту к Flux 2, SD3, Wan или произвольному DiT. Имена ключей заданы в исходнике буквально. Нода не смешивает CLIP, VAE и model sampling patches.

## Короткий рецепт подключения

Подайте Flux.1 `MODEL` в `model1` и `model2`. Оставьте все ratio равными 1 и поставьте `double_blocks.0. = 0,5`: только первый double block смешается пополам, остальные перечисленные группы останутся из `model1`.

Фрагмент показывает именно эту проверку. Точного `ModelMergeFlux1` в официальных templates 0.1.42 нет, поэтому он не назван готовым workflow.

## Входы, выходы и параметры

После `model1` и `model2` идут `img_in.`, `time_in.`, `guidance_in`, `vector_in.`, `txt_in.`, 19 ключей `double_blocks.0.`…`18.`, 38 ключей `single_blocks.0.`…`37.` и `final_layer.` — всего 63 ratio.

У каждого диапазон 0…1, шаг 0,01, default 1. Выход — `MODEL`, клон первой модели с ленивыми patches.

## Типовые связки

Два `UNETLoader` или совместимых checkpoint loader → `ModelMergeFlux1` → Flux sampling-ветвь. Тот же patched `MODEL` должен идти в scheduler/guider, если они зависят от модели.

Для одного коэффициента используйте `ModelMergeSimple`. `ModelMergeSD35_Large`, `ModelMergeWAN2_1` и `ModelMergeLTXV` имеют другие списки префиксов.

## Практический пример

Exact-source probe восстановил runtime-схему: 19 double и 38 single inputs, 63 коэффициента всего. Ключ `double_blocks.0.attn.to_q.weight` выбрал ratio `double_blocks.0. = 0,25`, а `double_blocks.10…` не спутался с блоком 1 благодаря точке после номера.

Ключ без совпадающего префикса получил первый ratio (`img_in.`). Это важная граница: неперечисленные веса не получают отдельный «безопасный default».

## Частые ошибки и способы проверки

- Ratio принят за долю второй модели; направление обратное.
- Flux.1 смешивается с другой архитектурой или несовместимой квантизацией.
- Изменён один блок, но забыты неперечисленные ключи: они используют первый ratio.
- Shape warnings проигнорированы. При несовпадении базовый вес уже масштабирован, а добавление пропускается.
- От merge ожидают смешивания CLIP/VAE.

Сравнивайте крайние значения 1 и 0, фиксируйте seed и смотрите консоль.

## Производительность и внутреннее поведение

Класс создаёт только словарь входов; merge наследуется от `ModelMergeBlocks`. Для каждого ключа берётся самое длинное буквальное совпадение префикса, после чего регистрируются strengths `(1 − ratio, ratio)`.

Нода не материализует checkpoint сразу, но загрузка двух моделей и применение десятков групп всё равно требуют памяти. Длинные patch-цепочки усложняют повторение результата.

## Совместимость, изменения и статус

Проверены ComfyUI 0.32.0, frontend 1.48.7, docs 0.5.9 и все 512 workflow JSON 0.1.42. Direct case не найден. Нода не deprecated и не experimental; replacement entry отсутствует.

Embedded docs перечисляют controls, но точные prefix/fallback semantics взяты из реализации. Реальные Flux checkpoint не запускались.

Редактор пока не проверил материал вручную.

## Связанные ноды и источники

Базовый алгоритм подробно разобран в `ModelMergeBlocks`; простой blend — в `ModelMergeSimple`.

### Источники

- [ModelMergeFlux1](https://github.com/Comfy-Org/ComfyUI/blob/c2bcbecd82ec5ae66594340b395c24ef0217b238/comfy_extras/nodes_model_merging_model_specific.py#L106-L130)
- [ModelMergeBlocks](https://github.com/Comfy-Org/ComfyUI/blob/c2bcbecd82ec5ae66594340b395c24ef0217b238/comfy_extras/nodes_model_merging.py#L138-L168)
- [Embedded docs 0.5.9](https://pypi.org/project/comfyui-embedded-docs/0.5.9/)

