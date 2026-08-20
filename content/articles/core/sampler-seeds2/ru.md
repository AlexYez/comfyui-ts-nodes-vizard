# SamplerSEEDS2: двухстадийный SEEDS-2 и exponential Heun

`SamplerSEEDS2` создаёт двухстадийный sampler в logSNR-времени. Он поддерживает коэффициенты `phi_1` и `phi_2`, стохастическую SDE-составляющую и настраиваемое положение промежуточной оценки. Несколько специальных наборов параметров совпадают с отдельными именами exponential Heun в реестре ComfyUI.

## 1. Что делает нода

Нода передаёт `solver_type`, `eta`, `s_noise` и `r` в фабрику `seeds_2`. На каждом ненулевом переходе алгоритм сначала вычисляет denoised в исходной точке, строит промежуточный state на доле `r`, второй раз вызывает модель и объединяет две оценки.

Это конструктор `SAMPLER`, а не исполняющая нода. Для работы нужны внешний `SamplerCustom` или `SamplerCustomAdvanced`, SIGMAS, модельный guidance, NOISE и LATENT.

## 2. Место в графе

Выход подключают в порт `sampler`. SEEDS-2 особенно чувствителен к sigma/logSNR-преобразованию модели, поэтому scheduler и GUIDER должны принадлежать одному модельному pipeline.

Для фиксированной конфигурации можно выбрать отдельное имя через `KSamplerSelect`: `exp_heun_2_x0` или `exp_heun_2_x0_sde`. `SamplerSEEDS2` полезен, когда нужны произвольные `r`, eta или выбор `phi_1`.

## 3. Входы

- `solver_type` — `phi_1` либо `phi_2`.
- `eta = 1` — stochastic strength, диапазон `0…100`.
- `s_noise = 1` — множитель SDE-noise, диапазон `0…100`.
- `r = 0.5` — относительное положение промежуточной стадии, диапазон `0.01…1`.

`r` не является denoise strength и не задаёт процент всей траектории. Это доля каждого текущего перехода lambda, на которой выполняется второй model evaluation.

## 4. Выход

Единственный выход `SAMPLER` хранит функцию `sample_seeds_2` и четыре options. Нода имеет search aliases `sde` и `exp heun`, но они не являются runtime-идентификаторами и не участвуют в resolver Wizard.

Описание runtime фиксирует три соответствия: defaults дают `seeds_2`; `phi_2, r = 1, eta = 0` соответствует `exp_heun_2_x0`; тот же набор с eta 1 и `s_noise = 1` — `exp_heun_2_x0_sde`.

## 5. Как работает

Алгоритм переводит SIGMAS в half-log-SNR и корректирует первую sigma под model sampling. На промежуточной lambda, полученной через `lerp(lambda_s, lambda_t, r)`, он строит `x_2` и получает `denoised_2`.

В ветви `phi_1` две оценки смешиваются через коэффициент `1 / (2r)`. В `phi_2` используются две phi-функции и отдельные веса `b1`, `b2`. Если `eta > 0` и effective `s_noise > 0`, шум добавляется в промежуточной и конечной частях перехода.

`s_noise` предварительно умножается на `model_sampling.noise_scale`. На переходе к sigma 0 промежуточного вызова нет: результатом становится первый `denoised` текущего шага.

## 6. Параметры и настройка

Для обычного SEEDS-2 оставьте `phi_1`, eta 1, `s_noise 1`, `r 0.5`. Для детерминированного exponential Heun используйте точный набор `phi_2`, eta 0, `r 1`; значение `s_noise` при eta 0 не влияет на injection, но recipe сохраняет 1 для читаемого совпадения с описанием ноды.

Не ставьте малый `r` без причины: коэффициент `1 / (2r)` растёт, а промежуточная точка прижимается к началу перехода. Верхняя граница eta 100 лишь валидируется runtime и не означает численную устойчивость.

## 7. Проверенный пример

Recipe `Детерминированный exponential Heun через SEEDS-2` задаёт `solver_type = phi_2`, `eta = 0`, `s_noise = 1`, `r = 1` и подключает sampler к `SamplerCustomAdvanced`. Этот набор прямо указан в runtime description как эквивалент `exp_heun_2_x0`.

Полный scan 512 официальных JSON и всех subgraph не нашёл `SamplerSEEDS2`, поэтому fragment не назван официальным workflow. Exact-source проба проверяет все options и отсутствие noise injection при eta 0; полный model pipeline не исполнялся.

## 8. Частые ошибки

- Принимают `r` за denoise или долю всего workflow.
- Ожидают один model call на каждый ненулевой переход; SEEDS-2 обычно делает два.
- Считают `s_noise = 0` и `eta = 0` полностью одинаковыми во всех формулах: eta участвует и в deterministic coefficients.
- Используют `phi_2, r = 1`, но забывают eta 0 для deterministic exponential Heun.
- Переносят SIGMAS от другой модели без проверки logSNR-преобразования.
- Не учитывают model-specific `noise_scale`.
- Путают search alias `exp heun` с точным `NodeId`.

## 9. Ограничения и производительность

На каждом обычном переходе выполняются две оценки модели, поэтому при одинаковой длине SIGMAS SEEDS-2 обычно дороже однооценочных методов. На финальном переходе к нулю остаётся одна оценка. Промежуточные state и denoised требуют дополнительной памяти.

Формулы используют экспоненты, phi-функции и half-log-SNR. Необычные SIGMAS, крайние eta или маленький r могут усилить погрешность. Алгоритм проверяет только имя `solver_type`; остальные значения ограничены UI-схемой, но не проходят дополнительную проверку устойчивости внутри execute.

## 10. Совместимость и источники

Статья сверена с ComfyUI `0.32.0`, frontend `1.48.7`, commit `c2bcbecd82ec5ae66594340b395c24ef0217b238`, embedded docs `0.5.9` и workflow templates `0.1.42`. Нода не experimental и не deprecated; formal replacement отсутствует.

Embedded docs правильно перечисляет три представимых sampler, но не объясняет две model evaluations, точную роль r, условие noise injection, model `noise_scale` и упрощённый финальный переход.

- [SamplerSEEDS2](https://github.com/Comfy-Org/ComfyUI/blob/c2bcbecd82ec5ae66594340b395c24ef0217b238/comfy_extras/nodes_custom_sampler.py#L681-L713)
- [sample_seeds_2 и exponential Heun wrappers](https://github.com/Comfy-Org/ComfyUI/blob/c2bcbecd82ec5ae66594340b395c24ef0217b238/comfy/k_diffusion/sampling.py#L1592-L1663)
- [Official workflow templates 0.1.42](https://pypi.org/project/comfyui-workflow-templates-json/0.1.42/)
