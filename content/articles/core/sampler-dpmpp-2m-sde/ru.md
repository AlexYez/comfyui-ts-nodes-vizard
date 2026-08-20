# SamplerDPMPP_2M_SDE: DPM++ SDE с midpoint или Heun

`SamplerDPMPP_2M_SDE` создаёт объект `SAMPLER` для многошагового DPM++ 2M SDE. Нода открывает выбор формулы поправки `midpoint`/`heun`, параметры шума `eta` и `s_noise`, а также CPU- или GPU-backed Brownian tree.

## 1. Что делает нода

При `noise_device = cpu` нода выбирает `dpmpp_2m_sde`; при `gpu` — `dpmpp_2m_sde_gpu`. В options передаются `eta`, `s_noise` и `solver_type`.

Обозначение `2M` указывает на многошаговую схему второго порядка: после первого прогноза sampler использует разность текущего и предыдущего denoised. Оно не задаёт два sampling steps и не означает два model calls на каждом переходе.

## 2. Место в графе

Выход соединяют со входом `sampler` у `SamplerCustom` или `SamplerCustomAdvanced`. Расписание `SIGMAS`, начальный NOISE, guider/model conditions и LATENT приходят отдельно.

`KSamplerSelect` умеет выбрать `dpmpp_2m_sde`, `dpmpp_2m_sde_gpu`, а также отдельные системные варианты `dpmpp_2m_sde_heun` и `dpmpp_2m_sde_heun_gpu`. Эта нода собирает тот же выбор в один узел с явным `solver_type` и параметрами шума.

## 3. Входы

- `solver_type: COMBO` — только `midpoint` или `heun`; options перечислены в таком порядке.
- `eta: FLOAT` — коэффициент SDE-части, default `1`, диапазон `0…100`, шаг `0,01`.
- `s_noise: FLOAT` — множитель Brownian increment, default `1`, диапазон `0…100`, шаг `0,01`.
- `noise_device: COMBO` — `gpu` или `cpu`, в runtime они перечислены в таком порядке.

`eta`, `s_noise` и `noise_device` помечены advanced; `solver_type` остаётся обычным widget. Seed и `SIGMAS` не входят в контракт ноды.

## 4. Выход

Нода возвращает один `SAMPLER`. Объект хранит выбранную функцию и options, но не выполняет модель до запуска custom-sampling consumer.

CPU/GPU суффикс выбирает реализацию Brownian noise sampler. Он не меняет `solver_type`: и `midpoint`, и `heun` доступны с обоими вариантами `noise_device`.

## 5. Как работает

На каждом переходе алгоритм получает один denoised-прогноз модели. Первый ненулевой переход использует его без multistep correction. Начиная со следующего перехода sampler сравнивает текущий denoised с сохранённым предыдущим и добавляет поправку.

Для `heun` и `midpoint` коэффициенты этой поправки различаются в exact source. На переходе к sigma 0 обе ветви сразу присваивают `x = denoised`, поэтому solver correction и новый Brownian noise там не добавляются.

Алгоритм использует half-log SNR выбранного `model_sampling`, корректирует первую sigma и умножает `s_noise` на model-specific `noise_scale`, если он определён. Случайное слагаемое выполняется только при `eta > 0` и `s_noise > 0`.

## 6. Параметры и настройка

Source-derived стартовая конфигурация — `midpoint`, `eta = 1`, `s_noise = 1`. Выбор между midpoint и Heun сравнивайте при одинаковых seed, NOISE, SIGMAS, model и guider: это разные поправки к одной и той же сохранённой истории.

`eta = 0` выключает Brownian term и меняет множители детерминированного обновления. `s_noise = 0` выключает только случайное слагаемое. Поэтому одинаковый seed не делает эти два режима эквивалентными.

`noise_device = cpu` создаёт Brownian tree на CPU, `gpu` — на устройстве tensor. Ни один вариант не гарантированно быстрее. Диапазон `0…100` у числовых inputs отражает schema, а не рабочую рекомендацию.

## 7. Проверочный fragment

Exhaustive scan wheel 0.1.42 охватил 512 JSON, 496 root-графов и 272 subgraphs. В них нет ни одного `SamplerDPMPP_2M_SDE`. Поэтому нельзя приписать официальным шаблонам widgets или topology именно этого classType.

Алгоритм встречается через другие ноды. В root-графе `image_hidream_o1`, UUID `a2143803-dd9d-4fd4-9370-31ce70307498`, `KSamplerSelect #230` с widgets `["dpmpp_2m_sde_gpu"]` подключён к `SamplerCustom #108.sampler`; рядом `BasicScheduler` задаёт `["normal", 40, 1]`.

Ещё три активных `KSampler` используют `dpmpp_2m_sde`. В `template_rob_realistic_2k_images_quick_variations` widgets равны `[966630005845873, "randomize", 5, 1, "dpmpp_2m_sde", "beta57", 0.6]`; в `templates_rob_realistic_2k_images_quick_variations.app` — `[873653643772748, "randomize", 5, 1, "dpmpp_2m_sde", "beta57", 0.4]`. Оба файла имеют UUID `9ae6082b-c7f4-433c-9971-7a8f65a3ea65`. В `utility_z_image_turbo_2k_upscaler.app`, UUID `109ab33d-f7ce-4924-905d-c8b0bfa6aeb5`, сохранено `[824287194145573, "randomize", 5, 1, "dpmpp_2m_sde", "beta", 0.33]`. Это доказательство algorithm name, а не специализированной ноды.

Recipe «DPM++ 2M SDE midpoint для SamplerCustomAdvanced» отображает официальный выбор `dpmpp_2m_sde_gpu` на exact constructor defaults: `midpoint`, `eta = 1`, `s_noise = 1`, `noise_device = gpu`; выход идёт в `SamplerCustomAdvanced.sampler`. NOISE, GUIDER, SIGMAS и LATENT оставлены внешними. В official HiDream consumer был `SamplerCustom`, поэтому данный fragment остаётся проверенной по типам адаптацией, а не копией полного графа. Он не импортировался и не выполнялся.

## 8. Частые ошибки

- Понимают `2M` как два model calls. В реализации один прогноз на переход и история прошлого прогноза.
- Ожидают одинаковый результат от `midpoint` и `heun`. Формулы correction различаются.
- Меняют `noise_device` и одновременно seed или SIGMAS, после чего сравнение теряет смысл.
- Полагают, что CPU/GPU option переносит саму diffusion model.
- Считают `eta = 0` простым синонимом `s_noise = 0`.
- Используют верхнюю границу 100 как рекомендованное значение.

## 9. Ограничения и производительность

Sampler хранит один предыдущий denoised-тензор и выполняет один model prediction на переход. Память истории меньше, чем у 3M, который хранит два предыдущих прогноза. Различие midpoint/Heun не добавляет второй model call в этой реализации.

Brownian tree и случайное сложение обычно дешевле model inference, но CPU-backed вариант включает перенос результата к устройству tensor. При `len(sigmas) <= 1` функция возвращает вход без исполнения модели. На очень коротком schedule многошаговая поправка успевает примениться мало раз или не применяется вовсе.

## 10. Совместимость и источники

Материал сверён с ComfyUI `0.32.0`, frontend `1.48.7`, commit `c2bcbecd82ec5ae66594340b395c24ef0217b238`, docs `0.5.9` и workflows `0.1.42`. Runtime ID — `SamplerDPMPP_2M_SDE`; все flags deprecated, experimental, dev-only, API-node и output-node равны false. Replacement и execution aliases не зафиксированы.

Embedded docs ошибочно называют `solver_type` и `noise_device` типом STRING, тогда как exact `/object_info` возвращает COMBO. Там также нет terminal branch, истории прошлого denoised, model-specific `noise_scale` и уточнения про Brownian tree.

- [Конструктор `SamplerDPMPP_2M_SDE`](https://github.com/Comfy-Org/ComfyUI/blob/c2bcbecd82ec5ae66594340b395c24ef0217b238/comfy_extras/nodes_custom_sampler.py#L421-L445)
- [Алгоритм 2M SDE](https://github.com/Comfy-Org/ComfyUI/blob/c2bcbecd82ec5ae66594340b395c24ef0217b238/comfy/k_diffusion/sampling.py#L822-L878)
- [CPU/GPU Brownian wrappers](https://github.com/Comfy-Org/ComfyUI/blob/c2bcbecd82ec5ae66594340b395c24ef0217b238/comfy/k_diffusion/sampling.py#L955-L971)
- [Official workflow templates 0.1.42](https://pypi.org/project/comfyui-workflow-templates-json/0.1.42/)
