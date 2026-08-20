# SelectCLIPDevice: назначить устройство для CLIP

## Что делает нода

`SelectCLIPDevice` создаёт clone объекта `CLIP` и меняет load/offload routing его model patcher. `default` восстанавливает устройства loader, `cpu` закрепляет оба маршрута за CPU, а `gpu:N` назначает N-е доступное torch device как load device.

Если выбранный GPU отсутствует, нода не завершает workflow ошибкой. Она возвращает CLIP clone с прежним routing и пишет информационное сообщение.

Selector не кодирует текст и не меняет prompt. Он перенастраивает patcher. В pinned 0.32.0 при fresh deepclone код не присваивает новый `patcher.model` полю `clip.cond_stage_model`, которое encode вызывает напрямую. Поэтому полное фактическое перемещение CLIP на другой GPU требует отдельного runtime-теста; одна проверка `patcher.load_device` его не доказывает.

## Место в графе

Ставьте `SelectCLIPDevice` после `CLIPLoader`, `DualCLIPLoader` или checkpoint loader и до `CLIPTextEncode`. Так encode использует уже выбранный routing.

Если CLIP проходит через merge или patch-ноду, закончите эти изменения до selector. При смене load device shared helper создаёт fresh deepclone через loader factory; patcher state переносится на новую базовую модель.

Нода действует независимо от `SelectModelDevice` и `SelectVAEDevice`. Выбор GPU для diffusion MODEL не перемещает CLIP автоматически.

## Входы

- `clip: CLIP` — обязательный текстовый энкодер.
- `device: COMBO` — `default`, `cpu` или динамический `gpu:N`.

Pinned clean inventory содержит только `default` и `cpu`. На системе с несколькими torch devices source добавляет `gpu:0`, `gpu:1` и далее. Dynamic choices намеренно исключены из schema fingerprint, иначе один и тот же NodeId менял бы fingerprint вместе с hardware.

Метод `validate_inputs` принимает и неизвестную строку. Сохранённый `gpu:1` поэтому можно открыть на одно-GPU машине; fallback сработает во время execute.

## Выходы

Выход `CLIP` — клонированная wrapper-структура. При доступном target её `patcher` получает новый routing. При недоступном target wrapper всё равно является clone, но load/offload devices остаются прежними.

`CLIP.clone()` копирует ссылку `cond_stage_model` из исходного wrapper. `SelectCLIPDevice.execute` после retarget заменяет только `clip.patcher`. В отличие от VAE selector, явной строки `clip.cond_stage_model = clip.patcher.model` в source нет. Это наблюдаемое расхождение указателей, а не само по себе доказательство неверного результата на реальном loader.

Нода не возвращает device отдельным портом. Проверяйте фактический routing по логам и поведению model manager.

Runtime output name — `CLIP`. Lowercase `clip` в embedded docs — человекочитаемая подпись, не имя порта для recipe connection.

## Как работает внутри

`execute` начинает с `clip.clone()`, затем вызывает `resolve_gpu_device_option`. `default` превращается в `None`; `cpu` — в CPU device; корректный `gpu:N` — в найденное torch device. Неизвестная строка приводит к раннему возврату CLIP clone.

Shared helper запоминает loader-original load/offload devices на underlying patcher model. `default` восстанавливает эту пару. CPU назначается одновременно как load и offload; dynamic patcher при необходимости преобразуется в обычный `ModelPatcher`.

Если другой GPU отличается от текущего load device, `_retarget_patcher` вызывает `deepclone_multigpu`. Метод требует `cached_patcher_init`, строит fresh base model и переносит patcher state. Offload device для explicit GPU остаётся исходным выбором loader.

`RuntimeError` от retarget перехватывается. Нода пишет warning и возвращает CLIP clone с routing, который был до неудачной смены. В отличие от `SelectModelDevice`, здесь нет отдельного compute-dtype adjustment и pruning MultiGPU model clones. В отличие от `SelectVAEDevice`, после fresh retarget wrapper model pointer не синхронизируется с patcher model.

## Настройки

`default` возвращает routing первого loader даже после цепочки selectors. Исходная пара сохраняется на model только при первом обращении.

`cpu` может освободить GPU-память под diffusion MODEL или VAE, но text encoding станет медленнее. Веса и intermediate tensors также могут перемещаться по правилам model manager; selector не обещает мгновенное освобождение всей VRAM.

`gpu:N` выбирает N-й элемент vendor-neutral device list. На NVIDIA это обычно соответствует `cuda:N`, но recipe хранит логический option, а не UUID физической карты.

## Пример подключения

Fragment `recipe.select-clip-device` содержит одну ноду с `device = gpu:1`:

1. внешний `CLIP` → `SelectCLIPDevice`;
2. выход `CLIP` → `CLIPTextEncode` в вашем графе;
3. при отсутствии второго GPU проверьте log: routing должен остаться loader-original.

Полный census workflow templates 0.1.42 дал ноль `SelectCLIPDevice` во всех 512 JSON, 496 root graphs и 272 subgraph; нулевыми также оказались scalar/raw mentions и EN/RU index titles. Fragment source-derived. Синтетический exact-source probe проверяет clone, cpu/gpu/default и unavailable fallback без CLIP weights и CUDA-вычислений. Probe также подтверждает, что после fresh retarget `cond_stage_model is not patcher.model`; реальное encode не запускалось.

## Частые ошибки

**`gpu:1` не отображается в combo.** ComfyUI не увидел как минимум два torch devices. Импортированная строка пройдёт validation, но runtime не сменит routing.

**CLIP остался на прежнем устройстве с warning.** Loader не предоставил `cached_patcher_init`, поэтому fresh deepclone невозможен. Выберите core loader с multigpu support.

**После `cpu` encode стал заметно медленнее.** Это ожидаемый trade-off: GPU VRAM освобождается для других компонентов ценой CPU compute и transfers.

**Ожидалось, что изменится diffusion MODEL.** Selector касается только `clip.patcher`. Для MODEL используйте `SelectModelDevice`.

**Нода «ничего не сделала», но объект на выходе другой.** При unavailable target routing сохраняется, однако `clip.clone()` уже выполнен. Сравнивайте devices, а не object identity.

**`default` выбрал не глобальный GPU.** Он восстанавливает loader-original routing конкретного CLIP.

**`patcher.load_device` изменился, но нужно доказать, где исполняется encode.** В 0.32.0 wrapper продолжает ссылаться на прежний `cond_stage_model` после fresh retarget. До отдельного real-device теста не считайте поле patcher достаточным доказательством полной миграции.

## Ограничения и производительность

Смена GPU может заново создать и загрузить весь текстовый энкодер. Для T5, Llama и других крупных CLIP-compatible encoders это заметный объём памяти и I/O. Нода не измеряет доступную VRAM заранее.

CPU-путь отключает dynamic-only поведение patcher, когда source может создать non-dynamic delegate. Если loader factory отсутствует, операция откатывается до routing clone.

Selector не синхронизирует execution с другими параллельными consumers одного исходного CLIP. Располагайте его до encode и избегайте неоднозначных веток, если разные selectors должны управлять разными copies.

Расхождение между fresh `patcher.model` и сохранённой ссылкой `cond_stage_model` — главный непроверенный участок pinned реализации. Статья фиксирует его как source finding; подтвердить влияние на загрузку и encode можно только с настоящим CLIP и двумя устройствами.

## Совместимость и источники

Статья проверена на ComfyUI `0.32.0`, commit `c2bcbecd82ec5ae66594340b395c24ef0217b238`, frontend `1.48.7`. Runtime fingerprint: `sha256:fb99fbc2ad455a81ba9499c53d7a9f743780e6b5668834ff83397414211e4d3a`. Нода active, не experimental, deprecated, dev-only или API node; replacement не заявлен.

Embedded docs 0.5.9 корректно описывают основные modes и unavailable fallback, но показывают фиксированный диапазон до `gpu:7`; source не задаёт такого max. Документация также не уточняет, что fallback возвращает wrapper clone, и не описывает requirement loader factory.

- [Shared device-routing helpers](https://github.com/Comfy-Org/ComfyUI/blob/c2bcbecd82ec5ae66594340b395c24ef0217b238/comfy_extras/nodes_multigpu.py#L51-L139)
- [Определение `SelectCLIPDevice`](https://github.com/Comfy-Org/ComfyUI/blob/c2bcbecd82ec5ae66594340b395c24ef0217b238/comfy_extras/nodes_multigpu.py#L234-L279)
- [Dynamic device options](https://github.com/Comfy-Org/ComfyUI/blob/c2bcbecd82ec5ae66594340b395c24ef0217b238/comfy/model_management.py#L246-L289)
- [`CLIP.clone` и wrapper model reference](https://github.com/Comfy-Org/ComfyUI/blob/c2bcbecd82ec5ae66594340b395c24ef0217b238/comfy/sd.py#L298-L307)
- [CLIP encode использует `cond_stage_model`](https://github.com/Comfy-Org/ComfyUI/blob/c2bcbecd82ec5ae66594340b395c24ef0217b238/comfy/sd.py#L392-L460)
- [Embedded docs 0.5.9](https://github.com/Comfy-Org/embedded-docs/blob/1d258cf6e374d60d138a2bfcd273c7e11f750ef9/comfyui_embedded_docs/docs/SelectCLIPDevice/en.md)

Редактор пока не проверил материал вручную.
