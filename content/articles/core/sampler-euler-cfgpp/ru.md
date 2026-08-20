# SamplerEulerCFGpp: две реализации Euler CFG++

`SamplerEulerCFGpp` создаёт объект `SAMPLER` для Euler CFG++ и предлагает две реализации: `regular` и `alternative`. Нода не принимает модель, conditioning или `SIGMAS` и сама ничего не денойзит — вычисления начнутся в `SamplerCustom` либо `SamplerCustomAdvanced`.

## 1. Что делает нода

При `version = regular` нода вызывает зарегистрированный `ksampler("euler_cfg_pp")`. Этот путь использует реализацию из `comfy/k_diffusion/sampling.py`: на каждом переходе она получает итоговый CFG-guided и безусловный denoised-прогнозы и выполняет Euler CFG++ update без ancestral renoise.

При `version = alternative` нода напрямую оборачивает локальную функцию `sample_euler_pp` из `nodes_advanced_samplers.py`. Она тоже использует безусловный прогноз, но строит производную и Euler-шаг по другой формуле. Это не переключатель качества и не новая версия модели: выбор меняет математику sampler.

## 2. Место в графе

Выход подключают к входу `sampler` у `SamplerCustom` или `SamplerCustomAdvanced`. Исполнителю отдельно нужны модель либо guider, начальный NOISE, `SIGMAS` и LATENT. Число переходов и их позиции определяет именно `SIGMAS`.

Для `regular` есть более простой эквивалент конструктора — `KSamplerSelect(sampler_name = euler_cfg_pp)`. Ветка `alternative` в общем списке sampler names отсутствует и доступна через эту специализированную ноду.

## 3. Вход

Единственный обязательный вход — `version: COMBO`. Runtime 0.32.0 разрешает два точных значения:

- `regular` — штатная `sample_euler_cfg_pp`;
- `alternative` — локальная `sample_euler_pp`.

Widget помечен как advanced. Входов CFG, seed, scheduler и steps здесь нет. CFG входит в guider или в исполняющую ноду, seed — в источник NOISE, а schedule — в `SIGMAS`.

## 4. Выход

Единственный выход имеет тип `SAMPLER` и не является list-output. `regular` возвращает `KSAMPLER`, связанный с именем `euler_cfg_pp`; `alternative` возвращает `KSAMPLER` с прямой ссылкой на `sample_euler_pp`.

Не путайте этот classType с `SamplerEulerAncestralCFGPP`. У ancestral-ноды другой модуль, входы `eta` и `s_noise` и отдельный runtime ID. Текущая нода помечена experimental, ancestral-вариант — нет.

## 5. Как работают две версии

Обе ветви устанавливают post-CFG callback, сохраняющий `uncond_denoised`, и отключают оптимизацию, которая могла бы пропустить безусловный проход при CFG=1. Поэтому наличие безусловного прогноза для формулы важнее потенциальной экономии этого режима.

`regular` вычисляет коэффициенты через half-log SNR выбранного `model_sampling`. На последнем переходе к нулевой sigma результатом становится `denoised`. На остальных переходах она вызывает общую CFG++ ancestral-функцию с `eta = 0` и `s_noise = 0`: случайный tensor не добавляется.

`alternative` для каждого перехода вычисляет `d = to_d(x - denoised + uncond_denoised, sigma, denoised)`, затем обновляет `x` на `d * (sigma_next - sigma)`. Отдельной terminal-ветви у неё нет. Из-за разных формул одинаковые model, seed и `SIGMAS` не обязаны давать одинаковый LATENT.

## 6. Выбор версии и настройка

Начинайте с `regular`, если workflow или автор модели не требует альтернативной ветви. Это зарегистрированный sampler name, который проще сопоставить с обычным `KSamplerSelect`. Сравнивайте версии только при фиксированных model, conditioning, NOISE, `SIGMAS`, CFG и latent-размере.

CFG задаётся не здесь. Значение CFG=1 не превращает ноду в обычный Euler: реализация всё равно запрашивает безусловный прогноз, поскольку принудительно отключает CFG1 optimization. Нода также не добавляет ancestral noise, однако весь результат может меняться со стартовым NOISE.

## 7. Проверочный fragment

Recipe «Euler CFG++ regular для custom sampling» сохраняет минимальную source-derived связь `SamplerEulerCFGpp(version = regular) → SamplerCustomAdvanced.sampler`. Остальные четыре входа исполнителя оставлены внешними, чтобы fragment можно было включить только в согласованный model-specific pipeline.

Полный recursive census `comfyui-workflow-templates-json 0.1.42` прочитал 512 JSON, 496 root-графов и 272 subgraph. В нём нет ни одного `SamplerEulerCFGpp`; строка `euler_cfg_pp` также не встречается в исполняемых widgets. Поэтому fragment проверен по source и runtime, но не объявлен официальным workflow-примером и не выполнялся с моделью.

## 8. Частые ошибки

- Выбирают `alternative`, считая её автоматически более новой или качественной. Source фиксирует лишь другую формулу.
- Путают `SamplerEulerCFGpp` с `SamplerEulerAncestralCFGPP` и ищут здесь `eta` или `s_noise`.
- Подключают `SAMPLER` к порту `sigmas` либо `noise`; нужен порт `sampler`.
- Ожидают, что нода задаст CFG. Он находится у guider или sampler-runner.
- Приписывают `regular` полную детерминированность: стартовый NOISE и модельный pipeline остаются внешними.
- Сравнивают версии с разными seed или `SIGMAS` и относят разницу к одной формуле.

## 9. Ограничения и производительность

Конструктор почти не расходует ресурсы; основная стоимость возникает при исполнении. В каждой ветви на один sigma-переход вызывается model wrapper, а post-CFG путь требует получить и сохранить безусловный denoised-прогноз. Принудительное отключение CFG1 optimization может делать CFG=1 дороже sampler, которому безусловный прогноз не нужен.

Нода имеет experimental-флаг в runtime 0.32.0. Это означает, что её интерфейс и поведение нельзя считать столь же стабильными, как у обычных core-нод. Количественное сравнение скорости, памяти и качества двух ветвей на весах не проводилось.

## 10. Совместимость и источники

Статья сверена с ComfyUI `0.32.0`, frontend `1.48.7`, commit `c2bcbecd82ec5ae66594340b395c24ef0217b238`, embedded docs `0.5.9` и workflow templates `0.1.42`. Точный ID — `SamplerEulerCFGpp`, модуль — `comfy_extras.nodes_advanced_samplers`; replacement и execution aliases отсутствуют.

Embedded docs верно перечисляют `regular`, `alternative` и выход `SAMPLER`, но не объясняют различия формул, post-CFG callback, отключённую CFG1 optimization и experimental-флаг. Русский файл вдобавок переводит имя порта как `версия`, хотя runtime-порт называется `version`; факты статьи взяты из source и `/object_info`.

- [Нода и alternative-реализация](https://github.com/Comfy-Org/ComfyUI/blob/c2bcbecd82ec5ae66594340b395c24ef0217b238/comfy_extras/nodes_advanced_samplers.py#L65-L140)
- [Штатный Euler CFG++](https://github.com/Comfy-Org/ComfyUI/blob/c2bcbecd82ec5ae66594340b395c24ef0217b238/comfy/k_diffusion/sampling.py#L1265-L1313)
- [Official workflow templates 0.1.42](https://pypi.org/project/comfyui-workflow-templates-json/0.1.42/)
