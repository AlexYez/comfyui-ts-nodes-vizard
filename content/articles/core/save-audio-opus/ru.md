# SaveAudioOpus: устаревший экспорт Opus

## Что делает нода

`SaveAudioOpus` кодирует входной `AUDIO` через `libopus` и сохраняет `.opus` в каталоге `output`. В schema доступны bitrate-варианты 64k, 96k, 128k, 192k и 320k.

Перед кодированием helper при необходимости меняет sample rate на один из поддерживаемых Opus. Каждый batch-элемент становится отдельным файлом, а подключаемый выход возвращает исходный AUDIO без этого resample.

Нода deprecated. В новом графе используйте `SaveAudioAdvanced` с `format: opus` и тем же `quality`.

## Когда использовать и когда не использовать

Сохраняйте `SaveAudioOpus` в старом графе только ради совместимости. Все четыре её вхождения в официальном bundle 0.1.42 отключены и не подключены, поэтому набор не подтверждает активную production-топологию.

Opus уместен для компактной доставки речи или музыки, когда lossless не нужен. Для мастер-файла используйте FLAC. Для нового Opus-экспорта выбирайте `SaveAudioAdvanced`.

Перед сохранением сведите материал до mono/stereo и проверьте bitrate для числа каналов. Закреплённый encoder отвергает mono 320k, хотя UI предлагает этот пункт; stereo 320k проходит.

## Короткий рецепт подключения

1. Запишите prefix и quality старой ноды.
2. Добавьте `SaveAudioAdvanced` и выберите `opus`.
3. Перенесите quality; типовой default — `128k`.
4. Переподключите AUDIO-вход и passthrough-выход.
5. Проверьте sample rate сохранённого файла и прослушайте результат.

Fragment «Заменить SaveAudioOpus на SaveAudioAdvanced с Opus 128k» использует безопасный типовой режим из runtime schema и официальных неактивных placeholders. Источник остаётся внешним; fragment не запускался end-to-end.

## Входы, выходы и параметры

`audio` — обязательный `AUDIO`; при `None` класс выдаёт `ValueError`. `filename_prefix` по умолчанию — `audio/ComfyUI`. `quality` имеет runtime-default `128k` и пять перечисленных вариантов.

Helper напрямую ставит bitrate 64000, 96000, 128000, 192000 или 320000. Поддерживаемые sample rate: 8, 12, 16, 24 и 48 кГц. Частота выше 48 понижается до 48; другая меньшая частота повышается до следующей поддерживаемой.

Выход `audio` передаёт исходный объект. Для прямых Python-вызовов без quality в execute остался default `V3`, которого нет в schema и bitrate mapping; обычный UI всегда передаёт одно из пяти актуальных значений.

## Типовые связки

Legacy-связка выглядит как `источник AUDIO → SaveAudioOpus`. Актуальный эквивалент — `источник → SaveAudioAdvanced(format=opus, quality=128k)`.

Выход saver можно направить в `CreateVideo` или другую AUDIO-ноду, но она получит исходный sample rate. Если важно работать именно с resampled Opus, перечитайте файл через `LoadAudio`.

`PreviewAudio` перед экспортом поможет услышать вход, но создаёт FLAC в `temp`, а не проверяет результат Opus-кодирования.

## Практический пример

Полный census 512 JSON нашёл четыре `SaveAudioOpus`: `api_elevenlabs_speech_to_speech`, `text_to_dialogue`, `text_to_sound_effects` и `text_to_speech`. Все находятся в root, имеют mode `Bypass`, widgets `audio/ComfyUI` и `128k`, не имеют входящих или исходящих связей.

Эти записи — сохранённые отключённые альтернативы рядом с активными `SaveAudioMP3`, а не доказательство выполненного Opus-экспорта. В 272 subgraph целевой тип отсутствует.

Изолированный прогон точного класса проверил 64k–192k на mono и 320k на stereo; вход 44,1 кГц записался как 48 кГц. Mono 320k в закреплённой сборке `libopus` вернул `Invalid argument`. Полный migration-fragment и субъективное прослушивание не выполнялись.

## Частые ошибки и способы проверки

**Принимают mode Bypass за рабочий пример.** Все четыре официальных placeholders отключены и отсоединены. Они подтверждают сериализацию, но не выполнение.

**Ожидают сохранения 44,1 кГц.** Opus-ветка пересчитывает её к 48 кГц. Проверьте stream metadata готового файла.

**Выбирают mono 320k и получают encoder error.** В закреплённом окружении используйте 192k или ниже для одного канала. Поведение может зависеть от сборки encoder, поэтому тестируйте целевую установку.

**Downstream получает другую частоту.** Passthrough не отражает Opus-resample: он остаётся исходным AUDIO.

**Полагаются на embedded docs об отсутствии выхода.** Runtime 0.32.0 объявляет `audio: AUDIO`; docs 0.5.9 это пропускают.

## Производительность и внутреннее поведение

Если sample rate не поддерживается, `torchaudio.functional.resample` создаёт новый tensor на CPU до кодирования. Затем каждый batch-элемент кодируется в памяти и записывается отдельным файлом.

Resample увеличивает число отсчётов, например при 44,1→48 кГц. Стоимость растёт с длительностью, каналами и batch. Passthrough не использует этот новый tensor и не несёт затрат повторного чтения.

Writer выбирает mono только при `C == 1`, иначе stereo. Пики не нормализуются. Prompt и `extra_pnginfo` могут попасть в container metadata при включённой записи metadata.

## Совместимость, изменения и устаревание

Статья закреплена на ComfyUI `0.32.0`, frontend `1.48.7`, runtime ID `SaveAudioOpus`, модуле `comfy_extras.nodes_audio`. Fingerprint: `sha256:f31967e146ded9377a0bb5457336f32d8fa0e7e6ec354377b145d96f25ab4302`.

Runtime отмечает ноду `deprecated: true`, `output_node: true`; experimental и dev-only выключены. Display name содержит `(DEPRECATED)`.

В `/api/node_replacements` нет автоматической миграции на `SaveAudioAdvanced`. Каталог связывает замену семантически и предлагает fragment для ручного переноса.

## Связанные ноды и источники

`SaveAudioAdvanced` сохраняет Opus актуальным способом. `LoadAudio` проверяет закодированный файл, `PreviewAudio` — исходный сигнал до экспорта.

- [Класс `SaveAudioOpus`](https://github.com/Comfy-Org/ComfyUI/blob/c2bcbecd82ec5ae66594340b395c24ef0217b238/comfy_extras/nodes_audio.py#L220-L248)
- [Opus-rate и bitrate в общем helper](https://github.com/Comfy-Org/ComfyUI/blob/c2bcbecd82ec5ae66594340b395c24ef0217b238/comfy_api/latest/_ui.py#L260-L374)
- [Официальный отключённый пример ElevenLabs](https://github.com/Comfy-Org/workflow_templates/blob/cca1ea5ea4560108ecc2f44dee951f41ea433062/templates/api_elevenlabs_speech_to_speech.json)
- [Embedded docs 0.5.9 для `SaveAudioOpus`](https://github.com/Comfy-Org/embedded-docs/blob/1d258cf6e374d60d138a2bfcd273c7e11f750ef9/comfyui_embedded_docs/docs/SaveAudioOpus/en.md)

