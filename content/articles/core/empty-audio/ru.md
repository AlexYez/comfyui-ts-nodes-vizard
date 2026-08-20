# EmptyAudio: тишина заданной длины

## Назначение

`EmptyAudio` создаёт waveform из нулей — готовую цифровую тишину с заданными duration, sample rate и числом каналов. Выход сразу имеет тип `AUDIO`.

В эту партию нода вошла вместо отсутствующего в ComfyUI 0.32.0 NodeId `StableAudioEmptyLatentImage`. Это замена области исследования, а не runtime alias или официальная migration-связь.

## Место в графе

Тишину можно подать в audio concat, merge, preview, save или ноду, которой нужен заполнитель `AUDIO`. Она подходит для паузы или пустой дорожки известного формата.

`EmptyLatentAudio` работает до генерации и возвращает `LATENT`. `EmptyAudio` не требует модели или VAE и возвращает waveform, который уже можно обрабатывать как звук.

## Входы

`duration` — FLOAT от 0 до `2^64 − 1` секунд с шагом 0,01; по умолчанию 60. Верхняя runtime-граница не означает, что такой tensor можно выделить в памяти.

`sample_rate` — INT от 1 до 192 000, по умолчанию 44 100. `channels` — INT 1 или 2, по умолчанию 2. Оба поля отмечены как advanced.

## Выход

`AUDIO` содержит `waveform` формы `[1, channels, num_samples]` и целое `sample_rate`. Batch всегда равен 1.

Waveform имеет dtype `float32`, создаётся на CPU и заполнен нулями. Нода не добавляет filename, duration или channel labels в metadata.

## Как работает

`num_samples` вычисляется как `int(round(duration × sample_rate))`. Затем `torch.zeros` выделяет tensor формы `(1, channels, num_samples)`.

Округление выполняется один раз для общего числа samples. Например, 2 секунды при 44 100 Гц дают ровно 88 200 samples на канал. Значение duration 0 создаёт допустимый tensor с последним dimension 0.

## Параметры и настройка

Выберите sample rate, который ожидает следующая audio-нода. `EmptyAudio` не выполняет resampling и не согласует частоту с другим клипом автоматически.

Один канал создаёт mono, два — stereo с одинаковой тишиной. Для batch из нескольких клипов требуется отдельная batch-логика: входа batch_size у ноды нет.

## Проверенный пример

Fragment «Две секунды stereo-тишины 44,1 кГц» задаёт duration 2, sample rate 44 100 и channels 2. По формуле результат имеет shape `[1, 2, 88200]` и содержит 176 400 float32-нулей.

Synthetic execution в pinned ComfyUI environment дополнительно проверил короткий случай 0,01 секунды, 8000 Гц, mono: shape `[1, 1, 80]`, dtype float32, сумма 0. В 512 official workflow templates JSON 0.1.42 `EmptyAudio` не найден; полный пользовательский workflow не запускался.

## Частые ошибки

**Выход используют как latent.** `AUDIO` нельзя подключить к `KSampler.latent_image`. Для этого нужен `EmptyLatentAudio`.

**Огромную runtime-границу считают безопасной.** Нода выделяет весь waveform сразу и не ставит memory guard.

**Channels принимают за batch.** Первый dimension всегда 1; channels занимает вторую ось.

**Sample rate считают преобразованием другого звука.** Нода создаёт новый клип. Она не меняет существующий waveform.

## Ограничения и производительность

Память waveform примерно равна `duration × sample_rate × channels × 4` байта. Две секунды stereo при 44,1 кГц занимают 705 600 байт только под samples; служебные расходы tensor не включены.

Длинный клип или 192 кГц быстро увеличивают allocation. CPU tensor может позже копироваться на другое устройство следующей нодой. Нода не создаёт fade, dither и временные метки и не проверяет, принимает ли downstream пустой waveform длительностью 0.

## Совместимость и источники

Статья описывает ComfyUI 0.32.0 на commit `c2bcbecd82ec5ae66594340b395c24ef0217b238`. Runtime ID — `EmptyAudio`, python module — `comfy_extras.nodes_audio`. Запрошенный `StableAudioEmptyLatentImage` отсутствует и в exact `/object_info`, и в embedded docs 0.5.9.

Embedded docs по пути `comfyui_embedded_docs/docs/EmptyAudio/en.md` точно описывают silence и диапазоны, но не предупреждают, что верхняя duration допускает практически невозможный allocation и что tensor создаётся целиком на CPU.

- [Реализация `EmptyAudio`](https://github.com/Comfy-Org/ComfyUI/blob/c2bcbecd82ec5ae66594340b395c24ef0217b238/comfy_extras/nodes_audio.py#L756-L800)
- [Official workflow templates JSON 0.1.42](https://pypi.org/project/comfyui-workflow-templates-json/0.1.42/)
- [Pinned embedded docs 0.5.9](https://pypi.org/project/comfyui-embedded-docs/0.5.9/)
