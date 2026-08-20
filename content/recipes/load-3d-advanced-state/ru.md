# Load3DAdvanced: передать FILE_3D, камеру и размеры

Выберите 3D-модель в `model_file`, выставьте камеру и гизмо в окне просмотра. При запуске интерфейс сериализует `camera_info` и `model_3d_info`, а сервер вернёт их вместе с исходным `FILE_3D` и размерами 1024 × 1024.

Подключайте только нужные выходы к внешним нодам. Фрагмент не содержит вымышленных значений `viewport_state`: это состояние создаёт живой виджет. В официальном пакете шаблонов 0.1.42 точного `Load3DAdvanced` нет, поэтому топология основана на схеме и закреплённом коде, а не на шаблоне.

При `none` выход `model_3d` пуст. Не подключайте такой результат к обязательному входу `FILE_3D`. Просмотрщик и весь фрагмент не исполнялись. Редактор пока не проверил материал вручную.

## Источники

- [Backend Load3DAdvanced](https://github.com/Comfy-Org/ComfyUI/blob/c2bcbecd82ec5ae66594340b395c24ef0217b238/comfy_extras/nodes_load_3d.py#L323-L383)
- [Frontend state serialization](https://github.com/Comfy-Org/ComfyUI_frontend/blob/6d6af63c00f132cd25dc29307fc56bd2c094fa22/src/extensions/core/load3dAdvanced.ts#L22-L103)
- [Официальные шаблоны 0.1.42](https://github.com/Comfy-Org/workflow_templates/tree/cca1ea5ea4560108ecc2f44dee951f41ea433062/templates)
