# Trellis2 Shape Stage: подготовка разреженной формы

Переводит занятые воксели в координаты разреженного latent и готовит conditioning для этапа формы Trellis2. Сама нода не выполняет сэмплирование геометрии.

## Как пользоваться

На вход подаются структурный VOXEL и positive/negative от визуального conditioning. Создаётся пустой latent с 32 каналами и координатами занятых ячеек. Для координатной сетки до 32 выбирается режим shape_generation_512, для большей — shape_generation. Метаданные передаются вместе с тензором.

## Пример подключения

Соедините VaeDecodeStructureTrellis2 с этой нодой и направьте все три обновлённых выхода — positive, negative и latent — в sampler формы. После него VaeDecodeShapeTrellis покажет mesh, а Trellis2TextureStage сможет подготовить материал.

## Ограничения и частые ошибки

Пустая или неудачная структура не исправляется одним переключением этапа. Не теряйте координаты, подменяя выход обычным Empty Latent: разреженные samples без координат не описывают положение в пространстве. Веса sampler должны соответствовать выбранному этапу и масштабу.

## Входы и настройки

Снимок ComfyUI 0.37.0. Условные поля показаны вместе с режимом, в котором они доступны; список установленных моделей зависит от вашей системы.

| Вход | Тип | Обязательный | Значения из схемы |
| --- | --- | --- | --- |
| `positive` | `CONDITIONING` | да | соединение / значение без фиксированного default |
| `negative` | `CONDITIONING` | да | соединение / значение без фиксированного default |
| `voxel` | `VOXEL` | да | соединение / значение без фиксированного default |

## Выходы

| Выход | Тип | Список |
| --- | --- | --- |
| `positive` | `CONDITIONING` | нет |
| `negative` | `CONDITIONING` | нет |
| `LATENT` | `LATENT` | нет |

## Проверенные источники и кейсы

В официальном шаблоне `3d_pixal3d_multi_views`: Граф: main (root). Входящие связи: `Pixal3DMultiViewConditioning`, `VaeDecodeStructureTrellis2`. Исходящие связи: `KSampler`, `Trellis2UpsampleStage`. Имя файла: `3d_pixal3d_multi_views.json`, пакет [workflow-templates-json 0.1.92](https://pypi.org/project/comfyui-workflow-templates-json/0.1.92/). SubgraphInput/Output обозначают границы подграфа. Это сохранённые связи; переключатели и внешние входы могут менять путь исполнения и значения виджетов. Полный запуск с весами здесь не выполнялся.

В официальном шаблоне `3d_pixal3d_trellis2_image_to_model`: Граф: main (root). Входящие связи: `ComfySwitchNode`, `VaeDecodeStructureTrellis2`. Исходящие связи: `KSampler`, `Trellis2UpsampleStage`. Имя файла: `3d_pixal3d_trellis2_image_to_model.json`, пакет [workflow-templates-json 0.1.92](https://pypi.org/project/comfyui-workflow-templates-json/0.1.92/). SubgraphInput/Output обозначают границы подграфа. Это сохранённые связи; переключатели и внешние входы могут менять путь исполнения и значения виджетов. Полный запуск с весами здесь не выполнялся.

[Реализация в ComfyUI 0.37.0](https://github.com/Comfy-Org/ComfyUI/blob/73c9bad4d21e7addbe1d13bc92eee0f1431b017d/comfy_extras/nodes_trellis2.py#L497-L562). Параметры сверены со снимком `/object_info` от 27 сентября 2026 года.

Статья прошла техническую и языковую подготовку; человеческое утверждение ещё не выполнено. Полная генерация с моделями в рамках этой проверки не запускалась.
