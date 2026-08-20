# Убрать служебный VACE-префикс перед VAEDecode

Подайте sampled LATENT из `KSampler` во вход `sampled_video_latent`. Выход `trim_latent` того же `WanVaceToVideo` соедините с `vace_trim_latent`, а VAE исходной цепочки — с `vae`.

## Почему trim_amount приходит по связи

`WanVaceToVideo` вычисляет длину latent-префикса для reference image. В шести официальных VACE-экземплярах локальное widget-значение TrimVideoLatent равно `0`, но INT-link с output slot 3 conditioning-ноды задаёт фактическое значение.

## Статус примера

VACE-топология подтверждена в `video_wan_vace_14B_ref2v`, `video_wan_vace_14B_t2v`, `video_wan_vace_14B_v2v`, `video_wan_vace_outpainting`, а также в subgraphs `video_wan_vace_flf2v` и `video_wan_vace_inpainting`. Полный census дополнительно нашёл два аналогичных Animate2 subgraph. Exact-source slice проверен на synthetic tensor; полный VACE fragment не запускался, поэтому `exampleExecuted` остаётся false. Полного workflow в recipe нет.
