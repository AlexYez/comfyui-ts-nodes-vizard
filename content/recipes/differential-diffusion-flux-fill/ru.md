# DifferentialDiffusion перед KSampler в Flux Fill

Подайте Flux Fill MODEL в `DifferentialDiffusion` со strength 1, затем соедините MODEL с `KSampler`. Fragment повторяет локальные settings `flux_fill_outpaint_example`: seed 164211176398261 в randomize-режиме, 20 steps, cfg 1, Euler, normal, denoise 1.

Positive, negative и latent с denoise mask остаются внешними входами. В полном template их готовит `InpaintModelConditioning` из изображения, mask и VAE; fragment не дублирует эту часть.

Структура сверена с root UUID `aff23af9-e8f4-41f8-8e4c-0854e355b753`. Веса не загружались, fragment не импортировался и не исполнялся.
