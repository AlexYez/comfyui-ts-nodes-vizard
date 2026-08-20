# LTXVSeparateAVLatent: разделить joint AV latent на видео и аудио

## Что делает нода

`LTXVSeparateAVLatent` извлекает два потока из joint AV latent: первый становится `video_latent`, второй — `audio_latent`. Ожидаемый `samples` — ComfyUI `NestedTensor`, созданный `LTXVConcatAVLatent` или совместимой AV-нодой.

Оба выхода получают неглубокую копию входного словаря. Затем ключ `samples` заменяется соответствующим потоком. Если во входе есть nested `noise_mask` и она не равна `None`, маска разбирается в том же порядке: первая идёт к видео, вторая — к аудио.

Нода не декодирует данные и не меняет их форму. После разделения видеолатент можно передать в VAE decode, upscale или следующую видеостадию, а аудиолатент — в `LTXVAudioVAEDecode` либо снова соединить с видео.

## Когда использовать и когда не использовать

Используйте ноду сразу после sampler, который обработал совместный audio-video latent. В официальных LTX 2.x subgraph это точка разветвления: видеопоток идёт в decode, crop или upscale, аудиопоток — в LTX Audio VAE decode либо во вторую AV-стадию.

Разделение полезно и между двумя sampler-проходами. Первый результат разбирается, видео дорабатывается отдельно, а сохранённый audio latent затем возвращается через `LTXVConcatAVLatent`.

Не подключайте обычный single-stream latent только потому, что порт называется `LATENT`. Метод вызывает `.unbind()` без указания оси. У `NestedTensor` это возвращает список потоков; у обычного `torch.Tensor` — срезы по batch-оси, что меняет смысл данных и может дать ошибку при пакете из одного элемента.

## Короткий рецепт подключения

1. Соберите joint latent через `LTXVConcatAVLatent`.
2. Выполните AV sampling совместимой моделью.
3. Подайте основной выход sampler в `av_latent`.
4. Отправьте `video_latent` в LTXV video decode, crop или upsample-ветвь.
5. Отправьте `audio_latent` в `LTXVAudioVAEDecode` либо сохраните для следующего `LTXVConcatAVLatent`.

В fragment Wizard перед separation стоит `SamplerCustomAdvanced`, а перед ним — Concat с пустым аудиолатентом. Такая последовательность подтверждена официальными шаблонами; сами веса, guider и расписание остаются внешними входами, полный граф не запускался.

## Входы, выходы и параметры

Единственный вход `av_latent` имеет тип `LATENT`. Числовых параметров и виджетов нет. Для штатной работы `av_latent["samples"]` должен содержать как минимум два потока в порядке video, audio.

Выход `video_latent` получает поток с индексом `0`, а `audio_latent` — поток с индексом `1`. Имена отражают договорённость, но код не проверяет содержимое и не читает поле `type`.

Если ключ `noise_mask` отсутствует, выходы его не получают. Если ключ есть и равен `None`, такое значение остаётся в обеих неглубоких копиях. Если маска присутствует и не равна `None`, реализация также вызывает `.unbind()` и выбирает первые два элемента; полностью нулевая маска тоже разделяется.

Поля `batch_index`, `type`, пользовательские метаданные и любые другие ключи копируются в оба словаря. Вложенные значения не клонируются: оба выхода могут ссылаться на один и тот же изменяемый объект metadata.

## Типовые связки

`SamplerCustomAdvanced → LTXVSeparateAVLatent` — основная официальная связка: 35 из 37 входов. Ещё два экземпляра получают joint latent от `KSampler`. Это подтверждает, что нода стоит после sampling, а не между произвольными LATENT-преобразованиями.

Аудиовыход 21 раз идёт в `LTXVAudioVAEDecode` и 16 раз возвращается в `LTXVConcatAVLatent`. Эти ветви не взаимоисключающие: один subgraph может декодировать финальный звук, другой — сохранить его для второго прохода.

Видеовыход связан с `LTXVCropGuides` 18 раз, с `LTXVLatentUpsampler` восемь раз, с `VAEDecode` семь раз и с `VAEDecodeTiled` 14 раз. Числа относятся к полному рекурсивному census и включают root-связи внутри разных subgraph-определений.

## Практический пример

В wheel `comfyui-workflow-templates-json 0.1.42` найдено 37 экземпляров `LTXVSeparateAVLatent` в 19 файлах. Все находятся в subgraph; 35 сохранены в mode `Always`, два — в mode `Bypass`.

`video_ltx2_3_id_lora` содержит две стадии. `SamplerCustomAdvanced` №291 передаёт joint output в `LTXVSeparateAVLatent` №309. Его video-выход питает conditioning и обработку первой стадии, а audio-выход подключён к `LTXVConcatAVLatent` №287 для следующего sampling. После второго sampler нода №311 снова разделяет потоки: видео идёт в decode, аудио — в `LTXVAudioVAEDecode` №303.

В других проверенных шаблонах структура меняется вокруг ноды, но порядок потоков остаётся тем же. Именно порядок, а не совпадение размеров, связывает `video_latent` и `audio_latent` с нужными выходами.

## Частые ошибки и проверка

**Ошибка индекса при разделении.** В `samples` меньше двух элементов. Проверьте, что upstream действительно создал `NestedTensor((video, audio))`, а не обычный LATENT с batch size `1`.

**Выходы похожи на два элемента batch.** Скорее всего, на вход попал обычный tensor. У него `.unbind()` без аргумента разделяет ось `0`; это не AV-разбиение. Вернитесь к `LTXVConcatAVLatent` и проверьте тип объекта во время выполнения.

**Маска не соответствует samples.** Joint `noise_mask` должна хранить те же два потока в том же порядке. Нода не сверяет число масок и форму каждой пары перед присваиванием.

**Изменение metadata одного выхода затронуло другой.** Копируется только внешний словарь. Если downstream меняет вложенный список или словарь на месте, предварительно создайте независимую копию в своей ноде.

## Производительность и внутреннее поведение

`NestedTensor.unbind()` в ComfyUI 0.32.0 просто возвращает внутренний список тензоров. `LTXVSeparateAVLatent` не копирует tensor storage, не выполняет resize и не переносит данные между устройствами. Операция почти не добавляет вычислений по сравнению с sampler или VAE.

Неглубокий `dict.copy()` создаёт два новых контейнера, но сами `samples`, маски и metadata остаются исходными объектами или view. Это экономит память; одновременно downstream-код должен осторожно относиться к изменениям на месте.

Если nested-структура содержит больше двух потоков, реализация берёт только элементы `0` и `1`; остальные не получают отдельного выхода. Если потоков меньше двух, срабатывает `IndexError`. Формального runtime-gate по числу потоков нет.

## Совместимость, изменения и устаревание

Статья сверена с ComfyUI `0.32.0`, frontend `1.48.7`, runtime ID `LTXVSeparateAVLatent` и модулем `comfy_extras.nodes_lt`. Fingerprint: `sha256:9aa183ccf30449afffab27a3fdbc03b541e03437b985f78256aa49670b0dbf0a`.

Нода активна, не experimental, не deprecated, не dev-only и не API node. Formal Node Replacement отсутствует. Runtime-описание допускает AV-модели помимо LTXV, включая MiniMax H3, если они используют тот же порядок nested-потоков.

Embedded docs 0.5.9 ошибочно объясняют разбиение как выбор первых двух элементов batch-измерения. Это верно только для случайно переданного обычного tensor и не описывает штатный контракт. Исходник `NestedTensor` подтверждает, что `.unbind()` возвращает отдельные video/audio streams.

## Связанные ноды и источники

`LTXVConcatAVLatent` выполняет обратную операцию. `LTXVAudioVAEDecode` преобразует второй выход в waveform, `LTXVLatentUpsampler` дорабатывает первый, а video VAE decoders превращают видеолатент в кадры.

- [Реализация `LTXVSeparateAVLatent`](https://github.com/Comfy-Org/ComfyUI/blob/c2bcbecd82ec5ae66594340b395c24ef0217b238/comfy_extras/nodes_lt.py#L822-L852)
- [Контракт `NestedTensor.unbind`](https://github.com/Comfy-Org/ComfyUI/blob/c2bcbecd82ec5ae66594340b395c24ef0217b238/comfy/nested_tensor.py#L3-L40)
- [Официальный LTX 2.3 ID-LoRA template](https://github.com/Comfy-Org/workflow_templates/blob/cca1ea5ea4560108ecc2f44dee951f41ea433062/templates/video_ltx2_3_id_lora.json)
- [Embedded docs 0.5.9](https://github.com/Comfy-Org/embedded-docs/blob/1d258cf6e374d60d138a2bfcd273c7e11f750ef9/comfyui_embedded_docs/docs/LTXVSeparateAVLatent/en.md)
