# Пустой LTXV latent → стартовое изображение inplace

Fragment повторяет узлы №295 и №296 из subgraph `video_ltx2_3_i2v`: `EmptyLTXVLatentVideo(768,512,97,1)` подключён к `LTXVImgToVideoInplace(strength=0.7, bypass=false)`. IMAGE и VAE остаются внешними входами.

Перед official Inplace обычно стоит `LTXVPreprocess`; здесь preprocessing не включён, потому что его параметры зависят от исходника. После Inplace передайте LATENT в `LTXVAddGuide`, `LTXVConcatAVLatent` или подтверждённую sampling-ветвь.

При strength `0.7` encoded positions получают noise mask `0.3`, хотя samples VAE записываются полностью. Полный video workflow и реальные веса не исполнялись.
