# STRING-результат 3D-сервиса → Preview3D

Подключите внешний `STRING` к `model_file`. Путь должен указывать на 3D-файл, который интерфейс этой установки может получить через `/view` из каталога `output`; строка сама по себе не переносит байты и не скачивает модель с другого компьютера.

Такая связь встречается в 23 из 24 официальных `Preview3D`: предыдущие ноды Hunyuan, Meshy, Rodin и Tripo возвращают строку, а Preview остаётся конечной точкой. Камера и фон во всех этих случаях не подключены. Фрагмент сохраняет эту топологию, но не включает платный или сетевой генератор.

Внешний сервис, модель, WebGL и весь фрагмент не исполнялись. Редактор пока не проверил материал вручную.

## Источники

- [Backend Preview3D](https://github.com/Comfy-Org/ComfyUI/blob/c2bcbecd82ec5ae66594340b395c24ef0217b238/comfy_extras/nodes_load_3d.py#L87-L129)
- [Frontend Preview3D](https://github.com/Comfy-Org/ComfyUI_frontend/blob/6d6af63c00f132cd25dc29307fc56bd2c094fa22/src/extensions/core/load3d.ts#L475-L686)
- [Официальные шаблоны 0.1.42](https://github.com/Comfy-Org/workflow_templates/tree/cca1ea5ea4560108ecc2f44dee951f41ea433062/templates)
