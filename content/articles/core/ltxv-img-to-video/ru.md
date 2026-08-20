# LTXVImgToVideo: подготовить legacy image-to-video latent

## Что делает нода

`LTXVImgToVideo` создаёт LTXV video latent из изображения и пустой временной последовательности. Она масштабирует IMAGE до заданных width/height, оставляет первые три канала, кодирует их через VAE и записывает полученные latent-кадры в начало нулевого тензора.

Полная форма такая же, как у `EmptyLTXVLatentVideo`: `(batch_size, 128, ((length - 1) // 8) + 1, height // 32, width // 32)`. Число закодированных temporal positions определяет фактический результат VAE.

Нода также создаёт `noise_mask`. Везде стоят единицы, а на закодированных начальных кадрах — `1 - strength`. Positive и negative возвращаются без изменений.

## Когда использовать и когда не использовать

Используйте ноду для legacy LTXV image-to-video графа, где одна нода одновременно создаёт video latent и задаёт его начальные кадры. Официальный wheel содержит ровно один такой root template.

Для LTX 2.x subgraph чаще применяется пара `EmptyLTXVLatentVideo → LTXVImgToVideoInplace`. Она отделяет создание формы от записи изображения и умеет работать с latent после upscale.

Не ожидайте расширения изображения в готовую последовательность кадров. Кодируется входной IMAGE batch; остальная временная часть остаётся нулевой и генерируется sampler-ом по маске.

## Короткий рецепт подключения

1. Получите positive и negative conditioning, совместимый VAE и входное IMAGE.
2. Для официального legacy preset задайте `768 × 512`, `length = 97`, `batch_size = 1`, `strength = 0.15`.
3. Передайте positive/negative outputs в `LTXVConditioning` с `frame_rate = 25`.
4. Подключите LATENT одновременно к `LTXVScheduler` и sampler-у.
5. После sampling декодируйте видеолатент совместимым VAE.

Wizard хранит только участок `LTXVImgToVideo → LTXVConditioning`. Он повторяет точные виджеты официального root, но не включает checkpoint, prompts, scheduler или sampler.

## Входы, выходы и параметры

`positive`, `negative`, `vae` и `image` обязательны. IMAGE ожидается в ComfyUI-формате `B,H,W,C`; альфа и другие каналы отбрасываются срезом `:3` перед VAE encode.

`width` и `height` имеют defaults `768/512`, минимум `64`, шаг `32`. `length` начинается с `9`, default `97`, шаг `8`. `batch_size` — `1…4096`.

`strength` — `FLOAT 0…1`, default `1`. Значение влияет на маску: `1` даёт ноль на reference-кадрах, `0` — единицу. Samples при любом strength одинаково заменяются VAE-латентом; арифметического blend с нулями нет.

Выходы `positive` и `negative` — исходные объекты conditioning. Выход `latent` содержит `samples` и `noise_mask`; поле spatial ratio не добавляется.

## Типовые связки

В официальном root два `CLIPTextEncode` питают positive/negative, `CheckpointLoaderSimple` — VAE, `LoadImage` — IMAGE. Это единственный прямой кейс NodeId в wheel 0.1.42.

Оба conditioning outputs подключены к `LTXVConditioning`. LATENT идёт одновременно в `LTXVScheduler` и `SamplerCustom`, чтобы scheduler увидел ту же форму, которая будет сэмплироваться.

Современная раздельная связка использует `EmptyLTXVLatentVideo` и `LTXVImgToVideoInplace`; формального Node Replacement между ними нет, поэтому миграцию надо делать вручную.

## Практический пример

`ltxv_image_to_video.json` содержит `LTXVImgToVideo` №77 с `[768,512,97,1,0.15]`, mode `Always`. Positive prompt описывает рыжую лису в зимнем пейзаже; negative prompt перечисляет артефакты. Статья не копирует тексты в recipe, потому что они не определяют контракт ноды.

IMAGE приходит от `LoadImage` №78, VAE — от `CheckpointLoaderSimple` №44. Outputs positive/negative идут в `LTXVConditioning` №69 со значением `25`. LATENT подключён к `LTXVScheduler` №71 и `SamplerCustom` №72.

При этих размерах пустая основа имеет форму `[1,128,13,16,24]`. Точная временная длина VAE encode зависит от числа изображений во входном batch.

## Частые ошибки и проверка

**Strength ведёт себя «наоборот».** Маска равна `1 - strength`: при `1` reference-позиции не зашумляются, при `0` доступны sampler-у полностью. Это не коэффициент смешивания samples.

**Conditioning якобы изменился внутри ноды.** Код возвращает positive/negative как есть. Frame rate добавляет отдельная `LTXVConditioning`.

**Ошибка присваивания VAE latent.** Проверьте совместимость каналов, spatial scale, temporal length и batch. Нода не адаптирует произвольную форму результата encode к фиксированным 128 каналам.

**Альфа пропала.** Перед encode берутся только первые три канала. Для прозрачности подготовьте композицию в IMAGE-ветви заранее.

## Производительность и внутреннее поведение

Resize выполняется через `common_upscale` с bilinear interpolation и center crop. Затем VAE encode расходует память модели, а полный нулевой тензор выделяется на `intermediate_device()`.

Присваивание `latent[:, :, :t.shape[2]] = t` может использовать broadcasting по batch, если это допускают формы PyTorch. Оно не делает явный repeat и не исправляет несовместимые dimensions.

Noise mask имеет форму `(batch_size,1,latent_T,1,1)`. Пространственное расширение оставлено sampler-у. Маска `float32`, независимо от dtype VAE latent.

## Совместимость, изменения и устаревание

Статья сверена с ComfyUI `0.32.0`, frontend `1.48.7`, runtime ID `LTXVImgToVideo` и модулем `comfy_extras.nodes_lt`. Fingerprint: `sha256:36fc9a19393c59083aded1df27bd9947e67d50e01e27dc8a46182111e0c32cdb`.

Нода активна, не deprecated и не experimental. Formal replacement отсутствует. Термин legacy здесь редакционный: официальный прямой пример старше новых subgraph и использует `SamplerCustom`, но runtime lifecycle не помечает ноду устаревшей.

Embedded docs 0.5.9 ошибочно говорят, что нода применяет frame masking к conditioning и «расширяет» изображение в последовательность. Исходник показывает passthrough conditioning и запись VAE latent в начало нулевой формы.

## Связанные ноды и источники

`LTXVImgToVideoInplace` выполняет близкую операцию над готовым latent. `EmptyLTXVLatentVideo` создаёт его форму, `LTXVConditioning` добавляет FPS, `LTXVScheduler` строит расписание.

- [Реализация `LTXVImgToVideo`](https://github.com/Comfy-Org/ComfyUI/blob/c2bcbecd82ec5ae66594340b395c24ef0217b238/comfy_extras/nodes_lt.py#L87-L129)
- [Официальный legacy image-to-video template](https://github.com/Comfy-Org/workflow_templates/blob/cca1ea5ea4560108ecc2f44dee951f41ea433062/templates/ltxv_image_to_video.json)
- [Embedded docs 0.5.9](https://github.com/Comfy-Org/embedded-docs/blob/1d258cf6e374d60d138a2bfcd273c7e11f750ef9/comfyui_embedded_docs/docs/LTXVImgToVideo/en.md)
