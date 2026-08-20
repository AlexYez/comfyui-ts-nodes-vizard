# Передать модель-зависимые SIGMAS в custom sampler

Подключите один и тот же выход `MODEL` после всех sampling-патчей к `BasicScheduler` и к ноде, из которой собран внешний `GUIDER`. В fragment стоят `simple`, 20 шагов и `denoise = 1` — те же значения, что у `BasicScheduler` №17 в официальном `flux_redux_model_example`.

Выход `SIGMAS` идёт во вход `sigmas` у `SamplerCustomAdvanced`. `NOISE`, `GUIDER`, `SAMPLER` и `LATENT` остаются внешними: fragment не загружает веса и поэтому не является полным workflow.

Связи прошли schema/runtime-проверку, а метод scheduler исполнен на подставном `model_sampling`. Настоящий sampler с моделью не запускался. Редактор пока не проверил материал вручную.

## Источники

- [BasicScheduler в ComfyUI v0.32.0](https://github.com/Comfy-Org/ComfyUI/blob/c2bcbecd82ec5ae66594340b395c24ef0217b238/comfy_extras/nodes_custom_sampler.py#L17-L44)
- [Официальный `flux_redux_model_example`](https://github.com/Comfy-Org/workflow_templates/blob/cca1ea5ea4560108ecc2f44dee951f41ea433062/templates/flux_redux_model_example.json)
