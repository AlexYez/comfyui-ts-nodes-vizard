# ModelMergeLTXV: смешивание 28 transformer blocks LTX-Video

## Что делает нода

`ModelMergeLTXV` смешивает совместимые LTX-Video diffusion-модели по точной карте: `patchify_proj.`, `adaln_single.`, `caption_projection.`, 28 `transformer_blocks`, `scale_shift_table` и `proj_out.`.

Каждый коэффициент — доля `model1`. Нода наследует prefix-based арифметику `ModelMergeBlocks`.

## Когда использовать и когда не использовать

Используйте её для двух LTXV checkpoint одной версии и структуры, когда нужен контроль отдельных transformer blocks. Сначала проверяйте небольшой участок и один и тот же video sampling setup.

Не смешивайте разные поколения/размеры LTXV, audio-video и несовместимые варианты без сравнения ключей. Нода не преобразует архитектуру и не проверяет формы до применения patches.

## Короткий рецепт подключения

Подайте две совместимые LTXV модели, оставьте все ratio 1 и задайте `transformer_blocks.0. = 0,5`. Только совпавшие ключи первого блока получат равную смесь.

Официального serialized merge case нет; fragment проверяет schema/prefix, а не полное видео.

## Входы, выходы и параметры

После двух моделей доступны три входные проекции, 28 полей `transformer_blocks.0.`…`27.`, `scale_shift_table` без завершающей точки и `proj_out.` — 33 ratio.

Диапазон каждого 0…1, default 1, шаг 0,01. Выход — patched `MODEL`.

## Типовые связки

Два LTXV model loader → `ModelMergeLTXV` → LTXV scheduler/guider/sampler. CLIP/text encoder, VAE и audio components выбираются отдельно.

Для одного коэффициента используйте `ModelMergeSimple`. Wan и Flux требуют собственных prefix-карт.

## Практический пример

Exact-source probe подтвердил 28 transformer inputs и 33 ratio всего. Отдельно проверен префикс `scale_shift_table`: из-за отсутствия точки он совпадает не только с точным ключом, но и с любой строкой, начинающейся так же, например `scale_shift_table_extra`.

В текущей LTXV-модели это соответствует ожидаемому имени, но статья фиксирует буквальное поведение, а не приписывает коду семантический разбор таблицы.

## Частые ошибки и способы проверки

- Ratio прочитан как доля model2.
- Смешаны несовместимые LTXV поколения.
- Текстовый/audio тракт считается частью MODEL merge.
- Неперечисленные ключи получают первый ratio и остаются незамеченными.
- Shape mismatch warning проигнорирован.

Сравните state dict, версии loader и результаты на фиксированном коротком clip.

## Производительность и внутреннее поведение

Нода формирует 33 числовых input, а merge наследуется от базового класса. Выбирается самый длинный буквальный префикс; patches materialize позже при загрузке весов.

Видео-модели велики: две копии/patch graphs требуют существенной памяти. Сам UI-node не запускает inference и не оценивает качество.

## Совместимость, изменения и статус

Проверено на ComfyUI 0.32.0 и frontend 1.48.7. Full census 512 JSON/496 roots/272 subgraphs не нашёл `ModelMergeLTXV`. Нода не deprecated/experimental, replacement отсутствует.

Docs 0.5.9 использованы вторично; counts и bare-prefix behavior проверены по исходнику.

Редактор пока не проверил материал вручную.

## Связанные ноды и источники

Общая механика — `ModelMergeBlocks`. Для Wan 2.1 используйте отдельную `ModelMergeWAN2_1`.

### Источники

- [ModelMergeLTXV](https://github.com/Comfy-Org/ComfyUI/blob/c2bcbecd82ec5ae66594340b395c24ef0217b238/comfy_extras/nodes_model_merging_model_specific.py#L177-L197)
- [ModelMergeBlocks](https://github.com/Comfy-Org/ComfyUI/blob/c2bcbecd82ec5ae66594340b395c24ef0217b238/comfy_extras/nodes_model_merging.py#L138-L168)
- [Embedded docs 0.5.9](https://pypi.org/project/comfyui-embedded-docs/0.5.9/)

