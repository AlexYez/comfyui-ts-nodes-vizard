# TripoSplatConditioning

## Назначение
Нода превращает подготовленное изображение в условия TripoSplat и создаёт фиксированную шумовую цель для KSampler.
## Место в графе
Подайте DINOv3 ViT-H/16+, Flux2 VAE и изображение после `TripoSplatPreprocessImage`. В официальном графе выходы `positive`, `negative` и `latent` идут прямо во входы 1, 2 и 3 `KSampler`; семплированный latent затем декодирует `VAEDecodeTripoSplat`.
## Входы
`clip_vision` должен отдавать DINOv3 sequence, `vae` — 128-канальный Flux2 latent, `image` — RGB batch.
## Positive
Изображение переводится из BHWC в BCHW и переносится на устройство vision-модели. Каждый канал нормализуется точными ImageNet mean/std; первый элемент ответа DINOv3 приводится к `float32` и проходит `layer_norm` без обучаемых весов. Полученная последовательность переносится на промежуточное устройство и становится основой positive.
## Negative
Negative содержит нули формы vision features и нулевой reference latent той же формы, а не повтор positive с пустым текстом.
## Reference latent
`vae.encode(image)` переносится на промежуточное устройство и записывается единственным элементом списка `reference_latents` в positive. Negative получает не этот объект, а отдельный `zeros_like(ref)`. Комментарий исходника ожидает 128 каналов Flux2 VAE, но нода не проверяет это число отдельно.
## Noise target
Создаются нули `[B,8192,16]` и camera `[B,1,5]`, объединённые `NestedTensor`; словарь содержит их под `samples`.
## Крайние случаи
Каналы изображения не обрезаются в этой ноде: ожидается корректный RGB preprocessing. Несовместимый vision encoder или VAE упадёт на форме или интерфейсе.
## Ограничения и ресурсы
DINOv3 явно загружается на устройство `clip_vision.load_device`, а features, reference latent и шумовая цель оказываются на `intermediate_device`. Размер target фиксирован и не управляется пользователем. Полный запус требует DINOv3, Flux2 VAE и TripoSplat; в Wizard проверены исходный код, схема и официальный граф, но не генерация с реальными весами.
## Совместимость и источники
Проверено по ComfyUI 0.32.0. Точные mean/std и формы закреплены; реальные DINOv3/Flux2 weights не запускались.
