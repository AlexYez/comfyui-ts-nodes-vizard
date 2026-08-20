# DualCFGGuider: две условные ветви и negative

## Что делает нода

`DualCFGGuider` получает три CONDITIONING и вычисляет три прогноза: `P` для `cond1`, `M` для `cond2` и `N` для `negative`. Два коэффициента задают, как они смешиваются.

В режиме `regular` default path равен `N + cfg_cond2_negative × (M − N) + cfg_conds × (P − M)`. В режиме `nested` сначала вычисляется `T = M + cfg_conds × (P − M)`, затем результат `N + cfg_cond2_negative × (T − N)`. Поэтому во вложенном режиме вклад `(P − M)` дополнительно умножается на вторую шкалу.

Перед расчётом нода копирует entries `cond2`, копирует словарь metadata каждого entry и записывает туда `prompt_type = negative`; исходный список не меняется. Это часть внутренней подготовки hooks/conditions, а не переименование порта.

## Когда использовать и когда не использовать

Используйте ноду для моделей и официальных graph patterns, которым нужны две условные ветви относительно общего negative: например, отдельные image-edit conditions или два prompt-представления.

Не считайте `cond1` и `cond2` симметричными. Формула строит направление `P − M`, а затем связывает `M` с `N`. Перестановка портов меняет результат даже при тех же коэффициентах.

Если у вас только positive и negative, `CFGGuider` проще и дешевле. Если conditional и unconditional должны считаться разными MODEL, нужен `DualModelGuider`, а не второй conditioning-порт.

## Короткий рецепт подключения

1. Подайте совместимый `MODEL`.
2. Подключите основное условие к `cond1`, промежуточное или второе — к `cond2`, baseline — к `negative`.
3. Для официальной HiDream/OmniGen конфигурации начните с `cfg_conds = 5`, `cfg_cond2_negative = 2`.
4. Выберите `regular`: все закреплённые official cases используют его.
5. Передайте GUIDER в `SamplerCustomAdvanced` и сравните с `nested` только при фиксированных остальных входах.

Fragment «Dual CFG regular: 5 и 2» повторяет проверенные widgets и типовую связь с custom sampler. Три CONDITIONING оставлены внешними, потому что их точная семантика зависит от модели. Fragment проверен по schema/runtime, но не выполнялся.

## Входы, выходы и параметры

Обязательны `model: MODEL`, `cond1`, `cond2`, `negative: CONDITIONING`. `cfg_conds` и `cfg_cond2_negative` — FLOAT с default 8, диапазоном 0–100, шагом 0,1 и round 0,01.

`style` — COMBO с двумя exact options: `regular` и `nested`. Выход — один `GUIDER`, не list-output. Runtime search alias `dual prompt guidance` записан в `searchAliases`, но не является execution ID.

Параметр `cfg_conds` относится к разности cond1–cond2. `cfg_cond2_negative` относится к cond2–negative в regular и ко всему внутреннему результату относительно negative в nested.

## Типовые связки

В HiDream `InstructPixToPixConditioning` выдаёт два conditions прямо в `cond1` и `cond2`, а отдельный `CLIPTextEncode` подаёт negative. MODEL проходит через Reroute; GUIDER и LATENT из edit-conditioning сходятся в `SamplerCustomAdvanced`.

В OmniGen 2 два `ReferenceLatent` формируют cond1/cond2, обычный `CLIPTextEncode` — negative, а MODEL приходит из `UNETLoader`. Это другая upstream topology с теми же widgets 5, 2, regular.

В каждый порт можно передать список conditioning entries с area, hooks и control metadata. Нода не объединяет эти списки заранее: sampler считает predictions для трёх ролей.

## Практический пример

Полный census 0.1.42 нашёл 4 `DualCFGGuider` в 4 файлах и 2 разных top-level UUID: 3 в root и 1 в subgraph. Все mode 0 и все четыре выхода идут в `SamplerCustomAdvanced.guider`.

Значения widgets: один случай `[3, 1.5, "regular"]` в `hidream_e1_1`; три случая `[5, 2, "regular"]` в `hidream_e1_full`, `image_omnigen2_image_edit` и `image_omnigen2_t2i`. Режим `nested` в официальном bundle не встречается.

Изолированная проба закреплённого класса использовала `N=10`, `M=20`, `P=30`, шкалы 2 и 3. `regular` дал 60, `nested` — 100. Так проверено различие формул без запуска модели.

## Частые ошибки и способы проверки

**Считают обе шкалы независимыми весами prompt.** В regular это веса двух разностей, а в nested вторая шкала умножает и внутренний вклад cond1.

**Переставляют cond1 и cond2.** Направление `P − M` меняется. Подключайте порты по официальной схеме конкретной модели.

**Ожидают nested case из official templates.** В bundle 0.1.42 их нет; nested подтверждён исходником и числовой пробой, но не полным workflow.

**Полагаются на cfg=1 одинаково в двух стилях.** Regular явно убирает negative при второй шкале 1 и затем cond2 при обеих шкалах 1. Nested заранее считает все три ветви.

**Игнорируют CFG hooks.** Внутренний `cfg_function` может быть заменён model options; показанные формулы относятся к default path.

## Производительность и внутреннее поведение

Без оптимизации sampler считает три conditioning predictions вместо двух у обычного CFG. Совместимые conditions могут батчироваться, но memory и compute всё равно возрастают.

В `regular`, если `disable_cfg1_optimization` false и `cfg_cond2_negative` близок к 1, negative condition заменяется на `None`. Если одновременно `cfg_conds` близок к 1, cond2 тоже заменяется на `None`; остаётся cond1.

В `nested` такой явной ветки нет: `calc_cond_batch` сразу получает negative, cond2 и cond1. `cfg_function` применяется один раз — к паре cond1/cond2; внешнее смешение с negative записано прямой арифметикой. В `regular` hook, наоборот, получает cond2/negative, а добавка cond1–cond2 вычисляется после него. Поэтому custom CFG hook не заменяет обе части ни одной из формул.

## Совместимость, изменения и статус

Статья закреплена на ComfyUI `0.32.0`, frontend `1.48.7`, runtime ID `DualCFGGuider`, модуле `comfy_extras.nodes_custom_sampler`. Fingerprint: `sha256:f7494f04202bf60700ef80108f6e0ec370b656a9d4e1a3bc4781b363a53aaa1a`.

Runtime не помечает ноду deprecated, experimental, dev-only или API-only; это не output node. Replacements для ID нет. Единственный runtime search alias — `dual prompt guidance`; execution aliases пусты.

Embedded docs 0.5.9 перечисляют две шкалы и styles, но не приводят формулы, metadata `prompt_type`, regular cfg=1 optimization и отсутствие nested в официальных workflows.

## Связанные ноды и источники

`CFGGuider` смешивает только C и U. `BasicGuider` оставляет один прогноз. `DualModelGuider` разделяет модели, а не conditions. Источниками cond1/cond2 могут быть `InstructPixToPixConditioning`, `ReferenceLatent` или обычные text conditions.

- [Реализация `DualCFGGuider` и обе формулы](https://github.com/Comfy-Org/ComfyUI/blob/c2bcbecd82ec5ae66594340b395c24ef0217b238/comfy_extras/nodes_custom_sampler.py#L856-L912)
- [Копирование и обновление conditioning metadata](https://github.com/Comfy-Org/ComfyUI/blob/c2bcbecd82ec5ae66594340b395c24ef0217b238/node_helpers.py#L9-L22)
- [Базовая `cfg_function`](https://github.com/Comfy-Org/ComfyUI/blob/c2bcbecd82ec5ae66594340b395c24ef0217b238/comfy/samplers.py#L592-L605)
- [Embedded docs 0.5.9 для `DualCFGGuider`](https://github.com/Comfy-Org/embedded-docs/blob/1d258cf6e374d60d138a2bfcd273c7e11f750ef9/comfyui_embedded_docs/docs/DualCFGGuider/en.md)
- [Официальный workflow bundle 0.1.42](https://pypi.org/project/comfyui-workflow-templates-json/0.1.42/)
