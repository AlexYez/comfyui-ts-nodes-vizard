# DifferentialDiffusion: поэтапное раскрытие градаций denoise mask

## Что делает нода

`DifferentialDiffusion` клонирует `MODEL` и устанавливает функцию обработки denoise mask. На каждом sampling step функция превращает градации маски в бинарное решение по текущему timestep: при обычном убывающем расписании участки с большим значением включаются раньше, с меньшим — позже. Это позволяет одной плавной маске задавать разную длительность denoise по областям.

Нода не создаёт маску сама и ничего не меняет без mask-aware sampling path. Она помечена experimental и патчит только поведение MODEL во время inpaint/outpaint sampling.

## Место в графе

Подайте MODEL после loader и model patches в `DifferentialDiffusion`, затем направьте выход в `KSampler` или другой путь, использующий `KSamplerX0Inpaint` с denoise mask. Маску и latent обычно готовят `InpaintModelConditioning` либо `SetLatentNoiseMask`.

Slot `denoise_mask_function` одиночный. Следующая downstream-нода, которая вызовет `set_model_denoise_mask_function`, заменит этот обработчик. SLG/CFG hooks используют другие slots и могут сохраняться рядом, но итог сочетания всё равно зависит от порядка MODEL-patches.

## Входы

`model: MODEL` — обязательный вход. `strength: FLOAT` находится в optional-секции `/object_info`; default 1, диапазон 0–1, шаг 0,01.

`strength` смешивает исходную маску с бинарной только при `0 < strength < 1`. Значение 0 не возвращает исходную маску: из-за условия в source оно попадает в ту же ветвь, что и 1, и выдаёт полностью бинарный результат. Это граничное поведение отличается от обычной линейной ручки 0–1.

## Выходы

Единственный `MODEL` — clone с новым `denoise_mask_function`. Веса модели и входной объект не меняются.

Выход не содержит MASK. Увидеть преобразованную маску отдельным разъёмом нельзя: функция вызывается sampler внутри каждого шага, только если denoise mask присутствует.

## Как работает внутри

Из полного списка sigmas sampler берутся `sigma_from = sigmas[0]` и конечная `sigma_to`: обычно `model_sampling.sigma_min`, но если последняя sigma расписания выше неё, используется последняя. Эти значения и текущая `sigma[0]` переводятся функцией `timestep`. Порог равен `(current_ts − ts_to) / (ts_from − ts_to)`.

Затем строится `binary_mask = denoise_mask >= threshold`. При `0 < strength < 1` результат равен `strength × binary_mask + (1 − strength) × denoise_mask`; при strength 0 или 1 возвращается `binary_mask`. Сравнение включает равенство. Код не clamp-ит threshold и не защищает знаменатель от `ts_from == ts_to`.

## Настройки

Для полностью порогового поведения используйте 1. Для частичного сохранения исходных градаций выбирайте значение строго между 0 и 1. Если нужен исходный mask без differential thresholding, обойдите ноду MODEL-ветвью; `strength = 0` не служит выключателем в pinned 0.32.0.

Смысл градаций зависит от самой mask: при нормальном диапазоне 0–1 значение 1 проходит высокий ранний порог, а низкие значения включаются позднее. Резкая чёрно-белая маска оставляет меньше пространства для постепенного распределения. Schedule с единственным timestep или совпавшими крайними timesteps требует отдельной проверки из-за деления на ноль.

## Пример подключения

Bundle 0.1.42 содержит четыре экземпляра в трёх файлах, все mode 0 и со `strength = 1`. В `flux_fill_outpaint_example`, root UUID `aff23af9-e8f4-41f8-8e4c-0854e355b753`, локальная цепочка: `UNETLoader #31 → DifferentialDiffusion #39 → KSampler #3`; sampler хранит 20 steps, cfg 1, Euler, normal, denoise 1. `InpaintModelConditioning #38` подаёт positive, negative и latent, а `ImagePadForOutpaint` — pixels и mask.

Другие случаи: subgraph `42bcb419-1e9f-48eb-a6d6-c22e0625db3a` в `flux_fill_inpaint_example` и два subgraphs OneReward — `cb0eaf1c-704f-477d-8893-79665db14ed1` и `b8560576-5524-4495-baa5-2cb40da12e9e`. Fragment `recipe.differential-diffusion-flux-fill` сохраняет локальную MODEL-цепочку и параметры outpaint sampler, но получает conditioning/latent извне и не исполнялся.

## Частые ошибки

**Ставят `strength = 0` как bypass.** В версии 0.32.0 это полностью бинарная ветвь, как при 1.

**Ждут эффект без denoise mask.** Sampler вызывает функцию только при наличии маски.

**Подключают MASK к самой ноде.** У неё нет mask-входа; mask передаётся через latent/inpaint pipeline.

**Цепляют два обработчика denoise mask.** Последняя запись в одиночный slot заменяет предыдущую.

**Путают значение маски с постоянной силой denoise.** Здесь градация прежде всего задаёт timestep, на котором область проходит меняющийся порог.

## Ограничения и производительность

Операции сравнения и смешивания проходят по всему tensor маски на каждом шаге. Обычно они значительно дешевле model forward, но создают бинарный tensor, а при промежуточном strength — ещё и blended tensor. Большие video/batch masks увеличивают эту стоимость пропорционально числу элементов и шагов.

Функция предполагает непустой список sigmas, индекс `sigma[0]` и различимые крайние timesteps. В source нет clamp для threshold, проверки диапазона denoise mask или защиты от нулевого знаменателя. Реальные Flux Fill/OneReward weights, визуальное качество, разные schedulers и browser workflow не запускались.

## Совместимость и источники

Статья закреплена на ComfyUI `0.32.0`, frontend `1.48.7`, runtime ID `DifferentialDiffusion`, модуле `comfy_extras.nodes_differential_diffusion`. Fingerprint: `sha256:99e5950eb9d8e119e5bcf78dc7167fcbdfd2f2d92d7c03730757fad9368cbb66`. Runtime flags: experimental true; deprecated, dev_only и api_node false. Replacements и execution aliases отсутствуют.

Embedded docs 0.5.9 правильно указывают threshold mask и диапазон strength, но не описывают разрыв при strength 0. Русская страница переводит runtime-имена портов и содержит шаблонную строку о переводе. Граничная ветвь в статье зафиксирована по исходнику.

- [Реализация `DifferentialDiffusion`](https://github.com/Comfy-Org/ComfyUI/blob/c2bcbecd82ec5ae66594340b395c24ef0217b238/comfy_extras/nodes_differential_diffusion.py#L9-L61)
- [Вызов denoise mask function в sampler](https://github.com/Comfy-Org/ComfyUI/blob/c2bcbecd82ec5ae66594340b395c24ef0217b238/comfy/samplers.py#L630-L643)
- [Запись одиночного mask handler](https://github.com/Comfy-Org/ComfyUI/blob/c2bcbecd82ec5ae66594340b395c24ef0217b238/comfy/model_patcher.py#L646-L659)
- [Embedded docs 0.5.9](https://github.com/Comfy-Org/embedded-docs/blob/1d258cf6e374d60d138a2bfcd273c7e11f750ef9/comfyui_embedded_docs/docs/DifferentialDiffusion/en.md)
- [Официальный workflow bundle 0.1.42](https://pypi.org/project/comfyui-workflow-templates-json/0.1.42/)
