# LTX 2.5 latent upscale ×2

Fragment повторяет центральную пару из двух официальных LTX 2.5 subgraph: `LatentUpscaleModelLoader → LTXVLatentUpsampler`. Имя `ltx-2.5-latent-spatial-upscaler-x2-bf16-1.0.safetensors` взято из workflow wheel 0.1.42.

Подайте во внешние входы видеолатент и `ltx-2.5-video-vae-bf16.safetensors` либо VAE из точно той же поставки. Выход увеличен по высоте и ширине вдвое, но не является готовым видео: его нужно подключить к совместимой второй LTX-стадии.

Полного workflow нет. Upcaler-файл, UNET/checkpoint, VAE, conditioning и audio-video topology должны совпадать. Веса не исполнялись; проверены схема, порты, официальное имя файла, порядок операций и model-free tensor path.
