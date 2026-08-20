# Подать пустой SD3 latent в KSampler

Fragment переносит ветвь из `sd3.5_simple_example`: `EmptySD3LatentImage` с размером `1024 × 1024`, batch `1` подключён к `KSampler`. Значения steps, CFG, sampler, scheduler, denoise и seed взяты из того же файла.

`MODEL`, positive и negative оставлены внешними входами. Это защищает от скрытой подмены checkpoint и текста. В исходном шаблоне клиентский контрол seed стоит в режиме `randomize`; фрагмент хранит серверный seed, а политику изменения seed нужно выбрать после вставки.

Выход sampler остаётся `LATENT`. Для изображения подключите `VAEDecode` с VAE той же цепочки модели. Schema фрагмента и отдельная тензорная ветвь проверены, но полный SD3.5 workflow с весами не запускался.
