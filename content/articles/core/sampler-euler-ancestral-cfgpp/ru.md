# SamplerEulerAncestralCFGPP: Euler ancestral с CFG++

`SamplerEulerAncestralCFGPP` создаёт объект `SAMPLER` для алгоритма `euler_ancestral_cfg_pp`. Нода не принимает `MODEL`, conditioning, latent или `SIGMAS` и ничего не генерирует сама. Эти компоненты соединяются позже в `SamplerCustom` или `SamplerCustomAdvanced`.

## Выход хранит алгоритм и два параметра

Метод ноды вызывает `comfy.samplers.ksampler("euler_ancestral_cfg_pp", {"eta": eta, "s_noise": s_noise})`. На выходе получается настроенный sampler, а не изображение и не latent.

Runtime-ID — `SamplerEulerAncestralCFGPP`, а видимое название — `SamplerEulerAncestralCFG++`. Разница относится только к отображению: semantic resolver должен связывать статью с exact ID без плюсов.

## eta задаёт ancestral-разложение перехода

`eta` имеет диапазон 0–1, шаг 0,01 и значение по умолчанию 1. Внутренний `get_ancestral_step` делит следующий уровень на `sigma_down` и `sigma_up`: первый участвует в детерминированном обновлении, второй задаёт величину новой случайной составляющей.

При `eta = 0` функция возвращает исходный `sigma_to` и нулевой `sigma_up`. При переходе 1 → 0,5 и `eta = 1` exact-source probe дал `sigma_down = 0,25` и `sigma_up ≈ 0,433013`. Поэтому `eta` — не размер шага, вопреки упрощённому описанию embedded docs.

## s_noise масштабирует добавляемый шум

`s_noise` по умолчанию равен 1, runtime разрешает 0–10 с шагом 0,01. На каждом нетерминальном переходе sampler умножает случайный tensor на `s_noise`, `sigma_up` и коэффициент `alpha_t`.

Перед этим значение дополнительно умножается на `model_sampling.noise_scale`, если у sampling-конфигурации модели есть такой атрибут. Одинаковый `s_noise` поэтому может означать разную фактическую амплитуду для разных моделей.

## eta = 0 и s_noise = 0 дают разные траектории

При `eta = 0` исчезает ancestral-разложение: `sigma_down` остаётся равным целевому уровню, а `sigma_up` равен нулю. Значение `s_noise` уже не влияет на добавление шума.

При `s_noise = 0` и положительном `eta` случайный tensor не добавляется, но `sigma_down` всё ещё рассчитан по ancestral-формуле. Такой режим не тождественен `eta = 0`.

## CFG++ использует unconditional denoised в производной

Sampler добавляет post-CFG hook и сохраняет `uncond_denoised`. Детерминированная производная строится из этого unconditional-предсказания, а guided `denoised` остаётся основой обновления. Это и есть существенное отличие CFG++ от обычного Euler ancestral.

Hook включает `disable_cfg1_optimization=True`, чтобы unconditional-ветвь была доступна и при коэффициенте guidance 1. Сам sampler не задаёт CFG: значение и conditioning приходят через внешний `GUIDER`.

Хотя у ноды нет входа `MODEL`, алгоритм получает sampling-конфигурацию из модели внутри выполняющего pipeline. Она нужна для перевода sigma в half-log-SNR, а также для `noise_scale`.

Подбирайте `SIGMAS` для той же sampling-версии модели, которую использует guider. Нода-конструктор не может проверить это соответствие заранее.

## Последний переход не добавляет ancestral noise

Если следующая sigma равна 0, цикл присваивает `x = denoised` и не выполняет Euler-разложение или добавление случайного шума. `eta` и `s_noise` действуют только на переходах с положительной следующей sigma.

Последовательность без завершающего нуля изменит эту ветку поведения. Проверяйте расписание до sampling, особенно если оно собрано вручную или обработано sigma-утилитами.

## SAMPLER подключается к component sampling

Типовая схема: внешний `NOISE`, `GUIDER`, этот `SAMPLER`, `SIGMAS` и `LATENT` входят в `SamplerCustomAdvanced`. Самpler-нода не заменяет scheduler: алгоритм перехода и расписание уровней шума остаются разными компонентами.

Если использовать обычный `KSampler`, алгоритм выбирается строкой в его widget. Отдельная нода нужна для component pipeline и явной настройки `eta` и `s_noise`.

## Exact-ноды нет в официальном wheel

В wheel 0.1.42 распарсены все 512 JSON: 496 root workflow и 272 `definitions.subgraphs`, всего 768 графовых областей. `SamplerEulerAncestralCFGPP` не встретился ни разу, поэтому у статьи нет официального набора widget-значений для exact-ноды.

Соседний официальный пример есть только у `KSamplerSelect`: в `template_image_speech_to_video` он выбирает строку `euler_ancestral_cfg_pp` и передаёт `SAMPLER` в `SamplerCustomAdvanced`. Это подтверждает использование алгоритма, но не сериализацию `eta` и `s_noise` отдельной ноды.

## Fragment фиксирует только проверенную связь

Recipe ставит значения по умолчанию `eta = 1`, `s_noise = 1` и соединяет выход с `SamplerCustomAdvanced.sampler`. Остальные четыре входа sampler остаются внешними; это source-derived fragment, а не официальный или полный workflow.

Метод-конструктор и `get_ancestral_step` исполнены на безопасных синтетических значениях. Полный CFG++ sampling с моделью не запускался, поэтому `exampleExecuted` остаётся `false`. Редактор пока не проверил материал вручную.

## Ошибки чаще возникают на стыке компонентов

- `SAMPLER` создан, но не подключён к выполняющей ноде: ничего не запускается.
- `eta = 0` принимают за то же самое, что `s_noise = 0`: детерминированные части различаются.
- `s_noise` переносят между моделями без учёта `noise_scale`.
- CFG++ называют отдельным CFG-значением: коэффициент задаёт guider, а sampler меняет использование unconditional-предсказания.
- Расписание не заканчивается нулём: последняя ветка алгоритма меняется.

Сначала проверьте `MODEL`/guider, `SIGMAS` и terminal zero, затем сравнивайте `eta` и `s_noise`.

## Источники

- [SamplerEulerAncestralCFGPP в ComfyUI v0.32.0](https://github.com/Comfy-Org/ComfyUI/blob/c2bcbecd82ec5ae66594340b395c24ef0217b238/comfy_extras/nodes_custom_sampler.py#L514-L535)
- [Алгоритм Euler ancestral CFG++](https://github.com/Comfy-Org/ComfyUI/blob/c2bcbecd82ec5ae66594340b395c24ef0217b238/comfy/k_diffusion/sampling.py#L1266-L1307)
- [Официальный соседний workflow с KSamplerSelect](https://github.com/Comfy-Org/workflow_templates/blob/cca1ea5ea4560108ecc2f44dee951f41ea433062/templates/template_image_speech_to_video.json)
- [Embedded docs 0.5.9](https://github.com/Comfy-Org/embedded-docs/blob/1d258cf6e374d60d138a2bfcd273c7e11f750ef9/comfyui_embedded_docs/docs/SamplerEulerAncestralCFGPP/en.md)
