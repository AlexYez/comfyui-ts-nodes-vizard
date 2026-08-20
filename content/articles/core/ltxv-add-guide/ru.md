# LTXVAddGuide: добавить референсный кадр или клип в LTXV latent

## Что делает нода

`LTXVAddGuide` кодирует IMAGE или короткий video batch через VAE и добавляет полученный guide latent в конец временной оси входного LATENT. Одновременно нода записывает в positive и negative conditioning координаты, по которым модель понимает, к какому месту основного ролика относится guide.

Выходной latent получает обновлённую `noise_mask`, а conditioning — `keyframe_idxs` и отдельную запись `guide_attention_entries`. Поэтому guide влияет не только через добавленные samples: модель также получает позицию, strength и optional spatial attention mask.

Guide-кадры служебные. После sampling их обычно удаляет `LTXVCropGuides`.

## Когда использовать и когда не использовать

Используйте ноду для первого или последнего референса, перехода между двумя изображениями, control-guide либо IC-LoRA guide в LTX 2.x. Несколько экземпляров можно соединять последовательно: каждый добавляет свой latent и metadata.

Для простого стартового кадра без keyframe metadata часто достаточно `LTXVImgToVideoInplace`. `LTXVAddGuide` нужна, когда положение референса задаётся `frame_idx`, guides несколько или downstream-модель читает guide attention entries.

Joint AV latent не поддерживается: код требует ровно 128 каналов и у основного, и у guide latent. Подключайте ноду к отдельному видеопотоку до `LTXVConcatAVLatent`.

## Короткий рецепт подключения

1. Создайте video LATENT и positive/negative conditioning для LTXV.
2. Подготовьте IMAGE через `LTXVPreprocess` и подключите совместимый VAE.
3. Для первого guide задайте `frame_idx = 0`; для последнего — `-1`.
4. Начните со `strength = 0.7` или `1.0`.
5. Если IC-LoRA хранит downscale metadata, подключите `GetICLoRAParameters`.
6. После sampling передайте разделённый video latent в `LTXVCropGuides`.

Рецепт Wizard повторяет официальный style-transition fragment с guides `0/0.7` и `-1/0.7`. Второй рецепт показывает exact IC-LoRA parameter link.

## Входы, выходы и параметры

Обязательные входы: `positive`, `negative`, `vae`, `latent`, `image`, `frame_idx` и `strength`. `frame_idx` принимает `-9999…9999`; отрицательные значения считаются от конца доступной video-последовательности. `strength` имеет диапазон `0…10` и default `1`.

Для causal guide код оставляет длину `8*n+1`: batch из 1–8 кадров сокращается до одного, 9–16 — до девяти. У multi-frame guide вне начала клипа сначала добавляется копия первого кадра, а уже дополненный batch режется до `8*n+1`; затем первый latent отбрасывается. Поэтому исходные 9 кадров превращаются для VAE в дубликат первого плюс первые восемь исходных, а исходный девятый кадр в этой ветви не сохраняется.

Optional `attention_mask` хранится как pixel mask в attention entry. Optional `iclora_parameters` задаёт пространственный downscale factor. Выходы — обновлённые positive, negative и LATENT.

## Типовые связки

Workflow wheel 0.1.42 содержит 12 экземпляров в семи файлах: 11 в mode `Always`, один в `Bypass`. Widgets распределены так: `[0,1]` — шесть нод, `[-1,0.7]` — три, `[0,0.7]` — три.

Шесть guide-нод получают latent от `LTXVImgToVideoInplace`, три — от `EmptyLTXVLatentVideo`, ещё три — от предыдущей `LTXVAddGuide`. Девять финальных guides передают LATENT в `LTXVConcatAVLatent`, три первых — следующей guide-ноде.

В двух IC-LoRA templates optional parameters приходят от `GetICLoRAParameters`. В style-transition и LTX 2.5 FLF2V изображения проходят через `LTXVPreprocess`.

## Практический пример

В `video_ltx2_3_flf2v` guide №115 получает empty latent и начальное изображение после `LTXVPreprocess` №104. Параметры: `frame_idx = 0`, `strength = 0.7`. Его три выхода переходят в guide №111 с конечным референсом, `frame_idx = -1`, `strength = 0.7`.

Второй guide передаёт conditioning в `CFGGuider`, а LATENT — в `LTXVConcatAVLatent` для добавления аудио. После sampling `LTXVSeparateAVLatent` отделяет видео, а `LTXVCropGuides` удаляет служебные позиции.

IC-LoRA case использует `frame_idx = 0`, `strength = 1` и коэффициент из metadata LoRA. Это другой официальный паттерн, а не обязательная часть обычного guide.

## Частые ошибки и проверка

**Guide оказался не на ожидаемом кадре.** Для multi-frame guide ненулевой индекс приводится к форме `8*k+1`, хотя tooltip говорит о кратности восьми. Например, `10` превращается в `9`. Это точное поведение 0.32.0.

**LATENT стал длиннее.** Нода добавляет guide samples в конец, а `frame_idx` хранится в координатах conditioning. Это не вставка tensor slice внутрь основной временной оси. Удалите служебный хвост через `LTXVCropGuides` после sampling.

**Ошибка про combined AV latent.** Один из tensors имеет не 128 каналов. Разделите audio/video либо перенесите AddGuide до Concat.

**Ошибка неделимого spatial size.** При IC-LoRA factor больше единицы latent width и height должны делиться на него без остатка.

**Strength выше 1 не меняет обычную noise mask ниже нуля.** Без IC-LoRA dilation значение ограничивается `max(0, 1-strength)`; усиление выше единицы хранится в attention entry.

## Производительность и внутреннее поведение

Нода масштабирует каждый guide под spatial grid latent и запускает VAE encode. Затем создаёт новые conditioning metadata, конкатенирует guide к samples и mask, а при наличии предыдущих guides объединяет keyframe coordinates.

Для IC-LoRA factor больше единицы guide кодируется на меньшей spatial grid, после чего sparse dilation размещает значения через шаг `factor`. Промежутки заполняются нулями, а служебная guide mask — значениями `-1` вне grid и `1` на grid до вычитания strength.

`attention_mask` не подменяет noise mask. Она сохраняется как `pixel_mask` формы `(1,1,F,H,W)` в `guide_attention_entries`; resize выполняется позднее model-side кодом. Active output LATENT содержит только `samples/noise_mask`, поэтому прочие metadata исходного словаря не копируются.

## Совместимость, изменения и устаревание

Статья сверена с ComfyUI `0.32.0`, frontend `1.48.7`, runtime ID `LTXVAddGuide` и модулем `comfy_extras.nodes_lt`. Fingerprint: `sha256:3c478070c2ad282646d3e923fc8ecbbe8196d3a68601421f99d2a612129885d1`.

Нода активна, не experimental и не deprecated; formal replacement отсутствует. Контракт зависит от пятиосевого 128-channel LTXV latent, `vae.downscale_index_formula` и model-side поддержки keyframe metadata.

Английские embedded docs 0.5.9 в целом соответствуют текущим inputs. Русская страница устарела: указывает strength только до `1`, не перечисляет `attention_mask` и `iclora_parameters`. Обе страницы упрощают фактическое выравнивание frame index.

## Связанные ноды и источники

`LTXVPreprocess` готовит референс, `GetICLoRAParameters` передаёт IC-LoRA scale, `LTXVConcatAVLatent` добавляет audio stream, `LTXVCropGuides` очищает результат. `LTXVImgToVideoInplace` — более простой вариант для стартового кадра без keyframe entries.

- [Реализация `LTXVAddGuide`](https://github.com/Comfy-Org/ComfyUI/blob/c2bcbecd82ec5ae66594340b395c24ef0217b238/comfy_extras/nodes_lt.py#L250-L496)
- [Guide attention helper](https://github.com/Comfy-Org/ComfyUI/blob/c2bcbecd82ec5ae66594340b395c24ef0217b238/comfy_extras/nodes_lt.py#L181-L208)
- [Официальный LTX 2.3 style-transition template](https://github.com/Comfy-Org/workflow_templates/blob/cca1ea5ea4560108ecc2f44dee951f41ea433062/templates/video_ltx2_3_flf2v.json)
- [Embedded docs 0.5.9](https://github.com/Comfy-Org/embedded-docs/blob/1d258cf6e374d60d138a2bfcd273c7e11f750ef9/comfyui_embedded_docs/docs/LTXVAddGuide/en.md)
