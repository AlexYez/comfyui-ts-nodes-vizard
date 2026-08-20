# ModelMergeCosmos7B: смешивание 28 блоков Cosmos 7B

## Что делает нода

`ModelMergeCosmos7B` смешивает совпадающие diffusion-веса двух Cosmos 7B-моделей по пяти служебным группам, 28 `blocks.blockN.` и `final_layer.`. Ratio — доля первой модели.

Карта соответствует 7B; она отличается от 36-блочной `ModelMergeCosmos14B`.

## Когда использовать и когда не использовать

Нода подходит для двух Cosmos 7B checkpoint одной структуры. Она нужна, когда требуется изменить вклад отдельных transformer blocks.

Не соединяйте 7B с 14B и не применяйте карту к Cosmos Predict2: имена и число блоков различаются. Совместимость text/video variants также проверяется по ключам, а не названию.

## Короткий рецепт подключения

Подайте два Cosmos 7B `MODEL`, оставьте все ratio 1 и задайте `blocks.block0. = 0,5`. Первый блок смешается пополам.

Recipe source-derived: в official workflow wheel direct merge case отсутствует.

## Входы, выходы и параметры

Поля: `pos_embedder.`, `extra_pos_embedder.`, `x_embedder.`, `t_embedder.`, точное исходное имя `affline_norm.`, затем `blocks.block0.`…`27.` и `final_layer.` — 34 ratio.

Все значения 0…1, default 1, шаг 0,01. Не исправляйте `affline_norm.` на `affine_norm.`: runtime ожидает именно строку из исходника.

## Типовые связки

Два Cosmos 7B loader → merge → соответствующий Cosmos sampling graph. CLIP/T5, VAE и latent video setup выбираются отдельно.

Для Cosmos 14B используйте отдельную карту; для общего blend — `ModelMergeSimple`.

## Практический пример

Exact source/runtime inspection подтвердил 28 блоков и 34 ratio. `blocks.block1.` и `blocks.block10.` разделяются точкой после номера.

Unmatched key получает первый ratio (`pos_embedder.`). Поэтому default для неперечисленных параметров меняется вместе с первым полем.

## Частые ошибки и способы проверки

- Выбрана 14B-модель для 7B-карты.
- Исправлена «опечатка» `affline_norm.` и потеряно совпадение.
- Ratio прочитан как доля model2.
- Shape mismatch не замечен.
- Video/text components считаются частью merge.

Сверяйте точные state-dict prefixes и block count.

## Производительность и внутреннее поведение

Класс объявляет prefix map, а базовый merge клонирует первую модель и регистрирует patches из второй. Тензоры materialize позднее.

Два 7B checkpoint требуют большой памяти и могут зависеть от offload. Нода не проверяет VRAM до очереди.

## Совместимость, изменения и статус

Baseline: ComfyUI 0.32.0/frontend 1.48.7. Direct occurrences среди 512 JSON и recursive subgraphs — 0. Deprecated/experimental false, replacement нет.

Реальные Cosmos weights и video run не выполнялись.

Редактор пока не проверил материал вручную.

## Связанные ноды и источники

Для 14B смотрите `ModelMergeCosmos14B`; общая арифметика — `ModelMergeBlocks`.

### Источники

- [ModelMergeCosmos7B](https://github.com/Comfy-Org/ComfyUI/blob/c2bcbecd82ec5ae66594340b395c24ef0217b238/comfy_extras/nodes_model_merging_model_specific.py#L199-L221)
- [ModelMergeBlocks](https://github.com/Comfy-Org/ComfyUI/blob/c2bcbecd82ec5ae66594340b395c24ef0217b238/comfy_extras/nodes_model_merging.py#L138-L168)
- [Embedded docs 0.5.9](https://pypi.org/project/comfyui-embedded-docs/0.5.9/)

