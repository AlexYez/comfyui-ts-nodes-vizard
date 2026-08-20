# Увеличить кадры видео моделью RealESRGAN x4

Fragment повторяет все вычислительные связи официального workflow `utility-gan_upscaler` из пакета `0.1.42`.

## Что перенесено из официального примера

`LoadVideo` передаёт `VIDEO` в `GetVideoComponents`. Выход `images` идёт в `ImageUpscaleWithModel`, а `UpscaleModelLoader` загружает точный файл `RealESRGAN_x4plus.safetensors`. После 4× обработки кадров `CreateVideo` получает исходные `audio` и `fps`, затем `SaveVideo` сохраняет результат с `video/ComfyUI`, `format = auto` и `codec = auto`.

Имя входного видео заменено подсказкой, потому что демонстрационный `gan_input.mp4` не входит в пользовательскую установку. Остальная топология и настройки совпадают с JSON шаблона.

## Подготовка модели и памяти

Скачайте [официальный repack RealESRGAN x4](https://huggingface.co/Comfy-Org/Real-ESRGAN_repackaged/resolve/main/RealESRGAN_x4plus.safetensors) в `ComfyUI/models/upscale_models`, затем обновите список моделей. Модель увеличивает каждую сторону в четыре раза, поэтому один кадр создаёт примерно в 16 раз больше пикселей.

Tiled-проход снижает память активаций, но не размер полного output-буфера и видео-batch. Для длинного или крупного ролика сначала проверьте короткий фрагмент.

## Статус проверки

Семь соединений, типы портов, имя модели и настройки сохранения сверены с `/object_info` ComfyUI `0.32.0` и официальным workflow. Fragment прошёл структурную проверку. Модель не скачивалась, видео не обрабатывалось, полный workflow намеренно не приложен.
