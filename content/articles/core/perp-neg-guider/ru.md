# PerpNegGuider: перпендикулярная negative-компонента

## Что делает нода

`PerpNegGuider` собирает экспериментальный `GUIDER` из модели и трёх условий: positive, negative и empty baseline. Он отделяет в negative-направлении часть, параллельную positive, и вычитает только оставшуюся перпендикулярную компоненту.

Замысел отличается от обычного CFG. Стандартный `CFGGuider` смешивает positive и negative predictions напрямую; здесь empty prediction служит общей точкой отсчёта, а параметр `neg_scale` управляет ортогональной частью negative.

## Место в графе

Подайте `MODEL` и три совместимых `CONDITIONING` во входы `PerpNegGuider`, затем соедините выход `GUIDER` со входом `SamplerCustomAdvanced.guider`. Noise, sampler, sigmas и latent подключаются к consumer отдельно.

Нода не совместима с обычным `KSampler` по типу выхода: KSampler не принимает `GUIDER`. Не нужно ставить рядом ещё один `CFGGuider`; они являются разными стратегиями для одного и того же места в custom-sampling graph.

## Входы

Обязательны `model: MODEL`, `positive: CONDITIONING`, `negative: CONDITIONING` и `empty_conditioning: CONDITIONING`. Empty-вход должен быть реальным baseline для того же encoder/model family, обычно conditioning пустого prompt; нода не создаёт его автоматически и не проверяет смысл.

`cfg: FLOAT` имеет default 8, диапазон 0–100, шаг 0,1 и округление 0,01. `neg_scale: FLOAT` имеет default 1, диапазон 0–100, шаг 0,01 и помечен advanced. Все шесть входов required.

## Выходы

Единственный выход — `GUIDER`, экземпляр специализированного класса `Guider_PerpNeg`. Это не MODEL, CONDITIONING или LATENT и не list-output.

Объект хранит подготовленные условия, cfg и neg_scale. Реальные tensor predictions вычисляются позже, когда `SamplerCustomAdvanced` вызывает guider на каждом sigma.

## Как работает внутри

Обозначим predictions как `P` для positive, `N` для negative и `E` для empty. Код строит `p = P − E`, `n = N − E`, затем `n⊥ = n − (<n,p> / ||p||²) × p`. Итог равен `E + cfg × (p − neg_scale × n⊥)`.

Скалярное произведение и норма суммируются по всему tensor. Это не отдельная проекция для каждого batch item, channel или пикселя. Перед формулой guider вызывает pre-CFG hooks, после неё — post-CFG hooks; обычную `sampler_cfg_function` он обходит.

## Настройки

`neg_scale = 1` использует полную перпендикулярную часть negative. При `neg_scale = 0` negative prediction можно не вычислять; результат становится empty-baseline CFG `E + cfg × (P − E)`, а не стандартной формулой с поданным negative.

При `cfg = 0` математический итог равен `E`, но код всё равно сначала вычисляет проекцию. Начинайте с умеренных значений, меняйте по одному параметру и фиксируйте noise, sigmas и модель. UI-диапазон 0–100 не является рекомендацией.

## Пример подключения

Полный scan 512 JSON официального bundle 0.1.42, включая 272 subgraphs, не нашёл ни одной `PerpNegGuider`; точных строковых упоминаний ID также нет. Значит, готового официального preset для параметров в этой версии нет.

Source-derived fragment соединяет `PerpNegGuider` с `SamplerCustomAdvanced`, оставляет MODEL, три CONDITIONING, NOISE, SAMPLER, SIGMAS и LATENT внешними и использует defaults `cfg = 8`, `neg_scale = 1`. Типы и структура проверены; fragment не импортировался и не выполнялся с моделью.

## Частые ошибки

**Подают обычный negative вместо empty baseline.** Входы играют разные роли. Empty должен представлять нейтральное условие того же encoder path.

**Считают `neg_scale = 0` обычным CFG.** Поданный negative тогда исключается, а baseline остаётся empty conditioning.

**Игнорируют нулевое positive-направление.** В формуле нет epsilon. Если `P − E` имеет нулевую норму, деление может породить NaN.

**Ожидают независимость элементов batch.** Dot product и norm глобальны; один элемент может влиять на коэффициент проекции остальных.

**Подключают MODEL patch с custom CFG function.** PerpNegGuider обходит `sampler_cfg_function`; например, линейная и треугольная video CFG patches не меняют его формулу.

## Ограничения и производительность

Обычно нужны три predictions: positive, negative и empty. `calc_cond_batch` получает их одним вызовом и может объединять совместимые conditions, но это не гарантирует один физический model forward при любом объёме памяти и metadata.

Есть оптимизация: при `neg_scale = 0` negative condition заменяется на `None`; если одновременно `cfg = 1`, также исключается empty. При включённом `disable_cfg1_optimization` эти сокращения не применяются.

Глобальная проекция требует дополнительных tensor operations, но они обычно дешевле diffusion predictions. Численная устойчивость не защищена epsilon или clamp. Проверяйте outputs на finite values, особенно если positive и empty близки.

## Совместимость и источники

Статья закреплена на ComfyUI `0.32.0`, frontend `1.48.7`, runtime ID `PerpNegGuider`, модуле `comfy_extras.nodes_perpneg`. Fingerprint: `sha256:74a7a7f40a3157ebad5bcc5137c65f80a980452778d01d54d38cd0f094ec8be6`. Runtime явно отмечает `experimental=true`; deprecated, dev_only и api_node равны false. Replacement и execution aliases отсутствуют.

В том же source есть старая нода `PerpNeg`, отмеченная deprecated и заменённая `PerpNegGuider`. Это отдельный runtime ID, а не alias текущей ноды. Embedded docs 0.5.9 перечисляют входы, но не раскрывают глобальную редукцию, отсутствие epsilon и обход `sampler_cfg_function`.

- [Реализация и формула `PerpNegGuider`](https://github.com/Comfy-Org/ComfyUI/blob/c2bcbecd82ec5ae66594340b395c24ef0217b238/comfy_extras/nodes_perpneg.py#L12-L151)
- [Стандартный CFG path для сравнения](https://github.com/Comfy-Org/ComfyUI/blob/c2bcbecd82ec5ae66594340b395c24ef0217b238/comfy/samplers.py#L592-L627)
- [Embedded docs 0.5.9](https://github.com/Comfy-Org/embedded-docs/blob/1d258cf6e374d60d138a2bfcd273c7e11f750ef9/comfyui_embedded_docs/docs/PerpNegGuider/en.md)
- [Официальный workflow bundle 0.1.42](https://pypi.org/project/comfyui-workflow-templates-json/0.1.42/)
