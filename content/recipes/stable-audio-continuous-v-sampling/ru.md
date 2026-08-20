# Stable Audio: явный continuous V sampling

Fragment ставит continuous V-prediction с `sigma_max = 500` и `sigma_min = 0,03`, затем строит `SIGMAS` через `BasicScheduler`. Эти границы взяты из системной конфигурации Stable Audio.

## Подключение

Подайте Stable Audio `MODEL`. Тот же patched выход используйте в guider. Conditioning, audio latent, sampler и VAE подключаются в своей части графа.

## Когда не применять

Официальный Stable Audio loader уже создаёт continuous V sampling с теми же границами. Не добавляйте patch автоматически: он нужен, если предыдущая нода заменила sampling или вы проводите контролируемый эксперимент.

## Границы проверки

Exact patch, тысячаточечная сетка и `atan/tan` conversion проверены без весов. Прямого patch-node case в official wheel нет; полный audio sampling не выполнялся. Редактор пока не проверил материал вручную.

## Источники

- [ModelSamplingContinuousV в ComfyUI v0.32.0](https://github.com/Comfy-Org/ComfyUI/blob/c2bcbecd82ec5ae66594340b395c24ef0217b238/comfy_extras/nodes_model_advanced.py#L242-L276)
- [Stable Audio sampling defaults](https://github.com/Comfy-Org/ComfyUI/blob/c2bcbecd82ec5ae66594340b395c24ef0217b238/comfy/supported_models.py#L584-L600)
