# Загрузить diff-ControlNet с его базовой MODEL

Подайте точную базовую MODEL в `DiffControlNetLoader`. Нода использует её при восстановлении difference weights и выдаёт отдельный CONTROL_NET; MODEL для sampler нужно провести собственной ветвью.

После loader фрагмент использует `ControlNetApplyAdvanced` с 1 / 0 / 1. Эти значения только показывают полную область действия и не подтверждены официальным diff-workflow.

В 512 JSON wheel 0.1.42 exact `DiffControlNetLoader` отсутствует. Fragment прошёл проверку схемы, но diff-checkpoint не загружался, веса не восстанавливались и ComfyUI-граф не исполнялся. Редактор пока не проверил материал вручную.

## Источники

- [DiffControlNetLoader в ComfyUI v0.32.0](https://github.com/Comfy-Org/ComfyUI/blob/c2bcbecd82ec5ae66594340b395c24ef0217b238/nodes.py#L880-L894)
- [Восстановление difference weights](https://github.com/Comfy-Org/ComfyUI/blob/c2bcbecd82ec5ae66594340b395c24ef0217b238/comfy/controlnet.py#L850-L863)
