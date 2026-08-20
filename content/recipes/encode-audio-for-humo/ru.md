# Кодировать AUDIO через Whisper для HuMo

Fragment переносит точную пару нод и имя модели из `video_humo.json`: `AudioEncoderLoader` с `whisper_large_v3_fp16.safetensors` подаёт `AUDIO_ENCODER` в `AudioEncoderEncode`.

Подключите исходный `AUDIO` к внешнему входу. Выход `AUDIO_ENCODER_OUTPUT` направьте в совместимую HuMo conditioning-ноду; сам consumer не включён, чтобы рецепт не притворялся полным video workflow.

Для Wan S2V и InfiniteTalk нужны другие официальные encoder presets. Не меняйте Whisper на Wav2Vec2 только потому, что тип сокета совпадает.

Топология, имя файла, schema и безопасный fake-encoder вызов проверены. Реальные веса Whisper, HuMo model и рендер видео не запускались.
