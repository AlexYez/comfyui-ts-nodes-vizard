# ModelSamplingContinuousEDM: непрерывная sigma-шкала и тип предсказания

`ModelSamplingContinuousEDM` клонирует модель и заменяет её sampling-объект непрерывной шкалой sigma. Пользователь задаёт нижнюю и верхнюю границы, а режим `sampling` выбирает формулу интерпретации output модели. Вариант Playground 2.5 дополнительно меняет latent format.

## Что делает нода

Обычные ветви строятся на `ModelSamplingContinuousEDM`: между `sigma_min` и `sigma_max` создаются 1000 точек, равномерных в логарифмическом пространстве. К базе подмешивается `V_PREDICTION`, `EDM` или `EPS`. Для `cosmos_rflow` используется другая база и формула rectified flow.

Нода не меняет веса и не определяет их тип. Она заменяет математику подготовки model input, расчёта denoised и преобразования percent/timestep/sigma. Неверный режим может выполниться без ошибки, но давать бессмысленную траекторию.

## Место в графе

Ставьте patch после загрузчика и перед guider, scheduler и sampler. Ветвите один patched `MODEL` в `BasicScheduler` и в guider, чтобы sigma-шкала и model prediction относились к одному объекту.

Если используется `edm_playground_v2.5`, downstream VAE/latent pipeline должен соответствовать `SDXL_Playground_2_5`. Патч меняет `latent_format` в модели, но не загружает нужный checkpoint, CLIP или VAE и не проверяет их семейство.

## Входы

- `model` — исходный `MODEL`; результат создаётся на клоне.
- `sampling` — `v_prediction`, `edm`, `edm_playground_v2.5`, `eps` или `cosmos_rflow`.
- `sigma_max` — верхняя граница интерфейса, по умолчанию 120, диапазон 0–1000.
- `sigma_min` — нижняя граница, по умолчанию 0,002, диапазон 0–1000.

Обе sigma помечены advanced и допускают дробный ввод без округления. Однако разрешённый интерфейсом ноль не проходит математическую реализацию: `math.log(0)` вызывает `ValueError`.

## Выход

Выход — cloned `MODEL` с patch `model_sampling`. В режиме Playground появляется второй object patch: `latent_format = SDXL_Playground_2_5`. В остальных четырёх режимах latent format не меняется.

Для обычной положительной пары границ новый объект содержит 1000 sigma. Свойства `sigma_min` и `sigma_max` просто читают первый и последний элементы. Если пользователь поменяет границы местами, код не остановится: массив станет убывающим, а названия свойств перестанут соответствовать числовому минимуму и максимуму.

## Как работают пять режимов

`v_prediction` использует V-формулу и `sigma_data = 1`. `eps` применяет epsilon-формулу и то же `sigma_data`. `edm` меняет знак и масштаб EDM denoised-формулы и устанавливает `sigma_data = 0,5`. `edm_playground_v2.5` делает то же и патчит Playground latent format.

`cosmos_rflow` сочетает `ModelSamplingCosmosRFlow` с `COSMOS_RFLOW`. При подготовке input sigma переводится в `sigma / (sigma + 1)`; denoised рассчитывается как смесь model input и output, а conversion между timestep и sigma ограничивается верхней границей. Это отдельная flow-семантика, а не ещё один пресет EDM.

## Параметры и настройка

Требуйте `0 < sigma_min < sigma_max`. Runtime-схема этого отношения не проверяет. Ноль приводит к ошибке логарифма; равные границы дают плоскую тысячаточечную сетку; обратный порядок создаёт убывающий внутренний массив. Ни один из этих случаев не превращается в понятное предупреждение UI.

Для `edm_playground_v2.5` ComfyUI сам распознаёт соответствующие SDXL weights по `edm_mean` и `edm_std`, задаёт `sigma_data = 0,5`, `sigma_max = 80`, `sigma_min = 0,002` и Playground latent format. Ручной patch с этими значениями полезен только при осознанном восстановлении этой конфигурации; для уже корректно распознанной модели он избыточен.

## Проверенный пример

Рецепт Wizard использует `edm_playground_v2.5`, `sigma_max = 80`, `sigma_min = 0,002` и передаёт patched модель в `BasicScheduler`. Значения взяты не из предположения: они совпадают с ветвью распознавания Playground 2.5 в закреплённом `supported_models.py`.

Ни одного точного `ModelSamplingContinuousEDM` не найдено в 512 JSON официального wheel 0.1.42 и всех subgraph. Fragment поэтому описан как source-derived реконструкция. Exact-метод исполнен для пяти режимов: проверены классы, `sigma_data`, 1000 sigma, отдельный latent-format patch, нулевая и обратная границы. Реальный Playground checkpoint не запускался. Редактор пока не проверил материал вручную.

## Частые ошибки

- `sigma_min = 0` считается допустимым из-за границы widget, но выполнение падает на логарифме.
- `sigma_min` больше `sigma_max`: код строит обратный ряд без предупреждения.
- Playground mode применяется к обычной SDXL-модели только ради названия.
- `cosmos_rflow` рассматривается как косметический scheduler, хотя меняется prediction и noise scaling.
- Patched модель идёт в scheduler, а guider получает исходную.
- Новый patch ставится после этой ноды и заменяет `model_sampling` ещё раз.

## Ограничения и производительность

Создание 1000 log-spaced чисел и clone patch обычно дёшево относительно inference. Дополнительной копии всех весов не требуется, но появляется отдельная модельная ветвь с собственными object patches.

Нода не валидирует checkpoint, latent format, порядок границ и численную устойчивость downstream sampler. Большой `sigma_max` может резко изменить масштаб model input. Сравнивайте только при одинаковых seed, latent, sampler и conditioning и сначала просматривайте реальные SIGMAS.

## Совместимость и источники проверки

Проверено для ComfyUI 0.32.0 и frontend 1.48.7. Нода относится к `model/patch`, не является experimental, deprecated или API-only и не имеет формальной замены.

В embedded docs wheel 0.5.9 отдельной директории `ModelSamplingContinuousEDM` нет. Поэтому статья опирается на runtime, исходник patch-ноды, базовые sampling-классы и официальную detection-логику SDXL Playground. Отсутствие документации не заменено догадками.

## Источники

- [ModelSamplingContinuousEDM в ComfyUI v0.32.0](https://github.com/Comfy-Org/ComfyUI/blob/c2bcbecd82ec5ae66594340b395c24ef0217b238/comfy_extras/nodes_model_advanced.py#L197-L240)
- [Continuous EDM и V sampling mathematics](https://github.com/Comfy-Org/ComfyUI/blob/c2bcbecd82ec5ae66594340b395c24ef0217b238/comfy/model_sampling.py#L226-L278)
- [Распознавание SDXL Playground 2.5](https://github.com/Comfy-Org/ComfyUI/blob/c2bcbecd82ec5ae66594340b395c24ef0217b238/comfy/supported_models.py#L211-L232)
