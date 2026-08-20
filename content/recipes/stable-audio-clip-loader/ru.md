# T5 Base для Stable Audio

Структура взята из official `audio_stable_audio_example`: `CLIPLoader` № 10 с `t5-base.safetensors`, `stable_audio`, `default` двумя связями питает положительный и отрицательный `CLIPTextEncode`. Текст положительного prompt переведён и сокращён; пустой negative сохранён.

Два выхода `CONDITIONING` ещё не образуют полный аудиограф. В исходном workflow они получают временные параметры через `ConditioningStableAudio`, после чего используются sampler вместе с audio-моделью и latent. Не подключайте этот fragment к произвольной image-модели только из-за совпадения типа порта.

Проверены настройки, номера и типы связей official JSON и runtime-схема ComfyUI 0.32.0. Файл T5 и diffusion-модель в тестовом окружении не загружались, звук не генерировался.
