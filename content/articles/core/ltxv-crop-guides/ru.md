# LTXVCropGuides: убрать служебные guide-кадры после sampling

## Что делает нода

`LTXVCropGuides` находит количество keyframe guides, добавленных `LTXVAddGuide`, и удаляет столько temporal positions с конца LATENT. Та же операция применяется к `noise_mask`.

После crop нода устанавливает `keyframe_idxs` и `guide_attention_entries` в `None` у positive и negative conditioning. Так downstream decode, upscale или следующий sampling pass получают обычную video-последовательность без служебного guide-хвоста.

Нода не ищет guides по значениям samples. Источником количества служит metadata positive conditioning.

## Когда использовать и когда не использовать

Используйте ноду после sampling, если до sampler применялась `LTXVAddGuide`. В audio-video pipeline сначала отделите video через `LTXVSeparateAVLatent`, затем удалите guide positions.

Не ставьте Crop до sampler: модель лишится добавленных reference latents и их metadata. Не применяйте её к произвольному latent только ради уменьшения длины — для этого нужен инструмент с явным числом кадров.

Если `keyframe_idxs` отсутствует, crop не выполняется. Нода всё равно создаёт output LATENT только с `samples/noise_mask`, поэтому другие metadata исходного dict не сохраняются.

## Короткий рецепт подключения

1. Соберите conditioning и LATENT через одну или несколько `LTXVAddGuide`.
2. Выполните sampling.
3. Для joint AV результата сначала примените `LTXVSeparateAVLatent`.
4. Подключите positive, negative и video LATENT к `LTXVCropGuides`.
5. Передайте очищенный LATENT в VAE decode или следующую spatial stage.

Wizard-рецепт содержит только `LTXVCropGuides` с тремя внешними входами. Такой fragment не создаёт ложную прямую связь с guides: positive, negative и LATENT нужно подать после реального sampler, а для joint AV результата — после `LTXVSeparateAVLatent`.

## Входы, выходы и параметры

`positive` и `negative` имеют тип `CONDITIONING`; `latent` — `LATENT`. Widgets и optional inputs отсутствуют.

Нода читает `keyframe_idxs` только из positive. Если latent имеет пятиосевую форму, количество вычисляется как длина token axis metadata, делённая на `latent_height * latent_width`. При недоступной форме используются `guide_attention_entries`, затем fallback по уникальным temporal starts.

Выходы — очищенные positive, negative и LATENT. Noise mask либо клонируется из input, либо создаётся как ones формы `(B,1,T,1,1)`.

## Типовые связки

В workflow wheel 0.1.42 найдено 18 экземпляров в 16 файлах: 17 mode `Always`, один mode `Bypass`. Нода не имеет widgets, поэтому все различия задаются связями.

В LTX 2.3 AV templates LATENT обычно приходит от `LTXVSeparateAVLatent`. Conditioning поступает из последней `LTXVAddGuide` либо из `LTXVConditioning`, если guides в конкретной ветви отключены.

Очищенный LATENT идёт в `VAEDecodeTiled` или `LTXVLatentUpsampler`; conditioning — в guider нужной стадии. Такое разветвление объясняет, почему нода возвращает все три объекта.

## Практический пример

В `video_ltx2_3_flf2v` две `LTXVAddGuide` добавляют начальный и конечный референс. После joint AV sampling `LTXVSeparateAVLatent` №121 передаёт video LATENT в `LTXVCropGuides` №106. Очищенный latent идёт в `VAEDecodeTiled` №105, а conditioning — в guider.

В control templates `video_ltx2_canny_to_video` и `video_ltx2_depth_to_video` output Crop направляется в `LTXVLatentUpsampler` для второй стадии. Это подтверждает, что служебные guides удаляются до изменения spatial resolution.

Полный census включает root и definitions.subgraphs всех 512 JSON из pinned wheel.

## Частые ошибки и проверка

**Обрезались реальные кадры.** Positive conditioning содержит keyframe metadata, не соответствующие входному LATENT. Сохраняйте пару conditioning/latent из одной sampling-ветви и не смешивайте результаты разных guides.

**Ничего не обрезалось.** В positive нет `keyframe_idxs` либо metadata были потеряны промежуточной нодой. Проверьте output последней `LTXVAddGuide` перед guider.

**Получился tensor нулевой длины.** Код не проверяет, что число guides меньше temporal length. Это признак несовместимой пары inputs.

**Пропало custom metadata LATENT.** Output намеренно содержит только `samples` и `noise_mask`. Сохраняйте нужные поля отдельно, если downstream расширение от них зависит.

## Производительность и внутреннее поведение

Сначала `samples` полностью клонируются. Существующая mask также клонируется; при её отсутствии создаётся новая. Crop `[:, :, :-num_keyframes]` возвращает slice этих новых tensors.

Conditioning обновляется через `conditioning_set_values`, поэтому tensor embeddings сохраняются, а metadata entries копируются и получают два ключа со значением `None`.

При нулевом числе guides positive и negative возвращаются без изменения object identity, но LATENT всё равно построен заново. Ветка не является полным identity bypass.

## Совместимость, изменения и устаревание

Статья проверена для ComfyUI `0.32.0`, frontend `1.48.7`, runtime ID `LTXVCropGuides` и модуля `comfy_extras.nodes_lt`. Fingerprint: `sha256:1b85c22c9ca23991f9fce46cff2ffee32e993ec36633c84dd2e95b62b2b46ee0`.

Нода активна, не experimental и не deprecated; formal replacement отсутствует. Её семантика привязана к metadata, которые формирует текущая `LTXVAddGuide`.

Embedded docs 0.5.9 правильно описывают tail crop и очистку двух guide-полей, но не предупреждают, что count берётся только из positive, custom latent metadata теряются, а oversized count не проверяется.

## Связанные ноды и источники

`LTXVAddGuide` добавляет служебные positions, `LTXVSeparateAVLatent` выделяет video stream, `LTXVCropGuides` очищает его. После этого `LTXVLatentUpsampler` или VAE decoder работают с пользовательской длиной ролика.

- [Реализация `LTXVCropGuides`](https://github.com/Comfy-Org/ComfyUI/blob/c2bcbecd82ec5ae66594340b395c24ef0217b238/comfy_extras/nodes_lt.py#L499-L540)
- [Подсчёт keyframes](https://github.com/Comfy-Org/ComfyUI/blob/c2bcbecd82ec5ae66594340b395c24ef0217b238/comfy_extras/nodes_lt.py#L232-L248)
- [Официальный LTX 2.3 FLF2V template](https://github.com/Comfy-Org/workflow_templates/blob/cca1ea5ea4560108ecc2f44dee951f41ea433062/templates/video_ltx2_3_flf2v.json)
- [Embedded docs 0.5.9](https://github.com/Comfy-Org/embedded-docs/blob/1d258cf6e374d60d138a2bfcd273c7e11f750ef9/comfyui_embedded_docs/docs/LTXVCropGuides/en.md)
