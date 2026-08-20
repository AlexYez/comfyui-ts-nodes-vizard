# SamplerDPMPP_3M_SDE: многошаговый DPM++ SDE третьего порядка

`SamplerDPMPP_3M_SDE` создаёт объект `SAMPLER` для `dpmpp_3m_sde`. Нода передаёт алгоритму `eta` и `s_noise`, а параметром `noise_device` выбирает, где хранится и вычисляется Brownian tree. Модель, расписание `SIGMAS` и запуск sampling находятся в других нодах.

## 1. Что делает нода

При `noise_device = cpu` нода вызывает `ksampler("dpmpp_3m_sde", options)`. Значение `gpu` выбирает `dpmpp_3m_sde_gpu`. В обоих случаях options содержат только `eta` и `s_noise`.

Часть `3M` означает многошаговую схему третьего порядка, которая использует историю предыдущих denoised-прогнозов. Это не требование поставить ровно три шага. Фактическое число переходов задаёт входной массив `SIGMAS` у ноды, которая исполнит sampler.

## 2. Место в графе

Выход `SAMPLER` подключают к `SamplerCustom.sampler` или `SamplerCustomAdvanced.sampler`. Исполняющей ноде отдельно нужны `SIGMAS`, стартовый NOISE, LATENT и guider либо model/conditioning — в зависимости от её интерфейса.

При стандартных настройках тот же алгоритм можно выбрать через `KSamplerSelect`: в системном списке есть `dpmpp_3m_sde` и `dpmpp_3m_sde_gpu`. Отдельная нода удобна, когда `eta`, `s_noise` и размещение Brownian tree должны быть явно видны в workflow.

## 3. Входы

- `eta: FLOAT` — коэффициент SDE-части; по умолчанию `1`, runtime-диапазон `0…100`, шаг `0,01`.
- `s_noise: FLOAT` — множитель случайного члена; по умолчанию `1`, диапазон `0…100`, шаг `0,01`.
- `noise_device: COMBO` — `gpu` или `cpu`; options в runtime перечислены именно в таком порядке.

Все три widgets помечены как advanced. Входа seed здесь нет: seed приходит в sampler через `extra_args`. Нода также не выбирает scheduler и не строит `SIGMAS`.

## 4. Выход

Единственный выход — `SAMPLER`, не list-output. Внутри находится функция `sample_dpmpp_3m_sde` либо её GPU-wrapper и словарь `{"eta": …, "s_noise": …}`.

Слово `gpu` относится к Brownian noise sampler, а не к отдельному запуску diffusion model. Модель исполняется на устройстве, которое определяет её обычный ComfyUI lifecycle.

## 5. Как работает

Алгоритм переводит sigma в half-log SNR с учётом `model_sampling`, корректирует первую sigma через `offset_first_sigma_for_snr` и делает один model prediction на каждый переход. Первый ненулевой переход использует текущий denoised-прогноз. Когда накоплен один предыдущий прогноз, добавляется поправка 2M; после накопления двух — поправки 3M.

На переходе к нулевой sigma результатом сразу становится текущий denoised. Между ненулевыми уровнями при `eta > 0` и `s_noise > 0` добавляется Brownian increment. Перед этим `s_noise` умножается на `model_sampling.noise_scale`, если такое поле есть.

CPU-ветвь строит `BrownianTreeNoiseSampler(..., cpu=True)`. GPU-wrapper заранее создаёт тот же sampler с `cpu=False` и передаёт его основной функции. Математическая многошаговая часть при этом общая.

## 6. Параметры и настройка

Без модельного примера начинайте с `eta = 1`, `s_noise = 1`. `eta = 0` убирает добавление Brownian noise и меняет SDE-множители в детерминированной части. `s_noise = 0` зануляет случайное слагаемое, но оставляет влияние `eta` на основное обновление, поэтому две настройки не тождественны.

Выбирайте `cpu`, если нужна CPU-backed Brownian tree, и `gpu`, если дерево должно оставаться на устройстве tensor. Это не обещание ускорения: результат зависит от устройства, размера latent, версии библиотек и стоимости обмена данными. Для сравнения фиксируйте seed, SIGMAS, model, guider и начальный NOISE.

Верхняя граница 100 — техническое ограничение widget, а не рекомендуемый диапазон. Большие `eta` или `s_noise` резко усиливают отклонение от обычной траектории и требуют отдельной проверки на выбранной модели.

## 7. Проверочный fragment

Полный recursive census официального `comfyui-workflow-templates-json 0.1.42` просмотрел 512 JSON, 496 root-графов и 272 `definitions.subgraphs`. Ни одного `SamplerDPMPP_3M_SDE` не найдено — ни активного, ни отключённого. Поэтому официальных widgets и topology именно для этого classType в закреплённом bundle нет.

Сам алгоритм `dpmpp_3m_sde_gpu` встречается в двух активных `KSampler`: `audio_stable_audio_example`, UUID `5fa61cc8-29d9-4deb-9f90-02d3c00b63b3`, с widgets `[840755638734093, "randomize", 50, 4.98, "dpmpp_3m_sde_gpu", "exponential", 1]`; и `sdxl_revision_text_prompts`, UUID `22fbfe6b-e7d7-4193-8409-8599b5dce771`, со значениями `[900749379955168, "randomize", 26, 8, "dpmpp_3m_sde_gpu", "exponential", 1]`. Это подтверждает использование algorithm name, но `KSampler` не открывает `eta`, `s_noise` и `noise_device` как порты этой ноды.

Recipe «DPM++ 3M SDE для SamplerCustomAdvanced» — source-derived mapping GPU-имени на специализированный constructor: `SamplerDPMPP_3M_SDE(eta = 1, s_noise = 1, noise_device = gpu) → SamplerCustomAdvanced.sampler`. Остальные четыре входа исполнителя оставлены внешними. Схема и типы портов проверены; fragment не импортировался в UI и не выполнялся с моделью.

## 8. Частые ошибки

- Считают `3M` числом sampling steps. Число переходов задаёт `SIGMAS`.
- Подключают `SAMPLER` к порту `noise` или `sigmas`. Нужен порт `sampler`.
- Ожидают, что `noise_device` перенесёт diffusion model между CPU и GPU. Он выбирает CPU/GPU вариант Brownian tree.
- Считают `eta = 0` и `s_noise = 0` полностью одинаковыми. Первый параметр входит и в основное SDE-обновление.
- Пытаются получить преимущество третьего порядка на слишком коротком schedule. Полная 3M-поправка появляется только после накопления двух предыдущих denoised-прогнозов.
- Принимают диапазон до 100 за безопасную рекомендацию.

## 9. Ограничения и производительность

После разогрева алгоритм хранит два предыдущих denoised-тензора и отношения шагов. Это увеличивает временную память относительно метода без истории, хотя основную стоимость по-прежнему составляет model prediction. На обычном переходе здесь один вызов модели, в отличие от двухстадийного `SamplerDPMPP_SDE`.

Brownian tree добавляет вычисления и при CPU-варианте переносит его значения обратно на исходное устройство tensor. GPU-вариант избегает CPU-backed tree, но может потребовать больше памяти устройства. При длине `SIGMAS` не больше одного низкоуровневая функция возвращает полученный `x` без model call; окружающий `KSAMPLER` всё равно отвечает за масштабирование входа и выхода.

## 10. Совместимость и источники

Статья закреплена на ComfyUI `0.32.0`, frontend `1.48.7`, commit `c2bcbecd82ec5ae66594340b395c24ef0217b238`, embedded docs `0.5.9` и workflow templates `0.1.42`. Runtime ID — `SamplerDPMPP_3M_SDE`; нода не deprecated, не experimental, не API-only и не output node. Replacement и execution aliases отсутствуют.

Embedded docs верно называют третий порядок, multistep и три входа, но не объясняют разогрев 2M→3M, terminal branch, `model_sampling.noise_scale` и точный смысл `noise_device`. Их формулировка про «вычисления шума на GPU или CPU» уточнена по реализации Brownian tree.

- [Конструктор `SamplerDPMPP_3M_SDE`](https://github.com/Comfy-Org/ComfyUI/blob/c2bcbecd82ec5ae66594340b395c24ef0217b238/comfy_extras/nodes_custom_sampler.py#L396-L419)
- [Алгоритм 3M SDE и GPU-wrapper](https://github.com/Comfy-Org/ComfyUI/blob/c2bcbecd82ec5ae66594340b395c24ef0217b238/comfy/k_diffusion/sampling.py#L882-L951)
- [Реализация Brownian tree](https://github.com/Comfy-Org/ComfyUI/blob/c2bcbecd82ec5ae66594340b395c24ef0217b238/comfy/k_diffusion/sampling.py#L91-L149)
- [Official workflow templates 0.1.42](https://pypi.org/project/comfyui-workflow-templates-json/0.1.42/)
