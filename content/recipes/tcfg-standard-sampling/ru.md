# TCFG перед KSampler

Соедините MODEL с `TCFG`, а `patched_model` — с `KSampler`. Positive и negative должны быть реальными совместимыми conditions: при отсутствующей unconditional-ветви hook пропускает SVD-преобразование.

KSampler использует runtime defaults ComfyUI 0.32.0: seed 0, 20 steps, cfg 8, Euler, simple и denoise 1. Официальный bundle 0.1.42 не содержит TCFG, поэтому эти settings не выдаются за model preset.

Fragment проверен по schema и exact source, но не импортировался и не выполнялся. Для оценки соберите параллельную MODEL-ветвь без TCFG при неизменных остальных входах.
