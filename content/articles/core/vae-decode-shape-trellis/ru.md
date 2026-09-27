# VAE Decode Shape Trellis: поверхность из разреженного latent

Декодирует sampled shape-latent в MESH и служебные SHAPE_SUBDIVIDES. Последние сохраняют структуру декодирования формы для согласованного получения текстурных вокселей.

## Как пользоваться

Нужен VAE формы и latent с samples и разреженными координатами. Если указан coord_resolution, разрешение декодирования выводится из него; иначе используется настройка VAE. Для модельной системы z_up геометрия переводится в y_up, принятую в дальнейшей 3D-цепочке.

## Пример подключения

Подключите latent после sampler формы. Mesh отправьте в GetMeshInfo и RenderMesh для проверки силуэта. SHAPE_SUBDIVIDES сохраните для VaeDecodeTextureTrellis той же формы; текстурный этап запускайте от соответствующего shape-latent, а не другого seed.

## Ограничения и частые ошибки

SHAPE_SUBDIVIDES не являются UV-развёрткой или обычной subdivision-модификацией mesh. Их нельзя произвольно заменить данными другого объекта. Получение поверхности не означает готовый материал: для текстуры потребуются отдельная генерация, декодирование, UV и запекание.

## Входы и настройки

Снимок ComfyUI 0.37.0. Условные поля показаны вместе с режимом, в котором они доступны; список установленных моделей зависит от вашей системы.

| Вход | Тип | Обязательный | Значения из схемы |
| --- | --- | --- | --- |
| `samples` | `LATENT` | да | соединение / значение без фиксированного default |
| `vae` | `VAE` | да | соединение / значение без фиксированного default |

## Выходы

| Выход | Тип | Список |
| --- | --- | --- |
| `mesh` | `MESH` | нет |
| `shape_subdivides` | `SHAPE_SUBDIVIDES` | нет |

## Проверенные источники и кейсы

В официальном шаблоне `3d_pixal3d_multi_views`: Граф: main (root). Входящие связи: `KSampler`, `VAELoader`. Исходящие связи: `BakeTextureFromVoxel`, `GetMeshInfo`, `VaeDecodeTextureTrellis`. Имя файла: `3d_pixal3d_multi_views.json`, пакет [workflow-templates-json 0.1.92](https://pypi.org/project/comfyui-workflow-templates-json/0.1.92/). SubgraphInput/Output обозначают границы подграфа. Это сохранённые связи; переключатели и внешние входы могут менять путь исполнения и значения виджетов. Полный запуск с весами здесь не выполнялся.

В официальном шаблоне `3d_pixal3d_trellis2_image_to_model`: Граф: main (root). Входящие связи: `KSampler`, `VAELoader`. Исходящие связи: `BakeTextureFromVoxel`, `GetMeshInfo`, `VaeDecodeTextureTrellis`. Имя файла: `3d_pixal3d_trellis2_image_to_model.json`, пакет [workflow-templates-json 0.1.92](https://pypi.org/project/comfyui-workflow-templates-json/0.1.92/). SubgraphInput/Output обозначают границы подграфа. Это сохранённые связи; переключатели и внешние входы могут менять путь исполнения и значения виджетов. Полный запуск с весами здесь не выполнялся.

[Реализация в ComfyUI 0.37.0](https://github.com/Comfy-Org/ComfyUI/blob/73c9bad4d21e7addbe1d13bc92eee0f1431b017d/comfy_extras/nodes_trellis2.py#L116-L193). Параметры сверены со снимком `/object_info` от 27 сентября 2026 года.

Статья прошла техническую и языковую подготовку; человеческое утверждение ещё не выполнено. Полная генерация с моделями в рамках этой проверки не запускалась.
