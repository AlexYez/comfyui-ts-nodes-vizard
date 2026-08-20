# Tiled decode с размером 512 и overlap 64

Подайте audio `LATENT` и совместимый `VAE` в `VAEDecodeAudioTiled`. Значения `512` и `64` — defaults схемы 0.32.0. Больший tile обычно требует больше памяти, а overlap участвует в сведении границ; итог зависит от архитектуры VAE.

В официальных workflow templates 0.1.42 exact-нода не встречается, поэтому этот fragment помечен как source-derived. Он не обещает, что default-параметры оптимальны для любого audio VAE, и не подменяет сравнение с обычным `VAEDecodeAudio`.

Fake-VAE probe подтвердил передачу `tile_x=512`, `tile_y=512`, `overlap=64`, последующую перестановку каналов и std-scaling. Настоящий tiled decode длинного аудио не выполнялся.
