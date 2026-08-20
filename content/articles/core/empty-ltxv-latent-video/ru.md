# EmptyLTXVLatentVideo: создать пустой видеолатент LTXV

## Что делает нода

`EmptyLTXVLatentVideo` создаёт заполненный нулями видеолатент для LTXV text-to-video и последующей image conditioning. Его форма вычисляется напрямую: `(batch_size, 128, ((length - 1) // 8) + 1, height // 32, width // 32)`.

Временная ось сжимается с шагом восемь, но первый кадр учитывается отдельно. Поэтому `length = 97` даёт `13` latent-кадров, а не `12`. Ширина и высота делятся целочисленно на `32`.

В словарь результата также записывается `downscale_ratio_spacial: 32`. Название поля в runtime содержит именно `spacial`; статья сохраняет точный ключ, а не исправляет его редакционно.

## Когда использовать и когда не использовать

Используйте ноду как начальный LATENT для LTXV text-to-video. В более новых LTX 2.x image-to-video subgraph тот же нулевой latent сначала получает стартовое изображение через `LTXVImgToVideoInplace`.

Нода подходит и как video stream перед `LTXVConcatAVLatent`, когда модель генерирует видео вместе с аудио. В этом случае аудиопоток создаётся отдельно, а Concat упаковывает оба тензора в joint AV latent.

Не применяйте эту форму к другой модели только из-за разъёма `LATENT`. Число каналов `128`, временное сжатие `8` и spatial ratio `32` зафиксированы в коде LTXV. Обычные Stable Diffusion latent имеют другую геометрию.

## Короткий рецепт подключения

1. Выберите итоговые `width`, `height` и число кадров `length`.
2. Для стандартного официального пресета начните с `768 × 512`, `97` кадров и `batch_size = 1`.
3. В text-to-video подайте LATENT в совместимый scheduler и sampler.
4. В image-to-video подключите его к `LTXVImgToVideoInplace.latent`, а изображение и VAE — к соседним входам.
5. Для AV-модели передайте подготовленный видеолатент в `LTXVConcatAVLatent.video_latent`.

Рецепт Wizard повторяет подтверждённую пару `EmptyLTXVLatentVideo → LTXVImgToVideoInplace` с пресетом `768/512/97/1`. Он оставляет IMAGE и VAE внешними и не содержит весов модели.

## Входы, выходы и параметры

`width` и `height` — целые числа от `64` до `MAX_RESOLUTION`, defaults `768` и `512`, шаг `32`. Кратность шагу соответствует формуле `// 32`; программный вызов с некратным значением всё равно использовал бы целочисленное деление.

`length` принимает значения от `1` до `MAX_RESOLUTION`, default `97`, шаг `8`. Допустимая последовательность виджета — `1, 9, 17, …`; она согласуется с временной формулой `8n + 1`.

`batch_size` — от `1` до `4096`, default `1`. Все четыре входа runtime считает required, хотя Python-метод имеет default для последнего параметра.

Единственный выход `LATENT` отображается как `LATENT`. Внутри есть `samples` и `downscale_ratio_spacial`; `noise_mask`, `batch_index` и conditioning metadata нода не создаёт.

## Типовые связки

В legacy text-to-video root выход одновременно подключён к `LTXVScheduler` и `SamplerCustom`. Scheduler рассчитывает сигмы по форме, sampler получает сами нули как исходный latent.

В LTX 2.x subgraph 15 связей ведут в `LTXVImgToVideoInplace`: image encoder заменяет первые latent-кадры и создаёт маску шума. Ещё три выхода идут в `LTXVAddGuide`, а три — прямо в `LTXVConcatAVLatent`.

Размеры часто приходят от `GetImageSize`, `ComfyMathExpression` и `PrimitiveInt`. Это помогает одной ветви вычислять согласованные width, height и length, но сама нода не проверяет, совпадают ли они с изображением или аудио.

## Практический пример

Полный recursive census wheel 0.1.42 нашёл 22 экземпляра в 20 файлах: один в root `ltxv_text_to_video`, 21 в subgraph. Двадцать одна нода сохранена с `[768,512,97,1]`; одна — с `[960,544,121,1]`.

В root text-to-video нода №70 создаёт `768 × 512`, 97 кадров, batch 1. Форма samples равна `[1,128,13,16,24]`. Её выход идёт и в `LTXVScheduler`, и в `SamplerCustom`.

В `video_ltx2_3_i2v` нода №295 с тем же пресетом подключена к `LTXVImgToVideoInplace` №296, где strength равен `0.7`. Этот официальный участок лежит внутри subgraph и использует внешние вычисления размеров.

## Частые ошибки и проверка

**Получилось меньше кадров в latent.** `length` описывает видео до VAE-сжатия. Значение `97` закономерно превращается в `13` временных позиций.

**Размер изображения не совпадает с latent.** Нода не меняет IMAGE. Используйте значения одной видеоветви или `LTXVImgToVideoInplace`, который масштабирует изображение по геометрии VAE и latent.

**Другой model выдаёт ошибку каналов.** Здесь всегда `128` latent-каналов. Проверьте архитектуру checkpoint; общий socket не конвертирует геометрию.

**Большой batch не помещается в память.** Разрешённый максимум `4096` — предел виджета, а не обещание работоспособности. Объём растёт по всем пяти измерениям.

## Производительность и внутреннее поведение

Нода выполняет одно выделение `torch.zeros` на `intermediate_device()`. Dtype явно не задан и в обычной конфигурации равен `float32`. Веса модели или VAE не загружаются.

Пространственные размеры округляются вниз через `// 32`. Временная формула эквивалентна потолку `length / 8` для положительных значений. При штатном шаге виджета округление не создаёт скрытого остатка.

Например, `[1,128,13,16,24]` содержит `638 976` элементов. Увеличение batch или разрешения быстро повышает стоимость последующего sampling, хотя создание нулей само по себе остаётся простой операцией.

## Совместимость, изменения и устаревание

Статья сверена с ComfyUI `0.32.0`, frontend `1.48.7`, runtime ID `EmptyLTXVLatentVideo` и модулем `comfy_extras.nodes_lt`. Fingerprint: `sha256:fdfe6248dd9d26006ba2e8d46f0ad53669db964e3962d55f8cc91a99d54427a2`.

Нода активна, не experimental, не deprecated, не dev-only и не API node. Formal replacement отсутствует. Сохранённый ключ `downscale_ratio_spacial` считается частью фактического поведения 0.32.0.

Embedded docs 0.5.9 верно называют нулевой latent и диапазоны, но не показывают точную форму, постоянные `128/8/32` и metadata. Русский файл также переводит системные имена параметров; в runtime они остаются `width`, `height`, `length`, `batch_size`.

## Связанные ноды и источники

`LTXVImgToVideoInplace` записывает стартовое изображение в готовую форму. `LTXVScheduler` строит расписание по latent, `LTXVConcatAVLatent` добавляет аудиопоток, а `LTXVAddGuide` вводит дополнительные референсные кадры.

- [Реализация `EmptyLTXVLatentVideo`](https://github.com/Comfy-Org/ComfyUI/blob/c2bcbecd82ec5ae66594340b395c24ef0217b238/comfy_extras/nodes_lt.py#L63-L85)
- [Официальный legacy text-to-video template](https://github.com/Comfy-Org/workflow_templates/blob/cca1ea5ea4560108ecc2f44dee951f41ea433062/templates/ltxv_text_to_video.json)
- [Embedded docs 0.5.9](https://github.com/Comfy-Org/embedded-docs/blob/1d258cf6e374d60d138a2bfcd273c7e11f750ef9/comfyui_embedded_docs/docs/EmptyLTXVLatentVideo/en.md)
