# SamplerDPMPP_2S_Ancestral: двухстадийный ancestral DPM++

`SamplerDPMPP_2S_Ancestral` создаёт `SAMPLER` для DPM++ 2S ancestral. Алгоритм делит переход sigma на детерминированную и шумовую части, делает промежуточный model prediction и добавляет ancestral noise между ненулевыми уровнями.

## 1. Что делает нода

Конструктор вызывает `ksampler("dpmpp_2s_ancestral", {"eta": eta, "s_noise": s_noise})`. В отличие от трёх SDE-нод этой партии здесь нет `noise_device`: используется noise sampler, который создаёт сам алгоритм.

`2S` означает двухстадийную схему внутри текущего перехода. Это не два шага в расписании. Число переходов и их sigma задаёт отдельный scheduler.

## 2. Место в графе

Выход подключают к `SamplerCustom.sampler` или `SamplerCustomAdvanced.sampler`. Для исполнения также нужны NOISE, SIGMAS, LATENT и guider либо MODEL вместе с conditioning — точный набор зависит от consumer.

`KSamplerSelect(dpmpp_2s_ancestral)` создаёт тот же algorithm с defaults. Специализированная нода нужна, когда `eta` и `s_noise` должны быть доступны как явные widgets или управляться отдельными primitive-узлами.

## 3. Входы

- `eta: FLOAT` — управляет ancestral-разбиением перехода; default `1`, диапазон `0…100`, шаг `0,01`.
- `s_noise: FLOAT` — масштаб добавляемого случайного tensor; default `1`, диапазон `0…100`, шаг `0,01`.

В exact schema эти два inputs не помечены advanced, в отличие от одноимённых полей соседних DPM++ SDE-нод. Seed, model, scheduler и `SIGMAS` не являются входами конструктора.

## 4. Выход

Единственный выход имеет тип `SAMPLER`. Объект хранит функцию `sample_dpmpp_2s_ancestral` и два числовых options. Он не является NOISE или LATENT.

Во время исполнения функция сама выбирает обычную ветвь или `sample_dpmpp_2s_ancestral_RF`, если model sampling имеет тип `CONST`. Этот dispatch зависит от модели и не виден в output schema.

## 5. Как работает

В обычной ветви `get_ancestral_step` вычисляет `sigma_down` и `sigma_up` из текущей sigma, следующей sigma и eta. Если `sigma_down` не ноль, алгоритм строит промежуточный latent на половине log-sigma интервала, вызывает модель второй раз и использует этот denoised для завершения шага. При `sigma_down = 0` применяется Euler terminal step с одним prediction.

Если следующая sigma положительна, к latent добавляется `noise * s_noise * sigma_up`. При `eta = 0` helper возвращает `sigma_down = sigma_next`, `sigma_up = 0`, поэтому ancestral renoise исчезает.

Для `CONST` используется отдельная RF-формула в lambda-space. Там `s_noise` умножается на model-specific `noise_scale`, а случайный член добавляется только при положительных next sigma и eta. Равные widgets не означают одинаковую численную траекторию обычной и RF-ветвей.

## 6. Параметры и настройка

Без проверенной рекомендации модели начните с `eta = 1` и `s_noise = 1`. Снижайте eta, чтобы уменьшить ancestral-разбиение и повторный шум. `eta = 0` убирает renoise, но начальный NOISE всё равно влияет на результат.

`s_noise = 0` зануляет добавляемый tensor, однако при `eta > 0` детерминированная часть всё ещё идёт к `sigma_down`, рассчитанной с ancestral split. Поэтому `s_noise = 0` и `eta = 0` не одно и то же.

Runtime разрешает значения до 100, но source и docs не рекомендуют экстремумы. Меняйте один параметр за раз и фиксируйте seed, SIGMAS, guider, model и начальный latent.

## 7. Проверочный fragment

Полный root/subgraph census official wheel 0.1.42 охватил 512 JSON, 496 root-графов и 272 subgraphs. Экземпляров `SamplerDPMPP_2S_Ancestral` не найдено; строка `dpmpp_2s_ancestral` также не встречается в widgets других нод. Следовательно, bundle не подтверждает model-specific topology этого алгоритма.

Recipe «DPM++ 2S ancestral для SamplerCustomAdvanced» использует source defaults `eta = 1`, `s_noise = 1` и соединяет `SAMPLER` с custom sampler. Остальные входы остаются внешними, чтобы fragment не выдавал случайное сочетание model и scheduler за официальный workflow. Schema/port contract проверен; исполнение не проводилось.

## 8. Частые ошибки

- Считают `2S` двумя scheduler steps. Это две стадии внутри обычного ненулевого перехода.
- Подают выход в `noise`, а не в `sampler`.
- Ожидают параметр `noise_device`, как у SDE 2M/3M. В runtime schema его нет.
- Приравнивают `s_noise = 0` к `eta = 0`.
- Забывают про отдельную RF/CONST-ветвь и переносят выводы между семействами моделей.
- Называют отсутствие occurrence в wheel ошибкой ноды. Это лишь отсутствие сериализованного официального case.

## 9. Ограничения и производительность

На обычном ненулевом переходе алгоритм делает два model predictions: начальный и промежуточный. Terminal/Euler branch обходится одним. Поэтому при равном schedule он обычно дороже многошаговых 2M/3M вариантов, которые используют историю и делают один model call на переход.

Default noise sampler создаёт случайный tensor на устройстве входного latent; отдельного переключателя CPU/GPU нет. RF-ветвь имеет другие формулы и масштабирует шум через `noise_scale`. При пустом schedule цикл не выполняется и возвращает входной `x`, хотя отдельной ранней проверки длины в функции нет.

## 10. Совместимость и источники

Материал проверен на ComfyUI `0.32.0`, frontend `1.48.7`, commit `c2bcbecd82ec5ae66594340b395c24ef0217b238`, docs `0.5.9` и workflows `0.1.42`. Exact ID — `SamplerDPMPP_2S_Ancestral`; runtime flags deprecated, experimental, dev-only, API-node и output-node равны false. Replacement и execution aliases отсутствуют.

Embedded docs дают общий смысл eta/s_noise, но не разделяют `sigma_down` и `sigma_up`, не описывают второй model call, terminal branch и RF/CONST dispatch. Фраза о «разнообразии при сохранении согласованности» не используется как техническая гарантия: закреплённый source её не измеряет.

- [Конструктор `SamplerDPMPP_2S_Ancestral`](https://github.com/Comfy-Org/ComfyUI/blob/c2bcbecd82ec5ae66594340b395c24ef0217b238/comfy_extras/nodes_custom_sampler.py#L474-L492)
- [Обычная и RF-ветви DPM++ 2S ancestral](https://github.com/Comfy-Org/ComfyUI/blob/c2bcbecd82ec5ae66594340b395c24ef0217b238/comfy/k_diffusion/sampling.py#L648-L734)
- [Ancestral-разбиение и default noise sampler](https://github.com/Comfy-Org/ComfyUI/blob/c2bcbecd82ec5ae66594340b395c24ef0217b238/comfy/k_diffusion/sampling.py#L68-L88)
- [Official workflow templates 0.1.42](https://pypi.org/project/comfyui-workflow-templates-json/0.1.42/)
