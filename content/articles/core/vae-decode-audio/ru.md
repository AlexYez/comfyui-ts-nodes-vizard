# VAEDecodeAudio: audio latent в waveform

## Назначение

`VAEDecodeAudio` преобразует audio `LATENT` в структуру `AUDIO`: waveform tensor и sample rate. Декодирование выполняет VAE, подключённый ко второму входу.

Нода также переставляет ось каналов и ограничивает общий уровень по standard deviation. Это часть реализации, а не отдельный виджет.

## Место в графе

В `samples` подают результат audio sampler либо закодированный audio latent. В `vae` подают VAE из совместимого checkpoint или `VAELoader`. Выход подключают к preview, save, audio processing или video assembly.

Для обычных latent небольшого размера используют `VAEDecodeAudio`. В том же module есть tiled-вариант с tile size и overlap; он предназначен для другого memory-профиля и имеет отдельный runtime ID.

## Входы

`samples` — обязательный `LATENT`. Runtime-тип не гарантирует, что latent аудиоформата: image latent формально подключается тем же типом, но не соответствует audio VAE.

`vae` — обязательный `VAE`. Нода не проверяет архитектурную пару заранее; несовместимость проявится внутри `vae.decode` либо даст неверную форму результата.

## Выход

Выход `AUDIO` — словарь с `waveform` и `sample_rate`. После `movedim(-1, 1)` ожидаемая форма waveform — `[batch, channels, samples]`.

Sample rate выбирается в таком порядке: поле `samples["sample_rate"]`, если оно есть; иначе `vae.audio_sample_rate_output`; затем `vae.audio_sample_rate`; в последнюю очередь 44 100.

## Как работает

Нода берёт `samples["samples"]`. Если tensor nested, helper разворачивает его и декодирует только последний элемент. Обычный tensor целиком передаётся в `vae.decode`, затем последняя ось переносится на позицию channels.

После decode вычисляется `torch.std` по channels и samples отдельно для каждого batch-элемента. Значение умножается на 5, но не опускается ниже 1; waveform делится на полученный коэффициент. Сигнал с исходным std меньше 0,2 не усиливается, а более высокий std уменьшается примерно до 0,2. Peak level при этом не нормализуется.

## Параметры и настройка

У ноды нет виджетов. Результат определяют содержимое latent и загруженный VAE. Используйте VAE из той же audio-модели или явно совместимый decoder.

Если latent несёт `sample_rate`, он переопределит атрибуты VAE. Это полезно для сохранённой частоты, но неверное metadata-число также попадёт в выход без resampling: helper меняет только значение поля.

## Проверенный пример

В `audio_stable_audio_example`, workflow `5fa61cc8-29d9-4deb-9f90-02d3c00b63b3`, `KSampler` № 3 передаёт latent ноде № 12, а VAE приходит от `CheckpointLoaderSimple` № 4. Выход AUDIO идёт в `SaveAudioMP3` № 19. Shared fragment каталога переносит `EmptyLatentAudio` № 11 → `KSampler` № 3 → `VAEDecodeAudio` № 12 и точные sampling widgets.

В 512 official JSON найдено 16 экземпляров `VAEDecodeAudio` в 16 файлах: 11 root и 5 subgraph, у всех `widgets_values: []`. Помимо KSampler и audio save есть Minimax video cases: `SamplerCustomAdvanced` → decoder → `CreateVideo`. Synthetic stub-VAE check подтвердил movedim, scaling и приоритет sample rate, но реальный VAE и звук не запускались.

## Частые ошибки

**Подключают image VAE к audio latent.** Одинаковый порт `VAE` не доказывает совместимость архитектуры.

**Ожидают peak normalization.** Код масштабирует по standard deviation. Отдельные peaks могут остаться выше желаемого уровня.

**Считают sample rate операцией resample.** Нода выбирает metadata-число, но не меняет временную сетку waveform после decode.

**Nested latent считают пакетным списком для полного decode.** Helper берёт последний элемент `unbind()`.

## Ограничения и производительность

Полный decode требует памяти под latent, внутренние VAE-активации и готовый waveform. Длинный audio latent или большой batch может не поместиться в память. Tiled decoder уменьшает профиль отдельных активаций ценой разбиения и overlap.

Постобработка создаёт standard-deviation tensor и выполняет деление waveform. Нода не обрезает NaN, не ограничивает peaks и не проверяет фактическую длительность. Audio quality и корректность каналов требуют прослушивания или измерения реального decode, которого здесь не было.

## Совместимость и источники

Материал закреплён на ComfyUI 0.32.0, commit `c2bcbecd82ec5ae66594340b395c24ef0217b238`. Runtime ID — `VAEDecodeAudio`, python module — `comfy_extras.nodes_audio`.

Embedded docs 0.5.9 по пути `comfyui_embedded_docs/docs/VAEDecodeAudio/en.md` верно упоминают normalization, но упрощают выбор sample rate до 44 100 или metadata samples. Реализация между ними проверяет `audio_sample_rate_output` и `audio_sample_rate` у VAE.

- [Helper и класс `VAEDecodeAudio`](https://github.com/Comfy-Org/ComfyUI/blob/c2bcbecd82ec5ae66594340b395c24ef0217b238/comfy_extras/nodes_audio.py#L98-L133)
- [Official workflow templates JSON 0.1.42](https://pypi.org/project/comfyui-workflow-templates-json/0.1.42/)
- [Pinned embedded docs 0.5.9](https://pypi.org/project/comfyui-embedded-docs/0.5.9/)
