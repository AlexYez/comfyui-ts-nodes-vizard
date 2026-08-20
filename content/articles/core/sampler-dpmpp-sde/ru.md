# SamplerDPMPP_SDE: двухстадийный DPM++ SDE с параметром r

`SamplerDPMPP_SDE` создаёт объект `SAMPLER` для stochastic DPM++ SDE. В отличие от многошаговых 2M/3M вариантов он рассчитывает промежуточную стадию внутри текущего перехода; её положение задаёт `r`.

## 1. Что делает нода

При `noise_device = cpu` конструктор выбирает `dpmpp_sde`, при `gpu` — `dpmpp_sde_gpu`. В options передаются `eta`, `s_noise` и `r`.

Нода только настраивает алгоритм. Она не получает MODEL или LATENT, не строит `SIGMAS` и не запускает denoise. Все эти части сходятся позже в `SamplerCustom` или `SamplerCustomAdvanced`.

## 2. Место в графе

`SAMPLER` подключают к одноимённому входу custom-sampling ноды. Рядом нужны внешний scheduler, noise source, guider и latent. Параметр `r` не заменяет расписание: он выбирает внутреннюю точку каждого ненулевого перехода.

Через `KSamplerSelect` доступны стандартные имена `dpmpp_sde` и `dpmpp_sde_gpu`, но там нельзя отдельно записать `r`, `eta` и `s_noise` в одном специализированном узле. При defaults результат должен сравниваться на полном одинаковом графе, а не только по имени sampler.

## 3. Входы

- `eta: FLOAT` — коэффициент stochastic/SDE-части; default `1`, диапазон `0…100`, шаг `0,01`.
- `s_noise: FLOAT` — множитель двух возможных Brownian increments; default `1`, тот же диапазон и шаг.
- `r: FLOAT` — доля интервала half-log SNR для промежуточной стадии; default `0,5`, runtime разрешает `0…100`.
- `noise_device: COMBO` — `gpu` или `cpu`, в runtime они перечислены в таком порядке.

Все inputs помечены advanced. Значение `r = 0` формально проходит runtime schema, но exact алгоритм вычисляет `1 / (2 * r)`. Оно приводит к делению на ноль и не должно использоваться.

## 4. Выход

Выход один — `SAMPLER`. CPU-вариант хранит функцию `sample_dpmpp_sde`, GPU-вариант — wrapper, который создаёт Brownian tree с `cpu=False`, а затем вызывает ту же основную функцию.

В объект не входят seed, model или SIGMAS. Они передаются только в момент исполнения. Поэтому изменение settings ноды без повторного запуска consumer само по себе не создаёт изображение.

## 5. Как работает

Для каждого ненулевого перехода алгоритм сначала получает denoised `D₁` в текущей sigma. Затем ставит внутреннюю точку на `r` доли log-SNR интервала, вычисляет промежуточный latent и вызывает модель второй раз, получая `D₂`. Итоговая комбинация использует коэффициент `1 / (2r)`.

Brownian noise может добавляться и к промежуточной стадии, и к конечному обновлению, если `eta > 0` и `s_noise > 0`. На переходе к sigma 0 код сразу возвращает текущий denoised и не делает второй model call.

Как и 2M/3M SDE, реализация учитывает `model_sampling`, корректирует первую sigma и умножает `s_noise` на доступный `noise_scale`. Значение `r = 0,5` помещает внутреннюю стадию в середину интервала и даёт `fac = 1`.

## 6. Параметры и настройка

Оставляйте `r = 0,5`, пока у модели нет проверенной рекомендации. Значения меньше или больше меняют положение внутреннего model evaluation и веса `D₁`/`D₂`. Runtime не ограничивает `r` единицей, но значения вне `(0, 1]` выводят стадию за привычный внутренний участок или к его границе; их нужно проверять отдельно.

Начальная source-derived конфигурация: `eta = 1`, `s_noise = 1`, `r = 0,5`. При `eta = 0` оба Brownian additions отключаются и меняются коэффициенты основного обновления. При `s_noise = 0` исчезает случайный tensor, но eta продолжает участвовать в формулах.

CPU/GPU option управляет Brownian tree, а не моделью. Для воспроизводимого сравнения фиксируйте весь граф. Даже одинаковый seed не гарантирует побитового совпадения между устройствами и библиотечными реализациями.

## 7. Проверочный fragment

Recursive scan официального wheel 0.1.42 просмотрел все 512 JSON, 496 root workflow и 272 subgraphs. `SamplerDPMPP_SDE` отсутствует полностью, включая mode 4. Строки `dpmpp_sde` и `dpmpp_sde_gpu` также не встречаются в serialized widgets других нод. Официального значения `r` или model topology в bundle нет.

Recipe «DPM++ SDE с r 0,5 для SamplerCustomAdvanced» повторяет constructor defaults и runtime types: `eta = 1`, `s_noise = 1`, `r = 0,5`, `noise_device = gpu`. `SAMPLER` подключён к `SamplerCustomAdvanced`; NOISE, GUIDER, SIGMAS и LATENT внешние. Это проверенный по schema fragment, а не исполненный model workflow.

## 8. Частые ошибки

- Ставят `r = 0`, потому что schema разрешает минимум 0. Реализация делит на `2r`.
- Считают `r` числом шагов. Оно задаёт внутреннюю точку каждого перехода.
- Сравнивают стоимость с 2M только по названию. Здесь обычно два model calls на ненулевой переход, у 2M — один.
- Ожидают, что `s_noise = 0` отменит всё влияние eta.
- Путают `noise_device` с устройством diffusion model.
- Принимают отсутствие official case за доказательство несовместимости. Bundle лишь не содержит пример этой ноды.

## 9. Ограничения и производительность

Главное ограничение — второй model evaluation на каждом переходе, кроме terminal. При одинаковом числе SIGMAS это обычно заметно дороже 2M/3M SDE, которые переиспользуют прошлые denoised и вызывают модель один раз на переход.

Алгоритм не хранит длинную историю, но временно держит промежуточный latent и второй prediction. Brownian tree добавляет собственную память; GPU-вариант размещает её на устройстве tensor. При массиве SIGMAS длиной 0 или 1 функция возвращает вход без model call.

## 10. Совместимость и источники

Статья закреплена на ComfyUI `0.32.0`, frontend `1.48.7`, commit `c2bcbecd82ec5ae66594340b395c24ef0217b238`, embedded docs `0.5.9` и workflows `0.1.42`. Нода имеет exact ID `SamplerDPMPP_SDE`, не помечена deprecated/experimental/dev-only/API-only и не является output node. Replacement и aliases отсутствуют.

Embedded docs оставляют `r` неопределённым «параметром, влияющим на поведение». Source показывает его точную роль в промежуточной lambda и делитель `1/(2r)`. Docs также не предупреждают, что разрешённый интерфейсом ноль недопустим для вычисления.

- [Конструктор `SamplerDPMPP_SDE`](https://github.com/Comfy-Org/ComfyUI/blob/c2bcbecd82ec5ae66594340b395c24ef0217b238/comfy_extras/nodes_custom_sampler.py#L448-L472)
- [Двухстадийный алгоритм DPM++ SDE](https://github.com/Comfy-Org/ComfyUI/blob/c2bcbecd82ec5ae66594340b395c24ef0217b238/comfy/k_diffusion/sampling.py#L738-L792)
- [GPU Brownian wrapper](https://github.com/Comfy-Org/ComfyUI/blob/c2bcbecd82ec5ae66594340b395c24ef0217b238/comfy/k_diffusion/sampling.py#L975-L981)
- [Official workflow templates 0.1.42](https://pypi.org/project/comfyui-workflow-templates-json/0.1.42/)
