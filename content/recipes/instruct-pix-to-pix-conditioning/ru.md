# Image-edit conditioning для KSampler

Подайте positive и negative `CONDITIONING`, совместимый `VAE` и редактируемый `IMAGE` в `InstructPixToPixConditioning`. Три выхода подключите к одноимённым входам `KSampler`; модель сэмплера должна поддерживать image-conditioning этого семейства.

Связка трёх выходов с sampler повторяет официальные `flux_canny_model_example`, `flux_depth_lora_example`, `hidream_e1_1` и `hidream_e1_full`. В первых двух случаях consumer — `KSampler`, в HiDream — `DualCFGGuider` и `SamplerCustomAdvanced`; fragment выбирает более компактный первый вариант.

Seed сделан фиксированным, а `cfg = 1.0`, `euler`, `normal`, 20 steps повторяют существенные настройки Flux Canny case. Это не означает совместимость любого checkpoint с этими параметрами.

Fragment структурно проверен, но не исполнялся с моделью, VAE и настоящим изображением.

Редактор пока не проверил материал вручную.
