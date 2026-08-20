# ModelMergeWAN2_1: смешивание блоков Wan 2.1

## Что делает нода

`ModelMergeWAN2_1` задаёт отдельную долю `model1` для embedding-групп Wan, 40 `blocks` и `head`. Исходный tooltip уточняет: модель 1.3B имеет 30 блоков, 14B — 40, а image-to-video вариант добавляет `img_emb.`.

Формула каждой совпавшей группы: `ratio × model1 + (1 − ratio) × model2`.

## Когда использовать и когда не использовать

Используйте ноду для checkpoint одного размера и режима Wan 2.1. Смешивание 14B с 1.3B или text-to-video с несовместимой image-to-video структурой не становится безопасным из-за наличия 40 полей.

Не задавайте коэффициенты blocks 30–39 для 1.3B в ожидании эффекта: таких ключей там нет. Не смешивайте разные architecture/config variants без сравнения state dict.

## Короткий рецепт подключения

Подайте две совместимые Wan 2.1 модели. Оставьте все ratio 1 и установите `blocks.0. = 0,5`, чтобы смешать только первый transformer block. Затем проверьте результат в том же video workflow.

Fragment не содержит полный video graph: прямого official case с merge-нодой в wheel 0.1.42 нет.

## Входы, выходы и параметры

После `model1/model2`: `patch_embedding.`, `time_embedding.`, `time_projection.`, `text_embedding.`, `img_emb.`, `blocks.0.`…`39.`, `head.` — 46 ratio.

Каждый диапазон 0…1, default 1, шаг 0,01. Для T2V ключ `img_emb.` может отсутствовать; для 1.3B отсутствуют последние десять block-групп.

## Типовые связки

Два Wan model loader → `ModelMergeWAN2_1` → соответствующий Wan conditioning/sampling graph. Тот же размер и режим модели должны использоваться на обеих сторонах.

Для общего blend можно применить `ModelMergeSimple`, но он не решает проблему несовместимых ключей. `ModelMergeLTXV` и Flux-ноды имеют другие карты.

## Практический пример

Exact-source probe подтвердил 40 block inputs, пять embedding inputs и head. Всего получается 46 коэффициентов. `img_emb.` присутствует в UI независимо от того, содержит ли конкретный checkpoint такой ключ.

Базовый merge принимает только ключи, существующие в `model1`. Поэтому группа, присутствующая лишь во второй I2V-модели, не добавляется в T2V-основу. Это ещё одна причина не использовать ноду для конвертации режима.

## Частые ошибки и способы проверки

- Смешаны 1.3B и 14B.
- T2V и I2V приняты за одинаковые state dict.
- Ratio трактуется как доля второй модели.
- Пустые поля blocks 30–39 у 1.3B считаются ошибкой ноды.
- Shape warnings скрыты в длинном логе.

Проверьте размер модели, наличие `img_emb`, число blocks и все warnings до sampling.

## Производительность и внутреннее поведение

Класс только формирует architecture-specific inputs; merge выполняет общий prefix-based алгоритм. Ключи второй модели фильтруются по `diffusion_model.` и добавляются к клону первой при совпадении state-dict key.

Полный video checkpoint велик, поэтому две модели заметно увеличивают память и время загрузки. Нода не генерирует кадры и не проверяет runtime-совместимость заранее.

## Совместимость, изменения и статус

Проверены ComfyUI 0.32.0, frontend 1.48.7, docs 0.5.9 и полный workflow wheel. Direct merge case отсутствует. Статусы deprecated/experimental false; replacement нет.

Recipe source-derived, реальный Wan sampling не выполнялся.

Редактор пока не проверил материал вручную.

## Связанные ноды и источники

Для общей механики смотрите `ModelMergeBlocks`; для других архитектур — `ModelMergeFlux1` и `ModelMergeLTXV`.

### Источники

- [ModelMergeWAN2_1](https://github.com/Comfy-Org/ComfyUI/blob/c2bcbecd82ec5ae66594340b395c24ef0217b238/comfy_extras/nodes_model_merging_model_specific.py#L247-L269)
- [ModelMergeBlocks](https://github.com/Comfy-Org/ComfyUI/blob/c2bcbecd82ec5ae66594340b395c24ef0217b238/comfy_extras/nodes_model_merging.py#L138-L168)
- [Embedded docs 0.5.9](https://pypi.org/project/comfyui-embedded-docs/0.5.9/)

