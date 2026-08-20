# Legacy LTXV image-to-video 768 × 512, 97 кадров

Fragment переносит два exact узла из `ltxv_image_to_video.json`: `LTXVImgToVideo` №77 с `[768,512,97,1,0.15]` и `LTXVConditioning` №69 с `25 fps`. Positive, negative, VAE и IMAGE остаются внешними.

LATENT-выход `i2v` подключите к совместимому LTXV scheduler и sampler. Conditioning outputs передайте в ту же sampling-ветвь. Strength `0.15` означает noise mask `0.85` на закодированных positions; это не 15-процентное смешивание samples.

Рецепт основан на legacy root template и не объявлен современной универсальной рекомендацией. Checkpoint, prompts, sampler и полная генерация в пакет не входят; `exampleExecuted=false` сохраняется до отдельного запуска с весами.
