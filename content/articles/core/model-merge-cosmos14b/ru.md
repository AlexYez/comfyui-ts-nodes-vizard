# ModelMergeCosmos14B: смешивание 36 блоков Cosmos 14B

## Что делает нода

`ModelMergeCosmos14B` даёт коэффициенты для embedding/norm-групп, 36 `blocks.blockN.` и `final_layer.` Cosmos 14B. Формула каждого совпавшего веса: `ratio × model1 + (1 − ratio) × model2`.

Это размер-специфичная карта; 7B использует 28 блоков.

## Когда использовать и когда не использовать

Используйте ноду только с двумя совместимыми Cosmos 14B checkpoint. Отдельные ratio подходят для локального block experiment.

Не смешивайте 14B с 7B, Predict2 или иной Cosmos architecture. Отсутствующие ключи не создаются, несовпадающие формы не преобразуются.

## Короткий рецепт подключения

Подайте две Cosmos 14B модели, оставьте все значения 1 и поставьте `blocks.block0. = 0,5`. Проверьте короткий video clip до сохранения результата.

В официальном workflow wheel merge-тип не встречается; fragment source-derived.

## Входы, выходы и параметры

Пять первых ratio: `pos_embedder.`, `extra_pos_embedder.`, `x_embedder.`, `t_embedder.`, `affline_norm.`. Затем 36 `blocks.block0.`…`35.` и `final_layer.` — 42 ratio.

Диапазон 0…1, default 1. Имя `affline_norm.` сохранено буквально из runtime.

## Типовые связки

Два Cosmos 14B loader → `ModelMergeCosmos14B` → Cosmos sampling graph. Сопутствующие text encoder/VAE остаются вне операции.

Для 7B нужна отдельная нода; для одного ratio — `ModelMergeSimple`.

## Практический пример

Pinned-source inspection подтвердил 36 блоков и 42 коэффициента. Индексные prefixes содержат точку, поэтому block3 не перехватывает block30.

Ключ без совпадения получает первый ratio. Таким образом `pos_embedder.` служит ещё и fallback для любых неперечисленных diffusion-весов.

## Частые ошибки и способы проверки

- Используется 7B checkpoint.
- Ratio читается как доля model2.
- `affline_norm.` переименован вручную.
- Неперечисленные keys не проверены.
- Полный video run запускается до короткой sanity-проверки.

Сверьте block count, формы и лог shape warnings.

## Производительность и внутреннее поведение

Merge ленивый, но две 14B-модели особенно дороги по памяти/диску. Общий алгоритм выбирает самый длинный literal prefix и хранит patch chain до загрузки веса.

Перемещение/offload может занимать больше времени, чем создание ноды; это нормальное следствие размера моделей.

## Совместимость, изменения и статус

Проверены ComfyUI 0.32.0, frontend 1.48.7, docs 0.5.9 и весь workflow wheel. Direct case отсутствует; нода не deprecated/experimental, replacement нет.

Checkpoint merge и inference не запускались.

Редактор пока не проверил материал вручную.

## Связанные ноды и источники

Смотрите `ModelMergeCosmos7B`, базовый `ModelMergeBlocks` и общий `ModelMergeSimple`.

### Источники

- [ModelMergeCosmos14B](https://github.com/Comfy-Org/ComfyUI/blob/c2bcbecd82ec5ae66594340b395c24ef0217b238/comfy_extras/nodes_model_merging_model_specific.py#L223-L245)
- [ModelMergeBlocks](https://github.com/Comfy-Org/ComfyUI/blob/c2bcbecd82ec5ae66594340b395c24ef0217b238/comfy_extras/nodes_model_merging.py#L138-L168)
- [Embedded docs 0.5.9](https://pypi.org/project/comfyui-embedded-docs/0.5.9/)

