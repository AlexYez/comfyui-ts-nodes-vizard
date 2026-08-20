# LTXAVTextEncoderLoader: собрать LTX audio/video CLIP из двух файлов

## Что делает нода

`LTXAVTextEncoderLoader` создаёт объект `CLIP` для LTX audio/video pipeline из двух файлов: отдельного text encoder и выбранного LTX checkpoint. Здесь `CLIP` — тип интерфейса ComfyUI, а не утверждение, что внутри находится классическая CLIP-модель.

Нода разрешает пути из каталогов `text_encoders` и `checkpoints`, задаёт `CLIPType.LTXV` и передаёт оба файла в `comfy.sd.load_clip` именно в порядке `[text_encoder, checkpoint]`. Также она сообщает loader путь к каталогу embeddings.

Описание schema подсказывает рецепт `ltxav: gemma 3 12B or matching gemma 4 model`. Это ориентир по семейству, но совместимость пары определяется содержимым весов, а не совпадением имён.

## Когда использовать и когда не использовать

Нода нужна для LTX 2.x графов, которым требуется связанный с checkpoint текстовый encoder. Официальные шаблоны используют её выход для положительного и отрицательного `CLIPTextEncode`, иногда пропуская CLIP через `LoraLoader`.

Не подставляйте произвольный Gemma и произвольный LTX checkpoint. Loader объединяет state dict двух файлов под конкретным `CLIPType.LTXV`; несовпадение версии, скрытой размерности или конфигурации может проявиться при загрузке либо при первом encode.

Обычный `CLIPLoader` подходит для архитектур, которые описываются одним text-encoder файлом и стандартным выбором типа. Он не заменяет двухфайловый LTXAV-контракт автоматически.

## Короткий рецепт подключения

1. Поместите text encoder в `models/text_encoders`, а совместимый LTX checkpoint — в `models/checkpoints`.
2. Выберите доказанную официальным шаблоном пару в `text_encoder` и `ckpt_name`.
3. Оставьте `device=default`, если нет причины держать encoder на CPU.
4. Подайте `CLIP` в один или два `CLIPTextEncode`.
5. Проверьте короткий prompt до запуска длинного video workflow.

Рецепт использует пару `gemma_3_12B_it_fp4_mixed.safetensors` и `ltx-2.3-22b-dev-fp8.safetensors`, сохранённую в официальном image-and-speech-to-video template. Файлы и полный encode не входят в проверку каталога.

## Входы, выходы и параметры

`text_encoder` — динамический combo из `text_encoders`. `ckpt_name` — динамический combo из `checkpoints`. Чистая установка без моделей даёт пустые options; эти значения не участвуют в schema fingerprint.

`device` принимает только `default` или `cpu` и помечен как advanced. В режиме `cpu` нода одновременно задаёт `load_device` и `offload_device` равными `torch.device("cpu")`. В режиме `default` словарь `model_options` остаётся пустым, а размещение выбирает ComfyUI.

Выход `CLIP` подключается к обычным prompt-encoder нодам. В schema нет отдельного audio-conditioning выхода: преобразование текста выполняется downstream.

## Типовые связки

`LTXAVTextEncoderLoader → CLIPTextEncode` — основная связь. Обычно один выход разветвляется на positive и negative prompt, поэтому модель загружается один раз.

В официальном LTX 2.3 subgraph выход также подключён к выключенному `LoraLoader`. Это показывает допустимость CLIP-LoRA ветви, но сохранённый mode `Bypass` не доказывает пользу конкретной LoRA для каждого графа.

`LTXAVTextEncoderLoader` часто соседствует с `LTXVAudioVAELoader`: первый готовит текстовое conditioning, второй — кодек аудио. Они читают один и тот же LTX checkpoint с разными целями.

## Практический пример

Полный recursive census 512 официальных JSON нашёл 18 экземпляров ноды в 16 файлах, все внутри subgraph. Семнадцать имеют mode `Always`, один — `Bypass`.

Пять раз сохранена пара `gemma_3_12B_it_fp4_mixed.safetensors` + `ltx-2.3-22b-dev-fp8.safetensors`; по четыре раза — пары с LTX 2.3 distilled, LTX 2 19B dev FP8 и LTX 2 19B distilled. Ещё один старый case использует полноточные `gemma_3_12B_it.safetensors` и `ltx-2-19b-dev.safetensors`.

Во всех 18 случаях `device` равен `default`. Всего census зафиксировал 32 прямые связи в `CLIPTextEncode` и шесть — в `LoraLoader`, потому что один loader часто обслуживает несколько prompt-ветвей.

## Частые ошибки и проверка

**Один из combo пуст.** Проверьте разные каталоги: text encoder должен лежать в `text_encoders`, checkpoint — в `checkpoints`. Один файл не появляется автоматически в обоих списках.

**Ошибка формы или неизвестной архитектуры.** Сверьте пару с одним официальным workflow. Совпадающие слова `Gemma` и `LTX` в именах ещё не гарантируют согласованную конфигурацию.

**CPU выбран, но граф очень медленный.** Этот режим фиксирует и load, и offload device на CPU. Для большого encoder это снимает нагрузку с VRAM ценой вычислений и памяти системы.

**Ожидался audio embedding.** Выход имеет тип `CLIP`; он должен пройти через text encode. Для waveform существует отдельное семейство `AudioEncoderLoader` и `AudioEncoderEncode`.

## Производительность и внутреннее поведение

`load_clip` читает оба checkpoint с `safe_load=True` и `return_metadata=True`, затем распознаёт text-encoder state dicts как `CLIPType.LTXV`. Два больших файла означают две операции чтения и заметное потребление памяти при инициализации.

В `default` ComfyUI самостоятельно выбирает load/offload device и dtype. В `cpu` нода передаёт только устройство; она не меняет dtype и не включает отдельную quantization. Фактическая поддержка FP4/FP8 зависит от формата весов и loader.

Каталог embeddings передаётся в loader, поэтому textual inversion lookup остаётся частью общего CLIP-интерфейса. Наличие каталога не означает, что всякий embedding совместим с конкретным LTX/Gemma encoder.

## Совместимость, изменения и устаревание

Проверено на ComfyUI `0.32.0`, frontend `1.48.7`, runtime ID `LTXAVTextEncoderLoader`, модуль `comfy_extras.nodes_lt_audio`. Fingerprint: `sha256:47204f52171b84be9098b9a1c0a87ae7265a40e94432e3425d52466e0d189774`.

Нода активна, не experimental, не deprecated, не dev-only и не API node. Formal replacement отсутствует. Dynamic combo values исключены из fingerprint, поэтому локальный набор моделей не считается изменением схемы.

Embedded docs 0.5.9 верно описывают пару файлов и `cpu`, но называют результат специализированным encoder для «audio generation» слишком узко: официальные связи ведут и в video prompt branches. Точные аргументы loader подтверждены кодом.

## Связанные ноды и источники

`CLIPTextEncode` превращает выход в conditioning. `LTXVAudioVAELoader` читает аудиокодек из того же checkpoint. `AudioEncoderLoader` работает уже с waveform encoder и выдаёт другой тип.

- [Реализация `LTXAVTextEncoderLoader`](https://github.com/Comfy-Org/ComfyUI/blob/c2bcbecd82ec5ae66594340b395c24ef0217b238/comfy_extras/nodes_lt_audio.py#L169-L211)
- [Официальный image-and-speech-to-video template](https://github.com/Comfy-Org/workflow_templates/blob/cca1ea5ea4560108ecc2f44dee951f41ea433062/templates/template_image_speech_to_video.json)
- [Embedded docs 0.5.9](https://github.com/Comfy-Org/embedded-docs/blob/1d258cf6e374d60d138a2bfcd273c7e11f750ef9/comfyui_embedded_docs/docs/LTXAVTextEncoderLoader/en.md)
