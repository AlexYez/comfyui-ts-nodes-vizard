# FreeU: source-derived runtime defaults

Fragment вставляет `FreeU` с defaults ComfyUI 0.32.0: `b1 = 1.1`, `b2 = 1.2`, `s1 = 0.9`, `s2 = 0.2`. Подайте выход в прежний sampling path и сравните с полностью обойдённой нодой при одинаковом seed.

Patch требует `unet_config.model_channels` и 4D decoder features. Он срабатывает только при `4×` и `2×` channel counts; 5D skip-тензор exact helper не обрабатывает даже через CPU fallback.

Official wheel 0.1.42 не содержит FreeU. Fragment получен из pinned source и runtime schema, не включает полный workflow и не подтверждает качество defaults для конкретного checkpoint.
