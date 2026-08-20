# Загрузить SVD-XT и подготовить условия для видео по изображению

Установите `svd_xt.safetensors` в зарегистрированный каталог контрольных точек. `ImageOnlyCheckpointLoader` передаст `CLIP_VISION` и `VAE` в `SVD_img2vid_Conditioning`, а `MODEL` — в `VideoLinearCFGGuidance` с `min_cfg = 1`.

Подайте одно исходное `IMAGE`. Значения `1024 × 576`, 25 кадров, `motion_bucket_id = 127`, `fps = 6` и нулевой `augmentation_level` взяты из официального `txt_to_image_to_video`. Подключите `positive`, `negative`, `latent` и настроенную `MODEL` к совместимому сэмплеру; эта последующая часть намеренно не включена.

`fps = 6` — условие SVD, а не скорость видеофайла. В официальном графе последующий `CreateVideo` использует частоту кадров 10. Фрагмент прошёл проверку схемы и безопасные проверки без модели, но контрольная точка, сэмплер и полный граф не запускались. Редактор пока не проверил материал вручную.

Источники: [реализация нод](https://github.com/Comfy-Org/ComfyUI/blob/c2bcbecd82ec5ae66594340b395c24ef0217b238/comfy_extras/nodes_video_model.py#L10-L57), [официальный граф](https://github.com/Comfy-Org/workflow_templates/blob/cca1ea5ea4560108ecc2f44dee951f41ea433062/templates/txt_to_image_to_video.json).
