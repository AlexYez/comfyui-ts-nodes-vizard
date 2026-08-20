# CFGGuider: классическое classifier-free guidance

## Что делает нода

`CFGGuider` связывает одну модель с positive и negative `CONDITIONING`, запоминает коэффициент `cfg` и возвращает `GUIDER` для custom sampling.

Без пользовательского `sampler_cfg_function` итоговый прогноз на каждом шаге равен `U + cfg × (C − U)`, где `C` — conditional-прогноз по positive, а `U` — unconditional-прогноз по negative. При `cfg = 0` остаётся `U`; при `1` результат равен `C`; значения выше 1 экстраполируют от negative к positive.

Нода не кодирует prompt и не запускает denoise. Она настраивает объект, который выполняет формулу внутри `SamplerCustomAdvanced`.

## Когда использовать и когда не использовать

Используйте `CFGGuider` для явного custom-sampling графа с обычной positive/negative парой. Он нужен, когда sampler, sigmas, noise и guider собираются отдельными нодами.

Не переносите число cfg из другого семейства моделей без проверки. Официальные шаблоны 0.1.42 используют значения от 1 до 6, а runtime разрешает 0–100. Допустимый диапазон интерфейса не означает полезный диапазон конкретной модели.

Если negative-ветвь не нужна по архитектуре, `BasicGuider` выражает это прямо. Для двух положительных условий используйте `DualCFGGuider`; для разных моделей conditional и unconditional — `DualModelGuider`.

## Короткий рецепт подключения

1. Подайте `MODEL` из совместимого loader или model-patch цепочки.
2. Подключите positive и negative `CONDITIONING`.
3. Начните с cfg из официального шаблона вашей модели.
4. Соедините `GUIDER` со входом `SamplerCustomAdvanced.guider`.
5. Держите noise, sigmas, sampler и latent неизменными при сравнении cfg.

Fragment «CFGGuider с cfg 3,5» повторяет топологию Chroma: два внешних CONDITIONING и MODEL входят в guider, а GUIDER идёт в `SamplerCustomAdvanced`. Он не включает модель или тексты prompt; структура проверена, полный граф не выполнялся.

## Входы, выходы и параметры

Обязательные входы: `model: MODEL`, `positive: CONDITIONING`, `negative: CONDITIONING`. `cfg` — `FLOAT` с default 8, диапазоном 0–100, шагом 0,1 и округлением widget до 0,01.

Выход один: `GUIDER`, не list-output. Нода не выдаёт denoised LATENT и не меняет входные conditioning при создании объекта.

Positive и negative — названия ролей, а не проверка содержимого. Пустой текст, `ConditioningZeroOut`, area metadata или control hooks остаются частью переданного CONDITIONING.

## Типовые связки

Обычная цепочка: два `CLIPTextEncode → CFGGuider → SamplerCustomAdvanced`. Модель может пройти через `ModelSamplingAuraFlow`, `ModelSamplingSD3`, LoRA или cache patch до guider.

Для img2video и video conditioning positive/negative часто формируют специализированные ноды — `LTXVConditioning`, `LTXVCropGuides`, `ReferenceLatent`. `CFGGuider` не требует, чтобы источник был именно CLIPTextEncode.

Условие с `ConditioningZeroOut` остаётся полноценной ветвью по структуре, но его тензоры нулевые. Это отличается от отсутствующего condition и от текстового negative prompt.

## Практический пример

В полном census 0.1.42 найдены 62 `CFGGuider` в 35 файлах и 15 разных top-level UUID: 8 в root, 54 в subgraphs. Mode 0 имеют 56 нод; ещё 6 сохранены в mode 4 и не являются активными доказательствами исполнения.

Распределение значений: cfg 1 — 41 раз, 6 — 8, 5 — 7, 3,5 — 2, 3 — 2, 4 — 2. Среди активных нод cfg 1 встречается 35 раз. Все 62 выхода соединены с `SamplerCustomAdvanced.guider`.

В `image_chroma_text_to_image`, UUID `b2d37916-fab5-425f-850d-7a64886e4d54`, `ModelSamplingAuraFlow #701`, positive `CLIPTextEncode #748` и negative `#749` входят в `CFGGuider #694` с cfg 3,5; GUIDER идёт в `SamplerCustomAdvanced #747`.

## Частые ошибки и способы проверки

**Считают negative списком запретов.** В формуле это baseline-прогноз `U`. Его содержание и metadata участвуют во всём вычислении.

**Ожидают два прохода при cfg 1.** Стандартная sampling function пропускает unconditional condition, если `disable_cfg1_optimization` не включён.

**Ставят cfg 0 для отключения guidance.** Результат становится `U`, а не conditional-прогнозом. Для `C` используйте 1.

**Игнорируют custom CFG hooks.** `sampler_cfg_function` может заменить стандартную формулу; pre/post hooks также могут изменить predictions. Проверяйте model options.

**Подключают GUIDER к обычному KSampler.** Нужен custom-sampling consumer с портом `GUIDER`.

## Производительность и внутреннее поведение

Обычно CFG требует conditional и unconditional прогнозов на каждом шаге. `calc_cond_batch` может объединять совместимые conditions в batch, но вычислительная и memory-нагрузка всё равно выше одного conditional-прохода.

При cfg, близком к 1 через `math.isclose`, unconditional condition заменяется на `None`, если optimization не запрещена. Это объясняет частое значение 1 в официальных distilled/video шаблонах.

Перед стандартной формулой могут работать `sampler_pre_cfg_function`, вместо неё — `sampler_cfg_function`, после неё — список `sampler_post_cfg_function`. Поэтому algebra статьи описывает default path.

## Совместимость, изменения и статус

Статья закреплена на ComfyUI `0.32.0`, frontend `1.48.7`, runtime ID `CFGGuider`, модуле `comfy_extras.nodes_custom_sampler`. Fingerprint: `sha256:d530e8a2677744e82d15018b1a3e4642acce83a73ff385811960dd66fa4d701b`.

Runtime flags deprecated, experimental, dev-only и API node равны false; это не output node. В списке replacements ID отсутствует, execution aliases не зафиксированы.

Embedded docs 0.5.9 верно перечисляют параметры, но описывают negative как «избегание нежелательного», не показывают формулу, cfg=0/1 и hook overrides.

## Связанные ноды и источники

`BasicGuider` оставляет один conditional-проход. `DualCFGGuider` вводит cond1/cond2/negative и две шкалы. `DualModelGuider` может считать `C` и `U` разными моделями. `CLIPTextEncode` и `ConditioningZeroOut` создают разные виды входных условий.

- [Реализация ноды `CFGGuider`](https://github.com/Comfy-Org/ComfyUI/blob/c2bcbecd82ec5ae66594340b395c24ef0217b238/comfy_extras/nodes_custom_sampler.py#L831-L854)
- [Стандартная CFG-формула и cfg=1 branch](https://github.com/Comfy-Org/ComfyUI/blob/c2bcbecd82ec5ae66594340b395c24ef0217b238/comfy/samplers.py#L592-L627)
- [Embedded docs 0.5.9 для `CFGGuider`](https://github.com/Comfy-Org/embedded-docs/blob/1d258cf6e374d60d138a2bfcd273c7e11f750ef9/comfyui_embedded_docs/docs/CFGGuider/en.md)
- [Официальный workflow bundle 0.1.42](https://pypi.org/project/comfyui-workflow-templates-json/0.1.42/)
