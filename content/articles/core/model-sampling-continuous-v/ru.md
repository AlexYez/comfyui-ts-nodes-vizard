# ModelSamplingContinuousV: непрерывная V-prediction шкала

`ModelSamplingContinuousV` клонирует `MODEL`, создаёт непрерывную log-spaced сетку sigma и трактует output модели как V-prediction. В отличие от дискретной схемы, связь sigma с timestep задаётся через `atan`, а обратное преобразование — через `tan`.

## Что делает нода

Patch соединяет базу `ModelSamplingContinuousV` с параметризацией `V_PREDICTION`. Между `sigma_min` и `sigma_max` строятся 1000 значений. `sigma_data` всегда равен 1, после чего новый sampling-объект записывается в клон модели.

Нода не обучает модель выдавать velocity. Она подходит только весам, для которых непрерывная V-параметризация предусмотрена архитектурой или training setup. Самый ясный системный пример в ComfyUI 0.32.0 — Stable Audio: его модельный класс по умолчанию использует `V_PREDICTION_CONTINUOUS`.

## Место в графе

Ставьте ноду после загрузки `MODEL` и до всех sampling-потребителей. Выход должен одновременно идти в guider и в model-aware scheduler. Если одна ветвь использует patched модель, а другая исходную, числовая шкала и формула предсказания расходятся.

Для Stable Audio conditioning, latent и VAE остаются отдельными сущностями. Этот patch не заменяет `ConditioningStableAudio`, `EmptyLatentAudio` или `VAEDecodeAudio` и не проверяет sample rate либо длительность.

## Входы

- `model` — модель, которая будет клонирована.
- `sampling` — единственный вариант `v_prediction`. Combo существует для единого интерфейса, но выбора между несколькими формулами нет.
- `sigma_max` — по умолчанию 500, диапазон 0–1000.
- `sigma_min` — по умолчанию 0,03, диапазон 0–1000.

Обе границы advanced, допускают точный дробный ввод и не округляются интерфейсом. Runtime не требует положительности и правильного порядка, хотя исходный расчёт требует `log(sigma)`.

## Выход

Выход имеет тип `MODEL` и содержит новый object patch `model_sampling`. Исходная ветвь не меняется. Внутри создаётся 1000 sigma, а `sigma_min` и `sigma_max` читаются как первый и последний элементы тензора.

При стандартных 0,03 и 500 значения идут по возрастанию. Из-за float32 верхняя точка в probe равна примерно 500,00006, а обратный round-trip `sigma → timestep → sigma` для 500 дал примерно 499,9869. Это ожидаемая численная погрешность `atan/tan`, а не изменение настройки пользователем.

## Как работает V-предсказание

Перед моделью input масштабируется через `sqrt(sigma² + sigma_data²)`. Denoised для V-prediction сочетает model input и model output с коэффициентами, зависящими от sigma. При `sigma_data = 1` вклад input равен `1 / (sigma² + 1)`, а вклад velocity масштабируется `sigma / sqrt(sigma² + 1)`.

Временная координата вычисляется как `atan(sigma) / π * 2`; обратное преобразование — `tan(timestep * π / 2)`. Сетка для совместимости всё равно хранится в log-space между пользовательскими границами. Scheduler может читать её пределы или использовать эти преобразования.

## Параметры и настройка

Используйте `0 < sigma_min < sigma_max`. Значение ноль разрешено widget-схемой, но `math.log(0)` завершает выполнение `ValueError`. Равные положительные границы дают плоский ряд, а обратный порядок — убывающий массив без предупреждения.

Stable Audio в закреплённом source задаёт `sigma_max = 500` и `sigma_min = 0,03` и уже создаёт continuous V sampling при загрузке. Ручная нода с теми же значениями обычно ничего полезного не добавляет. Она нужна, если предыдущий patch заменил sampling или вы сознательно исследуете другой диапазон.

## Проверенный пример

Рецепт Wizard фиксирует системные значения Stable Audio — 500 и 0,03 — и подключает patched `MODEL` к `BasicScheduler`. Это показывает правильный порядок и общий объект модели. Дальше пользователь подключает conditioning, sampler и audio latent своей схемы.

В 512 JSON официальных workflow templates 0.1.42 точной ноды `ModelSamplingContinuousV` нет. При этом реальные Stable Audio модели используют тот же sampling-класс автоматически; это подтверждено `model_base.py` и `supported_models.py`, а не сериализованной patch-нодой. Exact patch и `atan/tan` round-trip исполнены без весов. Полный audio sampling не запускался. Редактор пока не проверил материал вручную.

## Частые ошибки

- Patch применяется к epsilon-модели только потому, что значения sigma выглядят знакомо.
- Ноль в `sigma_min` принимается за законный предел, хотя логарифм не определён.
- Границы меняются местами и создают обратный внутренний ряд.
- Для официальной Stable Audio модели добавляется дублирующий patch без причины.
- Scheduler и guider получают разные версии `MODEL`.
- От patch-ноды ожидают готовый звук или `SIGMAS`, хотя выход — снова `MODEL`.

## Ограничения и производительность

Создание тысячаточечной сетки и object patch недороги по сравнению с diffusion inference. Clone создаёт отдельную конфигурационную ветвь; он не означает полное копирование всех весов в новую память в момент вызова.

Погрешность обратного `tan` растёт около верхней границы временной координаты, что видно на sigma 500. Нода не проверяет model family и не оценивает устойчивость sampler на выбранном диапазоне. При тестах меняйте один параметр за раз.

## Совместимость и источники проверки

Проверочная пара — ComfyUI 0.32.0 и frontend 1.48.7. Нода не experimental, не deprecated и не API-only; Node Replacement API её не заменяет. Runtime предлагает только `v_prediction`.

Embedded docs 0.5.9 верно перечисляют default 500/0,03 и общий V-сценарий, но не предупреждают о нуле, обратных границах, численной погрешности и том, что Stable Audio уже получает этот sampling автоматически. Эти детали сверены с source и probe.

## Источники

- [ModelSamplingContinuousV в ComfyUI v0.32.0](https://github.com/Comfy-Org/ComfyUI/blob/c2bcbecd82ec5ae66594340b395c24ef0217b238/comfy_extras/nodes_model_advanced.py#L242-L276)
- [Непрерывная V sampling-математика](https://github.com/Comfy-Org/ComfyUI/blob/c2bcbecd82ec5ae66594340b395c24ef0217b238/comfy/model_sampling.py#L226-L278)
- [Stable Audio model class](https://github.com/Comfy-Org/ComfyUI/blob/c2bcbecd82ec5ae66594340b395c24ef0217b238/comfy/model_base.py#L799-L826)
- [Embedded docs 0.5.9 для ModelSamplingContinuousV](https://github.com/Comfy-Org/embedded-docs/blob/1d258cf6e374d60d138a2bfcd273c7e11f750ef9/comfyui_embedded_docs/docs/ModelSamplingContinuousV/en.md)
