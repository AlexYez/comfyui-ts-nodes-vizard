# LTXVAudioVAEEncode: кодировать AUDIO для LTX audio latent

## Что делает нода

`LTXVAudioVAEEncode` переводит waveform в LTX audio `LATENT`. Класс наследует `VAEEncodeAudio` и меняет прежде всего публичную схему: VAE-порт называется `audio_vae`, а выход отображается как `Audio Latent`.

Само выполнение делегируется базовому encoder. При необходимости звук пересчитывается к `audio_vae.audio_sample_rate`, channels переносятся в последнюю ось, затем вызывается `audio_vae.encode`.

Результат — словарь только с `samples`. В него не добавляются sample rate и type.

## Когда использовать и когда не использовать

Нода нужна в LTX image-and-audio-to-video, где исходная речь или другой звук становится частью совместного AV latent. Специализированный ID помогает не перепутать audio VAE с image/video VAE того же графа.

Не используйте её с произвольным VAE. Подходящий loader и checkpoint должны содержать LTX audio autoencoder. Совпадение socket-типа `VAE` не является проверкой архитектуры.

Если граф не относится к LTX, обычный `VAEEncodeAudio` выражает намерение точнее. Технически wrapper выполняет тот же базовый алгоритм.

## Короткий рецепт подключения

1. Получите `AUDIO` и обрежьте его до нужной длительности.
2. Загрузите совместимый LTX Audio VAE.
3. Подайте их в `LTXVAudioVAEEncode`.
4. Добавьте mask или объедините latent с video-веткой по официальной схеме модели.
5. После sampling отделите audio latent и декодируйте LTX decoder.

Рецепт сохраняет доказанную связь `TrimAudioDuration(0,60) → LTXVAudioVAEEncode` из двух официальных speech-to-video templates. Остальная AV-цепочка вынесена наружу.

## Входы, выходы и параметры

`audio: AUDIO` и `audio_vae: VAE` обязательны. Виджетов нет. Tooltip подчёркивает, что второй вход — именно Audio VAE.

Wrapper вызывает `super().execute(audio_vae, audio)`. Базовый код сравнивает `audio["sample_rate"]` с `audio_vae.audio_sample_rate`, используя `44100`, если атрибута нет, и при необходимости resample-ит waveform.

Выход runtime-типа `LATENT` отображается как `Audio Latent`, но содержит только `{"samples": tensor}`. Название порта не добавляет служебные поля.

## Типовые связки

В официальном IA2V subgraph перед encoder стоит `TrimAudioDuration`, после — `SetLatentNoiseMask`. Дальше audio latent участвует в специализированной сборке LTX AV latent.

`LTXVAudioVAELoader` поставляет VAE в encode и decode. Использование одного экземпляра сохраняет согласованную latent-геометрию.

Для простого roundtrip без AV sampling можно сравнить encode с `LTXVAudioVAEDecode`, но такой тест проверяет VAE, а не полный LTX video pipeline.

## Практический пример

В wheel 0.1.42 найдено два `LTXVAudioVAEEncode`, оба внутри subgraph: `template_image_speech_to_video` и `video_ltx2_3_ia2v`. Оба mode Always, без widgets.

В каждом `TrimAudioDuration` № 332 подаёт AUDIO в encoder № 328, `LTXVAudioVAELoader` № 335 — VAE, а выход encoder идёт в `SetLatentNoiseMask` № 327. Сохранённые trim widgets равны `[0,60]`.

Fake-VAE запуск подтвердил, что специализированная нода даёт ту же resample/axis behavior, что базовая. Полный LTX sampler, модели и итоговое видео не запускались.

## Частые ошибки и способы проверки

**Ожидают sample rate и type в выходе.** Embedded docs 0.5.9 это утверждают, но код 0.32.0 возвращает только `samples`. Статья следует runtime.

**Подключают video VAE.** Имя `audio_vae` — смысловое ограничение, хотя socket общий. Используйте loader из проверенного LTX audio workflow.

**Не согласуют длительность с video.** Encoder не знает число кадров. Обрезку и AV-latent геометрию задаёт остальной граф.

**Аудио отсутствует.** Унаследованный код выбрасывает `ValueError` при `None`.

**Считают resample частью latent metadata.** Он меняет waveform до encode, но выбранная частота не записывается в выходной словарь.

## Производительность и внутреннее поведение

Стоимость складывается из возможного resample всего waveform и VAE encode. Длинная речь, большой batch и высокая частота повышают память и время.

Wrapper не добавляет вычислений поверх базового encoder. Нет нормализации, noise mask или копирования metadata; это выполняют соседние ноды.

VAE wrapper может использовать собственную memory-management и tiled fallback. Реальный профиль зависит от LTX checkpoint и устройства.

## Совместимость, изменения и устаревание

Проверено на ComfyUI `0.32.0`, frontend `1.48.7`, runtime ID `LTXVAudioVAEEncode`, модуль `comfy_extras.nodes_lt_audio`. Fingerprint: `sha256:1241bc4cb583386420ed3718a53e9820b423c58aa648606d834198f2a26bdaf3`.

Нода активна, не experimental и не deprecated. Она не alias базового encoder: runtime ID и schema отдельные, несмотря на наследование.

Выявлено расхождение embedded docs: описанные sample rate и type в LATENT отсутствуют. Это повторно проверено по wrapper, base class и прямому вызову.

## Связанные ноды и источники

`LTXVAudioVAEDecode` выполняет обратный LTX decode. `VAEEncodeAudio` — общий базовый вариант, `TrimAudioDuration` согласует временной участок.

- [Wrapper `LTXVAudioVAEEncode`](https://github.com/Comfy-Org/ComfyUI/blob/c2bcbecd82ec5ae66594340b395c24ef0217b238/comfy_extras/nodes_lt_audio.py#L37-L58)
- [Унаследованный `VAEEncodeAudio`](https://github.com/Comfy-Org/ComfyUI/blob/c2bcbecd82ec5ae66594340b395c24ef0217b238/comfy_extras/nodes_audio.py#L66-L96)
- [Официальный speech-to-video template](https://github.com/Comfy-Org/workflow_templates/blob/cca1ea5ea4560108ecc2f44dee951f41ea433062/templates/template_image_speech_to_video.json)
- [Embedded docs 0.5.9](https://github.com/Comfy-Org/embedded-docs/blob/1d258cf6e374d60d138a2bfcd273c7e11f750ef9/comfyui_embedded_docs/docs/LTXVAudioVAEEncode/en.md)
