# Провести Stable Cascade через Stage C и Stage B

Fragment повторяет центральную ветвь официального text-to-image примера. `StableCascade_EmptyLatentImage` создаёт пару пустых latent. Первый `KSampler` заполняет `stage_c`, затем `StableCascade_StageB_Conditioning` записывает этот prior в positive conditioning второго sampler. Выход `stage_b` служит начальным latent для Stage B.

## Подключение

Подайте модель Stage C, positive и negative в первый sampler. К входу `conditioning` ноды подготовки Stage B подключите то же исходное positive conditioning, которое использовано для Stage C. Для второго sampler нужны модель Stage B и negative conditioning из той же текстовой ветви.

После `sample_b` подключите `VAEDecode` и VAE из checkpoint Stage B. Не меняйте местами модели двух стадий: одинаковый тип сокета `MODEL` не означает одинаковый внутренний формат.

## Настройки из официального примера

Пустая пара имеет размер `1024 × 1024`, `compression = 42`, batch `1`. Stage C использует 20 шагов, CFG `4`, `euler_ancestral`, `simple`, denoise `1`; Stage B — 10 шагов, CFG `1.1` и те же sampler и scheduler. Числа seed сохранены из PNG, но клиентская политика обоих seed в исходном графе стоит на `randomize`.

## Границы проверки

Топология и widgets извлечены из workflow-метаданных официального PNG на закреплённом commit. Fragment и отдельные tensor-ветви проверены без весов. Полная пара моделей Stable Cascade не запускалась, редактор ещё не утверждал материал вручную.

## Источники

- [Официальный Stable Cascade text-to-image workflow](https://github.com/comfyanonymous/ComfyUI_examples/blob/f9431bb000ce792094ff345446e22cac1ea6cef3/stable_cascade/stable_cascade__text_to_image.png)
- [Реализация Stable Cascade в ComfyUI 0.32.0](https://github.com/Comfy-Org/ComfyUI/blob/c2bcbecd82ec5ae66594340b395c24ef0217b238/comfy_extras/nodes_stable_cascade.py#L27-L148)
