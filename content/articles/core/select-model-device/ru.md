# SelectModelDevice: назначить устройство для diffusion MODEL

## Что делает нода

`SelectModelDevice` возвращает клон `MODEL` с выбранным load/offload routing. Вариант `default` восстанавливает устройства, назначенные loader; `cpu` закрепляет load и offload за CPU; `gpu:N` выбирает N-е доступное torch device как load device и сохраняет исходную offload-политику loader.

Если target отличается от текущего load device, нода не переносит уже загруженные weights обычным `.to(...)`. Она вызывает reload factory и создаёт fresh deepclone, после чего переносит patcher state на новую базовую модель.

Недоступный `gpu:N` не останавливает workflow: runtime возвращает клон с прежним routing и пишет сообщение в лог.

## Место в графе

Ставьте selector сразу после loader и model modifiers, но до первого consumer: guider, scheduler, KSampler или sampler custom. Source предупреждает не помещать ноду после уже выполненного consumer той же модели. Если target совпадает с текущим устройством, fast path переиспользует underlying model и может видеть изменённое consumer-состояние.

Перед `MultiGPU_WorkUnits` selector задаёт primary device. Split-нода исключает этот target из списка extras. Если selector стоит после split и target сталкивается с существующим clone, `SelectModelDevice` удаляет конфликтующую копию и пересобирает clone mapping.

Нода не выбирает устройства для CLIP и VAE. Для них существуют отдельные selectors.

## Входы

- `model: MODEL` — обязательный diffusion model patcher.
- `device: COMBO` — `default`, `cpu` или динамический `gpu:N`.

В pinned clean `/object_info` варианты равны `default` и `cpu`, потому что snapshot не увидел несколько GPU. На runtime с двумя и более torch devices функция добавляет `gpu:0`, `gpu:1` и далее. Число не ограничено восьмью, хотя embedded docs показывают список только до `gpu:7`.

Validation намеренно принимает неизвестную строку device. Это позволяет открыть workflow с `gpu:1` на машине без второго GPU и выполнить fallback вместо schema error.

## Выходы

Выход `MODEL` — новый patcher object. Даже при недоступном target код сначала вызывает `model.clone()`, поэтому «passed through unchanged» означает прежнюю маршрутизацию и модельное поведение, а не тождество Python-объекта.

При смене GPU deepclone владеет fresh base model на новом load device. Patches и связанную patcher-конфигурацию переносит `ModelPatcher.deepclone_multigpu`.

Runtime output name — `MODEL`. Embedded docs используют lowercase `model` как подпись таблицы; recipe connections должны брать точное runtime-имя.

## Как работает внутри

Сначала нода клонирует patcher и разрешает строку device. `default` превращается в `None`, `cpu` — в `torch.device("cpu")`, `gpu:N` — в N-й элемент `get_all_torch_devices`. Неизвестное или отсутствующее устройство даёт ранний возврат клона.

Helper запоминает исходные load/offload devices на underlying model при первом selector в цепочке. `default` возвращает эту пару. Для CPU dynamic patcher при необходимости преобразуется в обычный `ModelPatcher`, после чего оба devices становятся CPU.

Для другого GPU `_retarget_patcher` вызывает `deepclone_multigpu(new_load_device=target)`, восстанавливает loader offload device и переносит base-device markers на fresh model. Loader без `cached_patcher_init` вызывает `RuntimeError`; selector ловит его, пишет warning и возвращает routing до retarget.

После успешного выбора не-default device нода проверяет compute dtype через `unet_manual_cast` и меняет его, если target не поддерживает weight dtype напрямую. Затем clone на том же device удаляется из multigpu additional models, чтобы primary и extra не совпали.

## Настройки

`default` полезен после предыдущего selector: он восстанавливает devices первого loader, а не глобальный текущий GPU процесса. Исходная пара хранится на model и переживает последующие clones.

`cpu` освобождает GPU от load и offload маршрута модели, но sampling на CPU обычно намного медленнее. Dynamic patcher может потребовать loader factory, чтобы перейти в non-dynamic режим.

`gpu:N` — позиция в vendor-neutral списке torch devices, а не обещание конкретного CUDA UUID. На multi-GPU системе сверяйте фактическое соответствие через лог и системные средства. Offload остаётся исходным выбором loader.

## Пример подключения

Общий fragment `recipe.multigpu-cfg-split` соединяет внешний `MODEL` с `SelectModelDevice(device = gpu:0)`, а затем с `MultiGPU_WorkUnits(max_gpus = 2)`. Такое расположение сначала задаёт primary и только затем создаёт extra clone.

На одно-GPU машине `gpu:0` не показывается в combo, потому что source добавляет явные gpu options только при двух и более devices. Однако импортированная строка проходит validation и resolver находит единственное устройство под индексом `0`; selector направляет MODEL туда, а split не находит extra device.

В 512 JSON официального workflow wheel 0.1.42 нет `SelectModelDevice`: root, 272 subgraph, indices, scalar и raw substring дали ноль. Fragment source-derived. Exact-source probe проверяет default/cpu/gpu/unavailable, fresh clone, dtype adjustment и collision pruning на синтетических patcher; настоящие weights не загружались.

## Частые ошибки

**`gpu:1` пропал из combo после переноса workflow.** На текущей машине нет второго обнаруженного device. Сохранённое значение проходит validation, но runtime оставляет routing без изменения.

**В логе warning о `cached_patcher_init`.** Custom loader не умеет создать fresh model. Используйте поддерживаемый core loader или добавьте factory в loader.

**Выбран GPU, но VRAM не освободилась на исходном.** Patcher routing и lifecycle управляются model manager; другие clones, consumers или models могут удерживать память. Selector не является командой глобальной очистки VRAM.

**Результат после selector зависит от предыдущего KSampler.** Перенесите selector до первого consumer. Fast path на том же device намеренно видит состояние shared underlying model.

**После selector исчез один MultiGPU clone.** Нода удаляет clone, чей load device совпал с новым primary. Это защита от дублирования, а не случайная потеря.

**Compute dtype изменился.** Нода выбирает supported manual-cast dtype для target. Проверьте лог `Select Model Device`.

## Ограничения и производительность

Fresh deepclone может перечитать и заново создать всю модель. Это увеличивает задержку первого запуска и требует памяти на target device. Patches переносятся, но loader должен поддерживать clean reconstruction.

CPU routing экономит VRAM ценой compute time и transfers. Выбор другого GPU полезен для распределения нескольких моделей или подготовки MultiGPU CFG, но сам по себе не ускоряет единственный model apply.

Fallback ловит `RuntimeError` retarget и оставляет routing. Другие типы исключений source не перехватывает. Просматривайте лог вместо того, чтобы считать отсутствие crash доказательством успешного перемещения.

## Совместимость и источники

Материал проверен на ComfyUI `0.32.0`, commit `c2bcbecd82ec5ae66594340b395c24ef0217b238`, frontend `1.48.7`. Runtime fingerprint: `sha256:5aff18a14cb2f9f6e37646632f13a6e087c12f0314ed9979e5cc90eabc146227`. Нода active, не experimental, deprecated, dev-only или API node; replacement не заявлен.

Embedded docs 0.5.9 верно описывают default/cpu/gpu routing и placement warning. Их фиксированный список `gpu:0`…`gpu:7` не является runtime max: source строит options по фактическому числу devices. Табличный output label lowercase также не совпадает с `/object_info` output name `MODEL`.

- [Реализация `SelectModelDevice`](https://github.com/Comfy-Org/ComfyUI/blob/c2bcbecd82ec5ae66594340b395c24ef0217b238/comfy_extras/nodes_multigpu.py#L51-L231)
- [Динамические device options](https://github.com/Comfy-Org/ComfyUI/blob/c2bcbecd82ec5ae66594340b395c24ef0217b238/comfy/model_management.py#L246-L289)
- [`ModelPatcher.deepclone_multigpu`](https://github.com/Comfy-Org/ComfyUI/blob/c2bcbecd82ec5ae66594340b395c24ef0217b238/comfy/model_patcher.py#L506-L553)
- [Embedded docs 0.5.9](https://github.com/Comfy-Org/embedded-docs/blob/1d258cf6e374d60d138a2bfcd273c7e11f750ef9/comfyui_embedded_docs/docs/SelectModelDevice/en.md)

Редактор пока не проверил материал вручную.
