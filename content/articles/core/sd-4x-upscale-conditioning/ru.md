# SD_4XUpscale_Conditioning: условие для diffusion x4 upscaler

## 1. Что делает нода

`SD_4XUpscale_Conditioning` подготавливает `CONDITIONING` и пустой latent для модели Stable Diffusion x4 Upscaler. Она нормализует исходный `IMAGE`, уменьшает его до размера условного изображения, добавляет `concat_image` и `noise_augmentation` в positive/negative metadata и создаёт нулевой четырёхканальный тензор целевого размера.

Название содержит `4X`, но runtime позволяет менять `scale_ratio` от `0` до `10`. Корректность нестандартного коэффициента зависит от модели и размеров; сама нода проверяет только объявленный диапазон виджета.

## 2. Место в графе

На вход приходят low-resolution `IMAGE`, positive и negative `CONDITIONING`. Три выхода подключают к sampler, где `MODEL` должен относиться к семейству `SD_X4Upscaler`. После sampling latent декодируют подходящим VAE.

Обычный diffusion checkpoint не становится x4-upscaler от одной этой ноды. Специальная модель читает `concat_image` и `noise_augmentation`; для других архитектур эти metadata могут быть бессмысленны или несовместимы.

## 3. Входы

- `images` (`IMAGE`) — исходный batch `[B, H, W, C]`.
- `positive`, `negative` (`CONDITIONING`) — две текстовые ветви, к которым добавляется одно изображение-условие.
- `scale_ratio` (`FLOAT`) — коэффициент целевой ширины и высоты; default `4.0`, диапазон `0.0…10.0`, шаг `0.01`.
- `noise_augmentation` (`FLOAT`) — уровень шумовой аугментации, записываемый в metadata; default `0.0`, диапазон `0.0…1.0`, шаг `0.001`, advanced widget.

Все пять входов находятся в `input.required`. Defaults принадлежат виджетам и не означают, что backend-вызов может опустить аргументы.

## 4. Выходы

- `positive` и `negative` (`CONDITIONING`) — исходные тензоры conditioning с поверхностно скопированными metadata, дополненными `concat_image` и `noise_augmentation`.
- `latent` (`LATENT`) — словарь с нулевым `samples` формы `[B, 4, target_h // 4, target_w // 4]`, где target вычисляется из исходного размера и `scale_ratio`.

В закреплённом исходнике нулевой тензор создаётся без явных `device` и `dtype`, то есть в стандартном вызове PyTorch это CPU `float32`. Перенос и приведение при дальнейшем sampling выполняют другие части pipeline.

## 5. Как работает внутри

Целевая ширина равна `max(1, round(W × scale_ratio))`, высота вычисляется так же. Изображение переводится из `[0, 1]` в `[-1, 1]`, переставляется в BCHW и передаётся в `common_upscale` с режимом `bilinear`, crop `center` и размером `target_w // 4 × target_h // 4`.

Получившийся тензор становится `concat_image` обеих ветвей. `noise_augmentation` сохраняется рядом как число; сама нода шум не генерирует. В классе `SD_X4Upscaler` это число позже превращается в дискретный noise level через `round(350 × value)`, а шум добавляется только при уровне больше нуля, с производным seed `seed - 10`.

Пустой latent создаётся отдельно с теми же batch и пространственными размерами, что и условное изображение. Это специализированный контракт x4-upscaler, его не следует переносить на обычное правило размера VAE latent.

## 6. Настройки

Для модели x4 начните с `scale_ratio = 4.0`. При исходном `W × H` нода сначала округляет `W × ratio` и `H × ratio`, затем использует целочисленное деление результата на четыре. Поэтому итоговое пространственное измерение latent может не совпасть с простым умножением при дробном ratio и малых размерах.

`noise_augmentation = 0.0` означает, что model consumer не добавляет шум к low-resolution условию. Увеличение параметра меняет не sampler noise напрямую, а специальное условие x4-модели. Подбирайте его под checkpoint и задачу, не путайте с `denoise` у `KSampler`.

Хотя runtime widget допускает `scale_ratio = 0`, эта граница небезопасна: после деления целевого размера на четыре `common_upscale` получает нулевую ширину и высоту. Exact-source probe воспроизвёл `ZeroDivisionError`. Используйте положительный коэффициент, при котором обе величины после `// 4` остаются не меньше единицы.

## 7. Пример подключения

Recipe `recipe.sd-4x-upscale-conditioning` подаёт low-resolution image и две внешние ветви в ноду, затем соединяет её `positive`, `negative` и `latent` с `KSampler`. `MODEL` остаётся внешним и явно обозначен как SD x4 model. У fragment `scale_ratio = 4.0`, `noise_augmentation = 0.0`; sampler settings приведены как стартовые, а не как официальный preset.

В полном wheel `0.1.42` exact NodeId отсутствует во всех корневых графах и subgraphs, поэтому fragment выведен из node и model-consumer source. Model-free probe для batch `[2, 5, 7, 3]` подтвердил условное изображение `[2, 3, 5, 7]`, latent `[2, 4, 5, 7]`, metadata `0.125` и CPU-выход. С настоящей x4-моделью fragment не запускался.

## 8. Частые ошибки

- Подключить обычный Stable Diffusion checkpoint вместо специализированного `SD_X4Upscaler`.
- Считать `noise_augmentation` тем же параметром, что sampler `denoise`.
- Утверждать, что нода уже добавила шум к пикселям. Она только записывает уровень; шум создаёт модель позже.
- Использовать `scale_ratio = 0` или слишком малое значение: целевой размер для `common_upscale` станет нулевым.
- Ожидать, что любой дробный ratio даст точный вещественный масштаб. В формуле есть `round` и `// 4`.
- Забыть декодировать выход sampler подходящим VAE после этого fragment.

## 9. Ограничения и производительность

Нода выполняет bilinear resize всего batch на CPU или устройстве входного тензора, а затем создаёт новый CPU latent `float32`. Память растёт с batch и целевой площадью `round(W × ratio) × round(H × ratio)`, хотя условное изображение и latent имеют размеры, делённые на четыре.

Это не tiled upscaler: разбиения на фрагменты и контроля пиков памяти нет. Границы виджета не гарантируют пригодность результата для модели. Формат рассчитан на конкретный model consumer и не заменяет универсальные image/latent upscale-ноды.

## 10. Совместимость и источники

Материал проверен на ComfyUI `0.32.0`, commit `c2bcbecd82ec5ae66594340b395c24ef0217b238`; fingerprint runtime-схемы — `sha256:fefa8870b9ff721d3cc91bf7b409e9dd2cf6c8a5312ea2de18d8929f3aa183d5`. Реализация: [`comfy_extras/nodes_sdupscale.py`, строки 7–52](https://github.com/Comfy-Org/ComfyUI/blob/c2bcbecd82ec5ae66594340b395c24ef0217b238/comfy_extras/nodes_sdupscale.py#L7-L52). Model consumer: [`comfy/model_base.py`, строки 642–676](https://github.com/Comfy-Org/ComfyUI/blob/c2bcbecd82ec5ae66594340b395c24ef0217b238/comfy/model_base.py#L642-L676).

Embedded docs `0.5.9` использованы как вторичный обзор, но их фраза о добавлении шума самой нодой уточнена по source: здесь сохраняется только scalar. В 512 JSON official wheel `0.1.42` прямых случаев нет. Статья `draft/in_review`; full inference, GPU profile и human approval ещё не выполнены.
