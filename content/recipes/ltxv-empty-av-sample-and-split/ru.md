# Пустой LTXV audio latent → AV sampling → разделение

Этот fragment сохраняет повторяющуюся структуру официальных LTX 2.x subgraph. `LTXVEmptyLatentAudio` создаёт второй поток с настройками `97`, `25`, `1`; `LTXVConcatAVLatent` соединяет его с внешним видеолатентом; `SamplerCustomAdvanced` обрабатывает joint AV latent; `LTXVSeparateAVLatent` возвращает видео и аудио на разные выходы.

Перед вставкой подготовьте совместимые `VAE`, `NOISE`, `GUIDER`, `SAMPLER`, `SIGMAS` и video `LATENT`. Число `97` взято из официального LTX 2.3 ID-LoRA template. Для другого ролика замените его фактическим числом кадров и сохраните ту же частоту кадров, что использует видеоветвь.

После разделения подключите `video_latent` к подходящему video VAE decode или следующей LTXV-стадии. `audio_latent` передайте в `LTXVAudioVAEDecode` либо сохраните для повторного Concat. Полный diffusion/model workflow и реальные веса этим рецептом не исполнялись.
