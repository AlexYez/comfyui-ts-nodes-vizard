# unCLIPCheckpointLoader: разобрать unCLIP-checkpoint

## Что делает нода

`unCLIPCheckpointLoader` передаёт выбранный файл общему checkpoint-детектору ComfyUI и просит извлечь четыре компонента: `MODEL`, `CLIP`, `VAE` и `CLIP_VISION`. Порядок выходов закреплён в классе и совпадает с tuple, который возвращает `load_checkpoint_guess_config`.

Название ноды не включает отдельную проверку «это unCLIP». Метод всегда вызывает общий загрузчик с `output_vae=True`, `output_clip=True` и `output_clipvision=True`. Дальше всё решают структура checkpoint и найденная конфигурация модели.

Канонические unCLIP-конфигурации в этом commit — `SD21UnclipL` и `SD21UnclipH`: обе используют SD 2.1, встроенный vision-префикс и noise augmentation, но различаются размером ADM. Другие конфигурации тоже могут иметь vision-префикс и дать четвёртый выход, однако от этого они не становятся SD 2.1 unCLIP. Произвольный checkpoint не становится совместимым только потому, что его можно выбрать в `ckpt_name`.

## Когда использовать и когда не использовать

Используйте эту ноду для полного checkpoint, который подтверждён как совместимый unCLIP bundle и содержит нужные diffusion, text, VAE и vision-веса. Тогда один файл снабжает sampler моделью, текстовый prompt — CLIP, decode — VAE, а image prompt — CLIP Vision.

Не используйте её как универсальный `CheckpointLoaderSimple` с «дополнительным полезным портом». Vision-компонент создаётся лишь при наличии подходящего `clip_vision_prefix`; текстовый CLIP также может отсутствовать. Типизированные порты описывают ожидаемый интерфейс ноды, а не гарантируют содержимое любого файла.

Для SDXL Revision официальный template 0.1.42 использует `CheckpointLoaderSimple` и отдельный `CLIPVisionLoader`, а не `unCLIPCheckpointLoader`. В model base у SDXL есть отдельная ветвь, которая умеет потреблять `unclip_conditioning`, но это не означает, что любой SDXL checkpoint содержит встроенный CLIP Vision. Поддержка metadata на стороне модели и состав checkpoint — разные контракты.

## Короткий рецепт подключения

1. Выберите проверенный SD 2.1 unCLIP checkpoint из `models/checkpoints`.
2. Подключите `MODEL` к sampler, `CLIP` к текстовым encode, `VAE` к decode.
3. Подайте `CLIP_VISION` в `CLIPVisionEncode`, а туда же — референсное `IMAGE`.
4. Соедините `CLIP_VISION_OUTPUT` с `unCLIPConditioning`.
5. Передайте базовое positive `CONDITIONING` в ту же `unCLIPConditioning`, затем в sampler.

Fragment «Разобрать unCLIP-checkpoint и добавить референс» показывает центральную ветвь загрузчик → vision encode → unCLIP conditioning. Имя checkpoint оставлено как осознанный выбор установленного совместимого файла. Fragment прошёл проверку схемы и runtime, но ни один checkpoint не загружался.

## Входы, выходы и параметры

`ckpt_name` — обязательный динамический список файлов группы `checkpoints`. В чистом runtime snapshot он пуст, поэтому имена локальных моделей не входят в fingerprint.

Выходы строго упорядочены: `MODEL`, `CLIP`, `VAE`, `CLIP_VISION`; ни один не является list-output. Внутренний общий загрузчик сначала определяет model config. `CLIP_VISION` строится только когда config задаёт `clip_vision_prefix`. `CLIP` создаётся только при найденной text-encoder цели и наличии соответствующих весов.

Аргументы Python-метода `output_vae` и `output_clip` не являются входами `/object_info`. В реализации ноды они игнорируются при dispatch: вниз всегда передаются значения `True`.

## Типовые связки

`MODEL → KSampler`, `CLIP → CLIPTextEncode`, `VAE → VAEDecode` повторяют обычную checkpoint-связку. Дополнительная ветвь `CLIP_VISION → CLIPVisionEncode → unCLIPConditioning` добавляет image embedding в positive conditioning.

Одну `CLIP_VISION` можно направить в несколько encode для нескольких референсов. Несколько `unCLIPConditioning` последовательно добавляют записи metadata; модель при sampling объединяет embeddings с их strength и noise augmentation.

Не смешивайте автоматически `CLIP_VISION` из одного семейства с diffusion model из другого. Даже если общий загрузчик сумел построить оба объекта, размер image embedding и ожидаемый ADM-контракт должны совпасть с принимающей моделью.

## Практический пример

В полном census `comfyui-workflow-templates-json 0.1.42` проверены 512 JSON, root nodes и 272 subgraphs. `unCLIPCheckpointLoader` не найден ни разу. Поэтому у закреплённого набора нет официальных widget values или реально сериализованной topology для этой ноды.

Ближайший официальный пример — `sdxl_revision_text_prompts`, UUID `22fbfe6b-e7d7-4193-8409-8599b5dce771`. Там `CheckpointLoaderSimple(sd_xl_base_1.0.safetensors)` даёт MODEL/CLIP/VAE, а отдельный `CLIPVisionLoader(clip_vision_g.safetensors)` питает два image encode. Две `unCLIPConditioning` со значениями `[0.75, 0]` соединены последовательно.

Изолированная проба закреплённого класса подтвердила путь `checkpoints`, передачу каталога embeddings, три принудительных флага `True` и возврат четырёх объектов без перестановки. Она проверяет вызов общего загрузчика, но не определение модели и не совместимость весов.

## Частые ошибки и способы проверки

**Выбирают обычный checkpoint.** Проверьте model family и состав файла. Отсутствующий vision-префикс оставляет `CLIP_VISION` пустым на внутреннем уровне.

**Считают четыре порта гарантией четырёх моделей.** Общий loader инициализирует компоненты условно. В diffusion-only fallback текстовый и vision-компоненты равны `None`, а VAE создаётся как объект, который должен сообщить ошибку при использовании.

**Подключают image embedding к несовместимой модели.** Сверьте SD 2.1 unCLIP L/H, размер ADM и источник vision-весов. Имя файла не является проверкой.

**Пытаются отключить CLIP или VAE параметрами API.** У ноды таких runtime-входов нет; её метод всегда запрашивает оба компонента.

**Путают с отдельным vision-loader.** Внешний файл из `models/clip_vision` загружает `CLIPVisionLoader`; он не появляется из этого checkpoint автоматически.

## Производительность и внутреннее поведение

Это тяжёлый составной загрузчик: один вызов читает checkpoint, определяет архитектуру, создаёт diffusion model, VAE, текстовый энкодер и при возможности визуальный энкодер. Пиковая RAM и время разбора выше, чем у загрузчика одного компонента.

Model patcher выбирает load/offload device по общей политике ComfyUI. CLIP Vision использует device и dtype текстовых энкодеров; VAE имеет свою политику. Нода не предоставляет переключателей device или dtype в интерфейсе.

Один полный loader обычно выгоднее четырёх повторных чтений одного checkpoint, но не устраняет стоимость самих компонентов. Не дублируйте его без необходимости; разветвляйте выходы.

## Совместимость, изменения и статус

Статья закреплена на ComfyUI `0.32.0`, frontend `1.48.7`, runtime ID `unCLIPCheckpointLoader`, модуле `nodes`. Fingerprint: `sha256:12837b6dd3fec9e42756ef88636e7f56f51508093951fc5b435717cd5c4d2b67`.

Runtime не выставляет deprecated, experimental, dev-only или API-node flags; нода не является output node. Две подтверждённые закреплённым исходником конфигурации SD 2.1 unCLIP — L с `adm_in_channels = 1536` и H с `2048`.

У самого loader нет whitelist по семейству. Он может вернуть vision-компонент и для иной конфигурации с `clip_vision_prefix`, однако это не превращает её в `SD21UnclipL/H` и не доказывает совместимость четырёх выходов в одном графе.

Embedded docs 0.5.9 перечисляют четыре выхода, но формулировка «if available» не объясняет ветвление общего загрузчика и не доказывает совместимость любого checkpoint. Эти ограничения взяты из `comfy/sd.py` и конфигураций поддерживаемых моделей.

## Связанные ноды и источники

`CheckpointLoaderSimple` подходит для обычного полного checkpoint без встроенного vision-выхода. `CLIPVisionLoader` загружает внешний vision-файл. `CLIPVisionEncode` получает embedding изображения, а `unCLIPConditioning` записывает его вместе со strength и noise augmentation в metadata.

- [Реализация `unCLIPCheckpointLoader`](https://github.com/Comfy-Org/ComfyUI/blob/c2bcbecd82ec5ae66594340b395c24ef0217b238/nodes.py#L675-L688)
- [Условное извлечение компонентов checkpoint](https://github.com/Comfy-Org/ComfyUI/blob/c2bcbecd82ec5ae66594340b395c24ef0217b238/comfy/sd.py#L2034-L2201)
- [Конфигурации `SD21UnclipL` и `SD21UnclipH`](https://github.com/Comfy-Org/ComfyUI/blob/c2bcbecd82ec5ae66594340b395c24ef0217b238/comfy/supported_models.py#L137-L160)
- [Потребление unCLIP metadata в SD 2.1 и SDXL](https://github.com/Comfy-Org/ComfyUI/blob/c2bcbecd82ec5ae66594340b395c24ef0217b238/comfy/model_base.py#L439-L480)
- [Embedded docs 0.5.9 для `unCLIPCheckpointLoader`](https://github.com/Comfy-Org/embedded-docs/blob/1d258cf6e374d60d138a2bfcd273c7e11f750ef9/comfyui_embedded_docs/docs/UnclipCheckpointLoader/en.md)
- [Официальный workflow bundle 0.1.42](https://pypi.org/project/comfyui-workflow-templates-json/0.1.42/)
