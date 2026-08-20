# CFGNorm: нормализация CFG по норме тензора

## Что делает нода

`CFGNorm` клонирует `MODEL` и меняет обработку classifier-free guidance. У ноды два разных режима. При `pre_cfg = false` она добавляет post-CFG hook и масштабирует уже смешанный результат. При `pre_cfg = true` она заменяет стандартную CFG-функцию, сначала сама смешивает conditional и unconditional tensors, затем выравнивает норму смеси по conditional tensor.

Runtime помечает ноду как экспериментальную. Она не подбирает `strength` под модель и не гарантирует улучшение результата: формула лишь меняет величину тензора по закреплённым правилам.

## Место в графе

Подайте `MODEL` после loader и model-sampling patches во вход `CFGNorm`, затем используйте `patched_model` в `KSampler`, `SamplerCustom` или guider. В официальных шаблонах встречаются цепочки `ModelSamplingAuraFlow → CFGNorm → KSampler` и `ModelSamplingFlux → CFGNorm → SamplerCustom`.

Порядок с другими CFG patches существенен. `pre_cfg = true` записывает единственную `sampler_cfg_function` и заменяет ранее установленную custom CFG-функцию. Default-режим добавляет post-hook в список; несколько post-hooks выполняются по порядку их добавления.

## Входы

`model: MODEL` и `strength: FLOAT` обязательны. У `strength` default 1, диапазон 0–100 и шаг 0,01. В разных режимах одно и то же число означает разное: post-режим умножает на него итог, pre-режим использует его как коэффициент смешения нормализованной и обычной CFG-комбинации.

`pre_cfg: BOOLEAN` — optional input с default `false`. При старой сериализации widget может отсутствовать; runtime тогда применяет false. Это поле есть в `/object_info` 0.32.0, хотя embedded docs 0.5.9 его ещё не описывают.

## Выходы

Единственный выход называется `patched_model` и имеет тип `MODEL`. Нода возвращает clone, поэтому исходный входной MODEL остаётся без нового hook.

Выход не является prediction, latent или guider. Формула срабатывает позже, когда sampler вызывает модель на очередной sigma.

## Как работает внутри

В post-режиме код берёт `cond_denoised` и текущий `denoised`, считает их нормы по оси каналов `dim=1`, затем вычисляет `scale = clamp(norm(cond) / (norm(result) + 1e−8), 0, 1)`. Возвращается `result × scale × strength`. При `strength = 1` этот scale не увеличивает норму; значение strength выше 1 уже может усилить итог.

В pre-режиме вычисляется обычная линейная смесь `comb = uncond + cfg × (cond − uncond)`. Её норма приводится к норме `cond` без верхнего clamp; нулевой `comb` оставляется нулевым. Затем `strength × rescaled + (1 − strength) × comb` выбирает промежуточный результат. При strength выше 1 это экстраполяция, а не доля от 0 до 1.

## Настройки

Для default post-режима `strength = 1` сохраняет формулу в её базовом виде. `strength = 0` возвращает нулевой tensor, а не отключает ноду. Чтобы сравнить граф без CFGNorm, обойдите patch отдельной MODEL-ветвью.

Для `pre_cfg = true` strength 0 оставляет стандартную линейную смесь, 1 полностью приводит её норму к conditional, а значения между 0 и 1 интерполируют. Значения выше 1 разрешены schema, но уходят за нормализованную точку. Подбирайте их только в контролируемом сравнении с одинаковыми seed, sigmas и sampler.

## Пример подключения

Полный census bundle 0.1.42 нашёл 33 `CFGNorm` в 19 файлах: одну в root и 32 в subgraphs; все mode 0. Widgets распределены так: 14 раз `[1]`, 18 раз `[1, false]` и один раз `[1, true]`.

Единственный официальный `pre_cfg = true` находится в `image_joyai_image_edit`, root UUID `b2c3d4e5-f6a7-4890-91bc-def012345678`, subgraph `7f6dd18d-96db-4ad7-a173-6f6d8a0c3d01`. `UNETLoader #3 → CFGNorm #12 → KSampler #10`; KSampler хранит 40 steps, cfg 4, Euler, normal и denoise 1. Fragment повторяет эту локальную топологию, но не включает веса и не выполнялся.

Tooltip связывает `pre_cfg = true` с моделями вроде Lens, однако оба закреплённых шаблона `image_lens_t2i` и `image_lens_turbo_t2i` сериализуют `[1, false]`. Версии source и templates зафиксированы как есть; из этого расхождения нельзя выводить новый рекомендованный preset.

## Частые ошибки

**Считают `strength = 0` выключателем.** Это верно только для pre-режима. В post-режиме выход формулы обнуляется.

**Не замечают `pre_cfg`.** Старые embedded docs показывают только strength. Сверяйте actual runtime schema и сериализованный второй widget.

**Ожидают одну формулу в обоих режимах.** False ставит post-hook с clamp до 1; true заменяет CFG combine и допускает увеличение нормы.

**Складывают custom CFG patches.** В pre-режиме ближайшая нода, которая снова вызовет `set_model_sampler_cfg_function`, перезапишет функцию.

**Считают норму глобальной.** Код сворачивает только `dim=1`; для тензора `[B,C,H,W]` масштаб различается по batch item и пространственной позиции.

## Ограничения и производительность

Нормы и поэлементное масштабирование заметно дешевле model forward, но выполняются на каждом sampling step. Память нужна для смеси, норм и промежуточного rescaled tensor.

В pre-режиме защита `clamp_min(1e−12)` не допускает деления на очень малую норму; отдельная ветка оставляет scale равным 1 при точном нуле. В post-режиме используется добавка `1e−8` и clamp 0–1.

Нода не отключает cfg=1 optimization. При `cond_scale = 1` standard sampling может не вычислять unconditional condition. Для pre-формулы это обычно сводит смесь к conditional tensor, но взаимодействие с другими hooks нужно проверять в их фактическом порядке.

## Совместимость и источники

Статья закреплена на ComfyUI `0.32.0`, frontend `1.48.7`, runtime ID `CFGNorm`, модуле `comfy_extras.nodes_cfg`. Fingerprint: `sha256:86e72419cab85ab8535177b18a883e6bf81d7b2d8eaba29408543f7afc9cc8f8`. Runtime flags: experimental true; deprecated, dev_only и api_node false. Replacement и execution aliases отсутствуют.

Embedded docs 0.5.9 не знают `pre_cfg`, называют сравниваемые tensors conditional и unconditional и обещают стабилизацию. Закреплённый default-source сравнивает `cond_denoised` с уже смешанным `denoised`; доказательства общей «стабилизации» в реализации нет.

- [Реализация `CFGNorm`](https://github.com/Comfy-Org/ComfyUI/blob/c2bcbecd82ec5ae66594340b395c24ef0217b238/comfy_extras/nodes_cfg.py#L51-L109)
- [CFG dispatch и hooks](https://github.com/Comfy-Org/ComfyUI/blob/c2bcbecd82ec5ae66594340b395c24ef0217b238/comfy/samplers.py#L592-L627)
- [Embedded docs 0.5.9](https://github.com/Comfy-Org/embedded-docs/blob/1d258cf6e374d60d138a2bfcd273c7e11f750ef9/comfyui_embedded_docs/docs/CFGNorm/en.md)
- [Официальный workflow bundle 0.1.42](https://pypi.org/project/comfyui-workflow-templates-json/0.1.42/)
