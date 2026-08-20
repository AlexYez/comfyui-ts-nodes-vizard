# Сохранить MODEL, CLIP_VISION и VAE в одну контрольную точку

Подайте совместимые `MODEL`, `CLIP_VISION` и `VAE` в `ImageOnlyCheckpointSave`. Префикс `checkpoints/wizard-image-only` создаст файл вида `output/checkpoints/wizard-image-only_00001_.safetensors`.

Нода не проверяет совместимость и не загружает файл повторно. После записи проверьте хеш и ключи словаря весов, затем перенесите контрольную точку в `models/checkpoints` или зарегистрированный путь моделей и выполните отдельную пробную загрузку. `output/checkpoints` не является каталогом моделей загрузчика по умолчанию.

Фрагмент основан на точной схеме и исходнике; в 512 официальных файлах JSON такой ноды нет. Схема и передача аргументов общей функции сохранения проверены без настоящих весов. Фрагмент целиком не выполнялся. Редактор пока не проверил материал вручную.

Источники: [ImageOnlyCheckpointSave](https://github.com/Comfy-Org/ComfyUI/blob/c2bcbecd82ec5ae66594340b395c24ef0217b238/comfy_extras/nodes_video_model.py#L110-L123), [общая функция сохранения](https://github.com/Comfy-Org/ComfyUI/blob/c2bcbecd82ec5ae66594340b395c24ef0217b238/comfy_extras/nodes_model_merging.py#L170-L227).
