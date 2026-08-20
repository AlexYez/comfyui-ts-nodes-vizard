# Flux.2 Klein: расписание по размеру изображения

Fragment воспроизводит начало корневого официального `image_flux2_klein_9b_kv_image_edit.json`: `GetImageSize` передаёт width и height в `Flux2Scheduler`, а scheduler настроен на четыре шага. Значения 1024 × 1024 остаются fallback; подключённые dimensions имеют приоритет.

Выход `SIGMAS` подключите к `SamplerCustomAdvanced` той же distilled Flux.2 Klein ветки. Latent должен соответствовать измеренному размеру изображения.

Fragment не содержит model, guider, noise, sampler или latent и не запускает image edit. Для base-варианта нельзя механически оставлять четыре шага: официальные base cases используют двадцать.
