# LTXVConditioning: добавить частоту кадров в conditioning

## Что делает нода

`LTXVConditioning` записывает `frame_rate` в metadata каждого элемента positive и negative conditioning. Она не пересчитывает текстовые embeddings и не меняет их численные значения.

Для каждого entry создаётся новый двухэлементный контейнер `[tensor, metadata_copy]`. Тензор остаётся тем же объектом, metadata копируется неглубоко, а поле `frame_rate` добавляется или перезаписывается.

Одинаковая частота попадает в обе ветви. Это позволяет LTXV-модели интерпретировать временную динамику согласованно, независимо от различий между positive и negative prompt.

## Когда использовать и когда не использовать

Используйте ноду в LTXV-графах перед `CFGGuider`, `SamplerCustom` или специализированными guide-нодами, когда модель ожидает частоту кадров в conditioning metadata.

Ставьте её после нод, которые добавляют свой conditioning-контекст, если их данные нужно сохранить. `conditioning_set_values` оставляет остальные ключи, поэтому `ref_audio`, hook metadata и текстовые поля не удаляются.

Не путайте `frame_rate` с параметром video encoder или `CreateVideo`. Эта нода сообщает значение модели, но не меняет FPS готового файла и не синхронизирует его автоматически с другими виджетами графа.

## Короткий рецепт подключения

1. Получите positive и negative от `CLIPTextEncode`, `LTXVImgToVideo` или другой conditioning-ноды.
2. Подайте одинаковую фактическую частоту видео в `frame_rate`.
3. Соедините оба выхода с guider или sampler-ветвью.
4. Используйте то же число в `CreateVideo` и расчётах аудиолатента, если граф содержит эти стадии.
5. При изменении FPS обновите все связанные виджеты, а не только эту ноду.

Рецепт Wizard сохраняет официальный legacy участок `LTXVImgToVideo → LTXVConditioning` с `25 fps`. Полный sampler остаётся за пределами fragment.

## Входы, выходы и параметры

`positive` и `negative` — обязательные входы `CONDITIONING`. Они могут содержать несколько entries; значение записывается в metadata каждого.

`frame_rate` — `FLOAT` от `0.0` до `1000.0`, default `25.0`, шаг `0.01`. Ноль формально разрешён runtime-схемой, хотя обычный видеопоток с нулевой частотой не имеет практической длительности.

Выходы называются `positive` и `negative` и сохраняют тип `CONDITIONING`. Число entries и tensor identities не меняются.

Если входное metadata уже содержит `frame_rate`, новое значение заменяет старое. Вложенные списки и словари внутри metadata не клонируются.

## Типовые связки

В 39 официальных соединениях conditioning приходит непосредственно от `CLIPTextEncode`. Ещё по одной positive/negative паре приходит от `LTXVImgToVideo` и `LTXVReferenceAudio`; три negative-входа используют `ConditioningZeroOut`.

Выходы 22 раза подключены к `CFGGuider`, восемь — к `LTXVDualCFGGuider`, по 18 — к `LTXVCropGuides` и `LTXVAddGuide`. Четыре связи идут прямо в `SamplerCustom`: по одной positive/negative паре в двух legacy root-графах.

Значение FPS часто приходит от `ComfyMathExpression` или `PrimitiveFloat`. Это особенно полезно в subgraph, где один внешний параметр управляет conditioning, длительностью аудио и video output.

## Практический пример

Полный census 0.1.42 нашёл 23 экземпляра в 21 файле: два root и 21 subgraph. Двадцать две ноды имеют mode `Always`, одна сохранена в mode `Bypass`.

Виджет равен `25` у 16 экземпляров и `24` у семи. Root `ltxv_image_to_video` использует `25`: positive/negative от `LTXVImgToVideo` №77 входят в `LTXVConditioning` №69, затем выходы поступают в `SamplerCustom` №72.

В `video_ltx2_3_id_lora` значение равно `24`. Перед нодой `LTXVReferenceAudio` добавляет voice reference, после неё `CFGGuider` получает оба conditioning с ref-токенами и frame rate.

## Частые ошибки и проверка

**Скорость готового видео не изменилась.** Нода не управляет контейнером. Поменяйте FPS в `CreateVideo` или saver отдельно.

**Audio и video разошлись по длительности.** Проверьте, что то же значение использовано при расчёте `LTXVEmptyLatentAudio` и во всех duration-узлах.

**Старое значение сохранилось.** Найдите downstream-ноду, которая позже снова пишет `frame_rate`; последняя запись в цепочке победит.

**Ожидается изменение prompt.** Текстовые тензоры не пересчитываются. Для нового prompt нужен повторный `CLIPTextEncode`.

## Производительность и внутреннее поведение

Операция проходит по спискам conditioning и копирует только их внешние metadata-словари. Tensor storage, device и dtype не меняются; model inference не запускается.

Стоимость линейна по числу entries и обычно мала. Вложенные metadata остаются общими ссылками, поэтому downstream-код, изменяющий их на месте, может затронуть другие ветви.

Positive и negative обрабатываются двумя отдельными вызовами. Между ними нет объединения, проверки числа entries или сравнения metadata.

## Совместимость, изменения и устаревание

Статья сверена с ComfyUI `0.32.0`, frontend `1.48.7`, runtime ID `LTXVConditioning` и модулем `comfy_extras.nodes_lt`. Fingerprint: `sha256:047867640f999858426cf2161d4fa043f962898d6c96437fe1c4ed43f3d6b65f`.

Нода активна, не experimental, не deprecated, не dev-only и не API node. Formal replacement отсутствует. Диапазон включает `0.0`, что отражено как runtime-факт, а не рекомендация.

Embedded docs 0.5.9 достаточно точно передают основное действие, но не объясняют shallow copy, overwrite существующего поля и отсутствие связи с FPS output-контейнера.

## Связанные ноды и источники

`CLIPTextEncode` создаёт исходное conditioning, `LTXVImgToVideo` и `LTXVReferenceAudio` добавляют свой контекст. `CFGGuider`, `LTXVDualCFGGuider`, `LTXVAddGuide` и `LTXVCropGuides` используют результат дальше.

- [Реализация `LTXVConditioning`](https://github.com/Comfy-Org/ComfyUI/blob/c2bcbecd82ec5ae66594340b395c24ef0217b238/comfy_extras/nodes_lt.py#L543-L564)
- [Копирование conditioning metadata](https://github.com/Comfy-Org/ComfyUI/blob/c2bcbecd82ec5ae66594340b395c24ef0217b238/node_helpers.py#L9-L23)
- [Официальный legacy image-to-video template](https://github.com/Comfy-Org/workflow_templates/blob/cca1ea5ea4560108ecc2f44dee951f41ea433062/templates/ltxv_image_to_video.json)
- [Embedded docs 0.5.9](https://github.com/Comfy-Org/embedded-docs/blob/1d258cf6e374d60d138a2bfcd273c7e11f750ef9/comfyui_embedded_docs/docs/LTXVConditioning/en.md)
