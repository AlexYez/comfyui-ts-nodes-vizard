# ModelSamplingSD3: flow-семплирование для SD3-подобных моделей

`ModelSamplingSD3` заменяет объект `model_sampling` внутри клона `MODEL`. Патч задаёт flow-шкалу sigma, тип предсказания `CONST` и коэффициент `shift`; веса модели он не меняет.

## Выход — клон с новым model_sampling

Метод сначала вызывает `model.clone()`, затем добавляет в клон патч объекта с ключом `model_sampling`. Исходный `MODEL` остаётся отдельной ветвью графа.

Это важно при разветвлении: следующая нода получает новую sampling-конфигурацию только через выход `ModelSamplingSD3`. Соединение с исходным `MODEL` обходит патч.

## Патч сочетает DiscreteFlow и CONST

Внутренний класс наследует `ModelSamplingDiscreteFlow` и `CONST`. `CONST.calculate_input` передаёт noisy latent в модель без дополнительного деления, а denoised вычисляет как `model_input − model_output · sigma`.

При добавлении шума `CONST` смешивает `sigma · noise` и `(1 − sigma) · latent_image`. Поэтому эта нода меняет не только список sigma: она заменяет весь объект, который описывает вход, предсказание и шумовую шкалу.

## shift входит в рациональное преобразование времени

`ModelSamplingDiscreteFlow.sigma` применяет `time_snr_shift(shift, t) = shift·t / (1 + (shift−1)·t)`. При `shift = 1` функция оставляет `t` без изменений; положительное значение выше единицы поднимает внутренние точки.

В `/object_info` значение по умолчанию равно 3, диапазон — 0–100, шаг — 0,01. Например, для `t = 0,5` и `shift = 3` получается `sigma = 0,75`. Это не та же формула, что у `ModelSamplingFlux`: там числовой shift сначала проходит через экспоненту.

## multiplier задаёт единицы времени

`ModelSamplingSD3.patch` передаёт `multiplier = 1000`. Метод `timestep(sigma)` поэтому возвращает `sigma · 1000`, а обратная функция перед shift делит timestep на 1000.

`ModelSamplingAuraFlow` наследует тот же патч, но вызывает его с multiplier 1. Sigma-сетки при одинаковом положительном shift совпадают, однако значения timestep, которые видит модель, различаются в тысячу раз.

## Sigma-сетка содержит тысячу точек

`set_parameters` строит `t = 1/1000 … 1000/1000`, применяет shift и сохраняет результат как `sigmas`. Верхняя точка равна 1 для любого положительного shift; нижняя зависит от него.

`percent_to_sigma` использует ту же функцию для внутренних долей. На краях он возвращает служебные 1 и 0, а не обязательно сохранённые `sigma_max` и `sigma_min`.

## shift = 0 создаёт NaN на верхнем краю

Runtime разрешает ноль, но формула при `t = 1` превращается в `0/0`. Проверка закреплённого кода подтвердила: первые 999 значений становятся нулевыми, а последний элемент sigma-сетки — `NaN`.

Не используйте нулевой shift как «отключение» патча. Для нейтрального преобразования времени нужен `shift = 1`; совместимость такого значения с конкретной моделью всё равно следует проверять отдельно.

## Исходный noise_scale переносится в патч

Перед заменой нода получает прежний `model_sampling`. Если у него есть атрибут `noise_scale`, значение копируется через `set_noise_scale`.

Это отличает SD3/AuraFlow-патч от `ModelSamplingFlux` и `ModelSamplingLTXV` в этой версии: те создают новый Flux sampling без явного переноса прежнего `noise_scale`.

## В официальных шаблонах shift зависит от модели

Полный подсчёт в шаблонах 0.1.42 нашёл 82 экземпляра: 46 в корневых графах и 36 в подграфах, всего в 50 файлах. Включена 71 нода, ещё 11 переведены в bypass; в виджете встречаются 2, 3, 5, 6, 7 и 8, включая близкие варианты после сериализации чисел с плавающей точкой.

Чаще всего выход идёт в `KSampler` или `KSamplerAdvanced`; также встречаются `CFGGuider`, `SamplerCustom`, `LatentApplyOperationCFG` и другие model-патчи. Эти значения относятся к конкретным архитектурам и не образуют универсальную шкалу качества.

## Hunyuan Video меняет только ветвь guider

В `hunyuan_video_text_to_video` `UNETLoader #12` разветвляется: одна связь идёт прямо в `BasicScheduler #17`, вторая — через `ModelSamplingSD3 #67` с `shift = 7` в `BasicGuider #22`. Затем scheduler и guider входят в `SamplerCustomAdvanced #13`.

Учебный фрагмент сохраняет только подтверждённую ветвь `MODEL → ModelSamplingSD3(7) → BasicGuider`. Он не утверждает, что shift 7 подходит другой модели, и отдельно описывает ветвь scheduler из официального графа.

## Проверка охватывает математику, но не генерацию

На подставной модели метод `patch` подтвердил клонирование, multiplier 1000, перенос `noise_scale` и установку выбранного shift. Отдельно исполнены закреплённые `time_snr_shift`, sigma-сетка и `CONST` на синтетических тензорах.

Веса Hunyuan Video не загружались, recipe целиком не исполнялся, поэтому `exampleExecuted=false`. Перед sampling проверьте модельную архитектуру, положительный shift и то, какая ветвь `MODEL` приходит в scheduler и guider. Редактор пока не проверил материал вручную.

## Источники

- [ModelSamplingSD3 в ComfyUI v0.32.0](https://github.com/Comfy-Org/ComfyUI/blob/c2bcbecd82ec5ae66594340b395c24ef0217b238/comfy_extras/nodes_model_advanced.py#L119-L147)
- [DiscreteFlow и time_snr_shift](https://github.com/Comfy-Org/ComfyUI/blob/c2bcbecd82ec5ae66594340b395c24ef0217b238/comfy/model_sampling.py#L279-L327)
- [CONST prediction](https://github.com/Comfy-Org/ComfyUI/blob/c2bcbecd82ec5ae66594340b395c24ef0217b238/comfy/model_sampling.py#L86-L103)
- [Официальный граф Hunyuan Video](https://github.com/Comfy-Org/workflow_templates/blob/cca1ea5ea4560108ecc2f44dee951f41ea433062/templates/hunyuan_video_text_to_video.json)
- [Embedded docs 0.5.9](https://github.com/Comfy-Org/embedded-docs/blob/1d258cf6e374d60d138a2bfcd273c7e11f750ef9/comfyui_embedded_docs/docs/ModelSamplingSD3/en.md)
