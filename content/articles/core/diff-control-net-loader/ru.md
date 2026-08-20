# DiffControlNetLoader: восстановить ControlNet из разностных весов

`DiffControlNetLoader` загружает файл из того же списка `controlnet`, но дополнительно требует базовую `MODEL`. Этот вход нужен для checkpoint, где сохранена разница относительно конкретной diffusion-модели, а не полный самостоятельный набор весов.

## MODEL участвует только в загрузке ControlNet

Нода передаёт `model` в `comfy.controlnet.load_controlnet(path, model)` и возвращает один `CONTROL_NET`. Исходная `MODEL` не патчится и не выходит из ноды.

Для sampling используйте ту же совместимую MODEL отдельной линией, а CONTROL_NET передайте в apply-ноду. Socket не создаёт скрытого соединения между loader и sampler.

## Difference weights складываются с базовыми

В ветви state dict с ключами `control_model.zero_convs...` loader ищет marker `difference`. Для ключей с префиксом `control_model.` он строит соответствующий ключ `diffusion_model.` и прибавляет tensor из state dict базовой модели. Эта ветвь определяется ключами, а не расширением файла.

Так восстанавливаются полные веса ControlNet. Это не смешивание двух готовых моделей с регулируемым коэффициентом: strength задаётся позже в `ControlNetApplyAdvanced`.

## Базовая модель должна совпадать с исходной

Diff-checkpoint рассчитан на определённую архитектуру и базовые веса. Совпадение типа `MODEL` недостаточно: порт не хранит имя checkpoint, размеры слоёв или версию, относительно которой вычислялась разница.

Неверная база может привести к несовпадению форм, отсутствующим ключам или численно бессмысленному результату. Используйте checkpoint, указанный автором diff-ControlNet.

## Обычный ControlNet не требует diff-loader

`DiffControlNetLoader` всегда принимает MODEL, но общий parser использует её именно там, где формат требует восстановления разности. Для самостоятельного ControlNet лишний вход не даёт преимуществ.

`ControlNetLoader` проще и точнее выражает обычный случай. Выбирайте diff-версию по формату файла и официальной схеме, а не потому, что в графе уже есть свободный выход MODEL.

## Файл берётся из общего списка controlnet

`control_net_name` показывает `models/controlnet`, `models/t2i_adapter` и дополнительные пути этой категории. Допустимы те же расширения checkpoint, что у обычного loader.

Отдельной папки `diff_controlnet` в core нет. Поэтому по расположению файла нельзя определить, нужен ли ему вход MODEL.

## Загрузка может временно занять больше памяти

При восстановлении difference weights source вызывает `load_models_gpu([model])`, получает state dict базовой модели и складывает подходящие tensors. Этот этап может загрузить MODEL на устройство ещё до sampling.

Точные затраты зависят от архитектуры, dtype и менеджера памяти. Статья не обещает, что diff-файл обязательно легче по VRAM во время загрузки.

## Обработка ошибки отличается от обычного loader

Обычный `ControlNetLoader` явно проверяет `None` и поднимает понятный `RuntimeError`. `DiffControlNetLoader` после общего вызова сразу возвращает результат без такой дополнительной проверки.

Нераспознанный файл всё равно пишет ошибку из общего loader, но сбой может проявиться позже на typed output или в apply/sampling. Смотрите первый traceback и log определения формата.

## Кэш учитывает MODEL и имя файла

Execution signature включает связь с upstream MODEL и `control_net_name`. Смена checkpoint в модельной ветви или другого имени ControlNet инвалидирует этот результат.

Содержимое файла отдельно не хэшируется: замена байтов под прежним именем не меняет собственный вход ноды. После такой замены нужна явная перезагрузка cache или процесса.

## В официальном wheel примеров нет

Сканирование 512 JSON, включая 496 root workflow и 272 `definitions.subgraphs`, не нашло ни одного exact `DiffControlNetLoader`. Значит, wheel 0.1.42 не подтверждает filename, базовую MODEL или downstream-настройки для этой ноды.

Embedded docs 0.5.9 содержит материал в каталоге `DiffControlnetLoader` с другим регистром буквы `n`. Он верно перечисляет два входа, но точный алгоритм difference weights описывает только pinned source.

## Fragment фиксирует границу ответственности

Рецепт принимает внешние MODEL, positive, negative, IMAGE и VAE. MODEL идёт только в `DiffControlNetLoader`; полученный CONTROL_NET вместе с остальными входами передаётся в `ControlNetApplyAdvanced` с нейтральными настройками 1 / 0 / 1.

Имя diff-файла оставлено placeholder, потому что официального case нет. Fragment прошёл проверку схемы, но checkpoint не загружался, восстановление весов и полный граф в ComfyUI не исполнялись. Редактор пока не проверил материал вручную.

## Источники

- [DiffControlNetLoader в ComfyUI v0.32.0](https://github.com/Comfy-Org/ComfyUI/blob/c2bcbecd82ec5ae66594340b395c24ef0217b238/nodes.py#L880-L894)
- [Восстановление difference weights](https://github.com/Comfy-Org/ComfyUI/blob/c2bcbecd82ec5ae66594340b395c24ef0217b238/comfy/controlnet.py#L807-L893)
- [Категория файлов controlnet](https://github.com/Comfy-Org/ComfyUI/blob/c2bcbecd82ec5ae66594340b395c24ef0217b238/folder_paths.py#L10-L38)
- [Execution cache по входной сигнатуре](https://github.com/Comfy-Org/ComfyUI/blob/c2bcbecd82ec5ae66594340b395c24ef0217b238/comfy_execution/caching.py#L82-L127)
- [Закреплённый wheel workflow templates 0.1.42](https://pypi.org/project/comfyui-workflow-templates-json/0.1.42/)
