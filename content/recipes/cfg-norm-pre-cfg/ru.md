# CFGNorm pre_cfg в JoyAI-графе

Подайте MODEL в `CFGNorm`, установите `strength = 1` и `pre_cfg = true`, затем соедините `patched_model` с `KSampler`. Positive, negative и latent остаются внешними входами.

KSampler повторяет сериализованные параметры `image_joyai_image_edit`: seed 42 в fixed-режиме, 40 steps, cfg 4, Euler, normal, denoise 1. В source fragment хранит только само число seed, потому что режим control-after-generate относится к UI widget.

Fragment сверён с runtime schema и официальным subgraph. JoyAI weights, encoder и VAE не включены; импорт и generation run не выполнялись.
