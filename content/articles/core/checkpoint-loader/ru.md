# CheckpointLoader (DEPRECATED): checkpoint с YAML-конфигурацией

## Назначение

`CheckpointLoader` загружает checkpoint и отдельный YAML-файл, возвращая `MODEL`, `CLIP` и `VAE`. Нода оставлена для старых графов и прямо помечена `DEPRECATED` в ComfyUI 0.32.0. Для нового обычного checkpoint сначала рассматривайте `CheckpointLoaderSimple`.

Название создаёт впечатление, что YAML полностью определяет архитектуру при загрузке. В текущем коде это уже не так: модель сначала распознаётся автоматическим детектором, а config затем используется для двух legacy-коррекций.

## Место в графе

Три выхода занимают то же место, что результаты обычного checkpoint loader: `MODEL` идёт в sampler или model patches, `CLIP` — в кодирование prompt, `VAE` — в encode/decode.

Нода оправдана при воспроизведении старого workflow, где YAML задаёт `parameterization: v` или `cond_stage_config.params.layer_idx`. Если таких требований нет и checkpoint определяется автоматически, дополнительный config только усложняет переносимость.

## Входы

`config_name` выбирает `.yaml` из `models/configs` и дополнительных путей категории `configs`. `ckpt_name` выбирает поддержанный tensor-файл из `models/checkpoints`.

Оба combo динамические. В чистом snapshot без моделей и config они пусты. Wizard показывает локальные значения из `/object_info`; статья не закрепляет имена файлов, которые отсутствуют у другого пользователя.

## Выходы

`MODEL` — распознанная diffusion-модель в patcher-объекте. `CLIP` — найденный в checkpoint текстовый энкодер. `VAE` — найденный VAE. Если checkpoint не содержит нужного компонента или его формат не поддержан, общий загрузчик может вернуть ошибку раньше, чем будет разобран YAML.

Нода не выдаёт config как отдельный объект и не сохраняет его для последующих нод. Его эффект применяется внутри вызова.

## Как работает

Сначала `comfy.sd.load_checkpoint_guess_config` читает checkpoint и автоматически определяет модель, CLIP и VAE. Только после этого `load_checkpoint` открывает YAML. Из `config['model']['params']` код проверяет `parameterization`; значение `v` заменяет model-sampling объекта на вариант V-prediction.

Затем из `cond_stage_config.params.layer_idx` при наличии берётся индекс слоя и вызывается `clip.clip_layer(layer_idx)`. Другие поля YAML в этой функции не строят архитектуру заново. Это существенное отличие ComfyUI 0.32.0 от общего описания в embedded docs.

## Параметры и настройка

Config должен быть валидным YAML с ожидаемой legacy-структурой `model.params.cond_stage_config`. Даже если нужны только выходы обычного checkpoint, неполный файл может завершить выполнение ошибкой доступа к ключу.

Не выбирайте случайный config «похожей» модели. Если старый граф зависит от V-prediction или остановки CLIP на определённом слое, перенесите exact YAML вместе с checkpoint. При миграции сравните эти два эффекта отдельно: автоматический `CheckpointLoaderSimple` не обязан воспроизводить внешнее переопределение.

## Проверенный пример

Рецепт «Диагностическая загрузка checkpoint с YAML» содержит одну legacy-ноду с явными placeholders для `config_name` и `ckpt_name`. Перед вставкой пользователь должен выбрать существующую согласованную пару. Fragment не предлагает вымышленный универсальный config.

В official workflow templates JSON 0.1.42 `CheckpointLoader` не найден ни в корневых графах, ни внутри subgraph. Поэтому пример основан на точном runtime-контракте и source path, а не назван официальным кейсом. Файлы не загружались и выходы не исполнялись.

## Частые ошибки

**Config не виден.** В baseline категория принимает `.yaml` из `models/configs`; проверьте расширение и model paths.

**Checkpoint определяется, но затем возникает ошибка YAML.** Файл не содержит ожидаемых `model.params` или `cond_stage_config`.

**Ожидают, что config заставит загрузить неизвестную архитектуру.** В 0.32.0 autodetection происходит до чтения YAML; неподдержанный checkpoint не спасается внешним config.

**После замены на Simple меняется результат.** Проверьте `parameterization: v` и `layer_idx`: это два реально используемых legacy-поля.

**Нода исчезла после обновления.** Она deprecated; сохраните версию окружения и план миграции до обновления production-графа.

## Ограничения и производительность

Основная стоимость — чтение полного checkpoint и создание трёх компонентов. YAML почти не влияет на время, но добавляет ещё одну внешнюю зависимость. Память определяется моделью, CLIP, VAE и политикой offload.

Deprecated-статус означает риск удаления, а не немедленную неисправность. Автоматической записи для `CheckpointLoader` в Node Replacement API baseline нет. `CheckpointLoaderSimple` — практическая альтернатива, но миграция требует проверить два legacy-переопределения вручную.

## Совместимость и источники

Статья сверена с `/object_info`, `nodes.py` и `comfy/sd.py` ComfyUI 0.32.0 на commit `c2bcbecd82ec5ae66594340b395c24ef0217b238`. Полный проход по 512 JSON official workflow package 0.1.42 не нашёл эту ноду.

Русский embedded-документ 0.5.9 верно перечисляет входы, выходы и deprecated-статус, но утверждение, что config определяет архитектуру, не соответствует текущей последовательности кода. В 0.32.0 архитектура сначала определяется по checkpoint; YAML меняет V-prediction и CLIP layer.

- [Реализация `CheckpointLoader`](https://github.com/Comfy-Org/ComfyUI/blob/c2bcbecd82ec5ae66594340b395c24ef0217b238/nodes.py#L595-L611)
- [Текущий `load_checkpoint` с legacy config](https://github.com/Comfy-Org/ComfyUI/blob/c2bcbecd82ec5ae66594340b395c24ef0217b238/comfy/sd.py#L2010-L2032)
- [Пути `checkpoints` и `configs`](https://github.com/Comfy-Org/ComfyUI/blob/c2bcbecd82ec5ae66594340b395c24ef0217b238/folder_paths.py#L24-L27)
- [Official workflow templates JSON 0.1.42](https://pypi.org/project/comfyui-workflow-templates-json/0.1.42/)
