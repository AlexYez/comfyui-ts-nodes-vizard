# Две секунды stereo-тишины 44,1 кГц

`EmptyAudio` получает duration 2, sample rate 44 100 и channels 2. Результат — float32 waveform формы `[1, 2, 88200]`, заполненный нулями, и metadata `sample_rate: 44100`.

Fragment не требует входов, модели или VAE. Подключите его AUDIO-выход к concat, merge, preview или save с совместимым sample rate.

Нода отсутствует в 512 official workflow templates JSON 0.1.42. Формула и короткий synthetic execution проверены, но полный пользовательский граф не запускался; статус — `in_review`.
