# SamplerARVideo: блочный сэмплер для Causal-WAN

`SamplerARVideo` создаёт объект `SAMPLER` для авторегрессионной генерации видео блоками. Он предназначен для Causal-WAN-совместимой модели, ведёт KV- и cross-attention-кеши и принимает пятиосевой latent `[B, C, T, H, W]`.

## 1. Что делает нода

Конструктор вызывает `ksampler("ar_video", {"num_frame_per_block": …})`. Алгоритм делит temporal-ось latent на блоки, полностью проходит schedule `SIGMAS` для одного блока, фиксирует его в кешах и только затем переходит к следующему.

Нода не превращает обычную image diffusion model в video-модель. До начала цикла реализация проверяет форму tensor и наличие у `diffusion_model` методов `init_kv_caches` и `init_crossattn_caches`; несовместимый checkpoint отвергается.

## 2. Место в графе

Выход подключают к `SamplerCustomAdvanced.sampler`. Рядом нужны `RandomNoise`, guider, `SIGMAS` и пятиосевой LATENT. MODEL в guider должна быть той же авторегрессионной моделью, для которой создан LATENT и schedule.

Для text-to-video LATENT может прийти из `EmptyARVideoLatent`. Для image-to-video нода `ARVideoI2V` клонирует MODEL, записывает закодированный стартовый кадр в `transformer_options.ar_config.initial_latent` и создаёт video LATENT нужной формы. Сам `SamplerARVideo` этих подготовительных действий не выполняет.

## 3. Вход

Единственный обязательный вход `num_frame_per_block: INT` имеет значение по умолчанию `1` и runtime-диапазон `1…64`. Tooltip называет 1 framewise-режимом, а 3 — chunkwise-режимом и требует соответствия training mode checkpoint.

В реализации значение применяется к третьей оси пятиосевого latent. У `EmptyARVideoLatent` число temporal-позиций равно `((length - 1) // 4) + 1`, поэтому widget нельзя безоговорочно трактовать как такое же количество декодированных видеокадров для любой модели.

## 4. Выход

Единственный выход — `SAMPLER`, не list-output. Он хранит зарегистрированную функцию `sample_ar_video` и `num_frame_per_block` в `extra_options`.

Объект не содержит checkpoint и video frames. Совместимость проверяется позже, когда sampler-runner передаст model wrapper, tensor и `SIGMAS` в алгоритм.

## 5. Как работает авторегрессионный цикл

Алгоритм требует ровно 5 измерений. Затем он получает внутреннюю diffusion model, создаёт KV-кеш на всю temporal-последовательность и cross-attention-кеш, а выход инициализирует нулевым tensor той же формы. Размер одного spatial frame sequence рассчитывается как `ceil(H / 2) × ceil(W / 2)` в latent-координатах.

Для каждого temporal-блока выполняются все переходы `SIGMAS`. На терминальном переходе блок становится равен `denoised`; на остальных создаётся свежий noise с seed `seed + block_index × 1000 + step_index`, после чего применяется flow-match формула `(1 - sigma_next) × denoised + sigma_next × noise`. Промежуточные записи KV-кеша откатываются, а завершённый блок фиксируется дополнительным model call при нулевой sigma.

Если задан `initial_latent`, алгоритм сначала копирует его в output, помещает `ar_state` в transformer options и делает нулевой model call для заполнения кеша. Блоки генерируются только для оставшейся temporal-части. В `finally` временный `ar_state` удаляется даже при ошибке.

## 6. Настройка размера блока

Используйте значение, для которого обучен checkpoint. Меньший блок увеличивает число авторегрессионных блоков и дополнительных commit-вызовов модели; больший обрабатывает больше temporal-позиций одновременно, но может потребовать больше рабочей памяти. Выбирать максимум 64 как способ ускорения без данных о training mode нельзя.

В официальном framewise case используются `num_frame_per_block = 1`, `CFGGuider(cfg = 1)` и `BasicScheduler(simple, 4, 1)`. Это согласованный пример для конкретного Causal Forcing pipeline, а не универсальная рекомендация для любого AR checkpoint.

## 7. Проверенный официальный fragment

Recipe «Causal Forcing: покадровый AR sampler» сохраняет точную связь `SamplerARVideo(1) → SamplerCustomAdvanced.sampler`. Она взята из `video_causal_forcing_i2v`, root UUID `b5d4e2f9-8c3a-4b0e-a4d2-f9e6b3c0a1d5`, subgraph `Image to Video (Causal Forcing Framewise)` с UUID `96ba6b5d-dd48-49b3-84c3-5b86eafc2a07`.

Полный census 512 JSON, 496 root-графов и 272 subgraph нашёл ровно один `SamplerARVideo`, mode 0, widgets `[1]`. В исходной topology `ARVideoI2V(832, 480, 81, 1)` подаёт MODEL в `CFGGuider` и `BasicScheduler`, LATENT — в `SamplerCustomAdvanced`; туда же входят `RandomNoise`, `SIGMAS` и текущий sampler. Fragment проверен по схеме и портам, но с Causal-WAN-весами не выполнялся.

## 8. Частые ошибки

- Подключают обычный 4D image latent. Алгоритм явно требует `[B, C, T, H, W]` и выдаёт `ValueError`.
- Используют checkpoint без cache API. Проверка завершится `TypeError` до sampling-loop.
- Выбирают block size по желаемой длине ролика, а не по training mode модели.
- Полагают, что `num_frame_per_block` задаёт общую длину. Длину задаёт temporal-размер LATENT.
- Смешивают MODEL после `ARVideoI2V` с LATENT или `SIGMAS` из другого model-sampling пути.
- Копируют четыре шага и CFG 1 из официального case на другой checkpoint без его рекомендаций.

## 9. Ограничения и производительность

Число основных model calls равно числу temporal-блоков, умноженному на число sigma-переходов. Дополнительно выполняется один нулевой commit-вызов на завершённый блок и, для I2V, один вызов для initial latent. Меньший block size обычно увеличивает число вызовов.

KV-кеш резервируется с учётом batch, всей temporal-длины и spatial sequence; расход памяти растёт вместе с ними и с архитектурой модели. Алгоритм вручную вызывает `torch.manual_seed` для каждого блока и шага, поэтому его воспроизводимость и влияние на глобальное состояние генератора следует проверять в полном pipeline. Работа на реальном Causal-WAN checkpoint, пиковая VRAM и время не измерялись.

## 10. Совместимость и источники

Статья закреплена на ComfyUI `0.32.0`, frontend `1.48.7`, commit `c2bcbecd82ec5ae66594340b395c24ef0217b238`, embedded docs `0.5.9` и workflow templates `0.1.42`. Точный ID — `SamplerARVideo`, модуль — `comfy_extras.nodes_ar_video`; нода не experimental и не deprecated, replacement и execution aliases отсутствуют.

Embedded docs верно называет Causal Forcing, Self-Forcing и требование совпадения block size с training mode, но не описывает 5D guard, cache API, I2V initial latent, формулу re-noise и стоимость commit-вызовов. Эти факты сверены по реализации и официальной topology.

- [Конструктор `SamplerARVideo`](https://github.com/Comfy-Org/ComfyUI/blob/c2bcbecd82ec5ae66594340b395c24ef0217b238/comfy_extras/nodes_ar_video.py#L44-L73)
- [ARVideoI2V и форма latent](https://github.com/Comfy-Org/ComfyUI/blob/c2bcbecd82ec5ae66594340b395c24ef0217b238/comfy_extras/nodes_ar_video.py#L76-L122)
- [Алгоритм `sample_ar_video`](https://github.com/Comfy-Org/ComfyUI/blob/c2bcbecd82ec5ae66594340b395c24ef0217b238/comfy/k_diffusion/sampling.py#L1845-L1957)
- [Official workflow templates 0.1.42](https://pypi.org/project/comfyui-workflow-templates-json/0.1.42/)
