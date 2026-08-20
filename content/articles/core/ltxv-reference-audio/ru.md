# LTXVReferenceAudio: передать голосовой референс в LTXV ID-LoRA

## Что делает нода

`LTXVReferenceAudio` готовит голосовой референс для LTXV ID-LoRA. Она приводит waveform к частоте Audio VAE, кодирует звук в latent, перестраивает его в последовательность токенов и записывает одинаковый `ref_audio` в positive и negative conditioning.

Кроме conditioning, нода возвращает клон MODEL с post-CFG-функцией. В заданном диапазоне сигм функция делает дополнительный model pass без `ref_audio`, сравнивает prediction с референсом и без него, затем прибавляет разницу к обычному CFG-результату: `cfg_result + (cond_pred - pred_noref) * identity_guidance_scale`.

Это подготовительная нода, а не аудиогенератор. Она не выдаёт `AUDIO`, не запускает sampler сама и не загружает ID-LoRA. Совместимый model и LoRA должны быть собраны upstream.

## Когда использовать и когда не использовать

Используйте ноду в LTXV ID-LoRA workflow для переноса особенностей голоса из короткого аудиоклипа. Runtime tooltip рекомендует около пяти секунд — это длительность, использованная при обучении; более короткий или длинный фрагмент может ослабить сходство, но код не обрезает его до пяти секунд.

Подключайте только Audio VAE и model того семейства, которое понимает токены `ref_audio`. Общий разъём `MODEL` или `VAE` не подтверждает такую совместимость. В официальном кейсе model сначала проходит через ID-LoRA, а Audio VAE загружается из того же LTX 2.3 checkpoint.

Не используйте ноду как обычный audio prompt encoder и не ожидайте, что `identity_guidance_scale = 0` удалит референс. Ноль отключает дополнительный проход и усиление, но закодированные токены всё равно добавляются в positive и negative conditioning.

## Короткий рецепт подключения

1. Загрузите LTXV model и примените совместимую ID-LoRA.
2. Подайте positive и negative от текстовых conditioning-ветвей.
3. Загрузите чистый референс типа `AUDIO` и совместимый LTX Audio VAE.
4. Начните с официального пресета `identity_guidance_scale = 3`, `start_percent = 0`, `end_percent = 1`.
5. Передайте MODEL-выход в `CFGGuider`, а оба conditioning-выхода — через `LTXVConditioning` в тот же guider.

Рецепт Wizard сохраняет точную структуру единственного официального кейса `video_ltx2_3_id_lora`. Он не содержит аудиофайл, checkpoint или LoRA и не заявляет запуск генерации с реальными весами.

## Входы, выходы и параметры

`model` — модель, которую нода клонирует и снабжает post-CFG callback. `positive` и `negative` — обязательные `CONDITIONING`; в каждый элемент их metadata добавляется один и тот же объект `ref_audio`.

`reference_audio` содержит `waveform` и `sample_rate`. Если частота отличается от `audio_vae.audio_sample_rate`, waveform ресэмплируется; при отсутствии атрибута VAE используется fallback `44100`. Канальная ось переносится из `(B, C, T)` в `(B, T, C)` перед encode.

`audio_vae` кодирует waveform. Ожидаемая форма результата — четыре измерения `(B, C, T, F)`. Нода переставляет её в `(B, T, C, F)` и сворачивает последние две оси, получая tokens `(B, T, C*F)`.

`identity_guidance_scale` принимает `0…100`, default `3`, шаг `0.01`. `start_percent` и `end_percent` принимают `0…1`, defaults `0` и `1`; они ограничивают только дополнительный guidance-pass. Выходы: клонированный `MODEL`, изменённые `positive` и `negative`.

## Типовые связки

Официальная model-ветвь выглядит как `LoraLoaderModelOnly → LTXVReferenceAudio → CFGGuider`. Именно MODEL-выход ноды должен попасть в guider; если подключить исходную модель в обход, установленная post-CFG-функция не выполнится.

Conditioning-ветвь проходит `CLIPTextEncode → LTXVReferenceAudio → LTXVConditioning → CFGGuider`. `LTXVConditioning` добавляет кадровую частоту, не заменяя `ref_audio`.

`LTXVAudioVAELoader → LTXVReferenceAudio` обеспечивает latent-геометрию референса. Один loader в официальном subgraph одновременно обслуживает reference encode, пустой аудиолатент и финальный decode, поэтому все стадии используют одну аудиосистему.

## Практический пример

Полный recursive census 512 JSON официального wheel 0.1.42 нашёл ровно один `LTXVReferenceAudio`. Он находится в subgraph UUID `98ee9e5b-467b-40aa-a534-36033f27d0b4` файла `video_ltx2_3_id_lora.json`, mode `Always`, node id `349`.

Сохранённые значения — `[3, 0, 1]`: scale `3`, guidance активен на полном процентном диапазоне. Вход MODEL приходит от ID-LoRA-ветви, reference audio — из внешнего входа subgraph, VAE — от `LTXVAudioVAELoader` №335. Positive и negative приходят от разных `CLIPTextEncode`.

MODEL-выход №349 идёт в `CFGGuider` №315. Conditioning-выходы сначала подключены к `LTXVConditioning` №307, затем к тому же guider. Этот кейс подтверждает topology и preset, но не доказывает совместимость других ID-LoRA или качество переноса на произвольном аудио.

## Частые ошибки и проверка

**Голосовой референс почти не влияет.** Проверьте, что используете ID-LoRA/model с поддержкой `ref_audio`, MODEL-выход ноды подключён к guider, а scale ненулевой в текущем диапазоне сигм.

**Scale равен нулю, но референс всё ещё действует.** Это ожидаемо: токены уже добавлены в conditioning. Ноль отключает только дополнительный no-reference pass. Чтобы убрать референс полностью, обойдите ноду conditioning-ветвью.

**Guidance ни разу не включается.** Сверьте порядок `start_percent ≤ end_percent`. Код не меняет их местами. При обратном диапазоне обычная убывающая sigma-шкала, как правило, не попадает в разрешённое окно.

**Ошибка формы после VAE encode.** Нода распаковывает ровно четыре измерения `B, C, T, F`. Обычный image VAE или другой audio encoder может вернуть несовместимый tensor.

**Расход памяти резко вырос.** В активном sigma-окне каждый sampling step получает дополнительный conditional model pass без референса. Сократите окно или поставьте scale `0`, если amplification не нужен.

## Производительность и внутреннее поведение

Ресэмплирование и VAE encode выполняются один раз при запуске ноды. Число ref-токенов растёт с длительностью клипа; код не содержит автоматического trim, chunking или ограничения примерно пятью секундами.

Post-CFG callback клонирует список conditioning entries для дополнительного прохода и удаляет `ref_audio` только из `model_conds` этих копий. Остальные model conditions и options сохраняются. Затем `calc_cond_batch` выполняет prediction на том же `input` и `sigma`.

Проверка окна берёт `sigma[0].item()`, то есть одну sigma для всего batch. Границы включены: guidance работает, когда `sigma_end ≤ sigma ≤ sigma_start`. При scale `0` или за пределами окна функция сразу возвращает готовый `denoised` без дополнительного model call.

Scale `1` не означает «обычный CFG»: extra pass всё ещё выполняется, а разность predictions прибавляется с коэффициентом `1`. Нода также не нормирует и не ограничивает эту поправку, поэтому высокий scale может дать нестабильный результат.

## Совместимость, изменения и устаревание

Статья сверена с ComfyUI `0.32.0`, frontend `1.48.7`, runtime ID `LTXVReferenceAudio` и модулем `comfy_extras.nodes_lt`. Fingerprint: `sha256:3b6634f8f0d62d633b4917834ea9da24aea26cb9f15ec4b9b8b35249ba4bc8a6`.

Нода активна, не experimental, не deprecated, не dev-only и не API node. Formal Node Replacement отсутствует. Совместимость с конкретной ID-LoRA определяется моделью и весами, а не одной runtime-схемой.

Embedded docs 0.5.9 правильно описывают назначение и диапазоны, но русский файл ошибочно подписывает MODEL-выход как `positive`. Закреплённый `/object_info` задаёт выходы `MODEL`, `positive`, `negative`. Документация также не уточняет, что scale `0` оставляет ref-токены в conditioning.

## Связанные ноды и источники

`LTXVAudioVAELoader` поставляет Audio VAE, `LTXVConditioning` добавляет frame rate, `CFGGuider` использует патченный MODEL и два conditioning. `LTXVEmptyLatentAudio`, `LTXVConcatAVLatent` и `LTXVSeparateAVLatent` отвечают за joint audio-video latent, но не за speaker identity.

- [Реализация `LTXVReferenceAudio`](https://github.com/Comfy-Org/ComfyUI/blob/c2bcbecd82ec5ae66594340b395c24ef0217b238/comfy_extras/nodes_lt.py#L855-L937)
- [Копирование conditioning metadata](https://github.com/Comfy-Org/ComfyUI/blob/c2bcbecd82ec5ae66594340b395c24ef0217b238/node_helpers.py#L9-L23)
- [Официальный LTX 2.3 ID-LoRA template](https://github.com/Comfy-Org/workflow_templates/blob/cca1ea5ea4560108ecc2f44dee951f41ea433062/templates/video_ltx2_3_id_lora.json)
- [Embedded docs 0.5.9](https://github.com/Comfy-Org/embedded-docs/blob/1d258cf6e374d60d138a2bfcd273c7e11f750ef9/comfyui_embedded_docs/docs/LTXVReferenceAudio/en.md)
