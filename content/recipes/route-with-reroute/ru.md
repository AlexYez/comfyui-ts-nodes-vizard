# Развести LATENT через Reroute

Учебный workflow соединяет `EmptyLatentImage` со старой frontend-нодой `Reroute`, а от неё проводит две ветви к `RepeatLatentBatch`. Reroute определяет тип `LATENT` по входящей связи и ничего не меняет в данных.

Пример намеренно хранит `type: "Reroute"` в массиве нод. Он нужен для статьи о точном старом class type и для проверки миграции. При открытии frontend 1.48.7 может предложить преобразовать ноду в native reroute point. Сохраните исходный файл, согласитесь на миграцию и убедитесь, что обе ветви остались подключены.

Для нового графа используйте `Add Reroute` в контекстном меню существующей линии. Эта команда создаёт native точку, а не ещё одну ноду `Reroute`. Не составляйте `extra.reroutes` вручную: формат связан с ID линий и поддерживается самим холстом.

Если попытаться соединить LATENT с входом другого типа, reroute не станет преобразователем. Добавьте настоящую ноду преобразования и используйте точку только для маршрута.

Fragment фиксирует роли и типы без обещания безопасно вставить произвольный JSON в текущий граф. Полный workflow прошёл структурную проверку, но не открывался и не запускался в живом ComfyUI в рамках этого редакционного прогона.

## Источники

- [Реализация старой Reroute-ноды](https://github.com/Comfy-Org/ComfyUI_frontend/blob/6d6af63c00f132cd25dc29307fc56bd2c094fa22/src/extensions/core/rerouteNode.ts#L14-L296)
- [Современная команда Add Reroute](https://github.com/Comfy-Org/ComfyUI_frontend/blob/6d6af63c00f132cd25dc29307fc56bd2c094fa22/src/lib/litegraph/src/LGraphCanvas.ts#L6679-L6727)
- [Официальный workflow с разветвлением через старые Reroute](https://github.com/Comfy-Org/workflow_templates/blob/cca1ea5ea4560108ecc2f44dee951f41ea433062/templates/templates-all_in_one-image_edit_models.json)
