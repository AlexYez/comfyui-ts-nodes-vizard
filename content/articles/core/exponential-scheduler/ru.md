# ExponentialScheduler: равномерная сетка по log sigma

`ExponentialScheduler` выдаёт явную последовательность уровней шума от `sigma_max` до `sigma_min`. Ненулевые значения образуют геометрическую прогрессию: их логарифмы расположены на равных расстояниях.

## Нода строит SIGMAS без входа MODEL

У неё три поля: `steps`, `sigma_max` и `sigma_min`. Входного `MODEL` нет, поэтому границы не считываются из модели и не меняются вместе с `ModelSampling…`-патчами.

Выход `SIGMAS` можно передать в custom sampler. Совместимость выбранного диапазона с моделью внутри guider нода не проверяет.

## Формула линейна только в логарифмической шкале

Исходник вычисляет `linspace(log(sigma_max), log(sigma_min), steps)`, затем применяет `exp` к каждому элементу. При `steps > 1` отношение соседних ненулевых уровней постоянно:

`q = exp((log(sigma_min) - log(sigma_max)) / (steps - 1))`.

В обычном порядке границ `0 < q < 1`, поэтому каждое следующее значение равно предыдущему, умноженному на один и тот же коэффициент.

## Значения по умолчанию охватывают 14,614642–0,0291675

Оба поля advanced имеют runtime-диапазон 0–5000, шаг 0,01 и `round = false`. Значения по умолчанию совпадают с явными границами у `KarrasScheduler` и `PolyexponentialScheduler`.

При четырёх шагах probe точной функции получил примерно `[14,614643; 1,840031; 0,231666; 0,0291675; 0]`. В отличие от Karras с теми же границами, промежуточные точки образуют постоянное отношение.

## steps определяет число ненулевых точек

Runtime разрешает 1–10000, значение по умолчанию — 20. После `steps` ненулевых уровней функция добавляет отдельный ноль, поэтому стандартная длина равна `steps + 1`.

При `steps = 1` `linspace` содержит только начальный логарифм: результатом будут `sigma_max` и 0. Нижняя граница в последовательность не попадёт.

## Ноль разрешён UI, но запрещён логарифмом

Интерфейс допускает `sigma_min = 0` и `sigma_max = 0`. Формула вызывает `math.log`, а логарифм нуля в Python поднимает `ValueError: math domain error`.

Для этой ноды обе границы должны быть строго положительными. Схема runtime этого требования не выражает, поэтому проверять его нужно до запуска очереди.

## sigma_max ниже sigma_min разворачивает направление

Порядок границ не валидируется. Если поставить `sigma_max = 0,1`, `sigma_min = 1`, ненулевая часть будет возрастать примерно как `[0,1; 0,215; 0,464; 1]`, а затем перейдёт к нулю.

Для обычного денойзинга используйте `sigma_max > sigma_min > 0`. Обратный порядок не превращается автоматически в корректный «reverse sampling».

## rho здесь отсутствует

Кривая полностью определяется двумя границами и количеством шагов. `PolyexponentialScheduler` добавляет `rho` и искривляет положение в `log(sigma)`; `KarrasScheduler` интерполирует в пространстве степенного корня.

При `rho = 1` polyexponential-формула математически совпадает с exponential. В `float32` probe получил почти одинаковые, но не побитово равные числа из-за другого порядка операций.

## Для модели границы подбираются отдельно

`ExponentialScheduler` удобен, когда диапазон sigma известен заранее и его нужно воспроизвести явно. Если шкала должна следовать конкретному `MODEL`, безопаснее начать с `BasicScheduler`, который читает `model_sampling`.

При переносе графа между архитектурами не считайте значения по умолчанию универсальными. Сверяйте границы с sampling-конфигурацией модели и поведением guider.

## Официальный wheel не даёт готового примера

В 512 JSON wheel 0.1.42 просмотрены 496 root workflow и 272 `definitions.subgraphs`. Ни в одной из 768 областей нет exact type `ExponentialScheduler`.

Следовательно, значения recipe основаны на runtime defaults и pinned-формуле, а не извлечены из официального workflow. Это различие сохранено в research ledger.

## Fragment проверяет только scheduler-ветку

Fragment соединяет `ExponentialScheduler` со входом `sigmas` у `SamplerCustomAdvanced`. `NOISE`, `GUIDER`, `SAMPLER` и `LATENT` остаются внешними, поэтому это не полный workflow.

Exact-source probe проверил формулу, постоянное отношение, конечный ноль, `steps = 1`, ошибку при нулевой границе и возрастающую сетку при перестановке границ. Модельный sampling не выполнялся. Редактор пока не проверил материал вручную.

## Источники

- [ExponentialScheduler в ComfyUI v0.32.0](https://github.com/Comfy-Org/ComfyUI/blob/c2bcbecd82ec5ae66594340b395c24ef0217b238/comfy_extras/nodes_custom_sampler.py#L69-L88)
- [Формула `get_sigmas_exponential`](https://github.com/Comfy-Org/ComfyUI/blob/c2bcbecd82ec5ae66594340b395c24ef0217b238/comfy/k_diffusion/sampling.py#L19-L35)
- [Pinned-набор официальных workflow](https://github.com/Comfy-Org/workflow_templates/tree/cca1ea5ea4560108ecc2f44dee951f41ea433062/templates)
- [Embedded docs 0.5.9 для ExponentialScheduler](https://github.com/Comfy-Org/embedded-docs/blob/1d258cf6e374d60d138a2bfcd273c7e11f750ef9/comfyui_embedded_docs/docs/ExponentialScheduler/en.md)
