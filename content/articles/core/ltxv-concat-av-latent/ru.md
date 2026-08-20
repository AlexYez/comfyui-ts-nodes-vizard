# LTXVConcatAVLatent: объединить видео- и аудиолатент

## Что делает нода

`LTXVConcatAVLatent` упаковывает видеолатент и аудиолатент в один joint AV latent. Реализация не склеивает тензоры через `torch.cat`: она создаёт `comfy.nested_tensor.NestedTensor` с двумя потоками, где видео хранится первым, аудио — вторым. Благодаря этому потоки могут иметь разное число измерений и разную внутреннюю форму.

Та же схема применяется к `noise_mask`. Если маска есть хотя бы у одного входа, для второго потока создаётся маска из единиц. Sampler затем видит две согласованные пары: video samples/video mask и audio samples/audio mask.

Нода также распознаёт уже объединённый `video_latent`. В этом режиме первый поток сохраняется как видео, а новый `audio_latent` заменяет прежний аудиопоток. Обычно различается временная ось; технически код умеет обрезать или дополнить любую единственную различающуюся ось с индексом `2` и выше.

## Когда использовать и когда не использовать

Используйте ноду перед совместным audio-video sampling в LTXV или другой AV-модели, которая понимает ComfyUI `NestedTensor`. Официальные LTX 2.x графы собирают joint latent до `SamplerCustomAdvanced`, а после sampling снова разделяют его через `LTXVSeparateAVLatent`.

Режим замены аудио нужен во второй стадии: видеопоток уже прошёл первый sampler или upscale, а аудио требуется вернуть к той же AV-структуре. Реализация сама подгоняет только длину заменяемого аудиопотока; она не меняет видео.

Не подключайте результат к произвольной ноде, которая ожидает обычный `torch.Tensor` и не обрабатывает nested-структуру. Общий порт `LATENT` подтверждает тип разъёма, но не гарантирует, что downstream-код вызовет операции покомпонентно.

## Короткий рецепт подключения

1. Подготовьте видеолатент из LTXV video pipeline.
2. Получите аудиолатент через `LTXVEmptyLatentAudio` или `LTXVAudioVAEEncode`.
3. Подайте видео в `video_latent`, аудио — в `audio_latent`.
4. Передайте joint `latent` в совместимый sampler вместе с guider, сигмами и noise.
5. После sampling подключите результат к `LTXVSeparateAVLatent` и обрабатывайте два выхода отдельно.

Рецепт Wizard сохраняет официальный порядок `Empty audio → Concat → SamplerCustomAdvanced → Separate` с пресетом `97/25/1`. Он оставляет video latent, VAE, NOISE, GUIDER, SAMPLER и SIGMAS внешними входами и потому не заменяет полный LTXV workflow.

## Входы, выходы и параметры

`video_latent` и `audio_latent` — обязательные входы типа `LATENT`. Виджетов и числовых параметров у ноды нет. В обычном режиме ожидается, что в каждом словаре есть ключ `samples` с тензором; наличие `noise_mask` необязательно.

Единственный выход называется `latent` и тоже имеет тип `LATENT`. Его `samples` — `NestedTensor((video_samples, audio_samples))`. Свойство `.shape` у этой обёртки возвращает форму первого, видеопотока; это существенно для нод, которые рассчитывают параметры по `latent["samples"].shape`.

Остальные поля собираются неглубоким слиянием словарей: сначала копируются поля `video_latent`, затем `audio_latent`. При одинаковом имени побеждает значение аудиовхода. После этого `samples` всегда заменяется joint-структурой, а присутствующая и не равная `None` `noise_mask` — парой масок.

## Типовые связки

`LTXVEmptyLatentAudio → LTXVConcatAVLatent` создаёт начальный AV latent для text-to-video-with-audio. В официальном wheel эта связь встречается 19 раз. Видеопоток чаще приходит от `LTXVImgToVideoInplace` — 21 связь; ещё встречаются guide, empty-video, upsample и mask-ветви.

`LTXVSeparateAVLatent.audio_latent → LTXVConcatAVLatent.audio_latent` возвращает аудио во вторую стадию. Таких связей найдено 16. Во всех этих официальных случаях видеовход остаётся отдельным тензором: 12 раз он приходит от `LTXVImgToVideoInplace`, четыре — от `LTXVLatentUpsampler`. Ветка замены аудио внутри уже nested `video_latent` подтверждена исходником и synthetic probe, но не официальным шаблоном.

Выход joint latent 35 раз идёт в `SamplerCustomAdvanced` и два раза — в `KSampler`. Пять scheduler-связей с `LTXVScheduler` используют форму первого потока для расчёта расписания; аудиотензор при этом остаётся второй частью nested-структуры.

## Практический пример

Полный рекурсивный census 512 JSON из официального wheel 0.1.42 нашёл 37 экземпляров `LTXVConcatAVLatent` в 19 файлах. Все расположены в subgraph: 35 имеют mode `Always`, два сохранены в mode `Bypass`.

В `video_ltx2_3_id_lora` нода №326 получает video latent от №325 и пустой audio latent от `LTXVEmptyLatentAudio` №348. Результат поступает в `SamplerCustomAdvanced` №291. После первого прохода `LTXVSeparateAVLatent` №309 отделяет аудио; нода №287 снова соединяет его с обработанным видео, а второй sampler получает joint latent от №287.

Обе ноды Concat в этом примере собирают два отдельных потока. У №287 видеовход приходит от `LTXVImgToVideoInplace` №296, а не из nested AV latent. Подгонка заменяемого аудио — отдельная ветвь реализации; её поведение проверено на синтетическом joint latent, но в wheel 0.1.42 такой topology нет.

## Частые ошибки и проверка

**Downstream-код падает на nested samples.** Подключите выход к ноде, для которой подтверждена работа с AV `NestedTensor`. Если операция обращается к тензору как к обычному массиву, одного совпадения разъёма `LATENT` недостаточно.

**При замене аудио получена ошибка `cannot be fitted`.** Новый и прежний аудиопотоки могут различаться только по одной оси с индексом `2` или выше. Различие batch, channels либо сразу нескольких измерений нода не исправляет.

**Маска ведёт себя неожиданно.** Когда маска задана лишь одному потоку, второй получает единицы. При дополнении короткого аудио нулями хвост его маски также заполняется единицами: этот участок оставляют доступным для генерации, а не блокируют.

**Пропало поле из видеолатента.** Проверьте одноимённое поле в `audio_latent`. Неглубокое слияние даёт аудиовходу приоритет для любых ключей, кроме явно пересобранных `samples` и маски.

## Производительность и внутреннее поведение

В обычной ветви нода не копирует содержимое video/audio samples и не выполняет численную конкатенацию. `NestedTensor` хранит ссылки на два исходных тензора, поэтому сборка обёртки дешева по сравнению с sampling.

Замена короткого аудио выделяет нулевой `pad` и объединяет его через `torch.cat`; маска при наличии расширяется тем же способом, но хвост получает единицы. Длинное аудио и его маска обрезаются через `narrow`, то есть результат может быть view исходного storage.

Операции `NestedTensor` применяются к потокам по отдельности. Его `.device`, `.dtype` и `.shape` сообщают свойства первого потока, а `.ndim` — максимальную размерность среди потоков. Это внутренний контракт 0.32.0, который нельзя приравнивать к обычному тензору с новой осью.

## Совместимость, изменения и устаревание

Статья сверена с ComfyUI `0.32.0`, frontend `1.48.7`, runtime ID `LTXVConcatAVLatent` и модулем `comfy_extras.nodes_lt`. Fingerprint: `sha256:d3acc56f6dd01fcaab5e7ff80a1ea34710f6164f5eae0b8ec090263d5e59f180`.

Нода активна, не experimental, не deprecated, не dev-only и не API node. Formal Node Replacement отсутствует. Описание runtime прямо расширяет область применения на другие AV-модели, например MiniMax H3, но конкретную совместимость надо подтверждать по формату потоков.

Embedded docs 0.5.9 называют операцию «concatenation» и описывают склейку `samples`. В закреплённом коде используется `NestedTensor`, а не `torch.cat`; документация также не раскрывает замену аудио, обрезку, padding и приоритет metadata. Статья следует реализации.

## Связанные ноды и источники

`LTXVEmptyLatentAudio` создаёт пустой второй поток, `LTXVAudioVAEEncode` даёт аудиолатент из waveform, `LTXVSeparateAVLatent` выполняет обратное разбиение. `LTXVScheduler`, `SamplerCustomAdvanced` и отдельные LTXV conditioning-ноды образуют подтверждённое окружение joint latent.

- [Реализация `LTXVConcatAVLatent`](https://github.com/Comfy-Org/ComfyUI/blob/c2bcbecd82ec5ae66594340b395c24ef0217b238/comfy_extras/nodes_lt.py#L747-L819)
- [Контракт `NestedTensor`](https://github.com/Comfy-Org/ComfyUI/blob/c2bcbecd82ec5ae66594340b395c24ef0217b238/comfy/nested_tensor.py#L3-L97)
- [Официальный LTX 2.3 ID-LoRA template](https://github.com/Comfy-Org/workflow_templates/blob/cca1ea5ea4560108ecc2f44dee951f41ea433062/templates/video_ltx2_3_id_lora.json)
- [Embedded docs 0.5.9](https://github.com/Comfy-Org/embedded-docs/blob/1d258cf6e374d60d138a2bfcd273c7e11f750ef9/comfyui_embedded_docs/docs/LTXVConcatAVLatent/en.md)
