# Causal Forcing: покадровый AR sampler

Fragment переносит связь `SamplerARVideo(num_frame_per_block = 1) → SamplerCustomAdvanced` из официального subgraph `Image to Video (Causal Forcing Framewise)`.

## Подключение

Внешние `GUIDER`, `SIGMAS` и LATENT должны опираться на одну и ту же Causal-WAN MODEL. В официальном case `ARVideoI2V` подаёт MODEL в `CFGGuider(cfg = 1)` и `BasicScheduler(simple, 4, 1)`, а его пятиосевой LATENT поступает в исполнитель; NOISE создаёт `RandomNoise`.

## Что сохраняет fragment

Сохранены widget `[1]` у `SamplerARVideo` и точная связь с портом `sampler`. Загрузчики UNET/VAE, start image, dimensions, `ARVideoI2V`, decode и video assembly оставлены внешними, чтобы fragment не притворялся автономным workflow.

## Что проверено

Кейс найден в `video_causal_forcing_i2v`, root UUID `b5d4e2f9-8c3a-4b0e-a4d2-f9e6b3c0a1d5`, subgraph UUID `96ba6b5d-dd48-49b3-84c3-5b86eafc2a07`. Node 12 подключён к `SamplerCustomAdvanced` node 15. Типы fragment сверены с runtime.

## Что не проверено

Fragment не импортировался и не запускался с Causal-WAN weights. Браузерный video pipeline и соответствие конкретного checkpoint framewise-режиму не проверялись; человеческое одобрение ожидается.
