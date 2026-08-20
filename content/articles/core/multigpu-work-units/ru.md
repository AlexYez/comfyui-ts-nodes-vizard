# MultiGPU_WorkUnits: разделить conditioning-работу между GPU

## Что делает нода

`MultiGPU_WorkUnits` подготавливает `MODEL` к параллельному sampling на нескольких устройствах. Она создаёт полные deepclone-копии модели на дополнительных GPU и регистрирует их как `multigpu` models. Во время sampling специальная ветка scheduler распределяет между устройствами отдельные conditioning work units.

Это не tensor sharding и не разрезание модели по слоям. На каждом выбранном GPU размещается самостоятельная модель. Поэтому каждое устройство должно вместить её веса и связанные additional models.

Ускорение зависит от числа независимых work units, их размера, обмена тензорами и скорости каждого GPU. Наличие двух копий само по себе не сокращает время исполнения.

## Место в графе

Ставьте ноду после операций, которые меняют сам объект `MODEL`: compile, переключения attention, merge и model patch. Исходный docstring прямо требует закончить такие изменения до создания deepclone. После `MultiGPU_WorkUnits` передайте выход в guider, scheduler или sampler обычным способом.

`SelectModelDevice` можно поставить перед split-нодой, чтобы выбрать primary device. `MultiGPU_WorkUnits` затем исключит primary из списка дополнительных устройств и возьмёт первые доступные GPU, пока общее число не достигнет `max_gpus`.

У ноды нет входа CFG. Она не проверяет guider и не запрещает CFG = 1. Однако scheduler может распараллелить только фактически созданные conditioning units. Если optimized CFG-путь оставил одну работу, второй GPU простаивает.

## Входы

- `model: MODEL` — модель после всех изменений, которые должны одинаково присутствовать на каждой копии.
- `max_gpus: INT` — максимальное общее число устройств, включая primary. Default `2`, минимум `1`, шаг `1`; верхний предел runtime не задаёт.

`max_gpus = 1` не создаёт дополнительную модель и удаляет унаследованные multigpu clones за пределами разрешённого набора. Если указать число больше доступного, нода использует только найденные устройства.

Loader исходной модели должен заполнить `cached_patcher_init`. Без этой reload factory `deepclone_multigpu` не может создать свежую модель на другом устройстве и поднимает `RuntimeError`.

## Выходы

Выход `MODEL` содержит клон исходного patcher с additional models под ключом `multigpu`. Тип порта остаётся обычным `MODEL`, поэтому downstream-ноды не получают отдельного списка устройств.

Если дополнительных устройств нет, нода пишет информационное сообщение и возвращает клонированный `MODEL` без multigpu acceleration. Если clones уже были созданы раньше, повторный вызов учитывает их load devices и удаляет экземпляры, которые выходят за новый лимит.

Результат не хранит измеренный speedup. Проверять загрузку GPU, время шага и итоговую идентичность нужно отдельно.

## Как работает внутри

`execute` вызывает `create_multigpu_deepclones(model, max_gpus, reuse_loaded=True)`. Функция сначала клонирует patcher, берёт все torch devices, исключает primary `load_device` и ограничивает дополнительные устройства первыми `max_gpus - 1` элементами. Уже зарегистрированные clones не создаются повторно; подходящая ранее загруженная multigpu-копия может быть переиспользована.

Новый экземпляр создаётся через `ModelPatcher.deepclone_multigpu`. Reload factory строит свежую базовую модель, а patcher переносит нужные patches, hooks и additional models. Clone получает флаг `is_multigpu_base_clone`, после чего главный patcher синхронизирует clone-набор.

Перед sampling helper собирает словарь `device → patcher`, а sampler создаёт по worker thread на устройство на время одного sample. Внутри diffusion steps scheduler считает conditioning units, задаёт равную ёмкость `ceil(total_conds / device_count)`, подбирает batch с учётом свободной памяти и отправляет его соответствующей модели. Входные тензоры переходят на рабочее устройство, а результат возвращается на исходный output device.

Зарегистрированный, но пока не публикуемый `MultiGPUOptionsNode` не входит в extension. Следовательно, scheduler 0.32.0 не использует пользовательскую относительную скорость GPU и делит работу равномерно по количеству units.

## Настройки

Для двух GPU начните с `max_gpus = 2`. Значение означает «primary плюс не более одного extra», а не «два дополнительных GPU». Для трёх устройств лимит `3` разрешает primary и две копии.

Нода сама не выбирает конкретные extra devices. Порядок приходит из `get_all_torch_devices`. Primary можно изменить через `SelectModelDevice`; оставшиеся берутся из доступного списка после его исключения.

Embedded docs 0.5.9 описывают поддерживаемую конфигурацию как одинаковые GPU Ampere или новее. Исполняемый код не сравнивает модель или производительность видеокарт. Это следует понимать как документированную границу поддержки и тестирования, а не как runtime validation. На разных GPU равное число work units создаёт дисбаланс.

## Пример подключения

Fragment `recipe.multigpu-cfg-split` задаёт:

1. внешний `MODEL` → `SelectModelDevice` с `device = gpu:0`;
2. выход `MODEL` → `MultiGPU_WorkUnits` с `max_gpus = 2`;
3. выход split-ноды → ваш guider или sampler.

На машине без `gpu:0` selector сохраняет прежний routing. Без второго устройства split-нода не создаёт extra clone. Для реального параллелизма нужны два доступных GPU, loader с reload factory, место под полную модель на каждом и больше одного conditioning work unit.

Проверены все 512 JSON official workflow templates 0.1.42: 496 root graphs и 272 subgraph. `MultiGPU_WorkUnits` отсутствует как node type, scalar и raw substring. Embedded docs ссылаются на mutable sample URL, но JSON sample не входит в pinned wheel 0.5.9. Fragment поэтому основан на exact source, а не назван официальным кейсом. Синтетическая проба проверяет clone selection и pruning без CUDA; полный граф на двух GPU не запускался.

## Частые ошибки

**Второй GPU не показывает нагрузку.** Проверьте число реальных conditioning units. При одной работе scheduler не может распределить её между двумя полными моделями.

**`max_gpus = 2`, а extra copies ожидалось две.** Лимит включает primary. Для primary плюс двух extras нужен лимит `3` и три доступных устройства.

**Получен `RuntimeError` о `cached_patcher_init`.** Loader не поддерживает fresh multigpu deepclone. Используйте core loader, перечисленный в сообщении ModelPatcher, либо обновите custom loader.

**Модель помещалась на одном GPU, но multigpu дал OOM.** Каждое устройство получает полную модель и связанные additional models. Нода не распределяет отдельные слои между картами.

**Compile или patch применён после split.** Перенесите modifier перед `MultiGPU_WorkUnits`, чтобы clones создавались из окончательного объекта.

**Быстрый GPU ждёт медленный.** В активном scheduler нет настройки relative speed. Используйте документированно поддерживаемую однородную конфигурацию.

## Ограничения и производительность

Создание свежих моделей увеличивает время подготовки и суммарную VRAM. Patcher может переиспользовать уже загруженный multigpu clone с подходящим UUID и устройством, но рассчитывать на это при первом запуске нельзя.

Параллелизм работает на уровне conditioning batches. Он не делит diffusion steps и не ускоряет участки workflow вне model apply: VAE, CLIP, загрузку файлов и post-processing. Перемещение входов на worker device и возврат outputs тоже занимает время.

Embedded docs упоминают ускорение до `1.95x`, но pinned страница не даёт воспроизводимого benchmark-протокола. Статья не превращает эту цифру в гарантию. Измеряйте одинаковый workflow после прогрева, проверяйте VRAM каждого устройства и сравнивайте итоговые tensors или изображения.

В source есть TODO о синхронизации output transfer для non-NVIDIA backends. CUDA прошла указанную в комментарии QA, а расширение поддержки требует отдельной проверки.

## Совместимость и источники

Материал проверен на ComfyUI `0.32.0`, commit `c2bcbecd82ec5ae66594340b395c24ef0217b238`, frontend `1.48.7`. Runtime fingerprint: `sha256:40bf0932ad255a6085ec723c3013db294d9edf2883365b0d0347f351221539ea`. Нода active, не experimental, deprecated, dev-only или API node; replacement не заявлен.

Embedded docs 0.5.9 используются как secondary support policy. Их список моделей, hardware boundary и speedup не являются проверками внутри node code. Русский текст также говорит, что CFG «должен быть больше 1»; точнее сформулировать условие через число work units, которое реально читает scheduler.

- [Определение `MultiGPU_WorkUnits`](https://github.com/Comfy-Org/ComfyUI/blob/c2bcbecd82ec5ae66594340b395c24ef0217b238/comfy_extras/nodes_multigpu.py#L20-L48)
- [Создание и pruning deepclone](https://github.com/Comfy-Org/ComfyUI/blob/c2bcbecd82ec5ae66594340b395c24ef0217b238/comfy/multigpu.py#L125-L195)
- [Распределение conditioning batches](https://github.com/Comfy-Org/ComfyUI/blob/c2bcbecd82ec5ae66594340b395c24ef0217b238/comfy/samplers.py#L358-L545)
- [Embedded docs 0.5.9](https://github.com/Comfy-Org/embedded-docs/blob/1d258cf6e374d60d138a2bfcd273c7e11f750ef9/comfyui_embedded_docs/docs/MultiGPU_WorkUnits/en.md)

Редактор пока не проверил материал вручную.
