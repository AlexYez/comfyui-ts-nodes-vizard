# DualModelGuider: CFG на двух моделях

## Что делает нода

`DualModelGuider` считает conditional-прогноз `C` основной моделью, а unconditional-прогноз `U` — отдельной `model_negative`, если она подключена. Затем используется стандартное смешение `U + cfg × (C − U)`.

Если `model_negative` не подключена, execute создаёт обычный `comfy.samplers.CFGGuider` на основной модели. Если `negative` не подключён, нода подставляет `[[None, {}]]`: это condition без cross-attention для text-free, image-only unconditional-прохода.

Нода помечена experimental в exact runtime. Она управляет полным lifecycle второй модели во время sampling: отдельной подготовкой, преобразованием latent, запуском и cleanup.

## Когда использовать и когда не использовать

Используйте ноду, когда архитектура поставляется отдельными conditional и unconditional diffusion models. Закреплённый официальный пример Ideogram 4 загружает два разных UNET-файла именно так.

Не подставляйте произвольные модели только потому, что обе имеют тип MODEL. Их latent format, sampling scale, prediction shape и смысл timesteps должны быть совместимы. Нода не проверяет семейство и не преобразует один prediction в пространство другого.

Для обычного CFG одной модели оставьте `model_negative` пустой или используйте `CFGGuider`. Для двух conditioning на одной модели нужен `DualCFGGuider`.

## Короткий рецепт подключения

1. Подайте conditional MODEL во вход `model`.
2. При наличии отдельной unconditional модели подключите её к `model_negative`.
3. Подайте positive CONDITIONING; negative можно подключить явно или оставить text-free.
4. Выберите cfg, рекомендованный моделью; официальный Ideogram 4 использует 7.
5. Соедините GUIDER с `SamplerCustomAdvanced` и используйте совместимые latent и sigmas.

Fragment «Две модели и CFG 7» повторяет official topology Ideogram на уровне портов: два внешних MODEL, positive и negative входят в guider, выход идёт в custom sampler. Модельные файлы не зашиты в fragment; он не запускался.

## Входы, выходы и параметры

Обязательны `model: MODEL`, `positive: CONDITIONING`, `cfg: FLOAT`. У основного model есть tooltip «positive (conditional) pass». `cfg` имеет default 4, диапазон 0–100, step 0,1 и round 0,01.

Optional-входы: `model_negative: MODEL` и `negative: CONDITIONING`. Tooltip прямо разрешает не подключать negative для text-free unconditional pass. Выход один — `GUIDER`, не list-output.

Если подключён negative, но не model_negative, обе ветви считает основной model через обычный CFGGuider. Если подключена model_negative, но negative пуст, вторая модель работает без text cross-attention.

## Типовые связки

В official Ideogram 4 основная `ideogram4_fp8_scaled.safetensors` проходит через `CFGOverride`, отдельная `ideogram4_unconditional_fp8_scaled.safetensors` идёт напрямую в `model_negative`. Positive создаёт `CLIPTextEncode`, а его копия проходит через `ConditioningZeroOut` в negative.

Выход `GUIDER` подключён к `SamplerCustomAdvanced`. Noise, sampler, sigmas и latent остаются общими для двух model predictions; раздельных расписаний sigma у ноды нет.

Если model_negative отсутствует, связка совпадает по классу guider с обычным `CFGGuider`. Это fallback, а не скрытая копия второй модели.

## Практический пример

Полный census 0.1.42 нашёл 2 `DualModelGuider` в двух файлах, одном top-level UUID и двух subgraphs; root occurrences нет. Оба mode 0, оба имеют widget `[7]` и ведут в `SamplerCustomAdvanced.guider`.

Файлы — `image_ideogram4_t2i` и `image_ideogram4_t2i_int8`. В обоих main model приходит от `CFGOverride`, model_negative — от `UNETLoader`, positive — от `CLIPTextEncode`, negative — от `ConditioningZeroOut`.

Изолированная проба exact execute подтвердила три ветви: fallback к обычному CFGGuider без model_negative, создание `Guider_DualModel` с отдельной моделью и подстановку null condition без negative. Числовая formula probe с `C=30`, `U=10`, cfg 4 дала 90. Реальные модели не запускались.

## Частые ошибки и способы проверки

**Меняют модели местами.** `model` всегда считает conditional, `model_negative` — unconditional. Порядок влияет на формулу.

**Считают optional negative нулевым тензором.** При пустом порте создаётся `[None, {}]` без cross-attention. `ConditioningZeroOut` сохраняет структуру и metadata, поэтому это другой случай.

**Используют несовместимые latent formats.** Вторая модель отдельно обрабатывает latent input, но predictions затем смешиваются напрямую. Проверяйте официальную пару.

**Ждут загрузки negative model при cfg 1.** `outer_sample` не подготавливает её, когда сохранённый cfg близок к 1. Флаг `disable_cfg1_optimization` из model options не отменяет этот ранний skip.

**Принимают experimental за category.** Здесь runtime действительно содержит `experimental: true`; это не вывод из имени раздела.

## Производительность и внутреннее поведение

При подключённой `model_negative` и cfg не равном 1 загружаются и выполняются две модели. Negative model проходит собственный `prepare_sampling`, `pre_run`, latent conversion и `cleanup`; пиковая VRAM/RAM может быть значительно выше обычного CFG одной моделью.

Основная и negative модели выполняются последовательно в `predict_noise`. Для negative branch код удаляет `multigpu_clones` из model options и прямо отмечает TODO о полноценной multi-GPU поддержке этой ветви.

При cfg 1 отдельная модель не подготавливается, и возвращается conditional prediction. Если model_negative вообще не подключена, используется базовый CFGGuider и его стандартные batching/optimization правила.

## Совместимость, изменения и статус

Статья закреплена на ComfyUI `0.32.0`, frontend `1.48.7`, runtime ID `DualModelGuider`, модуле `comfy_extras.nodes_custom_sampler`. Fingerprint: `sha256:376e3f9392576aa4e52f9aaa9baeb8f6e6d3165b622f1ec914d97ddd3a4323e3`.

Runtime выставляет `experimental: true`; deprecated, dev-only и API-node flags равны false. Это не output node, replacement для ID отсутствует, execution aliases не зафиксированы.

Embedded docs 0.5.9 хорошо отражают optional inputs и text-free pass, но не раскрывают cfg=1 ранний skip, separate lifecycle, fallback class и compatibility risks.

## Связанные ноды и источники

`CFGGuider` считает обе ветви одной моделью. `DualCFGGuider` считает три conditions одной моделью. `ConditioningZeroOut` создаёт нулевые тензоры, но не равен отсутствующему negative. `CLIPTextEncode` формирует positive в официальном Ideogram case.

- [Реализация `DualModelGuider`](https://github.com/Comfy-Org/ComfyUI/blob/c2bcbecd82ec5ae66594340b395c24ef0217b238/comfy_extras/nodes_custom_sampler.py#L914-L989)
- [Стандартная CFG-формула](https://github.com/Comfy-Org/ComfyUI/blob/c2bcbecd82ec5ae66594340b395c24ef0217b238/comfy/samplers.py#L592-L605)
- [Embedded docs 0.5.9 для `DualModelGuider`](https://github.com/Comfy-Org/embedded-docs/blob/1d258cf6e374d60d138a2bfcd273c7e11f750ef9/comfyui_embedded_docs/docs/DualModelGuider/en.md)
- [Официальный workflow bundle 0.1.42](https://pypi.org/project/comfyui-workflow-templates-json/0.1.42/)
