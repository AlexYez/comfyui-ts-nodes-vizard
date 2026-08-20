# Обрезать и кодировать речь для LTX IA2V

В `template_image_speech_to_video` и `video_ltx2_3_ia2v` нода `TrimAudioDuration` с сохранёнными виджетами `0 / 60` передаёт звук в `LTXVAudioVAEEncode`. LTX Audio VAE приходит от специализированного loader, а latent затем получает noise mask и входит в более крупную audio/video цепочку.

Фрагмент сохраняет только доказанную связь trim → encode. Он не содержит mask, объединение AV latent, sampler и модели. Выход `LATENT` состоит из поля `samples`; вопреки тексту embedded docs encoder не добавляет sample rate и type.

Полные LTX графы не исполнялись. Унаследованный resample и encode проверены с fake VAE, а два exact-примера — полным census wheel 0.1.42.
