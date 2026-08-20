# Линейный CFG перед KSampler

Подайте video `MODEL` в `VideoLinearCFGGuidance` с `min_cfg = 1`, затем соедините её выход с `KSampler`, где `cfg = 2,5`. Для batch из нескольких кадров функция распределит коэффициент от 1 на первом кадре до 2,5 на последнем.

Параметры KSampler повторяют сериализованный SVD-пример `txt_to_image_to_video`: 20 steps, Euler, Karras, denoise 1. Positive, negative и latent должны быть подготовлены совместимой video-conditioning нодой.

Fragment проверен по schema и официальной topology. Checkpoint, исходное изображение и декодирование не включены; импорт и model run не выполнялись.
