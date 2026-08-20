# Stable Cascade: shift 2 перед scheduler

Fragment патчит одну Stage C или Stage B модель значением `shift = 2` и передаёт её в `BasicScheduler`. Для второй стадии создайте отдельную ветвь с её собственным `MODEL`.

## Подключение

Подайте подходящий Stable Cascade `MODEL`. Используйте выход patch и в guider, и в scheduler. Не соединяйте одну модель одновременно с ветвями Stage C и Stage B.

## Настройки

`shift = 2` — default самой ноды, но не нейтральное значение: базовый fallback `StableCascadeSampling` равен 1. Для исходной cosine-кривой задайте 1 или уберите ручной patch. Ноль не используйте: он схлопывает сетку.

## Границы проверки

Exact-класс и 10 000 sigma проверены для shift 2 и 0 без весов. В official workflow wheel точной patch-ноды нет, модели Cascade не запускались. Редактор пока не проверил материал вручную.

## Источники

- [ModelSamplingStableCascade в ComfyUI v0.32.0](https://github.com/Comfy-Org/ComfyUI/blob/c2bcbecd82ec5ae66594340b395c24ef0217b238/comfy_extras/nodes_model_advanced.py#L91-L118)
- [StableCascadeSampling mathematics](https://github.com/Comfy-Org/ComfyUI/blob/c2bcbecd82ec5ae66594340b395c24ef0217b238/comfy/model_sampling.py#L349-L398)
