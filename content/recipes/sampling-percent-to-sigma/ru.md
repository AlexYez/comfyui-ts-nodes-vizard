# Задать первую sigma по 25% sampling

`SamplingPercentToSigma` получает долю 0,25 и вычисляет одно model-specific значение. Оно идёт во вход `sigma` у `SetFirstSigma`, который заменяет только первый элемент внешнего `SIGMAS`.

Перед sampling проверьте, что новая первая sigma не ниже второй. Fragment не обрезает хвост расписания и не исправляет его порядок. `return_actual_sigma = false` выбран потому, что для внутренней доли 0,25 endpoint-флаг всё равно ничего не меняет.

Exact topology отсутствует в official wheel 0.1.42. Преобразование и замена проверены отдельно на синтетических данных, но полный граф с моделью не исполнялся. Редактор пока не проверил материал вручную.

## Источники

- [SamplingPercentToSigma](https://github.com/Comfy-Org/ComfyUI/blob/c2bcbecd82ec5ae66594340b395c24ef0217b238/comfy_extras/nodes_custom_sampler.py#L351-L376)
- [SetFirstSigma](https://github.com/Comfy-Org/ComfyUI/blob/c2bcbecd82ec5ae66594340b395c24ef0217b238/comfy_extras/nodes_custom_sampler.py#L276-L296)
