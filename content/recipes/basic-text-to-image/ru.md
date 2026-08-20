# Базовая генерация изображения из текста

Этот рецепт собирает минимальную исполняемую цепочку: загружает checkpoint, кодирует положительный и отрицательный текст, создаёт пустой latent, выполняет сэмплирование, декодирует результат и сохраняет PNG.

## Перед запуском

Импортированный workflow содержит имя-заглушку `put_your_checkpoint_here.safetensors`. Откройте `CheckpointLoaderSimple` и выберите файл, который доступен в вашей установке. Сам checkpoint в JSON не входит.

Размер примера — 512 × 512. Это демонстрационное значение, а не требование ComfyUI или рекомендация для любой архитектуры. Выберите разрешение, которое поддерживает ваша модель и доступная память.

## Соединения

1. `CheckpointLoaderSimple.MODEL` → `KSampler.model`.
2. `CheckpointLoaderSimple.CLIP` → два входа `CLIPTextEncode.clip`.
3. Выходы двух `CLIPTextEncode` → `KSampler.positive` и `KSampler.negative`.
4. `EmptyLatentImage.LATENT` → `KSampler.latent_image`.
5. `KSampler.LATENT` → `VAEDecode.samples`.
6. `CheckpointLoaderSimple.VAE` → `VAEDecode.vae`.
7. `VAEDecode.IMAGE` → `SaveImage.images`.

## Проверка результата

Для первого запуска оставьте `denoise = 1.0`. Значения `steps = 20`, `cfg = 7.0`, `sampler_name = euler` и `scheduler = normal` служат проверочным профилем. После успешного запуска фиксируйте seed и меняйте по одному параметру.

PNG появится в выходном каталоге в подпапке `wizard/<дата>/`. Если очередь завершается ошибкой до `SaveImage`, сначала проверьте выбранный checkpoint и совместимость его компонентов с двумя `CLIPTextEncode` и `VAEDecode`.

## Фрагмент и полный workflow

`fragment.json` описывает смысловой участок «loader → sampler → decode → save» и явно перечисляет три внешних входа: положительное условие, отрицательное условие и исходный latent. Это формат Nodes Wizard для статьи, а не файл, который ComfyUI импортирует напрямую.

`basic-text-to-image.workflow.json` — полный workflow формата ComfyUI `0.4`. Его можно импортировать в интерфейс и затем выбрать локальный checkpoint.

## Источники

- [Официальный Basic API example](https://github.com/Comfy-Org/ComfyUI/blob/v0.32.0/script_examples/basic_api_example.py)
- [Определения core-нод ComfyUI v0.32.0](https://github.com/Comfy-Org/ComfyUI/blob/v0.32.0/nodes.py)
