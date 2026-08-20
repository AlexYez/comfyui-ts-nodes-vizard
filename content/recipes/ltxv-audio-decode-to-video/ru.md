# Декодировать LTX audio latent и добавить к видео

Официальные LTX 2.x subgraph отделяют audio latent через `LTXVSeparateAVLatent`, декодируют его в `LTXVAudioVAEDecode` и подключают `Audio` к optional-входу `CreateVideo`. В репрезентативном LTX 2.3 text-to-video узле `CreateVideo` сохранено `24 fps`.

Фрагмент начинает с внешнего audio `LATENT`, поэтому не включает AV-split, sampler и модели. Внешний IMAGE batch должен соответствовать нужной длительности; одна лишь нода CreateVideo не синхронизирует содержимое по смыслу.

Точная связь decode → CreateVideo найдена у всех 21 LTX decoder в wheel. Fake-VAE probe проверил форму waveform и sample rate, но реальный VAE, video encode и воспроизведение не запускались.
