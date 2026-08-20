# Управлять шириной двух latent-нод

Создайте две `EmptyLatentImage`. Дважды щёлкните по widget-входу `width` первой ноды: frontend добавит `PrimitiveNode`, подключит её и создаст числовой виджет. Проведите второй выходной link от той же Primitive к `width` второй ноды.

Установите значение `512` и оставьте control after generate в режиме `fixed`. Теперь перед очередью frontend перенесёт 512 в оба целевых виджета. Высоту и `batch_size` можно менять независимо.

Обе цели принимают `INT` с одинаковыми ограничениями, поэтому их конфигурации совместимы. Если второй вход потребует другой тип или диапазоны не будут пересекаться, связь не создастся. Не пытайтесь подключить Primitive к выходу `LATENT`: это не widget-вход.

В официальном `sdxl_simple_example` похожий рисунок используется для `steps`: PrimitiveNode № 45 передаёт значение двум `KSamplerAdvanced`. Учебный пример использует `EmptyLatentImage`, чтобы не требовать модель и показать механику на коротком графе.

Полный workflow и его структурированный fragment прошли проверку. Пример не был исполнен в живом ComfyUI, поэтому он остаётся редакционным черновиком до ручной проверки.

## Источники

- [Реализация PrimitiveNode](https://github.com/Comfy-Org/ComfyUI_frontend/blob/6d6af63c00f132cd25dc29307fc56bd2c094fa22/src/extensions/core/widgetInputs.ts#L31-L235)
- [Официальный workflow `sdxl_simple_example`](https://github.com/Comfy-Org/workflow_templates/blob/cca1ea5ea4560108ecc2f44dee951f41ea433062/templates/sdxl_simple_example.json)
