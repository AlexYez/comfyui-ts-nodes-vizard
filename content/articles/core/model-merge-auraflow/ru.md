# ModelMergeAuraflow: смешивание блоков AuraFlow

## Что делает нода

`ModelMergeAuraflow` применяет общий алгоритм `ModelMergeBlocks` к карте AuraFlow. Она даёт отдельную долю `model1` для пяти входных/служебных групп, четырёх `double_layers`, 32 `single_layers`, `modF.` и `final_linear.`.

Для совпавшего ключа: `result = ratio × model1 + (1 − ratio) × model2`. Значение 1 берёт первую модель, 0 — вторую.

## Когда использовать и когда не использовать

Нода нужна для двух AuraFlow checkpoint одной структуры. Она позволяет ограничить смесь одним transformer layer и не трогать остальные перечисленные группы.

Не используйте эту карту для Chroma/Flux или иной flow-модели. Совпадение общих слов в названии не означает совпадение state-dict ключей и форм.

## Короткий рецепт подключения

Подайте совместимые AuraFlow `MODEL`, оставьте все ratio равными 1 и задайте `double_layers.0. = 0,5`. Выход проверяйте тем же `ModelSamplingAuraFlow`, scheduler и seed, что исходные модели.

Фрагмент source-derived: direct merge case в official templates 0.1.42 отсутствует.

## Входы, выходы и параметры

После `model1/model2`: `init_x_linear.`, `positional_encoding`, `cond_seq_linear.`, `register_tokens`, `t_embedder.`, четыре `double_layers.0.`…`3.`, 32 `single_layers.0.`…`31.`, `modF.`, `final_linear.` — 43 ratio.

Все значения 0…1, default 1, шаг 0,01. `positional_encoding` и `register_tokens` заданы без завершающей точки, поэтому это буквальные широкие префиксы.

## Типовые связки

Два model loader → `ModelMergeAuraflow` → AuraFlow model-sampling patch → scheduler/guider. CLIP и VAE остаются отдельными.

Для единого коэффициента используйте `ModelMergeSimple`; для Flux.1 — отдельную `ModelMergeFlux1`.

## Практический пример

Exact-source schema probe подтвердил четыре double и 32 single inputs, 43 коэффициента всего. Проверка базового алгоритма показала: неперечисленный key получает первый ratio (`init_x_linear.`), а самый длинный подходящий префикс выигрывает.

Широкий `register_tokens` совпадёт с любым ключом, начинающимся этой строкой. Код не проверяет, что совпадение соответствует одному параметру.

## Частые ошибки и способы проверки

- Ratio прочитан как доля `model2`.
- Смешаны AuraFlow и другая architecture.
- Неперечисленные ключи забыты: они используют первый ratio.
- Shape mismatch warning проигнорирован.
- Patched model подключён к одному участку графа, а scheduler/guider получает исходную модель.

Проверяйте state dict, консоль и крайние значения 0/1.

## Производительность и внутреннее поведение

Класс строит только runtime input map. Наследуемый merge клонирует первую модель, читает эффективные diffusion patches второй и регистрирует ленивые операции с выбранным ratio.

Две полные модели требуют памяти; materialization происходит позже. Длинные цепочки merge/LoRA зависят от порядка.

## Совместимость, изменения и статус

Проверены ComfyUI 0.32.0, frontend 1.48.7, docs 0.5.9 и весь wheel workflows 0.1.42: exact type не встречается. Нода не deprecated/experimental, replacement отсутствует.

Реальные AuraFlow checkpoint не запускались; schema/prefix behavior проверен отдельно.

Редактор пока не проверил материал вручную.

## Связанные ноды и источники

Смотрите базовые `ModelMergeBlocks`, `ModelMergeSimple` и sampling-патч `ModelSamplingAuraFlow`.

### Источники

- [ModelMergeAuraflow](https://github.com/Comfy-Org/ComfyUI/blob/c2bcbecd82ec5ae66594340b395c24ef0217b238/comfy_extras/nodes_model_merging_model_specific.py#L79-L104)
- [ModelMergeBlocks](https://github.com/Comfy-Org/ComfyUI/blob/c2bcbecd82ec5ae66594340b395c24ef0217b238/comfy_extras/nodes_model_merging.py#L138-L168)
- [Embedded docs 0.5.9](https://pypi.org/project/comfyui-embedded-docs/0.5.9/)

