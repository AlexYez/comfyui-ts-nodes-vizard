# AudioEncoderEncode: получить признаки из AUDIO

## Что делает нода

`AudioEncoderEncode` запускает загруженный `AUDIO_ENCODER` на waveform и выдаёт контейнер `AUDIO_ENCODER_OUTPUT`. Это не звук и не audio latent: внутри находятся признаки, которые model-specific conditioning использует для синхронизации речи, движения или мимики.

Сама нода тонкая: она берёт `audio["waveform"]` и `audio["sample_rate"]`, вызывает `audio_encoder.encode_audio(...)` и возвращает результат без дополнительных преобразований. Существенная логика находится во wrapper encoder.

Стандартный wrapper загружает модель на вычислительное устройство, пересчитывает waveform к 16000 Гц и возвращает три поля: `encoded_audio`, `encoded_audio_all_layers` и `audio_samples`.

## Когда использовать и когда не использовать

Используйте ноду, когда downstream port прямо требует `AUDIO_ENCODER_OUTPUT`: HuMo, Wan Sound-to-Video и InfiniteTalk — подтверждённые официальные случаи. Выберите именно тот encoder, на признаках которого обучена модель.

Не подключайте результат к `AUDIO`, `LATENT` или `CONDITIONING`: тип и семантика отличаются. Чтобы добавить исходную дорожку к видео, ответвите оригинальный `AUDIO` в `CreateVideo`, а не пытайтесь декодировать encoder output.

Для LTX audio latent существует `LTXVAudioVAEEncode`. Он сохраняет структуру звука в латентном кодеке, тогда как здесь формируются признаки для управления моделью.

## Короткий рецепт подключения

1. Загрузите совместимый Whisper или Wav2Vec2 через `AudioEncoderLoader`.
2. Подайте непустой `AUDIO` из `LoadAudio`.
3. Соедините оба входа `AudioEncoderEncode`.
4. Передайте output только в подтверждённый model-specific consumer.
5. При сборке видео ответвите исходный AUDIO отдельно, если нужно сохранить дорожку.

Рецепт повторяет HuMo: `AudioEncoderLoader(whisper_large_v3_fp16.safetensors) → AudioEncoderEncode`, а внешние AUDIO и downstream consumer оставлены пользователю. Полная модель и веса не запускались.

## Входы, выходы и параметры

`audio_encoder` имеет тип `AUDIO_ENCODER` и должен прийти из совместимого loader. `audio` содержит waveform `[B,C,T]` и целочисленную `sample_rate`. У ноды нет widgets, optional inputs или собственной настройки длительности.

Выход `AUDIO_ENCODER_OUTPUT` — непрозрачный для UI словарь. Стандартная реализация кладёт `encoded_audio` — последний результат encoder, `encoded_audio_all_layers` — tuple промежуточных и финального слоёв, `audio_samples` — длину после resample к 16 кГц.

Форма признаков зависит от архитектуры. Wav2Vec2 base и large различаются размерностью и числом слоёв; Whisper Large V3 использует mel extractor и свой transformer. Поэтому универсального числа токенов в schema нет.

## Типовые связки

`LoadAudio → AudioEncoderEncode` подаёт waveform, а `AudioEncoderLoader → AudioEncoderEncode` — модель. Это минимальная доказанная пара входов.

`AudioEncoderEncode → WanHuMoImageToVideo` встречается в HuMo. `→ WanInfiniteTalkToVideo` найдено четыре раза в recursive census; `→ WanSoundImageToVideo` — два прямых раза, не считая внутренних subgraph types.

Некоторые consumers собирают все слои через `torch.cat`, другие — через `torch.stack` и вычисляют длину как `audio_samples // 640`. Отсюда следует, что подмена encoder с другим числом слоёв может пройти socket-проверку, но нарушить модельный контракт.

## Практический пример

В 512 официальных JSON найдено семь `AudioEncoderEncode` в трёх файлах: шесть mode `Always`, один `Bypass`. Четыре расположены в subgraph InfiniteTalk, два — в корневом Wan 2.2 S2V, один — в корневом HuMo.

HuMo связывает `LoadAudio` №58, `AudioEncoderLoader` №57 и encode №56; output идёт в `WanHuMoImageToVideo` №65. В Wan S2V активная ветвь использует Wav2Vec2 large English и разветвляет output на несколько model consumers.

Fake-encoder probe подтвердил, что нода передаёт исходный waveform и sample rate без копии и возвращает тот же словарь результата. Отдельный wrapper probe подтвердил resample 8→16 кГц и `audio_samples=16`; нейросетевые слои не выполнялись.

## Частые ошибки и проверка

**Тип сокета совпал, модель — нет.** Сверьте encoder filename с официальным workflow именно вашего consumer. Whisper и Wav2Vec2 нельзя выбирать по памяти или языку без модельной документации.

**Длинное аудио вызывает OOM.** Нода не обрезает waveform. Сначала ограничьте длительность через `TrimAudioDuration`, затем повторите encode.

**Ожидалось сохранение исходной sample rate.** Wrapper всегда приводит звук к 16000 Гц и записывает число уже пересчитанных отсчётов. Исходная частота в output отдельно не хранится.

**Выход нельзя прослушать.** Это признаки, а не waveform. Для контроля подключите исходный AUDIO к `PreviewAudio` или `CreateVideo` параллельно.

## Производительность и внутреннее поведение

Перед inferencing wrapper вызывает `load_model_gpu(self.patcher)`. Затем `torchaudio.functional.resample` целиком обрабатывает вход до 16 кГц и переносит его на `load_device` модели.

Wav2Vec2 сначала усредняет каналы, по необходимости нормализует весь tensor, извлекает свёрточные признаки и проходит transformer. Whisper также сводит каналы в mono, обрезает либо дополняет каждый batch-элемент до 30 секунд и строит 128-bin mel spectrogram.

Эти различия важны: Whisper фиксирует окно 480000 отсчётов, а общий wrapper всё равно сообщает `audio_samples` до внутреннего обрезания/дополнения. Consumer обязан интерпретировать поля в соответствии со своим encoder.

## Совместимость, изменения и устаревание

Статья относится к ComfyUI `0.32.0`, frontend `1.48.7`, runtime ID `AudioEncoderEncode`, модуль `comfy_extras.nodes_audio_encoder`. Fingerprint: `sha256:f391593cefb0b34f2dad1a4d2f700039a0e2727458639d2a65573ba075362128`.

Нода активна, не experimental, не deprecated, не dev-only и не API node. Formal replacement отсутствует. Display name в raw runtime не задан, поэтому UI может показывать системный ID.

Embedded docs 0.5.9 верно называют общий результат, но не перечисляют реальные поля, обязательный resample к 16 кГц, послойные признаки и архитектурные различия. Эти детали проверены по коду и официальным consumers.

## Связанные ноды и источники

`AudioEncoderLoader` создаёт wrapper, `LoadAudio` поставляет waveform. HuMo, InfiniteTalk и Wan Sound-to-Video потребляют признаки. `VAEEncodeAudio` решает другую задачу — кодирует звук в latent.

- [Реализация `AudioEncoderEncode`](https://github.com/Comfy-Org/ComfyUI/blob/c2bcbecd82ec5ae66594340b395c24ef0217b238/comfy_extras/nodes_audio_encoder.py#L34-L50)
- [Внутренний `encode_audio`](https://github.com/Comfy-Org/ComfyUI/blob/c2bcbecd82ec5ae66594340b395c24ef0217b238/comfy/audio_encoders/audio_encoders.py#L36-L47)
- [Официальный HuMo template](https://github.com/Comfy-Org/workflow_templates/blob/cca1ea5ea4560108ecc2f44dee951f41ea433062/templates/video_humo.json)
