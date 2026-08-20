# RenormCFG: порог и ограничение нормы guidance для Lumina 2

`RenormCFG` из модуля Lumina 2 клонирует модель и ставит собственную sampler CFG-функцию. Ниже порога `cfg_trunc` она вычисляет guidance для первых `in_channels` и при необходимости ограничивает его норму; на пороге и выше берёт conditional output без CFG.

## Что делает нода

Hook делит model output по каналам. Первые `in_channels` считаются epsilon-частью, оставшиеся — дополнительной частью модели. CFG применяется только к epsilon-части. Дополнительные каналы всегда копируются из conditional output; corresponding unconditional остаток вычисляется, но не используется.

Возвращается `x_orig - cfg_result`, то есть форма, которую ожидает sampler CFG hook. Нода не меняет conditioning и не создаёт guider; она вмешивается в объединение уже рассчитанных conditional/unconditional выходов.

## Место в графе

Ставьте patch после загрузки Lumina 2 модели и перед guider/sampler. Выход используйте во всей sampling-ветви. Current official `image_netayume_lumina_t2i` использует `ModelSamplingAuraFlow` и обычный `KSampler` с CFG 4, но не содержит `RenormCFG`; следовательно, этот patch не является обязательной частью каждого Lumina workflow.

Как и `RescaleCFG`, нода занимает единственный `sampler_cfg_function` slot. Последующий CFG patch заменит её, а не добавит вторую обработку.

## Входы

- `model` — модель, из которой читается `diffusion_model.in_channels` и которая затем клонируется.
- `cfg_trunc` — advanced float 0–100, по умолчанию 100.
- `renorm_cfg` — advanced float 0–100, по умолчанию 1.

Фактический CFG scale приходит из guider. Порог сравнивается с `timestep[0]`, без нормализации к процентам и без проверки шкалы конкретного model sampling.

## Выход

Выход — cloned `MODEL` с sampler CFG hook. Исходная модель не меняется. Hook замыкает ссылку на входной `model`, чтобы читать `in_channels`; клон и оригинал используют одну архитектурную конфигурацию каналов.

Нода не возвращает сообщение, какая ветвь порога сработала. Это можно выяснить только по текущему timestep или отдельной диагностике.

## Как работают порог и renorm

Если `timestep[0] < cfg_trunc`, epsilon-часть считается как `uncond + cond_scale * (cond - uncond)`. При `renorm_cfg > 0` source сравнивает её векторную норму с `norm(cond) * renorm_cfg`. Если новая норма не меньше лимита, guided epsilon умножается на отношение лимита к текущей норме.

Если timestep равен порогу или выше, CFG полностью пропускается: epsilon и дополнительные каналы берутся из conditional output. Условие строгое, поэтому значение ровно 100 при default `cfg_trunc = 100` попадает во вторую ветвь.

## Параметры и настройка

`renorm_cfg = 0` выключает ограничение нормы в нижней ветви, но не выключает threshold-логику. `renorm_cfg = 1` ограничивает guided epsilon нормой conditional epsilon. Значение больше 1 разрешает пропорционально больший предел.

`cfg_trunc` имеет смысл только вместе со шкалой timestep модели. Не трактуйте 100 как 10% или 100 шагов без проверки `model_sampling`. Для другого multiplier/shift одна и та же цифра может соответствовать иной части траектории.

## Проверенный пример

Fragment Wizard ставит `cfg_trunc = 100`, `renorm_cfg = 1` и подключает patched модель к `CFGGuider` с CFG 4 — тем же serialized CFG, который встречается в официальном NetaYume Lumina workflow, хотя сам `RenormCFG` там отсутствует. Positive/negative conditioning остаются внешними.

Exact hook проверен на синтетическом output с отдельными epsilon/rest каналами: подтверждены CFG-ветвь, conditional rest, граница timestep 100 и cap нормы. Полный scan 512 JSON не нашёл direct node. Реальная Lumina модель не запускалась. Редактор пока не проверил материал вручную.

## Частые ошибки

- Patch считается обязательным для Lumina, хотя текущий официальный шаблон обходится без него.
- `cfg_trunc` принимается за процент вместо raw timestep.
- `renorm_cfg = 0` считается полным bypass, но ветвь на timestep всё равно меняет CFG.
- После ноды ставится другой CFG patch и заменяет hook.
- Batch больше одного запускается без проверки: версия 0.32.0 падает на булевой проверке многoэлементного тензора.
- Нулевая conditional и guided нормы приводят к делению `0 / 0` и `NaN`.

## Ограничения и производительность

Нормы считаются по всем не-batch измерениям epsilon-части. Для batch 1 это работает; для batch больше одного `new_pos_norm >= max_new_norm` возвращает несколько boolean, а обычный Python `if` вызывает ошибку неоднозначности. Это подтверждённый дефект 0.32.0.

При обеих нулевых нормах условие истинно и масштаб равен `0/0`, поэтому output становится нечисловым. Нода не добавляет epsilon и не проверяет конечность. Дополнительные каналы никогда не получают unconditional/CFG смесь.

## Совместимость и источники проверки

Проверено на ComfyUI 0.32.0 и frontend 1.48.7. Нода V3 не помечена experimental, deprecated, dev-only или API-only. Formal replacement отсутствует.

Embedded docs 0.5.9 описывают общую идею, но не раскрывают строгую границу, разделение каналов, batch>1 defect и zero-norm `NaN`. Эти факты взяты из exact source и tensor probe. Official workflow используется только как реальный Lumina-контекст и явно не содержит patch.

### Источники

- [RenormCFG в ComfyUI v0.32.0](https://github.com/Comfy-Org/ComfyUI/blob/c2bcbecd82ec5ae66594340b395c24ef0217b238/comfy_extras/nodes_lumina2.py#L7-L64)
- [Официальный `image_netayume_lumina_t2i`](https://github.com/Comfy-Org/workflow_templates/blob/cca1ea5ea4560108ecc2f44dee951f41ea433062/templates/image_netayume_lumina_t2i.json)
- [Embedded docs 0.5.9 для RenormCFG](https://github.com/Comfy-Org/embedded-docs/blob/1d258cf6e374d60d138a2bfcd273c7e11f750ef9/comfyui_embedded_docs/docs/RenormCFG/en.md)
