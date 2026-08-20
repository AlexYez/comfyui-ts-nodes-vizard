# SamplerEulerAncestral: Euler ancestral с eta и s_noise

`SamplerEulerAncestral` создаёт объект `SAMPLER` для алгоритма Euler ancestral и открывает две расширенные настройки: `eta` и `s_noise`. Расписание `SIGMAS`, модель, шум и само исполнение приходят из других нод.

## 1. Что делает нода

Нода вызывает фабрику `ksampler("euler_ancestral", options)` и помещает в options значения `eta` и `s_noise`. Полученный объект выполняет шаг Euler к предсказанному clean sample, а между незавершающими шагами может добавлять ancestral noise.

Это конструктор алгоритма, а не sampler-runner. Без `SamplerCustom` или `SamplerCustomAdvanced` выход ничего не вычисляет.

## 2. Место в графе

Выход подключают в порт `sampler` у custom-sampling ноды. Рядом требуются `SIGMAS`, NOISE/LATENT и guider либо model+conditioning — в зависимости от выбранного исполнителя.

Если нужны стандартные `eta = 1` и `s_noise = 1`, тот же алгоритм можно выбрать через `KSamplerSelect(euler_ancestral)`. Отдельная нода нужна, когда параметры ancestral renoise должны быть видны в графе и сохранены явно.

## 3. Входы

- `eta` — сила ancestral-разбиения шага; диапазон runtime `0…100`, значение по умолчанию `1`.
- `s_noise` — множитель добавляемого случайного тензора; диапазон `0…100`, значение по умолчанию `1`.

Оба параметра помечены как advanced. Нода не принимает seed: конкретный рисунок шума предоставляет sampling-путь через noise sampler. Число и положение шагов задаёт внешний `SIGMAS`.

## 4. Выход

Единственный выход имеет тип `SAMPLER`. Он хранит ссылку на `euler_ancestral` и options `eta`, `s_noise`. Это не LATENT, не NOISE и не изображение.

В ComfyUI есть две низкоуровневые ветви: обычная для diffusion sampling и отдельная RF-ветвь, когда model sampling имеет тип `CONST`. Выбор происходит во время исполнения по модели, а не при создании ноды.

## 5. Как работает

В обычной ветви модель сначала предсказывает denoised sample. `get_ancestral_step` делит переход к следующей sigma на детерминированную часть `sigma_down` и шумовую `sigma_up` с учётом `eta`. Euler-шаг ведёт к `sigma_down`, после чего добавляется случайный тензор, умноженный на `s_noise * sigma_up`. На последнем переходе к нулю возвращается denoised sample без нового шума.

При `eta = 0` величина `sigma_up` становится нулевой, и ancestral renoise исчезает. `s_noise = 0` тоже зануляет добавляемый тензор, но не меняет само разбиение sigma, вычисленное из eta. В RF/CONST-ветви формулы другие, а `s_noise` дополнительно умножается на `model_sampling.noise_scale`.

## 6. Параметры и настройка

Без проверенного workflow оставляйте `eta = 1` и `s_noise = 1`. Снижайте `eta`, если нужно уменьшить стохастическое повторное зашумление между шагами. `eta = 0` делает этот участок детерминированным относительно ancestral noise, но весь pipeline всё равно может зависеть от исходного NOISE и модельных операций.

`s_noise` масштабирует только добавляемый шум. Значение выше 1 усиливает его и способно резко изменить результат; верхняя граница 100 — технический runtime-диапазон, а не рекомендация. Настройка не заменяет выбор scheduler и не увеличивает число шагов.

## 7. Проверенный пример

Recipe `LTX: Euler ancestral без повторного зашумления` переносит точный участок трёх официальных LTX workflow: `SamplerEulerAncestral(eta = 0, s_noise = 1) → SamplerCustomAdvanced`. В `template_ltx2_3_style_transition` рядом стоят `RandomNoise`, `CFGGuider`, `ManualSigmas` и video latent; используется выход `denoised_output` sampler.

Полный recursive census workflow templates 0.1.42 нашёл три экземпляра ноды, все в subgraph, все с widgets `[0, 1]` и все подключены к `SamplerCustomAdvanced`. Конструктор и математические ветви проверены по exact source; полный LTX workflow с весами не исполнялся.

## 8. Частые ошибки

- Считают `eta` числом или размером шагов. Шаги задаёт `SIGMAS`.
- Ожидают, что `eta = 0` удалит исходный NOISE. Оно убирает ancestral renoise между шагами.
- Полагают, что `s_noise = 0` и `eta = 0` математически тождественны во всех ветвях.
- Подключают выход к порту `noise` вместо `sampler`.
- Переносят параметры из diffusion workflow в flow/CONST модель без проверки отдельной ветви.
- Используют экстремальные значения только потому, что runtime разрешает диапазон до 100.

## 9. Ограничения и производительность

Сама нода почти бесплатна; вычисления начинаются внутри исполняющего sampler. Стоимость определяется моделью, формой latent и длиной SIGMAS. Ancestral noise требует генерации и сложения дополнительного тензора на каждом подходящем переходе, но это обычно значительно дешевле модельного вызова.

Результат зависит от внешнего noise sampler и его seed. Даже при `eta = 0` смена начального NOISE меняет траекторию. При `CONST` model sampling действует отдельная RF-формула и model-specific `noise_scale`, поэтому численно одинаковые настройки не обещают одинаковый характер между семействами моделей.

## 10. Совместимость и источники

Статья сверена с ComfyUI `0.32.0`, frontend `1.48.7`, commit `c2bcbecd82ec5ae66594340b395c24ef0217b238`, embedded docs `0.5.9` и workflow templates `0.1.42`. Нода не experimental и не deprecated; formal replacement отсутствует.

Embedded docs называет `eta` одновременно управлением «размером шага и стохастичностью». В реализации позиции шагов приходят из SIGMAS, а eta управляет ancestral-разбиением перехода и повторным шумом. Документация также не описывает RF/CONST-ветвь и model `noise_scale`.

- [SamplerEulerAncestral в ComfyUI v0.32.0](https://github.com/Comfy-Org/ComfyUI/blob/c2bcbecd82ec5ae66594340b395c24ef0217b238/comfy_extras/nodes_custom_sampler.py#L494-L522)
- [Euler ancestral: обычная и RF-ветви](https://github.com/Comfy-Org/ComfyUI/blob/c2bcbecd82ec5ae66594340b395c24ef0217b238/comfy/k_diffusion/sampling.py#L216-L267)
- [Official workflow templates 0.1.42](https://pypi.org/project/comfyui-workflow-templates-json/0.1.42/)
