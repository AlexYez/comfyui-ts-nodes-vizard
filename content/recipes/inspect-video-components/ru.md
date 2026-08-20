# Разобрать VIDEO и собрать его компоненты

Подключите внешний `VIDEO` к `GetVideoComponents`, затем проведите все четыре выхода в `CreateVideo`. Так сохраняются кадры, звук, средняя частота и объявленная глубина кодирования.

Для объекта, только что созданного через `CreateVideo`, эта пара не кодирует данные. Для файла первая нода декодирует все кадры и звук в память; повторное сохранение через `SaveVideo` уже будет отдельной операцией с возможным H.264-сжатием.

Это не прозрачный обратный проход: `GetVideoComponents` не выводит поле alpha и не переносит метаданные контейнера в новый `VideoFromComponents`. Фрагмент показывает проводку компонентов, а не безусловно побитовое восстановление файла.

Редактор пока не проверил материал вручную.

### Источники

- [GetVideoComponents и CreateVideo в ComfyUI v0.32.0](https://github.com/Comfy-Org/ComfyUI/blob/c2bcbecd82ec5ae66594340b395c24ef0217b238/comfy_extras/nodes_video.py#L152-L217)
- [Официальный SeedVR2 workflow](https://github.com/Comfy-Org/workflow_templates/blob/cca1ea5ea4560108ecc2f44dee951f41ea433062/templates/utility_seedvr2_3b_int8_upscale_video.json)
