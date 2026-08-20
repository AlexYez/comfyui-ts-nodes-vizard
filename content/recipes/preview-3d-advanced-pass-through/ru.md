# FILE_3D → Preview3DAdvanced со сквозными выходами

Подайте внешний `FILE_3D` на `model_3d`. Живой виджет интерфейса сформирует `viewport_state`; сервер скопирует модель в `temp` для просмотра и вернёт исходный объект вместе с камерой, трансформацией и размерами 1024 × 1024.

Необязательные входы намеренно не подключены: камера и сведения о модели берутся из `viewport_state`. Если нужна внешняя камера, подключите её отдельно — она имеет приоритет. В официальном пакете шаблонов 0.1.42 точного типа нет, поэтому фрагмент основан на закреплённой схеме и коде. Он не содержит `SaveGLB` и не создаёт постоянный файл в `output`.

Синтетически проверена только серверная ветка копирования в `temp`. WebGL и весь фрагмент не исполнялись. Редактор пока не проверил материал вручную.

## Источники

- [Backend Preview3DAdvanced](https://github.com/Comfy-Org/ComfyUI/blob/c2bcbecd82ec5ae66594340b395c24ef0217b238/comfy_extras/nodes_load_3d.py#L132-L190)
- [Frontend lifecycle](https://github.com/Comfy-Org/ComfyUI_frontend/blob/6d6af63c00f132cd25dc29307fc56bd2c094fa22/src/extensions/core/load3d.ts#L688-L892)
- [Официальные шаблоны 0.1.42](https://github.com/Comfy-Org/workflow_templates/tree/cca1ea5ea4560108ecc2f44dee951f41ea433062/templates)
