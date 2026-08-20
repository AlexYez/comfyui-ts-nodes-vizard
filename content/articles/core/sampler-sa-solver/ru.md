# SamplerSASolver: стохастический Adams predictor-corrector

`SamplerSASolver` создаёт Stochastic Adams sampler с настраиваемыми порядками predictor и corrector. В отличие от большинства sampler-конструкторов, ему нужна `MODEL`: по ней нода переводит проценты SDE-интервала в конкретные sigma и строит функцию `tau`.

## 1. Что делает нода

Нода извлекает из модели `model_sampling`, вычисляет `start_sigma` и `end_sigma`, создаёт `tau_func` и передаёт её вместе с orders, `s_noise` и двумя boolean-режимами в `sa_solver`.

Сам SA-Solver хранит историю denoised-предсказаний и строит многопорядковые Adams-коэффициенты. Predictor оценивает следующую точку, corrector уточняет её на основе доступной истории.

## 2. Место в графе

`MODEL` входит в конструктор, а его выход `SAMPLER` идёт в `SamplerCustom` либо `SamplerCustomAdvanced`. При advanced-сборке GUIDER тоже содержит модель. Оба пути должны ссылаться на одну и ту же модельную конфигурацию: иначе tau-интервал будет рассчитан по одной sigma-шкале, а denoising выполнится по другой.

SIGMAS всё равно приходит в исполняющий sampler отдельно. Проценты здесь не создают расписание; они только отмечают участок существующей траектории, где `tau` ненулевой.

## 3. Входы

- `model` — источник `percent_to_sigma` и последующего model contract.
- `eta = 1` — значение tau внутри SDE-интервала; диапазон `0…10`.
- `sde_start_percent = 0.2`, `sde_end_percent = 0.8` — границы интервала `0…1`.
- `s_noise = 1` — амплитуда SDE-noise.
- `predictor_order = 3` — максимум порядка predictor, `1…6`.
- `corrector_order = 4` — максимум порядка corrector, `0…6`.
- `use_pece` — включает дополнительную Evaluate после Correct.
- `simple_order_2` — использует упрощённый вариант коэффициентов второго порядка.

Runtime не записывает явный `default` для boolean-полей; в recipe они заданы `false`, чтобы поведение не зависело от представления frontend.

## 4. Выход

Выход `SAMPLER` содержит имя `sa_solver` и options: `tau_func`, `s_noise`, predictor/corrector orders, `use_pece`, `simple_order_2`. Модель как объект внутрь options не копируется; она уже использована при построении замыкания tau.

При `eta <= 0` функция tau всегда возвращает ноль, то есть stochastic interval отключён. При положительном eta она возвращает это значение только когда `start_sigma >= sigma >= end_sigma`, включая обе границы.

## 5. Как работает

На каждом элементе SIGMAS модель оценивает `denoised` для текущего predicted state. История ограничивается максимальным из predictor и corrector order. Реально доступный порядок начинается с единицы и растёт по мере накопления предсказаний; возле конечного нуля он снова понижается для устойчивости.

Corrector не применяется на первом шаге. Без PECE он также пропускается на финальном переходе к нулю. При `use_pece = true` corrected state дополнительно прогоняется через модель и заменяет последнюю запись истории — это может добавить model call на переход.

Если следующая sigma не ноль, predictor использует Adams-коэффициенты. Внутри заданного tau-интервала добавляется SDE-noise. Его масштаб включает `s_noise` и model-specific `noise_scale`. На финальном переходе predicted state становится текущим denoised.

## 6. Параметры и настройка

Начните с интервала `0.2…0.8`, eta 1, orders 3/4 и выключенных boolean. Для детерминированного ODE-варианта поставьте eta 0; `s_noise` тогда не создаёт шум, потому что tau равен нулю.

Не меняйте порядок границ вслепую. `percent_to_sigma` обычно убывает по мере роста процента, и функция ожидает `start_sigma >= end_sigma`. Если проценты переставлены, условие tau может ни разу не выполниться; нода не сортирует их автоматически.

Высокие orders требуют достаточно длинной истории. На коротком расписании значения 5–6 часто не будут достигнуты, поскольку solver ограничивает порядок числом доступных точек и снижает его к концу.

## 7. Проверенный пример

Recipe `SA-Solver с интервалом SDE 20–80%` сохраняет точные defaults конструктора и соединяет его с `SamplerCustomAdvanced`. Одна MODEL подаётся в `SamplerSASolver`, а совместимый GUIDER — отдельно; NOISE, SIGMAS и LATENT также остаются внешними.

Полный recursive census 512 официальных JSON и всех subgraph не обнаружил `SamplerSASolver`. Fragment поэтому основан на source/runtime contract, а не заявлен официальным. Exact-source проба проверяет `percent_to_sigma`, inclusive tau-интервал, eta 0 и все factory options; модельный sampling не выполнялся.

## 8. Частые ошибки

- Подключают к sampler GUIDER одной модели, а в конструктор — другую MODEL.
- Считают проценты генератором SIGMAS. Они задают лишь stochastic interval.
- Меняют start/end местами и получают tau 0 на всей траектории.
- Ждут order 4 на первом шаге без истории.
- Включают PECE и не учитывают дополнительные model evaluations.
- Называют eta «размером шага», как в embedded docs; здесь это амплитуда tau внутри интервала.
- Полагают, что `s_noise > 0` создаст шум при eta 0.

## 9. Ограничения и производительность

Хранение нескольких denoised-тензоров увеличивает память пропорционально реально используемому order. PECE способен добавить модельную оценку на шагах с corrector, поэтому разница во времени существенно больше, чем стоимость самого вычисления коэффициентов.

Коэффициенты получают решением малых линейных систем по истории lambda. Слишком близкие точки, чрезмерный order или необычное расписание могут ухудшить численную устойчивость. Runtime-тип SIGMAS не подтверждает, что расписание разумно для выбранной MODEL.

## 10. Совместимость и источники

Статья сверена с ComfyUI `0.32.0`, frontend `1.48.7`, commit `c2bcbecd82ec5ae66594340b395c24ef0217b238`, embedded docs `0.5.9` и workflow templates `0.1.42`. Нода не experimental и не deprecated; formal replacement отсутствует.

Embedded docs перечисляет параметры, но ошибочно называет eta коэффициентом размера шага и не объясняет модельно-зависимый перевод процентов, inclusive tau, рост/снижение фактического order и дополнительные PECE evaluations.

- [SamplerSASolver](https://github.com/Comfy-Org/ComfyUI/blob/c2bcbecd82ec5ae66594340b395c24ef0217b238/comfy_extras/nodes_custom_sampler.py#L636-L678)
- [sample_sa_solver](https://github.com/Comfy-Org/ComfyUI/blob/c2bcbecd82ec5ae66594340b395c24ef0217b238/comfy/k_diffusion/sampling.py#L1734-L1841)
- [get_tau_interval_func](https://github.com/Comfy-Org/ComfyUI/blob/c2bcbecd82ec5ae66594340b395c24ef0217b238/comfy/k_diffusion/sa_solver.py#L103-L121)
