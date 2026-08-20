# VAEDecodeAudioTiled: декодировать audio LATENT частями

## Что делает нода

`VAEDecodeAudioTiled` превращает audio `LATENT` в `AUDIO`, вызывая `vae.decode_tiled` с заданными размером тайла и перекрытием. Цель — уменьшить пиковый memory footprint длинного decode.

После VAE последняя ось переносится на позицию channels, и waveform получает привычную форму `[batch, channels, samples]`. Затем общий helper уменьшает слишком высокое standard deviation отдельно для каждого batch-элемента.

Это тот же post-processing, что у `VAEDecodeAudio`; отличается способ получения waveform внутри VAE.

## Когда использовать и когда не использовать

Tiled decode нужен, когда обычный audio VAE decode не помещается в память или длинный latent удобнее обрабатывать частями. Сначала разумно проверить обычный `VAEDecodeAudio`: он проще и не вводит границы тайлов.

Не выбирайте tiled только потому, что параметров больше. Маленький tile увеличивает число вызовов и overhead, а недостаточное перекрытие может сделать швы заметнее. Слишком большое overlap тратит память и время повторно.

Нода не исправляет несовместимый LATENT/VAE и не гарантирует меньшую итоговую память для любой пользовательской реализации VAE.

## Короткий рецепт подключения

1. Подайте audio `LATENT` и совместимый `VAE`.
2. Начните с defaults `tile_size=512`, `overlap=64`.
3. При OOM уменьшайте tile постепенно.
4. Если слышны границы, сравните overlap и обычный decode.
5. Проверяйте sample rate, длительность, NaN и пики результата.

Рецепт каталога — source-derived fragment с defaults. Exact-нода не встречается в официальных templates 0.1.42, поэтому настройки не названы проверенным workflow preset.

## Входы, выходы и параметры

`samples: LATENT` и `vae: VAE` обязательны. `tile_size` — `INT` от `32` до `8192`, default `512`, шаг `8`. `overlap` — `INT` от `0` до `1024`, default `64`, шаг `8`.

Класс передаёт один `tile_size` сразу как `tile_x` и `tile_y`. Для обычного одномерного audio latent dispatcher `VAE.decode_tiled` удаляет `tile_y` и вызывает 1D tiler. Поэтому число 512 относится к latent-оси, а не напрямую к 512 PCM-отсчётам.

Схема не требует `overlap < tile_size`. Невыгодные или некорректные сочетания доходят до VAE/tiler; подбирайте их осознанно.

## Типовые связки

Audio sampler или `VAEEncodeAudio` создаёт LATENT, tiled decoder возвращает AUDIO, затем идут `PreviewAudio` и `SaveAudioAdvanced`.

Для A/B подключите один latent к обычному и tiled decoder с одним VAE. Сравните длительность, waveform, границы и расход памяти.

Если LATENT содержит `sample_rate`, это число приоритетно попадает в выход, но waveform не resample-ится. Иначе helper выбирает `vae.audio_sample_rate_output`, затем `vae.audio_sample_rate`, затем `44100`.

## Практический пример

В полном обходе 512 JSON и 272 subgraph `VAEDecodeAudioTiled` не найден. Официального выбора tile/overlap для baseline 0.32.0 нет.

Fake VAE получил точные аргументы `tile_x=512`, `tile_y=512`, `overlap=64`. Возвращённый `[B,T,C]` был преобразован в `[B,C,T]`, а sample rate взят сначала из `samples`, затем из `audio_sample_rate_output`.

Отдельно проверена normalization: `std` считается по channels и samples, умножается на 5 и ограничивается снизу единицей. Реальный длинный audio latent и качество тайлов не проверялись.

## Частые ошибки и способы проверки

**Считают tile_size числом PCM samples.** Для 1D audio это размер участка latent; длина waveform зависит от temporal compression VAE.

**Overlap больше или равен tile.** Схема это допускает, но tiler может стать крайне медленным или завершиться ошибкой. Начните с согласованных defaults.

**Nested LATENT ожидают декодировать целиком.** Helper делает `unbind()` и берёт только последний элемент.

**Sample rate metadata считают resample.** После decode меняется только число в словаре; временная сетка waveform уже создана VAE.

**Очень короткий decode даёт NaN.** Для одного значения `torch.std` с correction по умолчанию возвращает NaN; нижняя граница его не исправляет. Проверяйте `isfinite`.

## Производительность и внутреннее поведение

Меньший tile снижает размер отдельных VAE-активаций, но увеличивает число участков. Overlap декодируется повторно и затем смешивается. Итоговый waveform всё равно должен поместиться в памяти.

Helper дополнительно вычисляет std по каждому batch и делит waveform. Если `std*5 < 1`, делитель становится 1; более громкий сигнал уменьшается. Peak отдельно не нормализуется.

При nested input декодируется последний tensor. Нода не ловит несовместимость формы и не выполняет fallback к обычному decoder.

## Совместимость, изменения и устаревание

Проверено на ComfyUI `0.32.0`, frontend `1.48.7`, runtime ID `VAEDecodeAudioTiled`, модуль `comfy_extras.nodes_audio`. Fingerprint: `sha256:7b778a1c2dea5519345b08497ffe6bc9a7f633a8aa4f752b8c9350bf8220e2d4`.

Нода активна, не experimental и не deprecated. Она остаётся отдельным ID от `VAEDecodeAudio`; формального replacement между ними нет.

Embedded docs объясняют memory purpose, но называют tile «участком аудио» без уточнения latent-единиц и не описывают std-scaling, sample-rate precedence, nested-last и singleton NaN.

## Связанные ноды и источники

`VAEDecodeAudio` — обычная альтернатива. `VAEEncodeAudio` создаёт audio latent, `PreviewAudio` и `SaveAudioAdvanced` помогают проверить и сохранить результат.

- [Helper и `VAEDecodeAudioTiled`](https://github.com/Comfy-Org/ComfyUI/blob/c2bcbecd82ec5ae66594340b395c24ef0217b238/comfy_extras/nodes_audio.py#L98-L159)
- [Dispatcher `VAE.decode_tiled`](https://github.com/Comfy-Org/ComfyUI/blob/c2bcbecd82ec5ae66594340b395c24ef0217b238/comfy/sd.py#L1281-L1311)
- [Embedded docs 0.5.9](https://github.com/Comfy-Org/embedded-docs/blob/1d258cf6e374d60d138a2bfcd273c7e11f750ef9/comfyui_embedded_docs/docs/VAEDecodeAudioTiled/en.md)
