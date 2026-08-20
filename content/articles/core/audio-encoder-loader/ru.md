# AudioEncoderLoader: загрузить Whisper или Wav2Vec2 encoder

## Что делает нода

`AudioEncoderLoader` читает отдельную модель из `models/audio_encoders` и возвращает объект `AUDIO_ENCODER`. Этот объект преобразует waveform в последовательность признаков для video-моделей, которые управляются речью или звуком.

После чтения state dict ComfyUI распознаёт две группы архитектур: Wav2Vec2 и Whisper Large V3. Wav2Vec2 определяется по `encoder.layer_norm.bias`; размер 1024 выбирает large-конфигурацию, 768 — base. Whisper определяется по `model.encoder.embed_positions.weight`.

Файл с неизвестной сигнатурой или неподдержанной размерностью отклоняется. Нода не угадывает архитектуру по имени и не скачивает веса автоматически.

## Когда использовать и когда не использовать

Используйте loader перед `AudioEncoderEncode` в HuMo, Wan Sound-to-Video и InfiniteTalk pipeline. Официальные шаблоны показывают Whisper Large V3 для HuMo, Wav2Vec2 large English для Wan S2V и Wav2Vec2 Chinese base для InfiniteTalk.

Не считайте эти модели взаимозаменяемыми. Downstream нода может ожидать число слоёв, размер признаков и обучение конкретного encoder. Socket `AUDIO_ENCODER_OUTPUT` подтверждает контейнер, но не семантическое соответствие модели.

Для кодирования в audio latent нужен VAE-loader, а не этот encoder. `AUDIO_ENCODER` выдаёт признаки conditioning и не умеет обратно восстанавливать waveform.

## Короткий рецепт подключения

1. Поместите доказанную модель в `models/audio_encoders`.
2. Выберите её в `audio_encoder_name`.
3. Подключите `AUDIO_ENCODER` к `AudioEncoderEncode.audio_encoder`.
4. Подайте в encode тот же `AUDIO`, который соответствует видео или управляющей речи.
5. Передайте `AUDIO_ENCODER_OUTPUT` только в совместимую conditioning-ноду модели.

Рецепт каталога повторяет официальный HuMo участок: `AudioEncoderLoader(whisper_large_v3_fp16.safetensors) → AudioEncoderEncode`, а AUDIO остаётся внешним. Веса и полный HuMo workflow не выполнялись.

## Входы, выходы и параметры

`audio_encoder_name` — динамический combo из каталога `audio_encoders`. В чистом snapshot options пусты, поскольку локальные имена весов не входят в воспроизводимый inventory и schema fingerprint.

Выход называется `AUDIO_ENCODER`. У ноды нет widgets для device, dtype или режима модели. При создании wrapper ComfyUI выбирает text-encoder load device, offload device и dtype через `model_management`.

Поддержанные расширения берутся из общего множества model-файлов ComfyUI. Безопасный формат safetensors предпочтительнее; само расширение не доказывает, что state dict относится к поддержанной архитектуре.

## Типовые связки

`AudioEncoderLoader → AudioEncoderEncode` встречается семь раз в официальном wheel, потому что каждый encode требует загруженный wrapper. Затем результат идёт в model-specific conditioning.

В `video_humo.json` encoder output подключён к `WanHuMoImageToVideo`. В Wan 2.2 Sound-to-Video он разветвляется между несколькими внутренними subgraph и `WanSoundImageToVideo`. В InfiniteTalk тот же тип подключён к `WanInfiniteTalkToVideo`.

`LoadAudio` обычно подаёт waveform параллельно в encoder и в `CreateVideo`, чтобы одна дорожка управляла генерацией и сохранялась в результате. Эта топология не означает, что output encoder содержит воспроизводимый звук.

## Практический пример

Полная перепись 512 JSON и вложенных subgraph нашла пять `AudioEncoderLoader` в трёх файлах: четыре mode `Always`, один `Bypass`. Все пять связаны с `AudioEncoderEncode`.

`video_humo.json` использует `whisper_large_v3_fp16.safetensors`. Два активных/выключенных экземпляра в Wan S2V хранят `wav2vec2_large_english_fp16.safetensors`. Две ветви InfiniteTalk используют `wav2vec2-chinese-base_fp16.safetensors`.

Это реальные preset names, но выбор языка нельзя свести только к английскому или китайскому в имени. Совместимость зависит от того, на каких признаках обучен downstream model.

## Частые ошибки и проверка

**Список пуст.** Проверьте `models/audio_encoders`, расширение и обновление списка. Папки `checkpoints` и `text_encoders` для этой ноды не подходят.

**`audio encoder file is invalid`.** State dict не содержит поддержанной Wav2Vec2/Whisper сигнатуры. Не переименовывайте случайный checkpoint под официальное имя; сверяйте источник и размер.

**Wav2Vec2 сообщает unsupported embed_dim.** В версии 0.32.0 loader принимает только 1024 и 768 для распознанной ветви. Другая конфигурация требует поддержки в коде.

**Граф выполняется, но conditioning не подходит.** Проверьте конкретный model preset: Whisper, Wav2Vec2 large и base имеют разное число слоёв и размерность. Тип сокета этого не проверяет.

## Производительность и внутреннее поведение

`load_torch_file(..., safe_load=True)` читает веса на CPU. Для safetensors используется safe reader; для прочих поддержанных форматов pinned ComfyUI вызывает `torch.load(..., weights_only=True)`.

После распознавания создаётся `AudioEncoderModel`, внутри — Wav2Vec2 либо Whisper. Модель переводится в `eval`, оборачивается `CoreModelPatcher`, а рабочая частота фиксируется на 16000 Гц. При encode wrapper загружает модель на выбранное устройство.

`load_state_dict(strict=False)` разрешает missing и unexpected keys, но печатает предупреждения. Это облегчает варианты упаковки, однако предупреждение нельзя игнорировать без проверки: пропущенные веса способны сделать признаки неверными.

## Совместимость, изменения и устаревание

Проверено на ComfyUI `0.32.0`, frontend `1.48.7`, runtime ID `AudioEncoderLoader`, модуль `comfy_extras.nodes_audio_encoder`. Fingerprint: `sha256:1081da530587f98b6a1d013f4ee13a73097333b81c676f78a0a099ee052661bd`.

Нода активна, не experimental, не deprecated, не dev-only и не API node. Formal replacement отсутствует. Локальный список файлов исключён из fingerprint.

Embedded docs 0.5.9 описывают общий loader, но не перечисляют распознаваемые архитектуры, размеры Wav2Vec2, фиксированные 16 кГц и предупреждения strict=False. Эти детали сверены с реализацией.

## Связанные ноды и источники

`AudioEncoderEncode` запускает модель на waveform. `LoadAudio` готовит вход. `LTXVAudioVAELoader` и `VAEEncodeAudio` относятся к latent-кодеку и выполняют другую задачу.

- [Реализация `AudioEncoderLoader`](https://github.com/Comfy-Org/ComfyUI/blob/c2bcbecd82ec5ae66594340b395c24ef0217b238/comfy_extras/nodes_audio_encoder.py#L8-L31)
- [Распознавание audio encoders](https://github.com/Comfy-Org/ComfyUI/blob/c2bcbecd82ec5ae66594340b395c24ef0217b238/comfy/audio_encoders/audio_encoders.py#L9-L92)
- [Официальный HuMo template](https://github.com/Comfy-Org/workflow_templates/blob/cca1ea5ea4560108ecc2f44dee951f41ea433062/templates/video_humo.json)
