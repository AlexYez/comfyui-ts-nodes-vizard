# SamplingPercentToSigma: получить sigma по доле sampling

`SamplingPercentToSigma` берёт `model_sampling` из входного `MODEL` и переводит долю 0–1 в значение `FLOAT`. Результат зависит от sampling-класса модели: одинаковый процент у discrete, continuous EDM, flow и Flux не обязан давать одну sigma.

## Процент идёт от начала к концу sampling

`sampling_percent = 0` обозначает верхний край, где sampling только начинается; 1 — нижний край после прохождения расписания. Внутренние значения движутся от высокой sigma к низкой по формуле конкретной модели.

Поле имеет шаг 0,0001 и runtime-диапазон 0–1. Нода не создаёт массив `SIGMAS`: она возвращает одно число с видимым именем `sigma_value`.

## MODEL определяет функцию преобразования

Метод вызывает `model.get_model_object("model_sampling")`, затем `model_sampling.percent_to_sigma(sampling_percent)`. Патчи `ModelSampling…` в upstream-ветке могут изменить результат.

Используйте тот же вариант `MODEL`, который участвует в соответствующем sampling pipeline. Нода не сравнивает его с моделью внутри другого guider.

## Discrete mapping интерполирует модельную сетку

Для `ModelSamplingDiscrete` внутренний процент разворачивается как `1 − percent`, умножается на 999 и передаётся в `sigma(timestep)`. Эта функция интерполирует логарифмы соседних элементов модельной sigma-сетки.

`StableCascadeSampling` использует собственную cosine/shift-функцию. Общее правило одно: interior-значение вычисляет сам объект `model_sampling`, а не `SamplingPercentToSigma`.

## Continuous EDM интерполирует логарифмы границ

`ModelSamplingContinuousEDM` для долей строго между 0 и 1 линейно интерполирует `log(sigma)` между `sigma_max` и `sigma_min`, затем применяет экспоненту.

Это похоже на exponential schedule, но нода возвращает одну точку, а не полный список. Границы берутся из модели, а не из widget.

## Flow и Flux учитывают shift

`ModelSamplingDiscreteFlow` применяет `time_snr_shift(self.shift, 1 − percent)`. `ModelSamplingFlux` использует `flux_time_shift` со своим `shift`.

Для этих классов значение в начале interval mapping равно 1 и в pinned-реализации совпадает с `sigma_max` сетки. На другом краю служебный 0 отличается от положительной `sigma_min`; endpoint-флаг возвращает сохранённую границу модели.

## false возвращает служебные края интервала

При `return_actual_sigma = false` нода оставляет результат `percent_to_sigma` без изменений. У discrete, continuous EDM и Stable Cascade доля 0 возвращает большое служебное число `999999999,9`, а доля 1 — 0.

У flow и Flux края равны 1 и 0. Эти значения удобны для проверок попадания в интервал: начало гарантированно не ниже model schedule, конец не выше него.

## true меняет только точные 0 и 1

Нода сначала вызывает `percent_to_sigma`, а затем при точном `sampling_percent == 0.0` заменяет результат на `model_sampling.sigma_max.item()`. При точной единице подставляется `sigma_min.item()`.

Для 0,25, 0,5 или любого другого внутреннего значения флаг ничего не меняет. Он не переключает альтернативную формулу по всей шкале.

## FLOAT можно передать в SetFirstSigma

Совместимая source-derived схема: `sigma_value` идёт во вход `sigma` ноды `SetFirstSigma`, а внешний `SIGMAS` — в её одноимённый вход. Так можно заменить первую точку значением, рассчитанным по модели.

`SetFirstSigma` не обрезает остальные точки. После замены убедитесь, что новая первая sigma не ниже второй; иначе расписание начнётся с возрастающего интервала.

## Official templates не дают exact-примера

В wheel 0.1.42 проверены 512 JSON, 496 root и 272 subgraph. `SamplingPercentToSigma` отсутствует во всех 768 графовых областях; следовательно, pinned-набор не подтверждает конкретный процент или downstream-ноду.

Recipe с долей 0,25 — учебный source-derived fragment. Он не объявлен официальным workflow и требует проверки порядка на реальном входном `SIGMAS`.

## Probe отделяет endpoint от полного sampling

Exact execute-метод проверен на подставном `model_sampling`: при false края остались `999999999,9` и 0, при true заменились на 14,5 и 0,03, а значение 0,25 не изменилось. Также подтверждено, что `percent_to_sigma` вызывается до endpoint override.

Настоящая модель, `SetFirstSigma` и sampler вместе не исполнялись; поэтому `exampleExecuted=false`. Редактор пока не проверил материал вручную.

## Источники

- [SamplingPercentToSigma в ComfyUI v0.32.0](https://github.com/Comfy-Org/ComfyUI/blob/c2bcbecd82ec5ae66594340b395c24ef0217b238/comfy_extras/nodes_custom_sampler.py#L351-L376)
- [Model-specific percent_to_sigma methods](https://github.com/Comfy-Org/ComfyUI/blob/c2bcbecd82ec5ae66594340b395c24ef0217b238/comfy/model_sampling.py#L211-L440)
- [Pinned-набор официальных workflow](https://github.com/Comfy-Org/workflow_templates/tree/cca1ea5ea4560108ecc2f44dee951f41ea433062/templates)
- [Embedded docs 0.5.9](https://github.com/Comfy-Org/embedded-docs/blob/1d258cf6e374d60d138a2bfcd273c7e11f750ef9/comfyui_embedded_docs/docs/SamplingPercentToSigma/en.md)
