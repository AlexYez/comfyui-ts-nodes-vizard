# EmptyLatentAudio: нулевой audio latent заданной длительности

## Назначение

`EmptyLatentAudio` создаёт нулевой tensor для начала генерации звука с нуля. Выход имеет общий тип `LATENT`, но содержит metadata `type: "audio"` и temporal downscale ratio.

Это не waveform и не тишина, которую можно сразу прослушать. Latent нужно обработать совместимой моделью и декодировать через audio VAE.

## Место в графе

Выход обычно подключают к `latent_image` у `KSampler` или к совместимому custom sampler. После sampling latent передают в `VAEDecodeAudio`.

`EmptyAudio` создаёт готовый `AUDIO` из нулей. `EmptyLatentAudio` создаёт пространство признаков с 64 каналами; sample rate его выхода не является пользовательским параметром.

## Входы

`seconds` — FLOAT от 1 до 1000 с шагом 0,1; значение по умолчанию — 47,6. Нода использует его для расчёта temporal length, но не хранит как отдельное поле результата.

`batch_size` — INT от 1 до 4096, по умолчанию 1. Он становится первым измерением tensor. Tooltip называет элементы «latent images», хотя runtime NodeId и metadata относятся к аудио.

## Выход

Словарь `LATENT` содержит `samples` формы `[batch_size, 64, length]`, строку `type: "audio"` и `downscale_ratio_temporal: 2048`. Samples заполнены нулями на `intermediate_device` ComfyUI.

Нода не добавляет `sample_rate`. Число 44 100 участвует только во внутренней формуле длины.

## Как работает

Length вычисляется как `round((seconds × 44100 / 2048) / 2) × 2`. Деление и последующее умножение на 2 делают length чётным. После округления фактическая длительность latent обычно немного отличается от введённых секунд.

Sampler видит нулевой tensor и metadata ratio. `fix_empty_latent_channels` при необходимости меняет число каналов и temporal length под latent format модели, если её temporal downscale ratio отличается от 2048.

## Параметры и настройка

Согласуйте seconds с моделью и желаемой длительностью. Формула жёстко использует 44 100 Гц; отдельного входа sample rate здесь нет. При 1 секунде length равен 22, а не точному частному 44 100 / 2048.

Batch увеличивает число параллельных latent. Он не создаёт многоканальный звук: audio channels появляются при VAE decode, а не через `batch_size`.

## Проверенный пример

В official workflow `audio_stable_audio_example`, ID `5fa61cc8-29d9-4deb-9f90-02d3c00b63b3`, нода № 11 использует widgets `[47.6, 1]`, подаёт LATENT в `latent_image` `KSampler` № 3, а результат sampler идёт в `VAEDecodeAudio` № 12. Рецепт каталога переносит эту тройку и sampling widgets без checkpoint-dependent значений.

Полный scan 512 JSON нашёл три экземпляра в трёх файлах: один в root и два в subgraphs. В двух Stable Audio 3 шаблонах widgets `[60, 1]`, но seconds также подключён от `PrimitiveFloat`, поэтому связанное значение имеет приоритет. Synthetic check с 1 секундой и batch 2 подтвердил shape `[2, 64, 22]`, нули и оба metadata-поля. Полный граф не запускался.

## Частые ошибки

**LATENT подключают к audio-порту.** До декодирования это не `AUDIO`. Нужен совместимый sampler и VAE decoder.

**Seconds считают точной длиной waveform.** Формула округляет latent length до чётного числа. Декодер и VAE определяют итоговое число samples.

**Batch_size принимают за stereo.** Batch и audio channels — разные оси.

**Игнорируют модельный latent format.** Sampler может адаптировать нулевой tensor к другому числу каналов или temporal ratio.

## Ограничения и производительность

Первичное выделение памяти пропорционально `batch_size × 64 × length`. Сам tensor сравнительно мал, но большой batch умножает стоимость последующего diffusion sampling и decode.

Нода рассчитана на audio latent с исходным ratio 2048 и формулой через 44 100 Гц. Она не проверяет, поддерживает ли загруженная модель такой формат, и не гарантирует точную секундную длину после VAE. Значение 1000 секунд может привести к очень дорогому sampler-run.

## Совместимость и источники

Статья описывает ComfyUI 0.32.0 на commit `c2bcbecd82ec5ae66594340b395c24ef0217b238`. Runtime ID — `EmptyLatentAudio`, python module — `comfy_extras.nodes_audio`.

Embedded docs 0.5.9 по пути `comfyui_embedded_docs/docs/EmptyLatentAudio/en.md` верно называют shape и ratio 2048, но говорят о расчёте по sample rate без уточнения, что 44 100 зашито в код и не задаётся входом.

- [Реализация `EmptyLatentAudio`](https://github.com/Comfy-Org/ComfyUI/blob/c2bcbecd82ec5ae66594340b395c24ef0217b238/comfy_extras/nodes_audio.py#L13-L36)
- [Адаптация нулевого latent под model format](https://github.com/Comfy-Org/ComfyUI/blob/c2bcbecd82ec5ae66594340b395c24ef0217b238/comfy/sample.py#L40-L63)
- [Official workflow templates JSON 0.1.42](https://pypi.org/project/comfyui-workflow-templates-json/0.1.42/)
- [Pinned embedded docs 0.5.9](https://pypi.org/project/comfyui-embedded-docs/0.5.9/)
