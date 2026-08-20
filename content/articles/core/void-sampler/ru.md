# VOIDSampler: DDIM без стандартного масштабирования начального шума

## Что делает нода

`VOIDSampler` возвращает объект `SAMPLER` с циклом `VOID_DDIM`. Он предназначен для VOID video inpainting models, обученных с `CogVideoXDDIMScheduler`. В отличие от стандартной KSampler-подготовки, цикл начинает прямо с `noise.to(float32)` и не вызывает model sampling `noise_scaling`.

На каждом переходе текущая sigma переводится в `alpha = 1 / (1 + sigma²)`. Из текущего `x` и предсказанного `denoised` восстанавливается `pred_eps`, после чего следующая точка собирается из `denoised` и того же epsilon на `alpha_next`. Если следующая sigma равна нулю, результатом шага становится `denoised` без этой формулы.

Нода не содержит widgets и не запускает sampling сама. Она поставляет алгоритм для входа `sampler` в `SamplerCustom` или `SamplerCustomAdvanced`.

## Когда использовать и когда не использовать

Используйте `VOIDSampler` только с VOID inpainting checkpoints и полной VOID conditioning/noise-ветвью. Source объясняет причину: VOID обучался на входном шуме со стандартным отклонением около единицы, тогда как стандартное KSampler scaling на большой sigma могло бы умножить его примерно в 4500 раз.

Для первого прохода подойдёт `RandomNoise`. Для второго официального прохода используется `VOIDWarpedNoiseSource`, который превращает optical-flow warped latent noise в объект `NOISE`. Сам sampler одинаков в обеих ветвях.

Не выбирайте его как универсальный DDIM для SD, Flux, LTX или обычного CogVideoX workflow. Он намеренно обходит стандартный model sampling contract. Совпадение типа `SAMPLER` не означает совместимость математики обучения.

## Короткий рецепт подключения

1. Создайте `VOIDSampler`.
2. Подайте его выход в `sampler` узла `SamplerCustomAdvanced`.
3. Для первого прохода подключите `RandomNoise`; для refinement pass — `VOIDWarpedNoiseSource`.
4. Получите `GUIDER` из VOID model и conditioning, а `SIGMAS` — из scheduler того же model.
5. Подайте latent из `VOIDInpaintConditioning` и запускайте только после проверки всех VOID-весов.

Fragment «VOID sampler → SamplerCustomAdvanced» воспроизводит одну точную официальную связь и оставляет четыре остальных входа sampler внешними. Полного workflow нет: двухпроходный официальный граф зависит от VOID UNet pass 1/pass 2, CogVideoX VAE, T5/CLIP, optical-flow model и mask-preprocessing.

## Входы, выходы и параметры

У `VOIDSampler` нет входов и настраиваемых параметров. Вызов `execute()` каждый раз создаёт новый `VOID_DDIM`.

Выход `SAMPLER` подключается к custom sampler. Параметры sampling — noise seed, conditioning, CFG, sigmas, latent и callback — приходят не в ноду, а позже через `SamplerCustomAdvanced` и внутренний sampler contract.

Внутренний метод принимает `latent_image` и `denoise_mask`, но в собственном цикле их не читает. Это важное отличие от sampler paths, которые смешивают исходный latent по маске на каждом шаге. В VOID mask semantics уже входят в `VOIDInpaintConditioning` и модельную ветвь; не приписывайте их этому объекту sampler.

## Типовые связки

Полный рекурсивный просмотр 512 JSON официального wheel нашёл два `VOIDSampler`, оба в одном subgraph `Video Inpaint (VOID)` файла `utility_void_video_inpainting.json`. Каждый подключён непосредственно к `SamplerCustomAdvanced`.

Первый pass использует `RandomNoise`, `CFGGuider`, `VOIDSampler`, `BasicScheduler` с `simple / 30 / denoise 1` и latent из `VOIDInpaintConditioning`. Его результат декодируется и служит материалом для optical-flow warped noise.

Второй pass заменяет `RandomNoise` на `VOIDWarpedNoiseSource`, но снова использует `CFGGuider`, такой же `VOIDSampler`, `BasicScheduler` и conditioning latent. Это не два режима одной ноды: различие формирует источник noise и отдельный VOID checkpoint.

## Практический пример

Exact-source probe без весов прошёл sigma-последовательность `[2, 1, 0.5, 0]` с простым model stub. Результат точно совпал с независимым ручным расчётом alpha-space DDIM, callback вызвался три раза с total `3`, а `model_options` и seed были переданы в каждый model call.

Float64 noise сразу стал float32. Для расписания из одной sigma model не вызывалась, цикл вернул тот же noise в float32. Для пары `[1, 0]` выход в точности совпал с `denoised` первого вызова — terminal-zero branch сработал без вычисления `pred_eps`.

Probe передал разные объекты `latent_image` и `denoise_mask`: результат не изменился, что соответствует отсутствию обращений к ним в source. Это численная проверка цикла, а не запуск VOID weights и не оценка восстановленного видео.

## Частые ошибки и способы проверки

**На вход подан обычный latent noise через стандартный KSampler path.** VOID требует custom sampler, который сам начинает с unscaled noise. Проверьте, что output `VOIDSampler` действительно подключён к `SamplerCustomAdvanced`.

**Второй проход мерцает или теряет движение.** В официальном графе pass 2 использует `VOIDWarpedNoiseSource`, созданный из optical-flow warped noise первого результата. `RandomNoise` во втором проходе меняет задачу.

**Ожидалось, что `denoise_mask` ограничит update.** Внутренний `VOID_DDIM.sample` этот аргумент не использует. Проверьте mask и latent на выходе `VOIDInpaintConditioning`, а не ищите mask widget у sampler.

**Последовательность sigmas идёт вверх или содержит ноль до конца.** Формула рассчитана на обычный убывающий schedule. При текущей sigma `0` и следующей ненулевой знаменатель `sqrt(1 − alpha)` обращается в ноль. Используйте подтверждённый VOID schedule.

**Один sigma-элемент ничего не сделал.** Число model calls равно `len(sigmas) − 1`. Для реального denoise нужен хотя бы один переход.

## Производительность и внутреннее поведение

Сам объект sampler почти ничего не занимает. Стоимость sampling определяется `len(sigmas) − 1` вызовами VOID model. Дополнительные операции на шаге — несколько element-wise умножений, сложений и вычисление двух scalar alpha.

Начальный noise принудительно переводится в float32, независимо от dtype источника. `s_in` создаётся длиной batch и масштабирует sigma для model call. `model_options` и seed берутся из `extra_args` и передаются без изменений.

Цикл детерминирован относительно входного noise и model predictions: собственного добавочного stochastic term нет. `latent_image` и `denoise_mask` не участвуют. Callback получает индекс, `denoised`, текущее `x` и общее число переходов перед update шага.

## Совместимость, изменения и устаревание

Статья проверена для ComfyUI `0.32.0`, frontend `1.48.7` и модуля `comfy_extras.nodes_void`. Runtime fingerprint: `sha256:53195b08cfc641e1998462fcd643188458853053218f8fa4ac790ae8af0aa1d3`.

Нода не experimental, deprecated, dev-only и не API node. Display name и search aliases отсутствуют; Node Replacement API не содержит записи. Python alias `get_sampler = execute` не является alias NodeId.

Embedded docs 0.5.9 правильно ограничивают ноду VOID и называют custom samplers/noise sources, но не раскрывают terminal-zero branch, игнорирование latent/mask, float32 cast и one-sigma behavior. После обновления source следует проверять эти детали отдельно от статической schema.

## Связанные ноды и источники

`RandomNoise` питает первый официальный проход. `BasicScheduler` поставляет `SIGMAS`, `CFGGuider` — guider, `SamplerCustomAdvanced` выполняет цикл. `VOIDQuadmaskPreprocess` готовит маску раньше в графе. Подробности 32-канального conditioning, RAFT-переноса шума и адаптера LATENT→NOISE разобраны в отдельных статьях `VOIDInpaintConditioning`, `VOIDWarpedNoise` и `VOIDWarpedNoiseSource`.

- [Реализация `VOIDSampler` и `VOID_DDIM`](https://github.com/Comfy-Org/ComfyUI/blob/c2bcbecd82ec5ae66594340b395c24ef0217b238/comfy_extras/nodes_void.py#L409-L467)
- [CogVideoX `V_PREDICTION_DDPM`](https://github.com/Comfy-Org/ComfyUI/blob/c2bcbecd82ec5ae66594340b395c24ef0217b238/comfy/model_sampling.py#L57-L79)
- [Встроенная документация 0.5.9](https://github.com/Comfy-Org/embedded-docs/blob/1d258cf6e374d60d138a2bfcd273c7e11f750ef9/comfyui_embedded_docs/docs/VOIDSampler/en.md)
- [Официальный VOID workflow 0.1.42](https://pypi.org/project/comfyui-workflow-templates-json/0.1.42/)
