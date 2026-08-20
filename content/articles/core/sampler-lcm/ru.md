# SamplerLCM: расписание и ограничение пошагового шума

`SamplerLCM` создаёт объект `SAMPLER` для алгоритма `lcm` и передаёт ему три настройки добавляемого между шагами шума. Нода не загружает LCM-модель, не строит `SIGMAS` и не запускает sampling.

## 1. Что делает нода

Конструктор вызывает `ksampler("lcm", options)`. В options записываются `s_noise`, `s_noise_end` и `noise_clip_std`, приведённые к `float`. Алгоритм после каждого model prediction принимает `denoised` за новую основу и, если следующая sigma больше нуля, добавляет новый случайный tensor через модельную функцию `noise_scaling`.

В отличие от выбора `lcm` через `KSamplerSelect`, специализированная нода позволяет менять множитель шума по ходу schedule и ограничивать выбросы случайного tensor. Эти параметры не меняют сам массив `SIGMAS`.

## 2. Место в графе

Выход `SAMPLER` подключают к порту `sampler` у `SamplerCustom` либо `SamplerCustomAdvanced`. Модель должна иметь подходящий `model_sampling`; schedule, conditioning или guider, начальный NOISE и LATENT приходят отдельно.

В официальном HiDream O1 Dev workflow `SamplerLCM` подключён к `SamplerCustom`. Тот же `ModelNoiseScale` питает model-вход исполнителя и `BasicScheduler(normal, 28, 1)`, поэтому MODEL и `SIGMAS` принадлежат одному настроенному sampling-пути.

## 3. Входы

- `s_noise: FLOAT` — множитель добавляемого шума в начале schedule; значение по умолчанию `1`, диапазон `0…64`, шаг `0,01`.
- `s_noise_end: FLOAT` — конечная точка линейного изменения множителя; по умолчанию `1`, диапазон `0…64`, шаг `0,01`.
- `noise_clip_std: FLOAT` — предел по модулю в единицах стандартного отклонения случайного tensor; `0` отключает clamp, диапазон `0…10`, шаг `0,01`.

Все входы обязательны. Runtime tooltip называет `1` соответствием training noise scale: в реализации это единичный множитель перед вызовом model-specific `noise_scaling`.

## 4. Выход

Единственный выход — `SAMPLER`, не list-output. Он хранит функцию `sample_lcm` и три числовые option. Это не LATENT и не готовое изображение.

Seed не записан в объект при создании. Во время исполнения `sample_lcm` берёт seed из `extra_args` и через него создаёт default noise sampler, если внешний noise sampler не передан.

## 5. Как работает расписание шума

На каждом переходе алгоритм вызывает модель, получает `denoised` и присваивает его текущему `x`. Если `sigma_next > 0`, он создаёт noise tensor. При `noise_clip_std > 0` вычисляется стандартное отклонение всего tensor, после чего каждый элемент ограничивается диапазоном `±noise_clip_std × std`.

Множитель линейно интерполируется от `s_noise` к `s_noise_end` по индексу перехода. Для schedule с одним переходом используется начальное значение. Если обычный schedule заканчивается нулевой sigma, на терминальном переходе шум вообще не добавляется; поэтому вычисленная конечная точка может не участвовать в последней фактической инъекции.

После умножения шум передаётся в `model_sampling.noise_scaling(sigma_next, noise, denoised)`. Эта model-specific операция важна: выражение не сводится во всех семействах моделей к простому `denoised + sigma × noise`.

## 6. Настройка параметров

Для постоянного множителя задайте одинаковые `s_noise` и `s_noise_end`. Значения `1, 1` оставляют случайный tensor без дополнительного масштабирования перед `noise_scaling`; нули выключают его вклад на соответствующей части schedule. Верхняя граница 64 — предел widget, а не рекомендуемый рабочий диапазон.

`noise_clip_std` меняет распределение именно нового noise tensor, а не ограничивает LATENT или denoised-прогноз. Малое значение срезает больше выбросов; влияние на изображение зависит от model sampling и schedule. Для честного сравнения фиксируйте MODEL, conditioning, seed, `SIGMAS`, LATENT и все три параметра.

## 7. Проверенный официальный fragment

Recipe «HiDream O1 Dev: SamplerLCM с ограничением шума» сохраняет точный официальный участок: `SamplerLCM(1, 1, 2.5) → SamplerCustom.sampler`, где у исполнителя `add_noise = true`, CFG `1` и сериализованный seed `270186383729385`. Кейс находится в `image_hidream_o1_dev`, UUID `a2143803-dd9d-4fd4-9370-31ce70307498`.

Полный census 512 JSON, 496 root-графов и 272 subgraph нашёл ровно один специализированный `SamplerLCM`, mode 0. Кроме него, имя `lcm` встречается в восьми исполняемых widgets обычных `KSampler` и `KSamplerSelect`; это подтверждает использование алгоритма, но не трёх дополнительных параметров этой ноды. Fragment прошёл schema и port validation, однако с HiDream-весами не запускался.

## 8. Частые ошибки

- Считают `s_noise_end` последней sigma. Это множитель noise tensor, а sigma приходит из `SIGMAS`.
- Полагают, что `noise_clip_std` ограничивает значения latent. Clamp применяется до `noise_scaling` только к новому шуму.
- Используют `SamplerLCM` с произвольной моделью только из-за названия. Совместимость определяет model sampling и проверенный pipeline.
- Подключают `SAMPLER` к порту `sigmas`; нужен `sampler`.
- Сравнивают clip-настройки при seed в режиме randomize.
- Ожидают, что `s_noise = s_noise_end = 0` удалит стартовый NOISE: параметры относятся к межшаговым инъекциям.

## 9. Ограничения и производительность

На каждый переход приходится один model prediction. Дополнительные операции — генерация noise tensor, вычисление его стандартного отклонения при включённом clamp, элементный clamp и model-specific scaling. Обычно модель дороже этих операций, но для больших latent глобальное `std` и дополнительный tensor увеличивают время и память.

Низкоуровневая функция обращается к `sigmas[i + 1]`, поэтому ей нужен schedule как минимум с двумя значениями; штатный custom-sampling путь строит такой массив. Проверка численного качества при разных градиентах `s_noise` и clip-порогах на моделях не выполнялась.

## 10. Совместимость и источники

Статья закреплена на ComfyUI `0.32.0`, frontend `1.48.7`, commit `c2bcbecd82ec5ae66594340b395c24ef0217b238`, embedded docs `0.5.9` и workflow templates `0.1.42`. Runtime ID — `SamplerLCM`, модуль — `comfy_extras.nodes_advanced_samplers`; нода не experimental и не deprecated, replacement и execution aliases отсутствуют.

Embedded docs правильно перечисляют три порта, но не уточняют порядок `denoised → clip noise → noise_scaling`, отсутствие инъекции перед нулевой sigma и отличие единичного множителя от самой model-specific шкалы. Эти детали сверены по реализации.

- [Конструктор `SamplerLCM`](https://github.com/Comfy-Org/ComfyUI/blob/c2bcbecd82ec5ae66594340b395c24ef0217b238/comfy_extras/nodes_advanced_samplers.py#L89-L117)
- [Алгоритм `sample_lcm`](https://github.com/Comfy-Org/ComfyUI/blob/c2bcbecd82ec5ae66594340b395c24ef0217b238/comfy/k_diffusion/sampling.py#L1015-L1045)
- [Official workflow templates 0.1.42](https://pypi.org/project/comfyui-workflow-templates-json/0.1.42/)
