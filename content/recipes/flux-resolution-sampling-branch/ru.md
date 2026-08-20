# Flux Redux: sampling patch для 1024×1024

Фрагмент повторяет ветвь `flux_redux_model_example`: `ModelSamplingFlux` использует `max_shift = 1,15`, `base_shift = 0,5`, ширину и высоту 1024, затем передаёт один изменённый `MODEL` в `BasicGuider` и `BasicScheduler(simple, 20, 1)`.

В полном графе размеры приходят от двух `PrimitiveNode`; здесь они зафиксированы в `settings`. Если семплирование идёт в другом разрешении, замените оба числа и заново проверьте соответствие модели.

`MODEL` и conditioning остаются внешними; sampler и latent не входят во фрагмент. Метод `patch` исполнен на подставной модели, но Flux-веса и полный граф не запускались. Редактор пока не проверил материал вручную.

## Источники

- [ModelSamplingFlux](https://github.com/Comfy-Org/ComfyUI/blob/c2bcbecd82ec5ae66594340b395c24ef0217b238/comfy_extras/nodes_model_advanced.py#L161-L196)
- [Граф Flux Redux](https://github.com/Comfy-Org/workflow_templates/blob/cca1ea5ea4560108ecc2f44dee951f41ea433062/templates/flux_redux_model_example.json)
