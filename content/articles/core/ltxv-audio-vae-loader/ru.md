# LTXVAudioVAELoader: загрузить audio VAE из LTX checkpoint

## Что делает нода

`LTXVAudioVAELoader` извлекает из LTX checkpoint аудиокодек: autoencoder вместе с vocoder. На выходе появляется объект общего типа `VAE`, который подходит к портам `audio_vae` у LTX-аудио нод. Сам loader не кодирует waveform и не создаёт latent.

Реализация сначала получает полный путь из каталога `checkpoints`, затем читает state dict и metadata. После этого она оставляет только ключи с префиксами `audio_vae.` и `vocoder.`, переименовывая первую ветвь в `autoencoder.`. Остальные веса checkpoint отбрасываются до создания `comfy.sd.VAE`.

В конце вызывается `throw_exception_if_invalid()`. Поэтому неподходящий файл не должен тихо превратиться в объект с пустой моделью: выполнение останавливается на проверке распознанной архитектуры.

## Когда использовать и когда не использовать

Используйте эту ноду в LTX 2.x графах, где один и тот же checkpoint содержит диффузионную модель, текстовую часть и audio VAE. Официальные шаблоны передают её выход в `LTXVAudioVAEDecode`, `LTXVAudioVAEEncode`, `LTXVEmptyLatentAudio` и `LTXVReferenceAudio`.

Не выбирайте checkpoint только по расширению `.safetensors`. Порт `VAE` проверяет лишь интерфейс объекта, а loader ожидает внутри конкретные ветви LTX audio. Обычный image VAE, отдельный diffusion model без vocoder или файл другой версии могут не распознаться либо оказаться несовместимыми с downstream latent.

`VAELoader` удобнее для самостоятельного VAE-файла из каталога `vae`. Здесь источник другой: поле `ckpt_name` смотрит именно в `checkpoints`, а из большого файла выбираются LTX-аудио ключи.

## Короткий рецепт подключения

1. Поместите совместимый LTX 2.x checkpoint в `models/checkpoints`.
2. Выберите его в `ckpt_name`.
3. Подайте `Audio VAE` в `LTXVAudioVAEEncode.audio_vae` и `LTXVAudioVAEDecode.audio_vae`.
4. Для пустого LTX audio latent можно ответвить тот же выход в `LTXVEmptyLatentAudio.audio_vae`.
5. Не смешивайте encode и decode с разными audio VAE без отдельной проверки форм и шкалы latent.

Рецепт каталога оставляет AUDIO и LATENT внешними входами, а loader связывает с двумя направлениями преобразования. Это структурированный fragment: checkpoint с весами в пакет не входит, полного запуска LTX-модели не было.

## Входы, выходы и параметры

`ckpt_name` — динамический список файлов из каталога `checkpoints`. Чистый runtime snapshot содержит пустой список: локальные имена моделей намеренно не входят в schema fingerprint. Добавление или удаление checkpoint меняет combo, но не контракт ноды.

Единственный выход называется `Audio VAE` и имеет тип `VAE`. Это wrapper, внутри которого ComfyUI хранит autoencoder, vocoder, параметры частоты и сведения о латентной форме. Набор доступных атрибутов определяется распознанной архитектурой файла.

В ноде нет выбора device, dtype, quantization или offload. Эти решения принимает общий VAE-loader и подсистема управления памятью ComfyUI по данным checkpoint и текущей конфигурации.

## Типовые связки

`LTXVAudioVAELoader → LTXVAudioVAEEncode` переводит готовый `AUDIO` в LTX audio latent. Обратная ветвь `LTXVAudioVAELoader → LTXVAudioVAEDecode` восстанавливает waveform после sampling или разделения audio/video latent.

`LTXVAudioVAELoader → LTXVEmptyLatentAudio` использует конфигурацию модели для правильного числа каналов, frequency bins и длины latent. Такая связь надёжнее, чем вручную угадывать форму тензора.

В официальном image-and-speech-to-video subgraph один loader одновременно подключён к encode и decode. Это не две независимые загрузки: обе ноды получают один объект VAE и тем самым работают в одной латентной системе координат.

## Практический пример

Полный просмотр wheel `comfyui-workflow-templates-json 0.1.42` нашёл 18 экземпляров `LTXVAudioVAELoader` в 16 файлах. Все находятся в subgraph: 17 имеют mode `Always`, один сохранён в mode `Bypass`.

В `template_image_speech_to_video` нода №335 выбирает `ltx-2.3-22b-dev-fp8.safetensors`. Её VAE идёт одновременно в `LTXVAudioVAEDecode` №303 и `LTXVAudioVAEEncode` №328. В других проверенных шаблонах встречаются `ltx-2-19b-dev-fp8.safetensors`, `ltx-2-19b-distilled.safetensors` и варианты LTX 2.3.

Эти имена доказывают конкретные официальные пресеты, но не являются универсальным списком совместимости. Файлы могут отсутствовать локально, а будущий checkpoint с похожим названием обязан пройти фактическое распознавание.

## Частые ошибки и проверка

**Combo пуст.** Проверьте каталог `models/checkpoints`, поддерживаемое расширение и обновите список моделей. В чистой установке без весов пустой список нормален.

**Файл загружается, но VAE объявлен недействительным.** Вероятно, в state dict нет ожидаемых `audio_vae.` или `vocoder.` ключей. Сверьте модель с официальным workflow и источником загрузки.

**Encode либо decode падает по форме.** Убедитесь, что все LTX-аудио ноды получили один совместимый VAE, а audio latent создан тем же семейством модели. Общий socket `VAE` не подтверждает архитектурное соответствие заранее.

**Ожидалась загрузка только маленького VAE-файла.** Нода читает выбранный checkpoint, а фильтрация происходит уже после получения state dict. Размер дисковой операции определяется полным файлом.

## Производительность и внутреннее поведение

`load_torch_file(..., return_metadata=True)` загружает state dict на CPU. Для safetensors ComfyUI использует safe reader и mmap-механизм в зависимости от настроек; для других поддержанных форматов применяется `torch.load(..., weights_only=True)`.

`state_dict_prefix_replace(..., filter_keys=True)` создаёт новый словарь только из двух выбранных ветвей. Префикс `audio_vae.` меняется на `autoencoder.`, а `vocoder.` остаётся тем же. Ключи diffusion model и текстового encoder не передаются конструктору VAE.

Загрузка большого checkpoint остаётся дорогой по диску и CPU, даже если итоговый объект содержит лишь аудиочасть. Последующее размещение весов на ускорителе контролирует VAE wrapper; сама нода не вызывает sampling и не декодирует звук.

## Совместимость, изменения и устаревание

Статья сверена с ComfyUI `0.32.0`, frontend `1.48.7`, runtime ID `LTXVAudioVAELoader` и модулем `comfy_extras.nodes_lt_audio`. Fingerprint: `sha256:5483348324384b5122eb55fe218919220931a4e52fe63ba753dca390e3dcce71`.

Нода активна, не experimental, не deprecated, не dev-only и не API node. Formal Node Replacement для неё отсутствует. Имена checkpoint являются локальными динамическими данными и исключаются из структурного fingerprint.

Embedded docs 0.5.9 верно называют источник и выход, но не объясняют фильтрацию state dict, точные префиксы, проверку invalid VAE и цену чтения полного checkpoint. Эти детали взяты из закреплённого исходника.

## Связанные ноды и источники

`LTXVAudioVAEEncode` кодирует AUDIO, `LTXVAudioVAEDecode` декодирует audio latent, а `LTXVEmptyLatentAudio` получает форму из конфигурации того же VAE. `VAELoader` относится к другому месту хранения и не является автоматической заменой.

- [Реализация `LTXVAudioVAELoader`](https://github.com/Comfy-Org/ComfyUI/blob/c2bcbecd82ec5ae66594340b395c24ef0217b238/comfy_extras/nodes_lt_audio.py#L9-L34)
- [Официальный image-and-speech-to-video template](https://github.com/Comfy-Org/workflow_templates/blob/cca1ea5ea4560108ecc2f44dee951f41ea433062/templates/template_image_speech_to_video.json)
- [Embedded docs 0.5.9](https://github.com/Comfy-Org/embedded-docs/blob/1d258cf6e374d60d138a2bfcd273c7e11f750ef9/comfyui_embedded_docs/docs/LTXVAudioVAELoader/en.md)
