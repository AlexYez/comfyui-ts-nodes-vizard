# ModelMergeSD35_Large: смешивание 38 joint blocks SD3.5 Large

## Что делает нода

`ModelMergeSD35_Large` смешивает diffusion-веса двух совместимых SD3.5 Large-моделей по архитектурной карте: пять embedding-групп, 38 `joint_blocks` и `final_layer`.

Ratio — доля `model1`: 1 оставляет первую модель, 0 берёт вторую, 0,5 смешивает совпадающий вес поровну.

## Когда использовать и когда не использовать

Нода нужна для точного эксперимента с двумя SD3.5 Large checkpoint одинаковой структуры. Она позволяет ограничить изменение одним joint block или отдельной проекцией.

Не используйте её для SD3 2B: у `ModelMergeSD3_2B` 24 joint blocks. Не смешивайте checkpoint с разными формами, prediction/model configs или способами квантизации без проверки.

## Короткий рецепт подключения

Подключите SD3.5 Large `MODEL` к обоим входам. Оставьте все значения 1, кроме `joint_blocks.0. = 0,5`. Выход используйте в неизменном SD3.5 sampling-графе и сравните с `model1`.

Recipe fragment source-derived: в официальных workflow templates 0.1.42 прямого `ModelMergeSD35_Large` нет.

## Входы, выходы и параметры

После двух моделей идут `pos_embed.`, `x_embedder.`, `context_embedder.`, `y_embedder.`, `t_embedder.`, `joint_blocks.0.`…`37.` и `final_layer.` — 44 ratio.

Все коэффициенты имеют диапазон 0…1, default 1 и шаг 0,01. Выходной `MODEL` остаётся ленивым patch-объектом.

## Типовые связки

Два совместимых loader → `ModelMergeSD35_Large` → SD3.5 guider/sampler. CLIP и VAE выбираются отдельно; модельный merge их не изменяет.

Для SD3 2B используйте точную ноду его архитектуры. Для одного общего коэффициента подходит `ModelMergeSimple`.

## Практический пример

Pinned-source probe подтвердил 38 нумерованных joint inputs и 44 коэффициента всего. Сопоставление происходит с буквальным state-dict префиксом, а не с вычисленным «номером слоя».

Если ключ не совпал ни с одной группой, общий алгоритм применяет первый ratio — здесь это `pos_embed.`. Поэтому все реальные ключи конкретного checkpoint нужно сверять, а не полагаться только на название модели.

## Частые ошибки и способы проверки

- SD3.5 Large перепутана с SD3 2B.
- Ratio прочитан как доля `model2`.
- Неперечисленные ключи забыты; они получают коэффициент первой группы.
- Shape mismatch оставлен без внимания.
- CLIP и VAE считаются частью операции.

Проверьте список state dict, консоль и обе крайние конфигурации 0/1 перед промежуточными preset.

## Производительность и внутреннее поведение

Нода наследует `ModelMergeBlocks`: клонирует `model1`, читает эффективные patches `model2` и выбирает самый длинный подходящий префикс. Итоговые веса вычисляются при применении модели.

Количество UI-полей велико, но регистрация patches дешевле sampling. Основные затраты приходятся на хранение/загрузку двух checkpoint и materialization весов.

## Совместимость, изменения и статус

Статья привязана к ComfyUI 0.32.0 и frontend 1.48.7. Direct workflow case в полном wheel не найден. Нода не deprecated/experimental, replacement отсутствует.

Docs 0.5.9 использованы как вторичное описание; точные counts, направление ratio и fallback сверены по исходнику и probe.

Редактор пока не проверил материал вручную.

## Связанные ноды и источники

Сравните `ModelMergeSD3_2B`, базовый `ModelMergeBlocks` и общий `ModelMergeSimple`.

### Источники

- [ModelMergeSD35_Large](https://github.com/Comfy-Org/ComfyUI/blob/c2bcbecd82ec5ae66594340b395c24ef0217b238/comfy_extras/nodes_model_merging_model_specific.py#L132-L153)
- [ModelMergeBlocks](https://github.com/Comfy-Org/ComfyUI/blob/c2bcbecd82ec5ae66594340b395c24ef0217b238/comfy_extras/nodes_model_merging.py#L138-L168)
- [Embedded docs 0.5.9](https://pypi.org/project/comfyui-embedded-docs/0.5.9/)

