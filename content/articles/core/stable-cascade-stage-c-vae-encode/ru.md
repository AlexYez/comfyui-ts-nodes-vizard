# StableCascade_StageC_VAEEncode: исходное изображение в prior Stage C

## Что делает нода

`StableCascade_StageC_VAEEncode` готовит пару latent для Stable Cascade img2img. Входной `IMAGE` имеет порядок измерений `batch × height × width × channels`. Нода вычисляет целевой размер:

```text
out_width  = (width  // compression) × vae.downscale_ratio
out_height = (height // compression) × vae.downscale_ratio
```

Затем она переводит изображение в NCHW, вызывает `common_upscale` с режимами `bicubic` и `center`, возвращает NHWC и передаёт VAE только первые три канала. Результат `vae.encode` становится `stage_c`. Для `stage_b` отдельно создаётся нулевой тензор формы `batch × 4 × ((height // 8) × 2) × ((width // 8) × 2)`.

У Stable Cascade Stage C VAE в ComfyUI 0.32.0 `downscale_ratio` равен `32`. С совместимым encoder итоговая сетка Stage C поэтому обычно имеет высоту `height // compression` и ширину `width // compression`. Альфа-канал и любые каналы после RGB отбрасываются до VAE.

## Когда использовать и когда не использовать

Используйте ноду, когда генерация Stage C должна отталкиваться от изображения: img2img, remix или другой сценарий, где исходная структура нужна в prior. Denoise в sampler Stage C определяет, насколько сильно этот prior будет изменён.

Для text-to-image без картинки нужна `StableCascade_EmptyLatentImage`. Она создаёт нулевые Stage C и Stage B напрямую и не расходует время на resize и VAE encode.

Не заменяйте этой нодой обычный `VAEEncode` в SDXL либо SD3. Здесь есть Stable Cascade-специфичная пара выходов, отдельный `compression` и placeholder для Stage B. Также не подавайте VAE другого семейства только потому, что сокет имеет тот же тип: формула полагается на его `downscale_ratio`, число выходных каналов и совместимость с моделью Stage C.

## Короткий рецепт подключения

Приложенный fragment повторяет официальную image-to-image ветвь:

1. `LoadImage.IMAGE` и VAE из checkpoint Stage C подключены к этой ноде.
2. `compression` установлен в `32`.
3. `stage_c` идёт в первый `KSampler` с моделью Stage C; denoise равен `0.6`.
4. Результат первого sampler добавляется в positive через `StableCascade_StageB_Conditioning`.
5. `stage_b` служит начальным latent для sampler Stage B с denoise `1`.
6. Готовый Stage B latent декодируется VAE из checkpoint Stage B.

Positive и negative для обеих стадий в исходном PNG получены из одной Stable Cascade CLIP-ветви. Fragment оставляет их внешними входами, чтобы не выбирать checkpoint и prompt за пользователя.

## Входы, выходы и параметры

- `image` — обязательный `IMAGE` в NHWC. Batch сохраняется.
- `vae` — обязательный `VAE`. Для штатного Stable Cascade Stage C coder коэффициент уменьшения равен `32`.
- `compression` — обязательный advanced `INT`: default `42`, минимум `4`, максимум `128`, шаг `1`.
- `stage_c` — словарь `LATENT` с `samples`, полученным от VAE.
- `stage_b` — словарь `LATENT` с нулевым `samples` и четырьмя каналами.

Embedded docs 0.5.9 помечает `compression` как optional, но `/object_info` 0.32.0 относит его к `required`. Advanced-флаг лишь скрывает параметр среди дополнительных настроек интерфейса; он не делает аргумент необязательным для backend.

Форма Stage B написана в исходнике как `(height // 8) × 2` и `(width // 8) × 2`. Для размеров, кратных восьми, это равно делению на четыре. Для произвольного API-входа результат может отличаться: при height `101` получается `24`, тогда как `101 // 4` дало бы `25`.

## Типовые связки

В шести PNG официальной Stable Cascade подборки эта нода встречается один раз — в `stable_cascade__image_to_image.png`. Там VAE приходит из `CheckpointLoaderSimple` Stage C, `compression` равен `32`, а оба выхода расходятся к соответствующим sampler. Результат Stage C передаётся в `StableCascade_StageB_Conditioning`.

Остальные пять PNG начинают с `StableCascade_EmptyLatentImage`; это подтверждает различие между img2img и нулевым стартом. В workflow wheel 0.1.42 ни этой ноды, ни остальных точных Stable Cascade ID нет после просмотра всех root и вложенных subgraph.

Для практического графа вокруг ноды обычно находятся `LoadImage`, loader checkpoint Stage C, два `KSampler`, `StableCascade_StageB_Conditioning` и VAE decode Stage B. Это описание официального case, а не требование backend schema: сама нода знает только об `IMAGE`, `VAE` и `compression`.

## Практический пример

Для изображения `1024 × 1024` и Stable Cascade VAE с ratio `32`:

- при `compression = 32` целевой resize остаётся `1024 × 1024`, а Stage C grid получается `32 × 32`;
- при `compression = 42` целевой resize равен `768 × 768`, потому что `1024 // 42 = 24`, а `24 × 32 = 768`; Stage C grid равен `24 × 24`;
- Stage B в обоих случаях создаётся как `4 × 256 × 256` на элемент batch, поскольку его размер не зависит от compression.

Безопасная проба выполнила точный метод и точный `common_upscale` на `IMAGE` формы `2 × 101 × 155 × 4`, с `compression = 32` и модельной VAE-заглушкой ratio `32`. VAE получил RGB формы `2 × 96 × 128 × 3`; вход совпал с отдельным расчётом center crop + bicubic. Stage C имел тестовую форму `2 × 16 × 3 × 4`, Stage B — `2 × 4 × 24 × 38` и был полностью нулевым. Настоящие веса VAE в этой пробе не использовались.

## Частые ошибки и способы проверки

**Края исходного изображения пропали.** Режим `center` сначала обрезает вход до aspect ratio целевого размера, затем масштабирует. Сравните отношения сторон до и после целочисленного деления на compression.

**Альфа-канал не повлиял на результат.** Это ожидаемо: в `vae.encode` передаются только `s[:, :, :, :3]`. Сведите прозрачность к RGB заранее, если она должна менять изображение.

**Получена нулевая или недопустимая цель resize.** При прямом API-вызове image dimension может оказаться меньше compression, тогда `dimension // compression` равно нулю. Уменьшите compression либо подайте более крупное изображение.

**Stage C sampler сообщает о несовместимой форме.** Проверьте, что VAE и MODEL относятся к одной Stable Cascade Stage C сборке. Тип `VAE` не кодирует семейство модели на уровне сокета.

**Stage B начинается с неверного размера.** Посчитайте точную формулу `(dimension // 8) × 2`, а не приблизительное `dimension / 4`. Для UI-размеров, кратных восьми, расхождения нет.

**Img2img слишком похож на исходник или полностью его теряет.** Меняйте denoise в sampler Stage C, не `compression`. Compression управляет пространственным разрешением prior, а denoise — силой изменения закодированного состояния.

## Производительность и внутреннее поведение

Нода выполняет две заметные операции: resize всего batch и VAE encode. Их стоимость растёт с числом пикселей целевого `out_width × out_height` и batch. При большом compression целевой кадр меньше; при малом — крупнее и дороже.

Перед resize изображение переставляется из NHWC в NCHW, после него — обратно. `movedim` часто создаёт view, но `interpolate` формирует новый tensor. Затем VAE управляет загрузкой своих весов, устройством и dtype по общим правилам ComfyUI.

Stage B placeholder создаётся отдельным `torch.zeros` без явных device и dtype, то есть в проверенной среде на CPU и в `float32`. Stage C tensor возвращает VAE и может иметь другое устройство или тип до следующих узлов. Нода не приводит оба выхода к общему размещению.

## Совместимость, изменения и устаревание

Контракт проверен для ComfyUI 0.32.0 и frontend 1.48.7. Нода активна, не experimental, не deprecated, не `api_node` и не `dev_only`; Node Replacement API не объявляет для неё alias или замену.

Fingerprint охватывает три обязательных входа, два именованных выхода и флаги. Смысл статьи дополнительно зависит от `common_upscale`, поведения `VAE.encode` и значения `vae.downscale_ratio`. После обновления нужно сверять не только `/object_info`, но и эти исходники.

Официальный image-to-image пример закреплён на commit `f9431bb000ce792094ff345446e22cac1ea6cef3`. Он доказывает topology и widgets, но не гарантирует, что `compression = 32` подходит каждой Stable Cascade модели или каждому исходному размеру.

## Связанные ноды и источники

- `StableCascade_StageB_Conditioning` добавляет отредактированный Stage C prior в positive второй стадии.
- `StableCascade_EmptyLatentImage` создаёт нулевую пару для text-to-image.
- `LoadImage` поставляет исходный `IMAGE` в официальном img2img case.
- `KSampler` меняет закодированный prior; его denoise отвечает за силу img2img.
- Обычный `VAEEncode` похож по назначению, но не создаёт Stable Cascade Stage B placeholder.

Формулы и отсечение RGB сверены по `nodes_stable_cascade.py`; center crop — по `common_upscale`; ratio `32` — по определению Stable Cascade coder в `comfy/sd.py`. Workflow-часть взята из метаданных официального image-to-image PNG, а отсутствие wheel-cases подтверждено полным рекурсивным просмотром 0.1.42.
