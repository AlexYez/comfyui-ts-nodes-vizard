# SelectVAEDevice: назначить GPU для VAE

## Что делает нода

`SelectVAEDevice` создаёт отдельную VAE wrapper-копию и направляет её model patcher на выбранный GPU. `default` восстанавливает load device loader, а `gpu:N` выбирает N-е доступное torch device. Offload device берётся из стандартной VAE-политики ComfyUI.

CPU намеренно отсутствует в UI. Если старый или импортированный workflow всё же передаст `cpu`, нода примет значение на schema validation, но во время execute оставит routing без изменения и запишет сообщение.

Selector не выполняет encode/decode и не меняет параметры VAE. Он готовит размещение весов для следующих VAE-операций.

## Место в графе

Ставьте `SelectVAEDevice` после `VAELoader` или checkpoint loader и до `VAEEncode`, `VAEDecode` либо их tiled-вариантов. Каждый downstream consumer тогда получает wrapper с выбранным patcher.

Выбор устройства VAE не связан автоматически с `SelectModelDevice` или `SelectCLIPDevice`. Один граф может оставить MODEL на primary GPU, а VAE направить на другой.

При смене load device helper создаёт fresh model через loader factory. Поэтому custom loader должен поддерживать `cached_patcher_init`; иначе selector вернёт routing clone после warning.

## Входы

- `vae: VAE` — обязательная VAE wrapper-структура.
- `device: COMBO` — `default` или динамический `gpu:N`; CPU в options отфильтрован.

Pinned clean inventory содержит только `default`, потому что snapshot не обнаружил несколько GPU. На multi-device runtime список получает `gpu:0`, `gpu:1` и далее. Эти hardware-dependent options исключаются из structural fingerprint.

`validate_inputs` возвращает `True` для любой device-строки. Это поддерживает переносимые workflows и runtime fallback.

## Выходы

Выход `VAE` — shallow copy исходной wrapper с клонированным patcher. Исходный wrapper не перенастраивается напрямую.

После успешного retarget код заменяет `vae.first_stage_model` на model нового patcher и синхронизирует `vae.device`: для explicit GPU это resolved device, для `default` — запомненное исходное поле wrapper.

При invalid или CPU request выход всё равно является wrapper/patcher copy, но routing и `first_stage_model` остаются исходными. Runtime output name — `VAE`, а не переведённое имя из таблицы embedded docs.

## Как работает внутри

Поскольку VAE wrapper не имеет `.clone()`, execute вызывает `copy.copy(vae)`, затем `vae.patcher.clone()`. После этого строка device разрешается тем же helper, что у других selectors.

Unavailable device даёт ранний возврат. CPU проверяется отдельно и также возвращает copy без retarget. Перед первой успешной операцией wrapper запоминает своё исходное `vae.device` в `_select_base_device`.

`_apply_patcher_device` хранит loader-original load/offload pair на patcher model. Для VAE параметр `base_offload_override` всегда получает `vae_offload_device()`: обычно CPU, а при `--gpu-only` — текущий torch device ComfyUI. Explicit `gpu:N` меняет load device, но сохраняет эту стандартную offload-политику.

Когда target отличается от текущего load device, создаётся fresh deepclone. После успеха wrapper указывает на fresh `first_stage_model`. `RuntimeError` перехватывается и оставляет routing clone.

## Настройки

`default` восстанавливает исходный load device patcher и поле `vae.device`. Offload при этом берётся из текущей стандартной VAE-политики, а не из произвольной строки recipe.

`gpu:N` полезен, когда VAE encode/decode конкурирует с diffusion MODEL за VRAM primary GPU. Выбор второго GPU требует свободного места под VAE и тензоры изображения/latent.

`cpu` не является поддерживаемой пользовательской настройкой. В отличие от `SelectCLIPDevice`, эта нода не предлагает CPU даже при наличии такого option у общего resolver.

## Пример подключения

Fragment `recipe.select-vae-device` задаёт `device = gpu:1`:

1. внешний `VAE` → `SelectVAEDevice`;
2. выход `VAE` → `VAEDecode` или `VAEEncode`;
3. при переносе workflow проверьте log и фактическую VRAM второго GPU.

Все 512 JSON official workflow templates 0.1.42 и 272 subgraph просмотрены полностью. `SelectVAEDevice` отсутствует как type, scalar, raw substring и index title. Fragment source-derived. Exact-source probe проверяет shallow wrapper copy, patcher clone, gpu/default/cpu/unavailable, standard offload и `first_stage_model` synchronization на синтетическом объекте; real VAE execution не выполнялся.

## Частые ошибки

**В combo нет `cpu`.** Это намеренное отличие от MODEL и CLIP selectors. Source исключает CPU из VAE options.

**Импортированный `cpu` выполнился без schema error, но VAE не переместился.** Validation разрешает переносимое значение, execute отклоняет CPU и оставляет routing.

**`gpu:1` дал fallback.** Второй torch device недоступен либо строка больше не соответствует hardware текущей машины.

**Получен warning о retarget.** Loader не предоставил factory для fresh deepclone. Используйте core VAE/checkpoint loader с multigpu support.

**После выбора GPU всё равно видна CPU offload.** Это стандартная VAE-политика при обычном запуске. Load device и offload device выполняют разные роли.

**Ожидалось, что исходный VAE изменится.** Нода создаёт shallow wrapper copy и patcher clone. Другие ветки от исходного VAE сохраняют прежнее размещение.

## Ограничения и производительность

Fresh deepclone может заново создать first-stage model. Первый encode/decode после смены устройства включает загрузку весов и transfers, поэтому единичный запуск может не выиграть по времени.

VAE обрабатывает крупные image tensors. Перенос на отдельный GPU уменьшает конкуренцию за VRAM primary, но добавляет межустройственные копирования на границах pipeline. Измеряйте полный workflow, а не только время VAE kernel.

Нода не меняет VAE dtype и не вызывает model-specific cast helper. Совместимость dtype с target остаётся в ответственности VAE/model manager.

## Совместимость и источники

Материал проверен на ComfyUI `0.32.0`, commit `c2bcbecd82ec5ae66594340b395c24ef0217b238`, frontend `1.48.7`. Runtime fingerprint: `sha256:20a2a0c9f63e53884a53d56d17f28557b678453a7015e334a73f2cb24b19886e`. Нода active, не experimental, deprecated, dev-only или API node; replacement не заявлен.

Embedded docs 0.5.9 верно исключают CPU и описывают fallback, но фиксируют только `gpu:0`…`gpu:7`, не объясняют wrapper/patcher copy и не различают load/offload device. В RU-странице runtime input `device` ошибочно переведён как `устройство`; fragment сохраняет exact identifier.

- [Shared device-routing helpers](https://github.com/Comfy-Org/ComfyUI/blob/c2bcbecd82ec5ae66594340b395c24ef0217b238/comfy_extras/nodes_multigpu.py#L51-L139)
- [Определение `SelectVAEDevice`](https://github.com/Comfy-Org/ComfyUI/blob/c2bcbecd82ec5ae66594340b395c24ef0217b238/comfy_extras/nodes_multigpu.py#L282-L347)
- [Dynamic device options](https://github.com/Comfy-Org/ComfyUI/blob/c2bcbecd82ec5ae66594340b395c24ef0217b238/comfy/model_management.py#L246-L289)
- [Стандартный VAE offload device](https://github.com/Comfy-Org/ComfyUI/blob/c2bcbecd82ec5ae66594340b395c24ef0217b238/comfy/model_management.py#L1239-L1248)
- [Embedded docs 0.5.9](https://github.com/Comfy-Org/embedded-docs/blob/1d258cf6e374d60d138a2bfcd273c7e11f750ef9/comfyui_embedded_docs/docs/SelectVAEDevice/en.md)

Редактор пока не проверил материал вручную.
