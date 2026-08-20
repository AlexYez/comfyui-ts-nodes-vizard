# ModelMergeMochiPreview: смешивание 48 блоков Mochi

## Что делает нода

`ModelMergeMochiPreview` задаёт коэффициенты для `pos_frequencies.`, time/T5-проекций, 48 `blocks` и `final_layer.` Mochi. Каждый коэффициент означает долю `model1` в совпавшем diffusion-весе.

Нода создаёт patch-объект; она не запускает видео и не сохраняет checkpoint.

## Когда использовать и когда не использовать

Используйте её только для двух Mochi Preview-моделей с одинаковыми 48-блочными state dict и совместимым способом загрузки.

Не применяйте карту к LTXV, Wan или другой версии Mochi, пока точные ключи и формы не совпадут. Наличие 48 UI-полей не превращает несовместимые веса в совместимые.

## Короткий рецепт подключения

Подайте две Mochi модели, оставьте все значения 1 и задайте `blocks.0. = 0,5`. Первый блок смешается поровну, остальные перечисленные группы останутся из первой модели.

Direct official workflow с этой merge-нодой не найден; fragment описывает проверенный порядок портов.

## Входы, выходы и параметры

После моделей идут `pos_frequencies.`, `t_embedder.`, `t5_y_embedder.`, `t5_yproj.`, `blocks.0.`…`47.`, `final_layer.` — 53 ratio.

Каждый FLOAT: default 1, min 0, max 1, step 0,01. Выход — `MODEL`.

## Типовые связки

Два совместимых loader → `ModelMergeMochiPreview` → Mochi conditioning/scheduler/sampler. T5/CLIP и VAE-компоненты merge не смешивает.

`ModelMergeLTXV` предназначена для другой видеоархитектуры; `ModelMergeSimple` даёт один общий ratio.

## Практический пример

Source/runtime probe подтвердил 48 block inputs и 53 коэффициента. `blocks.1.` не совпадает с `blocks.10.` из-за завершающей точки, поэтому индексные префиксы разделены корректно.

Любой diffusion-key без перечисленного префикса получает первый числовой коэффициент — `pos_frequencies.`. Это часть наследуемого алгоритма, а не отдельный Mochi default.

## Частые ошибки и способы проверки

- Смешаны разные размеры или поколения Mochi.
- Ratio принят за вклад второй модели.
- T5 encoder считается частью MODEL merge.
- Неперечисленные ключи не проверены.
- Shape warning затерян в логе длинного video run.

Начинайте с короткого clip и фиксированных sampling-параметров.

## Производительность и внутреннее поведение

Нода наследует literal-prefix поиск самого длинного совпадения. Для каждого ключа регистрируется `(1 − ratio)` patch-strength второй модели и `ratio` strength первой.

Mochi-модели велики; две модели увеличивают load/materialization cost. UI-операция сама по себе дешёвая.

## Совместимость, изменения и статус

Проверка: ComfyUI 0.32.0, frontend 1.48.7, docs 0.5.9, 512 workflow JSON и все subgraphs. Direct occurrence равен нулю. Deprecated/experimental false, replacement отсутствует.

Полный merge и inference не выполнялись.

Редактор пока не проверил материал вручную.

## Связанные ноды и источники

Общая механика описана в `ModelMergeBlocks`; рядом — архитектурные `ModelMergeLTXV` и `ModelMergeWAN2_1`.

### Источники

- [ModelMergeMochiPreview](https://github.com/Comfy-Org/ComfyUI/blob/c2bcbecd82ec5ae66594340b395c24ef0217b238/comfy_extras/nodes_model_merging_model_specific.py#L155-L175)
- [ModelMergeBlocks](https://github.com/Comfy-Org/ComfyUI/blob/c2bcbecd82ec5ae66594340b395c24ef0217b238/comfy_extras/nodes_model_merging.py#L138-L168)
- [Embedded docs 0.5.9](https://pypi.org/project/comfyui-embedded-docs/0.5.9/)

