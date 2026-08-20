# SamplerLCMUpscale: изменение размера latent во время sampling

`SamplerLCMUpscale` создаёт объект `SAMPLER`, который после model prediction поэтапно меняет spatial-размер latent. Несмотря на название, это отдельная реализация из `nodes_advanced_samplers.py`, а не обычный `lcm` с добавленной кнопкой upscale.

## 1. Что делает нода

Конструктор оборачивает `sample_lcm_upscale` и передаёт ему `total_upscale`, `upscale_steps` и `upscale_method`. На каждом переходе алгоритм заменяет текущий `x` на `denoised`, при необходимости интерполирует последние две оси tensor, а перед следующим ненулевым уровнем добавляет `sigma_next × randn_like(x)`.

Нода меняет latent во время sampling. Она не применяет pixel-upscaler, не загружает upscale-модель и не гарантирует сохранение деталей, которое обычно ожидают от отдельного image-upscale этапа.

## 2. Место в графе

Выход `SAMPLER` подключают к порту `sampler` у `SamplerCustom` или `SamplerCustomAdvanced`. Исполнитель отдельно получает модель либо guider, `SIGMAS`, стартовый NOISE и LATENT.

Модель должна принимать spatial-размеры, возникающие по ходу schedule. Итоговые размеры строятся относительно исходной формы LATENT, а не относительно результата предыдущей интерполяции, поэтому округление не накапливается как последовательное умножение текущей ширины и высоты.

## 3. Входы

- `scale_ratio: FLOAT` — конечный коэффициент spatial-размера; по умолчанию `1`, диапазон `0,1…20`, шаг `0,01`, advanced.
- `scale_steps: INT` — число ранних переходов с изменением размера; по умолчанию `-1`, диапазон `-1…1000`, advanced. Значение `-1` включает автоматический расчёт.
- `upscale_method: COMBO` — `bislerp`, `nearest-exact`, `bilinear`, `area` или `bicubic`.

Все три входа обязательны. `scale_ratio` меньше 1 фактически уменьшает latent, хотя имя classType содержит `Upscale`. Значение `scale_steps = 0` создаёт пустую последовательность интерполяций.

## 4. Выход

Единственный выход — `SAMPLER`, не list-output. В его `extra_options` находятся `total_upscale = scale_ratio`, нормализованный `upscale_steps` и выбранный метод. При отрицательном `scale_steps` конструктор передаёт `None`.

Нода не выдаёт увеличенный LATENT сразу. Форма изменится только после того, как внешний sampler-runner вызовет сохранённую функцию с model, исходным tensor и `SIGMAS`.

## 5. Как рассчитываются стадии

В автоматическом режиме число точек `numpy.linspace` равно `max(len(sigmas) // 2 + 1, 2)`. Первая точка с коэффициентом 1 отбрасывается; оставшиеся коэффициенты применяются на ранних переходах и заканчиваются ровно на `scale_ratio`.

При явном значении код прибавляет к `scale_steps` единицу, ограничивает число точек величиной `len(sigmas) + 1` и тоже отбрасывает первую точку. На переходе `i` целевые ширина и высота равны округлённым `orig_width × factor` и `orig_height × factor`. Затем, если `sigma_next > 0`, к уже интерполированному denoised добавляется новый гауссов tensor.

`common_upscale` для 4D tensor работает по последним двум осям. Для tensor с большим числом измерений она временно сворачивает дополнительные оси в batch, интерполирует spatial-плоскости и восстанавливает форму; это техническая поддержка формы, а не доказательство совместимости любой video-модели.

## 6. Настройка масштаба и метода

Начинайте с умеренного коэффициента и schedule, проверенного для конкретной модели. `scale_ratio = 2` удваивает latent width и height, а число spatial-элементов на поздних шагах растёт примерно в четыре раза. Значение 1 не увеличивает форму, хотя ранние вызовы интерполяции при ненулевом числе стадий всё ещё могут выполняться.

`bislerp` использует отдельную реализацию ComfyUI; остальные перечисленные методы передаются в `torch.nn.functional.interpolate`. Выбор влияет на значения latent, а не только на внешний вид пиксельной сетки. Сравнивайте методы при одинаковых seed, `SIGMAS`, модели, стартовой форме и числе стадий.

## 7. Проверочный fragment

Recipe «LCM Upscale: двукратное увеличение latent» задаёт source-derived связку `SamplerLCMUpscale(2, -1, bislerp) → SamplerCustomAdvanced.sampler`. Она показывает точные типы портов и автоматический режим стадий, но не претендует на универсальные параметры качества.

Полный scan 512 JSON, 496 root-графов и 272 subgraph не нашёл ни одного `SamplerLCMUpscale`. В official `utility_pid_latent_upscale_dit` есть соседний latent-upscale pipeline с `KSamplerSelect(lcm)`, однако он использует обычный алгоритм `lcm`, PiD conditioning и другой classType. Fragment прошёл schema и safe shape/constructor probe, но с моделью не исполнялся.

## 8. Частые ошибки

- Считают `scale_ratio` коэффициентом готового изображения. Он применяется к spatial-размеру latent tensor.
- Принимают `scale_steps = -1` за отключение. Это автоматический режим; для пустой последовательности используется 0.
- Полагают, что каждое увеличение умножает уже увеличенную форму. Цели считаются от исходной ширины и высоты.
- Выбирают коэффициент 20 только потому, что его разрешает widget. Площадь tensor и стоимость модели растут намного быстрее линейного коэффициента.
- Отождествляют ноду с `SamplerLCM`: здесь нет `s_noise`, `s_noise_end`, `noise_clip_std` и model-specific `noise_scaling`.
- Выдают соседний official PiD workflow за пример этой ноды, хотя `SamplerLCMUpscale` в нём отсутствует.

## 9. Ограничения и производительность

На каждый sigma-переход приходится один model prediction. После роста spatial-формы последующие model calls, denoised tensors и новый noise tensor становятся дороже по времени и памяти. Интерполяция тоже создаёт новый tensor; резкий коэффициент способен привести к нехватке памяти ещё до декодирования.

Алгоритм использует `torch.randn_like` напрямую, а не параметризованный `noise_sampler` из `sample_lcm`. Численное воспроизведение зависит от состояния генератора, которое организует окружающий sampling-путь. Нода не проверяет, способен ли checkpoint работать на меняющемся размере, и не оценивает качество интерполяции.

## 10. Совместимость и источники

Статья сверена с ComfyUI `0.32.0`, frontend `1.48.7`, commit `c2bcbecd82ec5ae66594340b395c24ef0217b238`, embedded docs `0.5.9` и workflow templates `0.1.42`. Runtime ID — `SamplerLCMUpscale`, модуль — `comfy_extras.nodes_advanced_samplers`; нода не experimental и не deprecated, replacement и execution aliases отсутствуют.

Embedded docs верно перечисляют порты и методы, но называют результат «higher resolution output while maintaining image quality». Source не даёт такой гарантии. Документация также помечает два advanced-входа как необязательные, хотя `/object_info` относит все три к required. В статье сохранён runtime-контракт.

- [Нода и алгоритм `sample_lcm_upscale`](https://github.com/Comfy-Org/ComfyUI/blob/c2bcbecd82ec5ae66594340b395c24ef0217b238/comfy_extras/nodes_advanced_samplers.py#L13-L62)
- [`common_upscale` и обработка пространственных осей](https://github.com/Comfy-Org/ComfyUI/blob/c2bcbecd82ec5ae66594340b395c24ef0217b238/comfy/utils.py#L1069-L1101)
- [Official workflow templates 0.1.42](https://pypi.org/project/comfyui-workflow-templates-json/0.1.42/)
