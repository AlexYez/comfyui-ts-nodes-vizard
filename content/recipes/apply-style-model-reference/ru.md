# Добавить Flux Redux-токены одного референса

Загрузите официальную пару `sigclip_vision_patch14_384.safetensors` и `flux1-redux-dev.safetensors`. Reference IMAGE кодируется с center crop, а `StyleModelApply` добавляет полученные токены к внешнему Flux CONDITIONING в режиме multiply со strength 1.

Socket `CONDITIONING` не проверяет размерность. Для этого fragment нужен Flux tensor ширины 4096; conditioning другого семейства может пройти type check и упасть при конкатенации.

Топология и widgets взяты из первой reference-ветви официального `flux_redux_model_example`. Fragment прошёл schema check, но веса не загружались и граф в ComfyUI не исполнялся. Редактор пока не проверил материал вручную.

## Источники

- [Style model loader и apply в ComfyUI v0.32.0](https://github.com/Comfy-Org/ComfyUI/blob/c2bcbecd82ec5ae66594340b395c24ef0217b238/nodes.py#L1097-L1174)
- [Официальный Flux Redux workflow](https://github.com/Comfy-Org/workflow_templates/blob/cca1ea5ea4560108ecc2f44dee951f41ea433062/templates/flux_redux_model_example.json)
