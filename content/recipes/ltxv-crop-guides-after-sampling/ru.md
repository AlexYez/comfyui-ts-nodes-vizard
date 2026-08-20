# Удалить LTXV guide positions после sampling

Подключите к `LTXVCropGuides` positive/negative от той же цепочки `LTXVAddGuide`, которая использовалась sampling-ветвью, и полученный video LATENT. Если sampler возвращает joint AV latent, сначала отделите видео через `LTXVSeparateAVLatent`.

Выход LATENT можно отправить в VAE decode или `LTXVLatentUpsampler`; очищенное conditioning — в guider следующей стадии. Не подключайте pre-sampling latent: Crop удаляет temporal tail сразу и тем самым лишит модель guide samples.

Fragment намеренно состоит из одной ноды с external inputs. Он отражает official post-sampling placement, но не выдаёт отсутствующий sampler за готовый workflow. Полный graph не исполнялся.
