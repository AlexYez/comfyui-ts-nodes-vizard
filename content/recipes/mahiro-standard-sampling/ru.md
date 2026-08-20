# Mahiro перед KSampler

Соедините MODEL с `Mahiro`, а `patched_model` — с `KSampler`. Positive, negative и latent остаются внешними входами sampler.

KSampler использует runtime defaults ComfyUI 0.32.0: seed 0, 20 steps, cfg 8, Euler, simple и denoise 1. Bundle 0.1.42 не содержит прямого Mahiro case, поэтому fragment не задаёт модель и не представляет эти числа как рекомендацию.

Schema и exact-source formula проверены. Fragment не импортировался и не выполнялся; сравнивайте его с прямой MODEL-ветвью при тех же noise и sigmas.
