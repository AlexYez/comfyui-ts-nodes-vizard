# LTXVImgToVideoInplace: записать изображение в готовый LTXV latent

## Что делает нода

`LTXVImgToVideoInplace` берёт готовый video LATENT, клонирует его `samples` и заменяет начальные temporal positions результатом VAE encode входного изображения. Остальная последовательность сохраняется.

Целевой размер IMAGE вычисляется из spatial shape latent и `vae.downscale_index_formula`. Если изображение отличается, оно масштабируется bilinear-методом с center crop. Перед encode используются только RGB-каналы.

`strength` не смешивает samples. Он задаёт `noise_mask` первых encoded positions как `1 - strength`; сами latent-значения VAE записываются полностью.

## Когда использовать и когда не использовать

Используйте ноду в LTX 2.x image-to-video subgraph после `EmptyLTXVLatentVideo` или после `LTXVLatentUpsampler`. Так одна и та же операция подходит к первой и второй стадии разных пространственных размеров.

`bypass` удобен, когда один subgraph переключает text-to-video и image-to-video. При `true` нода возвращает исходный словарь без clone, encode и resize.

Не подключайте joint AV `NestedTensor`: метод вызывает `.clone()` у `samples` и распаковывает пятиосевую форму. В 0.32.0 `NestedTensor` не реализует `clone`; официальные графы применяют Inplace до `LTXVConcatAVLatent`.

## Короткий рецепт подключения

1. Создайте `EmptyLTXVLatentVideo` с нужной длиной и разрешением.
2. Подключите IMAGE и совместимый VAE к Inplace.
3. Начните с `strength = 1`, `bypass = false` для закреплённого первого кадра.
4. Передайте выход в `LTXVAddGuide`, `LTXVConcatAVLatent` или sampler-ветвь.
5. Для второй стадии подайте вместо empty latent результат `LTXVLatentUpsampler`.

Рецепт Wizard повторяет официальный первый этап `Empty 768/512/97/1 → Inplace strength 0.7`. Он не включает preprocessing, sampler и model weights.

## Входы, выходы и параметры

`vae`, `image` и `latent` обязательны. VAE должен иметь трёхэлементный `downscale_index_formula`; код использует второй элемент как height scale, третий — как width scale.

`strength` принимает `0…1`, default `1`. На encoded positions mask равна `1 - strength`; остальные positions сохраняют прежнюю маску либо получают единицы.

`bypass` — BOOLEAN, default `false`. В bypass-ветви возвращается ровно входной `latent`, включая все metadata и исходные object identities.

В активной ветви output содержит только `samples` и `noise_mask`. Другие поля входного словаря, например `batch_index`, `type` или `downscale_ratio_spacial`, не копируются.

## Типовые связки

Из 27 официальных экземпляров 15 получают latent от `EmptyLTXVLatentVideo`, 12 — от `LTXVLatentUpsampler`. Это ровно две заявленные рабочие роли.

IMAGE 17 раз приходит от `LTXVPreprocess`; ещё десять связей входят через subgraph ports. VAE поставляют `CheckpointLoaderSimple`, `VAELoader` или reroute внутри subgraph.

Выход 21 раз идёт в `LTXVConcatAVLatent` для совместного audio-video sampling и шесть раз — в `LTXVAddGuide`.

## Практический пример

Full census wheel 0.1.42 нашёл 27 нод в 13 файлах, все в subgraph. Двадцать пять имеют mode `Always`, две — mode `Bypass`. Widgets: `[1,false]` встречается 20 раз, `[0.7,false]` — шесть, `[1,true]` — один.

В `video_ltx2_3_i2v` Empty №295 передаёт latent в Inplace №296 с `strength = 0.7`. IMAGE приходит от `LTXVPreprocess` №289, VAE — от checkpoint-ветви. Выход идёт дальше в AV/sampling pipeline.

В той же subgraph Inplace №288 получает latent от `LTXVLatentUpsampler` №287 и использует `strength = 1`. Это подтверждает повторное image conditioning после learned upscale.

## Частые ошибки и проверка

**Strength уменьшен, но samples не стали смесью.** Код всегда полностью записывает VAE latent. Strength меняет лишь маску шума; embedded docs описывают blending неточно.

**Исчезло metadata.** Активная ветвь создаёт новый словарь только с `samples/noise_mask`. Если downstream нужен другой ключ, восстановите его отдельной совместимой нодой.

**Ошибка `.clone()` или распаковки shape.** На вход попал nested AV latent либо не пятиосевой tensor. Применяйте Inplace к отдельному видеопотоку до Concat.

**Bypass не создаёт копию.** Это намеренно: возвращается тот же dict. Не меняйте его downstream на месте, если исходная ветвь должна остаться независимой.

## Производительность и внутреннее поведение

Активная ветвь клонирует весь samples tensor, затем запускает resize и VAE encode. Пиковая память включает исходный latent, его clone, IMAGE после resize и VAE intermediates.

Если вход уже совпадает с target pixels, resize пропускается. Target вычисляется из latent width/height, а не из отдельного виджета — у ноды нет собственных width и height.

`get_noise_mask` клонирует существующую маску. Если её нет, создаёт float32 ones формы `(B,1,T,1,1)`. Затем начальный диапазон перезаписывается `1 - strength`.

## Совместимость, изменения и устаревание

Статья сверена с ComfyUI `0.32.0`, frontend `1.48.7`, runtime ID `LTXVImgToVideoInplace` и модулем `comfy_extras.nodes_lt`. Fingerprint: `sha256:a72c287a49555d2909eb69807fe80fedfb6d0fde6fa5f9584ea98b9d25c7d2b0`.

Нода активна, не deprecated и не experimental; formal replacement отсутствует. Она зависит от пятиосевого LTXV latent и VAE scale formula, хотя socket остаётся общим `LATENT`.

Embedded docs 0.5.9 верно описывают resize и bypass, но неверно называют strength коэффициентом смешивания. Они также не предупреждают об удалении metadata и несовместимости с NestedTensor.

## Связанные ноды и источники

`EmptyLTXVLatentVideo` даёт исходную форму, `LTXVLatentUpsampler` — latent второй стадии, `LTXVPreprocess` готовит IMAGE. Затем `LTXVConcatAVLatent` добавляет аудио или `LTXVAddGuide` вводит дополнительные референсы.

- [Реализация `LTXVImgToVideoInplace`](https://github.com/Comfy-Org/ComfyUI/blob/c2bcbecd82ec5ae66594340b395c24ef0217b238/comfy_extras/nodes_lt.py#L132-L178)
- [Noise-mask helper](https://github.com/Comfy-Org/ComfyUI/blob/c2bcbecd82ec5ae66594340b395c24ef0217b238/comfy_extras/nodes_lt.py#L218-L230)
- [Официальный LTX 2.3 image-to-video template](https://github.com/Comfy-Org/workflow_templates/blob/cca1ea5ea4560108ecc2f44dee951f41ea433062/templates/video_ltx2_3_i2v.json)
- [Embedded docs 0.5.9](https://github.com/Comfy-Org/embedded-docs/blob/1d258cf6e374d60d138a2bfcd273c7e11f750ef9/comfyui_embedded_docs/docs/LTXVImgToVideoInplace/en.md)
