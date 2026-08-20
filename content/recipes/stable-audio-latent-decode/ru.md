# Stable Audio latent, sampling и VAE decode

Fragment воспроизводит функциональную цепочку из official `audio_stable_audio_example`, workflow ID `5fa61cc8-29d9-4deb-9f90-02d3c00b63b3`: `EmptyLatentAudio` № 11 → `KSampler` № 3 → `VAEDecodeAudio` № 12.

Перенесены widgets: 47,6 секунды, batch 1; seed 840755638734093, 50 steps, CFG 4,98, `dpmpp_3m_sde_gpu`, `exponential`, denoise 1. MODEL, positive, negative и VAE оставлены внешними, поэтому fragment не закрепляет checkpoint-файл.

Topology и настройки сверены с wheel 0.1.42. Unit-level tensor helpers проверены отдельно, но diffusion model и VAE с реальными weights не запускались; рецепт остаётся `in_review`.
