# VOID sampler → SamplerCustomAdvanced

Fragment воспроизводит прямую связь, которая дважды встречается в официальном subgraph `Video Inpaint (VOID)`: `VOIDSampler → SamplerCustomAdvanced`. У ноды нет widgets, поэтому fragment не скрывает параметров.

Для pass 1 подайте `RandomNoise`; для pass 2 — `VOIDWarpedNoiseSource`. Остальные внешние входы должны прийти из совместимого VOID graph: `CFGGuider`, `BasicScheduler` и latent `VOIDInpaintConditioning`.

Полного workflow нет. VOID использует отдельные UNET pass 1/pass 2, CogVideoX VAE, текстовый encoder, optical flow и mask branch. Веса не запускались; проверены topology, порты и exact DDIM update на синтетических tensors.
