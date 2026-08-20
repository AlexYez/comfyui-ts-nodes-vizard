# ControlNetApplyAdvanced: где и с какой силой действует ControlNet

`ControlNetApplyAdvanced` добавляет изображение-подсказку и модель ControlNet к двум ветвям `CONDITIONING`: positive и negative. Нода не меняет диффузионную `MODEL` и не запускает sampling — она записывает объект контроля в metadata conditioning, которое затем получает sampler.

## Нода принимает обе ветви conditioning

На вход нужны positive, negative, `CONTROL_NET` и `IMAGE`. Выходы тоже называются positive и negative, поэтому их следует вести в соответствующие входы sampler без перестановки.

Если `strength = 0`, функция сразу возвращает исходные объекты conditioning. В этом случае она не копирует metadata, не подготавливает изображение и не добавляет ControlNet.

## strength умножает residual ControlNet

Диапазон `strength` — от 0 до 10, значение по умолчанию — 1. ControlNet вычисляет свои residual, после чего базовый режим `CONSTANT` умножает каждый из них на заданную силу.

Число 1 не гарантирует «правильную» силу для любой пары моделей. Значения выше 1 усиливают residual математически, но могут чрезмерно прижать результат к карте контроля или дать артефакты.

## start_percent и end_percent задают участок sampling

Оба параметра лежат в диапазоне 0–1. Перед sampling ComfyUI переводит проценты в timesteps модели; ControlNet возвращает управление только внутри получившегося интервала.

Нода не проверяет условие `start_percent ≤ end_percent`. Ставьте начало не позже конца: для обратного диапазона в source нет особой «инверсной» семантики.

## IMAGE становится BCHW-подсказкой

ComfyUI хранит `IMAGE` как BHWC, а нода переставляет последнюю ось каналов на вторую: `image.movedim(-1, 1)`. Этот BCHW tensor передаётся в копию ControlNet как исходный control hint.

Подсказка должна соответствовать назначению модели: Canny-ControlNet ждёт карту границ, depth-модель — карту глубины. Сам `ControlNetApplyAdvanced` не строит такую карту и не проверяет её смысл.

## VAE нужен только некоторым ControlNet

Порт `vae` необязательный в runtime-схеме. Если загруженный ControlNet хранит собственный latent format, `set_cond_hint` сохраняет переданный VAE. При первом `get_control` ControlNet масштабирует подсказку и кодирует её этим VAE. Без VAE `set_cond_hint` сначала пишет предупреждение, а `get_control` затем поднимает `ValueError`.

Во всех пяти официальных экземплярах wheel 0.1.42 VAE подключён. Это не превращает VAE в универсальное обязательное правило, но для неизвестной современной архитектуры безопаснее следовать её официальному workflow.

## Metadata копируется, embedding остаётся тем же

Для каждого элемента conditioning нода создаёт новый словарь metadata через `copy()`, но сохраняет исходный tensor embedding. Затем в копию добавляются ключи `control` и `control_apply_to_uncond`.

Так upstream conditioning не меняется на месте. Копирование неглубокое: вложенные значения metadata, кроме заменённого объекта контроля, остаются общими ссылками.

## Positive и negative получают явный ControlNet

Обе ветви проходят один и тот же алгоритм. Если их metadata указывает на одинаковый предыдущий ControlNet, нода переиспользует одну новую копию для обеих ветвей; это делает цепочку согласованной.

Флаг `control_apply_to_uncond` ставится в `false`. Это не отключает negative: ControlNet уже записан в каждый её элемент явно. Флаг запрещает sampler автоматически копировать control из positive в противоположную ветвь, как это делала legacy-нода.

## Предыдущий ControlNet сохраняется в цепочке

Если входное conditioning уже содержит ключ `control`, новая копия вызывает `set_previous_controlnet` для этого объекта. Во время sampling предыдущая сеть вычисляется рекурсивно, а её residual складываются с residual новой.

Чтобы не разорвать цепочку, передавайте оба выхода первой `ControlNetApplyAdvanced` в одноимённые входы второй. В официальном wheel такой двухступенчатой пары нет; механизм подтверждён исходником, а не шаблоном.

## Официальные примеры используют полный диапазон

Полный просмотр 496 root workflow и 272 subgraph нашёл пять `ControlNetApplyAdvanced`: три в root и две внутри subgraph. Все включены, имеют `start_percent = 0`, `end_percent = 1` и подключённый VAE.

Сила равна 1 в трёх случаях, 0,66 в SD3.5 Canny и сериализованному числу `0.7000000000000002` в SD3.5 Depth. Последнее — обычный след float-сериализации, а не особая настройка точности.

## Fragment показывает две перекрывающиеся ступени

Рецепт последовательно применяет два внешних ControlNet: первый действует на участке 0–0,65, второй — 0,35–1. Это учебные значения, а не настройки из официального шаблона. Для каждой ступени оставлены отдельные IMAGE и VAE-входы.

Fragment прошёл проверку схемы и точную source-level проверку цепочки на синтетических объектах, но модели ControlNet и полный граф в ComfyUI не исполнялись. Редактор пока не проверил материал вручную.

## Источники

- [ControlNetApplyAdvanced в ComfyUI v0.32.0](https://github.com/Comfy-Org/ComfyUI/blob/c2bcbecd82ec5ae66594340b395c24ef0217b238/nodes.py#L928-L976)
- [Диапазон, сила и цепочка в ControlBase](https://github.com/Comfy-Org/ComfyUI/blob/c2bcbecd82ec5ae66594340b395c24ef0217b238/comfy/controlnet.py#L83-L229)
- [Подготовка control hint через VAE](https://github.com/Comfy-Org/ComfyUI/blob/c2bcbecd82ec5ae66594340b395c24ef0217b238/comfy/controlnet.py#L269-L286)
- [Обработка control_apply_to_uncond в sampler](https://github.com/Comfy-Org/ComfyUI/blob/c2bcbecd82ec5ae66594340b395c24ef0217b238/comfy/samplers.py#L1050-L1073)
- [Официальный SD3.5 Canny workflow](https://github.com/Comfy-Org/workflow_templates/blob/cca1ea5ea4560108ecc2f44dee951f41ea433062/templates/sd3.5_large_canny_controlnet_example.json)
