# LTXV: расписание для latent 768 × 512 × 97

Fragment повторяет две соседние ноды официального `ltxv_text_to_video.json`: `EmptyLTXVLatentVideo(768, 512, 97, 1)` подключён к `LTXVScheduler(30, 2.05, 0.95, true, 0.1)`.

Пустой latent имеет samples формы `[1, 128, 13, 16, 24]`, поэтому scheduler использует 4992 токена, а не fallback 4096. Его `SIGMAS` в полном графе идут в `SamplerCustom`; тот же latent подключается к sampler.

Модель, conditioning и sampler в fragment не входят. Полное video sampling не выполнялось, workflow-поле отсутствует. Для LTX 2 используйте соответствующий официальный subgraph: там встречаются 20 шагов, а distilled LoRA case — 12.
