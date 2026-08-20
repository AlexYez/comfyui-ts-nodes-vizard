# ModelComputeDtype: вручную задать вычислительную точность модели

`ModelComputeDtype` клонирует `MODEL` и задаёт `manual_cast_dtype`. Доступны `default`, `fp32`, `fp16` и `bf16`. Это отладочный инструмент для управления вычислительным dtype модели, а не конвертер checkpoint-файла.

## Что делает нода

Строка выбора переводится в `torch.float32`, `torch.float16`, `torch.bfloat16` или `None` для `default`. Затем клон получает object patch `manual_cast_dtype`.

При явном dtype `ModelPatcher` включает `force_cast_weights = true`. Он также создаёт новый `patches_uuid`, чтобы модельная загрузка не переиспользовала несовместимый закэшированный вариант. Исходный checkpoint на диске не меняется.

## Место в графе

Ставьте ноду после загрузки модели и до guider/sampler. Если дальше идут другие model patches, ведите их от этого выхода. Compute dtype относится к выполнению самой diffusion-модели; он не задаёт dtype CLIP, VAE, latent storage или финального изображения автоматически.

Для сравнения режимов создавайте отдельные ветви только по необходимости. Несколько активных dtype-вариантов одной большой модели могут вызывать перезагрузки и перераспределение памяти.

## Входы

- `model` — исходный `MODEL`.
- `dtype` — advanced combo: `default`, `fp32`, `fp16`, `bf16`.

`default` переводится в `None` и возвращает выбор внутренней логике ComfyUI/модели. Это не обязательно текущий dtype весов checkpoint и не синоним fp16.

## Выход

Выход — cloned `MODEL` с настройкой compute dtype. При fp32/fp16/bf16 флаг принудительного cast включён. При default patch содержит `None`, но новый clone всё равно является отдельной ветвью.

Нода ничего не вычисляет на весах в момент создания fragment сама по себе; фактическое приведение происходит при загрузке/исполнении модели через `ModelPatcher`.

## Как выбирается dtype

Helper `string_to_torch_dtype` имеет три явные ветви: fp32, fp16 и bf16. Любая другая строка возвращает `None`; UI обычно ограничивает значения combo, но программный вызов может передать другое имя и фактически получить default.

`set_model_compute_dtype` записывает dtype под именем `manual_cast_dtype`. Для ненулевого объекта dtype включается `force_cast_weights`; затем UUID patches меняется. Это объясняет, почему переключение может заставить ComfyUI перезагрузить или пересобрать модельную ветвь.

## Параметры и настройка

Используйте `default`, пока нет конкретной проблемы или измерительной задачи. `fp32` может помочь исследовать численную нестабильность, но обычно требует больше памяти и времени. `fp16` и `bf16` зависят от поддержки устройства и операций; меньшее число бит не гарантирует меньший peak VRAM во всех графах.

Не выбирайте dtype по названию GPU без проверки. Запустите один и тот же короткий workflow, сравните загрузку, peak memory, время и конечность выходов. На CPU или неподдерживаемом backend отдельные операции могут откатиться, замедлиться либо завершиться ошибкой.

## Проверенный пример

Fragment Wizard выбирает `fp32` и подключает patched модель к `CFGGuider`. Positive и negative conditioning остаются внешними. Это диагностический вариант: он показывает правильный порядок, но не утверждает, что fp32 лучше для конкретной модели.

В полном official wheel 0.1.42 точных `ModelComputeDtype` нет. Exact patch выполнен для всех четырёх значений: подтверждены `None`, `torch.float32`, `torch.float16` и `torch.bfloat16`. Реальная загрузка больших весов и устройство-специфический benchmark не выполнялись. Редактор пока не проверил материал вручную.

## Частые ошибки

- `default` принимается за fp16, хотя это отсутствие ручного dtype.
- Пользователь ждёт перекодированный checkpoint на диске.
- Compute dtype модели путают с dtype VAE, CLIP или latent.
- Явный fp32 включается на малой VRAM без оценки перезагрузки и peak memory.
- bf16 выбирается на устройстве без полноценной поддержки.
- Несколько dtype-ветвей запускаются по очереди и вызывают повторные reload.

## Ограничения и производительность

Сам patch дешёвый, но его последствия могут быть дорогими: `force_cast_weights` и новый patches UUID способны вызвать полное приведение/перезагрузку модели. Расход памяти, скорость и точность зависят от архитектуры, устройства, backend и остальных patches.

Нода не проверяет поддержку dtype заранее и не измеряет итог. Она относится к `advanced/debug`, поэтому безопасный процесс — короткий probe, затем профиль на целевом workflow, а не постоянное принудительное значение по умолчанию.

## Совместимость и источники проверки

Проверено на ComfyUI 0.32.0 и frontend 1.48.7. Нода не имеет source-флагов deprecated/experimental/API, формальной замены нет. Runtime search aliases: `model precision`, `change dtype`.

Embedded docs 0.5.9 правильно перечисляют варианты, но не объясняют `None` для default, `force_cast_weights`, новый patches UUID и возможную перезагрузку. Эти детали проверены по `node_helpers.py` и `model_patcher.py`.

### Источники

- [ModelComputeDtype в ComfyUI v0.32.0](https://github.com/Comfy-Org/ComfyUI/blob/c2bcbecd82ec5ae66594340b395c24ef0217b238/comfy_extras/nodes_model_advanced.py#L333-L349)
- [Преобразование строки в torch dtype](https://github.com/Comfy-Org/ComfyUI/blob/c2bcbecd82ec5ae66594340b395c24ef0217b238/node_helpers.py#L77-L84)
- [ModelPatcher set_model_compute_dtype](https://github.com/Comfy-Org/ComfyUI/blob/c2bcbecd82ec5ae66594340b395c24ef0217b238/comfy/model_patcher.py#L740-L746)
- [Embedded docs 0.5.9 для ModelComputeDtype](https://github.com/Comfy-Org/embedded-docs/blob/1d258cf6e374d60d138a2bfcd273c7e11f750ef9/comfyui_embedded_docs/docs/ModelComputeDtype/en.md)
