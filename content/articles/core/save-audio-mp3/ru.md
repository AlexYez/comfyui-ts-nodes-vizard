# SaveAudioMP3: устаревший экспорт MP3

## Что делает нода

`SaveAudioMP3` кодирует входной `AUDIO` через `libmp3lame` и пишет результат в `output`. Пользователь выбирает `V0`, `128k` или `320k`; каждый элемент batch становится отдельным `.mp3`.

После записи нода возвращает исходный `AUDIO` через выход `audio`. Downstream получает tensor до кодирования, без потерь MP3 и без повторного чтения файла.

Тип помечен deprecated. Его актуальная замена — `SaveAudioAdvanced` с `format: mp3` и тем же значением `quality`.

## Когда использовать и когда не использовать

Сохраняйте старую ноду только для воспроизведения уже проверенного workflow. В официальном bundle 0.1.42 она всё ещё широко встречается, поэтому её нельзя считать удалённой из 0.32.0.

Новый граф собирайте на `SaveAudioAdvanced`: отдельные `SaveAudioMP3`, `SaveAudioOpus` и `SaveAudio` уже отмечены устаревшими. Замена сохраняет формат, prefix и подключаемый AUDIO-выход.

MP3 подходит для совместимости и компактного прослушивания, но не для lossless-мастера или повторных циклов обработки. Для архива выберите FLAC; перед кодированием подготовьте mono/stereo и нужный уровень.

## Короткий рецепт подключения

1. Запишите `filename_prefix` и `quality` старой ноды.
2. Добавьте `SaveAudioAdvanced`, выберите `mp3`.
3. Перенесите `V0`, `128k` или `320k` во вложенный `quality`.
4. Переподключите вход и, если нужно, passthrough-выход.
5. Сравните созданные имена, число batch-файлов, sample rate и слышимый результат.

Fragment «Заменить SaveAudioMP3 на SaveAudioAdvanced с MP3 V0» повторяет самый частый официальный вариант: `audio/ComfyUI`, MP3, V0. Источник AUDIO остаётся внешним; fragment не исполнялся как полный граф.

## Входы, выходы и параметры

`audio` — обязательный `AUDIO`; `None` вызывает явный `ValueError`. `filename_prefix` имеет runtime-default `audio/ComfyUI`. `quality` — COMBO с default `V0` и вариантами `V0`, `128k`, `320k`.

В helper `V0` устанавливает `codec_context.qscale = 1`. Для `128k` и `320k` задаётся `bit_rate` 128000 или 320000. Это разные способы управления encoder; статья не приравнивает V0 к фиксированному bitrate.

Выход `audio` имеет тип `AUDIO`. Для `[B,C,T]` создаётся `B` файлов и возвращается тот же входной объект. Примечательная разница для прямых Python-вызовов: default параметра execute равен `128k`, тогда как runtime schema передаёт `V0`.

## Типовые связки

`VAEDecodeAudio → SaveAudioMP3` — характерная старая цепочка генерации звука. Другие официальные графы подключают выходы ElevenLabs API-нод к saver.

Эквивалентная актуальная цепочка: `источник AUDIO → SaveAudioAdvanced(format=mp3, quality=...)`. Выход новой ноды можно продолжить в `CreateVideo`, preview или другое AUDIO-преобразование.

Если требуется проверить кодированный MP3, загрузите созданный файл через `LoadAudio`. Passthrough не содержит MP3-артефакт: это исходный waveform.

## Практический пример

Полный census wheel 0.1.42 нашёл 19 `SaveAudioMP3` в 19 root-файлах и ни одной в 272 subgraph. Все 19 имеют mode `Always`, входящую связь `AUDIO → audio`, quality `V0` и неиспользуемый выход.

Десять нод используют prefix `audio/ComfyUI`; два — `audio/stable_audio_3`; ещё семь имеют собственные имена. Источники: десять `VAEDecodeAudio`, шесть ElevenLabs-ноды и три root-экземпляра официальных audio-subgraph.

В `audio_stable_audio_example.json`, workflow UUID `5fa61cc8-29d9-4deb-9f90-02d3c00b63b3`, `VAEDecodeAudio` № 12 подключён к `SaveAudioMP3` № 19 с `audio/ComfyUI` и V0. Изолированный прогон точного класса также создал V0, 128k и 320k MP3 без моделей; полный migration-fragment не запускался.

## Частые ошибки и способы проверки

**Считают официальное использование признаком актуальности.** Bundle сохраняет рабочие legacy-графы, но runtime всё равно ставит `deprecated: true`.

**После миграции забывают вложенный quality.** В `SaveAudioAdvanced` качество находится внутри dynamic format `mp3`, а не отдельным верхнеуровневым виджетом.

**Embedded docs говорят, что выхода нет.** Это расхождение: runtime и execute возвращают подключаемый `audio: AUDIO`. В официальных случаях он просто не соединён.

**Путают schema-default и Python-default.** UI 0.32.0 выбирает V0. Только прямой вызов `execute` без `quality` использует 128k.

**Сохраняют больше двух каналов.** Общий helper объявляет любое `C != 1` stereo и flatten-ит waveform. Сведите каналы до mono/stereo до MP3.

## Производительность и внутреннее поведение

Каждый batch-элемент переносится на CPU, превращается в NumPy, кодируется в памяти и затем записывается на диск. Чем длиннее waveform и выше batch, тем больше CPU-времени, памяти и файлов.

MP3 — lossy-кодек. Нода не нормализует пики, не меняет sample rate специально и не измеряет loudness. Возможность закодировать конкретную частоту зависит от `libmp3lame` в PyAV/FFmpeg окружении.

При включённых metadata helper добавляет prompt и `extra_pnginfo` в container metadata. `%batch_num%` в prefix различает элементы batch, а общий счётчик защищает предыдущие файлы от простого совпадения имени.

## Совместимость, изменения и устаревание

Материал закреплён на ComfyUI `0.32.0`, frontend `1.48.7`, runtime ID `SaveAudioMP3` и модуле `comfy_extras.nodes_audio`. Fingerprint: `sha256:6b831dbf8325bcd6a3471b857742220da599d19c30fa92e5a12d435962ca57d1`.

Runtime: `deprecated: true`, `output_node: true`, не experimental и не dev-only. Display name содержит `(DEPRECATED)`.

Автоматического `SaveAudioMP3 → SaveAudioAdvanced` в `/api/node_replacements` 0.32.0 нет. Рецепт показывает ручной перенос эквивалентных настроек и требует проверки результата.

## Связанные ноды и источники

`SaveAudioAdvanced` — актуальный saver. `VAEDecodeAudio` часто подаёт ему сгенерированный звук. `LoadAudio` перечитывает MP3 для контроля кодированного результата.

- [Класс `SaveAudioMP3`](https://github.com/Comfy-Org/ComfyUI/blob/c2bcbecd82ec5ae66594340b395c24ef0217b238/comfy_extras/nodes_audio.py#L188-L217)
- [MP3-ветка общего helper](https://github.com/Comfy-Org/ComfyUI/blob/c2bcbecd82ec5ae66594340b395c24ef0217b238/comfy_api/latest/_ui.py#L289-L374)
- [Официальный Stable Audio 1.0 workflow](https://github.com/Comfy-Org/workflow_templates/blob/cca1ea5ea4560108ecc2f44dee951f41ea433062/templates/audio_stable_audio_example.json)
- [Embedded docs 0.5.9 для `SaveAudioMP3`](https://github.com/Comfy-Org/embedded-docs/blob/1d258cf6e374d60d138a2bfcd273c7e11f750ef9/comfyui_embedded_docs/docs/SaveAudioMP3/en.md)

