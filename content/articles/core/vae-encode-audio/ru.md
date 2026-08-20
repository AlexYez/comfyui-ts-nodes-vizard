# VAEEncodeAudio: перевести waveform в audio LATENT

## Что делает нода

`VAEEncodeAudio` кодирует обычный `AUDIO` в `LATENT` через подключённый VAE. Если частота входа не совпадает с ожидаемой частотой модели, waveform сначала пересчитывается.

Входной звук имеет форму `[batch, channels, samples]`. Перед `vae.encode` нода переносит channels в конец и передаёт `[batch, samples, channels]`. Обратное внутреннее преобразование уже относится к реализации самого ComfyUI VAE.

Выходной словарь содержит только `samples`. Частота дискретизации, type и прочая metadata входа в LATENT не добавляются.

## Когда использовать и когда не использовать

Нода нужна для audio-to-audio editing, инициализации sampler исходным звуком и других графов, где модель работает с audio latent. Официальный ACE-Step music-to-music workflow использует именно такую схему.

Не подключайте произвольный image/video VAE только потому, что порт имеет общий тип `VAE`. Архитектура должна принимать waveform после перестановки осей. Несовместимость проявится ошибкой формы или некорректным latent.

Если исходный звук не должен влиять на генерацию, используйте соответствующую empty audio latent-ноду модели. Encode тратит память и время на сохранение структуры реального входа.

## Короткий рецепт подключения

1. Загрузите непустой `AUDIO`.
2. Получите audio VAE из совместимого checkpoint или loader.
3. Подайте оба объекта в `VAEEncodeAudio`.
4. Передайте `LATENT` в sampler или специализированную latent-операцию.
5. Для контроля декодируйте результат тем же семейством VAE и прослушайте.

Рецепт каталога оставляет только encode с двумя внешними портами. В официальном ACE-Step графе перед ним стоит `LoadAudio`, после него — `KSampler`.

## Входы, выходы и параметры

`audio: AUDIO` и `vae: VAE` обязательны, виджетов нет. Из AUDIO читаются `waveform` и `sample_rate`. Ожидаемая частота берётся из `vae.audio_sample_rate`; если атрибут отсутствует, используется `44100`.

При несовпадении вызывается `torchaudio.functional.resample(waveform, sample_rate, vae_sample_rate)`. При совпадении в encode идёт исходный waveform без resample-копии.

Если `audio is None`, нода явно выбрасывает `ValueError` с подсказкой, что исходное видео могло не иметь аудиодорожки. Выход — `LATENT` с единственным полем `samples`.

## Типовые связки

`LoadAudio → VAEEncodeAudio → KSampler` — доказанная ACE-Step связка. Conditioning и MODEL при этом должны относиться к той же audio-архитектуре.

После sampling результат декодируют через `VAEDecodeAudio` или tiled-вариант. Один и тот же VAE-семейство для encode/decode снижает риск несовместимой латентной шкалы и формы.

`LTXVAudioVAEEncode` наследует это поведение, но имеет отдельный ID и порт `audio_vae`, чтобы точнее обозначить LTX audio pipeline.

## Практический пример

В полном census 512 официальных JSON найден один `VAEEncodeAudio`: root-нода № 68 в `audio_ace_step_1_m2m_editing`. `LoadAudio` № 64 подаёт AUDIO, `CheckpointLoaderSimple` № 40 — VAE, а выход LATENT входит в `latent_image` `KSampler` № 52.

У encode нет widgets и mode равен Always. Других exact-примеров, включая subgraph, в wheel 0.1.42 нет.

Fake-VAE probe при входе `8000 Hz` и VAE `16000 Hz` получил tensor `[1, 16, 1]` вместо `[1, 1, 8]`, что подтверждает resample и `movedim(1, -1)`. Реальный ACE checkpoint и полный sampler не запускались.

## Частые ошибки и способы проверки

**На входе `None`.** Это частый случай у видео без audio track. Проверьте `GetVideoComponents` или источник до encode.

**Подключён не-audio VAE.** Общий socket не подтверждает архитектурную совместимость. Сверяйте loader и пример модели.

**Ожидают сохранения sample rate в LATENT.** Нода возвращает только `samples`. Downstream decode определяет частоту отдельно.

**Длительность немного меняется после resample.** Число отсчётов зависит от отношения частот и реализации resampler. Сравнивайте время, а не только T.

**Перепутаны оси.** Пользовательский VAE должен быть совместим с ComfyUI wrapper; напрямую поданный объект получает `[B,T,C]`.

## Производительность и внутреннее поведение

Resample читает весь waveform и при разных частотах создаёт новый tensor. После этого VAE encode обычно доминирует по памяти и времени; размер зависит от длительности, batch и модели.

ComfyUI VAE может самостоятельно перейти к tiled encode при OOM, но сама нода не показывает tile-параметры. Это отличается от явного tiled decoder.

Входная metadata не переносится. Нода не изменяет исходный AUDIO inplace и не добавляет noise mask или batch index к LATENT.

## Совместимость, изменения и устаревание

Проверено на ComfyUI `0.32.0`, frontend `1.48.7`, runtime ID `VAEEncodeAudio`, модуль `comfy_extras.nodes_audio`. Fingerprint: `sha256:79b40b34b464c25243174eaa37324cf92f2adef42842436da047fc2a8f54cd0b`.

Нода активна, не experimental и не deprecated. Python alias `encode = execute` не является runtime alias.

Embedded docs верно описывают автоматический resample и LATENT. Точная перестановка осей, default `44100`, samples-only output и None-ошибка проверены по исходнику и fake-VAE вызову.

## Связанные ноды и источники

`VAEDecodeAudio` выполняет обычный обратный decode, `VAEDecodeAudioTiled` — явный tiled. `LoadAudio` готовит waveform, а `VAE Loader` должен соответствовать аудиомодели.

- [Реализация `VAEEncodeAudio`](https://github.com/Comfy-Org/ComfyUI/blob/c2bcbecd82ec5ae66594340b395c24ef0217b238/comfy_extras/nodes_audio.py#L66-L96)
- [Официальный ACE-Step editing template](https://github.com/Comfy-Org/workflow_templates/blob/cca1ea5ea4560108ecc2f44dee951f41ea433062/templates/audio_ace_step_1_m2m_editing.json)
- [Embedded docs 0.5.9](https://github.com/Comfy-Org/embedded-docs/blob/1d258cf6e374d60d138a2bfcd273c7e11f750ef9/comfyui_embedded_docs/docs/VAEEncodeAudio/en.md)
