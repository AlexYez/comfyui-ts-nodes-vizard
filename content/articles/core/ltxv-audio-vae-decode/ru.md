# LTXVAudioVAEDecode: получить AUDIO из LTX audio latent

## Что делает нода

`LTXVAudioVAEDecode` декодирует LTX audio `LATENT` в `AUDIO`. Она вызывает специализированный `audio_vae.decode`, переносит последнюю ось результата на позицию channels и возвращает waveform с частотой модели.

Если `samples["samples"]` — nested tensor, нода делает `unbind()` и выбирает последний элемент. Остальные nested-части не декодируются.

В отличие от общего `VAEDecodeAudio`, здесь нет std-scaling после VAE. Амплитуда остаётся такой, какой её вернул LTX decoder.

## Когда использовать и когда не использовать

Нода предназначена для аудиочасти LTX 2.x AV latent. В официальных графах joint latent сначала разделяется через `LTXVSeparateAVLatent`, затем audio-часть декодируется и добавляется в `CreateVideo`.

Не подключайте произвольный audio latent и VAE другой архитектуры. Порт `LATENT` не различает семейства на уровне типов, поэтому совместимость обеспечивает структура workflow.

Для Stable Audio, ACE или другого общего audio VAE обычно нужен `VAEDecodeAudio`; он также применяет отдельную нормализацию, которой у LTX-ноды нет.

## Короткий рецепт подключения

1. Отделите audio latent от LTX AV latent.
2. Подайте тот же совместимый LTX Audio VAE, который соответствует модели.
3. Декодируйте через `LTXVAudioVAEDecode`.
4. Прослушайте AUDIO отдельно или подключите к `CreateVideo.audio`.
5. Сверьте fps, длительность и отсутствие NaN/clipping.

Рецепт каталога повторяет устойчивую official topology decoder → `CreateVideo` при `24 fps`. AV split, sampler и video decode остаются внешними.

## Входы, выходы и параметры

`samples: LATENT` и `audio_vae: VAE` обязательны, виджетов нет. Из LATENT используется только поле `samples`.

После `audio_vae.decode(audio_latent)` ожидается форма `[B,T,C]`. `movedim(-1,1)` создаёт `[B,C,T]`, затем результат переносится на device входного audio latent.

Sample rate читается строго из `audio_vae.first_stage_model.output_sample_rate` и приводится к `int`. Поле `samples["sample_rate"]` и wrapper-атрибуты VAE здесь не имеют приоритета.

## Типовые связки

`LTXVSeparateAVLatent.audio → LTXVAudioVAEDecode → CreateVideo.audio` встречается во всех официальных случаях baseline. VAE обычно приходит от `LTXVAudioVAELoader`; в трёх LTX 2.5 subgraph используется общий `VAELoader`.

`LTXVAudioVAEEncode` готовит исходный audio latent для image-and-audio-to-video. После sampling decode возвращает сгенерированный или изменённый звук.

Для диагностики подключите `PreviewAudio` перед `CreateVideo`. Это помогает отделить дефект audio decode от video container/codec.

## Практический пример

Полный census 0.1.42 нашёл 21 `LTXVAudioVAEDecode` в 19 файлах, все внутри subgraph. Двадцать mode Always, один mode Bypass. Root-вхождений нет.

Во всех 21 случаях вход LATENT приходит от `LTXVSeparateAVLatent`, а выход AUDIO идёт в `CreateVideo`. Восемнадцать VAE-входов подключены к `LTXVAudioVAELoader`, три в LTX 2.5 — к `VAELoader`.

В репрезентативном `video_ltx2_3_t2v` decoder № 220 получает audio-выход split № 218 и VAE № 221, затем подключается к `CreateVideo` № 242 с fps 24. Fake VAE подтвердил форму, device и sample rate; настоящие веса не запускались.

## Частые ошибки и способы проверки

**Используют joint AV latent напрямую.** Официальный граф сначала отделяет audio-часть. Подайте выход правильного порта `LTXVSeparateAVLatent`.

**Ожидают decode всех nested-элементов.** Нода берёт последний `unbind()`; это не batch-цикл.

**Подключают VAE без `first_stage_model.output_sample_rate`.** Decode может вернуть waveform, но чтение частоты завершится ошибкой атрибута.

**Ожидают std normalization как у общего decoder.** LTX-нода её не выполняет. Проверяйте уровень отдельно.

**Меняют metadata sample_rate в LATENT.** Эта нода его игнорирует; частота приходит из first-stage модели.

## Производительность и внутреннее поведение

Decode выполняется целиком одним вызовом `audio_vae.decode`; явных tile-параметров нет. Пиковая память зависит от длительности latent, batch, VAE и его внутренней реализации.

`movedim` обычно создаёт view, но последующее `.to(audio_latent.device)` может выделить копию, если decoder вернул tensor на другом устройстве. Выходной словарь новый и содержит только waveform/sample_rate.

Нет clamp, normalization или проверки finite. Эти свойства следует измерять после реального decode.

## Совместимость, изменения и устаревание

Материал закреплён на ComfyUI `0.32.0`, frontend `1.48.7`, runtime ID `LTXVAudioVAEDecode`, модуль `comfy_extras.nodes_lt_audio`. Fingerprint: `sha256:8e75992d4ea4cf77781d6adea98ec3fd339e3f0f0c23865802e88ca1321f50ca`.

Нода активна, не experimental и не deprecated. Формальных replacement и aliases нет.

Embedded docs верно фиксируют nested-last и sample rate модели. Отличие от generic std-scaling, строгий путь `first_stage_model.output_sample_rate` и массовая CreateVideo topology проверены дополнительно.

## Связанные ноды и источники

`LTXVAudioVAEEncode` выполняет LTX encode. `VAEDecodeAudio` — общий decoder с другим post-processing; `PreviewAudio` и `SaveAudioAdvanced` помогают проверить выход.

- [Реализация `LTXVAudioVAEDecode`](https://github.com/Comfy-Org/ComfyUI/blob/c2bcbecd82ec5ae66594340b395c24ef0217b238/comfy_extras/nodes_lt_audio.py#L60-L89)
- [Официальный LTX 2.3 text-to-video template](https://github.com/Comfy-Org/workflow_templates/blob/cca1ea5ea4560108ecc2f44dee951f41ea433062/templates/video_ltx2_3_t2v.json)
- [Embedded docs 0.5.9](https://github.com/Comfy-Org/embedded-docs/blob/1d258cf6e374d60d138a2bfcd273c7e11f750ef9/comfyui_embedded_docs/docs/LTXVAudioVAEDecode/en.md)
