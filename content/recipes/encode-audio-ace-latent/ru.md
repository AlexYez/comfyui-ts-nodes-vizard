# Закодировать AUDIO для ACE-Step editing

В официальном ACE-Step music-to-music workflow `LoadAudio` подаёт waveform в `VAEEncodeAudio`, VAE приходит от `CheckpointLoaderSimple`, а полученный `LATENT` входит в `KSampler` как `latent_image`. Фрагмент оставляет только универсальный encode-узел и два внешних порта.

Используйте VAE из той же audio-модели. Если частота входа отличается от `vae.audio_sample_rate`, нода выполнит resample до кодирования. Выход содержит только поле `samples`; sampler, conditioning и checkpoint в fragment не входят.

Полный ACE-Step workflow и реальные веса не запускались. Топология проверена по wheel 0.1.42, а resample, перестановка осей и форма выходного словаря — на fake VAE.
