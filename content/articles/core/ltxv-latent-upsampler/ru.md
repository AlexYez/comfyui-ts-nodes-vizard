# LTXVLatentUpsampler: обученное увеличение LTX-видео в latent-пространстве

## Что делает нода

`LTXVLatentUpsampler` увеличивает пространственные размеры видеолатента LTX в два раза обученной моделью. Если вход имеет форму `[B, C, T, H, W]`, типичный LTX spatial upscaler возвращает `[B, C, T, 2H, 2W]`: пакет, число каналов и временная длина остаются прежними.

Это не обычная интерполяция. Нода переводит tensor в dtype и на устройство upscale-модели, снимает нормализацию через `vae.first_stage_model.per_channel_statistics`, запускает обученный `LatentUpsampler`, снова нормализует результат тем же VAE и возвращает его в исходном dtype на intermediate device ComfyUI.

Исходный словарь `LATENT` копируется поверхностно. Поле `samples` заменяется, остальные ключи сохраняются ссылками, но `noise_mask` удаляется: её пространственная форма после увеличения уже не соответствует результату. Входной словарь при этом не меняется.

## Когда использовать и когда не использовать

Используйте ноду в двухстадийном LTX workflow, когда первый проход создаёт видео на меньшем пространственном разрешении, а следующий проход должен доработать увеличенный latent. В официальных шаблонах 0.1.42 это происходит после `LTXVCropGuides` или после отделения видеочасти через `LTXVSeparateAVLatent`.

Три компонента должны относиться к одной совместимой поставке: видеолатент LTX, spatial upscaler и VAE с нужной статистикой каналов. Имена официальных файлов отражают поколение модели: LTX 2 использует `ltx-2-spatial-upscaler-x2-1.0.safetensors`, LTX 2.3 — `ltx-2.3-spatial-upscaler-x2-1.1.safetensors`, LTX 2.5 — `ltx-2.5-latent-spatial-upscaler-x2-bf16-1.0.safetensors`.

Не подавайте сюда latent другой архитектуры только потому, что порт называется `LATENT`. Нода не проверяет семантику каналов и поколения модели до вычисления. Для простого изменения размера Stable Diffusion latent без обученного LTX upscaler подходят `LatentUpscale` или `LatentUpscaleBy`; они решают другую задачу и не требуют VAE.

## Короткий рецепт подключения

1. Получите видеолатент первого прохода. Для joint audio-video latent сначала отделите видео через `LTXVSeparateAVLatent`.
2. Загрузите подходящий файл в `LatentUpscaleModelLoader`.
3. Подайте тот же LTX VAE, который относится к latent и модели следующего прохода.
4. Соедините три входа с `LTXVLatentUpsampler`.
5. Передайте увеличенный latent в `LTXVImgToVideoInplace` либо снова объедините с аудио через `LTXVConcatAVLatent` — ровно так расходятся официальные ветви.

Fragment «LTX 2.5 latent upscale ×2» воспроизводит проверяемую центральную пару loader → upsampler и оставляет `samples` и `vae` внешними входами. Полный workflow не приложен: checkpoint, VAE, audio/video conditioning и второй sampler должны быть согласованы как единый LTX-набор.

## Входы, выходы и параметры

`samples` — обязательный `LATENT`. Рабочий tensor читается из `samples["samples"]`. Для видео ожидается пятиосевая форма `[batch, channels, time, height, width]`; конкретное число каналов определяется upscaler-файлом.

`upscale_model` — обязательный `LATENT_UPSCALE_MODEL` из `LatentUpscaleModelLoader`. У ноды нет выбора метода или коэффициента: поведение определяет загруженная модель. Встроенный docstring фиксирует увеличение ×2, и все три найденных официальных файла — spatial upscaler ×2.

`vae` — обязательный `VAE`. Нужен не для декодирования в пиксели, а для парных операций `un_normalize` и `normalize` по каналам. Обычный VAE без `per_channel_statistics` или VAE другой семьи не удовлетворяет этому контракту.

Выход — `LATENT` с новым `samples`. Исходный dtype восстанавливается. `noise_mask` отсутствует, а такие ключи, как `batch_index`, сохраняются поверхностной копией без пересчёта.

## Типовые связки

Полный рекурсивный просмотр 512 JSON официального wheel нашёл 16 экземпляров ноды в 14 шаблонах, все внутри subgraph. В восьми случаях входной latent приходит от `LTXVCropGuides`, ещё в восьми — от `LTXVSeparateAVLatent`. Во всех случаях upscale-модель приходит от `LatentUpscaleModelLoader`.

После ноды двенадцать ветвей идут в `LTXVImgToVideoInplace`: увеличенный latent становится latent-входом следующей стадии image-to-video. Четыре ветви идут в `LTXVConcatAVLatent`, где увеличенное видео вновь соединяется с аудиолатентом.

VAE приходит напрямую от `VAELoader` или `CheckpointLoaderSimple`, либо через `Reroute`. Reroute не меняет объект: это тот же источник нормализации. Подмена на удобный VAE из другого графа может дать ошибку атрибута, несовместимые каналы или содержательно неверное масштабирование.

## Практический пример

Exact-source probe без весов подал tensor формы `[2, 3, 4, 5, 6]` в точный метод ноды, заменив тяжёлую модель прозрачной операцией пространственного повторения. Результат имел форму `[2, 3, 4, 10, 12]`: изменились только две последние оси.

Probe подтвердил порядок преобразований. Исходный float32 был передан модели как float64, сначала вызвался `un_normalize` на форме `[2, 3, 4, 5, 6]`, затем `normalize` на `[2, 3, 4, 10, 12]`, а наружу вернулся float32. На отдельной малой конфигурации точный `LatentUpsampler` с `PixelShuffleND(2)` превратил `[1, 1, 2, 3, 4]` в `[1, 1, 2, 6, 8]`.

Метаданные сохранились теми же объектами, `noise_mask` исчезла только из результата, но осталась во входном словаре. Это model-free проверка кода и формы, а не доказательство качества изображения реальным LTX upscaler.

## Частые ошибки и способы проверки

**`LatentUpscaleModelLoader` не видит файл.** Проверьте каталог `models/latent_upscale_models` и точное имя файла. Combo-значения зависят от локальной установки и намеренно не входят в runtime fingerprint статьи.

**Ошибка про `per_channel_statistics`.** Подан VAE без нужного LTX-контракта. Возьмите VAE из того же официального LTX workflow, а не произвольный декодер с совместимым типом порта.

**Несовпадение каналов в convolution.** Upcaler и latent относятся к разным поколениям или архитектурам. Сверьте имя spatial upscaler, checkpoint/UNET, VAE и источник latent.

**После upscale сломалось inpainting-mask поведение.** Нода удаляет `noise_mask` намеренно и не увеличивает её. Постройте маску заново в пространстве второй стадии; не рассчитывайте на автоматическое наследование.

**Изменилась длительность видео.** Для официального spatial ×2 временная ось сохраняется. Если `T` изменился, проверьте фактическую конфигурацию загруженного файла: generic `LatentUpsampler` также умеет temporal upsample, но статья и найденные LTX recipes относятся к spatial-моделям.

## Производительность и внутреннее поведение

Нода обрабатывает весь latent одним вызовом и прямо помечена в source как вариант «without tiling». Пиковая память растёт вместе с `B × C × T × H × W`, а после пространственного ×2 число выходных элементов становится примерно в четыре раза больше. Длинное видео и большой batch особенно дороги.

Перед загрузкой модели ComfyUI получает оценку `math.prod(latents.shape) × 3000.0`. В source рядом стоит `TODO: more accurate`, поэтому это эвристика, не точный прогноз VRAM. В probe для 720 входных элементов оценка составила 2 160 000.

Model patcher загружается на `load_device`; latent переводится в dtype модели. После upscaler результат возвращается в dtype входа и на `intermediate_device`. Эти копирования тоже занимают память. Отсутствие tiling означает, что при нехватке VRAM нужно уменьшать исходное разрешение, длину или batch, а не искать скрытый tile-параметр.

## Совместимость, изменения и устаревание

Статья проверена для ComfyUI `0.32.0`, frontend `1.48.7` и модуля `comfy_extras.nodes_lt_upsampler`. Runtime fingerprint: `sha256:bffddacf566625e966b72241079a3eebde82dcb1e5be707f736a4c713bd74b48`.

Нода помечена `experimental = true`. Она не deprecated, не dev-only и не API node; записей в Node Replacement API и search aliases нет. Alias метода `upscale_latent = execute` отмечен в source как `TODO: remove`, но это Python-совместимость, а не другой NodeId.

Embedded docs 0.5.9 правильно описывают ×2, нормализацию и удаление `noise_mask`. После обновления ComfyUI нужно заново проверять как schema fingerprint, так и реальные LTX filenames/config: generic model loader читает конфигурацию из metadata safetensors, поэтому возможности файла шире статической схемы ноды.

## Связанные ноды и источники

`VAELoader` поставляет VAE для channel statistics. `LatentUpscale` и `LatentUpscaleBy` меняют размер latent интерполяцией и полезны как контраст, но не заменяют обученный LTX upscaler. В найденных официальных графах соседями служат `LTXVSeparateAVLatent`, `LTXVCropGuides`, `LTXVImgToVideoInplace` и `LTXVConcatAVLatent`; отдельные статьи для них ещё готовятся, поэтому manifest не создаёт битых связей.

- [Реализация `LTXVLatentUpsampler`](https://github.com/Comfy-Org/ComfyUI/blob/c2bcbecd82ec5ae66594340b395c24ef0217b238/comfy_extras/nodes_lt_upsampler.py#L7-L65)
- [Реализация обученного `LatentUpsampler`](https://github.com/Comfy-Org/ComfyUI/blob/c2bcbecd82ec5ae66594340b395c24ef0217b238/comfy/ldm/lightricks/latent_upsampler.py#L147-L297)
- [Встроенная документация 0.5.9](https://github.com/Comfy-Org/embedded-docs/blob/1d258cf6e374d60d138a2bfcd273c7e11f750ef9/comfyui_embedded_docs/docs/LTXVLatentUpsampler/en.md)
- [Официальные workflow templates 0.1.42](https://pypi.org/project/comfyui-workflow-templates-json/0.1.42/)
