# WanMoveTrackToVideo

## Назначение
Нода создаёт Wan Move video latent и внедряет trajectories в reference latent positive-ветви.
## Место в графе
Подайте positive/negative, VAE, start image и optional TRACKS/CLIP Vision; три выхода идут в Wan sampler.

`start_image` объявлен обязательным в runtime-схеме, хотя Python-метод допускает `None`. Без него нода всё равно создаёт пустой noise target и может добавить CLIP Vision, но не формирует concat latent, mask и track conditioning.
## Пустой latent
Всегда создаются нули `[batch,16,((length−1)//4)+1,height//8,width//8]`.
## Reference video
Start image масштабируется; затем video длины length заполняется серым 0,5, а первые доступные кадры заменяются start image.

Изображения ограничиваются первыми `length` кадрами и приводятся к заданному размеру bilinear-методом с центральной обрезкой. Batch изображений снова играет роль временной последовательности. VAE видит RGB canvas целиком, включая неизвестный серый хвост.
## VAE и mask
RGB video кодируется VAE. Concat mask начинается единицами и обнуляется до temporal latent length исходных start frames.
## Tracks
При наличии tracks и strength>0 создаются positional embeddings с compression `[4,8,8]`, затем приводятся к batch и внедряются `replace_feature`.

Path обрезается до `length`, но visibility берётся без явного среза. Если ключ отсутствует, создаётся матрица истинных значений `[length,num_tracks]`. `create_pos_embeddings` переводит координаты в feature-представление, после чего `resize_to_batch_size` повторяет его до требуемого batch.
## Positive и negative
Positive получает latent с track features, negative — исходный concat latent. Оба получают одинаковый concat mask.

При `strength<=0` или отсутствии tracks обе ветви получают один и тот же исходный VAE-latent. При положительной силе track feature внедряется только в positive, создавая часть guidance-разницы. Значения strength до 100 не ограничиваются нормализацией этой ноды.
## CLIP Vision
Optional `clip_vision_output` одинаково добавляется в positive и negative независимо от start image/tracks.
## Ограничения
Без start image tracks полностью игнорируются и conditioning concat не создаётся. Visibility default и shape matching зависят от track input.

Temporal path короче canvas не дополняется здесь; поведение определяется `create_pos_embeddings`. Координаты вне кадра, несовпадающая mask и неверное устройство tensor могут вызвать ошибку либо дать слабое conditioning. Перед sampling используйте `WanMoveVisualizeTracks` на тех же width и height.
## Совместимость и источники
Проверено по ComfyUI 0.32.0. Полный Wan Move sampling не исполнялся.
