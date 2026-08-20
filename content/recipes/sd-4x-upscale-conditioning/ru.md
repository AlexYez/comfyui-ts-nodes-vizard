# SD x4 Upscaler conditioning для KSampler

Подайте low-resolution `IMAGE` и positive/negative `CONDITIONING` в `SD_4XUpscale_Conditioning`. Три выхода соедините с `KSampler`, а в `model` подайте именно модель семейства Stable Diffusion x4 Upscaler.

При `scale_ratio = 4.0` нода создаёт latent примерно в четыре раза шире и выше исходного изображения. `noise_augmentation = 0.0` оставляет low-resolution условие без добавочного шума на стороне модели.

Этот fragment выведен из node и model-consumer source. В официальном wheel 0.1.42 exact NodeId отсутствует, поэтому параметры KSampler не выдаются за официальный пресет и должны подбираться под checkpoint.

Полный fragment не исполнялся с SD x4 моделью. Синтетическая проверка покрывает размеры, нормализацию, копирование metadata и нулевой latent.

Редактор пока не проверил материал вручную.
