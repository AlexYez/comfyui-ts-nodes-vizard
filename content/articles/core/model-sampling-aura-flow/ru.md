# ModelSamplingAuraFlow: DiscreteFlow с timestep 0–1

`ModelSamplingAuraFlow` создаёт клон `MODEL` с flow-семплированием для временной шкалы AuraFlow. Нода наследует реализацию `ModelSamplingSD3`, но передаёт `multiplier = 1` вместо 1000 и использует `shift = 1,73` по умолчанию.

## Нода переиспользует SD3-патч

`patch_aura` вызывает `ModelSamplingSD3.patch(model, shift, multiplier=1.0)`. Поэтому результат сочетает `ModelSamplingDiscreteFlow` и тип предсказания `CONST`, а исходный `MODEL` не меняется.

Выход — новая ветвь с заменённым объектом `model_sampling`. Название AuraFlow не выполняет проверку архитектуры входных весов.

## multiplier 1 меняет единицы времени

Внутренний `timestep(sigma)` возвращает `sigma · multiplier`. Для AuraFlow multiplier равен 1, поэтому диапазон timestep следует flow-шкале 0–1.

У `ModelSamplingSD3` multiplier равен 1000. При одинаковом положительном shift их sigma-сетки совпадут, но модель получит timestep в других единицах; поэтому две ноды не взаимозаменяемы по одному только значению shift.

## shift применяет time_snr_shift

Формула равна `shift·t / (1 + (shift−1)·t)`. Значение 1 оставляет шкалу линейной, а значение 1,73 по умолчанию поднимает внутренние sigma относительно исходного `t`.

В `/object_info` разрешён диапазон 0–100 с шагом 0,01. Параметр входит в формулу напрямую. В `ModelSamplingFlux` и `ModelSamplingLTXV` аналогично названное число используется как `mu` внутри `exp(mu)`, поэтому переносить настройки между семействами нельзя.

## CONST задаёт flow-предсказание

Модель получает noisy latent без нормализации через sigma. Denoised вычисляется как `model_input − model_output · sigma`, а стартовый шум смешивается с latent по весам `sigma` и `1 − sigma`.

Scheduler и sampler читают эти правила из изменённого `MODEL`. Одного совпадения типа сокета `MODEL` недостаточно: важна модельная архитектура и ожидаемая параметризация.

## Нулевой shift не отключает преобразование

Runtime разрешает `shift = 0`, но при последней точке `t = 1` формула даёт `0/0`. Проверка закреплённого кода получила `NaN` в верхнем элементе sigma-сетки.

Нейтральная математическая функция соответствует `shift = 1`, а не нулю. Это не рекомендация для любой AuraFlow-модели: конкретное значение должно следовать её графу или документации.

## noise_scale наследуется от исходной модели

Общий SD3-патч проверяет прежний `model_sampling`. Если у него есть `noise_scale`, новый объект получает то же число.

Так сохраняется модельная настройка амплитуды шума. Визуально похожий новый патч на Flux/LTXV в v0.32.0 не выполняет такого копирования явно.

## В официальных шаблонах shift зависит от модели

Полный рекурсивный подсчёт нашёл 72 ноды: 15 в корневых графах и 57 в подграфах, всего в 56 файлах. Включены 70 нод, ещё 2 переведены в bypass. Чаще всего сериализованы 3, 3,1 и 1; также встречаются 3,16, 4, 6 и 7.

Выход обычно идёт в `KSampler` или `CFGNorm`. Реже он разветвляется в guider и scheduler. Эти настройки принадлежат Hunyuan3D, ACE, Chroma, Qwen Image и другим конкретным ветвям, а не единому набору настроек AuraFlow.

## Chroma разветвляет один изменённый MODEL

В `image_chroma_text_to_image` `UNETLoader #731` входит в `ModelSamplingAuraFlow #701` с `shift = 1`. Выход идёт одновременно в `CFGGuider #694` с cfg 3,5 и `BasicScheduler #734` со значениями `beta`, 26, 1.

Оба результата затем подключены к `SamplerCustomAdvanced #747`. Такое разветвление гарантирует, что guider и scheduler используют один объект `model_sampling`.

## Учебный фрагмент сохраняет подтверждённую ветвь

Фрагмент содержит `ModelSamplingAuraFlow(1)`, `CFGGuider(3,5)` и `BasicScheduler(beta, 26, 1)`. Исходный `MODEL` и два conditioning подключаются извне; sampler, noise и latent остаются внешними.

Это сокращённая топология из официального графа Chroma, а не универсальный рецепт для моделей, где в шаблонах используется shift 3 или 3,1.

## Проверка ограничена конфигурацией sampling

Метод `patch` на подставной модели подтвердил клонирование, multiplier 1, перенос `noise_scale` и установку выбранного shift. Формула и sigma-сетка исполнены на CPU без весов.

Chroma-модель не загружалась, полный фрагмент не выполнялся, поэтому `exampleExecuted=false`. Перед запуском проверьте происхождение модели, положительный shift и одинаковую изменённую ветвь у scheduler и guider. Редактор пока не проверил материал вручную.

## Источники

- [ModelSamplingAuraFlow в ComfyUI v0.32.0](https://github.com/Comfy-Org/ComfyUI/blob/c2bcbecd82ec5ae66594340b395c24ef0217b238/comfy_extras/nodes_model_advanced.py#L148-L160)
- [Наследуемый SD3-патч](https://github.com/Comfy-Org/ComfyUI/blob/c2bcbecd82ec5ae66594340b395c24ef0217b238/comfy_extras/nodes_model_advanced.py#L119-L147)
- [DiscreteFlow и time_snr_shift](https://github.com/Comfy-Org/ComfyUI/blob/c2bcbecd82ec5ae66594340b395c24ef0217b238/comfy/model_sampling.py#L279-L327)
- [Официальный граф Chroma](https://github.com/Comfy-Org/workflow_templates/blob/cca1ea5ea4560108ecc2f44dee951f41ea433062/templates/image_chroma_text_to_image.json)
- [Embedded docs 0.5.9](https://github.com/Comfy-Org/embedded-docs/blob/1d258cf6e374d60d138a2bfcd273c7e11f750ef9/comfyui_embedded_docs/docs/ModelSamplingAuraFlow/en.md)
